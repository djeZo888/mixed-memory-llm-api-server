# H039 technical retention acceptance

H040 adds a [separately gated collector/controller contract](h040-interoperability.md),
disabled one-cycle stage and schema-v2 dimension report. The 72-fact corpus and
exact scorer expectations below are retained. The new full native profile also
requires cold resume after the latest independently accepted continuation;
the historical 37-call synthetic flow cannot qualify that dimension.

Source preparation only. Native acceptance, model fidelity, operational rollback,
automatic triggering and deployment are **NOT_TESTED**. No model connection is
included. The checked-in controller configuration is disabled. Task E owns the
separate `native-adapter/` subtree; it is not part of task B's implementation.

The synthetic Kestrel Pump Monitor conversation introduces 56, 64 and 72 active
facts over three small cycles. Critical totals are 49, 56 and 62; noncritical
totals are 7, 8 and 10. Corrections change pin maps, resistances, voltages, rates,
timers and HTTP interfaces. Some values intentionally return to earlier values.
Original and superseded records remain present. Untrusted vendor instructions
cannot grant permissions. Missing electrical, bench, site and resume checks must
remain unfinished.

`fixtures/ground-truth.json` is an authored synthetic answer key for the scorer.
It is not a model input. The fixture is safe to review in Git; actual model
answers, captured provider requests, native histories and private technical
conversations belong only in private task output. **Do not mount this repository
or the prepared packet in a model workspace.** A directory name or mode 0600 does
not isolate processes with the same user ID. The native launcher must enforce
the reviewed filesystem and tool scope.

From the repository root, using Node 24 without installing dependencies:

```sh
node --test --test-reporter=tap ai-harness/server/test/h039-compaction-retention.test.ts
node ai-harness/acceptance/compaction/controller.mjs plan
node ai-harness/acceptance/compaction/controller.mjs prepare ../output/NEW-private-packet
node ai-harness/acceptance/compaction/controller.mjs score summary-only 3 /private/answer.json /private/trace.json
node ai-harness/acceptance/compaction/controller.mjs validate-record /private/record.json
```

`prepare` creates a new exclusive private directory outside this checkout,
including through symlinks, with directories 0700 and files 0600. The answer key
goes to `scorer-private`; original records go to `source-steward`. `model-input`
contains separate transport requests, not a filesystem bundle for the model.
Only the current conversation delta enters the original thread. Recall requests
enter isolated probes. The summary probe gets no delta directory, answer key,
original-record file, tools or network. A duplicate output path is rejected.

The scorer accepts structured JSON only. Every fact value uses exact strings,
including units, spelling, pin numbers, negation and authorization states. Extra
prose and unknown fields fail. Both critical and noncritical coverage are
reported; this initial suite conservatively requires complete coverage. No model
judge is used. Continuation produces a real policy artifact and independent
engineering calculations; its numerical tolerance is 1e-9 SI units. Changing
JSON property order is harmless. Changing a unit, pin, permission or test status
is not.

Each cycle separates:

1. Summary-only recall from a qualified compacted checkpoint, without tools or
   answer-bearing files. Actual first-request bytes, independently derived input
   hashes, effective launcher scope and unchanged parent state are required.
2. Durable recall from a separate qualified projection of the same checkpoint.
   Exact schema/range/manifest identifiers are deliberately held out from this
   probe branch. Original-source reads must have observed call IDs, scope and
   exact content hashes. Current citations must match the latest corrections.
   This projection tests retrieval; it is not a replacement for the ordinary
   summary-only quality measurement.
3. Continuation in the original thread, with neither probe's answers appended.
   It produces `sensor-policy.json` and `engineering-calculation.json` using the
   latest state. Fixture calculations are independently authored in the tests.

The H039 baseline cold resume is deliberately **before cycle-three continuation**, when the cycle
three compacted checkpoint is still current. It requires a real runner restart,
captured persisted history, unchanged checkpoint and no replay. Continuation is
then checked separately. H040 additionally verifies a real owned application
restart after the accepted continuation and unchanged captured artifacts.
The final child probe proves that a private sentinel
was actually recorded in the parent, checks a child-only nonce, and compares the
complete child first request to an independent minimal-brief manifest. Distinct
IDs or a child saying UNKNOWN do not prove clean inheritance by themselves.

`evidence.schema.json` is a reusable Draft 2020-12 schema-v2 record contract.
Archived version-one evidence retains its own source/hash domain. Metadata
absence carries a reason; counts and durations are measured or explicitly null.
Compaction and probe/continuation/resume observations have separate identities,
counts and durations. Usage absence alone does not invalidate a settled result.
Native PASS also requires pinned runtime/model/tokenizer identity, manual action
attribution, correct per-cycle denominators, bound distinct probe identities,
captured request/scope proofs, retained originals and settlement. Schema
validation alone proves no external event occurred.

Action IDs satisfy production `requireId` limits. The verifier extracts summary
messages from exact owned native compacted-record bytes, normalizes typed native
Responses input itself, and binds instructions, remaining request fields and
full tool definitions to an independently frozen envelope. An adapter cannot
supply an independent summary or manufacture normalized "wire bytes" as native
evidence.

Synthetic fault records cover empty/truncated/invalid summaries, timeout,
cancellation, process death, duplicate action, restart, absent usage, full-input
admission boundaries and unattributed automatic triggering. They verify recorder
and controller behavior. They do not fault-inject the pinned native binary or
prove native cleanup, transactional rollback, admission or deployment safety.

The [adapter contract](native-controller-contract.md) describes later reviewed
execution. The [memory/retrieval proposal](state-and-retrieval.md) names the
smallest changes needed from other owners. B does not implement those changes
and does not wait for the native-adapter task.

Summary projection uses only the selected native `compacted.payload.message`,
never `replacement_history`. Full persisted-state hashes are separate from the
selected record hash and must bind the independent pre-operation baseline,
latest surviving post-baseline record and actual settled turn/window. Parent
immutability and cold resume check full state so appended answers/replays fail.
