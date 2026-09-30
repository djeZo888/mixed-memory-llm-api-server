# H017 owner repair — SOURCE ONLY

Native session `01a0e445-a819-7622-a5ea-ca006b1de33b`, started 2026-09-27
19:09:25 UTC, hard bound 19:36:00 UTC. Base is published
`d09620402007046881606dfbdc74c9ee3fde09b2`; branch
`worker1/h017-owner-repair-01`. No ai-vm contact, model action, request, remote
write, subagent or push occurred. Original production failure cause remains
**UNKNOWN**. H016 raw/private evidence and HELD records were not modified.

## First-priority offline result

**PASS at 19:11:11 UTC:** unmodified ordinary owner `7768181c` accepted genuine
complete retained R9 `/props` and `/slots` with the authentic DEPLOY17 qualified
manifest and HTTP mocked. All 16 identity/capacity predicates passed, at actual
usable context 1,000,000. Exact source, private evidence and manifest hashes are
in `OFFLINE-R9-REPLAY.json`. No identity was synthesized. This result excludes an
incompatibility with those saved R9 responses; it does not establish the original
live failure cause. Root was notified immediately, before report packaging.
Per Root direction, the passed replay was not repeated after code instrumentation;
the readiness predicate is unchanged. The explicit private-fixture regression
is retained as `tests/test_mimo_owner_r9_replay.py` and skips unless given both
pinned private paths. Private prompts/responses were not copied into Git.

## Narrow repair

- Primary and settlement failures retain separate phase, allowlisted code and
  timestamp diagnostics. Primary exceptions propagate even when cleanup fails.
  Guarded receipt failure cannot skip physical settlement; sanitized systemd
  journal output provides another durable diagnostic route. Both write routes
  remain best effort if their underlying storage fails.
- The serial mandatory loop records its current operation and monotonic cycle
  elapsed time only upon failure. Operations distinguish Docker inspection,
  NVML, host/cgroup reads, latch, each native HTTP call, and protected receipt
  writes. The five-second whole-sample deadline is unchanged. Serial maxima of
  2s Docker + 2s NVML + 1s props + 1s slots plus other work can exceed that budget;
  this is a source-supported hypothesis, not proof of the historical cause.
- Only exact settlement retries canonical lease contention, for at most ten
  seconds, or an earlier supplied monotonic deadline. The retained installed
  helper exports `acquire_lease` and `LeaseBusy`; its unchanged pinned lease
  module is `483ba038...`. Borrowing calls its existing scope/mint validator.
  Every acquisition uses the canonical API; across retries the inode must stay
  unchanged. Trust/identity/storage errors do not retry. No alternate lock,
  deletion, holder signal or lifecycle API change exists.
- Proxy admission intent is persisted before Popen. Settlement stops the exact
  child before reading its final protected disposition. Clean release requires
  matching launch, boot, native, child PID/start ticks and parent, plus integer
  active=0 and quarantined=false. ExecStopPost must freshly prove the recorded
  child generation absent before reading. Unknown/malformed/missing/wrong
  generation dispositions retain request ambiguity. Historical true holds are
  never cleared. This closes the pre-stop-idle/admission race using the existing
  begin-before-native-I/O and finish-after-terminal contract.
- First physical settlement failure becomes HELD with no physical proof, without
  inventing request ambiguity for a proven no-proxy launch. In the special
  repeated, same-manifest/already-SETTLED/schema2/no-proxy/no-hold case, canonical acquisition
  expiry preserves the earlier receipt/proof and records
  `settlement_recheck_failure`, then raises. It does **not** claim fresh GPU idle.
  Changed identity/inode/hardware errors do not take this preservation path.
  The CLI's protected invocation match and unchanged rollback's fresh exact
  container/cgroup/GPU/source checks remain mandatory.
- Docker stop grace 3s/client bound 7s and unit TimeoutStopSec=45 are unchanged.
  A timed-out stop can finish later; only subsequent fresh exact physical proof
  establishes that later settlement. No success is inferred from the timeout.

## Capacity and proposed installation

`MANIFEST-950000.proposed.json` changes requested/expected usable context to
950,000 and pins only the new owner/launch bytes within the retained 95-source
closure. One separately pinned capacity amendment is added. Unit, proxy,
registered guards, node closure, image, model shards and GLM rollback bytes are
unchanged. `qualified:true` retains the reviewed historical static/native R9
qualification; it is not a new 950K allocation or production PASS.

`CAPACITY-AMENDMENT.json` separates the 950,000 request/expected usable capacity
from source-calculated physical padding 950,016. Old physical 1,000,192 minus
950,016 at 51,200 B/token saves **2,450 MiB / 2.392578125 GiB**. The unrounded
50,000-token reduction is 2.384185791 GiB. Applying padded savings to measured
R9 free 7,481 MiB gives projected 9,931 MiB / 10.145% of 97,887 MiB. This is an
estimate, not allocation proof. Used+free leaves a measured 636 MiB difference
from total; no inferred total-minus-used free value is substituted.

Actual 950K props/slots agreement, >=7% GPU free, short real generation/tool
continuation, ordinary production and Sova acceptance remain **NOT_TESTED**.
R9 4K/16K/full17 evidence is reused with its genuine historical identity and
occupiedTested=16,384. No 64K or near950K optimized success is declared.
See `INSTALLATION-PLAN.md` and exact `INSTALLATION-DELTA.json` before any future
live action. The final independent chain remains undispatched.

## Focused validation

58 tests discovered: **57 PASS, 1 explicit R9 replay SKIP**. After the final
one-line same-manifest preservation constraint, all 11 focused settlement tests
passed again, including changed-manifest refusal; other source is unchanged. Scope is the existing
MiMo owner/node/proxy tests plus narrow owner regressions. Real local flock tests
cover eventual release/same inode, finite expiry, replaced inode refusal,
existing-capability borrowing and untrusted lock refusal. Tests also cover
primary+cleanup+receipt failure, operation/elapsed diagnostics, socket timeout
pending versus mandatory fatal, creation/admission intent, post-stop admission
race, final generation matching, repeated physical proof, and actual canonical
busy expiry preserving only the permitted old no-proxy receipt. Test fixtures
replace an inode only inside a temporary directory. No production lock was read
or modified. Changed Python syntax and owner --help pass; manifest validation,
950000 launch equality and diff whitespace pass. Sanitized full test log and
exact source hashes accompany this report. No live test result is claimed.
