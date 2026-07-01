#!/usr/bin/env bash
# Mini Jarvis — Linux/Arch one-click launcher
# Usage: bash run_mini_jarvis.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "[1/7] Checking Python..."
if ! python3 --version &>/dev/null; then
  echo "Python3 not found. Install it with: sudo pacman -S python  (or your distro's equivalent)"
  exit 1
fi

echo "[2/7] Preparing virtual environment..."
if [ ! -f ".venv/bin/python" ]; then
  python3 -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate

echo "[3/7] Installing / updating requirements..."
pip install --upgrade pip -q
pip install -r requirements.txt -q

echo "[4/7] Ensuring .env exists..."
if [ ! -f ".env" ]; then
  cp .env.example .env
  echo "  Created .env from .env.example — review it before running again."
fi

echo "[5/7] Checking Ollama model..."
OLLAMA_MODEL_NAME="${OLLAMA_MODEL:-qwen3.5:0.8b}"
if ! command -v ollama &>/dev/null; then
  echo "Ollama not found. Install it from https://ollama.com/download and retry."
  exit 1
fi
if ! ollama list 2>/dev/null | awk '{print $1}' | grep -Fxqi "$OLLAMA_MODEL_NAME"; then
  echo "  Pulling $OLLAMA_MODEL_NAME (first run only)..."
  ollama pull "$OLLAMA_MODEL_NAME"
fi

echo "[6/7] Starting Ollama server if not already running..."
if ! curl -sf http://127.0.0.1:11434/api/tags -o /dev/null 2>/dev/null; then
  echo "  Launching ollama serve in background..."
  ollama serve &
  OLLAMA_PID=$!
  sleep 2
  # Ensure we kill it if this script exits early
  trap 'kill "$OLLAMA_PID" 2>/dev/null || true' EXIT
else
  OLLAMA_PID=""
fi

echo "[7/7] Starting Mini Jarvis server..."
export HF_HUB_DISABLE_SYMLINKS_WARNING=1
export HF_HUB_DISABLE_TELEMETRY=1
python assistant_server.py

echo "Mini Jarvis stopped."
