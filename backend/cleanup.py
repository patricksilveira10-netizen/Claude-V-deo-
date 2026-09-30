"""Limpeza de backend/temp para uso contínuo.

Cada job é identificado pelo video_id (12 hex) e deixa, no máximo, três arquivos "finais":
    temp/<id>.<ext>                                  vídeo original (player + re-render)
    temp/<id>.video_data.json                        análise
    temp/renders/<id>/output_final_reels.mp4         vídeo final
Todo o resto com o prefixo do job é intermediário (WAV do Whisper, clipes de render, partes do yt-dlp,
.part.mp4 de encode abortado) e é apagado sempre. O job inteiro expira após TEMP_RETENTION_HOURS sem
atividade. Jobs em andamento (active_job) nunca são tocados.
"""

import logging
import re
import shutil
import threading
import time
from collections import defaultdict
from contextlib import contextmanager
from pathlib import Path

import config

_JOB_FILE = re.compile(r"^([0-9a-f]{12})\.")
_JOB_DIR = re.compile(r"^[0-9a-f]{12}$")

log = logging.getLogger("uvicorn.error")

_active: dict[str, int] = {}
_active_lock = threading.Lock()


@contextmanager
def active_job(video_id: str):
    """Marca o job como em uso enquanto o bloco roda (ingestão, análise, render)."""
    with _active_lock:
        _active[video_id] = _active.get(video_id, 0) + 1
    try:
        yield
    finally:
        with _active_lock:
            _active[video_id] -= 1
            if not _active[video_id]:
                del _active[video_id]


def _is_final(entry: Path, video_id: str) -> bool:
    if entry.parent == config.TEMP_DIR:
        if entry.name == f"{video_id}.video_data.json":
            return True
        return entry.name[len(video_id) :].lower() in config.ALLOWED_EXTENSIONS  # exatamente <id>.<ext>
    return entry.name == config.OUTPUT_FILENAME and entry.parent.name == video_id


def _collect() -> dict[str, list[Path]]:
    """Entradas de primeiro nível por job (a pasta renders/<id> entra pelos seus filhos)."""
    jobs: dict[str, list[Path]] = defaultdict(list)
    for p in config.TEMP_DIR.iterdir():
        m = _JOB_FILE.match(p.name)
        if m and p.is_file():
            jobs[m[1]].append(p)
    if config.RENDERS_DIR.is_dir():
        for d in config.RENDERS_DIR.iterdir():
            if d.is_dir() and _JOB_DIR.match(d.name):
                jobs[d.name].extend(d.iterdir())
                jobs[d.name].append(d)  # a própria pasta (removida se esvaziar)
    return jobs


def _size(p: Path) -> int:
    try:
        return p.stat().st_size if p.is_file() else sum(f.stat().st_size for f in p.rglob("*") if f.is_file())
    except OSError:
        return 0


def _newest(entries: list[Path]) -> float:
    """Última atividade do job = mtime do arquivo mais novo. mtime de pasta não conta: muda a cada
    arquivo criado/apagado dentro dela (inclusive pela própria limpeza)."""
    stamps = [0.0]
    for e in entries:
        try:
            files = [e] if e.is_file() else [f for f in e.rglob("*") if f.is_file()]
            stamps.extend(f.stat().st_mtime for f in files)
        except OSError:
            pass
    return max(stamps)


def _remove(p: Path) -> int:
    """Apaga arquivo/pasta; devolve bytes liberados (0 se em uso — ex.: arquivo aberto no Windows)."""
    size = _size(p)
    try:
        if p.is_dir():
            shutil.rmtree(p)
        else:
            p.unlink()
        return size
    except FileNotFoundError:
        return 0
    except OSError as e:
        log.warning(f"[cleanup] não foi possível apagar {p.name}: {e}")
        return 0


def purge_temp(retention_hours: float | None = None, now: float | None = None) -> dict:
    retention_hours = config.TEMP_RETENTION_HOURS if retention_hours is None else retention_hours
    now = time.time() if now is None else now
    freed, removed, expired_jobs = 0, 0, []

    for video_id, entries in _collect().items():
        # O lock segura novos active_job() deste id durante a remoção (evita apagar algo que acabou de entrar em uso).
        with _active_lock:
            if video_id in _active:
                continue
            expired = retention_hours > 0 and now - _newest(entries) > retention_hours * 3600
            for entry in sorted(entries, key=lambda e: e.is_dir()):  # arquivos antes da pasta que os contém
                if entry.is_dir() and entry.parent == config.RENDERS_DIR:
                    if expired or not any(entry.iterdir()):
                        freed += _remove(entry)
                    continue
                if expired or not _is_final(entry, video_id):
                    if entry.exists():
                        freed += _remove(entry)
                        removed += 1
            if expired:
                expired_jobs.append(video_id)

    if removed or expired_jobs:
        size = f"{freed / 1_048_576:.1f} MB" if freed >= 1_048_576 else f"{freed / 1024:.0f} KB"
        msg = f"[cleanup] {removed} item(ns) removido(s), {size} liberados"
        if expired_jobs:
            msg += f"; jobs expirados (> {retention_hours:g}h): {', '.join(expired_jobs)}"
        log.info(msg)
    return {"removed": removed, "freed_bytes": freed, "expired_jobs": expired_jobs}
