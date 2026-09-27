# H013 Worker2 — offline reboot/ECC review

Base/branch: `33c49020fa5d107006c1d7566f63f83033f3dbe0` / `worker2/h013-reboot-review`.
Scope: isolated mac-worker2 source/evidence review only. Read AGENTS.md, ../PLAN.md and applicable source guidance. No ai-vm/ai-harness/Worker1 contact, inference, allocation, download, build, deployment, shared-checkout change or push. Sova remains paused by instruction; no current live state was observed. Root decides and coordinates; Worker1 alone performs later VM operations.

**Recommendation:** after concrete verified H012 PASS, promote only the three existing production runtime context constants/bounds below, using the existing boot owner and original production container. Preserve the private candidate, original 480K source/config/state and all scientific receipts. No owner redesign, Docker restart-policy change or new runner framework is needed. Failed/incomplete 1M is never promoted. This report is a proposal, not activation approval or live acceptance.

## Result and identity boundary

Latest local evidence is `reports/h012-flash1m-20260927/LAUNCH-RECEIPT.json:1–40`: **RUNNING_PREFILL_CONFIRMED at 02:37:00 UTC**, main sent 02:36:10, deadline 04:36:10; exactly 1,000,000 native input, pool 1,048,576, output <=1,024. No terminal result is available here; systemd `Result=success` on a running unit is not inference PASS.

Fresh unit `h012-manual1m-02.service`; stage `/data/services/h012-manual1m-02-20260927`; candidate `llm-frontier-flash-h012-manual1m-02`, port 30011, ID `5e4fd432cd86ddac3021f804facae4f5dbf710bcaf2873200e8834ec323977ea`, nonce `80f690e35a6849fe841efcc0957b9809`. Durable receipt base `/data/logs/flash-h008-20260926/H012-MANUAL1M-02`; preserve `-OWNER.json`, `.json`, fixture, stream/progress/telemetry, native logs, unit/container/boot/source identities and complete guard evidence off-VM before maintenance.

`reports/h011-worker2-20260927/manual/manual.py` is now the canonical **corrected** source, despite its historical directory name. Lines 97–101/183 canonicalize complete mount contents; 486–509 borrow/reset the outer lease. Applying exactly the five attempt02 identity substitutions in `reports/h012-flash1m-20260927/MOUNT-ORDER-FIX-AND-FRESH-IDENTITIES.patch:1–23` reproduced staged manual SHA256 **a661309ec32bde912f84395f8bb98fc0a9daca4ccf0c16d2cdfdb2f52c4f1560** offline. `REVIEW02.json:4–7` binds archive **180b0e9188fd41846ffe4e31d6c90aa4c973a9f9170663786ce482b871b408d5** and manifest **f5186cd4efdd0797c126b9c979c3055017aa8047dbb807e57c0aeca7cab1daa4**; `STAGE02.json:1` records deployed component hashes. Archive/deployed bytes were not fetched.

PASS requires `manual.py:84–91,424–449`: semantic PASS, transport complete, SSE DONE and body drained, finish reason `stop`, prompt usage exactly 1,000,000, completion 1–1,024 and consistent total, no resource failure, exact identities/capacity, settled writers and durable terminal owner `PASSED_RETAINED_PENDING_PRODUCTION_PROMOTION`. A retained-success evidence-write quarantine (`:450–458`) needs root reconciliation, not inferred PASS. Failure cleanup (`:282–314,459–478`) confirms exact candidate stop/cgroup settlement before original 480K recovery; unknown ownership stays quarantined.

The candidate is **not reboot durable**: `manual.py:442–445,546` explicitly records restart=no and original desired-running 480K restoration. Native scheduler 300s forward-progress watchdog remains distinct from the two-hour main deadline and 900s four-way job (`reports/h011-worker2-20260927/WATCHDOG-SOURCE-01.md:3–7`). Healthy chunked prefill advances the scheduler counter; do not extend any bound.

## Minimal proposed diff and production ordering

Exact replacements, only on reviewed PASS; no source patch has been applied:

| Existing source and line | Old -> proposed |
|---|---|
| `scripts/runtime/flash/file_auth.py:17` | BOUNDS input `479993` -> `1048569`; input+reserved output `479998` -> `1048574` |
| same file `:128,137` | Both context/pool arguments `480000` -> `1048576`, and assertion likewise |
| `scripts/runtime/flash/tokenize_adapter.py:14` | `CONTEXT = 480000` -> `CONTEXT = 1048576` |
| `scripts/runtime/flash/idle.py:51` | Required context/pool `1048576`, max_req_len `1048575`, max_req_input_len `1048570` |

