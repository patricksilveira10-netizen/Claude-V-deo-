import shutil
import uuid
from pathlib import Path

import yt_dlp
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, HttpUrl

from config import ALLOWED_EXTENSIONS, MAX_HEIGHT, TEMP_DIR, UPLOAD_CHUNK_SIZE

app = FastAPI(title="Shorts Engine", version="0.1.0")


class IngestResult(BaseModel):
    video_id: str
    filename: str
    path: str
    size_bytes: int
    source: str


class DownloadRequest(BaseModel):
    url: HttpUrl


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "ffmpeg": shutil.which("ffmpeg") is not None}


@app.post("/api/ingest/upload", response_model=IngestResult)
async def ingest_upload(file: UploadFile = File(...)) -> IngestResult:
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(415, f"Extensão não suportada: '{ext}'. Aceitas: {sorted(ALLOWED_EXTENSIONS)}")

    video_id = _new_id()
    dest = TEMP_DIR / f"{video_id}{ext}"
    size = 0
    try:
        # Streaming em chunks: não carrega o vídeo inteiro em memória.
        with dest.open("wb") as out:
            while chunk := await file.read(UPLOAD_CHUNK_SIZE):
                out.write(chunk)
                size += len(chunk)
    except Exception:
        dest.unlink(missing_ok=True)
        raise
    finally:
        await file.close()

    if size == 0:
        dest.unlink(missing_ok=True)
        raise HTTPException(400, "Arquivo vazio.")

    return IngestResult(video_id=video_id, filename=dest.name, path=str(dest), size_bytes=size, source="upload")


def _download(url: str, video_id: str) -> Path:
    has_ffmpeg = shutil.which("ffmpeg") is not None
    # Com FFmpeg: melhor vídeo + melhor áudio (<=1080p) mesclados em MP4.
    # Sem FFmpeg: só formatos progressivos (vídeo+áudio no mesmo arquivo).
    fmt = (
        f"bv*[height<={MAX_HEIGHT}][ext=mp4]+ba[ext=m4a]/bv*[height<={MAX_HEIGHT}]+ba/b[height<={MAX_HEIGHT}]"
        if has_ffmpeg
        else f"b[height<={MAX_HEIGHT}]/b"
    )
    opts = {
        "format": fmt,
        "outtmpl": str(TEMP_DIR / f"{video_id}.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "restrictfilenames": True,
    }
    if has_ffmpeg:
        opts["merge_output_format"] = "mp4"

    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        downloads = info.get("requested_downloads") or []
        filepath = downloads[0].get("filepath") if downloads else ydl.prepare_filename(info)
    return Path(filepath)


@app.post("/api/ingest/download", response_model=IngestResult)
async def ingest_download(req: DownloadRequest) -> IngestResult:
    video_id = _new_id()
    try:
        path = await run_in_threadpool(_download, str(req.url), video_id)
    except yt_dlp.utils.DownloadError as e:
        for leftover in TEMP_DIR.glob(f"{video_id}.*"):
            leftover.unlink(missing_ok=True)
        raise HTTPException(422, f"Falha no download: {e}") from e

    if not path.exists():
        raise HTTPException(500, "Download concluído mas arquivo não encontrado.")

    return IngestResult(
        video_id=video_id, filename=path.name, path=str(path), size_bytes=path.stat().st_size, source=str(req.url)
    )
