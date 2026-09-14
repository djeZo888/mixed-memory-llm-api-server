# D1b — bounded parallel acquisition and runtime contract

## Scope and implementation

Mac-Orchestrator explicitly authorized stopping only the current GLM acquisition, preserving every final/partial byte, and resuming the same 11 R2 artifacts with 3–4 distinct transfers. No additional model, inference activation, build/image change, GPU/daemon/driver change, disk mutation, historical checkout edit, reboot, or push is part of D1b.

Branch: `milestone/d1b-parallel-acquisition`; D1 base `6bab46f043ed42213f442220815b363f1fdddf23`. Exact artifact: `unsloth/GLM-5.3-GGUF@346b3591c7f28d1a23716f97a065ecf12ec14771`, UD-Q4_K_XL only, 11 files / **467289116837 bytes**.

The helper defaults to four distinct shard workers (three supported; one available for sequential fallback), under one global flock. An RLock serializes counters, rows and atomic JSON/fsync/replace. Failure cancels peers and joins them before terminal status and lock release; SIGTERM/SIGINT request cooperative cancellation. Reads have 90-second socket timeouts, service stop timeout 120 seconds. Failed integrity is preserved and never marked PASS. Complete interrupted partials are fsynced before rename. Existing final shards are rehashed on each restart; exact 11-name directory, sizes and all computed hashes gate final PASS.

Strict UUID/device/symlink/root guards, exact pinned metadata and HTTP 206/Content-Range/length checks remain. Startup reserves remaining download plus 20 GiB; midstream checks retain 20 GiB plus four write buffers. A model-mount failure can write STOP only to independently reverified `/data`; if that filesystem/root guard also fails, it logs that prior JSON may be stale and makes no fallback write. Four streams using 16 MiB chunks, a 2 GiB service memory cap, eleven futures, six attempts per shard, one overwritten status file, and bounded error output keep memory/logs bounded.

## Stop and preservation evidence

Live state was incomplete. Only `d1-glm53-acquire-20260915.service` was stopped with `systemctl stop`. At `2026-09-14T22:56:25.121053+00:00`: inactive/dead, MainPID 0, old PID 34781 absent, global lock independently acquired and released. **55550277637 bytes** remained:

| Shard | Path suffix | Bytes | Inode |
| --- | --- | ---: | ---: |
| 1 | `00001-of-00011.gguf` | 9428677 | 169607172 |
| 2 | `00002-of-00011.gguf` | 49433942336 | 169607173 |
| 3 | `00003-of-00011.gguf.partial` | 6106906624 | 169607174 |

All paths are beneath `/data/models-large/glm-5.3-ud-q4-k-xl/UD-Q4_K_XL/GLM-5.3-UD-Q4_K_XL-`. The **entire** shard-3 existing prefix SHA256 is `fbd51cf9be9f284ebd7be05e491268918e886412c2670cee7d1508c73d9baac1`. Exact pre-stop and stable post-stop paths/sizes/state are retained in original run `evidence/d1b-before-stop.json` and `evidence/d1b-after-stop.json`. D1 had computed-verified shards 1 and 2; successor rechecks them.

Verified live mounts: `/data` UUID `8daf56f1-5649-4163-9d87-919c2d271875`; `/data/models-large` UUID `a6d4ab58-84e1-4e48-9a67-13ad1c6f6e0a`. Strict and both unchanged common guards passed before stop and staging; root free about 5.197 GB, accepted below-6-GiB warning but above exact 4-GiB stop. The unchanged common guard still writes its two tiny historical `/tmp` diagnostics.

## Verification before resume — PASS

