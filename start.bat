@echo off
rem Shorts Engine - inicia tudo com um comando (Windows)
rem   API FastAPI em http://127.0.0.1:8000 (janela propria) + interface Vite em http://localhost:5173 (abre o navegador).
rem   Na 1a execucao cria backend\.venv e instala as dependencias (alguns minutos).
setlocal
title Shorts Engine
cd /d "%~dp0"
set "PYTHONUNBUFFERED=1"
set "PYTHONUTF8=1"

rem 0) Python do sistema (so para criar o venv / rodar o bootstrap): py launcher, depois python no PATH
set "PY="
for %%v in (3.12 3.11 3.13 3.10) do if not defined PY py -%%v -c "import sys" >nul 2>&1 && set "PY=py -%%v"
if defined PY goto :have_python
python -c "import sys; sys.exit(sys.version_info < (3, 10))" >nul 2>&1
if not errorlevel 1 set "PY=python"
if defined PY goto :have_python
echo [ERRO] Python 3.10+ nao encontrado (recomendado 3.11/3.12).
echo        Instale: winget install Python.Python.3.12   (ou https://www.python.org/downloads/)
goto :fail

:have_python
rem Checa FFmpeg/Node, cria o venv e instala dependencias (so quando requirements/lockfile mudam)
%PY% scripts\bootstrap.py setup
if errorlevel 1 goto :fail

rem a) Ativa o ambiente virtual
call "backend\.venv\Scripts\activate.bat"

rem b) API em paralelo, numa janela propria (feche essa janela para encerrar a API)
python scripts\bootstrap.py api-status
if errorlevel 4 goto :port_busy
if errorlevel 3 goto :start_api
echo [start] API ja esta rodando em :8000 - reutilizando (feche a janela antiga para carregar codigo novo).
goto :frontend

:start_api
start "Shorts Engine API" /d "%~dp0backend" cmd /k python -m uvicorn main:app --host 127.0.0.1 --port 8000 --no-access-log
python scripts\bootstrap.py wait-api 120
if errorlevel 1 goto :fail
goto :frontend

:port_busy
echo [ERRO] A porta 8000 esta ocupada por outro programa. Libere-a e rode de novo.
goto :fail

:frontend
rem c) Interface web (abre o navegador)
cd /d "%~dp0frontend"
echo [start] Abrindo a interface... Ctrl+C encerra o frontend; a API segue na janela "Shorts Engine API".
call npm run dev -- --open
goto :eof

:fail
echo.
pause
exit /b 1
