# I1 prerequisite package lock and source evidence

Status: **PASS — source implementation and synthetic prerequisite checks.**
Fresh Ubuntu package execution, physical GPU driver installation, firmware interaction,
actual reboot/resume and GPU-container acceptance: **NOT_TESTED by I1**.

## Implemented boundary

`scripts/install/prerequisites.py` implements base dependencies and a driver/reboot
checkpoint. `scripts/install/versions.lock.json` contains schema-versioned exact
package versions, archive filenames, SHA256, archive bytes and installed bytes for
164 unique packages. Docker/containerd/toolkit groups are locked inputs for the
next container-runtime stage; this module does not install or start those services.

The public Python interface is `Prerequisites(config, runner, storage_guard)` with
`check_base()`, `apply_base()`, `check_driver()` and `apply_driver()`. The caller
holds the exclusive installer/lifecycle lock and supplies a verified-storage guard.
Command execution uses `runner.run(argv, timeout=..., env=...)`. Checks return a
boolean; mutation methods return evidence or a sanitized `PrerequisiteError`.
`RebootRequired` has `exit_code=75` and a `checkpoint` dictionary. It does not reboot.
`recover_policy()` is called under the caller's writable lock before completed-stage
checks during apply/resume. A pending policy marker makes read-only verification
fail even when package versions and the loaded driver already match. Sanitized
machine error codes and package/version/target-kernel details are exposed separately
from raw command output.

## Exact source facts obtained

On 2026-09-14 UTC / 2026-09-15 local time, read-only SSH inspection found Ubuntu
24.04.4 amd64, kernel `6.8.0-134-generic`, matching loaded module/NVML driver
`595.71.05` and two NVIDIA RTX PRO 6000 Blackwell Workstation Edition GPUs. No
installation, service change, disk change or acquisition-job change was performed.

Read-only `apt-cache policy`/`apt-cache show` provided package versions and signed
archive metadata from the VM's existing indexes. Their newest package-index mtime
was **2026-07-07T13:12:08Z**; this was explicitly treated as cached evidence.
`apt-get -s -o Dir::State::status=/dev/null --no-install-recommends install ...`
resolved a complete dependency allowlist without changing the VM.

Current HTTPS HEAD checks then verified **all 164 locked archive URLs returned
HTTP 200 and Content-Length equal to the metadata size**. This is availability
evidence, not package-byte hash verification or installation evidence. Apt verifies
archive hashes against authenticated metadata during actual installation. The
installer first verifies the selected metadata SHA256/size against the committed
lock, so a changed or missing lock fails rather than selecting a newer package.

