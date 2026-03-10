@echo off
setlocal

cd /d "%~dp0"
title Mini Jarvis Launcher

echo [1/7] Checking Python...
python --version >nul 2>&1
if errorlevel 1 (
  echo Python not found. Install Python 3.10+ and retry.
  pause
  exit /b 1
)

echo [2/7] Preparing virtual environment...
if not exist ".venv\Scripts\python.exe" (
  python -m venv .venv
  if errorlevel 1 (
    echo Failed to create virtual environment.
    pause
    exit /b 1
  )
)

echo [3/7] Installing requirements...
call ".venv\Scripts\activate.bat"
python -m pip install --upgrade pip
pip install -r requirements.txt
if errorlevel 1 (
  echo Dependency install failed.
  pause
  exit /b 1
)

echo [4/7] Ensuring .env exists...
if not exist ".env" (
  copy ".env.example" ".env" >nul
)

echo [5/7] Ensuring Ollama model exists...
ollama list | findstr /i "qwen2.5:3b-instruct" >nul
if errorlevel 1 (
  ollama pull qwen2.5:3b-instruct
  if errorlevel 1 (
    echo Could not pull Ollama model.
    pause
    exit /b 1
  )
)

echo [6/7] Starting Ollama server if needed...
powershell -NoProfile -Command "try { Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/tags' -TimeoutSec 2 | Out-Null; exit 0 } catch { exit 1 }"
if errorlevel 1 (
  start "Ollama Serve" cmd /c "ollama serve"
  timeout /t 2 /nobreak >nul
)

echo [7/7] Starting Mini Jarvis server...
set HF_HUB_DISABLE_SYMLINKS_WARNING=1
set HF_HUB_DISABLE_TELEMETRY=1
python assistant_server.py

echo Mini Jarvis stopped.
pause
