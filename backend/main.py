import re
import shutil
import time
import uuid
from pathlib import Path, PurePath

import yt_dlp
from fastapi import FastAPI, File, HTTPException, Path as PathParam, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, HttpUrl

from config import ALLOWED_EXTENSIONS, MAX_HEIGHT, OUTPUT_FILENAME, RENDERS_DIR, TEMP_DIR, UPLOAD_CHUNK_SIZE
from processor import ProcessingError, VideoProcessor
from renderer import RenderError, VideoRenderer
from schemas import VideoData

app = FastAPI(title="Shorts Engine", version="0.1.0")

VIDEO_ID_PATTERN = r"^[0-9a-f]{12}$"


class IngestResult(BaseModel):
    video_id: str
    filename: str
    path: str
    size_bytes: int
    source: str


class DownloadRequest(BaseModel):
    url: HttpUrl


class ProcessRequest(BaseModel):
    video_id: str = Field(pattern=VIDEO_ID_PATTERN)
    language: str | None = Field(default=None, description="Código ISO (ex.: 'pt'). Vazio = autodetecção.")


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


def _resolve_video(video_id: str) -> Path:
    for p in TEMP_DIR.glob(f"{video_id}.*"):
        if p.suffix.lower() in ALLOWED_EXTENSIONS:
            return p
    raise HTTPException(404, f"Vídeo '{video_id}' não encontrado em temp/.")


@app.get("/api/media/{video_id}")
def media(video_id: str = PathParam(pattern=VIDEO_ID_PATTERN)) -> FileResponse:
    """Serve o vídeo original para o player (FileResponse suporta Range/seek)."""
    return FileResponse(_resolve_video(video_id))


@app.post("/api/process", response_model=VideoData)
async def process(req: ProcessRequest) -> VideoData:
    video = _resolve_video(req.video_id)
    processor = VideoProcessor(video, language=req.language)
    try:
        return await run_in_threadpool(processor.run)
    except ProcessingError as e:
        raise HTTPException(422, str(e)) from e


class RenderResult(BaseModel):
    video_id: str
    url: str
    duration: float
    clips: int
    size_bytes: int
    render_seconds: float


@app.post("/api/render", response_model=RenderResult)
async def render(data: VideoData) -> RenderResult:
    # video_path vem do cliente: só aceita um vídeo ingerido (temp/<id>.<ext>), nunca um caminho arbitrário.
    video_id = PurePath(data.video_path).stem
    if not re.fullmatch(VIDEO_ID_PATTERN, video_id):
        raise HTTPException(422, f"video_path inválido: '{data.video_path}'.")
    video = _resolve_video(video_id)

    renderer = VideoRenderer(data, video, video_id)
    try:
        result = await run_in_threadpool(renderer.run)
    except RenderError as e:
        raise HTTPException(422, str(e)) from e
    return RenderResult(
        video_id=video_id,
        # ?v= muda a cada render: o navegador não reaproveita o MP4 anterior do cache.
        url=f"/api/render/{video_id}/{OUTPUT_FILENAME}?v={int(time.time() * 1000)}",
        duration=result["duration"],
        clips=result["clips"],
        size_bytes=result["size_bytes"],
        render_seconds=result["render_seconds"],
    )


@app.get("/api/render/{video_id}/" + OUTPUT_FILENAME)
def download_render(video_id: str = PathParam(pattern=VIDEO_ID_PATTERN), download: bool = False) -> FileResponse:
    path = RENDERS_DIR / video_id / OUTPUT_FILENAME
    if not path.is_file():
        raise HTTPException(404, "Render não encontrado.")
    # ?download=1 força "Salvar como"; sem ele o navegador reproduz inline.
    return FileResponse(path, media_type="video/mp4", filename=OUTPUT_FILENAME if download else None)
