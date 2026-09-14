# Fresh Linux installation

## Delivery status: I1 prerequisites boundary; I1b required

The full fresh-machine installer is **not complete**. This revision implements
read-only planning, protected dedicated storage registration/adoption, pinned
Ubuntu base packages, driver installation and an explicit reboot checkpoint.
Full `apply`/`resume` refuses before mutation with exit **78** while required
runtime/model/service/client/acceptance stages are missing. It never prints READY.
See [I1 report](../reports/i1-installer-prerequisites.md) and
[I1b continuation](../reports/i1b-continuation.md).

Supported target for this boundary: **Ubuntu 24.04 amd64**, system Python3,
APT, CA certificates, Ubuntu archive keyring, util-linux and root or sudo. An existing mounted **ext4 or XFS** filesystem
on a dedicated disk is supported. One data/model filesystem or two separately
registered filesystems are supported. LVM, RAID, mapper devices, root/boot disk
ancestry, ambiguous UUIDs, symlinked roots and a missing mount are refused.
Other hosts are reported unsupported; a Mac cannot be used to apply this source.
No Codex/cloud subscription or cloud API key is required.

## Read-only plan

Use a reviewed checkout. Do not pipe a download into a shell. Inspect the config
and preserve its identity for resume:

```sh
./install.sh --help
./install.sh plan --profile flagship-hybrid --model-set glm --data-dir /data
./install.sh plan --config scripts/install/server.example.json
```

`--profile flagship-hybrid` selects GLM as the intended active model;
`--profile fast-gpu` selects Qwen. `--model-set glm`, `qwen` or `glm,qwen` is
mandatory for server/combined roles. There is no implicit smoke downgrade.
The example explicitly selects both models; select only the desired artifacts.

The plan reports OS/kernel/RAM/GPU observations, exact package lock, model
revision/manifest/download bytes, storage identity, disk reserves, selected
stages and effects. A fixture is always labeled **SYNTHETIC_FIXTURE**. Expected
weight sizes are 467289116837 bytes for GLM and 80407722953 bytes for Qwen;
these are **disk** requirements. No measured RAM/VRAM minimum or full-model fit
is published by I1. D1/F1A dual-96GB hardware observations do not prove model fit.
Runtime build reservations (100GiB with GLM; otherwise40GiB) plus20GiB spare are
conservative disk estimates. I1b acquisition must account for actual remaining
bytes and shared filesystem reservations before downloading.

Unavailable storage is reported unverified, not ready. `plan` does not refresh
APT indexes, install packages, write state, initialize disks or query inference.
Exact pin availability is checked by signed metadata before package installation;
[package source evidence](../reports/i1-package-sources.md) records research.

## Explicit partial prerequisite application

These commands are for the reviewed prerequisite boundary on an authorized
Linux test host. They **do not install a usable inference service**:

```sh
sudo ./install.sh apply --config scripts/install/server.example.json --through driver --yes
sudo ./install.sh resume --through driver --yes
sudo ./install.sh verify --through driver
sudo ./install.sh status
```

`--through storage` and `--through base` are narrower boundaries. Normal
`./install.sh apply --config ... --yes` returns78 until I1b completes.
`--dry-run` redirects to read-only planning; a fixture can only be passed to
`plan`, never mutation or verification commands.

Driver changes may return **75 / REBOOT_CHECKPOINT**. Read the protected
`driver-checkpoint.json` for the target kernel and Secure Boot result. Reboot
explicitly into the recorded signed kernel, then run the resume command above.
The installer never reboots automatically. A same-boot retry does not pass;
module/userspace versions and the expected distinct GPU count must agree.
Firmware/signing or driver failure after reboot remains a failure needing
external resolution. GPU-container execution belongs to I1b and is not implied
by a driver query. Compatible loaded drivers are preserved; no host CUDA Toolkit
or DKMS build is installed by this boundary.

APT uses a private signed Ubuntu snapshot source, lists, archive cache, temporary
files and logs on data; existing host sources remain unchanged. Missing pins,
unlocked dependency changes, removals or downgrades stop. OS packages necessarily
consume root space; the configured package budget and free-space reserve gate
installation. Package service starts are temporarily inhibited with a saved
policy restored after the transaction; interrupted policy state is recoverable.
Read [package policy](../reports/i1-package-sources.md) before target testing.

