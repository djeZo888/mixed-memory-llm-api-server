# H013 Worker2 — offline reboot/ECC review

Base/branch: `33c49020fa5d107006c1d7566f63f83033f3dbe0` / `worker2/h013-reboot-review`.
Scope: isolated mac-worker2 source/evidence review and bounded offline implementation only. Read AGENTS.md, ../PLAN.md and applicable source guidance. No ai-vm/ai-harness/Worker1 contact, inference, allocation, download, build, deployment, shared-checkout change or push. Sova remains paused by instruction; no current live state was observed. Root decides and coordinates; Worker1 alone performs later VM operations.

**Source candidate implemented; activation remains gated on concrete verified H012 PASS.** Use the existing boot owner/original production container and combine its first 1M start with the ONE authorized guest reboot. Preserve the private candidate, original 480K source/config/state and all scientific receipts. No owner redesign, Docker restart-policy change or new runner framework is needed. Failed/incomplete 1M is never promoted. This report is a proposal, not activation approval or live acceptance.

## Result and identity boundary

Latest local evidence is `reports/h012-flash1m-20260927/LAUNCH-RECEIPT.json:1–40`: **RUNNING_PREFILL_CONFIRMED at 02:37:00 UTC**, main sent 02:36:10, deadline 04:36:10; exactly 1,000,000 native input, pool 1,048,576, output <=1,024. No terminal result is available here; systemd `Result=success` on a running unit is not inference PASS.

Fresh unit `h012-manual1m-02.service`; stage `/data/services/h012-manual1m-02-20260927`; candidate `llm-frontier-flash-h012-manual1m-02`, port 30011, ID `5e4fd432cd86ddac3021f804facae4f5dbf710bcaf2873200e8834ec323977ea`, nonce `80f690e35a6849fe841efcc0957b9809`. Durable receipt base `/data/logs/flash-h008-20260926/H012-MANUAL1M-02`; preserve `-OWNER.json`, `.json`, fixture, stream/progress/telemetry, native logs, unit/container/boot/source identities and complete guard evidence off-VM before maintenance.

`reports/h011-worker2-20260927/manual/manual.py` is now the canonical **corrected** source, despite its historical directory name. Lines 97–101/183 canonicalize complete mount contents; 486–509 borrow/reset the outer lease. Applying exactly the five attempt02 identity substitutions in `reports/h012-flash1m-20260927/MOUNT-ORDER-FIX-AND-FRESH-IDENTITIES.patch:1–23` reproduced staged manual SHA256 **a661309ec32bde912f84395f8bb98fc0a9daca4ccf0c16d2cdfdb2f52c4f1560** offline. `REVIEW02.json:4–7` binds archive **180b0e9188fd41846ffe4e31d6c90aa4c973a9f9170663786ce482b871b408d5** and manifest **f5186cd4efdd0797c126b9c979c3055017aa8047dbb807e57c0aeca7cab1daa4**; `STAGE02.json:1` records deployed component hashes. Archive/deployed bytes were not fetched.

PASS requires `manual.py:84–91,424–449`: semantic PASS, transport complete, SSE DONE and body drained, finish reason `stop`, prompt usage exactly 1,000,000, completion 1–1,024 and consistent total, no resource failure, exact identities/capacity, settled writers and durable terminal owner `PASSED_RETAINED_PENDING_PRODUCTION_PROMOTION`. A retained-success evidence-write quarantine (`:450–458`) needs root reconciliation, not inferred PASS. Failure cleanup (`:282–314,459–478`) confirms exact candidate stop/cgroup settlement before original 480K recovery; unknown ownership stays quarantined.

The candidate is **not reboot durable**: `manual.py:442–445,546` explicitly records restart=no and original desired-running 480K restoration. Native scheduler 300s forward-progress watchdog remains distinct from the two-hour main deadline and 900s four-way job (`reports/h011-worker2-20260927/WATCHDOG-SOURCE-01.md:3–7`). Healthy chunked prefill advances the scheduler counter; do not extend any bound.

## Implemented source diff and root-reviewed promotion ordering

Exact offline replacements below are implemented; no activation or 1M qualification is claimed:

| Existing source and line | Old -> proposed |
|---|---|
| `scripts/runtime/flash/file_auth.py:17` | BOUNDS input `479993` -> `1048569`; input+reserved output `479998` -> `1048574` |
| same file `:128,137` | Both context/pool arguments `480000` -> `1048576`, and assertion likewise |
| `scripts/runtime/flash/tokenize_adapter.py:14` | `CONTEXT = 480000` -> `CONTEXT = 1048576` |
| `scripts/runtime/flash/idle.py:51` | Required context/pool `1048576`, max_req_len `1048575`, max_req_input_len `1048570` |

Keep loopback port 30010, launcher command, owner/container name, GPU UUID, image, weights revision `eb9eb208eb0d988989d07a6a12d0fdeb5f52574a`, auth, FP8 E4M3 cache, 64 CPU workers/eight NUMA pools/CPU0–71, radix disabled and 2048 prefill settings unchanged. The source arithmetic matches the qualified candidate's `manual/context_profile.py:18–30`; neither declared capacity nor this arithmetic establishes completed 1M occupancy.

