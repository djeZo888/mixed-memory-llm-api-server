# H033 PERF01 — Qwen count verification

Source-only change against `aec3d5964c4abd412872f496d03a397f8612dc57`.
No VM contact, deployment, inference or GitHub push occurred in this task.

Production counting now uses one verifier-owned operation bracket:
`control + node → native → tokenize → native → control + node`.
A successful count requires the same boot, active identity, control generation
and service generation on both sides. Both native capacity/profile checks remain.
Every control/node predicate still runs, including selection, storage, owner
readiness, protected source policy and hardware latch checks. Proofs expire at
15 seconds; reported node/service ages also advance during metadata collection.
Tokenize keeps its 15-second timeout; control reads retain their 30-second bound.
Caller cancellation reaches the bracket reads and prevents publishing a result.
No cached health, retries, shared mutable probe context or deadline was added.

Only `codex-production.ts` and `codex-qwen.ts` change executable source.
The existing main/host composition passes the callable verifier, including its
optional bracket method, directly to the counter. Ordinary two-lane admission
still performs four control/four node/two native reads; counting now performs
two control/two node/two native reads, compared with four/four/two previously.
Custom verifiers without the method keep the existing double-verification path.
The token body is unchanged except for the existing removal of stream fields.

Final validation: **40 focused tests passed**, zero failed/cancelled/skipped.
Targeted strict TypeScript no-emit checking passed for both changed source files
and both new test files. Coverage includes actual factory→host→counter wiring,
exact body forwarding, call order/counts, schema 1/2, restart/generation changes,
selection/storage/owner/hardware/native drift on both sides, stale proof and
collection expiry, operation/probe errors, timeout/cancellation and concurrent
request isolation. These are local fixtures, not live deployment acceptance.

For the same 13-request schedule from H032, the call-count arithmetic would be
104→78 control GETs (count-only: 52→26). This is a source/fixture-derived reduction;
no live latency reduction or completed workflow improvement is claimed. The
remaining expensive control collection and ordinary admission are unchanged.

Activation belongs to W2 after exact root GO and an idle application gap.
Integrate this source with W2's reviewed changes, freeze the combined source and
compiled diff, and use a fresh app-only activation. PERF01 is expected to change
only `codex-production.js` and `codex-qwen.js` executable modules. Do not deploy
Python control/node sources, rewrite Qwen/MiMo receipts or replay a prior helper.
The running MiMo source closure intersects the rejected Python optimization;
this app-only packet avoids that lifecycle transition. Preserve current models,
profiles, histories, uncertain owners and quarantines. Root/W2 own any subsequent
small-workflow timing and acceptance evidence.
