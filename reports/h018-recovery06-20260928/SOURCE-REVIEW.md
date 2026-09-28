# H018 RECOVERY06 local source and LIVE05 timeline review

Scope: local read-only audit of the isolated RECOVERY06 repository and retained LIVE05 evidence. No SSH/VM action, tests, deployment, model request, source change, or shared policy/owner edit was performed by this reviewer. Recovery readiness is owned by ROOT and must be taken from its fresh authenticated receipt.

Authoritative prior task: `/Users/agent/CodexProjects/llm-orchestration/tasks/H018-LIVE-05-20260928` (abbreviated `LIVE05` below). Native CLI session: `01a0e585-588d-75e2-9382-bc279dfcffcf`.

## Current-only source for review

At audit, `git status --short --branch` showed branch `worker1/h018-recovery-06` and only untracked `scripts/h018/live05/`. Both files are byte-for-byte identical to the exited LIVE05 copies.

| File | Bytes | SHA256 | Role |
|---|---:|---|---|
| `scripts/h018/live05/retime_last.py` | 3362 | `9ef3cc3ed87b68d9d8c6ba89766f16685ce49e0ec06157fe70544400929e581c` | Source for the completed, inactive LAST admission-clock retime; does not dispatch. |
| `scripts/h018/live05/enable_selected.py` | 4270 | `d143918b2c8b8ee81c1b265b16b4efcfceed07211ccf57028a209a09b718bd1d` | Conditional post-qualification enable helper; not executed after the failed qualification. |

These two compact source files are suitable for an archival source-only commit. They contain protected credential **paths**, not credential values, and contain no raw traces/model data. Do not include `private/`, CLI event streams, generated configuration-injected remote scripts, raw receipts, or source/result copies from prior tasks in the source commit. Preserve those in LIVE05 and cite them.

These are configuration-injected historical helper bodies, not standalone reusable commands. `retime_last.py` expects `CONFIG`, `OLD_PINS`, and `NEW_SOURCE`; `enable_selected.py` expects `CONFIG`, `QUALIFIED_RECEIPTS`, and `READ_HELPER_SOURCE`. Their presence or publication supplies no execution authority. Do not execute either against the restored GLM selection.

Static source review: the retime helper checks the pinned owner and identity/selection, borrows the canonical settlement lease, applies registered-storage guards, requires LAST inactive/static with MainPID 0 and all authority/attempt files absent, checks reviewed source pins, backs up old bytes with exclusive mode 0400, changes exactly two epochs, and verifies source/identity/absence again. It performs no manager reload and no dispatch. The enable helper requires actual native/production receipt gates, exact 950000 capacity, authenticated idle native/private slots, ready/unlatched canonical service, and unchanged owner/selection; it uses `enable --no-reload`. Its receipt conditions were not satisfied in LIVE05.

`scripts/h018/last950k/client.py` is already tracked, unchanged in this isolated copy, with SHA256 `28d61829c6b28067b59db4520ef72a94d5b230cfb28058f2cfe8984525b1f63b`. Its last affecting commit is `093c6bdaa7939bc3bec36e206745c5ed98fa9bed`. It contains exactly two `1790559000` constants and no `1790558700`. Do not represent that tracked prior change as a new RECOVERY06 source edit.

## Exact LAST timeline and causality boundary

Timestamped native event source:
`/Users/agent/.codex/sessions/2026/09/28/rollout-2026-09-28T02-58-36-01a0e585-588d-75e2-9382-bc279dfcffcf.jsonl`.

All times below are 2026-09-28 UTC. SHA256 values for commands mean the UTF-8 bytes of the decoded `exec_command.cmd`, which equal the native CommandExecution `command[2]`; they are not hashes of escaped JSON or shell display wrappers.

| Time | Evidence | Event |
|---|---|---|
| 01:00:13.510 | Native event line 62; completed line 64 at 01:00:13.595 | Local source/file reads only (`sed`, `rg`, `ls`, `cat`, `head`, `date`); command SHA256 `3559f409b3597592b529c4131631fee69bd3c58f5c66a5daa2febe7faeaaaae1`. |
| 01:00:16.138523 | `LIVE05/ROOT-FAILURE-LIVE05.json`, `primary_failure.observed_at` | Primary `lifecycle_busy`, operation `hardware_latch`, phase `RUNNING`. |
| 01:00:21.574 | Native event line 69; completed line 71 at 01:00:21.671 | Local source/config reads only; embedded Python reads JSON and prints source pins. Command SHA256 `20a476e6571b5277b1b737825c56a3ab40b405797f765f2cb49cbdde638bd240`. |
| 01:00:25.163753 | `LIVE05/ROOT-FAILURE-LIVE05.json`, `cleanup_failure.observed_at` | Separate cleanup `command_timeout`, operation `settlement`, phase `SETTLING`. |
| 01:01:22.470 | Native event line 76, call `call_lNJxzQKqIJr8m8nGc8qx8qZ4` | First helper-creation/remote-retime command tool call. Input SHA256 `b31c58ca8c1e0a11fc4822614accbb45e60fb36f5d4e64986c1946b4643f48ae`; decoded command SHA256 `3408fe49ba752dc39be9725f2d707d2daeeb3e3aeb93ecc8e1414b1e465c6bac`. |
| 01:01:22.512056 | Local retained LIVE05 `repo/scripts/h018/live05/retime_last.py` filesystem birthtime | Helper source first created. Its mtime is 01:01:22.514925. |
| 01:01:22.645–01:01:23.198 | Native event line 78, command `exec-b5344c91-0bd7-422c-8bbb-da09b0b9520f` | Recorded CommandExecution interval (`started_at_ms=1790557282645`, `completed_at_ms=1790557283198`), exit code 0. Source creation stat and CommandExecution start are different instrumentation boundaries; do not equate them. |
| 01:01:23.203 | Native event line 79 | Tool output received. |
| 01:01:23.318082 | `LIVE05/ROOT-LAST-PREP-LIVE05.json`, VM UTC | Remote transaction receipt: `INACTIVE_LAST_RETIMED_SOURCE_ONLY`, `manager_reload=false`, `dispatched=false`. Mac/VM clocks are not assumed perfectly synchronized. |

