# ai-harness work

The user authorized implementation and deployment of [v0.0.1](PLAN-v0.0.1.md)
and the [v0.0.2 work](PLAN-v0.0.2.md) on 2026-09-22. This supersedes earlier
frontend/harness exclusions for this directory and bounded ai-harness work.
Root-authorized v0.0.2 deployment and focused live acceptance supersede the
earlier fixture-only task restriction. The
[v0.0.2 acceptance report](docs/acceptance-v0.0.2.md) records current outcomes
and distinguishes actual deployment/live evidence from synthetic fixtures.
The bounded campaign and readback are complete; their grants do not authorize
further inference, deployment or unrelated history inspection.
Production changes and live inference remain separately assigned and root
coordinated within the current task's source/runtime/origin grant. Fixture
evidence alone grants no production access. Owned UI acceptance must preserve
other users' conversations/files and shared services; it grants no ai-vm contact.
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
