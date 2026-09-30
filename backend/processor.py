"""Etapa de análise: vídeo original -> video_data.json (nenhum vídeo é renderizado aqui)."""

import json
import os
import statistics
import subprocess
import threading
import time
import uuid
import wave
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from config import (
    BASE_DIR,
    CUT_PADDING,
    FACE_DETECT_WIDTH,
    FACE_SAMPLE_INTERVAL,
    SILENCE_MIN_GAP,
    TARGET_ASPECT,
    WHISPER_MODEL,
)
from schemas import CutClip, KeepClip, VideoData, VideoMetadata, Word

SAMPLE_RATE = 16_000  # taxa nativa do Whisper

_models: dict = {}
_whisper_lock = threading.Lock()  # carregamento e inferência serializados
_whisper_status = {"state": "idle", "model": WHISPER_MODEL, "error": None, "load_seconds": None}


def whisper_status() -> dict:
    return dict(_whisper_status)


def _get_whisper(name: str):
    """Chamar com _whisper_lock. Na 1ª vez baixa o checkpoint (~140 MB no 'base') para ~/.cache/whisper."""
    if name not in _models:
        t0 = time.monotonic()
        _whisper_status.update(state="loading", model=name, error=None)
        print(f"[whisper] carregando modelo '{name}'…", flush=True)
        try:
            import whisper  # import tardio: torch é pesado e só é necessário aqui

            url = whisper._MODELS.get(name)
            if url:  # modelo oficial: load_model baixa para ~/.cache/whisper se ainda não estiver lá
                cache = Path(os.getenv("XDG_CACHE_HOME", Path.home() / ".cache")) / "whisper" / Path(url).name
                if not cache.exists():
                    print(f"[whisper] 1ª vez: baixando '{name}' para {cache.parent} (só acontece uma vez)…", flush=True)
            _models[name] = whisper.load_model(name)
        except Exception as e:
            _whisper_status.update(state="error", error=str(e))
            print(f"[whisper] falha ao carregar '{name}': {e}", flush=True)
            raise
        secs = round(time.monotonic() - t0, 1)
        _whisper_status.update(state="ready", load_seconds=secs)
        print(f"[whisper] modelo '{name}' pronto ({secs}s)", flush=True)
    return _models[name]


def preload_whisper(name: str = WHISPER_MODEL) -> None:
    """Aquece o modelo em background ao subir a API (a 1ª análise não paga download + load)."""
    try:
        with _whisper_lock:
            _get_whisper(name)
    except Exception:
        pass  # status "error" já registrado; a próxima análise tenta de novo


def _r(t: float) -> float:
    return round(t, 3)


class ProcessingError(RuntimeError):
    pass


@dataclass
class _Probe:
    width: int
    height: int
    fps: float
    duration: float
    has_audio: bool


