# Shorts Engine

Pipeline local (uso privado) para transformar vídeos horizontais em Reels/Shorts 9:16 com jump cuts automáticos, enquadramento no rosto e legenda animada palavra a palavra.

Fluxo: **Ingestão (upload/URL) → Análise (Whisper + cortes + face tracking → JSON) → Ajuste na tela → Renderizar (FFmpeg a partir do JSON) → Baixar MP4**.

## Início rápido

**Pré-requisitos** (uma vez):

| | Windows | macOS | Linux (Ubuntu/Debian) |
|---|---|---|---|
| Python 3.11/3.12 | `winget install Python.Python.3.12` | `brew install python@3.12` | `sudo apt install python3.12 python3.12-venv` |
| Node 20.19+ / 22.12+ | `winget install OpenJS.NodeJS.LTS` | `brew install node` | [nodejs.org](https://nodejs.org) ou nvm |
| FFmpeg | `winget install Gyan.FFmpeg` | `brew install ffmpeg` | `sudo apt install ffmpeg` |

Depois de instalar, feche e reabra o terminal (para o PATH valer).

**Rodar:**

```bash
./start.sh        # Linux/macOS
start.bat         # Windows (ou duplo clique)
```

O script checa as ferramentas, cria `backend/.venv`, instala as dependências (só quando `requirements.txt`/`package-lock.json` mudam), sobe a API em `http://127.0.0.1:8000` e abre a interface em `http://localhost:5173`.

- **1ª execução:** alguns minutos (torch + Whisper). Ao subir, a API baixa o modelo Whisper (~140 MB no `base`) para `~/.cache/whisper`. O selo no topo da tela mostra "carregando" até ficar "pronto".
- **Encerrar:** `Ctrl+C` no terminal. No Windows a API roda numa janela própria ("Shorts Engine API"): feche essa janela para encerrá-la. Se ela ficar aberta, o próximo `start.bat` reaproveita a API já em execução.

## Usando a tela
- **Esquerda:** cole uma URL ou faça upload → a análise roda automaticamente → player do original com a janela 9:16 do bloco ativo → **RENDERIZAR VÍDEO FINAL** → o vídeo final aparece logo abaixo com o botão **Baixar Vídeo Processado (.mp4)**.
- **Direita (timeline):** clique no cabeçalho do bloco para ir ao trecho; clique numa palavra para corrigir (Enter confirma, Esc cancela); `✂ Cortar` / `↺ Manter` alterna o tipo; slider/campo ajusta o `crop_center_x`; `🔍 Zoom` liga um zoom-in leve no bloco.
- "Pular blocos cut no preview" simula o resultado final durante a reprodução.

## Configuração (variáveis de ambiente)
| Variável | Padrão | Efeito |
|---|---|---|
| `WHISPER_MODEL` | `base` | `tiny`, `base`, `small`, `medium`, `large-v3`, `turbo`… (maior = mais preciso e mais lento) |
| `WHISPER_PRELOAD` | `1` | `0` = só carrega o modelo na 1ª análise |
| `TEMP_RETENTION_HOURS` | `24` | jobs sem atividade há mais tempo são apagados; `0` desliga a expiração |

Ex.: `WHISPER_MODEL=small ./start.sh` · Windows: `set WHISPER_MODEL=small` e depois `start.bat`.
Demais parâmetros (limiar de silêncio, estilo da legenda, zoom, qualidade) ficam em `backend/config.py`.

## Limpeza automática de `backend/temp`
- **Intermediários** (WAV do Whisper, clipes do render, partes de download, encode abortado) são apagados **ao fim de cada render** e **ao iniciar a API**.
- **Jobs inteiros** (original + `video_data.json` + MP4 final) expiram após `TEMP_RETENTION_HOURS` sem atividade. Até lá dá para ajustar e renderizar de novo.
- Jobs em andamento nunca são tocados.

## API
| Método | Rota | Corpo | Descrição |
|---|---|---|---|
| GET | `/api/health` | — | Status da API, FFmpeg e Whisper (`idle`/`loading`/`ready`/`error`) |
| POST | `/api/ingest/upload` | multipart `file` | Salva em `backend/temp/<id>.<ext>` |
| POST | `/api/ingest/download` | `{"url": "..."}` | yt-dlp, máx. 1080p, salva em `backend/temp/` |
| GET | `/api/media/{video_id}` | — | Vídeo original para o player (suporta Range/seek) |
| POST | `/api/process` | `{"video_id": "...", "language": "pt"}` | Gera e retorna o `video_data.json` (`language` opcional: sem ele, autodetecção) |
| POST | `/api/render` | `video_data.json` editado | Renderiza o MP4 9:16 final e retorna `url` |
| GET | `/api/render/{video_id}/output_final_reels.mp4` | `?download=1` | MP4 final (inline ou como anexo) |

## Renderização (`backend/renderer.py`)
Dois passes, desenhados para **não dessincronizar áudio e vídeo**:
1. Cada bloco `keep` vira um intermediário `.mov` (H.264 CRF 12 + PCM) com exatamente N frames e N/fps segundos de áudio, com limites encaixados na grade de frames (fps racional exato, VFR → CFR).
2. Concat demuxer + legenda `.ass` (uma palavra por vez, Montserrat Black embutida em `assets/fonts`) + encode final único (H.264 CRF 20 + AAC 192k, 1080x1920, `+faststart`).

Saída: `backend/temp/renders/<video_id>/output_final_reels.mp4`.

## Testes
```bash
cd backend
.venv/bin/python tests/check_render_sync.py   # sincronia A/V: flash + bipe em cada emenda (29.97fps, com/sem áudio, zoom)
.venv/bin/python tests/check_cleanup.py       # limpeza de temp/
```
(Windows: `.venv\Scripts\python tests\check_render_sync.py`)

## Rodando sem os scripts
```bash
cd backend && source .venv/bin/activate && python -m uvicorn main:app --port 8000   # terminal 1
cd frontend && npm run dev                                                          # terminal 2
```

## Problemas comuns
- **"FFmpeg/ffprobe não encontrado"**: instale (tabela acima) e reabra o terminal.
- **"A porta 8000 está ocupada"**: outro programa usa a porta; feche-o.
- **Selo "Whisper: erro ao carregar"**: normalmente é falta de internet no 1º download do modelo; passe o mouse sobre o selo para ver o erro. A próxima análise tenta de novo.
- **Player em branco com aviso de codec**: o navegador não decodifica o arquivo original (HEVC/AV1). A análise e o render funcionam normalmente.
