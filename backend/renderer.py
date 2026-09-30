"""Etapa de renderização: video_data.json (editado) -> MP4 9:16 com jump cuts e legendas animadas.

Estratégia anti-dessincronia (2 passes):
  1. Cada bloco "keep" vira um intermediário independente com duração EXATA de N frames:
     - fps racional exato (29.97 -> 30000/1001): com o valor arredondado a grade escorrega ~µs/frame
       e o seek pode descartar o primeiro frame do bloco;
     - seek de entrada cai NUM FRAME da grade, ~1s antes do bloco; o corte fino é feito por
       trim/atrim com meia margem de frame (sem ambiguidade de borda) sobre timestamps já em CFR;
     - vídeo fechado em N frames por trim=end_frame (tpad cobre fonte curta) e áudio no sample exato
       por atrim=end_sample (apad cobre). Os dois terminam DENTRO do filtro: "-frames:v"/"-t" encerram
       o arquivo quando o vídeo acaba e descartam o áudio ainda no pipeline (~20ms a menos por clipe);
     - intermediário MOV com timescale do próprio fps (MKV arredonda timestamps a 1ms) e áudio PCM
       (sem priming de AAC, que acumularia drift a cada emenda).
  2. Concat demuxer + legenda .ass + um único encode final (H.264 + AAC).
"""

import json
import shutil
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

from config import (
    AUDIO_RATE,
    FONTS_DIR,
    OUTPUT_FILENAME,
    OUTPUT_H,
    OUTPUT_W,
    RENDER_WORKERS,
    RENDERS_DIR,
    SUB_FONT,
    SUB_FONT_SIZE,
    SUB_MARGIN_V,
    SUB_OUTLINE,
    SUB_PRIMARY,
    SUB_SHADOW,
    TARGET_ASPECT,
    ZOOM_IN_AMOUNT,
)
from schemas import KeepClip, VideoData

_render_lock = threading.Lock()  # FFmpeg já satura a CPU: um render por vez


class RenderError(RuntimeError):
    pass


def exact_fps(fps: float) -> Fraction:
    """29.97 -> 30000/1001, 23.976 -> 24000/1001, 25.0 -> 25."""
    for base in (24, 30, 48, 60, 120):
        ntsc = Fraction(base * 1000, 1001)
        if abs(fps - float(ntsc)) < 0.002:
            return ntsc
    return Fraction(fps).limit_denominator(1001)


@dataclass
class Segment:
    """Bloco "keep" encaixado na grade de frames, com sua posição na linha do tempo final."""

    clip: KeepClip
    src_start: float  # s no vídeo original (múltiplo de 1/fps)
    frames: int
    out_start: float  # s no vídeo final

    def duration(self, fps: Fraction) -> float:
        return float(self.frames / fps)


def _run(cmd: list[str], cwd: Path | None = None) -> None:
    res = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RenderError(f"FFmpeg falhou ({Path(cmd[0]).name}): {res.stderr.strip()[-1500:]}")


