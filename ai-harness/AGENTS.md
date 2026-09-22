# ai-harness work

The user authorized implementation and deployment of [v0.0.1](PLAN-v0.0.1.md)
and the [v0.0.2 work](PLAN-v0.0.2.md) on 2026-09-22. This supersedes earlier
frontend/harness exclusions for this directory and bounded ai-harness work.
The current H002-UI-FIXTURES task is source/fixture and release-document
preparation only; see the [v0.0.2 acceptance report](docs/acceptance-v0.0.2.md).
Its isolated rootless browser fixture allowance authorizes no production app,
gateway/inference, deployment, shared-service or ai-vm contact. Production and
any later live acceptance remain separately assigned and root coordinated.
Preserve all ai-vm production services, weights, runtimes, GPU placement and warm
dual-Qwen 480K configuration.

Mac-Orchestrator plans/reviews/synchronizes. Implementation, builds and tests
run through fresh remote Codex CLI tasks on mac-worker1 and mac-worker2 with
isolated copies; only assigned worker tasks contact the VMs. Retain session IDs
and evidence. Coordinate shared service changes and live inference centrally.

No GLM lifecycle work, new models, Proxmox changes, extra Linux login users,
general installer, unsolicited sudoers changes, or secrets in Git.
Use the existing user account. The user has enabled on-demand passwordless sudo
for necessary host setup; keep ordinary project files and runtime services owned
by the existing unprivileged user. Do not equate mock or
static tests with live deployment acceptance. Keep native engine patches small
and reproducible against the pinned source. No direct pushes to main.
