# Shorts Engine

Pipeline local para ingestão, edição em massa e renderização de vídeos curtos (Reels/Shorts).

Fluxo: **Ingestão → análise (JSON de metadados) → ajuste no frontend → Renderizar (FFmpeg a partir do JSON)**.

## Requisitos
- Python 3.11+
- Node 20+
- FFmpeg no PATH (necessário para mesclar vídeo+áudio no yt-dlp e para renderização)

## Backend
```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

## Frontend
```bash
cd frontend
npm install
npm run dev                      # http://localhost:5173, /api → :8000
```

## API
| Método | Rota | Corpo | Descrição |
|---|---|---|---|
| GET | `/api/health` | — | Status + se o FFmpeg foi encontrado |
| POST | `/api/ingest/upload` | multipart `file` | Salva em `backend/temp/<id>.<ext>` |
| POST | `/api/ingest/download` | `{"url": "..."}` | yt-dlp, máx. 1080p, salva em `backend/temp/` |
| POST | `/api/process` | `{"video_id": "...", "language": "pt"}` | Gera e retorna o `video_data.json` (salvo em `backend/temp/<id>.video_data.json`) |

`language` é opcional (sem ele, o Whisper detecta o idioma). O modelo vem da variável `WHISPER_MODEL` (padrão `base`); os demais parâmetros de análise ficam em `backend/config.py`.
