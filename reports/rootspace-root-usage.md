# ROOTSPACE — root usage diagnosed; native crash evidence retained

**Root available 3,629,518,848 bytes (3.380 GiB); registered storage and registered root guards remain FAIL. No cleanup or VM workflow was performed.** The protected source hashes/modes and registry/mount identities match. The N76/32K GLM backend is unchanged.

## Cause and evidence boundary

The full root-filesystem metadata walk found two new Apport artifacts totaling **1,578,762,240 allocated bytes**. Q38FIX's recorded loss was 1,578,770,432 bytes; the difference is only 8,192 bytes. No deleted-open root files were found (1,110 processes initially; 1,113 finally, no FD scan errors).

A bounded crash-report header check found `/usr/bin/python3.12`, signal **11**, PID **265467**, namespace PID **43**, parent PID **265408**, UID **0**. Internal command comparison matched the Qwen `sglang38_fixture/cache_probe.py` identity; no command arguments or environment were printed. The standalone core filename records start ticks **2515351** and the current boot ID. The PID is absent. The report date is **04:34:05Z**; artifact modification times are **04:34:26–29Z**, inside the supplied Q38FIX attempt window. This strongly associates the growth with that fixture. The report contains no cgroup field, so exact Docker-ID attribution is not asserted. The crashing native function remains unknown. Header parsing stopped before the base64 `CoreDump` attachment; neither core payload was inspected, copied, or hashed.

## Exact inventory and dry-run disposition

Both paths are on root device **64512 (252:0)**, UID/GID **0/0**, link count **1**. Exact nanosecond timestamps and atimes are in `root-space-facts.json` and `attribution.json`.

| Path | Inode | Mode | Apparent bytes | Allocated bytes | mtime UTC | ctime UTC |
| --- | ---: | --- | ---: | ---: | --- | --- |
| `/var/lib/apport/coredump/core._usr_bin_python3_12.0.9423b346-6186-4855-b1cf-f1725a853fe9.265467.2515351` | 266791 | 0400 | 970,436,608 | 970,440,704 | 04:34:29.471533 | 04:34:29.681535 |
| `/var/crash/_usr_bin_python3.12.0.crash` | 266790 | 0640 | 608,314,664 | 608,321,536 | 04:34:26.852518 | 04:34:26.852518 |

At **04:50:17Z**, 1,112 processes were checked: no open FD referred to either exact device/inode, and no Apport/whoopsie process was found. Both artifacts' identities, sizes, allocation and times remained unchanged through the final scan.

**Dry-run deletion list: empty.** These are raw native failure evidence, expressly covered by the instruction to preserve actual fixture evidence/raw failure files. A `CoreDump` attachment header exists in the crash report, but byte equivalence/completeness was not established under this metadata-only scope. Neither artifact was deemed redundant/disposable. They remain in place; no large archival move, deletion, truncation, or process termination occurred. Released bytes: **0**; deleted-open release delay: not applicable.

Even removing both would yield only **5,208,281,088 bytes (4.851 GiB)**, below 6 GiB. No other useful-size, plainly disposable task artifact was established. `/swap.img`, OS/runtime/package files, user Codex files/cache, system journals, and all existing task evidence were retained.

## Actual root accounting

Root is ext4 `/dev/mapper/ubuntu--vg-ubuntu--lv`, UUID **bc752bce-bb3f-4802-8adf-69c45a88689d**, device **252:0**, unchanged before/after.

| Measure | Bytes |
| --- | ---: |
| statvfs total usable blocks | 15,186,501,632 |
| statvfs used | 10,763,210,752 |
| root walk allocated | 10,763,063,296 |
| root walk apparent, final | 10,723,586,890 |
| used minus walked allocation | 147,456 |
| free including unavailable reserve | 4,423,290,880 |
| available to ordinary allocation / guard | 3,629,518,848 |
| free minus available | 793,772,032 |

