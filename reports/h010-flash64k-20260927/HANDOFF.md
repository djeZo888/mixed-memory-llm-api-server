# H010 Worker1 handoff

Primary occupied64K qualification is complete and passed. One varied8192 warmup
hit its128-output cap (correctness unproven); one fresh exact65536 request
returned150 tokens and stopped normally with all checks correct. No primary
retry or extra benchmark ran. [Results](RESULTS.md), [machine data](RESULTS.json),
[capacity estimate](CAPACITY.md).

Production context/actual pool480000, official FP8 model/runtime, eight NUMA
pools/64 guest expert threads, ECC policy, all four model containers and existing
Sova configuration were preserved. The source/guard/readiness check at23:48:25
passed. Primary unit `h010-flash64k-qualification` is inactive/MainPID0/success.
No request remains owned by Worker1. Socket/SSE observations are not an atomic
native-drain claim. [Clear primary handback](evidence/PRIMARY-HANDBACK.json).

Optional four-instance overlap was not established. The23:44 staging check
rejected before mutation/inference. Root explicitly authorized one corrected
23:49 window; Worker1 armed it at23:47:08, then stopped only the task timer at
23:48:02 under root's abort because Worker2 was not armed. Zero Flash smoke
requests ran; no third attempt is authorized. The primary evidence is unchanged.
Both owned units are inactive/MainPID0. No model unit was touched by the abort.
Worker2 owns its smoke outcomes and Sova restoration. Worker1 has not contacted
ai-harness and does not claim Sova running without Worker2's receipt.
[First failure](evidence/OVERLAP-NOT-RUN.json), [abort](evidence/OVERLAP-ABORT.json).

Task root on mac-worker1:
`/Users/agent/CodexProjects/llm-orchestration/tasks/H010-FLASH64K-20260926`.
Native session `01a0e007-15cf-7c42-af30-7711982abd06`, start23:22:35, effective
native hardend00:17:35 UTC from3300-second budget. Primary finished23:35:37,
well before independent request deadline00:41:20/global00:58 and unit01:02.
No continuation is needed for inference. Root whole budget ends01:16:45;
worker implementation/evidence closure01:06 remains unchanged.

Retain local tools/evidence/raw/events and all existing task artifacts. Raw13
primary files total2,124,205bytes in task `evidence/raw`, with matching protected
VM files under `/data/logs/flash-h008-20260926/H010-FLASH64K*`. Full native log,
analysis and analyzer remain task-side with hashes/pointers in RESULTS.json.
Do not replay dispatch. No models, runtime, weights, credentials, old watcher,
rollback or historical qualifications should be removed or changed.

Source checkpoint `a9d3034` and bundle `H010-SOURCE-a9d3034.bundle` are based on
`6772a77e9a8ecc37200509ec50f501be5fa48c11`. Root plan commit200661a is authority,
not the implementation base. Final report commit/bundle identity will be written
to task-root `FINAL-IDENTITY.json`; root alone owns publication/integration.
No Git push was performed. Ten offline stream/error/deadline checks, fixture
self-test, exact executed-job hash reconstruction and report/raw arithmetic
review passed. No additional VM benchmark or general test suite is needed.
