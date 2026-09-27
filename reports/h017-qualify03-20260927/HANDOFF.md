# H017 QUALIFY03 — swap repair installed; corrected ordinary load independent

Latest actual observation: **20:04:50 UTC, LOADING**, same healthy identity and
fresh ordinary guard at the short-source staging boundary. No inference has
been dispatched. This paid task closes early while the independent load runs.
Do not restart it, alter its bounds, restore GLM or dispatch another load.

Corrected ordinary `llm-frontier-mimo.service` started19:58:45 UTC; native started
19:58:46.550187738Z. Unit PID1540308/invocation6e0c4561cfdf4ecd83a373ce2aa4b7d5;
native PID1541651/container624bd1f5bb049adc8ead5205ff0f2446d4c61c6701b551871ee4fc42ab3deb8f;
launchb08bc770f6244655a803ec1ba835813f. Selection generation6 binds manifest
83daa3e66924a8f945c168dfe9e0856c8c518196908335e029708eb46c0636eb.
Ordinary load retains its1800s budget, approximately20:28:47UTC, plus ordinary
settlement behavior; CLI closure/cap does not terminate it. Global window21:07:11UTC.

## Failure evidence and authorized repair

The required first read ran once at19:51:21 and immediately wrote ROOT-NOTICE.json.
Initial ordinary launch failed19:44:02.513799 on `added_host_swap` while LOADING.
Separate settlement `command_timeout` was preserved; final stateSETTLED,
request_holdfalse, proxy_startedfalse, PID/cgroup/GPU compute released.
`ROOT-NOTICE-INITIAL-FAILURE.json` preserves this initial notice.

The19:55:37 bounded diagnostic reconfirmed exact physical settlement. Startup and
last-good aggregate swap used102236160B; current103022592B, a786432B/768KiB increase.
SwapTotal remained3157258240B. The19:43:57 last-good owned cgroup swap.current0,
swap.max0, OOM0; hostMemAvailable700038922240B (about652GiB). Current available
reserve97.053%, memory PSI some/full averages10/60/300 all0.00; current cumulative
pswpin7487/pswpout29244 have no retained event baseline. The exact failing numeric
sample was NOT persisted. Do not invent its byte delta, pressure values or process
attribution. Configuration prohibited native swap; retained evidence is consistent
with minor nonowned aggregate variation, not proof of which process caused it.

Root directly authorized the narrow repair and ONE corrected load after these
facts. Aggregate used-swap movement is now a diagnostic in the normal sample;
SwapTotal identity, own swap.current==0/swap.max==0, cgroup OOM0, host15%, GPU7%,
temperature85C/lower, hardware latch, storage, source/identity and deadlines remain
unchanged. Future validation failures retain the cheap numeric host/baseline/
cgroup sample in the failure receipt. No kernel/swappiness/swap configuration
change. Owner SHA2566b9e409b4f32eb7b05af35c0d1ceeda533daa439f6abe4eab65847321bc1e04f.
ROOT-SWAP-REPAIR.json and SWAP-REPAIR.patch were emitted before staging.

Protected archive `/data/build/H017-20260927/worker1-qualify03/archive` retains exact
old raw manifest/state/selection/guard/source, original GLM config/state/owner,
old db4e93c1 inspect/stdout/stderr and unit journal. Canonical lease and registered
storage/root guards passed. Only the exact stopped db4e93c1 container was removed;
only owner source and its manifest pin changed; selection advanced genuinely5to6.
The staging lease was released before fresh legitimate hardware-latchfalse proof
(age3583ms) and the one ordinary systemd start. Qwen0/Qwen1/image identities,
readiness and idle scheduler observations passed; GLM stayed settled. No Sova work.

## Short qualification prepared, not dispatched

