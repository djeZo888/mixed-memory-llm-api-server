# R8 exact source review — OPTIMIZE10

Prepared 2026-09-27T15:07:15.517682+00:00 in the isolated `49679c0ffc5e3ed3919dcd6125f939f96db3eae6` checkout. Local source/checks only; no SSH, dispatch, native measurement, or commit by this subtask.

The sole native inference change is `--threads 64` → `--threads 16` (argv value index 34). `--threads-batch 64`, `GOMP_SPINCOUNT=0`, capacity 131072, F16 K/V, image cdb6efd, native weights, CPU mask/strict flags, NUMA distribute plus outer interleave 0–7, load none/no-host, GPU, batch 2048/ubatch 512, memory 704 GiB and all other Docker/native settings are retained. This is a causal thread-count candidate, not a selected final setting.

The source namespace is `worker1-r8`, container `llm-h016-mimo-pro-r8`, unit `h016-mimo-profile-20260927-r8.service`. Admission is 17:00 UTC, settlement 17:25 UTC, overall 17:48:08 UTC on 2026-09-27. Launcher command after exact-source root GO and normal R7 settlement: `/usr/bin/python3 -B /data/build/H016-20260927/worker1-r8/launch_r8.py --run`. The launcher retains independent systemd ownership, no restart, RuntimeMaxSec to settlement, mixed kill, 420-second stop budget and existing ExecStopPost cleanup. It requires at least 25 minutes before admission. It does not stop R7.

The predecessor gate requires exact R7 container `b0c319cce5c8fcececc28acb01ec92f68693588ba843c8136107927aa7ffbac1`, native PID 232672 / StartedAt `2026-09-27T14:28:05.871420053Z`, owner PID 229308 and invocation `2034e3b8f6004f6da8ebf7a92a389690`. It requires retained `SETTLED_GLM_RESTORED`, no native/owner/proxy processes, no native/unit cgroups, native PID0 and recorded GPU release; ordinary preflight then revalidates original GLM running. No adoption or cleanup bypass.

Exactly the same tiny 8-output warmup and tag-A 128-output fixture are dispatched by the systemd owner. Baseline requires native count 83; seed270927, temp0, thinkingfalse. The exact baseline compact JSON SHA256 is `1fef2a52395898b3628a2e2e08058e7719cd43ca08906e16dd50bdd8e9cfc86f`. `PROFILE128` and the CPU perf module are omitted. No activity sampler starts; retained cheap counter snapshots occur only at request boundaries. No context ladder or tool qualification.

Recorder changes retain raw chunks in memory, adding UTC beside monotonic timestamps for each chunk, first/last output, request sent, terminal SSE and DONE/drain, with native timings, usage and finish preserved. The per-request `LABEL-PROGRESS.jsonl` is opened through protected storage anchors before transmission, without a lifecycle lease spanning inference. The first output performs exactly one direct write of a compact `FIRST_OUTPUT` UTC/monotonic/fixture-identity event, immediately readable on VM; no guard or fsync runs there. Other writes remain at boundaries/finally; no per-delta write. After each full drain, one authenticated `/slots` read must show the sole slot `is_processing=false`; its UTC/monotonic receipt records settlement. These are reader-arrival timestamps, not GPU token completion.

Existing bounded post-load placement is retained. One matching bounded post-warm placement read (maximum 3 seconds) records actual TID affinity masks plus guest NUMA CPU lists before baseline. Its source expectation is 16 decode worker indices across 8 nodes, 2 per node. All thread counts are not a worker classifier; actual masks must be reviewed. A timeout is unavailable optional evidence, never a guard bypass. No process walk was added to the 5-second safety loop.

Focused validation passed: all 9 Python files parse; native argv lengths equal with one value change; AST equality for `settle`, `cleanup_proxy_and_settle`, `suppress` and mandatory `monitor`; exact R7 baseline payload equality; only warm+baseline request calls; local mocked split SSE byte-for-byte round-trip and timestamp/usage/finish/DONE/drain/native-timing retention; post-drain native-idle receipt and exactly one immediate FIRST_OUTPUT progress write. No native test or broad test suite ran. Actual R8 load, affinity, thermals, performance and reserves remain untested.

Focused patch SHA256: `4036bf8518c9880664e969bfb798afcd5b9bd3dc0abadeff841c628244eb3a49` (`R8-VS-R7.patch`). The patch compares R8 to R7 and shows the absent perf source; it does not modify R7. Source SHA256 manifest is `R8-SOURCE-SHA256.json` (source files only; remote protected dependency pins/quiet receipt must be included by the launcher packet as before).

| Source | SHA256 |
|---|---|
| LAUNCH.json | `4dd54a77360b8b84ed6eb2a93735212683e47ff8fc76781b4e94a9e09aa65418` |
| benchmark.py | `32cd65e4ff42878b2062db21071c0bc90f71be07ac856dc9404b4b4901fecaec` |
| candidate_owner.py | `04d8e326506279baa5f9932df861b8cefc3b08195adc0ee25f26b705aecb2f3e` |
| inspect_gguf.py | `bc76625dc1e370db29036fc8218eac82bea414e73dce6daa2b3bd43e650acba4` |
| launch_r8.py | `49867ba17fe4be9d366139712f0e8f655d16a9dc8cab05b45b36ea8fdeacc538` |
| native_identity.py | `0ba1f5781585ba887bd639e950870976e0ecb159caa674cb72dfa41cc48d3518` |
| private_proxy.py | `4d76bff2e2330c3ca5675f0c2c6413b9dc945d62fe11cb56e678bdb89d9c1317` |
| profile_activity.py | `dadbb73a4096364a5ddd401dd8dbd3f40d1dd9ec453d1ce10eebc59c82fe051a` |
| telemetry.py | `79b63724750bdc51f029353bd2f3e6670da224946071b963d8b833e980f50c99` |
| verify_retained.py | `e61659072656e4ec1ae47879d787eff58ce366838721f1213054122ce6abe457` |

## Review provenance after FIRST_OUTPUT recording addition

The initial copied patch digest `63746fb97ec2094de574910cc3054678b00cb55d67b77582311424d02b31ca65` described reader `7c6c6422c1dc8efdd4657555a38f0225e78c5e446a7e145505704d24fd6b49ac`, before root requested immediate FIRST_OUTPUT recording. The final reader `32cd65e4ff42878b2062db21071c0bc90f71be07ac856dc9404b4b4901fecaec` adds only the preopened anchored progress file, one direct FIRST_OUTPUT write, and its close. The accurate final patch digest is `4036bf8518c9880664e969bfb798afcd5b9bd3dc0abadeff841c628244eb3a49`.

Parent reports that ROOT-R8-GO's individual source hashes match all current source files, including the final reader, and that this exact packet was staged at 15:11:33 UTC; the GO patch digest retained the initial value. Parent saved an AUTHORITY-NOTE. These dispatch/GO facts are parent-reported, not remote checks by this local-only subtask. Source remains frozen; no restoration or source edits followed that notification. Final local SHA256 manifest equality and all Python syntax checks passed.
