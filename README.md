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

## Frontend (tela de ajuste)
- **Esquerda:** URL/upload → análise automática → player com a janela 9:16 do bloco ativo sobreposta → **RENDERIZAR VÍDEO FINAL** (`POST /api/render` com o JSON editado).
- **Direita:** timeline. Clique no cabeçalho do bloco para ir ao trecho; clique numa palavra para corrigir (Enter confirma, Esc cancela); `✂ Cortar` / `↺ Manter` alterna o tipo; slider/campo ajusta o `crop_center_x`.
- "Pular blocos cut no preview" simula o resultado final durante a reprodução.

## API
| Método | Rota | Corpo | Descrição |
|---|---|---|---|
| GET | `/api/health` | — | Status + se o FFmpeg foi encontrado |
| POST | `/api/ingest/upload` | multipart `file` | Salva em `backend/temp/<id>.<ext>` |
| POST | `/api/ingest/download` | `{"url": "..."}` | yt-dlp, máx. 1080p, salva em `backend/temp/` |
| GET | `/api/media/{video_id}` | — | Serve o vídeo original para o player (suporta Range/seek) |
| POST | `/api/process` | `{"video_id": "...", "language": "pt"}` | Gera e retorna o `video_data.json` (salvo em `backend/temp/<id>.video_data.json`) |

`language` é opcional (sem ele, o Whisper detecta o idioma). O modelo vem da variável `WHISPER_MODEL` (padrão `base`); os demais parâmetros de análise ficam em `backend/config.py`.