The LAST retime command and source creation were after both recorded failures. This excludes that retime transaction from being the contemporaneous lease contender at 01:00:16. It does not identify the historical lease holder. The 01:00:13/21 commands did not perform VM writes or invoke SSH.

Exact remote source change is retained in `LIVE05/private/LAST-RETIME.diff`: only two validation constants changed `1790558700` (01:25) to `1790559000` (01:30). Old remote client SHA256 `1c2b1f9dfc913bad7122d6c621e5d8dd0e14566cf2f7a68118397fb319b1a54c`; new SHA256 `28d61829c6b28067b59db4520ef72a94d5b230cfb28058f2cfe8984525b1f63b`. The independent active cap remained 28800 seconds. `LIVE05/ROOT-GO-LAST.INACTIVE.json` has `authorized=false` and no native, production, or Sova acceptance receipt. LAST was not started.

## Compact qualification and recovery facts from retained evidence

- `LIVE05/ROOT-FAILURE-LIVE05.json`: authenticated configured/allocated capacity at dispatch was 950000. Tiny text passed with 14 prompt tokens, 2 completion tokens, full DONE/HTTP drain, and authenticated idle settlement. Input processing was 1.051045 s, output generation 0.147262 s, total 2.417055 s. Full17 was interrupted after dispatch at 01:00:01.289724; expected input was 9540, actual processed tokens remain UNPROVEN, no raw chunks/terminal SSE were received, and continuation never started. No qualified 950000 receipt was emitted. Sova MiMo was NOT TESTED. LAST was not dispatched.
- The failed full17 request SHA256 remains `bf254278639b602dcf87ba29fcf9e76c4f8d5fe5a0dcdb7d01aa22c871ae3275`. Physical release does not establish terminal stream completion or HTTP success.
- `LIVE05/ROOT-RECOVERY-CHECKPOINT.json`: at 01:10:54.053710–01:10:54.073798, exact current holder was canonical node PID 3309508, FD 7, device 0:26, inode 1838; before/after `/proc/locks` matched, capture complete. This is current-at-capture holder proof, not proof of the 01:00:16 holder.
- `LIVE05/private/EXACT-PHYSICAL-SETTLEMENT-LIVE05.json`, SHA256 `bbfb136a19321e32d7e11882a6d4c6acf978aa3518a0a398197152639a74899c`: at 01:11:35.378741 exact MiMo native PID released, cgroup empty, GPU compute empty, and exact proxy released under the validated existing canonical settlement lease. Failed stream completion remained `UNPROVEN`; retained HELD state bytes and both failure records were preserved at that check.
- `LIVE05/ROOT-ROLLBACK-START.json`: failed state archived immutably at `/data/build/H018-20260928/live05/FAILED-LIVE05-IMMUTABLE.json`, mode 0400, SHA256 `8849fce861f1644b7757b4a97e1c3e91893ebdab1aa46ba913c463fe5e1df1d5`. Failed-own-request reconciliation at 01:14:11.740936 preserved primary/cleanup failures and did not claim HTTP success. Normal GLM rollback dispatched 01:14:12.356313–01:14:12.369805, selected frontier `glm-5.3-flash`, generation 11. Node PID 3309508/invocation `7264f712a5024b2484d38535790b94df` stayed active/running/enabled; no node stop was needed.
- ROOT's fresh `H018-RECOVERY-06-20260928/ROOT-READY.json`, observed at 01:19:41.037039, records protected authenticated GLM readiness and `/v1/models` max-model length 1048576, server context/allocation capacity 1048576, and fresh ready/unlatched canonical GLM, two Qwen and image services. GLM native container `2b5e5e386f70678cefebbfcb66cfdab568e9b3744abfb366f03a66ea7fdb03ab`, PID 3099917/start ticks 7075659, image `sha256:51791e17c0149019e2ddc032d8c1b2f60b86c3a6c293daff639e20053baa858a`, selection generation 11, and unchanged canonical node PID 3309508 are recorded there. This reviewer read that receipt locally; it did not perform another live check.

No new probes or tests were run for this source review. Upstream swap-fix proof/history was not retested. No periodic-proof/hot-path or shared policy/owner fix is included here.
