# Q38DEV — bounded device metadata observation

**OBSERVED.** `/dev/nvidia-modeset` was a character device, major/minor **195:254**, and was the only observed name rejected by the unchanged `check_device_names` predicate. This is a separate observation; Q38VR3 did not record its triggering name, so that historical name remains unknown.

## Device facts

| Path | Type | Character major:minor |
|---|---|---|
| `/dev/nvidia-modeset` | char | 195:254 |
| `/dev/nvidia-uvm` | char | 511:0 |
| `/dev/nvidia-uvm-tools` | char | 511:1 |
| `/dev/nvidiactl` | char | 195:255 |

`/dev/nvidia-caps`, `/dev/dri`, `/dev/kfd`, and `/dev/dxg` were absent. No other allowed entries, directories, or symlinks were observed. The inventory had no errors or truncation: four entries, 829 output bytes, exit 0.

- Start/attach UTC: **2026-09-15T04:25:06.838309+00:00**.
- End/attach UTC: **2026-09-15T04:25:07.177105+00:00**.
- Inner inventory UTC: **2026-09-15T04:25:07.139106121Z–2026-09-15T04:25:07.139166211Z**.
- Cleanup and final guards completed: **2026-09-15T04:25:07.491195+00:00**.

These timestamps support Root's comparison with D3N32's native requests. D3N32's operations were not queried; actual overlap is not determined here. Requested task-parent `device-facts.json` and `phase-result.md` were published immediately on observation, acknowledged before cleanup, and updated with final cleanup/guard facts before this report.

## Scope and runtime

Executed from mac-worker1 through SSH `ai-vm`, using exact reviewed source base `3acd2741635a05e42474f1b19664e477b510cf78`. One create and one start; no second container, retry, native fixture, model/API request, device-node open/read/write, native-library call, allocation, inference, download, build, key access, registry/service modification, or source-policy correction. Installer remains **STOPPED**. This diagnostic cannot produce **PASS_NATIVE**, an auth receipt, or proof of usable GPU access.

Reused Q38ENV's corrected narrow Docker inspection and owned disposable lifetime. The unchanged `qwen38_oci` relationship accepted exact image `lmsysorg/sglang@sha256:37bbbd3444732a464bbc68dee4fb0164e0ce9e18e2f027f3fc967f1152d3c262` in its reviewed `oci_platform_manifest` Docker-ID domain. No refetch, model rehash, or unrelated artifact inventory occurred.

Host policy was inspected before start: NVIDIA runtime; literal `NVIDIA_VISIBLE_DEVICES=none`, `NVIDIA_DRIVER_CAPABILITIES=compute,utility`, empty `CUDA_VISIBLE_DEVICES`; no DeviceRequests, host devices, device cgroup rules, published ports, or bind mounts; network none; read-only root; all capabilities dropped; no-new-privileges; private IPC; no logs or restart. The known image's static ExposedPorts metadata does not publish a port.

Documented diagnostic differences: fixed stdlib `python3 -B -c` metadata inventory replaces the fixture command; no fixture/source mount or cache/source/model/key inputs. It uses Q38ENV's small private `/cache` and `/tmp` tmpfs (8 MiB each), plus reviewed empty `/models` (8 MiB) and `/run/secrets` (1 MiB) tmpfs. All four are nodev/noexec/nosuid; the three named private data paths are mode 0700. Q38ENV CPU limit 1 is retained; memory 8 GiB, pids 128, shm 64 MiB. Native policy and latest inner `none`/`void` acceptance remain unchanged.

The command filters `/dev` names for `nvidia*`, uses `lstat` for path type and character major/minor, and traverses only real directories under `/dev/nvidia-caps` or `/dev/dri`. Symlinks are not followed; targets would be disclosed only within the allowed paths and bound. No device node is opened. All attempted paths count toward the 128-record cap; output is capped at 32 KiB, paths/targets at 512 bytes, recursion at 16; in-process alarm 5 seconds and attached-process timeout 15 seconds. Full exact command is retained in evidence.

## Verification and warnings

| Check | Result |
|---|---|
| Local exact base and clean feature branch before work | PASS |
| Controller/inventory/publication Python AST and Docker-template JSON structure | PASS; no local inventory execution |
| Fixed installed registered guard/dependency hashes and protected paths, before/after | PASS |
| Registered mount and root guards; exact data/model UUIDs, before/after | PASS |
| Installed image identity and created-container host policy | PASS |
| One bounded inventory, no truncation/errors | OBSERVED; diagnostic only |
| Owned identity, exited/pid0 state, immutable-ID removal without force | QUIESCENT_REMOVAL_VERIFIED |
| Separate successful empty exact-ID Docker listing | ABSENCE_VERIFIED |
| Final VM evidence directory/files | root:root 0700 / root-owned 0600 |
| Local exact copies of immediate facts and phase result | PASS |

Guard source: `/usr/local/lib/llm-server/control-api/scripts/common/registered-storage.py`, SHA256 `21cf082a841aeab9470bd6704b77104961b9d4afcaec696d90aa22b65f5b6f3d`; dependency `scripts/install/storage.py`, SHA256 `4f834e92d149ea1955e79d34c53c18bf8c5846a4121d779e135a50d31a615505`. Used isolated Python under `sudo -n`, including `--root-guard --json`. No legacy fallback or environment identity override. UUIDs: data `8daf56f1-5649-4163-9d87-919c2d271875`; models `a6d4ab58-84e1-4e48-9a67-13ad1c6f6e0a`.

Root free space after: **5,208,424,448 bytes**, above 4 GiB STOP and below 6 GiB warning. This existing capacity warning remains. No new test suite or fixture/native acceptance was run. Image/create preparation returned 0 with empty stderr; bounded CLI evidence is retained. Expected failed inspect after removal was independently resolved by successful empty exact-ID listing, with its bounded Docker stderr retained on the VM.

Owned ID: `a52cec602c81be1b3c62fed6ddd8854dc0fc396dfc02d2f42204a94c08fd69f3`. VM originals are only under `/data/logs/q38dev-20260915`; no VM staging was needed. The ten copied evidence files total 23,959 bytes.

Evidence: [facts](q38dev-evidence/device-facts.json), [phase](q38dev-evidence/phase-result.md), [exact command](q38dev-evidence/diagnostic-command.json), [pre-start policy](q38dev-evidence/container-before-start.json), [final guards](q38dev-evidence/guards-after.json), [independent absence](q38dev-evidence/final-owned-id-absence.json).

Next action: Root reviews the measured `nvidia-modeset` fact and separately owns any source-policy decision. Stop here; per-GPU exclusion remains unchanged. No push requested.