Keep loopback port 30010, launcher command, owner/container name, GPU UUID, image, weights revision `eb9eb208eb0d988989d07a6a12d0fdeb5f52574a`, auth, FP8 E4M3 cache, 64 CPU workers/eight NUMA pools/CPU0–71, radix disabled and 2048 prefill settings unchanged. The source arithmetic matches the qualified candidate's `manual/context_profile.py:18–30`; neither declared capacity nor this arithmetic establishes completed 1M occupancy.

1. Root reviews actual terminal evidence; Worker1 verifies the exact fresh owner/job/container, settled requests, unchanged pins, storage/root guards and canonical lifecycle lease. Do not interrupt active 1M or alter its ECC/source. Archive H012 terminal evidence before any transition. On failure/incompletion confirm original 480K recovery through the current attempt02 owner; no 1M source change.
2. On PASS, stage/hash/review the three proposed files while the candidate remains loaded. Snapshot original protected `/data/services/flash-h008-20260926/{source,config.json,state.json}`, service/enablement, container inspect and installed release copies. Preserve original container ID and desired-running intent. Keep staged candidate and all historical releases intact.
3. Under one borrowed canonical lease, **before changing production hashes**, validate/stop only the exact candidate using current attempt02 validation and stop-proof semantics (`manual.py:211–225,282–294`): require `stopped(c) == True`: Running=false, PID=0, neither restarting nor paused, and empty captured cgroup. Use a separate H013 maintenance receipt. **Do not call `stop_candidate` blindly:** lines 295–296 rewrite H012's terminal owner; preserve its immutable scientific PASS. Do not call `restore`, which restarts 480K. Keeping the candidate container/stage stopped retains rollback evidence; simultaneous two-650GiB allocation is outside the guards.
4. With both Flash instances stopped, install the three files through existing anchored storage writes and update only their protected `config.json.source_sha256` entries. Verify all seven source entries before owner start. Multi-file publication is not magically atomic: interrupted/mixed hashes must refuse startup, with the complete protected snapshot available. Update files in the existing bind-mounted source directory; do not silently swap its inode/symlink and leave the preserved container bound to stale bytes. The original container remains preserved but consumes the selected source on restart; restoring 480K requires restoring its exact original source/config as well.
5. Existing `owner.py:116–123,126–179` already supports borrowed lease, guarded source identity, same-container start, desired intent and hardware admission. `llm-frontier-flash.service:13–14` uses resume/halt; `halt` preserves running intent, `stop` changes it. Keep Docker restart=no and verify current enabled unit/drop-ins match reviewed owner paths. Start the preserved production container through its owner. Require actual native readiness, authenticated tokenizer context, allocation log/pool, and a bounded short validation before considering replacement accepted; systemd active or Docker running alone is insufficient. Preserve candidate until that verification succeeds. Any failed replacement stays a disclosed failure with Sova paused; no silent 480K labeled 1M. Old H012 status helpers can reject changed production hashes (`manual.py:118–133,223`); use archived result plus separate H013 maintenance readback, never rewrite historical pins to make them pass.
6. After durable production acceptance, stop each service through its owner preserving intended reboot state; settle all requests, then perform the one authorized guest reboot. Verify new boot ID and actual restored native capacity again. A guest passthrough inability to apply ECC is a reported stop condition, not authority for host reboot/reset.

Before later Sova unpause, align **all** capacity surfaces on accepted actual capacity:

- Preserve `configs/deployments/glm-5.3-flash-480000-fp8-kt.json` as rollback; derive a separate `glm-5.3-flash-1048576-fp8-kt` declaration with launch context/pool, configured capacity and native bounds above, linked to actual H012 PASS. Retain historical acceptance fields as history, not fresh claims. This declaration alone does not launch anything.
- `scripts/control/node_observation.py:340–341`: select matching 1M deployment ID and configured_context_tokens only with the installed accepted 1M source. It currently hardcodes 480K and checks container identity rather than native capacity. Root must bind publication to source/manifest identity and native readback; rollback must restore the corresponding advertisement too.
- `ai-harness/config/frontier.json:3` contextWindow ->1048576; `ai-harness/server/src/frontier.ts:27,197,289` add1048576 to type/allowlists. Keep native-count equality and margins7/2 (`:242,251–257`), output ceiling65536, revisions/auth unchanged.
- `ai-harness/deploy/engine/configure-profile.mjs:10` FRONTIER_CONTEXT ->1048576 updates provider limit at41 and managed frontier agent context at217. Line233 rejects differing existing agent content: root must assign an explicit, protected migration of exact old managed bytes only; preserve custom conflicts, sessions, histories and user files. Leave Qwen default/pools480000. This review performs no Sova changes, build or contact. End-to-end advertised/native agreement remains a later release gate.

