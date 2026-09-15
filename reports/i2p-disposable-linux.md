# I2P — disposable Linux validation environment

Status: **IN_PROGRESS**. Coordinator revision1 selects a fresh GitHub-hosted
`ubuntu-24.04` VM instead of installing a Mac virtualization tool. Source base
`75a6bf915f30a1582348071eb733d05c33e10eb7`, branch
`milestone/i2p-disposable-linux`. Actual hosted observations will be recorded after
execution; no guest or installer acceptance is claimed yet.

## Worker capability and decision

Read-only CLI metadata: macOS26.6.2 arm64,32GiB RAM,10 CPUs,
`kern.hv_support=1`, UID502; initial free storage1,927,343,759,360 bytes
(about1.75TiB). QEMU,UTM,Lima,Multipass,Docker,Podman and alternative runner
executables were absent from PATH and bounded standard install locations.
Homebrew installed-package metadata and application names confirmed no guest
runner. An initial process-name search produced only unrelated input-method
names; it was not evidence of a running VM. No auth/global app config or raw
environment was read. No host software installed, no guest disk allocated.

Coordinator `incoming.md` revision1 supersedes the local guest-first request:
use an isolated hosted Ubuntu24.04 VM workflow and harmless real Linux primitive
probes, with no apt/install. No ai-vm access, local hypervisor, production device,
model/runtime/GPU or installer/lifecycle/auth/controller/client source changes.

## Evidence boundaries

The hosted runner is a fresh x64 VM with sudo, unlike the container-based
`ubuntu-slim` label. [GitHub runner documentation](https://docs.github.com/en/actions/reference/runners/github-hosted-runners).
The `ubuntu-24.04` label is a rolling image, **not an immutable Ubuntu image
checksum pin**. Record actual ImageOS/ImageVersion, kernel, OS and source hashes
per run. Actions and tested source are immutable commit-pinned. No claim of a
reproducibly pinned full guest image is made for this coordinator-selected route.
[Runner image lifecycle](https://docs.github.com/en/actions/concepts/runners/github-hosted-runners).

Real package watcher integration,I1R/I1S storage cases, full installer, real apt,
GPU installation/inference and reboot acceptance remain **NOT_TESTED**.

## Implementation and verification interface

[Usage and I2R/I2S continuation](../scripts/validation/i2p/README.md).
Dedicated workflow owns a fresh runner per attempt, exact-source checkout,
minimal root environment, ten-minute job/four-minute probe timeout and explicit
three-file sanitized artifact with14-day retention. No repository secrets are
passed to units. Actions are pinned to reviewed commit SHAs.

Local checks before first feature push: context/identity/refusal tests PASS,
main/loop dry-runs PASS; no Linux operations executed on Mac. Independent review
caught and fixed a systemd helper path protection issue, partition sysfs topology
handling and ambiguous loop-allocation cleanup reporting before live execution.
Each successful probe must include successful owned cleanup; ambiguous cleanup
fails the run. Actual CI result is pending and will be appended after observation.

The systemd primitive uses a living harmless supervisor as MainPID; a child
launcher exits normally or self-SIGKILLs while its descendant retains flock.
This does not prove I1R watcher survival or a service whose MainPID exits.
Units receive RuntimeMaxSec60,KillMode=control-group,PrivateDevices,
PrivateNetwork,64MiB memory and eight-task bounds.
[Ubuntu systemd execution documentation](https://manpages.ubuntu.com/manpages/noble/man5/systemd.exec.5.html).
