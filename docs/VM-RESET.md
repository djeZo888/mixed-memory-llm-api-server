# VM retirement and V2 reset plan

**Status on 2 October 2026: read-only inventory completed; reset not performed.** No application was stopped, account created, package removed, credential changed or model file deleted by this closeout inventory. This is a preservation and retirement plan, not a claim that the machines are already clean.

## Retain the OS and isolate the new application

Both `ai-vm` and `ai-harness` were observed running Ubuntu 24.04.4, x86-64, kernel 6.8.0-142. Retaining the OS, GPU stack and model volume avoids reinstalling or downloading weights again. A fresh unprivileged `sovav2` service account and fresh application directories are the recommended reset boundary. Keep the existing operator account and verified SSH access until migration and recovery are checked.

That produces a clean **application environment**, not a byte-for-byte fresh OS. Existing OS package upgrades, logs and machine configuration remain. Some machine-wide V1 settings and root-owned services require explicit retirement; creating a user alone does not neutralize them.

## Preserve before retiring anything

| Preserve | Reason |
| --- | --- |
| Dedicated model volume and all weight/cache/download directories | Actual weights are on the separate `/data/models-large` volume, with approximately 1.46 TB used. `/data/models` was empty. Preserve completed assets, partial downloads, repository snapshots, revisions, tokenizer/config files and existing manifests. |
| Original conversations, database and accompanying journal files, uploads and generated artifacts | Git history preserves code, not user data. Obtain an application-consistent backup and verify a restore before deleting the old application state. |
| Protected credentials and authentication state | Keep outside Git in a private retirement archive; record paths and permissions without copying secret values into reports. Do not silently rotate or discard credentials. Grant V2 only its intended access. |
| Application releases, runtime environments, container metadata/images and service definitions | Retain enough to inspect or reproduce V1 and extract selected reusable components. Archive does not authorize restarting an old service. |
| Current package inventory, APT history and installer evidence | These establish the observed installation and support reconstruction of a smaller installer dependency set. |
| Base networking, trusted SSH access, guest tooling, storage mounts and GPU drivers | Preserve access and platform operation. Review huge-page, cgroup, firewall, routing and boot changes separately before resetting them. |

Do not recursively change ownership or permissions on the model store. Inventory found 75 root-only weight files; a fresh non-root account cannot read all retained models without targeted permission provisioning. Give the new account narrowly scoped access and a separate writable cache when the V2 runtime is selected. Weight files were not exhaustively rehashed during inventory; retained manifests and revision metadata are references, not newly verified full-volume integrity.

## Reconstruct the installer dependencies

The private closeout inventory contains installed package names, architectures and versions, manual/automatic package marks, holds, available APT histories and installer logs. `ai-vm` has 878 installed packages (884 total dpkg records), with 46 manual and 832 automatic marks. `ai-harness` has 794 installed packages, with 51 manual and 743 automatic marks. Neither host reported held packages. Available APT history comprises three files on `ai-vm` and two on `ai-harness`.

No exact initial dpkg baseline was found. Surviving APT installation events identify 291 distinct names on `ai-vm` and 192 on `ai-harness`; they do not establish an exact fresh-OS difference. The logs can identify useful candidates, but not prove a complete minimal dependency list.

| Observed package | Host | Recorded version | Candidate role |
| --- | --- | --- | --- |
| `openssh-server` | Both | `1:9.6p1-3ubuntu13.19` | Operator access; preserve. |
| `python3` | Both | `3.12.3-0ubuntu2.1` | Base/runtime tooling; evaluate component needs. |
| `build-essential` | Both | `12.10ubuntu1` | Build dependency; need not be in every production component. |
| `nvidia-driver-595-open` | ai-vm | `595.84-0ubuntu0.24.04.1` | GPU platform; preserve during retirement. |
| `nvidia-container-toolkit` | ai-vm | `1.19.1-1` | GPU container support; qualify with the chosen V2 runtime. |
| `docker-ce` / `containerd.io` | ai-vm | `5:29.6.1-1~ubuntu.24.04~noble` / `2.2.5-1~ubuntu.24.04~noble` | Existing inference container platform. |
| `podman` / `uidmap` / `fuse-overlayfs` | ai-harness | `4.9.3+ds1-1ubuntu0.2` / `1:4.13+dfsg1-4ubuntu3.2` / `1.13-1` | Existing rootless application isolation. |

These are observed examples, not a V2 install command or final runtime/version choice. Full exact package exports and categorized candidates are retained privately.

Keep three lists distinct:

1. **Observed installed inventory:** the exact current packages and versions, including ordinary OS packages. This is reproducible inventory, not a minimal installer specification.
2. **Post-install additions and changes:** reconstruct from installer baseline and surviving APT logs. Record missing or rotated evidence and upgrades separately from added dependencies.
3. **V2 installer prerequisites:** select only packages needed by the reviewed V2 components, then prove them on a clean application environment. Manually installed does not mean required by Sova; some runtime dependencies are Python, Node, containers or downloaded binaries rather than APT packages.

Classify candidates into base/access/storage/guest packages, GPU drivers/toolkit/container support, application runtime dependencies, development/debug tools, and V1-specific leftovers. Preserve the first two categories during retirement. Archive isolated V1 application environments rather than purging system packages by guesswork. The V2 dependency list remains provisional until its runtime choices and direct component tests are complete.

## Concrete reset sequence

The private manifest enumerates host-specific paths, service states, process identities and archive candidates. Execute that reviewed manifest under a new retirement scope; old V1 operational approvals are expired.

1. Verify current owners, running jobs and storage again. Save the service/package/placement inventory and obtain verified application-consistent data backups.
2. Stop only identified V1 application and inference owners, with their supported lifecycle procedure. Confirm the actual processes, containers and owned resources have settled before reassigning them. Do not use a broad process-name kill.
3. Disable identified V1 autostarts, user services, timers, socket activation and container restart policies. Archive their definitions and the existing releases, configuration and isolated environments before removing active application paths.
4. Create the fresh service account and empty V2 application directories. Keep operator SSH and the retained model store; do not transfer old owner records, boot IDs, qualifications or approvals into V2.
5. Review V1 machine-wide network/cgroup/huge-page settings individually. Preserve essential networking, GPU/guest services and mounts. Leave package removal until the V2 prerequisites are established.
6. Check reconnect/login, mounts, driver visibility, retained model metadata and restored data. Verify V1 services cannot restart automatically and no retired process still owns a required resource. Record the actual outcome and remaining exceptions.

CHA_FAN3 remains deferred under the user's direction: BMC configuration is to stay at 100%. Retirement must not re-enable its old temperature controller or change BMC policy. The external Ada's idle visibility is not a sustained-load/link qualification; that remains a V2 hardware test.

The final reset record must say what was archived, disabled, removed and preserved, which account was created, which checks actually passed, and what remains. Until execution is recorded, this document stays a plan.