## ECC policy and exact matched repeat

Normal `scripts/runtime/flash/owner.py` and `scripts/lifecycle/hardware_policy.py` have no ECC-enabled policy predicate. `scripts/control/node_collectors.py:136–140` reports current ECC only. The explicit Enabled/Enabled check is historical H012 `manual.py:188–195`; leave that source and its receipts untouched. For the new H013 maintenance/driver copy, enforce the exact four UUID inventory below and **Disabled/Disabled current/pending** after reboot. Add this small assertion to existing pre/post identity capture (`attempt03/driver/job-body.py:53–73`) using `nvidia-smi --query-gpu=uuid,ecc.mode.current,ecc.mode.pending --format=csv,noheader,nounits`; unknown/missing/duplicate UUIDs or unsupported ECC readback refuse admission. Pending Disabled alone is not applied ECC. Preserve hardware-latch policy, cumulative/error evidence, and all other admission guards. Worker1 must reconcile actual installed policy/source hashes; local source is not deployed-state proof.

| Lane | Exact UUID | Baseline current/pending | Required post-reboot |
|---|---|---|---|
| Flash | GPU-69acfa26-8b60-61b5-702d-aee252c163cc | Enabled/Enabled | Disabled/Disabled |
| Qwen0 | GPU-88058d9d-08e5-cb1e-a77a-04cbc1488237 | Enabled/Enabled | Disabled/Disabled |
| Qwen1 Server | GPU-93dbfca8-ef3a-9628-a798-6a4afd0af528 | Enabled/Enabled | Disabled/Disabled |
| Ada | GPU-5d895991-b794-2b4c-b9c4-5f1b668afd23 | Disabled/Disabled | Disabled/Disabled |

Baseline ECC is preserved `attempt03/FINAL-IDENTITY.json:1`. Worker1 records prechange current/pending, limits, clocks, fans, thresholds, flags and counters before targeting only the three Blackwell UUIDs for ECC off. Ada gets no ECC mutation. No power/fan/clock change, error-counter reset or latch clear. If ECC off makes an error counter unavailable, retain its prior evidence and record N/A; do not report zero or improvement. Required safety/identity checks must still pass.

Reproduction source root: `reports/h011-fourway-20260927/attempt03/driver/` (not earlier H011 driver). Reuse `vm-common.py` + fresh reviewed `PARAMETERS` + `job-body.py`, as `dispatch.py:10–18` does. Change only fresh H013 prefix/unit/output/owner namespace, exact source/base/session/quiet/contract/boot/container/StartedAt/capacity identities and current bounded dispatch deadline. `dispatch.py:23` contains expired 01:42 UTC; do not execute it unchanged. Keep original namespace immutable, write-new/no-replay behavior and canonical lease/storage/auth checks. Reconcile installed source identities before embedding fresh PARAMETERS; do not carry old 480K capacities into a PASS branch.

Reuse exact archived `/data/logs/flash-h008-20260926/H011-FOURWAY03-FIXTURES.json` (21,483,489 bytes), SHA256 **135f2bbbea8deda81576feb667fbbd2411810a04150da9a76e6f0b730b467dec**; historical task path `evidence/FIXTURES03.json`. Copy verified bytes to the new namespace, never run `prepare-fixtures.py` or regenerate text/templates/token IDs. `FIXTURE-COUNTS-HASHES.json` binds all 12 cases per Qwen and Flash (`:222–232`); its old Flash context_limit480000 is immutable counting provenance, not the new pool claim. Qwen count records' max_model_len262144 are not current480000 pool proof. Verify actual pool separately. Exact archived bytes are **absent in this checkout**: root/Worker1 must verify retained bytes against manifests before use; missing/mismatched bytes block exact reproduction.

