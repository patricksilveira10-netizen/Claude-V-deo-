#!/usr/bin/env python3
"""Preparação do ambiente para start.sh / start.bat (Linux, macOS e Windows).

    python scripts/bootstrap.py setup          checa ferramentas, cria backend/.venv, instala dependências
    python scripts/bootstrap.py api-status     0 = nossa API já responde em :8000 | 3 = porta livre | 4 = porta ocupada
    python scripts/bootstrap.py wait-api [s]   espera a API responder (falha se o processo --pid morrer)

Sintaxe compatível com Python 3.8+ de propósito: um Python antigo precisa conseguir dizer que é antigo.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND, FRONTEND = ROOT / "backend", ROOT / "frontend"
VENV = BACKEND / ".venv"
IS_WIN = os.name == "nt"
VENV_PY = VENV / ("Scripts/python.exe" if IS_WIN else "bin/python")
API_HOST, API_PORT = "127.0.0.1", 8000
MIN_PY = (3, 10)
MIN_NODE = ((20, 19), (22, 12))  # Vite 8: ^20.19.0 || >=22.12.0

# Sem proxy para 127.0.0.1: proxies corporativos (HTTP_PROXY) não enxergam a máquina local.
_local = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def say(msg: str) -> None:
    print(f"[setup] {msg}", flush=True)


def fail(msg: str) -> None:
    print(f"\n[ERRO] {msg}\n", file=sys.stderr, flush=True)
    sys.exit(1)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(cmd: list, cwd: Path | None = None) -> None:
    print("  $ " + " ".join(str(c) for c in cmd), flush=True)
    if subprocess.run([str(c) for c in cmd], cwd=cwd).returncode != 0:
        fail(f"comando falhou: {' '.join(str(c) for c in cmd)}")


def install_hint(tool: str) -> str:
    system = platform.system()
    hints = {
        "ffmpeg": {
            "Windows": "winget install Gyan.FFmpeg   (depois feche e reabra o terminal)",
            "Darwin": "brew install ffmpeg",
            "Linux": "sudo apt install ffmpeg   (ou o gerenciador da sua distro)",
        },
        "node": {
            "Windows": "winget install OpenJS.NodeJS.LTS   (ou https://nodejs.org)",
            "Darwin": "brew install node   (ou https://nodejs.org)",
            "Linux": "https://nodejs.org  ou  https://github.com/nvm-sh/nvm",
        },
        "python": {
            "Windows": "winget install Python.Python.3.12   (ou https://www.python.org/downloads/)",
            "Darwin": "brew install python@3.12",
            "Linux": "sudo apt install python3.12 python3.12-venv",
        },
    }
    return hints[tool].get(system, hints[tool]["Linux"])


# ── checagens ─────────────────────────────────────────────────────────────
def check_tools() -> str:
    if sys.version_info < MIN_PY:
        fail(f"Python {platform.python_version()} é antigo; precisa de 3.10+ (recomendado 3.11/3.12).\n"
             f"  Instale: {install_hint('python')}")  # fmt: skip

    missing = [t for t in ("ffmpeg", "ffprobe") if not shutil.which(t)]
    if missing:
        fail(f"{' e '.join(missing)} não encontrado(s) no PATH (obrigatório para análise e render).\n"
             f"  Instale: {install_hint('ffmpeg')}")  # fmt: skip

    node, npm = shutil.which("node"), shutil.which("npm")
    if not node or not npm:
        fail(f"Node.js/npm não encontrado. Precisa de Node 20.19+ ou 22.12+.\n  Instale: {install_hint('node')}")
    out = subprocess.run([node, "--version"], capture_output=True, text=True).stdout.strip().lstrip("v")
    try:
        major, minor = (int(x) for x in out.split(".")[:2])
    except ValueError:
        fail(f"Não consegui ler a versão do Node ('{out}').")
    ok = (major == 20 and minor >= 19) or (major == 22 and minor >= 12) or major > 22
    if not ok:
        fail(f"Node {out} é incompatível com o Vite 8 (precisa 20.19+ ou 22.12+).\n  Atualize: {install_hint('node')}")
    return npm


# ── Python ────────────────────────────────────────────────────────────────
def ensure_venv() -> None:
    if not VENV_PY.exists():
        say(f"criando backend/.venv com Python {platform.python_version()} …")
        res = subprocess.run([sys.executable, "-m", "venv", str(VENV)])
        if res.returncode != 0 or not VENV_PY.exists():
            hint = "  No Ubuntu/Debian: sudo apt install python3-venv\n" if platform.system() == "Linux" else ""
            fail(f"não foi possível criar o ambiente virtual.\n{hint}")

    req = BACKEND / "requirements.txt"
    stamp = VENV / ".requirements.sha256"
    if stamp.exists() and stamp.read_text().strip() == sha256(req):
        say("dependências Python em dia")
        return

    say("instalando dependências Python (1ª vez leva alguns minutos: torch + whisper são grandes) …")
    pip = [VENV_PY, "-m", "pip", "--disable-pip-version-check"]
    run(pip + ["install", "--upgrade", "pip"])
    torch_present = subprocess.run([VENV_PY, "-c", "import torch"], capture_output=True).returncode == 0
    if platform.system() == "Linux" and not shutil.which("nvidia-smi") and not torch_present:
        # Sem GPU NVIDIA: wheel CPU (~200 MB) em vez do padrão do PyPI com CUDA (vários GB).
        say("sem GPU NVIDIA: instalando torch CPU …")
        res = subprocess.run([str(c) for c in pip + ["install", "torch", "--index-url", "https://download.pytorch.org/whl/cpu"]])
        if res.returncode != 0:
            say("índice CPU do PyTorch indisponível; seguindo com o torch padrão do PyPI")
    run(pip + ["install", "-r", req])
    stamp.write_text(sha256(req))


# ── Node ──────────────────────────────────────────────────────────────────
def ensure_node_modules(npm: str) -> None:
    lock = FRONTEND / "package-lock.json"
    stamp = FRONTEND / "node_modules" / ".package-lock.sha256"
    if stamp.exists() and stamp.read_text().strip() == sha256(lock):
        say("dependências do frontend em dia")
        return
    say("instalando dependências do frontend (npm ci) …")
    run([npm, "ci", "--no-audit", "--no-fund"], cwd=FRONTEND)
    stamp.write_text(sha256(lock))


# ── API ───────────────────────────────────────────────────────────────────
def api_status() -> int:
    try:
        with _local.open(f"http://{API_HOST}:{API_PORT}/api/health", timeout=2) as r:
            data = json.load(r)
        return 0 if isinstance(data, dict) and "whisper" in data else 4
    except (urllib.error.HTTPError, ValueError):
        return 4  # responde, mas não é a nossa API
    except (urllib.error.URLError, OSError):
        with socket.socket() as s:
            s.settimeout(1)
            return 4 if s.connect_ex((API_HOST, API_PORT)) == 0 else 3


def _alive(pid: int) -> bool:
    if IS_WIN:
        return True  # no Windows a API roda numa janela própria; o timeout cobre falhas
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def wait_api(timeout: float, pid: int | None) -> int:
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        if api_status() == 0:
            say(f"API pronta em http://{API_HOST}:{API_PORT} ({time.monotonic() - t0:.1f}s)")
            return 0
        if pid and not _alive(pid):
            print("\n[ERRO] a API encerrou durante a inicialização (veja o erro acima).\n", file=sys.stderr)
            return 1
        time.sleep(0.5)
    print(f"\n[ERRO] a API não respondeu em {timeout:.0f}s.\n", file=sys.stderr)
    return 1


def main(argv: list) -> int:
    cmd = argv[1] if len(argv) > 1 else "setup"
    if cmd == "setup":
        npm = check_tools()
        ensure_venv()
        ensure_node_modules(npm)
        return 0
    if cmd == "api-status":
        return api_status()
    if cmd == "wait-api":
        timeout = float(argv[2]) if len(argv) > 2 else 90
        pid = int(argv[argv.index("--pid") + 1]) if "--pid" in argv else None
        return wait_api(timeout, pid)
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
