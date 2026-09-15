# ROOTSPACE recovery — exact crash archives preserved; root guards PASS

**Root available 5,208,223,744 bytes (4.851 GiB), both full canonical guards PASS.** Recovery released exactly **1,578,762,240 bytes**. GLM is unchanged and quiescent at the final observation. ROOTSPACE VM ownership was released **2026-09-15T05:00:12.981933+00:00**; `../recovery-ready.md` was published immediately before report packaging. Parent owns the approved D3CAP2 next action; no request or model transition was performed here.

## Authorization and scope

The continuation and `../coordination-input.md` explicitly authorized archiving exactly the two identified Apport files, superseding the initial no-large-archive/evidence-retention constraint for these originals. The initial diagnosis commit **39189271c76338ac4573d1f6e5fc14618ad6fef8** and all nine report/evidence files remain unchanged. This is a separate recovery record.

The exact plan and preflight were saved on the worker before VM mutation. Root capacity initially failed; the installed verifier's identity-only checks independently confirmed the authoritative registry, dedicated mounts, protected roots and source identities. This specific recovery used the explicit authorization while the capacity guard failed. It did not waive the guard for ordinary model/fixture work.

## Preserved raw artifacts

Archive parent: **`/data/logs/rootspace-recovery-20260915-archive`**, newly created root:root **0700**, device 2065 / 8:17, inode 47972640. Files are root:root **0400**, link count 1, with original atime/mtime preserved. Raw content stayed on ai-vm and never entered stdout, worker files or Git.

| Original | Archive basename | Original inode | Archive inode | Bytes |
| --- | --- | ---: | ---: | ---: |
| `/var/lib/apport/coredump/core._usr_bin_python3_12.0.9423b346-6186-4855-b1cf-f1725a853fe9.265467.2515351` | `core._usr_bin_python3_12.0.9423b346-6186-4855-b1cf-f1725a853fe9.265467.2515351` | 266791 | 47972641 | 970,436,608 |
| `/var/crash/_usr_bin_python3.12.0.crash` | `_usr_bin_python3.12.0.crash` | 266790 | 47972642 | 608,314,664 |

SHA256 values, identical for the copy stream, full source reread and independent archive reread:

- Standalone core: **`36dd457ac3e3589945da2aa2e5f67c0827d4f8d0399848112cfb7ee85d34b3a5`**.
- Crash report: **`08b8ac574c1e92f59a221e9c435a4bf2e13403003514dcb8691d7be0a3e0e5a9`**.

Copying used anchored directory FDs, `O_NOFOLLOW`, exclusive destination creation and `O_NOATIME` source reads. Both copies were fsynced and independently rehashed before either original was unlinked. Source device/inode/owner/group/mode/link count/size/allocated bytes/mtime/ctime/atime were identical before and after copying and immediately before each exact unlink. Source ancestry was root-owned and nonsymlink; `/var/crash` retains its existing sticky 1777 mode. Destination ancestry remained protected and bound to the registered data mount. Mounted identities were revalidated after copying and after removal.

A fresh all-process FD-reference scan preceded each unlink; only this recovery process's exact read descriptors were present. The original core was removed at **05:00:12.586Z** and crash report at **05:00:12.676Z**. Their source FDs were immediately closed, source directories fsynced, and both originals verified absent. Final scan of 1,108 processes found no original/archive FD references, no crash-handler process and no errors. No deleted-open delay remains for these artifacts. No other file was deleted or process terminated.

## Final canonical guard, identity and quiescence evidence

Final observation completed **2026-09-15T05:00:12.981924+00:00**:

| Measure | Before | After |
| --- | ---: | ---: |
| Root available bytes | 3,629,461,504 | 5,208,223,744 |
| Root free including unavailable reserve | 4,423,233,536 | 6,001,995,776 |
| Full registered guard | capacity STOP | PASS |
| Full registered `--root-guard` | capacity STOP | PASS; 4,273 files inspected |

Root is now **913,256,448 bytes above 4 GiB** and **1,234,227,200 bytes below 6 GiB**. Both guards truthfully retain the <6 GiB warning. No further useful-size exact permissible task artifact was established, so no scope expansion was used to reach 6 GiB.

The exact root-protected installed guard remained mode 0755/SHA256 `21cf082a841aeab9470bd6704b77104961b9d4afcaec696d90aa22b65f5b6f3d`; adjacent storage dependency remained mode 0644/SHA256 `4f834e92d149ea1955e79d34c53c18bf8c5846a4121d779e135a50d31a615505`. Registry `/etc/local-ai-server/storage.json` and protected ancestry verified. The full invocations used isolated `sudo -n /usr/bin/python3 -I -B` with the canonical installed path, no override, fallback or installer workflow.

Unchanged ext4 identities: root **bc752bce-bb3f-4802-8adf-69c45a88689d**, 252:0; `/data` **8daf56f1-5649-4163-9d87-919c2d271875**, 8:17; `/data/models-large` **a6d4ab58-84e1-4e48-9a67-13ad1c6f6e0a**, 8:33.

GLM container **7cde6a376f58a1dee7ad425fbd104bbd7337effa6d6943a5bfc0dbeed4bbee78**, image **sha256:86feba4c82a8ec083d8da31fb8d1648f7b221b724a48eca571f5dd277a0caab9**, PID **243279**, start ticks **2367582**, running state, start **04:09:20.746242473Z** and restart count **0** match before/after. At **05:00:12.921Z**, read-only `ss` inspection found zero established connections involving API port 30002; the latest native slot lifecycle event was stopped processing at **04:32:15.806020433Z**. Only event type/time were emitted from the bounded log inspection. No inference/control/tokenization request was sent. These point-in-time observations establish recovery handoff quiescence; they do not certify subsequent independent work.

## Native crash evidence and handoff

Minimal useful metadata is already preserved in the original diagnosis: Qwen fixture `cache_probe.py`, signal 11, PID 265467 / NSpid 43 / PPid 265408, UID 0, filename start token 2515351, report date 04:34:05Z and artifact times 04:34:26–29Z. Native crashing function and exact Docker cgroup binding remain unknown. Both complete raw artifacts now remain protected on registered data for a separately scoped diagnosis; no environment/command/core contents were dumped, and no host crash-reporting setting was changed.

`../recovery-ready.md`, `../root-space-facts.json` and `../phase-result.md` carry the current recovery result. Full metadata, exact plan, emitted operator code and guard output are in `reports/rootspace-recovery-evidence/`. No new Codex session, production source change, model/service/network change, installer work, request or automatic D3CAP/Q38FIX resumption occurred. Recovery holds no lifecycle/request lease or archive FD and schedules no further VM call. Only local packaging followed the ownership release.

Validation: successful actual SSH recovery (exit 0, empty stderr), three matching hashes for each file, unchanged source identity proofs, fsync/absence/FD checks, full guard PASS, unchanged GLM and current quiescence PASS. Report JSON/hash-manifest, quiet secret scan, whitespace, exact author/committer and clean-tree/bundle checks accompany publication. No source/installer test suite was needed or run.