def _ass_time(t: float) -> str:
    cs = max(0, int(round(t * 100)))
    h, cs = divmod(cs, 360_000)
    m, cs = divmod(cs, 6_000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _ass_escape(text: str) -> str:
    # { } abrem blocos de override e \ inicia tags: neutraliza para texto literal.
    return text.replace("\\", "/").replace("{", "(").replace("}", ")").replace("\n", " ")


def _word_size(word: str) -> int:
    """Palavras longas encolhem para caber na largura útil (sem quebra de linha: WrapStyle 2)."""
    usable = OUTPUT_W - 2 * 60
    est = len(word) * SUB_FONT_SIZE * 0.6  # largura média (conservadora) de glifo da Montserrat Black
    return SUB_FONT_SIZE if est <= usable else int(usable / (len(word) * 0.6))


def build_ass(segments: list[Segment], fps: Fraction) -> str:
    """Uma palavra por vez, visível exatamente entre start e end (remapeados para a linha do tempo final)."""
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {OUTPUT_W}
PlayResY: {OUTPUT_H}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Word,{SUB_FONT},{SUB_FONT_SIZE},{SUB_PRIMARY},&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,{SUB_OUTLINE},{SUB_SHADOW},2,60,60,{SUB_MARGIN_V},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = []
    for seg in segments:
        seg_end = seg.src_start + seg.duration(fps)
        for w in seg.clip.transcript:
            # Palavra recortada aos limites do bloco (o encaixe na grade pode ter aparado alguns ms).
            s, e = max(w.start, seg.src_start), min(w.end, seg_end)
            if e <= s or not w.word.strip():
                continue
            out_s = seg.out_start + (s - seg.src_start)
            out_e = seg.out_start + (e - seg.src_start)
            if round(out_e * 100) <= round(out_s * 100):
                out_e = out_s + 0.01
            # "Pop" de entrada: 80% -> 100% em 80ms.
            word = _ass_escape(w.word.strip())
            size = _word_size(word)
            text = (rf"{{\fs{size}}}" if size != SUB_FONT_SIZE else "") + r"{\fscx80\fscy80\t(0,80,\fscx100\fscy100)}" + word
            lines.append(f"Dialogue: 0,{_ass_time(out_s)},{_ass_time(out_e)},Word,,0,0,0,,{text}")
    return header + "\n".join(lines) + "\n"


class VideoRenderer:
    def __init__(self, data: VideoData, video_path: Path, video_id: str):
        self.data = data
        self.video_path = video_path
        self.fps = exact_fps(data.metadata.fps)
        self.out_dir = RENDERS_DIR / video_id
        self.work_dir = self.out_dir / "work"
        self.output_path = self.out_dir / OUTPUT_FILENAME

    # ── pipeline ────────────────────────────────────────────────────────
    def run(self) -> dict:
        t0 = time.monotonic()
        segments = self._plan()
        if not segments:
            raise RenderError("Nenhum bloco 'keep' com duração >= 1 frame.")

        with _render_lock:
            shutil.rmtree(self.work_dir, ignore_errors=True)
            self.work_dir.mkdir(parents=True)
            try:
                has_audio = self._has_audio()
                with ThreadPoolExecutor(RENDER_WORKERS) as pool:
                    parts = list(pool.map(lambda iv: self._render_segment(*iv, has_audio), enumerate(segments)))
                self._write_subtitles(segments)
                self._concat_and_burn(parts)
            finally:
                shutil.rmtree(self.work_dir, ignore_errors=True)

        total = sum(s.duration(self.fps) for s in segments)
        return {
            "output_path": str(self.output_path),
            "duration": round(total, 3),
            "clips": len(segments),
            "size_bytes": self.output_path.stat().st_size,
            "render_seconds": round(time.monotonic() - t0, 2),
        }

    # ── planejamento: grade de frames ───────────────────────────────────
    def _plan(self) -> list[Segment]:
        segments: list[Segment] = []
        cursor = 0.0
        for clip in self.data.timeline:
            if not isinstance(clip, KeepClip):
                continue
            f0 = round(clip.start_time * self.fps)
            f1 = round(clip.end_time * self.fps)
            if f1 <= f0:
                continue  # bloco menor que meio frame
            seg = Segment(clip=clip, src_start=float(f0 / self.fps), frames=f1 - f0, out_start=cursor)
            segments.append(seg)
            cursor += seg.duration(self.fps)
        return segments

    def _has_audio(self) -> bool:
        res = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index", "-of", "json", str(self.video_path)],
            capture_output=True, text=True,
        )  # fmt: skip
        return bool(json.loads(res.stdout or "{}").get("streams"))

    # ── passe 1: um intermediário por bloco keep ─────────────────────────
    def _crop_width(self) -> int:
        w, h = self.data.metadata.width, self.data.metadata.height
        return min(w, int(round(h * TARGET_ASPECT)) // 2 * 2)  # mesma regra do processor

    def _crop_filter(self, clip: KeepClip) -> str:
        w, h = self.data.metadata.width, self.data.metadata.height
        crop_w = self._crop_width()
        x = min(max(clip.crop_center_x - crop_w // 2, 0), w - crop_w)
        return f"crop=w={crop_w}:h={h}:x={x}:y=0"

    def _fit_filters(self) -> list[str]:
        ratio = self._crop_width() / self.data.metadata.height
        target = OUTPUT_W / OUTPUT_H
        if abs(ratio - target) / target < 0.02:
            # ~9:16 (crop par arredondado): preenche e apara <=2px, sem filete preto de pad.
            return [
                f"scale={OUTPUT_W}:{OUTPUT_H}:force_original_aspect_ratio=increase:flags=lanczos",
                f"crop={OUTPUT_W}:{OUTPUT_H}",
            ]
        # Bem mais estreito que 9:16 (ex.: gravação de tela 9:19.5): cabe inteiro, com barras.
        return [
            f"scale={OUTPUT_W}:{OUTPUT_H}:force_original_aspect_ratio=decrease:flags=lanczos",
            f"pad={OUTPUT_W}:{OUTPUT_H}:(ow-iw)/2:(oh-ih)/2",
        ]

    def _video_filter(self, seg: Segment, lead: int) -> str:
        fps, half = self.fps, 0.5 / self.fps
        chain = [
            f"fps={fps}",  # CFR: fontes VFR (celular) viram grade fixa de frames
            # frames [lead, lead+N) da grade pós-seek; ±meio frame torna a borda inequívoca
            f"trim=start={float(lead / fps - half):.6f}:end={float((lead + seg.frames) / fps - half):.6f}",
            "setpts=PTS-STARTPTS",
            self._crop_filter(seg.clip),
            *self._fit_filters(),
        ]
        if seg.clip.zoom_in:
            # zoompan arredonda x/y para pixels inteiros (tremido); superamostrar 2x suaviza.
            n = max(seg.frames - 1, 1)
            chain += [
                f"scale={OUTPUT_W * 2}:{OUTPUT_H * 2}:flags=bicubic",
                f"zoompan=z='1+{ZOOM_IN_AMOUNT}*on/{n}':x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2'"
                f":d=1:s={OUTPUT_W}x{OUTPUT_H}:fps={fps}",
            ]
        chain += [
            "tpad=stop_mode=clone:stop_duration=1",  # se a fonte acabar antes, repete o último frame
            f"trim=end_frame={seg.frames}",  # fecha em N frames exatos
            "setsar=1",
            "format=yuv420p",
        ]
        return ",".join(chain)

    def _render_segment(self, idx: int, seg: Segment, has_audio: bool) -> Path:
        out = self.work_dir / f"clip_{idx:04d}.mov"
        f0 = round(seg.src_start * self.fps)
        lead = min(f0, round(self.fps))  # ~1s de pré-rolagem, em frames inteiros
        seek = float((f0 - lead) / self.fps)
        a_start = float(lead / self.fps)
        n_samples = round(seg.frames / self.fps * AUDIO_RATE)
        cmd = [
            "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
            # -ss antes do -i: seek rápido; o ponto cai exatamente num frame da grade.
            "-ss", f"{seek:.6f}", "-i", str(self.video_path),
        ]  # fmt: skip
        if not has_audio:
            cmd += ["-f", "lavfi", "-i", f"anullsrc=r={AUDIO_RATE}:cl=stereo"]
        audio_in = "0:a:0" if has_audio else "1:a:0"
        cmd += [
            "-map", "0:v:0", "-map", audio_in,
            "-vf", self._video_filter(seg, lead),
            # async preenche buracos do áudio; apad cobre fonte curta; atrim fecha no sample exato de N frames.
            "-af", (
                f"aresample={AUDIO_RATE}:async=1:first_pts=0,atrim=start={a_start:.6f},asetpts=PTS-STARTPTS,"
                f"apad,atrim=end_sample={n_samples}"
            ),
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "12", "-g", str(max(1, round(self.fps))),
            "-c:a", "pcm_s16le", "-ar", str(AUDIO_RATE), "-ac", "2",
            str(out),
        ]  # fmt: skip
        _run(cmd)
        return out

    # ── passe 2: concat + legenda + encode final ─────────────────────────
    def _write_subtitles(self, segments: list[Segment]) -> None:
        ass = build_ass(segments, self.fps)
        (self.work_dir / "legenda_dinamica.ass").write_text(ass, encoding="utf-8")
        # Fontes copiadas para o work dir: fontsdir relativo evita escapar caminhos (C:\, :) no filtergraph.
        if FONTS_DIR.is_dir():
            shutil.copytree(FONTS_DIR, self.work_dir / "fonts", dirs_exist_ok=True)

    def _concat_and_burn(self, parts: list[Path]) -> None:
        listing = "".join(f"file '{p.name}'\n" for p in parts)
        (self.work_dir / "list.txt").write_text(listing, encoding="utf-8")
        tmp_out = self.out_dir / f".{OUTPUT_FILENAME}.part.mp4"
        subs = "ass=legenda_dinamica.ass" + (":fontsdir=fonts" if (self.work_dir / "fonts").is_dir() else "")
        cmd = [
            "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "concat", "-safe", "0", "-i", "list.txt",
            "-vf", subs,
            "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-profile:v", "high", "-pix_fmt", "yuv420p",
            "-r", f"{self.fps}",
            "-c:a", "aac", "-b:a", "192k", "-ar", str(AUDIO_RATE),
            "-movflags", "+faststart",
            str(tmp_out.resolve()),
        ]  # fmt: skip
        try:
            _run(cmd, cwd=self.work_dir)
        except RenderError:
            tmp_out.unlink(missing_ok=True)
            raise
        # atômico: nunca expõe um MP4 pela metade. No Windows o replace falha se o MP4 anterior ainda
        # estiver aberto (player/download em curso): tenta por alguns segundos antes de desistir.
        for attempt in range(10):
            try:
                tmp_out.replace(self.output_path)
                return
            except PermissionError as e:
                if attempt == 9:
                    tmp_out.unlink(missing_ok=True)
                    raise RenderError("O MP4 anterior está em uso (feche o player/download e renderize de novo).") from e
                time.sleep(0.5)