## Storage identity and persistence

Default `--storage-mode existing` adopts the explicit exact mount. Supplying
`--data-uuid` pins the expected UUID in advance; if omitted, the observed UUID is
registered at adoption and becomes authoritative. `--model-dir` defaults to
`<data-dir>/models`. A distinct mounted model filesystem may be registered with
`--model-dir` and `--model-uuid`.

`--storage-mode mount --data-uuid UUID` explicitly allows mounting an existing
filesystem by UUID and adding a matching fstab entry. The target must be empty
when unmounted. Existing config/data are preserved. A content-addressed fstab
backup is on the verified data filesystem before fstab replacement. A conflicting
entry or an already-mounted UUID at another target is refused.

Blank-disk **planning only** accepts `--storage-mode initialize
--initialize-empty-disk /dev/disk/by-id/ID --confirm-disk-id ID`. It checks stable
serial/WWN/size, signatures, partitions, holders and root/boot ancestry. Actual
initialization is pending I1b; this revision cannot partition or format a disk.
NVMe partition topology is tested synthetically; no real device was exercised.

Tiny protected trust anchors:

- `/etc/local-ai-server/storage.json`: schema1 data/model roots, UUIDs and layout.
- `/etc/local-ai-server/bootstrap.json`: schema1 config/source/lock hashes and
  state locator; no credentials.

Bulk state is under `<data-dir>`: `services/installer/state.json`, protected
checkpoints, `cache/installer-apt`, `build`, `hf-cache`, `models`, `docker`,
`containerd`, `logs`, `backups` and `services/secrets`. State/secrets directories
are0700; JSON state is0600. Observed missing storage stops writes. Directory-FD anchored writes across a
mount-detach race are still required in I1b; this boundary does not prove that
race safe and is for reviewed disposable testing.
The generic common guards use the fixed root-owned registry, ignore UUID/path
environment overrides and refuse unsafe legacy test overrides when registered.
Historical ai-vm UUIDs remain in legacy-only branches and never choose a fresh
installer identity.

One `/run/llmctl/lifecycle.lock` lease covers a prerequisite transition. Atomic
stage records include schema, installation ID, config/input/lock hashes,
attempt/start/end/status and sanitized failures. Every resumed stage rechecks
postconditions. An identical completed boundary runs verification without
rewriting state, packages or credentials. Incompatible config/source/lock changes
fail closed; source upgrades need an explicit reviewed migration in I1b.
`status` labels saved state and storage observation separately; it does not
claim current service health. `verify --through ...` proves only that boundary.

## Client and deployment integration still required

`--role server|client|combined` validates role-specific inputs. Client/combined
require explicit ordinary `--client-user`, workspace/prefix, loopback API URL,
model ID and protected key reference. Root is rejected as the client user.
These are configuration interfaces only in I1. I1b must provision pinned Node/npm,
consume [V0](client-install.md), provide the SSH tunnel helper, and run the real
bounded OpenCode read/edit/test acceptance as the ordinary user. Server-only
machines remain API-only and must not execute agent tools.

I1b must integrate L1 generic storage + single-owner lifecycle, safe F1S file auth
and actual image sentinel gate, pinned D1 build/import, resumable per-file
acquisition, API key preservation, systemd mount ordering/stopped intent,
rollback, liveness/readiness/auth/generation/streaming/tool continuation and
client acceptance. No unavailable gate may be labeled successful.

## Worker checks and evidence limits

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests/install -p 'test_*.py' -v
bash -n install.sh scripts/common/require-data-mounted.sh scripts/common/root-disk-guard.sh
./install.sh plan --profile flagship-hybrid --model-set glm,qwen \
  --fixture-host tests/install/fixtures/ubuntu-host.json
```

I1 tests use temporary files, fake command outputs and process-lock fixtures.
They install no host packages, touch no VM disk, download no weights and activate
no model. Ubuntu container/bootstrap, real loopback mounts, live adoption,
GPU-container/model/client behavior and full fresh-host GPU/reboot acceptance
are **NOT_TESTED** here. I2 must report each later evidence class separately.
