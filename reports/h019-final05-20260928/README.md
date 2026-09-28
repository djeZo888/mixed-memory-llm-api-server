# H019 FINAL05 — independent near-950K request submitted

At 2026-09-28T03:39:04.724259Z the single final request was independently
running under `h019-final950k.service`, PID1553170, invocation
`09fe3630e9924732925eba78773e011e`. The request body was sent at
03:36:16.206379Z by the transport; the authenticated reader recorded BODY_SENT
at03:36:16.506071Z. Both timestamps are preserved separately.

Actual native input counting returned **948975**, output budget **1024** and
one reserved native slot token within the950000 context. The2581549-byte exact
request SHA256 is
`932c76632afed416c80b2107d59b51cc85bde00e46e212d89e66c4a87661f0df`.
The eight-hour client deadline is **2026-09-28T11:36:11.085467Z**, measured from
job preparation; systemd independently retains RuntimeMaxSec=8h. Admission was
before04:10:29Z. There was one dispatch, no64K request and no replay.

Authenticated loopback and private `/slots` GETs were fully drained and showed
slot0, native task654, `is_processing=true`,950000 context and matching request
seed/output/temperature. At collection, native counters were12288 prompt tokens
and10240 processed, zero cached. These are in-progress slot observations; they
do not establish completed948975-token occupancy. The exact948975 count comes
from the native count, client and request progress receipts. The private proxy
recorded one active request and no quarantine. Unit PID, cgroup and process
INVOCATION_ID were matched. Final correctness, terminal SSE/usage/DONE, complete
owned HTTP drain and authenticated native idle are **PENDING**.

## Identity and guards

MiMo remains selected at canonical generation12, launch
`b23d112359424d909862207e30f0c9d7`, boot
`6535a867-8e27-49d9-8a04-4ecc1adb1e32`. Supervisor605245/invocation
`930ba539af27423d9547e9e233d46e0d`, native605646/startticks7627770 and container
`aae59a6db7da41ff58056ce11e762060a6fe8aeecdad3d0e6813057573238d54`
match the qualified production instance. Image remains
`cdb6efd75f53a8b453f866f30511b0f5c8d19440d3adaaf419e97bde1c2bf21e`.
Manifest semantic SHA is
`d8bd9326118458774ac2b585e6029faa2a607d195001d85e14c5d238f6c05be4`;
raw SHA is`743edc0f8fa343f8c05efe7a307cf5a6eb4396b09ba9ed378230fe9d62e1e0a0`.

Fresh preflight verified115 pinned source entries, owner source preflight,
registered mounts, exact receipt bytes, actual native/container identity and both
idle slots before staging. All four same-boot hardware proofs were5.24s old or
less. The canonical lock remains device26/inode1838. No new model load or lock
observer was needed. No lifecycle lease spanned transfer, token counting,
inference or waits.

The03:39:00 owner guard was4.684s old at collection, statusok, no hardware latch.
Dedicated704GiB memory/zero-swap policy remains enforced; owned swap/OOM are0.
Host available reserve was40.709%; frontier free memory9979/97887MiB and43C.
Existing15%/7% reserve floors,85C-or-lower thermal bound and5s/15s guard bounds
are unchanged. No resource fault was observed. MiMo stays warm; no GLM rollback.

## Acceptance and narrow change

Root reviewed `scripts/h019/stage_acceptance.py`, SHA
`9aadda867bfacd8db5e6fea5683a5ecc6194a00f645ee3a220705b41cb96bc7d`.
The helper uses existing mounted/anchored protection and exclusive creation;
it never overwrites a candidate, authority, dispatch/client receipt or acceptance.
It wrote only `/data/build/H019-20260928/acceptance.json`, SHA
`380e30de3f5ffeaa356fc8d1430d8ecdb8a6349c19a8a3c615c462de65357390`.
No runtime/client/owner source was changed. Unchanged reviewed prepare_authority
and dispatch each executed once. Active authority SHA is
`70eacb03085d323fcbb2ba12346f526198eae7c3d99b008177f1f691bad37eb9`.

Only authentic final_native17 and production PASS receipts were used:

- `/data/logs/H019-20260928/worker1-short/FINAL17-QUALIFICATION.json`, SHA
  `a3e0d9ab4589d8f1a79b6154fda08be1b64fece1dcbaeb1876ef1e677ce4d923`.
- `/data/logs/H019-20260928/worker1-short/ALLOCATION.json`, SHA
  `290564ca19af632e118e536fff35699e928131d44c010391e23d0db5c0e7e184`.

**Sova application acceptance is FAILED**, separately recorded by root/W2
attempt02 SHA`8626c39036d3b65ab329ad04aca72feb195dc53f59ae4453d1f46aa95bee2324`.
Its original supervisor status`SETTLEMENT_UNKNOWN` remains historical evidence.
Root-reviewed current W2 settlement SHA
`4c88c7951600c45a1009e3dd64bedd8aa63bc49de49d4c921e9a194f0a7bacc0`
confirms app/acceptance units and owned engines quiet, zero active/uncertain
frontier requests, no more app inference. Independent current W1 native/proxy
idle proof resolved the current dispatch precondition. Retained app workspace
quarantine is separate from native/private proxy quarantine.
The unchanged authority/client generic`PENDING_NOT_TESTED_APP_PAUSED` field means
an absent Sova PASS proof; it does **not** replace the actual failed app result.
Sova remains paused. W1 performed no ai-harness operations.

## Verification, limitations and handoff

The staging helper passed Python syntax parsing, exact root SHA review,
exclusive-create execution and protected byte readback. Existing source closure,
receipt bindings and startup assertions passed. No native benchmark was repeated
and no extra model/runtime build, download, hashing or tuning occurred. Existing
Qwen/image owners were untouched; W2 passive readback reported them available.
There was no new active Qwen/image inference test.

Read-only collector corrections are retained privately: exact slot-object equality
was too strict because native returns additional diagnostics; owner protected()
has a2MiB bound below the actual2.58MB request; GuardedFile reads are chunked; and
active native prompt counters are separate from the exact pre-counted input.
Collectors were corrected without changing live guards or replaying a request.
All original receipts remain unchanged.

Private PREFLIGHT.json, DISPATCH.json, REQUEST-START.json, CHECKPOINT.json and
PACKAGE.json are beside this task's isolated repo. Raw request/SSE/authority and
ongoing evidence remain root-protected under `/data/logs/H019-20260928/worker1-final950k`
and `/data/build/H019-20260928/worker1-final950k`. No credential values were
included in Git. Automation remains paused and was not modified.

Native session`01a0e611-7787-73b2-907f-cde0fb705559` uses inherited CLI settings.
Session window03:31:39.465241–03:46:39.465241Z. Actual exit is written by the
wrapper after return; it is not invented here. After this startup snapshot W1
packages and exits without further VM polling. Root owns Git publication and
later result collection. No final benchmark success or main-merge acceptance
is claimed.
