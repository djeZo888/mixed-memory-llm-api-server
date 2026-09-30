# H031 SOURCE04 — MiMo startup admission correction

ROOT authorized a narrow source correction at 10:24 UTC: bound the first
canonical-lease entry in `supervise()` to 2 seconds, retrying refused entry only.
Implementation is complete.61 focused checks pass (28 admission/guard/receipt/producer
checks plus33 existing owner/startup compatibility checks). The exact baseline
supervise function fails the transient-holder fixture at its first acquisition;
the corrected source passes. Historical holder identity remains unproved.
This packet deploys nothing; there were no VM calls, inference, configuration,
ticket/capability changes, image changes or GitHub push.

## Demonstrated mechanism and scope

At base `711b24e283c16b61067621de39b796a8657ee309`, `owner.py:1658` performs one
nonblocking canonical acquisition. A temporary legitimate holder causes immediate
refusal before ownership, receipt consumption or Docker mutations. A finite
actual-supervise fixture with real temporary flock reproduced that source
behavior. The existing five-second guard budget begins after admission and stays
unchanged. No nested canonical acquisition was found in verified startup latch
or node producer paths: each passes its already-held capability to nested work.

The authorized local owner helper must preserve canonical inode and boot while
waiting, acquire within a two-second admission budget, and revalidate current
source, manifest, selection, prior state and recovery under the acquired lease
before any mutation. Retry applies only to entry; an acquired body exception
propagates and body/native work executes at most once. All existing source,
storage, hardware, physical-absence, ownership, context and runtime limits remain.
No common lease API refactor, stale proof fallback or fault clearing is proposed.

## Retained evidence and limits

ACTIVATE02 at 09:55:18.415682 and SOURCE03 at 10:09:56.776569 recorded CLI
`lifecycle_busy`, followed by ExecStopPost `recovery_invocation_changed`. Retained
old SETTLED state and unconsumed chain stayed unchanged. The CLI maps LeaseBusy
without its throw site; neither historical holder nor historical self-contention
is proved. ExecStopPost checks invocation before settlement and preserves the
old owner under the new failed invocation. SOURCE03's earlier helper-only
all-five-GPU refusal is separate from its one normal start and is not a
production hardware-fault finding.

The base-source pin comparison matched all 96 captured manifest source entries.
The final owner correction changes one pinned source;95/96 final source entries
still match the captured manifest, and the changed owner hash is recorded below.
The retained manifest raw hash is
`56ad1378aeab24215e0b064d731a688ab0c1df4302994a82c976b697be78ad7d`;
canonical hash is
`9315a02f73288d9f6041b47316008fdf7502d7755be66278fd4ce0ec0ee0a9e9`.
No current VM readback is claimed.

The external PREP helper remains unverified: owner requires
`03c0933c194c79a6aca5e98e26bd1682f99927c0f9dbfe53f25d9938caf3724c`,
but local `scripts/h014/prep.py` is
`6e8d364344ba31cc33247b1d1e55d3fdb826d48fc812336573e22a594c11040b`.
Neither retained tar nor the sole local history revision supplies exact bytes.
Its installed setup()/manifest() implementation is not proved by fixture helpers.
Qualification, model/platform bytes and current health were not reverified.

## Focused validation

The corrected batch passes all61 focused checks, including10 new admission cases:
transient real-holder release reaches the body once; sustained contention expires
without writes; changed inode/boot/manifest/prior-state/source refuses; an acquired
body LeaseBusy is never retried; borrowed lease and strict STOP_TIMEOUT stale-proof
refusal are preserved. Two existing synthetic fixture seams now explicitly stub
startup admission; new real-flock cases exercise the actual helper. The original
supervise AST fails the same transient-release test with LeaseBusy. See
BASELINE-FAIL.log and baseline_repro.py for the finite source reproduction.
Existing source fixtures use mocked installed storage/systemd/GPU/Docker
boundaries and real temporary canonical flock. No runtime is started, and source
fixtures do not qualify any live workflow.

## Future activation prerequisites

The old owner pin is
`687aa9e57f59103b39f6c4aefcf51d5ffc0bb9cf697fb443747d3757c332b090`.
The new owner pin is `2875de12f543ba06de36d57d06f4a8d87553765f74cd4cb69e0d7c76942a698c`. Because owner is
pinned, future activation requires root review of exact final owner/dependency
hashes, an updated exact source closure and approved source delta. An explicit
compatible source transition must preserve immutable predecessor archives,
existing intent/supplement/receipt chain, failures, uncertain owners and
quarantines. Root must separately authorize activation and obtain required
current physical absence and exact MiMo-target hardware proof. No existing
uncertain or consumed work may be replayed and no old receipt is silently reused
for a new manifest. Current installed source, manifest and selection are untouched.

Root alone publishes. Image source `4ebe25cf` remains outside this task and is
not deployed here. See CALL-PATH.md, SOURCE-PINS.json and TESTS.log. Raw private
captures remain outside Git. Final tests and source are committed together; no paid waiting remains.
