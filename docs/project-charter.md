# Project Charter

## Purpose

Build a reproducible open-source deployment framework for large local LLM inference on mixed system-RAM plus NVIDIA-VRAM workstations.

## In Scope

- Host preflight checks.
- Data-disk safety and root-disk protection.
- Backend profiles for KTransformers and ik_llama.
- Authenticated OpenAI-compatible API serving.
- Repeatable tests, reports, and benchmarks.

## Out Of Scope

- Web browsing.
- Web scraping.
- Browser automation.
- Human chat UI.
- Committing model weights or secrets.

## Success Criteria

A new operator can follow milestone reports and scripts to deploy, verify, operate, and benchmark local LLM backends without filling the root disk or exposing an unauthenticated API.