The image payloads are not in that archived text fixture; retain exact deterministic `job-body.py:239` prompt, opaque1920x1080 geometry and seeds202609270+i (i0–7). First wire hashes: Flash `2d0ea24741b129200bcaa309b672f49fef9b42562fcea8f6e84ec8a937c3fbd4`; Qwen0 `0b1c6690a4e8e36489b58fe6ddb42757ba18104d01f0d41dbf4a91bd46f32c91`; Qwen1 `2e75c96f25f02caf92f9d34b60f5c1052d61e09ef2db95ad24741f552e4641eb`; image0 `b436fd7033caa9a38bb838690a1931af335c6eb1f5138cf9179a8a61a14ba745` (`RESULTS.json:146,164,181,198`). Preserve same serializer/options and verify each wire hash; different fresh Qwen cases within the run remain the archived per-index cases, not newly generated inputs. Short warmups and settled comparable starting temperatures precede the barrier and must be separately recorded.

Bounds unchanged: one Flash65536/output768; <=12 fresh262144/output128 requests per Qwen; <=8 FullHD images; Qwen pools480000; Flash pool1048576 only after verified PASS, otherwise480000. 300s is the **new-submission window**, not spacing between requests; per-request540s (`job-body.py:172–173`), settlement trigger870s (`:275`), systemd job900s (`dispatch.py:29`). Preserve serial per-lane requests and barrier, buffered stream capture/separate writers, 85C or lower reported hardware threshold (`:251–253`), Flash7%, host15%, Qwen16GiB, Ada5%,650GiB/no-swap Flash containment, error/storage/auth/identity/lifecycle guards (`:101–122`). Client closure is not native settlement. One repeat only; thermal stop is final evidence, not permission to retry.

Telemetry-only addition in new copy: include supported `clocks.current.graphics`, `clocks.current.sm`, `clocks.current.memory`, ECC current/pending in the existing field list/support probe (`job-body.py:9–10,254–258`); record unsupported fields explicitly. Keep before/after raw `nvidia-smi -q -x` capture (`:240–241,284`) for power limits and hardware thresholds. Mandatory ECC identity gate is separate from optional telemetry support. Do not alter controls or mask unsupported safety inputs.

## Preserved ECC-on fan03 baseline

Values below verified against committed compact evidence, **not rederived from absent raw telemetry**. Source `attempt03/RESULTS.json:8–127`; power-limit values are report-only `RESULTS.md:126–129`.

| GPU | Observed min–peak C (not all start values) | Independent peak W | W at same Blackwell peak | Reported limit W | Fan percent/RPM | Actual clocks / hardware threshold |
|---|---:|---:|---:|---:|---|---|
| Flash |38–45|114.67|91.17|600|percent unavailable here / RPM unavailable|unavailable / unavailable|
| Qwen0 |35–85|603.00|599.08|600|percent unavailable here / RPM unavailable|unavailable / unavailable|
| Qwen1 Server |36–85|645.28|645.28|600|[N/A] / unavailable|unavailable / unavailable|
| Ada external Core X PSU |35–73|299.32|294.27|300|percent unavailable here / RPM unavailable|unavailable / unavailable|

Three Blackwells on the user-declared2200W workstation PSU: highest same-sample power.draw subtotal **1335.53W at01:41:44.186740**; Ada separately **294.27W**. All-four diagnostic1629.80W is not workstation PSU load. The report's separate instantaneous-field subtotal1388.92W at01:41:39.186155 is a distinct measurement (`RESULTS.md:90–96`), not summed independent peaks. GPU readings do not measure CPU, wall/PSU power or headroom/transients; those sensors were unavailable. Clock-event flags are not clock frequencies; driver never sampled actual clocks. Before/after XML may contain thresholds but is absent here. Do not substitute typical hardware values.

Individual hw_slowdown, hw_thermal_slowdown, hw_power_brake_slowdown and sw_thermal_slowdown: **zero active samples on all four** in compact results. sw_power_cap: Flash0/Qwen0 53/Server0/Ada52. The analyzer compares aggregate `clocks_event_reasons.active` with literal `Active` (`driver/analyze.py:22`); its aggregate zero is not a valid bitmask interpretation. Cite individual flags. **85C was the conservative test guard; these records do not prove hardware thermal throttling/overheating.** No claims about unsampled intervals.

