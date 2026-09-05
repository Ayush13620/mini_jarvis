# Mini Jarvis — Online Edition

[![GitHub](https://img.shields.io/badge/GitHub-Ayush13620-blue)](https://github.com/Ayush13620/mini_jarvis)

Cloud-powered voice assistant with ultra-fast response times and natural voice.

ESP32 mic stream → Python server (VAD + STT) → Groq Cloud LLM → Edge Neural TTS → laptop speaker + HUD display

## Stack

| Component | Provider | Model |
|-----------|----------|-------|
| STT | Groq Cloud | `whisper-large-v3` |
| LLM | Groq Cloud | `llama-3.3-70b-versatile` |
| TTS | Microsoft Edge | `en-US-ChristopherNeural` |

## Quick start

### Linux

```bash
cd online
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env and add your GROQ_API_KEY from https://console.groq.com
python assistant_server.py
```

Or use one-click launcher:

```bash
bash run_mini_jarvis.sh
```

### Windows

```powershell
cd online
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
Copy-Item .env.example .env
# Edit .env and add your GROQ_API_KEY from https://console.groq.com
python assistant_server.py
```

Or use one-click launcher:

```powershell
run_mini_jarvis.bat
```

## Getting API keys

### Groq (free tier)

1. Visit https://console.groq.com
2. Sign up for a free account
3. Create an API key
4. Add to `.env`:
   ```
   GROQ_API_KEY=gsk_your_key_here
   ```

Groq's free tier includes:
- 30 requests/minute for chat
- 7,200 requests/hour for STT
- No credit card required

## Configuration

All settings are in `.env`. Key options:

| Variable | Default | Description |
|----------|---------|-------------|
| `STT_PROVIDER` | `groq` | Cloud STT (groq, openai) |
| `GROQ_STT_MODEL` | `whisper-large-v3` | Whisper model on Groq |
| `USE_OLLAMA_CHAT` | `false` | Use Groq/OpenAI instead of Ollama |
| `GROQ_MODEL` | `llama-3.3-70b-versatile` | LLM model |
| `TTS_PROVIDER` | `edge-tts` | Cloud TTS (edge-tts, openai) |
| `EDGE_TTS_VOICE` | `en-US-ChristopherNeural` | TTS voice |
| `ENABLE_HUD` | `true` | Show hologram HUD window |

### Available voices (edge-tts)

- `en-US-ChristopherNeural` (default, male)
- `en-US-JennyNeural` (female)
- `en-US-GuyNeural` (male)
- `en-US-AriaNeural` (female)

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
            │ Groq Cloud   │    │  Groq Cloud  │    │ Hologram HUD │
            │  (Whisper)   │    │  (LLM)       │    │  (pygame)    │
            └──────────────┘    └──────────────┘    └──────────────┘
                                         │
                                         ▼
                                 ┌──────────────┐
                                 │  Edge-TTS    │
                                 │  (Neural)    │
                                 └──────────────┘
```

Requires internet connection to Groq and Microsoft Edge TTS endpoints.

## Troubleshooting

### ESP32 won't connect
- Confirm server prints `listening on 0.0.0.0:5000`
- Ensure laptop and ESP32 are on the same Wi-Fi network
- Check firewall allows inbound TCP 5000

### Groq API errors
- Verify `GROQ_API_KEY` is set correctly in `.env`
- Check rate limits at https://console.groq.com
- Ensure API key has access to `llama-3.3-70b-versatile` model

### Poor transcription
- Check mic gain isn't clipping
- Tune VAD settings in `.env`

### Slow response
- Check internet connection speed
- Groq is usually <2s — slower responses indicate network issues

## License

MIT License — see LICENSE file for details.