1. Root reviews actual terminal H012 PASS/correctness/usage/guards; Worker1 archives original terminal receipts and raw evidence off-VM. An active request remains untouched. Failure/incompletion is never promoted; confirm exact-stop/original480K recovery through the unchanged H012 owner and preserve the result.
2. Stage reviewed production files, profile, source hashes and future Sova changes without starting production. Snapshot protected original source/config/state, original container inspect and boot-unit intent. Keep candidate loaded until the maintenance transition; preserve its stopped container/stage thereafter. Do not coallocate two650GiB budgets.
3. Under the canonical borrowed lease, before changing original production hashes, use attempt02 exact validation/stop semantics (`manual.py:211–225,282–294`): `stopped(c)==True`, PID0, neither restarting nor paused and empty captured cgroup. Write a separate H013 maintenance receipt: do not call the helper blindly because295–296 overwrite historical terminal PASS. Stop all owners preserving desired-running intent (`owner.py:126–134`; service resume/halt). No `restore` call that would reload480K.
4. While owners are stopped, install the reviewed source files through anchored writes and update exact protected manifest entries; verify all seven bytes/hash entries and root/storage guards. Keep the original bind-mounted source directory identity; do not silently swap its inode/symlink. An interrupted multi-file update must refuse startup, not treat mismatched bytes as accepted. Save exact old source/config rollback. Record UUID-mapped ECCcurrent/pending/counters, set pendingOFF only on3Blackwells, leaveAdaoff, and perform the ONE guest reboot. No pre-reboot production Flash allocation.
5. After new boot ID, verify actual ECCcurrent/pending Disabled on all4, registered storage and all pins, then authenticate native production30010 readiness, tokenizer context1048576, actual1M pool/allocation and short correctness before load repeat or eventual Sova resume. The existing enabled unit performs first production1M start; active systemd/Docker alone is insufficient. If boot/pool/correctness fails, remainpaused and report explicit failed acceptance; preserve rollback and candidate, never label480K as1M. Guest inability to apply ECC is a stop condition, not host reboot/reset authority. Historical manual status may reject new production hashes (`manual.py:118–133,223`); use archived H012 evidence and separate H013 readback, never rewrite old pins.

Implemented source supports the following; all remain deployment/actual-result gated before later Sova unpause:

- Preserved `configs/deployments/glm-5.3-flash-480000-fp8-kt.json` as rollback; added a separate `glm-5.3-flash-1048576-fp8-kt` declaration with launch context/pool and native bounds above, explicitly PENDING actualH012PASS/root review. This declaration alone does not launch anything.
- `scripts/control/node_observation.py:38–92,398–405,584–598` now binds exact seven-file protected source identities (historical480K or candidate1M), then publishes deployment/capacity only when authenticated `/get_server_info` agrees on context/pool/native input margin and a second source/container/boot identity read has the same non-null integer generation. Unknown/partial/mismatched readback publishes no capacity. It does not declare occupied-context qualification.
- `ai-harness/config/frontier.json:3` contextWindow1048576, **qualified=false**; `ai-harness/server/src/frontier.ts:27,197,289` add1048576 to type/allowlists. Keep native-count equality and margins7/2 (`:242,251–257`), output ceiling65536, revisions/auth unchanged.
- `ai-harness/deploy/engine/configure-profile.mjs:10` FRONTIER_CONTEXT ->1048576 updates provider limit at41 and managed frontier agent context at217. The managed-agent migration accepts only exact old SHA256 `ac773137a850439b9109bc22080071d46d60b8758ad9660d15981f7a7c761dfe`, rechecks protected ownership/modes/link/path/content and atomically replaces only agent.md; custom conflicts are rejected and histories/other files preserved. Leave Qwen default/pools480000. Only offline Sova source changed; no build, application mutation or contact. End-to-end advertised/native agreement remains a later release gate.

## ECC policy and exact matched repeat

Normal `scripts/runtime/flash/owner.py` and `scripts/lifecycle/hardware_policy.py` have no ECC-enabled policy predicate: **no production ECC source change or new policy framework was introduced**. `scripts/control/node_collectors.py:136–140` reports current ECC only. The explicit Enabled/Enabled check is historical H012 `manual.py:188–195`; leave that source and its receipts untouched. The new H013 operational policy requires the exact four UUID inventory below and **Disabled/Disabled current/pending** after reboot. Add this small assertion to existing pre/post identity capture (`attempt03/driver/job-body.py:53–73`) using `nvidia-smi --query-gpu=uuid,ecc.mode.current,ecc.mode.pending --format=csv,noheader,nounits`; unknown/missing/duplicate UUIDs or unsupported ECC readback refuse admission. Pending Disabled alone is not applied ECC. Preserve hardware-latch policy, cumulative/error evidence, and all other admission guards. Worker1 must reconcile actual installed policy/source hashes; local source is not deployed-state proof.

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

