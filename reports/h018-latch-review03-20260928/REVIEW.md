# H018 LATCH-REVIEW03 — independent source diagnosis

Base: `5b3841755e295917b1b32bb1a66c37d68967e191`. Owner SHA-256:
`dbb54dd908a5f9d1e833d34f9cf5d72fce27583fea089c35071b46e0b91f4e05`.
Session `01a0e563-64ad-7eb0-9c28-60c9b8038a0f`; launcher start
2026-09-28T00:21:31.014686Z; hard stop 00:40:00Z.
Early findings written at 00:23:29.333942Z.

## Decision at baseline review

The retained error does not establish a positive hardware fault or its alternative
cause. The source supports a dependency on the separate proof producer, including
proof expiry after failed/blocked publication. It does not establish that inference
held a lifecycle lease, that the producer ceased, or why publication failed.
No TTL extension, unknown-to-healthy conversion, qualification, activation or live
deployment is approved by this record. A candidate review, if supplied, is separate.

## Exact reader and producer chain

| Source at base | Behavior relevant to this failure |
| --- | --- |
| `scripts/runtime/mimo/owner.py:563-569` | `latch()` creates the registered binding, then calls `read_latch_status` for the one selected UUID and owner boot. Only literal `False` passes. `True` and `None` share `owned_gpu_latch_unproven`. Binding-construction errors outside the reader are separate exceptions. |
| `scripts/runtime/mimo/owner.py:846-907` | Every nominal five-second cycle checks selection, boot, exact container, GPU/host/cgroup resources, then hardware latch. The whole mandatory cycle uses the existing five-second bound (`201-213`). Failed latch projection is not saved; only successful cycles write hardware proof to `guard.json`. |
| `scripts/lifecycle/hardware_policy.py:137-188` | Allowlisted required UUIDs; protected state parsed with `HardwareLatch`; positive target records take precedence even with inherited boot/expired proof. Without a positive, each exact target needs current-boot proof with valid timestamp and wall age in `[0,15000]` ms. Unknown returns a generic reason; exceptions are caught. Valid state with old/missing proof retains semantic identity, whereas failed read/schema validation ordinarily has null identity. |
| `scripts/control/hardware_latch.py:34-39,90-130` | TTL is 15000 ms. Schema, UUID, boot, receipt, allowed fault code and evidence consistency are validated. The positive fault codes are `gpu_fallen_off_bus` and `gpu_unrecoverable_hardware_fault`; generic driver errors and ECC counters are not those codes (`142-169`). |
| `scripts/control/node_serve.py:42-55`; `node_collectors.py:259-272` | The existing node service wires `production_callbacks` into `BoundedObservers` and starts them. Hardware evidence is a scheduled callback, independent of GET handlers and service readiness collectors. |
| `scripts/control/node_collectors.py:98-143,215-256` | Exact GPU XML collector checks one exact UUID and stable boot across the probe; it retains capture wall/monotonic timestamps. `HardwareEvidenceCollector` is the periodic writer, acquiring the canonical lease nonblocking before binding/observing inventory/validating exact cached GPU receipts. Receipts older than 15 s are skipped; current wall freshness is rechecked inside policy. |
| `scripts/control/passive.py:18-20,65-109,126-135` | Nominal 5 s scheduling, 2 s callback deadline, 15 s cache staleness. Each callback has its own slot/thread. A hung slot is retained without replacement. Lease/probe/storage exceptions become generic `collector_failed`; a late completion is marked timeout. This scheduler does not cancel a callback or roll back already-performed protected writes. |
| `scripts/lifecycle/hardware_policy.py:219-250`; `scripts/control/hardware_latch.py:276-320` | Producer rechecks age after protected reads. State mutations are persisted before publishing changed state. Policy creates fresh protected latch views for inventory/exact validation. |
| `scripts/lifecycle/hardware_policy.py:113-134`; `scripts/common/lifecycle_lease.py:167-208` | Writes require the validated canonical lease and registered, anchored storage guards before/after atomic replacement. Contention raises `LeaseBusy` immediately; descriptors close on exit. No producer retry loop exists. |

