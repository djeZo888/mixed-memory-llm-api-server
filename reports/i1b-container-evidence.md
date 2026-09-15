# I1b container engine, toolkit, and GPU gate source

Status: **PASS for bounded source and synthetic tests; package execution PENDING
reviewed I1R transaction/lease integration.** No ai-vm access or mutation occurred.
Fresh Linux package/service execution, actual GPU gate, and fresh boot are
**NOT_TESTED**. Whole-installer readiness is not claimed.

## Delivered interface

`scripts/install/container.py` exports:

```python
ContainerStage(config, runner, guard, *, prereqs=None,
               system_root=Path('/'), uid=0, lock=None)
check() -> bool
apply() -> evidence
check_gpu() -> bool
apply_gpu() -> evidence
```

The dispatcher owns the existing global installer/lifecycle lease throughout.
`guard()` returns the exact I1 protected storage registration, including `data`,
`models`, and `roots`. The class uses generic registered data paths; it contains no
ai-vm UUID, disk name, or mandatory `/data` path. Test root/UID/Runner injection is
an in-process seam, with no CLI/environment bypass.

`ContainerPackages` extends the existing `Prerequisites` package solver and policy
transaction. It adds exact Docker/NVIDIA sources and keys, and held directory-FD
paths for apt caches, lists, sources, archives, logs, and temporary files.
`/proc/<installer PID>/fd/<FD>/...` keeps subprocess destinations on the original
filesystem if the public mount disappears. State/key/source writes use
`scripts/install/storage_io.py` anchored files and atomic promotion. Private apt
storage uses `APT::Sandbox::User=root`; unprivileged `_apt` cannot traverse these
0700 registered directories. No host apt source list is replaced.

The default stage constructs this subclass. Injecting vanilla I1 Prerequisites
would omit the container repository/anchor extensions and is unsupported.

## Exact source and archive verification

The existing reviewed lock contains Docker engine/CLI
`5:29.6.1-1~ubuntu.24.04~noble`, containerd
`2.2.5-1~ubuntu.24.04~noble`, buildx
`0.35.0-1~ubuntu.24.04~noble`, and all four NVIDIA container packages `1.19.1-1`.
The Ubuntu dependency snapshot remains `20260707T140000Z`.

On 2026-09-15, the worker fetched and computed SHA256 for **all 37 unique archives
in the Docker/toolkit dependency union: 95,799,538 bytes**. Every size and hash
matched `scripts/install/versions.lock.json`. These verification downloads were
streamed into a digest in memory; no archive payload was saved on the worker root
filesystem. Dependency closure originates in I1's empty-dpkg-status apt simulation;
actual fresh Linux solver execution remains untested here. The inherited solver
rejects changed/unlocked dependencies, removals, and downgrades before installation.

Current primary Docker/NVIDIA package indexes matched the exact version/SHA256/size
of all eight requested packages. Checked index identities:

| Primary index | Download bytes | Computed SHA256 |
| --- | ---: | --- |
| `https://download.docker.com/linux/ubuntu/dists/noble/stable/binary-amd64/Packages.gz` | 79,331 | `ab2747b0eafe295134d4f58886ab7074f8b703853d9874b6f57c85c15507a11b` |
| `https://nvidia.github.io/libnvidia-container/stable/deb/amd64/Packages` | 172,146 | `0f49d47408ff375dcf85174a8f29d21104b0b55960525951fb3e9cb3b966c112` |

Added exact primary repository key inputs:

| Key | Bytes | SHA256 | Primary fingerprint |
| --- | ---: | --- | --- |
| Docker `https://download.docker.com/linux/ubuntu/gpg` | 3,817 | `1500c1f56fa9e26b9b8f42452a553675796ade0807cdce11975eb98170b3a570` | `9DC858229FC7DD38854AE2D88D81803C0EBFCD88` |
| NVIDIA `https://nvidia.github.io/libnvidia-container/gpgkey` | 3,195 | `c880576d6cf75a48e5027a871bac70fd0421ab07d2b55f30877b21f1c87959c9` | `C95B321B61E88C1809C4F759DDCAE044F796ECB0` |

