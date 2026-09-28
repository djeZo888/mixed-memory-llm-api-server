# H018 LIVE05 failed qualification and RECOVERY06 backend recovery

Original GLM is authenticated ready at **2026-09-28T01:19:41.037039Z** with
**1048576 context**, selected generation **11**, and its exact retained
container/image/source identity. Canonical GLM, Qwenx2 and image are fresh,
ready and unlatched; both Qwens retain 480000 context. The node remains
PID3309508, active/running/enabled with its original invocation. Qwenx2/image
container IDs, image IDs, PIDs and start times match the preserved baseline.
`ROOT-READY.json` is the backend handoff for W2's original Sova restoration;
this task does not claim that application restoration has completed.

This fresh bounded native session made one authenticated read through supported
`/v1/readiness`, `/v1/models`, `/get_server_info` and canonical node status.
The earlier `/health` and `/get_model_info` 404 responses were unsupported-route
responses. They did not establish model failure. No generation, model load,
restart, node change, manager reload, remote write or source deployment occurred
in RECOVERY06. The read helper and raw reply remain private in the task directory.

LIVE05 remains **FAILED / NOT QUALIFIED**. Actual 950000 configured/allocated
capacity and tiny text passed, with 14 input and 2 output tokens, terminal DONE,
full HTTP drain and authenticated native idle settlement. Tiny input processing
was 1.051045 seconds; output generation 0.147262 seconds; total 2.417055 seconds.
The full17 request was interrupted: its 9540 input tokens were counted/expected,
not proved processed. No native tool qualification receipt exists. Continuation
never started. Sova MiMo, current 4K/16K/64K and near950K were NOT TESTED.
LAST was NOT STARTED. Request completion remains **UNPROVEN**, despite proved
physical release; no uncertain request was replayed.

The primary failure was `lifecycle_busy` during `hardware_latch` at
01:00:16.138523Z; separate cleanup `command_timeout` followed at
01:00:25.163753Z. The holder at failure is **UNKNOWN**. At 01:10:54 the observed
holder was node PID3309508/FD7 on canonical inode1838. These are distinct facts.
At 01:11:35, exact MiMo native PID/cgroup/GPU/proxy release was proved under the
canonical lease. The failed state was archived mode0400 and explicitly
reconciled without claiming HTTP success. Normal GLM selection/start followed
at 01:14:12. The node did not need to be stopped.

The LAST helper's source was created at 01:01:22.512056Z, after both failures;
its completed remote retime receipt is 01:01:23.318082Z. Exact native event
boundaries and command hashes are retained in `SOURCE-REVIEW.md`. At 01:00:13
and 01:00:21 only local reads occurred. The completed inactive retime changed
only two admission constants from 01:25 to 01:30; the total eight-hour active
cap stayed unchanged. LAST authority remains inactive and supplies no authority
for this recovery session. Its 01:30 client source was already committed in
base093c6bd; this commit adds only the two inherited LIVE05 helper bodies and
compact recovery evidence. They are archived configuration-injected sources,
not standalone commands or authorization to execute them against restored GLM.

Raw source, request/stream traces and full results remain in the previous
LIVE05 task; `EVIDENCE-MAPPING.json` records paths and hashes. Upstream swap-fix
commit637b684 and its existing proof are reused, not retested. No periodic
hardware-proof fix or shared policy/owner edit is included. W2 owns independent
proposal/review of that issue, and its work is not deployed by this task.

Publication checks are limited to scoped source/evidence secret review and
Git diff/whitespace review. No new runtime or benchmark tests were authorized
or run. The bounded session ID, start and hard deadline are in `SESSION.json`;
its wrapper writes the actual exit only after the native session returns.
The review branch and bundle are local; no Git push was performed.
