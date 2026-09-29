# H029 CORE01 — control refresh and current Qwen admission

Control/readiness source fixes are deployed; native model recovery and application
acceptance are reported separately. No inference was submitted by this worker.
Native Worker1 session `01a0eac7-732c-7f92-8ece-6c85cf74950f`, exact base
`f6ffc43cf9b18348361ee6f70647780fa7ab9f89`. Start 2026-09-29 01:28:54 UTC;
checkpoint 02:18:54, hard deadline 02:23:54 UTC. No subagents or extra CLI sessions.

Control refresh collects slow manager/readiness/catalog observations outside the
canonical lifecycle lease. It brackets collection with boot/mount, state, owner,
generation, pending-create, source/profile/receipt and native-runtime anchors,
then rechecks under nonblocking canonical ownership before reconciliation.
Publication has a one-second external-call budget; filesystem/kernel latency is
not a hard realtime guarantee. The journal reuses the checked manager and keeps
its existing anchored writer. Successful reads reuse that candidate; starts and
stops retain their original complete lifecycle serialization. Recovery masking,
unknown/write failures and historical interrupted receipts remain fail closed.
The H024 original lock holder/cause remains unproved; this repairs the separately
demonstrated slow-refresh contention mechanism.

Qwen diagnostics add static predicate codes, per-stage timing and existing
request-owner correlation across lane admission and native count. The current
log is private, bounded to 64 KiB plus one rotation, and projects only approved
metadata. No prompt, model output, key, raw exception or runtime identity enters
it. Existing Responses observer shape stays unchanged. A failed lane is recorded
without removing a healthy lane. Strict receipt/boot/runtime/generation/freshness,
hardware and native capacity checks remain; 480K context and ordinary 65536 output
are unchanged. Ada200K routing is excluded; MiniMax stays default.

At initial live preflight, boot `992bf979-efae-495b-9ab2-26e75ed5c5d0` had Ada200K
ready, both 480K Qwens stopped and no current Qwen operation. Package admission
passed after a preserved initial LeaseBusy refusal. Both owner slot preflights
then refused `concurrent_acceptance_identity_mismatch`: the current control
closure differs from its accepted receipt only in the already-reviewed H028
private-network and hardware-policy files. No start or inference was dispatched.
Additional read-only inventory found four H028 node leaves updated only in the
node copy; the proposed reviewed source-only receipt successor reconciles all
three owner copies while preserving model/runtime/capacity evidence and history.

Validation: 124 finite Python tests and 33 selected TypeScript tests pass;
TypeScript typecheck passes. New fixtures cover blocked collection leaving a
guard lease available, identity/CAS changes, expired/unknown proof, write failure,
unchanged generation, unrelated directory churn, source ABA, recovery masking,
static safe reasons and healthy-lane survival. Initial fixture failures remain
in private task output. These results are not live Codex or Qwen qualification.

The root-reviewed first deployment at 01:51:02 UTC unified the three installed
source copies and replaced only source_sha256/reviewed_source_commit in the
acceptance receipt; all other receipt fields remain exact. Protected backups
are under /data/backups/H029-CORE01-acc99d37. Control/node restarted; Ada remained
on its original 23:44:51 service start. The first refresh failed closed before
publication because Docker reordered otherwise identical Mounts entries. That
failure is retained. A focused correction canonicalizes complete mount entries,
preserving multiplicity and rejecting missing/non-list/non-dictionary shape.
Source/Destination/RW/content changes still invalidate the observation. The
corrected adapter passes 36 affected refresh/production fixtures. A second,
separate Ada coexistence correction is described below.

The corrected adapter `127f1e71...` was applied at 01:57:07 UTC with source-only
receipt successor `7ead1d1f...`. The first successful status took 0.924258 s and
both lane generations were current. Kernel sampling saw 0.139085 s of canonical
ownership; its release edge was censored, so this is an observed lower bound,
not a complete hold duration. No latency/freshness timeout was relaxed.

The next actual owner preflight exposed `untrusted_concurrent_peer` in both
slots. `Manager.conflict_check` routed the sole resident dedicated Ada through
the image-only validator. The narrow follow-up adds only that exact named Ada
peer: it reuses H028's pinned inert pure validator, checks disjoint UUID,
protected source/config/state, current boot and reinspection of native
PID/StartedAt/launch/mount identity. Unknown peers stay refused; Ada receives no
harness route or lifecycle change. Eighteen affected image/Ada peer fixtures
pass, including source/owner/native/boot drift and unknown-consumer refusal.


The peer correction was approved and deployed at 02:05:43 UTC. Exact installed
source is ccd0eb7bc2f4ce4385b15f1421c2dcbdae25fe4d; adapter 127f1e71 and
manager a6c39140. All 82 source-closure files match across control, node and the
registered release. Across all three preserved predecessors, every receipt
field except source/reviewed revision and every instance field except the
receipt reference remains unchanged. Current canonical receipt digest is
4435c20b4a1fc4efc327f8608a2f9f3a88242d95bad85f4c7c0a8d6c944ae9ce;
raw-file SHA256 is 4413086d2cb486501225cd4adac34ad7ee914a8c7a998b330d2f908e2aab29d7.

Both actual owner preflights passed. Qwen0 normal start was accepted as
f70b723200954ad7826269e2fa2d2e74 at 02:07:09UTC and succeeded at 02:08:33UTC,
reporting ready at control generation 57. Qwen1's serialized normal start was
accepted at 02:09:21UTC as 6252154567174f6db786b5902a53d6d3. Neither start was
replayed. These are owner lifecycle operations, not inference qualifications.


Qwen1 succeeded at 02:11:03 UTC, ready at control generation 53. The final
02:12 UTC handoff confirms both native endpoints ready with 480000 configured
and allocated tokens, one running-request slot, unchanged nonthinking/template
parser/runtime policy, fresh node observations and false Qwen hardware latches.
Both lifecycle operations are settled and persisted. Ada remains ready at 200000
with its original container ID and StartedAt; no Ada restart occurred.

The necessary final warm status read took 9.086261 s. Actual canonical ownership
was sampled at 2 ms intervals as one complete, uncensored 0.039714 s span. This was
an unchanged-state refresh, so it does not claim a measured durable-write bound;
the earlier cold-write observation remains explicitly censored. The long slow
collection now occurs outside the shared lease. This is one bounded readiness
measurement, not a benchmark or hard realtime guarantee.

The branch remains incomplete for full Codex qualification. Worker2 owns the
combined harness activation and actual tool/follow-up/replay acceptance; Worker1
submitted zero inference requests. MiMo/image/frontier were not started. No
model/engine/driver, power/fan/ECC, capacity policy, history, hold or quarantine
was changed. Root owns publication and any later task; no worker GitHub push.

Evidence chronology: `activation.json` includes earlier source-transition,
preflight and start-acceptance snapshots. Its nested `laneReadiness` value and
earlier container states describe those historical steps. Use `finalWarmRefresh`
and `ready-handoff.json`'s top-level slots/native/services for final readiness;
the receipt metadata itself is source evidence, not a live readiness claim.
CORE01 exited successfully at 02:14:51 UTC, before its hard deadline.