Dedicated source: `scripts/h017/qualify03/client.py` and `h017-qualify03.service`.
Remote source/config only at `/data/build/H017-20260927/worker1-qualify03/short`;
log root `/data/logs/H017-20260927/worker1-qualify03-short`. Unit is NOT installed,
linked, enabled or dispatched. ROOT-SHORT-PREPARED.json gives every source pin.
Client36c2fb38e75959be9f6cf996dd8282e5beca68c0cda00a63c06cc9de9bba0ccf;
authority9325c1d26cfae43b8b01ccf008c06108f327305f33af749de0a6b445c09a82e3.

It reuses already staged immutable H016 transportefbd8a3f/reader3adf8f43 and R9
fixture/helpers. One tiny READY text(max32), then unchanged authentic full17
strict:false/nested schemas, real task-only read(path), actual toolresult and
continuation, each full17 turn requesting65536 ceiling with naturally short answer.
Native count==usage, terminal finish/usage/DONE/fullHTTPdrain, first/last/raw/body
receipts and exact proxy disposition are preserved. Actual own completion clears
only its own may-active flag before global slot checks; slots do not claim GPUidle.
Unambiguous local BUSY never stops the model. An ambiguous actually submitted
request invokes exact existing ordinary-owner settlement; no restart/retry.

Preflight requires actual ordinaryRUNNING, same complete identity/source,
fresh healthy guard, native/privateprops+slots usable950000, idle slot and unused
proxy lane, canonical MiMo row fresh/ready/unlatched, no node actions, and independent
systemd ownership. No generation can occur while merelyLOADING. Single-attempt
client15min active cap; admission closes20:20UTC, hard end20:35UTC. No deadline of
a running client may be hotpatched. Server load retains its separate cap.

Mechanical next actions, each one bounded call, no paid polling:

1. `python3 /Users/agent/CodexProjects/llm-orchestration/tasks/H017-QUALIFY-03-20260927/READ-STATUS.py`
   saves private exact state/guard/log/native/proxy/capacity/node evidence plus
   ROOT-READ-STATUS.json. If merely loading, close; if actual failure, preserve
   primary and settlement and report without another load.
2. Only after actual ready gates pass, the already-authorized one job:
   `python3 /Users/agent/CodexProjects/llm-orchestration/tasks/H017-QUALIFY-03-20260927/DISPATCH-SHORT.py dispatch`
   repeats gates, links the exact unit and starts once. ROOT-SHORT-DISPATCH.json
   records actual unit/PID plus available body/first-output progress. Durable
   reader files continue independently; do not own inference in a foreground CLI.
3. At a meaningful short terminal event, one read:
   `python3 /Users/agent/CodexProjects/llm-orchestration/tasks/H017-QUALIFY-03-20260927/COLLECT-SHORT.py`
   saves private full receipts and immediately emits ROOT-QUALIFICATION.json.
   On actualPASS_KEEP_WARM, QUALIFICATION.json is byte-exact original full17
   receipt with its hash. Send to root/W2 before formatting. Historical R9
   usable1M/occupied16384/static pins remain distinct. No fresh950K allocation,
   short/native17, current benchmark or Sova acceptance is claimed yet.

W2 owns minimal truthful950K overlay and actual Sova acceptance. LAST remains
inactive and uninstalled/unstaged/undispatched in its H017 namespace, pending
actual SovaPASS plus root LASTGO. The only LAST change is local unit journal
stdout/stderr; client87b024ce and reader3adf8f43 remain byte-identical. Unit hash
cccc5bfbfe44b2c1a96fec205dee5421e35fb7c9914db8516c64a80f08e815e7; closure refreshed.
The historical LIVE02 LAST-GO template is historical, not a current dispatch file.

## Verification and delivery

Owner focused checks:37PASS/1SKIP(total38); skip is the explicit private R9 replay
fixture already archived, not a new model test. LAST focused30PASS. Short client
admission/exact-settlement/secrecy7PASS. Helpers syntax checked; no Linux short
unit execution or live inference acceptance claimed. No broad test sweep.
Raw evidence remains in task-private files and protected remote archive; repository
reports contain sanitized status and hashes. Source commit/bundle/hash are in the
final local PACKAGE.json. No git push, subagents, model downloads or other experiments.
