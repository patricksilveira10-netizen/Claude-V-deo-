"""Teste de regressão de sincronia A/V do VideoRenderer.

Gera uma fonte 29.97fps / AAC 44.1kHz com marcadores (flash branco de 1 frame + bipe no mesmo instante),
renderiza com blocos "keep" de limites fora da grade de frames e mede, no MP4 final, o desvio
entre cada flash e seu bipe e em relação à posição esperada.

Uso: cd backend && .venv/bin/python tests/check_render_sync.py
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import renderer as R  # noqa: E402
from schemas import VideoData  # noqa: E402

FPS_NUM, FPS_DEN = 30000, 1001
FPS = FPS_NUM / FPS_DEN
DUR = 20.0
MARKERS = [1.0, 3.7, 6.25, 9.1, 12.4, 15.8, 18.3]
KEEPS = [(0.513, 2.207), (3.311, 4.9), (5.97, 7.03), (8.8, 10.02), (12.0, 13.1), (15.5, 16.44), (18.0, 19.5)]
TOL = 1 / FPS  # tolerância: 1 frame


def make_source(path: Path, with_audio: bool = True) -> list[float]:
    frames = [round(m * FPS) for m in MARKERS]
    times = [k / FPS for k in frames]  # instante exato do frame-marcador
    enable = "+".join(f"eq(n,{k})" for k in frames)
    vf = f"drawbox=x=0:y=0:w=iw:h=ih:color=white:t=fill:enable='{enable}'"
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"color=c=0x303030:s=1920x1080:r={FPS_NUM}/{FPS_DEN}:d={DUR}"]
    if with_audio:
        # aevalsrc: bipe com precisão de amostra (enable= de filtros só age por frame de áudio, ~23ms)
        beeps = "+".join(f"between(t,{t:.6f},{t + 0.03:.6f})" for t in times)
        cmd += ["-f", "lavfi", "-i", f"aevalsrc='if({beeps},0.5*sin(2*PI*1000*t),0)':s=44100:d={DUR}"]
    cmd += ["-vf", vf, "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p"]
    cmd += ["-c:a", "aac", "-b:a", "128k"] if with_audio else []
    subprocess.run(cmd + [str(path)], check=True)
    return times


def video_data(path: Path, zoom: bool = False) -> VideoData:
    timeline, cid, cursor = [], 1, 0.0
    for s, e in KEEPS:
        if s > cursor:
            timeline.append({"clip_id": cid, "type": "cut", "start_time": cursor, "end_time": s, "reason": "silence"})
            cid += 1
        words = [{"word": "Marca", "start": m - 0.1, "end": m + 0.2} for m in MARKERS if s <= m < e]
        timeline.append({"clip_id": cid, "type": "keep", "start_time": s, "end_time": e, "crop_center_x": 1300,
                         "transcript": words, "zoom_in": zoom and cid % 4 == 0})  # fmt: skip
        cid += 1
        cursor = e
    return VideoData.model_validate(
        {"video_path": path.name, "metadata": {"width": 1920, "height": 1080, "fps": round(FPS, 3)}, "timeline": timeline}
    )


def probe(path: Path) -> dict:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-count_frames", "-show_entries",
         "stream=codec_type,width,height,nb_read_frames,duration,sample_rate:format=duration", "-of", "json", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout  # fmt: skip
    return json.loads(out)


def flash_times(path: Path, fps: float) -> list[float]:
    cap, i, prev, hits = cv2.VideoCapture(str(path)), 0, False, []
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        bright = frame[:600].mean() > 180  # topo do quadro: longe da legenda
        if bright and not prev:
            hits.append(i / fps)
        prev, i = bright, i + 1
    return hits


def beep_times(path: Path) -> list[float]:
    pcm = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", str(path), "-ac", "1", "-ar", "48000", "-f", "s16le", "-"],
                         capture_output=True, check=True).stdout  # fmt: skip
    a = np.abs(np.frombuffer(pcm, np.int16).astype(np.float32) / 32768)
    idx = np.flatnonzero(a > 0.2)
    if idx.size == 0:
        return []
    onsets = [idx[0]] + [j for p, j in zip(idx, idx[1:]) if j - p > 4800]  # >100ms de silêncio = novo bipe
    return [o / 48000 for o in onsets]


def main() -> int:
    failures = 0
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        R.RENDERS_DIR = td / "renders"  # não suja backend/temp

        for label, with_audio, zoom in [("com áudio", True, False), ("com áudio + zoom_in", True, True), ("sem áudio", False, False)]:
            src = td / "000000000000.mp4"
            marker_src_times = make_source(src, with_audio)
            data = video_data(src, zoom)
            rnd = R.VideoRenderer(data, src, "000000000000")
            rnd.out_dir = td / "renders"
            rnd.work_dir, rnd.output_path = rnd.out_dir / "work", rnd.out_dir / "out.mp4"
            res = rnd.run()
            segs = rnd._plan()

            info = probe(rnd.output_path)
            v = next(s for s in info["streams"] if s["codec_type"] == "video")
            a = next(s for s in info["streams"] if s["codec_type"] == "audio")
            exp_frames = sum(s.frames for s in segs)
            vdur, adur = float(v["duration"]), float(a["duration"])
            print(f"\n=== {label}: {res['clips']} clipes, {res['render_seconds']}s de render")
            print(f"  saída {v['width']}x{v['height']}  frames {v['nb_read_frames']} (esperado {exp_frames})"
                  f"  dur vídeo {vdur:.4f}s  áudio {adur:.4f}s  Δ {abs(vdur - adur) * 1000:.1f}ms")  # fmt: skip
            ok = int(v["nb_read_frames"]) == exp_frames and (v["width"], v["height"]) == (1080, 1920)
            ok &= abs(vdur - adur) < 0.03  # < 1 frame AAC (21ms) + margem

            expected = []
            for t in marker_src_times:
                seg = next(s for s in segs if s.src_start <= t < s.src_start + s.duration(FPS))
                expected.append(seg.out_start + (t - seg.src_start))
            flashes = flash_times(rnd.output_path, FPS)
            beeps = beep_times(rnd.output_path) if with_audio else []
            print(f"  {'esperado':>9} {'flash':>8} {'bipe':>8} {'flash-esp':>10} {'bipe-flash':>11}")
            for i, e in enumerate(expected):
                f = flashes[i] if i < len(flashes) else float("nan")
                b = beeps[i] if i < len(beeps) else float("nan")
                line = f"  {e:9.3f} {f:8.3f} {b:8.3f} {(f - e) * 1000:8.1f}ms"
                good = abs(f - e) < TOL
                if with_audio:
                    line += f" {(b - f) * 1000:9.1f}ms"
                    good &= abs(b - f) < TOL
                print(line + ("" if good else "  <-- FORA"))
                ok &= good
            ok &= len(flashes) == len(expected) and (not with_audio or len(beeps) == len(expected))
            print("  OK" if ok else "  FALHOU")
            failures += not ok
            ass_lines = (rnd.out_dir / "legenda_dinamica.ass").read_text().count("Dialogue:")
            print(f"  legenda: {ass_lines} palavras")
    return failures


if __name__ == "__main__":
    sys.exit(main())
