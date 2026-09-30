import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
TEMP_DIR = BASE_DIR / "temp"
TEMP_DIR.mkdir(parents=True, exist_ok=True)

MAX_HEIGHT = 1080
UPLOAD_CHUNK_SIZE = 8 * 1024 * 1024  # 8 MiB
ALLOWED_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}

# Análise
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "base")
SILENCE_MIN_GAP = 0.5  # s — gap entre palavras acima disso vira "cut"
CUT_PADDING = 0.0  # s — margem preservada em volta da fala em cada corte
FACE_SAMPLE_INTERVAL = 1.0  # s — 1 frame amostrado por segundo de bloco "keep"
FACE_DETECT_WIDTH = 960  # px — frame reduzido antes da detecção (velocidade x rostos pequenos)
TARGET_ASPECT = 9 / 16
