# H035 IMAGE-INTENT02 — current request and saved image provenance

Source **2a7978f503da9c2ff049baa0c99f5e138840325e**, based on
**d0d4543e8fe8862f08d4186cb0734efba0ef854e**. This is a source/local-test
correction. No deployment or new live workflow was performed by this task.

The failed retained run `cfe55e79-cea8-4282-ae5b-d8543a8980ab` in session
`392b6bcf-7842-4748-a856-95456634a4de` returned a final-only promise to delegate.
The exact captured provider request `d00de01f-9904-46e2-932b-90da53054018`
contained the original current request and installed tool declarations, followed
by an app-owned status block listing two completed jobs from prior runs.
The block lacked an explicit current-run binding. The model's answer referred
to that snapshot and the old edit; it did not execute the requested delegation.

Independent offline comparison found zero provider tool-call deltas,
`finish_reason=stop`, and 60 completion tokens. Responses returned one completed
assistant message; native and app history contain that same final text. There
is no observed emitted tool/child intent lost in transport, and no adapter fix
is claimed. All 142 captured files and 132 boundary records passed size/hash
verification. Archived rows contain zero image jobs for this run. These are
observations of supplied captures, not a new live-state readback.

Snapshot influence is visible, but unique causality is unproven. The original
request also explicitly constrained retention of existing job identity. The
historical completed edit remains valid for its own original request; that
alone cannot prove execution of a different transformation or fresh delegation.
Raw prompts, responses, native histories and captures remain outside Git.

## Change and attribution

The prior context seam originated in H035 IMAGE-HANDOFF01 commit
`dbcd579f8b5ee91ff86c4035bfe643d51e8cd3d1`. This task changes only its
`broker.ts`, `app.ts`, and `image-broker.ts` production paths:

- Pass the exact dispatch run ID into saved image context and label each job's
  originating run and mechanical current/prior-run relationship.
- Order prior handoff, saved job status, then the clearly delimited current
  request. Preserve original request, selected-reference text and history.
- State that saved completion applies to that job. Status/continuation keeps
  the exact existing ID without resubmission; a new run ID does not imply a
  new image operation. External approval releases the native turn.

There is no intent classifier, automatic image submission, hidden job, history
rewrite, new tool result, or skills/catalog/tool-policy change. Root reviewed
the production diff at 20:34 UTC with no source blocker.

## Focused evidence and limits

Five selected offline tests passed: three new app/broker/context regressions
plus two existing late-result/restart and historical-immutability checks.
They use an in-process app, fake engine/backend and local temporary files;
no listener, network request, model, or real image service is used. Assertions
cover exact request/reference ordering, completed and approval-pending
provenance, status/continuation identity, no automatic execution, session
isolation, preserved handoff/history and unchanged late-result ownership.
Server build and focused test TypeScript validation passed with reused locked
dependencies. No broad suite was rerun.

Initial fixture upload/artifact and regenerated-reference-path mistakes, plus
two test typing errors, were corrected; their failed receipts are retained.
Production source did not change during those fixture corrections. A local
audit-helper null-field parsing mistake was corrected before its final audit.
Deterministic checks do not prove future model compliance. W2 owns the unchanged
live retry after root review; this task does not claim live success, full image
qualification, or repair of the historical final answer.

The [safe results record](h035-image-intent02-results.json) pins source, trace
hashes and focused receipts. Source bundle prerequisite is exactly `d0d4543`;
report-only export follows separately. Wrapper records the actual native exit
after this session ends.
