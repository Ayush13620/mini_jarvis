# Security Policy

## Supported versions

This project is currently in alpha (`v0.1-alpha`), and security fixes are applied to the latest `main` branch.

## Reporting a vulnerability

If you find a security issue, please do not open a public issue with exploit details.

Please report privately via:

- GitHub private security advisory (preferred), or
- direct contact with the repository maintainer

When reporting, include:

- affected file/component
- steps to reproduce
- expected vs actual behavior
- potential impact

## Security notes for this project

- ESP32 setup portal credentials are device-generated and printed on serial output.
- Configuration traffic in setup mode is HTTP over local AP and is not encrypted.
- Optional `AUTH_TOKEN` is available for ESP32 -> server handshake.
- Do not commit `.env` or secrets to Git.

## Recommended deployment precautions

- Keep laptop Wi-Fi profile as `Private` only on trusted networks.
- Restrict inbound firewall rule to required network profile and port (`5000`).
- Rotate setup credentials by resetting device config (`RESETCFG`) when needed.
