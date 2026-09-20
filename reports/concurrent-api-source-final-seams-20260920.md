# Concurrent API final review corrections — source only

Both final findings from the first sections of `incoming-latest.md` are corrected.
This supersedes the pending-create and resident-memory claims in the
[862ea01 handoff](concurrent-api-source-20260920.md). Retained native session
`01a0bdbd-0467-7430-ae53-12cb90bc8a30`, isolated mac-worker1 checkout; no VM,
Proxmox or Worker2 contact, live lease, inference, deployment, service restart,
push, installer work/tests, or separately owned benchmark source changes.

Tested source: `c06ee04adc906a82afbeea208531275dac96f06e`.
Correction commits, on this API branch only:

- `c785607da32625670b51863be7ddd9f7515f85a9`: resident no-swap shmem accounting.
- `c06ee04adc906a82afbeea208531275dac96f06e`: durable create-dispatch certainty.

## Corrected behavior

`pending_create.dispatch` is saved as `not_dispatched` before the final local
source check, then durably becomes `uncertain` before invoking Docker create.
Only the proven pre-dispatch record plus exact-name absence permits canonical
stop to clear a pending owner without a container identity. Generic CLI failure
and timeout do not establish daemon settlement. Any number of empty inventories
leaves an uncertain owner intact; older markerless records are uncertain too.
The control adapter cannot emit an absence proof for them, and recovery checks
independently enforce that distinction. Selection/retry remain blocked.

A late container is reconciled only through the existing exact name, full ID,
image and owner/instance/deployment label checks. The immutable saved container
does not carry the dispatch marker. Normal and storage-loss paths preserve the
healthy peer. No new daemon-settlement API or automatic destructive recovery
was added: if an uncertain request never materializes, it remains owned until
root can establish an actual reviewed settlement.

Host admission credits disjoint resident cgroup `anon + shmem` once, with zero
swap and exact current container/cgroup ownership. It requires explicit counters
and `shmem <= file`; total file cache, THP subsets, RSS and `memory.current` are
not extra credit. Remaining obligations to both reviewed host caps plus 16 GiB
OS reserve remain. Root's supplied rounded first-RUN shape (GLM 399.6 GiB shmem,
0.9 GiB anon, host 463 GiB available) now requires about 287.5 GiB to start Qwen,
instead of the erroneous 687.1 GiB. This is a synthetic accounting replay, not
a newly acquired live reading or acceptance receipt.

The root-accepted GPU free/UUID query, Qwen actual native pool, GLM native context
readiness and post-probe identity logic were not changed by these corrections.

## Focused validation

`python3 ../run-final-seam-checks.py` at the tested source above:

| Scope | Passed | Failures / errors / skips |
| --- | ---: | --- |
| Slot ownership, control recovery, current memory and closed profiles | 60 | 0 / 0 / 0 |
| Affected existing manager/lease/storage recovery and control regressions | 151 | 0 / 0 / 0 |
| Total | **211** | **0 / 0 / 0** |

The delayed-create regression makes three empty observations through fresh
recovery ownership before the timed-out create materializes, then stops only
that exact container. Other focused checks cover durable pre-dispatch failure,
generic post-dispatch failure, old/malformed markers, false absence denial,
identity mismatch, peer preservation, missing/inconsistent memory counters,
overlapping file/THP counters and both resident cap remainders. Independent
read-only review found no remaining blocker in the pending-create correction.
The full 601 suite was not repeated; its prior receipt remains historical.

Machine-readable [receipt](concurrent-api-final-seams-tests-20260920.json)
lists exact modules, source hashes and retained log hashes. The task directory
retains `session-id`, incremental statuses, `run-final-seam-checks.py`,
`final-seams-focused.log`, `final-seams-affected.log`, `final-seams-test-receipt.json`,
`candidate.diff` (correction from 862ea01), `working-source.diff` (full API delta
from a2186a4), `source-manifest.json`, `rollup.bundle` and `bundle-receipt.json`.
The earlier bundle and receipt are retained with the `.862ea01` suffix.

## Pending activation decisions

Production remains conditional on the favorable benchmark decision, accepted
capacity/allocation evidence and root source review. GLM 480,000 and Qwen
700,160 remain unvalidated profile declarations here. Root must freeze the
accepted closed profiles, Qwen host cap, measured margins and occupied-context
claims, then supply the protected acceptance evidence.

Timing at GLM 65,536 does not establish speed at configured 480,000. A later
root-reviewed allocation plus short smoke/tool checks at the accepted large
configured capacity will record timing; no additional long GLM request or
context ladder is prescribed by this source task.

Keep benchmark and API commits separate until fresh Worker1 integration after
benchmark restoration. Root reviews the combined source and affected checks
before a separate activation/acceptance session uses the existing guarded
migration, two-endpoint checks, targeted peer-stream survival, boot/recovery and
manual rollback contracts. Synthetic checks close neither live acceptance nor
the benchmark decision. No further source change is requested by these two
review findings.