Executed on `ai-vm`, isolated snapshot `/data/build/d1b-glm53-20260915/repo`:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 scripts/d1/test_helpers.py -v
PYTHONDONTWRITEBYTECODE=1 python3 scripts/d1/test_parallel.py -v
bash -n scripts/d1/launch-acquisition.sh
scripts/d1/launch-acquisition.sh --help
PYTHONDONTWRITEBYTECODE=1 python3 scripts/d1/acquire.py --help
```

**5 existing + 16 new synthetic tests PASS**. New fixtures cover real four-thread overlap across eight distinct synthetic shards; 128 atomic status publications with concurrent readers; exact partial inode/prefix/Range preservation and retry offsets; wrong Range/length/body/hash/device; mount mismatch and midstream failure with peer cancellation; cancellation before transfer; no group acceptance on any worker failure; cross-process exclusive flock held through STOP publication and released afterward; capacity boundary; full-partial hash/fsync/rename ordering. Fixture data stays under original run `tmp/`; no live mount is disturbed and no fixture performs a model/network request. Local 16-test suite also passed. VM outputs are in isolated run `evidence/test-helpers.txt` and `evidence/test-parallel.txt`.

Independent diff review completed; durability/reserve findings fixed and tested. All eight staged helper/dependency/test/manifest SHA256s match local source. Acquisition helper SHA256: `950334895648a53db8ffef32171f2e97a64bdf6b0c07eed56424a4649a76fcf4`. Grep credential scan and whitespace checks pass; remote URL has no embedded credentials. No secrets or weight data are committed.

## Durable paths and remaining work

Updated helper lives in **new isolated** `/data/build/d1b-glm53-20260915/repo/scripts/d1/`; existing D1 source and other checkouts remain unchanged. Successor uses the same reviewed original run `/data/build/d1-glm53-20260915`, authoritative `evidence/acquisition-status.json`, model directory, lock, metadata manifest and D0B ready SHA. Resume/new-unit identity, verified-prefix proof and bounded throughput measurement are recorded below. `../acquisition-state.md` is the immediate moving handoff; `../runtime-contract.md` contains read-only runtime identity/flags for Worker2/D3.

Full acquisition/all 11 hashes remain **PENDING**. GLM model loading, GPU inference, Jinja reasoning/tool round trips, memory fit, authenticated readiness and lifecycle remain **NOT_TESTED**. CUDA enumeration and actual CLI help establish neither GLM inference nor tool correctness. The completed bounded resume and measurement are recorded below; acquisition acceptance belongs to a fresh task.

## Resume and measured handoff — PASS optimization, acquisition RUNNING

- Helper source commit: `220887d722d1f481f87c246a7e3767cd94b07453`; tests and deployed helper hashes match this commit. Report/continuation additions do not change the running helper.
- New exact unit **`d1-glm53-acquire-20260915-d1b-p4.service`**, PID **49253**, start **2026-09-14 23:02:39 UTC**, invocation `55ab64073abe462189f82c54ce8e299e`. This is the only active acquisition unit. Existing build `d1-llama-build-20260915-r2.service` is inactive/dead, MainPID 0, exit 0; it was left unchanged.
- Live resume preservation **PASS**: shards 1 and 2 retain their original inodes/sizes and were rehashed successfully; shard 3 retains inode 169607174 and its entire original 6106906624-byte prefix SHA256. First resumed request offset **6106906624**, HTTP **206**, exact `Content-Range: bytes 6106906624-48566415135/48566415136`. No old bytes were discarded.
- Live duplicate launch **refused before service creation**; independent second-process flock acquisition **refused** while PID 49253 owned it. Four distinct live transfers (shards 3–6) confirmed. No transfer errors/retries/failed rows recorded at final snapshot.

### Bounded throughput

**108712962 bytes/s (108.71 MB/s decimal)** over **150.004689 seconds**, `2026-09-14T23:04:07.161616+00:00` to `2026-09-14T23:06:37.166314+00:00`. Endpoint filesystem totals increased **16307453952 bytes**, from **64811300869** to **81118754821**. All four distinct shard files grew:

| Shard | Start bytes | End bytes | Added bytes | MB/s |
| --- | ---: | ---: | ---: | ---: |
| 00003 | 9143582720 | 13891534848 | 4747952128 | 31.65 |
| 00004 | 2785017856 | 7012876288 | 4227858432 | 28.18 |
| 00005 | 2734686208 | 6912212992 | 4177526784 | 27.85 |
| 00006 | 704643072 | 3858759680 | 3154116608 | 21.03 |

This is **1.489×**, about **48.9% higher**, than D1's approximate 73 MB/s sequential rate. It is an endpoint byte-delta observation with small sequential-stat timing skew, **not a rigorous network benchmark**. The observed improvement justified retaining four workers; no further tuning occurred.

### Final bounded snapshot and limits

At **2026-09-14T23:07:32.283808+00:00**, unit/PID remained active/running. Actual file total **87124998149 / 467289116837 bytes**. Authoritative JSON, updated **2026-09-14T23:07:20Z**, reports **85833152517 bytes**, **2/11 computed-verified**, **49443371013 verified bytes**, status **DOWNLOADING**. Filesystem and JSON samples differ because downloads continue and JSON refreshes approximately every 15 seconds; neither moving total is final integrity acceptance.

Both common guards and strict live UUID/root checks **PASS** after measurement; root free **5199921152 bytes**. Model mount and `/data` identities remain exact. Service task count 5 matches one coordinator plus four workers. Memory is bounded by 2 GiB including file cache: observed anonymous memory 140808192 bytes and file cache 1928359936 bytes; cgroup recorded max-limit reclaim activity, **zero OOM/OOM-kill events**. Acquisition log was 456 bytes at the handoff check.

Read-only runtime contract **PASS**: live image ID `sha256:6866856c573d69d504f82265321b182f631a7b3912a1ed1b4efbf893729d4e62`, tag `local/llama-cpp:v0.4.1-b29c606-cu132-sm120-d1`, local RepoDigest with the same SHA; clean source `b29c606e28a01b1bc8c1351026a0fa6e616bf6c4`, CUDA 13.2.1 pinned bases, SM120a build. Actual recorded help (58136 bytes, SHA256 `a144e0605fbd0092e6e68cc51d1cdc3c3f8ea75bb63e2f53e4478ab2cde9e8a5`) includes `--chat-template-kwargs`, `--reasoning-format`, `--reasoning-budget`, CPU-MoE/device/tensor-split, Jinja, API-key-file and no-WebUI. Exact pins, defaults and reasoning/UI caveats are in task sibling `runtime-contract.md`; no container or inference endpoint was launched during that check.

**Next recommended action:** leave this durable owner running and end this bounded session. A fresh acceptance task must inspect live unit/status, finish all eleven size/computed-SHA checks and final storage guards; follow [D1b continuation](d1b-continuation.md). Full-download/all-hash **PENDING**; GLM load/inference, tool round trips, authenticated readiness, memory fit and lifecycle **NOT_TESTED**. No D3 activation or additional model is authorized here.
