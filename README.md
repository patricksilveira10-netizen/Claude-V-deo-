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
| POST | `/api/render` | `video_data.json` editado | Renderiza o MP4 9:16 final e retorna `url` para download |
| GET | `/api/render/{video_id}/output_final_reels.mp4` | `?download=1` | Serve o MP4 final (inline ou como anexo) |
| POST | `/api/process` | `{"video_id": "...", "language": "pt"}` | Gera e retorna o `video_data.json` (salvo em `backend/temp/<id>.video_data.json`) |

`language` é opcional (sem ele, o Whisper detecta o idioma). O modelo vem da variável `WHISPER_MODEL` (padrão `base`); os demais parâmetros de análise ficam em `backend/config.py`.

## Renderização (`backend/renderer.py`)
Dois passes, desenhados para **não dessincronizar áudio e vídeo**:
1. Cada bloco `keep` vira um intermediário `.mov` (H.264 CRF 12 + PCM) com exatamente N frames e N/fps segundos de áudio, com limites encaixados na grade de frames (fps racional exato, VFR → CFR).
2. Concat demuxer + legenda `.ass` (uma palavra por vez, Montserrat Black embutida em `assets/fonts`) + encode final único (H.264 CRF 20 + AAC 192k, 1080x1920, `+faststart`).

Saída: `backend/temp/renders/<video_id>/output_final_reels.mp4` (+ `legenda_dinamica.ass`). Estilo da legenda e zoom em `backend/config.py`.

Teste de regressão de sincronia (flash + bipe em cada emenda, 29.97fps, com/sem áudio, com zoom):
```bash
cd backend && .venv/bin/python tests/check_render_sync.py
```
