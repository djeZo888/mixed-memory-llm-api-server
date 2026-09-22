# ai-harness work

The user authorized implementation and deployment of [v0.0.1](PLAN-v0.0.1.md)
on 2026-09-22. This supersedes earlier frontend/harness exclusions for this
directory and bounded ai-harness work. Preserve all ai-vm production services,
weights, runtimes, GPU placement and warm dual-Qwen 480K configuration.

Mac-Orchestrator plans/reviews/synchronizes. Implementation, builds and tests
run through fresh remote Codex CLI tasks on mac-worker1 with isolated copies;
only assigned Worker1 tasks contact the VMs. Retain session IDs and evidence.

No GLM lifecycle work, new models, Proxmox changes, extra Linux login users,
general installer, mac-worker2, unsolicited sudoers changes, or secrets in Git.
Use the existing user account. If privileged setup requires user intervention,
prepare and review the exact minimal bootstrap first. Do not equate mock or
static tests with live deployment acceptance. Keep native engine patches small
and reproducible against the pinned source. No direct pushes to main.
