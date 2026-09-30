"""Teste da limpeza automática de temp/ (cleanup.purge_temp).

Uso: cd backend && .venv/bin/python tests/check_cleanup.py
"""

import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import cleanup  # noqa: E402
import config  # noqa: E402

A, B, C, D = "a" * 12, "b" * 12, "c" * 12, "d" * 12
OLD = time.time() - 30 * 3600  # 30h atrás


def touch(p: Path, mtime: float | None = None, data: bytes = b"x" * 1000) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    if mtime:
        os.utime(p, (mtime, mtime))
    return p


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        temp = Path(td)
        renders = temp / "renders"
        config.TEMP_DIR, config.RENDERS_DIR = temp, renders

        # Job A: recente, finais + intermediários de todo tipo
        finals_a = [touch(temp / f"{A}.mp4"), touch(temp / f"{A}.video_data.json"), touch(renders / A / config.OUTPUT_FILENAME)]
        inter_a = [
            touch(temp / f"{A}.x1y2z3.wav"),
            touch(temp / f"{A}.mp4.part"),
            touch(temp / f"{A}.f137.mp4"),
            touch(renders / A / "work" / "clip_0000.mov"),
            touch(renders / A / f".{config.OUTPUT_FILENAME}.part.mp4"),
            touch(renders / A / "legenda_dinamica.ass"),
        ]
        # Job B: inativo há 30h -> expira inteiro
        job_b = [touch(temp / f"{B}.webm", OLD), touch(temp / f"{B}.video_data.json", OLD),
                 touch(renders / B / config.OUTPUT_FILENAME, OLD)]  # fmt: skip
        # Job C: antigo, mas em andamento -> intocado
        job_c = [touch(temp / f"{C}.mp4", OLD), touch(temp / f"{C}.abc123.wav", OLD)]
        # Job D: só intermediários (render abortado) -> pasta some
        touch(renders / D / "work" / "clip_0000.mov")
        # Fora de qualquer job -> intocado
        foreign = [touch(temp / ".gitkeep", data=b""), touch(temp / "notas.txt"), touch(renders / "leia.txt"),
                   touch(renders / "nao-e-id" / "x.bin")]  # fmt: skip

        with cleanup.active_job(C):
            stats = cleanup.purge_temp(retention_hours=24)

        checks = {
            "finais do job recente mantidos": all(p.exists() for p in finals_a),
            "intermediários do job recente apagados": not any(p.exists() for p in inter_a),
            "pasta work/ do job recente apagada": not (renders / A / "work").exists(),
            "job expirado removido inteiro": not any(p.exists() for p in job_b) and not (renders / B).exists(),
            "job ativo intocado (mesmo antigo e com WAV)": all(p.exists() for p in job_c),
            "job só com intermediários: pasta removida": not (renders / D).exists(),
            "arquivos fora de jobs intocados": all(p.exists() for p in foreign),
            "estatística de jobs expirados": stats["expired_jobs"] == [B],
        }
        # Job C deixa de estar ativo: agora o WAV (intermediário) sai e o job (30h) expira
        stats2 = cleanup.purge_temp(retention_hours=24)
        checks["após terminar, job antigo expira"] = not any(p.exists() for p in job_c) and stats2["expired_jobs"] == [C]
        # retenção desligada: nada de job inteiro expira
        old_final = touch(temp / f"{D}.mp4", OLD)
        cleanup.purge_temp(retention_hours=0)
        checks["retenção <= 0 não expira jobs"] = old_final.exists()

    for name, ok in checks.items():
        print(("✓ " if ok else "✗ ") + name)
    return sum(not ok for ok in checks.values())


if __name__ == "__main__":
    sys.exit(main())