Three Blackwells on the user-declared2200W workstation PSU: highest same-sample power.draw subtotal **1335.53W at01:41:44.186740**; Ada separately **294.27W**. All-four diagnostic1629.80W is not workstation PSU load. The report's separate instantaneous-field subtotal1388.92W at01:41:39.186155 is a distinct measurement (`RESULTS.md:90–96`), not summed independent peaks. GPU readings do not measure CPU, wall/PSU power or headroom/transients; those sensors were unavailable. Fan percentages indicate intended setting, not RPM. NVML T.Limit is relative and cannot establish an absolute hardware threshold. Clock-event flags are not clock frequencies; driver never sampled actual clocks. Before/after XML may contain thresholds but is absent here. Do not substitute typical hardware values.

Individual hw_slowdown, hw_thermal_slowdown, hw_power_brake_slowdown and sw_thermal_slowdown: **zero active samples on all four** in compact results. sw_power_cap: Flash0/Qwen0 53/Server0/Ada52. The analyzer compares aggregate `clocks_event_reasons.active` with literal `Active` (`driver/analyze.py:22`); its aggregate zero is not a valid bitmask interpretation. Cite individual flags. **85C was the conservative test guard; these records do not prove hardware thermal throttling/overheating.** No claims about unsampled intervals.

Fan03 barrier01:41:02.180099, Server cutoff01:41:51.187347 after49.007248s; Qwen0 reached85C later during cancellation.74 samples, maximum gap1.00313s; client intersection48.089593s, zero completed requests, no Flash advancing native progress proof, no five-minute qualification (`RESULTS.json:205–248`, `RESULTS.md:48–66`). Host available minimum564.832GiB; no owned swap/recorded OOM increments or host swap IO. Server starting36C is reported; min temperatures above must not be relabeled as all starting temperatures. Exact per-card barrier temperature/fan/clock series and ambient are unavailable here.

Compare only the same early interval against fan03, then separately report longer sustained behavior if reached. Different user fan adjustments, starting/ambient/inlet temperatures, reboot/cache/warmup state and possible Flash1M retained allocation confound a pure ECC comparison. ECC temperature/performance effect remains a hypothesis, not an established Blackwell measurement. Native progress, client timing, GPU/CPU activity and actual kernel overlap are distinct evidence.

## Source/receipt hashes and review handoff

Paths are repo-relative. The table records immutable **baseline** hashes at the required base; current implementation hashes are separately recorded in STATUS.json.

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

## Changes and tests

Changed runtime3files, pending1Mdeployment, truthful node capacity observation, Sova config/allowlists/provider/exact-old managed-agent migration and focused tests. Historical H011/H012 runner/evidence/manifests, old480Kprofile, owner/boot service, native/runtime/model pins and fan03driver/limits remain byte-unchanged. No production ECC-on check existed, so ECC policy is the explicit H013 operational pre/post gate above.

- PASS: `python3 -B -m unittest tests.test_flash_tokenize_adapter tests.test_flash_1m_boundary` (12 tests), executing real admission middleware with local response/count/device stubs; exactP-7/P-2 boundaries, output65536/default/alias, native partial/old allocation refusal, pending profile/pin preservation.
- PASS: `python3 -B -m unittest tests.test_flash_capacity_observation tests.test_node_observation` (20 tests):1M/480Kactual pools, invalid/conflicting capacity, manifest/common-source drift, unknown/changed identity and no unconditional1Madvertisement.
- PASS: `node --test --test-name-pattern='frontier|custom main' ai-harness/deploy/engine/configure-profile.test.mjs` (4 tests): config/Qwen480K and exact-old/custom/mode/link migration boundaries.
- PASS: `ai-harness/server/test/frontier-contract.test.ts` (2 tests), Node24 native TypeScript transform with command-local `.js`→`.ts` import hook, mocked fetch only;1Mallowance, invalid capacities, pending qualification, native count identity, margins and65536output. Experimental transform warning only; no dependency install/build/network.
Server contract command (no HTTP; test mocks fetch):

```sh
node --experimental-transform-types --input-type=module <<'JS'
import { registerHooks } from 'node:module';
registerHooks({ resolve(s, c, next) {
  return next(s === '../src/frontier.js' || s === './errors.js' ? s.slice(0, -3) + '.ts' : s, c);
}});
await import('./ai-harness/server/test/frontier-contract.test.ts');
JS
```

- Existing `python3 -B -m unittest tests.test_flash_runtime` could not run:6errors from missing fastapi/zmq, no policy assertions reached. Narrow stdlib tests above cover changed runtime policy; full HTTP/native acceptance remains unverified. No dependencies installed.
- Exact attempt02 five-identity reconstruction/hash, existing seven-case mount regression and PASS predicate checks passed in initial review. Syntax/hash/whitespace checks passed; historical hashes checked against base.

Root owns exact source review and actual H012 terminal result gate. Worker1 alone stages/applies guarded changes, reboots once and performs the one bounded repeat. Sova stayspaused through failed/unknown acceptance; root alone coordinates eventual qualification publication/unpause. No waiting for1M or Worker1, no activation or push in this session.