The small 147,456-byte accounting gap gives no evidence of a hidden multi-GiB/deleted-open consumer. Superblock metadata reports 189,696 reserved blocks × 4,096 = **776,994,816 bytes**. The observed free-minus-available value is 16,777,216 bytes larger; its internal filesystem component was not separately attributed. No reserve settings were changed. Superblock overhead is 86,278 × 4,096 = **353,394,688 bytes**, exactly the difference between raw block count and statvfs total.

Major allocated consumers: `/usr` **4,746,387,456**, `/swap.img` **3,157,266,432**, `/var` **2,404,962,304** (includes both crash files), `/home` **447,287,296**. Complete top-directory totals and every root regular file ≥1 MiB by size or allocation are in the snapshots. All smaller entries contribute to the totals. The final walk inspected 164,838 unique entries /129,079 regular files, deduplicated 13 hardlink repeats and had no errors. It did not follow symlinks or cross `/boot`, `/data`, `/dev`, `/proc`, `/run`, or `/sys`; the mounted `/data/models-large` was consequently outside the walk. Under-mount content was not exposed through mount changes.

## Guard and backend verification

Fresh checks completed **2026-09-15T04:51:10.252179+00:00**. Exact installed root-protected identities remain:

- `/usr/local/lib/llm-server/control-api/scripts/common/registered-storage.py`: SHA256 `21cf082a841aeab9470bd6704b77104961b9d4afcaec696d90aa22b65f5b6f3d`, mode **0755**.
- Adjacent `scripts/install/storage.py`: SHA256 `4f834e92d149ea1955e79d34c53c18bf8c5846a4121d779e135a50d31a615505`, mode **0644**.
- Registry `/etc/local-ai-server/storage.json` and source ancestry are root-owned, protected and nonsymlink. Its dedicated roots match mounted identities: `/data` ext4 UUID **8daf56f1-5649-4163-9d87-919c2d271875**; `/data/models-large` ext4 UUID **a6d4ab58-84e1-4e48-9a67-13ad1c6f6e0a**.

The installed verifier's identity-only checks succeeded; **both complete guard invocations exited 1** because available root space is below 4 GiB. Identity checks are not a guard PASS or permission for dependent writes. Root is **665,448,448 bytes below 4 GiB** and **2,812,932,096 bytes below 6 GiB**. No override or historical helper was used.

GLM container **7cde6a376f58a1dee7ad425fbd104bbd7337effa6d6943a5bfc0dbeed4bbee78**, image **sha256:86feba4c82a8ec083d8da31fb8d1648f7b221b724a48eca571f5dd277a0caab9**, PID **243279**, process start ticks **2367582**, container start **04:09:20.746242473Z**, running status and restart count **0** are identical before/after. No inference/auth request was sent; readiness, backend configuration contents and native performance were not retested. No cleanup holder was created. No service/container/network/model/storage change, lifecycle/request lease acquisition, VM artifact write, or installer work occurred.

## Handoff and validation

Worker coordination: `../root-space-facts.json` and `../phase-result.md` were published promptly and finalized with this report. Worker evidence is `../evidence/`; committed copies are `reports/rootspace-evidence/`. Original Q38FIX and D3CAP checkouts, task metadata and VM evidence paths remain untouched. No new Codex session was spawned.

The metadata collectors were run successfully over `ssh ai-vm 'sudo -n /usr/bin/python3 -I -B -'`, with stdout/stderr saved on the worker. `diagnose.py.txt` was run before and after; `attribute.py.txt` was run once. JSON parsing, identity comparisons, empty error lists, unchanged candidate metadata, whitespace and quiet secret checks validate this report. These are operational observations; no source or installer test suite was run.

**Next action belongs to the parent:** use the preserved crash evidence to diagnose the fixture SIGSEGV and determine exact evidence disposition/storage recovery scope. Actual D3CAP/Q38FIX work remains paused while the root guard fails. ROOTSPACE made no automatic retry or resumption and did not broaden cleanup scope.