Fan03 barrier01:41:02.180099, Server cutoff01:41:51.187347 after49.007248s; Qwen0 reached85C later during cancellation.74 samples, maximum gap1.00313s; client intersection48.089593s, zero completed requests, no Flash advancing native progress proof, no five-minute qualification (`RESULTS.json:205–248`, `RESULTS.md:48–66`). Host available minimum564.832GiB; no owned swap/recorded OOM increments or host swap IO. Server starting36C is reported; min temperatures above must not be relabeled as all starting temperatures. Exact per-card barrier temperature/fan/clock series and ambient are unavailable here.

Compare only the same early interval against fan03, then separately report longer sustained behavior if reached. Different user fan adjustments, starting/ambient/inlet temperatures, reboot/cache/warmup state and possible Flash1M retained allocation confound a pure ECC comparison. ECC temperature/performance effect remains a hypothesis, not an established Blackwell measurement. Native progress, client timing, GPU/CPU activity and actual kernel overlap are distinct evidence.

## Source/receipt hashes and review handoff

All relative paths below are in this pinned repo. Local SHA256 hashes are also machine-readable in STATUS.json.

```text
841e7968e89504fd4f03210476423a49e2145c9d2b7cc4d7d32fc65a780405b8  scripts/runtime/flash/file_auth.py
030037024701cacf1f0accff8edb273cd7d1c290df53f87077fb740aec38638b  scripts/runtime/flash/idle.py
31273f8be764a526f62da55e0038b87cb90fef7b05468de184e840ca4d6eec55  scripts/runtime/flash/tokenize_adapter.py
d4a628876b8643a01277039ab744e87a2218e3b87e2c6207e2d67816b570a4b1  scripts/runtime/flash/owner.py
f92c8eef83fe4367cf8f74808aecfcbb0fca905cb5afb9e3afc09cef8576bc7e  scripts/runtime/flash/llm-frontier-flash.service
dbcbb86cfaf9559afd8584c2dbd1ba1602d937c1a05d3e9870e541c686fa04a7  reports/h011-fourway-20260927/attempt03/driver/job-body.py
f0e1b7d38c927cefe7a6c68d262903934ab5235abf57bfc86df2b13db8f98631  reports/h011-fourway-20260927/attempt03/driver/vm-common.py
3ba9eb85879fd0603da880fce2cf25a43dc1ed1e490dca278b948daa8b26738c  reports/h011-fourway-20260927/attempt03/driver/dispatch.py
ec9b6e4a3e92ff6da0103e6509451013ffad1f6fd1c34a73fe482cb90c028c25  reports/h011-fourway-20260927/attempt03/RESULTS.json
d6d602a482befed5e52372fe62bb0512f4b818f5fce58f262fd477d7895bcbea  reports/h011-fourway-20260927/attempt03/FIXTURE-COUNTS-HASHES.json
```

 Raw identities are recorded in `attempt03/RAW-HASHES.json:133–155,193–200` under the VM log directory above; actual raw contents were not available for revalidation:

| Preserved artifact | SHA256 |
|---|---|
| H011-FOURWAY03-job.py |3f365054dece103571c59b00e756bc25087e38d7447b76d9af5edc766a0521e8|
| H011-FOURWAY03-telemetry.jsonl |410c2bb545f9859469750455356b8a349c67a8902ec18b3cb275fd8f3660b4f3|
| H011-FOURWAY03.json |bd4b7d74fd23975cbe539c2a8a741645a818c849880d6138a5e67b0ae71f1b31|

Offline validation completed: exact attempt02 manual reconstruction/hash and syntax; retained-success positive/negative predicate checks (RUNNING, failed semantics, incomplete stream, length finish, resource/identity failure refused); existing seven-case mount identity regression PASS; proposed three-file replacement uniqueness/syntax and candidate-bound arithmetic checked. No runtime source was changed and no broad test suite/build was run. Worker1 implementation should test boundary counts, unchanged containment, manifest refusal on partial source, current/pending ECC matrix, and Sova allowlist/count mismatch/managed-agent migration before root exact review and deployment. None of these offline checks establish live reboot or inference acceptance.

Root's next gate is concrete H012 terminal evidence, then exact implementation/package review. Worker1 owns guarded promotion/ECC/reboot/repeat and preserves new off-VM receipts; root owns result publication and eventual Sova release after capacity agreement. This session finishes without waiting for1M or Worker1.
