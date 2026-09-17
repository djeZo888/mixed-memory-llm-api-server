# FINALOPS reboot and exact cleanup — complete

One normal reboot and the root-approved C1 cleanup completed on 2026-09-17. All four exact obsolete trees are absent, all three approved stopped containers were retired, and the four approved operational metadata files were privately backed up and retired. No targets remain. Selected Qwen remains ready at PID **11259**, generation **6**, with its original container, image and resume intent. Canonical lifecycle lease and local request ownership were released at completion; no Worker1 VM command remains active.

Worker: Mac-Worker1. Session: `01a0ae41-156a-7ee0-8b4e-b2b6a1dd77ad`. Runtime source: `ab6daa475cc2f1c04956d862f460f9f01c4ee952`. This report/evidence commit does not change deployed source.

| Reboot observation (UTC) | Time |
| --- | --- |
| Normal reboot dispatch, after lease release | 07:57:22.475249 |
| First observed SSH return, new boot ID and guards | 08:02:03.693464 |
| Authenticated native/control readiness; ownership released to Worker2 | 08:02:23.580691 |
| Worker2 independent LAN acceptance and release | 08:06:22.492747 |

Boot changed from `f059feb9-8fc1-41f2-a64d-38cc3516ed44` to `a32f0280-3165-4b92-ac9c-776021439463`. Reconnect temporarily returned timeout / `No route to host`; the cause was not established. First observed SSH return was 281.218215 seconds after dispatch; ready was observed 301.105442 seconds after dispatch. No second reboot occurred. Worker2 reported authenticated Qwen READY, missing-key 401, correct alias and a short streamed completion. Root later reported the successful user demo and reopened idle maintenance. No cleanup inference, benchmark or model switch was performed.

Both registered ext4 mounts passed exact UUID checks: `/data` = `8daf56f1-5649-4163-9d87-919c2d271875`; `/data/models-large` = `a6d4ab58-84e1-4e48-9a67-13ad1c6f6e0a`. Kernel `6.8.0-139-generic`, loaded/module/userspace NVIDIA `595.84`, and both GPUs passed. Installed guard/dependency modes remained 0755/0644, registry 0600; the 4 GiB root floor passed throughout guarded phases.

Root reviewed the corrected 08:25:23 dry-run before apply. It matched complete tree metadata/digests, UUID/mount/ancestry, pinned acquisition manifests, file/link/entry counts, no nested mounts, process FD/cwd/root/mmap/lock visibility, target-specific acquisition ownership, container contracts and operational references. Ten historical files were read through checked FDs as untrusted provenance. Ubuntu notifier was untouched. Full reviewed identities are in [corrected-dry-run.json](finalops-evidence/corrected-dry-run.json).

| Deleted literal tree | Measured allocation removed (bytes) | Absence verified UTC | Post-check |
| --- | ---: | --- | --- |
| `/data/models/minimax-m3-mxfp8` | 443,776,548,864 | 08:34:36.955242 | PASS |
| `/data/models/qwen3-30b-a3b-instruct-2507` | 61,084,520,448 | 08:35:00.496550 | PASS |
| `/data/models/qwen3-0.6b-smoke` | 1,519,300,608 | 08:35:23.807834 | PASS |
| `/data/models-large/qwen3-coder-next-fp8` | 80,408,006,656 | 08:35:47.355089 | PASS |

Total measured tree allocation removed: **586,788,376,576 bytes**. Immediately before each tree, the unchanged reviewed FD helper `c0270cda…` repeated the complete snapshot and live ownership/storage/non-use checks; deletion used symlink-resistant directory-FD traversal. Each target then passed exact absence, retired-container absence, retained metadata, source/proof/key/receipt/weight/image preservation, mount/guard and authenticated catalog/native-readiness checks. Catalog has exactly the two retained entries; Qwen alone is running/ready. This does not claim simultaneous GLM readiness or new context acceptance.

Three full stopped-container IDs were reinspected for expected image, Compose identity, exact broad mounts, exited/PID0/restart=no, then removed with `docker rm FULL_ID` and no force or volume flags:

- `634daeb70a3ae9aa7403ec8d2256984de9cfe8b5521b839de16a1707164f7522`
- `321ee2110e2e0130739ca51fe192b23d746ecefca76e746c9e2df3fd8a799153`
- `6cfa91273417ad7f5ae23a471aaf7b2f5be47bfab74550df93b71587fb3fb71f`

The only operational files retired after exact identity/hash rechecks and protected small backups were:

- `/data/services/llm-manager/acquisition/qwen3-coder-next-fp8.complete.json`
- `/data/services/llm-manager/compose/minimax-m3-poc.compose.yml`
- `/data/services/llm-manager/compose/sglang-smoke.compose.yml`
- `/data/services/llm-manager/compose/sglang-qwen3-30b.compose.yml`

F1A/F1D provenance, current selection/recovery/configuration, accepted GLM/Qwen weights and receipts, all runtime/Docker images including D1, keys, source/proofs, NETPATCH, shared caches and other model entries remain outside deletion scope. Backups contain metadata only and cannot restore deleted weights. Backup files allocated **28,672 bytes**; retired metadata had allocated **24,576 bytes**. Raw backup contents remain private.

`/data/models` alone was temporarily changed from uid1000/gid1001/02775 to uid0/gid1001/02755 under the approved exact dev2065/inode12320769 check. It was restored on the same inode after the earlier refusal and after successful apply (08:35:59.183369 UTC), with xattrs verified. No recursion or target chmod occurred.

| Filesystem | Available before (bytes) | Available after (bytes) | Measured delta (bytes) |
| --- | ---: | ---: | ---: |
| `/` | 5,546,250,240 | 5,545,844,736 | -405,504 |
| `/data` | 1,337,402,023,936 | 1,844,134,727,680 | +506,732,703,744 |
| `/data/models-large` | 2,590,859,284,480 | 2,671,267,291,136 | +80,408,006,656 |

These are endpoint availability observations during apply, not an attribution of every freed block. Concurrent service/log writes, stopped-container metadata retirement and filesystem accounting can affect the delta. Root-space reduction was 405,504 bytes and remained above the floor. Weight allocation removed is reported separately; no root-space recovery is claimed.

The first preapply attempt refused before any retirement because Docker returned Mounts in a different order. Read-only diagnosis found 18 positional mount-field differences. The next guarded attempt compared the full accepted running state after sorting complete mount records, retaining every field and duplicate multiplicity; exact equality passed at 08:34:19.302776 UTC. No other state difference was accepted. The complete live equality operands stayed in memory; the retained evidence is the exact comparator source, successful execution milestone and original diagnostic field paths. Original refusal/provenance and executable predicate evidence remain in [normalization.json](finalops-evidence/normalization.json). Earlier report-parent mode, empty systemd-job parser, unsafe parent and historical-reference/unit classification refusals are historical; none stopped the healthy backend. Sanitized wrapper refusal events are retained in [historical-refusals.json](finalops-evidence/historical-refusals.json); private diagnostic captures remain outside the repository.

Final authenticated readiness, preservation, guards and aligned GPU checks passed; canonical lease release and result were emitted at **08:36:18.365933 UTC**, then the dispatcher exited 0. The original 11 meaningful local helper cases were retained; no unrelated tests or additional matrix ran. Task-local apply glue received syntax verification and live guarded verification. Sanitized summary, per-target events and reproduction sources are under [finalops-evidence](finalops-evidence/summary.json). Private diagnostics and complete protected reports remain outside the repository.
