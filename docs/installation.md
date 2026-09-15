# Fresh Linux installation

## Delivery status: bounded I1b source; complete installer still pending

This revision adds container/toolkit, pinned runtime-artifact and GLM/Qwen
acquisition stages to I1's storage/prerequisite/driver graph. It **does not yet
provide the complete fresh-machine installer**. `ready` is always false. Full
`apply`/`resume` returns **78 before mutation** until I1c integrates and verifies
service, authenticated control API, client and actual chosen-role acceptance.

There is also a deliberate source integration checkpoint: package mutation
through `base` or later returns `reviewed_i1r_l1_package_integration_required`
until the reviewed I1R package transaction and L1 authorized lease-export/admission
interfaces are integrated. Their developing source is owned separately; this
checkout does not bypass them. Runtime parent-loss supervision must use the
reviewed ownership contract too. See [I1b stage interfaces](orchestration/i1b-stage-api.md),
[I1b report](../reports/i1b-runtime-acquisition.md) and
[I1S disk handoff](orchestration/i1s-storage-handoff.md).

Target: **Ubuntu 24.04 amd64**, system Python3, APT, CA certificates, Ubuntu
archive keyring, util-linux and root or sudo. A Mac is a source/test worker,
not a supported apply target. Source-only worker tests install no host packages,
change no live VM, restart no live service and download no model weights.

## Read-only plan

From the exact reviewed checkout:

```sh
./install.sh --help
./install.sh plan --profile flagship-hybrid --model-set glm --data-dir /data
./install.sh plan --config scripts/install/server.example.json
```

Server/combined roles require an explicit model set: `glm`, `qwen`, or `glm,qwen`.
`flagship-hybrid` selects GLM as the eventual active model; `fast-gpu` selects
Qwen. Only these reviewed acquisitions are supported. No implicit small-model
fallback or additional model download is performed.

The plan reports host support, exact packages/dependency hashes and bytes,
immutable runtime/source/base-image identities, registry blob transfer sizes,
model manifests/revisions/counts/bytes, dedicated storage and conservative
capacity reservations. It lists daemon start/restart and disposable GPU probe
effects. Image descriptor byte counts exclude Git/build package traffic; build
space remains a separate reservation. Shared blob digests and package names can
be deduplicated; the model filesystem receives no duplicate HF weight cache.

| Selection | Artifacts | Exact model bytes |
| --- | ---: | ---: |
| GLM-5.3 UD-Q4_K_XL | 11 | 467289116837 |
| Qwen3-Coder-Next-FP8 | 48 | 80407722953 |
| Both | 59 | 547696839790 |

Initial runtime/build reservations are 100 GiB for GLM and 40 GiB for Qwen,
combined when both are selected, plus 20 GiB free reserve per distinct filesystem.
These are disk budgets, **not measured RAM/VRAM fit requirements**. Acquisition
remeasures actual remaining bytes under one owner. Verified completed runtimes
already occupy filesystem space and are not reserved a second time during the
acquisition stage. On a registered host, read-only plan also reports actual
remaining model bytes; that size scan does not assert hash validity.

Plan writes no state, refreshes no package indexes and starts no daemon. Synthetic
host fixtures are labeled `SYNTHETIC_FIXTURE` and cannot enable apply/resume/verify.
Unavailable or changed registered storage fails closed. Package availability and
signed metadata are rechecked before installation; source research is not a
promise that a remote package remains available forever.

## Bounded stage interface

After the reviewed I1R/L1 integration checkpoint is resolved, the intended
bounded commands are:

```sh
sudo ./install.sh apply --config scripts/install/server.example.json --through runtime --yes
sudo ./install.sh resume --through acquisition --yes
sudo ./install.sh verify --through acquisition
sudo ./install.sh status
```

Boundaries: `storage`, `base`, `driver`, `container`, `runtime`, `acquisition`.
`models` aliases `acquisition`. Runtime includes the separate GPU-container gate.
Acquisition includes every selected manifest. The stages use the real dispatcher
and recheck postconditions on resume; complete stage markers alone never pass.
The commands above are **pending source integration**, not instructions to run
this unreviewed worker source on a live host. `--through storage` retains I1's
existing/mount boundary. `--dry-run` is read-only planning.

Driver installation may return **75 / REBOOT_CHECKPOINT**. No automatic reboot
occurs. Resume requires matching loaded module/userspace and expected GPU count.
GPU-container evidence is tied to actual boot, driver, pinned image and daemon
configuration; fixture records never constitute production GPU proof.

`status` distinguishes saved stage records from its current storage observation.
It does not assert service health. `verify --through acquisition` hashes all
expected model bytes again, which can take substantial time for 547.7 GB.
Changed config, lock, source or storage identities fail closed. A release upgrade
needs reviewed migration; deleting state or weakening hashes is not a migration.