class VideoProcessor:
    def __init__(
        self,
        video_path: Path,
        model_name: str = WHISPER_MODEL,
        language: str | None = None,
        min_gap: float = SILENCE_MIN_GAP,
        padding: float = CUT_PADDING,
    ):
        self.video_path = Path(video_path).resolve()
        self.model_name = model_name
        self.language = language
        self.min_gap = min_gap
        self.padding = padding
        self.output_path = self.video_path.with_suffix(".video_data.json")

    # ── pipeline ────────────────────────────────────────────────────────
    def run(self) -> VideoData:
        probe = self._probe()

        words: list[Word] = []
        if probe.has_audio:
            wav = self._extract_audio()
            try:
                words = self._transcribe(wav)
            finally:
                wav.unlink(missing_ok=True)

        segments = self._build_segments(words, probe.duration)
        keeps = [(s, e) for s, e, kind in segments if kind == "keep"]
        centers = self._crop_centers(keeps, probe)

        timeline: list[KeepClip | CutClip] = []
        keep_idx = 0
        for clip_id, (start, end, kind) in enumerate(segments, start=1):
            if kind == "keep":
                timeline.append(
                    KeepClip(
                        clip_id=clip_id,
                        start_time=_r(start),
                        end_time=_r(end),
                        crop_center_x=centers[keep_idx],
                        transcript=[w for w in words if start <= w.start < end],
                    )
                )
                keep_idx += 1
            else:
                timeline.append(CutClip(clip_id=clip_id, start_time=_r(start), end_time=_r(end)))

        data = VideoData(
            video_path=self._relative_path(),
            metadata=VideoMetadata(width=probe.width, height=probe.height, fps=_r(probe.fps)),
            timeline=timeline,
        )
        self.output_path.write_text(json.dumps(data.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")
        return data

    # ── 0. metadados ────────────────────────────────────────────────────
    def _probe(self) -> _Probe:
        cmd = ["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", "-show_format", str(self.video_path)]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            raise ProcessingError(f"ffprobe falhou: {res.stderr.strip()[-500:]}")
        info = json.loads(res.stdout)
        streams = info.get("streams", [])
        video = next((s for s in streams if s.get("codec_type") == "video"), None)
        if video is None:
            raise ProcessingError("Arquivo sem stream de vídeo.")

        width, height = int(video["width"]), int(video["height"])
        # Vídeos de celular: dimensões codificadas em paisagem + flag de rotação.
        # FFmpeg e OpenCV aplicam a rotação por padrão, então usamos a dimensão exibida.
        rotation = int(video.get("tags", {}).get("rotate", 0))
        for sd in video.get("side_data_list", []):
            rotation = int(sd.get("rotation", rotation))
        if abs(rotation) % 180 == 90:
            width, height = height, width

        num, den = (video.get("avg_frame_rate") or "0/1").split("/")
        fps = float(num) / float(den) if float(den) else 0.0
        if fps <= 0:
            num, den = video.get("r_frame_rate", "30/1").split("/")
            fps = float(num) / float(den)

        duration = float(info.get("format", {}).get("duration") or video.get("duration") or 0.0)
        has_audio = any(s.get("codec_type") == "audio" for s in streams)
        return _Probe(width, height, fps, duration, has_audio)

    # ── 1. extração de áudio ───────────────────────────────────────────
    def _extract_audio(self) -> Path:
        wav = self.video_path.parent / f"{self.video_path.stem}.{uuid.uuid4().hex[:6]}.wav"
        cmd = [
            "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(self.video_path),
            "-vn", "-ac", "1", "-ar", str(SAMPLE_RATE), "-c:a", "pcm_s16le",
            str(wav),
        ]  # fmt: skip
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            wav.unlink(missing_ok=True)
            raise ProcessingError(f"Extração de áudio falhou: {res.stderr.strip()[-500:]}")
        return wav

    # ── 2. transcrição ─────────────────────────────────────────────────
    def _transcribe(self, wav: Path) -> list[Word]:
        # Lê o WAV direto em memória: evita que o Whisper chame o FFmpeg de novo.
        with wave.open(str(wav), "rb") as f:
            pcm = f.readframes(f.getnframes())
        audio = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
        if audio.size == 0:
            return []

        import torch

        with _whisper_lock:
            try:
                model = _get_whisper(self.model_name)
            except Exception as e:  # download/checkpoint corrompido/sem rede
                raise ProcessingError(f"Falha ao carregar Whisper '{self.model_name}': {e}") from e
            result = model.transcribe(
                audio,
                word_timestamps=True,
                language=self.language,
                fp16=torch.cuda.is_available(),
            )

        words: list[Word] = []
        for seg in result.get("segments", []):
            for w in seg.get("words", []):
                text = w["word"].strip()
                if text:
                    words.append(Word(word=text, start=_r(w["start"]), end=_r(max(w["end"], w["start"]))))
        words.sort(key=lambda w: w.start)
        return words

    # ── 3. jump cuts ───────────────────────────────────────────────────
    def _build_segments(self, words: list[Word], duration: float) -> list[tuple[float, float, str]]:
        """Divide [0, duration] em blocos contíguos keep/cut a partir dos gaps entre palavras."""
        duration = max([duration, *(w.end for w in words)])
        if duration <= 0:
            return []
        if not words:
            return [(0.0, duration, "keep")]  # sem fala: não descarta o vídeo inteiro

        pad = self.padding
        cuts: list[tuple[float, float]] = []
        prev_end = 0.0
        for i, w in enumerate(words):
            if w.start - prev_end > self.min_gap:
                # Silêncio inicial não recebe padding à esquerda (não há fala antes).
                cuts.append((prev_end + (pad if i else 0.0), w.start - pad))
            prev_end = max(prev_end, w.end)
        if duration - prev_end > self.min_gap:
            cuts.append((prev_end + pad, duration))

        segments: list[tuple[float, float, str]] = []
        cursor = 0.0
        for cs, ce in cuts:
            if ce - cs <= 0:
                continue
            if cs > cursor:
                segments.append((cursor, cs, "keep"))
            segments.append((cs, ce, "cut"))
            cursor = ce
        if duration > cursor:
            segments.append((cursor, duration, "keep"))
        return segments

    # ── 4. smart crop 9:16 ─────────────────────────────────────────────
    def _crop_centers(self, keeps: list[tuple[float, float]], probe: _Probe) -> list[int]:
        crop_w = min(probe.width, int(round(probe.height * TARGET_ASPECT)) // 2 * 2)
        half = crop_w / 2
        default = probe.width / 2

        def clamp(cx: float) -> int:
            return int(round(min(max(cx, half), probe.width - half)))

        if crop_w >= probe.width:  # já é 9:16 ou mais estreito: nada a enquadrar
            return [clamp(default)] * len(keeps)

        # Amostras em ordem crescente de tempo: o seek do OpenCV só anda para frente.
        samples: list[tuple[float, int]] = []
        for idx, (s, e) in enumerate(keeps):
            t = s + FACE_SAMPLE_INTERVAL / 2
            block = []
            while t < e:
                block.append((t, idx))
                t += FACE_SAMPLE_INTERVAL
            samples.extend(block or [((s + e) / 2, idx)])
        samples.sort()

        cascade = cv2.CascadeClassifier(str(Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"))
        found: list[list[float]] = [[] for _ in keeps]
        cap = cv2.VideoCapture(str(self.video_path))
        if not cap.isOpened():
            raise ProcessingError("OpenCV não conseguiu abrir o vídeo.")
        try:
            for t, idx in samples:
                cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
                ok, frame = cap.read()
                if not ok:
                    continue
                cx = self._detect_face_x(frame, cascade)
                if cx is not None:
                    # Normaliza para a largura do probe (independe da resolução decodificada).
                    found[idx].append(cx * probe.width / frame.shape[1])
        finally:
            cap.release()

        # Mediana por bloco; blocos sem rosto herdam o vizinho mais próximo (continuidade de câmera).
        raw: list[float | None] = [statistics.median(xs) if xs else None for xs in found]
        last = None
        for i, v in enumerate(raw):
            raw[i] = last = v if v is not None else last
        nxt = None
        for i in range(len(raw) - 1, -1, -1):
            raw[i] = nxt = raw[i] if raw[i] is not None else nxt
        return [clamp(v if v is not None else default) for v in raw]

    @staticmethod
    def _detect_face_x(frame: np.ndarray, cascade: cv2.CascadeClassifier) -> float | None:
        h, w = frame.shape[:2]
        scale = min(1.0, FACE_DETECT_WIDTH / w)
        small = cv2.resize(frame, (int(w * scale), int(h * scale))) if scale < 1 else frame
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)  # sem equalizeHist: distorce rostos em fundos uniformes
        faces, _, weights = cascade.detectMultiScale3(
            gray, scaleFactor=1.1, minNeighbors=5, minSize=(24, 24), outputRejectLevels=True
        )
        if len(faces) == 0:
            return None
        # Maior confiança, não maior área: falsos positivos do Haar costumam ser grandes.
        (x, _, fw, _), _ = max(zip(faces, weights), key=lambda fw_: float(fw_[1]))
        return (x + fw / 2) / scale

    def _relative_path(self) -> str:
        try:
            return self.video_path.relative_to(BASE_DIR).as_posix()
        except ValueError:
            return self.video_path.as_posix()
