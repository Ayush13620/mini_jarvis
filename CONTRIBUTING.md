# Contributing Guide

Thanks for contributing to Mini Jarvis.

## Development setup

```powershell
cd C:\Users\Ayush\Desktop\mini_jarvis
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

## Run locally

```powershell
.\.venv\Scripts\python.exe assistant_server.py
```

For ESP32 firmware, open:

- `esp32_stream_client_with_login/esp32_stream_client_with_login.ino`

## Testing

Run Python tests before opening a PR:

```powershell
python -m unittest discover -v
```

## Coding conventions

- Keep changes focused and small.
- Prefer configuration via `.env` over hardcoding.
- Avoid committing generated artifacts (`.venv`, logs, binaries, `.env`).
- Add/adjust tests when changing decode, VAD, or transcript-filter logic.

## Pull request checklist

- [ ] Project still runs end-to-end
- [ ] Tests pass
- [ ] README updated if behavior changed
- [ ] No secrets committed

## Areas where help is welcome

- audio quality and noise suppression
- network resilience and reconnect logic
- ESP32 reliability and diagnostics
- documentation and onboarding improvements