The worker computed key fingerprints from the downloaded OpenPGP primary packet.
The worker did not run gpg signature verification or apt; actual install uses apt's
signed metadata verification with the hash-pinned keys and then compares archive
metadata against the committed lock. Key rotation fails closed until reviewed.
Upstream repository/version-selection guidance was checked at
[Docker Ubuntu installation](https://docs.docker.com/engine/install/ubuntu/) and
[NVIDIA Toolkit installation](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html).

## Service, configuration, and interruption behavior

- Docker/containerd persistent roots and temporary/cache directories are on
  registered storage before package installation. Docker's existing settings and
  custom runtimes are narrowly retained; semantically complete daemon JSON and
  compatible containerd TOML are preserved byte-for-byte. Original protected
  backups are written once and validated on resume.
- Configured or observed mismatching roots, populated old root payload, ambiguous
  imported containerd configs, root/config command overrides (including compact
  short options), unsafe API listeners, and unbounded log settings fail closed.
  Existing active daemons needing a change require coordinated service work; this
  stage never silently migrates data or restarts another workload.
- The exact `.deb` maintainer scripts were inspected. Docker/containerd use
  `invoke-rc.d`/`deb-systemd-invoke`. NVIDIA toolkit-base directly calls
  `systemctl enable --now` and `systemctl start` for CDI refresh units. Therefore
  all five units are temporarily runtime-masked: Docker service/socket,
  containerd service, and NVIDIA CDI refresh path/service. Existing masks and the
  prior `policy-rc.d` bytes/mode are preserved.
- Configuration validation precedes explicit Docker/containerd start. Drop-ins
  require the registered mount and bind it into private service mount namespaces.
  The postcondition checks effective `Environment`, `BindPaths`, `PrivateMounts`,
  service argv, live DockerRootDir/runtime, and parsed containerd config. A changed
  completion marker cannot bypass those observations. Private-bind compatibility
  between Docker/containerd still needs a real disposable Linux service test.
- Container JSON logs have bounded rotation on registered Docker storage. Daemon
  stdout/stderr are disabled to avoid root journal growth. Protected installer apt
  logs and structured stage evidence remain on registered storage.

Docker documents separate daemon/containerd storage configuration; containerd's
pinned configuration reference specifies global root/state and imported overrides.
([Docker daemon configuration](https://docs.docker.com/engine/daemon/),
[containerd v2.2.5 configuration](https://github.com/containerd/containerd/blob/v2.2.5/docs/man/containerd-config.toml.5.md))

## GPU gate

The gate reuses the reviewed D1 CUDA runtime image:
`nvidia/cuda:13.2.1-runtime-ubuntu24.04@sha256:285c50be684df76df5cd0e3162687e74b7b67add47134ff55075e3a9cfa94044`.
The lock includes primary OCI descriptors, exact compressed artifact bytes
**1,480,435,595**, and a separate conservative **8 GiB** capacity reserve for
unpacking/engine overhead. Descriptor bytes are not a measured installed size.

Before reuse, inspect must match linux/amd64, exact RepoDigest, and one of the
known immutable registry config/platform/index identities. The command is an
isolated `docker run --rm --pull never --network none --read-only --gpus all` using
that digest and querying GPU driver/PCI identities. Host and container GPU sets
must match exactly and remain unchanged across execution. No model starts.
The protected proof is tied to current boot, image, lock, config, and GPU facts.
Read-only verification requires those current facts as well as the proof.

Injected fixture Runners produce `SYNTHETIC_FIXTURE`; production core.Runner
produces `ACTUAL_GPU_COMMAND` only after executing the command. Production checks
reject synthetic proof. The source gate follows NVIDIA's documented GPU workload
interface; this is not an actual GPU execution result.
([NVIDIA GPU container configuration](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/docker-specialized.html))

## Validation and remaining integration

Command:

```sh
python3 -m unittest discover -s tests/install -p test_container.py -v
```

**23 synthetic tests passed on macOS.** They exercise real stage methods, package
command ordering and masks, original policy/config preservation, interrupted
resume, root and service-flag mismatch rejection, existing root payload, exact
package/key pins and metadata drift, failed postconditions, mount-loss recovery,
GPU/image/boot identity drift, both config-ID/manifest-ID image stores, explicit
fixture evidence labeling, effective namespace drift, unsafe logging/listeners,
and I1R admission refusal before configuration or package mutation.

I1R is an explicit source integration dependency: when Runner lacks
`package_identity`, `prepare_package`, `hold_package_lease`, `run_package`, or
`inspect_package`, package work raises
`Pending('i1r_package_lease_integration_required')`. No raw lease-FD bypass is used.
The inherited reviewed prerequisite transaction must establish package cgroup
quiescence before masks are restored. Unknown ownership or mount loss leaves the
protective masks/checkpoint intact. Integrate the reviewed I1R implementation and
canonical lease admission before any real installation.

Next: merge I1R/L1 through the coordinator, run actual snapshot resolution/package
installation and systemd namespace checks in disposable Ubuntu 24.04 amd64, then
run a real GPU gate on separately authorized disposable hardware. Final boot,
lifecycle/U1/client/service acceptance remains owned by I1c; blank-disk completion
is separately handed to I1S. No fresh-install or full READY claim is made here.
