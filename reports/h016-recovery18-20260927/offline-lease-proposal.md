# H016 RECOVERY18 — offline lease and settlement review

This is an offline proposal only. No runtime source, service, lease, guard or
hardware setting was changed by this review. Reviewed source is the supplied
DEPLOY17 revision `8f52fe930768c4ca081f6eb296ff49a3a8eec25b`.

## Findings

- `scripts/runtime/mimo/owner.py:610-612` invokes `settle_state()` from
  `supervise()`'s `finally`. If the main operation raises and settlement also
  raises, the settlement exception becomes the surfaced exception. The CLI at
  lines 667-672 emits only that exception's type or RuntimeError text; it does
  not preserve the original exception chain. The observed `LeaseBusy` therefore
  does **not** establish the original load failure cause. That cause and the
  original lease holder remain **UNKNOWN**. The later node holder PID 3309508
  is not evidence that it held the lease at 18:04:45.
- `stop_exact()` at lines 426-448 acquires the canonical lease with
  `blocking=False`, validates exact launch/container identity and registered
  storage, then stops only that container and verifies PID, cgroup and owned
  GPU release. The current implementation has no bounded contention wait.
  `scripts/common/lifecycle_lease.py:166-208` supports blocking or nonblocking
  acquisition, validates the canonical inode and closes the owned descriptor;
  its documented contract requires nested callers to borrow an active lease.
  Nothing in this review supports deleting/replacing the lock or killing its
  holder.
- `scripts/control/node_collectors.py:225-256` defines the scheduled
  `HardwareEvidenceCollector`, which takes the canonical nonblocking lease
  while persisting hardware evidence. This is a source-supported node lease
  path consistent with the current observed node holder; the read does not
  identify its Python thread or prove this specific call held the lock at
  either observation or original failure. No hardware latch was cleared.
- `settle_state()` at lines 475-499 sets `request_hold=True` for **every**
  physical settlement exception, including lease contention. It preserves that
  boolean on subsequent successful settlement. Thus a physical failure can
  leave a sticky request hold even when `proxy_started=False`. A successful
  physical stop alone cannot clear it under the existing API.
- `rollback_glm()` at lines 615-638 correctly requires complete physical
  settlement and `request_hold=False`, freshly verifies exact container,
  cgroup/GPU absence and preserved GLM file hashes, writes an explicit GLM
  selection with `generation=expected.generation+1`, then releases the lease
  before invoking the ordinary GLM unit. No manual fabricated selection or
  generation is needed. Existing quarantine checks must remain effective.

## Narrow future change, for separate review

1. Persist an allowlisted primary failure code and phase before settlement;
   record settlement failure independently. Ensure a receipt-write failure
   cannot skip physical settlement. Preserve both errors without logging
   credentials, arbitrary command output or request content. Keep the primary
   failure visible in the final diagnostic when settlement also fails.
2. Add a deadline-aware canonical acquisition/borrowing path only where needed
   for exact settlement. A bounded wait must retain canonical inode and trust
   checks, distinguish contention from invalid storage/identity, and stop at
   the authorized deadline. A nested settlement with an existing valid lease
   must borrow it through the established API rather than reacquire it. Do not
   weaken stop identity, storage, reserve, thermal or GPU-absence checks.
3. Separate physical-settlement failure from actual request ambiguity in the
   state schema. Never clear a request quarantine automatically merely because
   the native process has stopped. A migration/reconciliation of an old sticky
   boolean needs explicit root-reviewed evidence: exact launch/boot/source,
   archived failed state, fresh complete physical release, proven proxy never
   started/no inference, and no contrary matching proxy receipt or owner. Any
   uncertain request history retains the hold. Preserve the old receipt and a
   distinct reconciliation receipt; do not silently rewrite historical fault
   evidence.

Future scoped tests should cover dual primary/settlement errors, bounded
contention and unchanged-inode acquisition, lease borrowing, physical failure
without a proxy, genuine active/quarantined request retention, and rollback's
selection-before-start ordering. No new tests were run for this documentation.

## Recovery boundary reported by root

Root reports ordinary exact settlement at 18:12:57 UTC with unchanged lock inode,
followed by a separately recorded, root-authorized reconciliation and unchanged
`rollback_glm()`. GLM started at 18:14:48 UTC with selection generation 4 and
authenticated readiness was observed at 18:17:36 UTC, context 1,048,576. Root's
raw receipts and final compact recovery record are authoritative for those live
facts; this offline review did not contact ai-vm or independently re-observe them.
