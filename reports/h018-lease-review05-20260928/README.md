# H018 LEASE REVIEW05 — source-only independent review

Source: `f25c86ff00bfbd19806a515826d2e0949fee7d0d`. Owner SHA-256:
`218c890f1f3d8f7f80998aaf5cf7463c32febf5e454713f40da76a9ed60027d0`.
Native session/start/deadline: [EARLY.json](EARLY.json). Machine-readable conclusion,
input hashes and limits: [FINDINGS.json](FINDINGS.json). No implementation edits,
tests, host contact, requests, build, deployment or runtime changes.

## Actionable source finding

The scheduled `HardwareEvidenceCollector` holds the canonical exclusive lease
across binding, inventory observation and eligible proof refreshes for all four
GPUs (`scripts/control/node_collectors.py:235–255`; GPU list at
`scripts/lifecycle/hardware_policy.py:29–32`). Each changed proof is persisted
(`scripts/control/hardware_latch.py:299–319`), and `RegisteredLatchStore.write`
runs `root_payload_guard` before and after its tiny JSON write
(`scripts/lifecycle/hardware_policy.py:113–134`). Four newly changed healthy
proofs therefore imply eight scans; inventory transitions can add writes.
This is source-derived, not an observed LIVE05 write/scan count.

The guard recursively walks eligible root-device trees including `/opt` and
`/var/lib`, checking each file (`scripts/install/storage.py:377–429`, especially
396–424). It excludes registered data/model mounts and symlinks. `/etc` is not
a scan candidate. The observer's two-second budget marks an overdue sample but
does not interrupt its worker (`scripts/control/passive.py:18–20,65–85,98–109`).
`production_binding` limits external command waits, not this Python walk
(`scripts/control/node_observation.py:281–292`). The canonical lease can remain
held during that work. This is a plausible bottleneck and contention mechanism;
its actual duration and historical ownership are unmeasured.

## Smallest correction to review with W1

Remove only the two recursive scans from steady-state proof persistence.
Retain the existing borrowed canonical lease checks, registered path validation,
`binding.mounted_guard(..., roles=('data',))`, bounded protected existing-JSON
read, `HardwareLatch` validation, anchored atomic write and anchor check
(`scripts/lifecycle/hardware_policy.py:113–134`). Existing binding and mounted
facilities verify protected registration and actual mount/path identity before
and after the transaction (`scripts/lifecycle/storage_binding.py:174–233,254–285`;
`scripts/install/storage_io.py:261–319,402–437,579–643`). No unlocked writer or
new framework is needed.

Retain full root scans at initialization/lifecycle/deployment boundaries
(e.g. `hardware_policy.py:88,109`, `owner.py:888,918,732,749`). W1 must keep
boundary coverage explicit when reviewing callers. Preserve positive faults,
unknown-storage failure, exact proof identity/freshness, original deadlines,
and independent memory/swap/OOM/thermal guards. Do not widen TTL, turn unknown
into false, or globally disable root scans. This proposal removes demonstrated
redundant work; it is neither an implemented fix nor proof that all contention
or storage delays disappear.

## Owner, clients and causal limit

The owner releases its startup lease before supervision. Its stale/unknown
projection branch acquires the canonical lease nonblocking (`owner.py:588–639`);
`LeaseBusy` is propagated to fail-closed settlement (`owner.py:919–995`). The
canonical `flock` error identifies contention, not its holder
(`scripts/common/lifecycle_lease.py:166–206`).

Short02 and its request reader do not hold that lease over inference; storage
and proxy thread locks are distinct. LIVE04 read collection and node status GET
also do not acquire it. Tracked dispatch/deployment scripts release staging
leases before child start. Detailed paths and lines are in FINDINGS.json.
A separate conditional nested-acquisition defect exists when startup or short
dispatch calls `latch()` while already holding a lease and its projection has
expired (`owner.py:886–900,595–598`; `live04/read_dispatch.py:43–45`). Borrowing the
validated lease would correct that path, but it does not explain the subsequent
reported RUNNING failure.

Root reports 950K ready, tiny pass, 9,536-token tool prefill, primary
`lifecycle_busy` in `hardware_latch` at 01:00:16 and separate cleanup
`command_timeout` at 01:00:25. Exact LIVE05 holder/timeline and inactive-LAST
preparation source were not supplied. The copied LIVE04 handoff only says LAST
was inactive at its earlier checkpoint. **Do not attribute this failure to W1
LAST preparation or the hardware collector without contemporaneous evidence.**
No new qualifier, request completion or physical settlement is established here.

Completed early on actionable source evidence. Actual process exit is recorded
by the wrapper; this report does not manufacture an exit timestamp.
