# Mini Jarvis (ESP32 + Laptop) - v0.1 Alpha

Mini Jarvis is a local-first voice assistant pipeline:

ESP32 mic stream -> Python server (VAD + STT) -> local Ollama chat -> local TTS (laptop speaker)

This repository is currently an alpha proof-of-concept focused on rapid iteration and demos.

## Current status

- Works end-to-end with local STT/chat/TTS
- Includes ESP32 Wi-Fi setup portal + saved config
- Includes reconnect handling and runtime diagnostics
- Still has known instability in noisy environments

## Project layout

- `assistant_server.py`: TCP server + VAD + STT + chat + TTS
- `esp32_stream_client_with_login/esp32_stream_client_with_login.ino`: ESP32 firmware with setup portal
- `esp32_mic_input_test/esp32_mic_input_test.ino`: standalone mic input tester
- `requirements.txt`: Python dependencies
- `.env.example`: runtime config template
- `run_mini_jarvis.bat`: one-click launcher

## Quick start (Windows)

```powershell
cd C:\Users\Ayush\Desktop\mini_jarvis
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
Copy-Item .env.example .env
```

Start Ollama:

```powershell
ollama pull qwen2.5:3b-instruct
ollama serve
```

Start server:

```powershell
.\.venv\Scripts\python.exe assistant_server.py
```

Or use one-click launcher:

```powershell
run_mini_jarvis.bat
```

## ESP32 setup

1. Flash `esp32_stream_client_with_login.ino`.
2. If credentials are missing/invalid, ESP32 opens AP `Jarvis-Setup`.
3. Connect to AP and open `http://192.168.4.1`.
4. Save:
- home Wi-Fi SSID/password
- `server_ip` (your laptop IPv4)
- `server_port` (`5000` by default)

Serial commands:

- `SHOWCFG` / `STATUS`: print config and connection state
- `RESETCFG`: clear saved config and reboot to setup mode

## Known issues (alpha)

- Network profile/firewall can block ESP32 -> laptop TCP connect
- Audio quality is sensitive to mic gain and electrical noise
- False triggers or missed words may occur in noisy rooms
- TTS currently plays on laptop only (not streamed back to ESP32 speaker)

## Troubleshooting

1. If ESP32 cannot connect:
- confirm server prints `listening on 0.0.0.0:5000`
- confirm laptop/ESP32 are on same subnet
- ensure Windows firewall allows inbound TCP 5000 on active profile

2. If transcription is poor:
- calibrate mic gain to avoid clipping
- use `esp32_mic_input_test` and keep `p2p` out of saturation
- tune `.env` VAD settings (`ENERGY_THRESHOLD`, `VAD_MULTIPLIER`, `MAX_SPEECH_MS`)

3. If startup is too slow:
- use `WHISPER_MODEL=small.en` in `.env`

## Roadmap

- mDNS/hostname discovery to reduce static-IP dependency
- stronger audio preprocessing (AGC/noise suppression)
- richer health dashboard and metrics
- stream assistant audio back to ESP32 speaker
- modularize server code into smaller packages
