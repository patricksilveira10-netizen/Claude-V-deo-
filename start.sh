#!/usr/bin/env bash
# Shorts Engine — inicia tudo com um comando (Linux/macOS):
#   API FastAPI em http://127.0.0.1:8000 (segundo plano) + interface Vite em http://localhost:5173 (abre o navegador).
# Ctrl+C encerra os dois. Na 1ª execução cria backend/.venv e instala as dependências (alguns minutos).
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
export PYTHONUNBUFFERED=1 PYTHONUTF8=1

# 0) Python do sistema (só para criar o venv / rodar o bootstrap)
PY=""
for c in python3.12 python3.11 python3.13 python3 python; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(sys.version_info < (3, 10))' 2>/dev/null; then
    PY="$c"; break
  fi
done
if [ -z "$PY" ]; then
  echo "[ERRO] Python 3.10+ não encontrado (recomendado 3.11/3.12). macOS: brew install python@3.12 | Ubuntu: sudo apt install python3.12 python3.12-venv" >&2
  exit 1
fi

# Checa FFmpeg/Node, cria o venv e instala dependências (só quando requirements/lockfile mudam)
"$PY" scripts/bootstrap.py setup

# a) Ativa o ambiente virtual
set +u  # scripts activate antigos referenciam variáveis não definidas
# shellcheck disable=SC1091
source backend/.venv/bin/activate
set -u

# b) API em segundo plano
API_PID=""
cleanup() {
  if [ -n "$API_PID" ] && kill -0 "$API_PID" 2>/dev/null; then
    echo "[start] encerrando a API…"
    kill "$API_PID" 2>/dev/null || true
    wait "$API_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT
trap 'exit 130' INT TERM HUP

status=0
python scripts/bootstrap.py api-status || status=$?
case "$status" in
  0) echo "[start] API já está rodando em :8000 — reutilizando (feche a outra instância para carregar código novo)." ;;
  3) (cd backend && exec python -m uvicorn main:app --host 127.0.0.1 --port 8000 --no-access-log) &
     API_PID=$!
     python scripts/bootstrap.py wait-api 90 --pid "$API_PID" ;;
  *) echo "[ERRO] A porta 8000 está ocupada por outro programa. Libere-a e rode de novo." >&2
     exit 1 ;;
esac

# c) Interface web (abre o navegador)
cd frontend
echo "[start] abrindo a interface… (Ctrl+C encerra tudo)"
npm run dev -- --open
