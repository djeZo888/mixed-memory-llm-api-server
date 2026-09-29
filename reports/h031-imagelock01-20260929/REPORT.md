# H031 IMAGELOCK01 — source correction, not deployed

The image lifecycle reserves exclusive image ownership under short canonical
lease scopes, then creates/starts/warms/stops/removes the exact native container
outside the common lease. Protected operation and recovery descriptors/receipts
retain ownership across those phases. Boot, source/config, mounted storage,
state/token, selected GPU and native process generation are rechecked before
mutation or ready publication. No new service, API, runtime or timeout was added.

The normal bounded exact-UUID hardware probe now runs outside the common lease.
The existing `HardwarePolicy.validate_required` publishes its proof through
held anchored storage inside the lease, rechecking boot and the unchanged
15-second limit. Same-boot positive latches remain sticky; unknown fails closed.
This is a split of probe/publication, not the intermediate latch-only proposal.

The common scope contains protected local file checks, boot/PID ticks and atomic
state writes/fsync, with no subprocess or readiness/stop waits. Entry and the
pre-publication validation budget use the existing two seconds, capped by the
operation deadline. Filesystem syscall latency is not a hard real-time promise.
Recovery holds its separate reservation through one systemctl restart; the
actual unit PID/invocation consumes the child handoff once. A timed-out restart
without an acknowledged child retains its unresolved reservation. Unknown
Docker actions are never replayed; generic daemon errors cannot prove absence.

## Validation

- 83 focused image-runtime tests pass; Python compilation and diff checks pass.
- Exact base `70e3e7c1e59eb846eab65f16c11215c000f79351` fails the same real-lock
  startup fixture with `LeaseBusy`; corrected source passes.
- Real anchored storage/flock tests cover blocked load/warm/stop, exclusive
  operations, invalidated owner/source/boot/config/native generation, exact
  settlement and unknown-action retention. Full startup and warm-error paths
  also run through the actual lifecycle code with fake native I/O.
- Hardware tests cover fresh/stale/future/unknown/changed-boot evidence and
  positive latch retention. Recovery tests cover prior ExecStop/new ExecStart,
  one-time handoff, foreign/dead owners and uncertain restart retention.
- Fixture maximum observed common hold was about4.1ms with external I/O stubbed.
  This is neither a live measurement nor a latency guarantee.

## Current inventory and activation boundary

One read-only capture at08:53:18UTC retained the same MiMo launch/container and
RUNNING state, current guard and image native identity. Its aged proxy report
and null active-work field do not prove current idle. All96 captured MiMo source
pins matched. Both reviewed node leaves remain undeployed. Private snapshots,
exact source maps and handoff files are outside Git in task `output/`.

The exact combined proposal covers image service/config plus W2 owner, the two
already-reviewed node leaves and the MiMo successor manifest. MiMo directly
pins those three changed leaves; image service is separately pinned by image
config. No closure-list expansion is needed. Keep the old MiMo closure intact
through staged intent, normal old-owner stop and full physical release; archive
predecessor evidence before the one installation/reconcile/start sequence.

**NOT_DEPLOYED.** No VM mutation or inference occurred in this task. Historical
failures, uncertain owners/quarantines, profiles and capability gates remain.
The source fixture does not establish the historical competing lock holder or
qualify a live workflow. Exact combined root GO and current settlement/readiness
proof are still required. No GitHub push or end-window restoration.