## Container/runtime behavior

The package lock includes Docker/containerd/toolkit dependency closure with exact
primary URLs, bytes and SHA256, signed source/key identities and Ubuntu snapshot
policy. Private APT sources, archives, temporary files and logs live on dedicated
storage. OS package files necessarily consume the separately bounded root budget.
Existing host repository configuration is preserved.

Before first daemon start the stage prepares registered Docker/containerd/cache
roots, narrowly merges compatible config and installs mount-bound service
settings. Conflicting roots, unreviewed overrides, root payload and active
containers are refused. Existing compatible settings and data are preserved.
Package autostart prevention includes policy restoration and temporary masks for
Docker/containerd and NVIDIA CDI refresh units that bypass `policy-rc.d`.
Interrupted/unknown package ownership must be reconciled by I1R before unmasking.

GLM runtime uses the reviewed D1 Dockerfile, source commit, CUDA base digests,
architecture/build settings and source ancestry. Completed images are inspected;
CLI flags, source/CMake/compiler evidence and device enumeration are checked by
actual bounded probes before a production runtime contract is issued. Qwen uses
the exact reviewed SGLang registry digest and source/CLI capability contract.
A matching mutable tag alone never establishes identity. These stages activate
no model. SGLang native sentinel authentication remains a separate I1c/F1S gate.

## Acquisition and protected storage

Existing dedicated ext4/XFS filesystems may share data/models or use two exact
registered mounts. Root/boot ancestry, LVM/RAID/mapper devices, ambiguous UUIDs,
unsafe ancestry and symlinked/missing mounts are refused. `--storage-mode mount
--data-uuid UUID` supports an explicit existing filesystem and narrowly backed-up
fstab entry. Historical ai-vm UUIDs are never new-host defaults.

Blank-disk plan uses explicit stable by-id and matching confirmation. Formatting
remains unimplemented here; [I1S owns the concrete continuation](orchestration/i1s-storage-handoff.md).
It must prove transaction ownership and safe interruption before that checkpoint
can be removed. No live device is a formatting-test target.

Trust anchors are root-owned private `/etc/local-ai-server/storage.json` and
`bootstrap.json`. Stage state is under `<data>/services/installer`. Directory-FD
anchored I/O rechecks protected ancestry, inode/device, exact mount identity and
registration around bounded writes, fsync and rename. The continuous guard reads
mountinfo directly, avoiding a subprocess for every model-data chunk. Detachment
cannot redirect held-descriptor writes to an underlying root directory.

Acquisition uses one aggregate pool of at most four workers, up to six network
attempts per artifact, exact immutable URL/revision, valid Content-Range and
content length, consistent response identity, and computed SHA256 before atomic
promotion. Git assets also verify their pinned Git blob hash. Partial bytes survive
interruption. A corrupt full partial is preserved with a `.rejected.<sha256>.<unique>`
suffix; next resume retries that missing artifact without losing other shards.
Oversize, ambiguous or corrupt final files are preserved and rejected for review.

Expected manifests remain unchanged. Protected schema1 completion contracts are
`<roots.state>/acquisition/glm.complete.json` and/or `qwen.complete.json`. Each
contains exact manifest identity, registered destination, computed artifact
hashes and total verified bytes. Lifecycle must validate them through the reviewed
I1c/L1 integration. Completion proves acquisition only, not load/auth/health/tool
acceptance. API key bytes are never generated or rewritten by these stages.

## Remaining completion work and evidence limits

I1c must consume reviewed I1S, L1, I1R, F1S, U1 and V0 interfaces: protected release
source, keys/instances/boot/stopped intent, native SGLang auth sentinel proof,
authenticated model catalog/switch over the existing Manager, ordinary-user staged
OpenCode bootstrap, and actual chosen-role health/generation/streaming/tool/client
edit-test acceptance. The server remains API-only. Client tools require an
explicit ordinary user and trusted workspace; no browser UI or agent tools on
the inference VM.

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests/install -p 'test_*.py' -v
bash -n install.sh scripts/common/require-data-mounted.sh scripts/common/root-disk-guard.sh
./install.sh plan --profile flagship-hybrid --model-set glm,qwen \
  --fixture-host tests/install/fixtures/ubuntu-host.json
```

Evidence classes are separate: macOS filesystem/process/HTTP fixtures; primary
HTTP package/registry verification; Linux namespace/process tests (skipped here);
real Ubuntu package/systemd/GPU/model/client acceptance (**NOT_TESTED**). A full
fresh-host GPU installation and reboot remains **NOT_TESTED**. See the I1b report
for final counts and the exact handoff revision.