Inventory observation precedes exact GPU publication. Exact GPU callbacks are
ordered Qwen0, Qwen1, image, frontier (`scripts/control/node.py:16-22`,
`node_collectors.py:24,248-255,264`). An exception while processing an earlier
target can therefore abort that producer call before frontier publication.
The bounded storage runner shares an invocation deadline (`node_observation.py:281-292`).
These are possible mechanisms, not established historical events.

The protected JSON reader deliberately detects path replacement or changed file
metadata during a read (`scripts/lifecycle/storage_binding.py:287-316`). A storage
read failure, including a detected concurrent replacement, can also produce the
same unknown latch result. The current failure record cannot distinguish this
from expiry. Atomic writing is not permission to ignore a failed protected read.

## Lease ownership and inference

The MiMo owner releases its launch lease before the monitor loop (`owner.py:810-843`).
Its ordinary status writes explicitly do not acquire that lease (`336-342`).
The proxy's stream lock is a process-local `threading.Lock` (`private_proxy.py:123,173-251`).
The H018 short client routes through the final13 transport; its reader opens
guarded storage handles around the request but no canonical lifecycle lease
(`scripts/h016/final13_long/reader.py:110-145`,
`scripts/h016/final13_long/client.py:112-116,144-227`,
`scripts/h018/short/client.py:134-167`). The source does not show an inference-held
canonical lease. Runtime contention, producer failure or delayed XML probing
requires actual retained producer/holder evidence.

## Positive faults and other unknowns

Same-boot positive records cannot be cleared by a healthy inventory or exact
validation (`hardware_latch.py:213-228,251-273`). Passive reads do not clear
inherited positives either. Existing explicit current-boot producer validation
has separate inherited-boot semantics; a correction must not silently apply those
semantics to an already-positive owner read.

Missing or corrupt protected state, wrong boot/UUID, future timestamp, storage
failure and expired evidence are distinct cases. None establishes a hardware
fault, and none is healthy evidence. Existing owner GPU/thermal/VRAM checks
(`owner.py:478-531`) also do not by themselves clear a sticky positive or authorize
replacing failed protected storage checks.

## Retained H018 evidence

`../input/FAILURE-DIAGNOSTIC.json` was collected at 00:19:51.569702Z. Its owner
state records primary refusal at 00:16:03.140247Z, operation `hardware_latch`,
phase `RUNNING`, cycle elapsed 0.115341 s. The journal separately records cleanup
interruptions at 00:16:04.416370 and 00:16:04.765025, followed by cleanup
`command_timeout` at 00:16:12.436586. Those cleanup errors do not replace the
primary latch failure.

The later hardware status is False, age 3657.917976 ms, matching owner boot, and
the separately collected protected record has empty targets. Its frontier proof
is timestamped 00:19:48.049171. This is later recovery/availability evidence,
not the failing read. It is consistent with no sticky same-boot positive; continuity
of the installed producers/protected state across the interval is not established
by these files alone.

The later container record says exited, exit code 139, finished at
00:16:17.026845645Z; native PID and cgroup are absent and the selected GPU's
compute list is empty. These observations follow owner/client stop attempts.
They neither identify the original cause of exit139 nor prove an inference crash
preceded the owner refusal. Saved proxy state still says active_requests=1; owner
state remains HELD/request_hold=true with settlement null. Keep physical release
and unresolved request completion separate; do not replay the unfinished request.

`ROOT-QUALIFICATION.json` says FAILED_NO_QUALIFICATION_NO_RETRY. No current950K
native tools or Sova acceptance follows from READY or the tiny completed answer.

At 00:26, `W1-NEAREST-GUARD-NOTICE.md` supplies **message-derived evidence only**:
last saved guard at 00:15:58.123911, proof age10953.0828ms, implying capture about
00:15:47.171. With no intervening refresh it would be about15.97s old at failure.
This strongly aligns with TTL crossing, but does not prove no intervening write or
the actual failing projection. The notice also reports GPU free9979MiB/38C,
owned swap/OOM0 and an earlier short-text guard; the authoritative extract was
not yet supplied when this paragraph was written.