Several moving Ubuntu archive URLs, including the locked curl and driver userspace
package, returned 404. Their exact artifacts returned 200 from the official Ubuntu
snapshot `20260707T140000Z`. The implementation therefore creates private,
signature-checked installer sources for that snapshot under the data filesystem.
The host's normal apt sources and unattended-update configuration are preserved.
Ubuntu documents timestamped snapshots for reproducible package installations.
([Ubuntu Snapshot Service](https://snapshot.ubuntu.com/))

| Group | Requested versions | Dependency closure | Archive bytes | Installed package bytes |
| --- | --- | ---: | ---: | ---: |
| Base | Full list below | 127 | 48,992,374 | 190,710,784 |
| Driver | `595.71.05-0ubuntu0.24.04.1`; kernel/module packages `6.8.0-134.134` | 45 | 243,271,460 | 680,865,792 |
| Docker | engine/CLI `5:29.6.1-1~ubuntu.24.04~noble`; containerd `2.2.5-1~ubuntu.24.04~noble`; buildx `0.35.0-1~ubuntu.24.04~noble` | 33 | 87,644,918 | 345,444,352 |
| NVIDIA toolkit | All four packages `1.19.1-1` | 9 | 11,627,870 | 49,573,888 |

Closures overlap; totals must not be summed as independent disk requirements.
Actual pending package changes, archive bytes and root reservation are calculated
from the host-specific apt simulation before package mutation.

Base requested pins:

```text
ca-certificates=20260601~24.04.1
curl=8.5.0-2ubuntu10.10
e2fsprogs=1.47.0-2.4~exp1ubuntu4.1
git=1:2.43.0-1ubuntu7.3
gnupg=2.4.4-2ubuntu17.4
jq=1.7.1-3ubuntu0.24.04.2
mokutil=0.6.0-2build3
parted=3.6-4build1
pciutils=1:3.10.0-2build1
python3=3.12.3-0ubuntu2.1
python3-venv=3.12.3-0ubuntu2.1
util-linux=2.39.3-9ubuntu6.5
```

## Driver policy and checkpoint

An already working driver at least `595.71.05` is preserved when NVML identifies
the expected distinct PCI GPUs and every reported driver version agrees with the
loaded kernel module and `modinfo`. This is a prerequisite capability check;
runtime GPU-container and actual model acceptance remain required later. It does
not claim every later driver/runtime combination is empirically validated.

When installation is needed, the package set is the minimal headless userspace
(`nvidia-headless-no-dkms-595-open`, `nvidia-utils-595`) plus the pinned Ubuntu
precompiled open kernel modules and matching kernel image. It avoids host CUDA
Toolkit and DKMS builds. Ubuntu documents precompiled kernel-module and userspace
installation as an available driver path; Secure Boot requires signed modules.
([Ubuntu NVIDIA driver installation](https://documentation.ubuntu.com/server/how-to/graphics/install-nvidia-drivers/),
[Ubuntu Secure Boot](https://documentation.ubuntu.com/security/security-features/platform-protections/secure-boot/))

The installer detects Secure Boot, saves the prior driver/kernel package inventory,
preserves prior kernels and package configurations, and records a private driver
checkpoint on data storage. No purge, autoremove, forced module unload or automatic
reboot occurs. After reboot, the boot ID must differ and the driver/GPU checks must
pass. Same-boot resume remains exit 75 even if synthetic commands report a matching
driver. A failed post-reboot module/userspace/GPU check is a failure, with firmware,
module signing and kernel selection named as diagnostic targets. On systems whose
bootloader selects another kernel, select the checkpoint's target kernel before
resuming; Secure Boot firmware/key enrollment remains an explicit external step.

The checkpoint prints `./install.sh resume --through driver --yes` for this bounded
I1 prerequisite delivery. Full deployment remains pending until the later stages
and lifecycle portability interface are integrated.

## Storage, package and service boundaries

- Guarded private apt lists, archives, sources, temporary files and logs reside on
  the registered data filesystem. The installer does not use root storage as a
  payload fallback after observed mount loss. Directory-FD anchoring across a
  detach race remains I1b work; repeated path checks do not close that race. Existing path ancestors must be owned by the executing root
  user, non-symlink directories and not writable by group/others.
- Root must retain at least 4 GiB plus pending installed bytes and a generated-file
  allowance (256 MiB base, 1 GiB driver). The default per-stage package reservation
  limit is 2 GiB. Generated initramfs and maintainer-script output are included in
  this reservation; it is a conservative admission allowance, not a filesystem
  quota. Post-command root/storage guards still run.
- Only changed dependencies from apt's simulation are installed, all with exact
  locked versions. Existing compatible OS dependencies are preserved. Any removal,
  downgrade, changed unlocked dependency, missing pin or changed metadata fails.
  The entire closure is never blindly reinstalled or downgraded. Requested base
  package version drift needs a reviewed lock update rather than a forced downgrade.
- Downloads finish before dpkg runs. Both sides of each apt command recheck
  storage. Existing `policy-rc.d` is protected, retained byte-for-byte, temporarily
  replaced by an exit-101 inhibitor, and restored, including interrupted-run
  recovery. No unrelated running service is intentionally restarted.
- JSON records use mode 0600, random exclusive temporary files, fsync and atomic
  replacement. Existing symlinks/hardlinks/unsafe ownership are rejected. A tiny
  root service-policy restoration still occurs after mount loss; its data marker
  is touched only once storage identity passes again.

Docker installation from exact apt versions and NVIDIA's four-package version
selection are documented by their upstreams. Their service/data-root deployment is
outside this module's implemented boundary.
([Docker Ubuntu installation](https://docs.docker.com/engine/install/ubuntu/),
[NVIDIA Container Toolkit installation](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html))

## Checks and next action

Command: `python3 -m unittest discover -s tests/install -p test_prerequisites.py -v`

**24 synthetic tests passed** on the Mac worker. Cases cover exact dependency
selection; verified second-run no-op; absent pins and sanitized errors; dependency
drift/removal/downgrade rejection; root versus data capacity; mount loss before
dpkg; ordinary-user mutation rejection; service-policy preservation and interrupted
recovery; failed dpkg postconditions; compatible-driver preservation; module
mismatch/GPU count; driver reboot and same-boot rejection; failed post-reboot driver;
unknown Secure Boot; symlink-before-payload rejection; untrusted additional sources;
writable parent directories; hardlinks/fixed temporary path protection; mount loss
with an otherwise working driver; completed-package recovery of a policy left by
an interrupted install without reinstalling packages; and required lock metadata.

The observed driver major in the lock is descriptive. Compatible-driver adoption
uses the minimum version and module/NVML/GPU consistency checks; the later actual
GPU-container gate is mandatory for runtime compatibility. Anchored directory-file
descriptor operations that close the remaining mount-loss/write race are recorded
as an I1b hardening requirement; current guards and path validation are not a claim
that this race is completely eliminated.

Next: I2 should run actual private-snapshot package resolution/install in a disposable
Ubuntu 24.04 environment, validate service inhibition/initramfs root overhead, and
exercise the driver/boot path on a disposable GPU host if one becomes available.
The later installer continuation must add the Docker/containerd/toolkit storage
configuration and actual GPU container gate before runtime/model activation.
