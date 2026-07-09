# Offline Resilience Goals

M9F reframes the project around local AI resilience. The primary goal is not cost saving. The goal is to keep a useful, high-quality AI capability available when internet access is degraded, expensive, filtered, unreliable, or unavailable.

## Mission

The system should provide a local AI service that remains useful during an internet blackout or degraded-internet scenario. Online web tools, hosted APIs, and browser-assisted research are still valuable when the network works, but they must not be required for the core local assistant function.

The local system should be able to act as:

- Technical assistant for coding, sysadmin, debugging, architecture, and operational planning.
- General knowledge assistant for broad explanations, synthesis, and planning.
- Long-context project worker for large dossiers, repositories, reports, and multi-step local work.
- Local search and knowledge interface over saved documents, web captures, project notes, and prior sessions.

## Design Priorities

- Preserve a healthy localhost-only active backend before every large-model experiment.
- Put the VM's system RAM to real use through mixed RAM/VRAM inference rather than treating full VRAM fit as mandatory.
- Prefer answer quality and local availability over peak tokens/sec for hard work. Several tokens/sec is acceptable if the result is materially better.
- Keep at least one very large local model path on the roadmap for hard technical, multi-step, and general tasks.
- Add local memory/RAG as a core feature, not as a later convenience.
- Save online research and web-scraped material with provenance so it can be used offline later.
- Keep public API/front-door/auth work deferred until local function, routing, and memory are robust.

## Non-Goals For M9F

M9F does not download models, pull images, build runtimes, stop or restart the 30B backend, start new containers, expose an API, create services, or change Docker/containerd daemon configuration. It is a planning and documentation milestone only.

## Offline Operating Target

A useful offline setup should support these flows:

- Ask a short technical or general question and get a direct local answer.
- Attach a local project directory, report bundle, or saved web dossier and have a long-context worker process it.
- Search local memory for prior decisions, source excerpts, and captured pages.
- Create a retrieval pack with citations and pass it to the active model.
- Switch model roles while preserving the one-active-backend policy.

## Exposure Policy

All backends remain localhost-first. Public API exposure, reverse proxy, auth, TLS, firewall changes, and external front-door work stay secondary to the local offline-resilience mission and require later reviewed milestones.