At 00:27:45 the supplied `PREFAILURE-GUARD.json` became available (SHA-256
`ea7d6975e32aabd0f42506635df6db8958d486c7e3742620232655f1b29cf951`).
It confirms the prior guard timestamp, exact matching boot/UUID, literal False
and age10953.082799911499ms. Adding the5.016336s to the recorded failure gives
approximately15969.4188ms **if unchanged**. The guard publication timestamp may
slightly follow the reader's wall-time age calculation, so this is an alignment
calculation, not a recovered failure sample. The extract confirms free9979MiB,
38C, child/parent swap usage0, swap limits0, OOM/OOM-kill0. It explicitly marks
`failure_projection=NOT_RETAINED`. Its parent source digest is
`784783ad0c7b29ea845546132b52300045418e96be64c8f9019cd0eaff37c234`;
the complete parent collection is not supplied here for independent digest
verification. The earlier notice's short-text guard has not been independently
provided in this extract.

The later supplied `ROOT-DIAGNOSIS.json` adds exact physical **and proxy** release
at 00:21:31.256807Z through the existing validated settlement lease. It preserves
the HELD state bytes, request_hold and both failures; terminal stream completion
remains unproven. There is no inference possible in the exact released processes,
but no successful full17 completion and no replay authorization follows.

That supplied diagnosis reports the existing node service active since17:44:54,
with stdout/stderr null and no failure-window journal entries. The producer slot
is not projected into public NodeStatus and historical slot/lease-holder evidence
was not retained. Thus **blocked versus ceased versus failed versus delayed
producer remains unresolved**, rather than an answer that the producer was
definitely blocked by inference. Current empty lock observations are not history.
Eight supplied installed-source hashes (producer, scheduler, unit, latch policy,
latch state machine, storage I/O, transport and reader) match this checkout;
`INSTALLED-SOURCE-COMPARISON.json` records them. The external prep source is not
present here for hashing.

The diagnosis also reports native cancellation at00:16:03.656592115 and a second
interrupt/kernel null-IP worker segfaults at00:16:05.464600080, after the initial
owner refusal. This supports a teardown association without proving causality.
No NVRM/Xid entries were found in the retained kernel window; callback suppression
limits completeness. These are supplied W1 findings, not new worker2 VM reads.

## Focused baseline verification

`python3 -B reports/h018-latch-review03-20260928/test_latch_contract.py`
passed five tests in0.037s. The fixture executes the baseline reader, owner latch,
pure sticky state machine and producer contention entry path. Clock, storage and
LeaseBusy are explicit synthetic seams. It does not query a GPU, acquire the
installed lease, write protected storage, run broad tests or establish live cause.
`BASELINE-TESTS.txt` records exact output.

The checks cover TTL crossing without state mutation, wrongboot/missing/future/
corrupt/unreadable evidence refusing, same/inherited positive precedence, healthy
same-boot exact evidence preserving a positive, and publication contention leaving
persisted proof stale despite a fresh unpersisted collector receipt.

## Pending independent correction review

No W1 implementation is present at the baseline write. For a frozen correction,
check its actual admission case against supplied evidence, its exact-UUID/stable-
boot proof, sticky-positive refusal, all unknown/error paths, canonical lease
borrowing at launch, finite whole-cycle budget, no replay loop, protected writes,
source pins, bounded failure classification and preserved resource/settlement
guards. Existing `HardwarePolicy.require_start` defaults to one target probe
with a possible inventory fallback (`hardware_policy.py:252-371`); calling it
is not automatically evidence that the requested narrower behavior was met.

No production sources, Sova files, image46fe, host6c4b, selection, service state,
authorization or deadlines were changed. No contacts, downloads, builds,
inference, subagents or pushes occurred. The requested H018 task STATUS path is
not present in this isolated checkout/local task tree; supplied current root
notices and retained input files are recorded explicitly instead.
