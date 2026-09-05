# Mini Jarvis — Offline Edition

[![GitHub](https://img.shields.io/badge/GitHub-Ayush13620-blue)](https://github.com/Ayush13620/mini_jarvis)

Fully offline voice assistant — no cloud APIs required after initial setup.

ESP32 mic stream → Python server (VAD + STT) → Ollama chat → pyttsx3 TTS → laptop speaker + HUD display

## Stack

| Component | Provider | Model |
|-----------|----------|-------|
| STT | faster-whisper (local) | `tiny.en` (~40MB) |
| LLM | Ollama (local) | `qwen3.5:0.8b` (~400MB) |
| TTS | pyttsx3 (local) | offline synthesis |

## Quick start

### Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Install Ollama: https://ollama.com/download
ollama serve &
ollama pull qwen3.5:0.8b
python assistant_server.py
```

Or use one-click launcher:

```bash
bash run_mini_jarvis.sh
```

### Windows

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
Copy-Item .env.example .env
# Install Ollama from https://ollama.com/download
ollama serve
ollama pull qwen3.5:0.8b
python assistant_server.py
```

Or use one-click launcher:

```powershell
run_mini_jarvis.bat
```

## Hardware requirements

- **CPU:** Modern x86_64 (Whisper runs on CPU)
- **RAM:** 4GB minimum, 8GB recommended
  - faster-whisper tiny.en: ~1GB
  - Ollama qwen3.5:0.8b: ~1.5GB
- **Disk:** ~2GB for models
- **Microphone:** ESP32 with I2S/analog mic (see `esp32_firmware/`)

## Configuration

All settings are in `.env`. Key options:

| Variable | Default | Description |
|----------|---------|-------------|
| `STT_PROVIDER` | `local` | Whisper model (local only) |
| `WHISPER_MODEL` | `tiny.en` | Model size: tiny.en, base.en, small.en |
| `USE_OLLAMA_CHAT` | `true` | Use Ollama (offline) |
| `OLLAMA_MODEL` | `qwen3.5:0.8b` | LLM size — upgrade to `qwen3.5:2b` for better answers |
| `TTS_PROVIDER` | `local` | pyttsx3 (offline) |
| `ENABLE_HUD` | `true` | Show hologram HUD window |

## ESP32 setup

1. Flash `esp32_firmware/esp32_firmware.ino` via Arduino IDE
2. If credentials are missing/invalid, ESP32 opens AP `Jarvis-Setup`
3. Connect to AP and open `http://192.168.4.1`
4. Login with `admin` / `<password-shown-on-serial-monitor>`
5. Configure:
   - Wi-Fi SSID/password
   - Server IP (your laptop's local IP)
   - Server port (`5000` by default)
   - Optional AUTH token (must match server's `.env`)

### Serial commands

- `SHOWCFG` / `STATUS` — print config and connection state
- `RESETCFG` — clear saved config and reboot to setup mode

## Architecture

```
┌─────────────┐    TCP Audio     ┌──────────────────┐
│   ESP32     │ ────────────────▶│  Python Server   │
│  (mic+relay)│◀──────────────── │ (VAD+STT+Chat)   │
└─────────────┘   JSON Commands  └──────────────────┘
                                         │
                    ┌────────────────────┼────────────────────┐
                    ▼                    ▼                    ▼
            ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
            │ faster-      │    │  Ollama      │    │ Hologram HUD │
            │ whisper      │    │  (qwen3.5)   │    │  (pygame)    │
            │ (tiny.en)    │    │              │    │              │
            └──────────────┘    └──────────────┘    └──────────────┘
                                         │
                                         ▼
                                 ┌──────────────┐
                                 │  pyttsx3     │
                                 │  (TTS)       │
                                 └──────────────┘
```

All components run locally — no internet required.

## Troubleshooting

### ESP32 won't connect
- Confirm server prints `listening on 0.0.0.0:5000`
- Ensure laptop and ESP32 are on the same Wi-Fi network
- Check firewall allows inbound TCP 5000

### Poor transcription
- Check mic gain isn't clipping (use serial monitor for `p2p` values)
- Tune VAD settings in `.env`:
  - `ENERGY_THRESHOLD=280` — Increase for noisy rooms
  - `VAD_MULTIPLIER=3.2` — Higher = less sensitive

### Slow startup
- First run downloads Whisper model (~40MB for `tiny.en`)
- Ollama pulls the chat model on first run (~400MB for `qwen3.5:0.8b`)
- Use `WHISPER_MODEL=tiny.en` for fastest startup
- Use `OLLAMA_MODEL=qwen3.5:2b` for stronger answers (needs more RAM)

### Hologram HUD not showing
- Ensure `pygame>=2.5.0` is installed
- Set `ENABLE_HUD=true` in `.env`

## License

MIT License — see LICENSE file for details.
