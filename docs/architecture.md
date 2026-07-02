# Architecture

## Layers

1. Host safety: preflight, disk dry-run, root-disk guard, and milestone reports.
2. Storage: `/data` for models, caches, Docker, containerd, builds, logs, services, backups, and secrets after M2.
3. Runtime profiles: backend-specific configuration for KTransformers and ik_llama.
4. API: OpenAI-compatible endpoints, local-first binding, and API-key enforcement for exposure.
5. Operations: health checks, logs, restarts, benchmark records, and troubleshooting.

## Default Network Posture

Inference backends bind to `127.0.0.1` by default. External access requires an explicit exposure milestone, API keys, and documented firewall/TLS or VPN controls.

## Data Boundary

The root disk is a control-plane disk. Large or persistent AI data belongs on `/data` only after the M2 data-disk milestone prepares it.
