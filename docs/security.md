# Security

## Core Rules

- No secrets in git.
- No real `.env` files in git.
- No local Codex memory files in git.
- No model weights in git.
- API exposure beyond localhost requires API-key auth and documented firewall/TLS or VPN policy.

## Secret Scan

Run a grep-based secret scan before every push. If a real secret is found, stop and do not push.

## Storage Safety

Root-disk exhaustion is a security and reliability risk. Large AI data belongs on `/data` only after M2 prepares it.
