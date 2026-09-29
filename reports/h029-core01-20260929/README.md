# H029 CORE01 — control refresh and current Qwen admission

Source repair and deterministic fixtures; deployment/live acceptance are separate.
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
