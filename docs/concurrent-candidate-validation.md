# Closed candidate validation (source preparation)

`python3 -B -m benchmark.concurrent_validate` (with `PYTHONPATH=scripts`) is a
separate pre-acceptance campaign. It has no production receipt writer or
migration/start shortcut. Production `check_acceptance()` remains unchanged.
Exactly GLM480000/GPU0/96 CPUs/640GiB and Qwen700160/GPU1/16 CPUs/32GiB are
rendered from the pinned production declarations. No CLI capacity, argument,
resource or skip-validation override exists.

The manifests retain production weights, immutable images, aliases, native
ports30002/30004, cache paths, wrappers and defaults. Their explicit differences
are temporary names/ownership labels, campaign log/service paths, and a read-only
mount of the identical pair-wrapper bytes from protected staged source. The
new pair wrapper need not already be installed in production. The old installed
Manager remains the canonical singleton owner; candidate declaration modules
load under a private package and cannot replace it.

Future root dispatch (NOT authorized by this source handoff):

1. Review this source, benchmark outcome, original Qwen TP2 restoration and
   writer release. Freeze a new ordinary Worker1 session and current guard pins.
2. Run the bounded actual-image auth fixture as described in
   `tests/lifecycle/sglang38_fixture/PAIR-README.md`, under the existing lifecycle
   lease and registered-storage guards. Preserve exact cleanup evidence. Bind its
   actual protected registered-log path and raw SHA256 into GO; copy the receipt
   privately to Worker1 for content/source verification. Local tests do not
   create this proof.
3. `PYTHONPATH=scripts python3 -B -m benchmark.concurrent_validate prepare
   --task-dir "$TASK" --session-id "$PREP_SESSION"` creates only local review
   artifacts. Root fills `GO.template.json` with the canonical arm digest,
   reviewed source, actual-image proof, restored ownership handoff, fresh RUN
   session and dispatch epochs. The budget is at most1200seconds and includes
   load/warm/checks; PREP establishes no epoch. No assumption is made about load
   time fitting that budget.
4. `PYTHONPATH=scripts python3 -B -m benchmark.concurrent_validate run
   --task-dir "$TASK" --session-id "$RUN_SESSION" --go "$GO"` is the proposed
   live entrypoint, only after separate review/authorization. It stages through
   existing guarded writers, captures the idle schema2 singleton baseline,
   preserves private state/source/journals, and retires/restores with borrowed
   canonical lifecycle ownership.
5. The exact loaded pair receives one discarded 12-record warmup per model,
   one 12-record schema-constrained smoke per model, and one12-record real local
   `read_file` call plus matching continuation per model. Each body is natively
   counted at <=4096 input and <=256 output tokens; schemas have no answer
   constants. Actual request/result hashes, counts, TTFT, elapsed/native timing,
   correctness, auth/alias denial and both-resident allocation evidence are
   retained. No fitter, ladder, near-capacity occupied prompt or G64 speed claim.
6. Restore outside the measurement deadline; fresh Worker1 authenticated private
   LAN verification, host finalization and tunnel closure are mandatory. After
   `RECOVERY_REQUIRED`, go directly to the existing canonical recovery path;
   do not repeatedly invoke a known-failing restore wrapper. Preserve the
   underlying failure and ledger. Recovery-only execution writes a separate
   outcome and never upgrades failed/incomplete checks to candidate PASS.

Planned create intent is durable before preparation. Only the exact Docker
create dispatch seam changes it to uncertain. A proved pre-dispatch failure may
settle that intent durably; an empty post-timeout inventory cannot. Unresolved
uncertainty blocks destructive cleanup. Reconciliation permits only the exact
reviewed name/image/labels and full immutable ID, including mapping helpers.

The reviewed shared working-set helper reports sampled **ESTIMATE**, distinct
from raw current/peak and extra charged cache. It makes no instant-reclaimability
or exact-union claim. Both remaining cap obligations retain resident disjoint
anon+no-swap-shmem credit and16GiB OS reserve; fresh pre-retirement/preload
availability requires688GiB before credits. Each GPU retains16GiB free and
Qwen's10% comparison. Missing helper inputs stay UNAVAILABLE, and numeric
resource/identity/count/auth/correctness failures stop. Intermittent GLM speed
alone warns. Accepted configured capacity and largest occupied context remain
separate root decisions.

Live proof is still outstanding: actual-image fixture, actual native allocated
GLM480000/Qwen700160 pool and Qwen700154 input limit, exact UUID/tensor placement,
resource margins at those configurations, short model checks and restoration.
Production-default GLM logging must supply the allocation parser's required
facts; absent facts fail closed without silently adding a verbosity flag.
Candidate evidence is never `ACCEPTED_FOR_ACTIVATION`. Root must separately
review any accepted-receipt field mapping (including raw peaks versus estimated
required working set), production migration and later API/boot acceptance.
