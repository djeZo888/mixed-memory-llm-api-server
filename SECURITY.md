# SECURITY.md

## Security Status

This project is in early bootstrap. Treat all deployment automation as operator-reviewed until stable releases exist.

## Secret Policy

Do not commit secrets, tokens, passwords, SSH keys, API keys, sudo files, real `.env` files, Hugging Face tokens, GitHub tokens, auth files, model weights, or `/data/services/secrets` contents.

Do not commit `MEMORY.md`, `.codex/`, or local Codex memory files.

Only `.env.example` with placeholders belongs in git.

## API Exposure Policy

Backends bind to `127.0.0.1` by default. Any non-local exposure must require API-key authentication and a documented firewall/TLS or VPN policy.

## Reporting Security Issues

Use GitHub security advisories or the repository owner's preferred private channel. Do not open public issues containing credentials, private endpoints, or exploitable details.
