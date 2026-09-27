# H014 download terminal snapshot

**Terminal timeout; all expected bytes present, verification incomplete.** One read-only ai-vm snapshot from mac-worker1 at **2026-09-27T08:55:27.329731+00:00–2026-09-27T08:55:27.351662+00:00**. No repeated polling or VM mutation.

| Measure | Exact result |
|---|---:|
| Expected files / bytes | 13 / 577,669,438,240 |
| Present final + partial bytes | 577,669,438,240 (100%) |
| Final bytes | 528,287,426,336 |
| Partial bytes | 49,382,011,904 |
| Existing published-hash verification | 12/13 shards / 528,287,426,336 bytes (91.451510%) |

Shard `MiMo-V2.6-Pro-RL-MXFP4-00012-of-00013.gguf.partial` has its full expected 49,382,011,904-byte length, but its durable state is `HASHING`, with no successful existing digest or verification flag. It remains unverified and preserved. The other 12 exact selected files have existing job hash receipts matching their committed published SHA256 values and durable verification flags. The durable manifest equals the committed selected manifest. No weights were hashed or their contents read in this collection.

The exact unit `h014-pro-download-20260927.service` is `failed/failed`, `Result=timeout`, `ExecMainCode=1`, `ExecMainStatus=1`, `MainPID=0`, `ControlPID=0`. Invocation ID is `528af0f4f3eb4002b934eea0a06217b7`. Recorded job PID was 1726144, start 07:20:01.337918 UTC, deadline 08:50:01.337914 UTC. Systemd reported its runtime limit at **08:50:01.320888 UTC** and main exit at **08:50:03.626167 UTC**. Durable status is `STOPPED_PARTIAL_PRESERVED`, `TimeoutError`, exit 1, finished 08:50:01.322119 UTC. The unit cgroup and all 14 checked recorded main/transfer PIDs are absent. Native job settlement is supported by the terminal unit and absent cgroup; no broad process scan was performed.

The durable aggregate `bytes_present=577562244896` is stale; this report uses current exact selected-file stats. Separate FINAL/ERROR JSON receipts were absent. The durable STATUS and short exact-unit journal provide the terminal evidence; the invocation-filtered journal returned no entries.

Selected variant: **AesSedai/MiMo-V2.6-Pro-RL-GGUF**, revision `ba4eabb78b6c51ffd873ec73b9e12b0f64aced5d`, **MXFP4**. Publisher precision is **native MXFP4 experts + BF16 nonexperts + F32 small tensors**, counts **207/163/357**. There is no extra Q8 attention conversion. Retained first-shard metadata reports `mimo2`, 73 blocks including 3 MTP, K/V dimensions 192/128, and published context 1,048,576. The first shard has zero tensors; prior partial headers are limited evidence. Full tensor inventory, loaded behavior and inference quality remain unqualified; author conversion lineage is incomplete. Pinned llama.cpp `7ac59a6e3ad851cd41af00f678effab0598ba9a8` CPU-expert Q8 activation arithmetic is not new weight quantization.

The existing image `sha256:cdb6efd75f53a8b453f866f30511b0f5c8d19440d3adaaf419e97bde1c2bf21e` completed at 07:27:53 UTC per the retained checkpoint. Its status remains CLI-only, MiMo not loaded; no runtime probe or rebuild occurred here.

Session `01a0e211-edfb-71a0-970f-377089d559bd` started **2026-09-27T08:53:40Z**, hard bound **08:59:40 UTC**. Snapshot collector exited **0**; report written **2026-09-27T08:57:13.242233+00:00**. Root subsequently verified launcher exit0 at 2026-09-27T08:58:08Z; task `finished-utc`/`exit-code` are authoritative. Delivery receipt records work completion, commit and bundle independently. Source base: `f6b417d021437e721ad2a1bbdd3b95d4d9cab606`.

Evidence: [STATUS.json](STATUS.json), [selected manifest](../h014-backend-prep-20260927/SELECTED-ARTIFACT.json), [retained checkpoint](../h014-checkpoint-20260927/CHECKPOINT.md), [precision/runtime notes](../h014-backend-prep-20260927/RUNTIME-NOTES.md). Bounded sanitized raw remains in the private task, SHA256 `c5c9e26ab4653aaba9e89737dbf20636432a91044a131c2bb47f95946e9c49c4`. Only this report and STATUS are committed. Local arithmetic, manifest/receipt reconciliation, scope, whitespace and secret-pattern checks replace an unnecessary application test suite for this report-only change.

Preserve the remaining partial. No automatic continuation, download retry, new verification pass, model load, inference, fan/ECC/BMC change or installer work was performed or scheduled.
