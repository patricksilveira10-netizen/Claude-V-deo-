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

# Renderização
RENDERS_DIR = TEMP_DIR / "renders"
FONTS_DIR = BASE_DIR / "assets" / "fonts"
OUTPUT_W, OUTPUT_H = 1080, 1920  # Reels/Shorts
OUTPUT_FILENAME = "output_final_reels.mp4"
AUDIO_RATE = 48_000
ZOOM_IN_AMOUNT = 0.10  # zoom_in: 1.00x -> 1.10x ao longo do clipe
RENDER_WORKERS = max(1, min(4, (os.cpu_count() or 2) // 2))  # clipes renderizados em paralelo

# Legenda (.ass)
SUB_FONT = "Montserrat Black"  # arquivo em assets/fonts (fallback do libass se ausente)
SUB_FONT_SIZE = 140
SUB_PRIMARY = "&H0000FFFF"  # ASS é &HAABBGGRR -> amarelo
SUB_OUTLINE = 9
SUB_SHADOW = 4
SUB_MARGIN_V = 560  # px a partir da base (1920): texto no terço inferior, fora do rosto e da UI do app
