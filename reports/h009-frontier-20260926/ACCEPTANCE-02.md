# H009 native code workflow acceptance

PASS, actual20:56:29.375863–21:11:41.573613UTC on2026-09-26. Native worker2
session01a0df78-5580-7ad1-bbfd-f552733ae48d began20:46:40UTC. Root accepted
semantic evidence. Production start remains separately gated by final Ada
reboot recovery; this report alone does not claim activation.

One Qwen parent delegated exactly once in foreground to the native frontier
child. Flash used native-default-auto with the actual full17tool schemas;
read edge.mjs/check.mjs using bash, patched onlyedge.mjs using write, then ran
nodecheck.mjs with paired EDGE_CHECK_PASS. Its useful final returned to the
same parent. Qwen independently read the final edit, ran nodecheck.mjs with
actual EDGE_CHECK_PASS and returned an accurate final preserving the task ID.
The driver also independently executed the checks. A separate Qwen request
returned323 in154ms while Flash was active (36input/4outputtokens).

| Flash request | Exact input | Reported output | Active to settled seconds |
|---|---:|---:|---:|
| Read fixture |11555|17|620.277|
| Patch file |11729|668|108.967|
| Run checks |12417|14|44.548|
| Child final |12439|49|49.335|

Outputs total748 from the native persisted token-usage table, matched by child
session/input/order; separate reported reasoning fields are0, which does not
establish absence of hidden reasoning. Each request had2048combined-output
ceiling. Durations include prefill and generation, not model decode throughput.
Full-roster count-only measured11367 and emitted no Flash generation; native
transport retried the deliberate count rejection, with all attempts rejected
before inference. No live overflow replay or second child was used.

Parent `mvs_c3300df8d35d4115a8ec07c6a79b0d01`; child
`mvs_d8df17f7b7304c11923d9537ee7f000a`; task
`bg_81661554-c232-4e6e-af8d-807b772d8980`. Paired tool IDs:
`call_440c096f0ffb4b7f8d321107`(read via bash),
`call_96b7dc10d6c743cd972ac895`(write),
`call_57d830d76a4c4d60bed8c9d2`(checks via bash).
Final code SHA c108dde27a7acf4efe5ec999078cbb6926df27c4b088cb38a1a0c54bf38fa761.

Supervisor exited0; broker/gateway/app normal close completed; both owned PIDs
and containers absent and8080/8081unbound. All4live Flash requests terminal
settled. No atomic backend active-counter/drain claim. App/search remained
stopped for Worker1 final Ada reboot. Production data was not used by the
isolated test;26sessions/133messages/62files and current regular files matched
retained stop/backup evidence at paired promotion.

Qualification is this code workflow with full exposed schemas, not every tool
behavior,480Koccupiedcontext, or new cancellation/reconnect/image tests. Qwen
remains default. Production context480000/output65536 unchanged; no hidden16K
cap. The native task wrapper reported model_verdict/file_change missing;
actual route, paired history, final file and independent checks establish the
model/tool/patch evidence. Child used separate write rather than the prompt's
suggested combined bash; the required useful workflow passed.

The original pre-app attempt failed on retained dependency permissions before
any app/native activity. Its runroot/job/log remain archived `.preapp-failed-02`.
Root authorized the corrected attempt after exact dependency mode repair and
actual app/gateway import checks; see [packaging correction](PACKAGING-02.md).
The [capture correction](CAPTURE-02.md) preserves durable boundaries while
avoiding per-token fsync. Driver/gate/image/source pins and compact actual
receipts are in ACCEPTANCE-02.json; private wire snapshots remain onai-harness.

Final deployment completed after Worker1 final recovery; see [deployment receipt](DEPLOYMENT-02.md). Private health/status200, canonical Flash/Qwensavailable, FullHD restored, current data/files preserved.
