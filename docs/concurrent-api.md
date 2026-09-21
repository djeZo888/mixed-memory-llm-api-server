# Dual Qwen production slots — 2026-09-21 live acceptance

**Live production acceptance PASS — 2026-09-21, 03:21 UTC**, installed source
`04143b18cca7aca724d9a4a4bcf943fe86c040db`, default `dual-qwen` and optional
`glm-qwen` replacing only GPU0. The [dated proof](../reports/dualq-480k-20260921.md#dated-production-acceptance--2026-09-21)
records both Qwen instances warm/ready with running/resume intent after the
completed mode-switch sequence. Benchmark STOPPED/manual restoration remains
historical. Hardware boot, cold-boot replay and live full rollback remain
NOT_TESTED. CLOSE consumed saved files only, without VM work or retesting.
Installer, frontend and future ai-harness implementation remain out of scope.

## Fixed placements and discovery

The existing Manager, canonical lifecycle lease, serialized control executor,
identity journal and protected boot owner remain authoritative. Persisted v3
keys `glm` and `qwen` mean GPU0 and GPU1 respectively; the first is a historical
key, not a restriction to a GLM model. Public `placement` and `instance_id` (equal to the deployment ID) distinguish the two Qwen copies despite their identical model ID.

| Mode / slot | Deployment | Native port / alias | CPU mask / hard host cap |
| --- | --- | --- | --- |
| Default GPU0 Qwen | `qwen38-27b-q0-480000-yarn4-bf16kv` | 30002 / `qwen3.8-27b-gpu0` | 0–7 / 32 GiB |
| Both modes GPU1 Qwen | `qwen38-27b-q1-480000-yarn4-bf16kv` | 30004 / `qwen3.8-27b` | 0–7 / 32 GiB |
| Optional GPU0 GLM | `glm-5.3-ud-q4-k-xl-g1-480000` | 30002 / `glm-5.3` | 0–71 / 640 GiB |

All three configure **480,000 tokens**. Qwen actual scheduler pool must equal
480,000, input limit 479,994 and optional request limit 479,999. GLM `/props`
resolved context must equal 480,000. These checks do not establish occupied
context/retrieval correctness. Saved dual-Q benchmark evidence covers
479,490 / 479,495 occupied tokens, with Q1 strict-format failure and semantic
PASS. Subsequent production native allocation and bounded live API acceptance
passed; no new near-max workload was run.

Masks are shared guest CPU affinity, not exclusive or physical CPU allocations.
Q/Q shares the same 8 guest CPUs; G/Q shares Qwen's 8 with GLM's 72. Online guest
CPUs must remain 0–71. Both caps are no-swap. Reuse exact runtime/image/model pins,
Qwen BF16 KV, YaRN 4, chunk size 2,048, static memory fraction 0.8,
GLM N76/F16/fit-off and existing cache
policy. Separate writable cache/log/service paths and full container identities
are mandatory. Historical 700160/96+16 and TP2 profiles are not admitted as this pair.

No common inference router is added. Clients discover and explicitly address
both Qwen instances; a concurrent pair uses distinct URLs and aliases. Native
listeners remain authenticated IPv4 loopback. Existing protected private policy
maps 10.156.100.60:30002/30004 to those physical endpoints and control on 30000.
The historical proxy role `glm` names port 30002 even while Qwen0 occupies it.
Native `/v1/models` is endpoint-local. No wildcard/public/IPv6 exposure or key
rotation is introduced. Installed network config was read-only verified in PREP.

Authenticated control status/catalog expose `default_mode`, `current_mode`
(basis: selected deployments), `available_modes`, configured/accepted/occupied
capacity distinctions, readiness, degraded state, mutation busy and transition
cost. Available modes are closed declarations, not admission receipts. Inference
running/queued counts, freshness and external harness backlog stay **unknown**;
Ready never means idle. Catalog switch-cost seconds remain null; actual
operations took 255.585590 s to GLM / 120.568066 s back Q0, excluding
pre-admission/status overhead. Earlier GLM G65008
native decode was 0.453261513 tokens/s; it is historical workload evidence, not a
switch-time estimate or a general throughput guarantee.

## Acknowledged targeted replacement and durable ownership

Retain expected generation/active identity, idempotency and operation polling.
A switch/restart of ANY running target requires `allow_interrupt:true` even if
it looks Ready or unhealthy. A single trusted future client pauses its dispatch
and drains its own backlog before acknowledging replacement. There is **no
atomic server drain guarantee**: direct inference endpoints bypass the lifecycle
lease, so an idle sample cannot fence new requests. No gate/proxy framework is
added. The server does not choose when Qwen failed, assess answer quality or
implement escalation policy. G/Q reduces Qwen instances from 2 to 1.

Only the target is stopped/replaced. GPU1 Qwen keeps its exact identity and
stream. Failure must retain peer and recovery ownership, never silently restore
or replace the peer. Return to Q/Q explicitly replaces GPU0 with Qwen0.

The existing protected systemd boot-start/boot-stop owner replays `resume`
intents GPU1 first, then GPU0; Docker restart remains `no`. Control/proxies use
existing ai-vm services. Production has no Worker1/SSH/benchmark-keeper lifetime
dependency. Saved evidence confirms installed source, running/resume intents,
control restart, warm idempotent replay and private clients after SSH exit.
Hardware boot, cold-boot replay and live full rollback remain NOT_TESTED.
Do not adopt benchmark containers. RUN2's saved receipt records canonical
STOPPED/manual restoration; it does not establish current production state.

## Explicit migration and recovery contract

`llmctl migrate-slots` is an explicit canonical-lease mutation. An ordinary API
request must not silently migrate singleton state. The version 3 state contains
exactly `slots.glm` and `slots.qwen`, with separate selected deployment,
desired/observed state, owned container identity, generation and boot policy.
Migration preserves the original v2 intent and identity in the corresponding
slot; saved `ready` does not establish running/readiness after migration.

Before writing v3, preserve a protected backup at the fixed state-adjacent path
`active/pre-slots-v2.json`. Its envelope retains the original v2 record and
the `prior_source` attestation from the protected instance's `slot_migration`:

| Field | Required meaning |
| --- | --- |
| `prior_source_revision` | Exact prior 40-hex source commit |
| `prior_source_manifest_sha256` | Exact protected prior source manifest digest |
| `prior_boot_unit_sha256` | Exact prior boot-unit digest |
| `prior_source_root` | Prior protected source beneath the registered services root |
| `prior_recovery_source_root` | Fixed `/usr/local/lib/local-ai-server` recovery source |
| `approval_reference` | Root review identity authorizing this migration |

The v3 migration record contains `from_schema: 2` and `backup_sha256`, the
canonical-JSON digest of that envelope. Do not overwrite the original backup
to accommodate a changed source, state, or intent. Protect and preserve the
actual prior source/recovery snapshots and boot unit as well as their recorded
digests; an attestation cannot reconstruct missing source bytes.

Normal persisted state and the protected `/run` recovery journal must retain
both owned identities. Storage loss cannot justify selecting only one slot or
reconstructing ownership from a name. A failed second start must keep the healthy
peer and the exact failed identity visible. Shutdown attempts both owned stops;
partial failure stays a failure with the outstanding identity retained. Neither
saved desired state nor Docker restart policy substitutes for fresh observation.

## Root-reviewed manual rollback

There is no automatic destructive rollback. A separate reviewed activation or
recovery session must perform this sequence with the current installed guards,
protected paths and canonical lifecycle owner:

1. Drain or explicitly interrupt the relevant requests under the authorized
   scope; drain the control executor and settle outstanding operation receipts.
   Preserve the current state/journal, the immutable v2 backup, source manifests,
   boot intent and exact container identities before any source replacement.
   Exclude other mutators through the existing ownership/lease contract.
2. Verify protected backup identity and canonical digest against the v3 migration
   record. Verify the retained prior source commit/manifest, recovery source and
   boot-unit bytes against the attestation. Verify exact registration, mounts,
   current installed guards, credentials and source paths. Missing evidence,
   ambiguous ownership, storage failure or a stale journal stops rollback.
3. Identify each new pair-owned container by full ID, name, image ID, ownership,
   instance and deployment, including a failed or partially created container.
   Reinspect these identities immediately before scoped stop/removal. Stop and
   remove only the exact new owned containers within root's reviewed scope;
   never use a name wildcard, global prune or an unverified adopted container.
   Record partial failures and retain recovery ownership until reconciled.
4. Prove the recorded pair-owned full IDs absent and prove that no untracked
   owned container remains. `llmctl rollback-check` is a read-only prerequisite
   check: it must refuse incomplete absence/ownership evidence and return the
   prior source/state/boot prerequisites. It neither removes containers nor
   restores source/state, and it does not replace the separate control-operation
   drain or live source-byte verification.
5. With the lease/maintenance ownership preserved, restore the protected prior
   production and recovery source, the exact backed-up v2 state, the backed-up
   singleton control journal (or its captured absence), and original
   boot intent/unit. Recheck source digests and registration. Use that reviewed
   canonical lifecycle to return the original
   `qwen38-27b-1000000-yarn4-tp2-bf16kv` deployment to its captured intent; never
   infer `running` from the saved record or start an originally stopped model.
6. Verify fresh readiness (or stopped state), original boot preference, unchanged
   credentials/storage identities, expected service state and no pair remnants.
   A Worker1 ordinary private-LAN client must verify authenticated original-Qwen
   behavior before claiming a running rollback accepted. Keep failures explicit
   and retain the private recovery artifacts; do not mark a partial restore done.

For a migration rolled back before any production switch, preserve the old TP2
container when it is stopped and its selected deployment and complete owned
identity still exactly match the protected v2 backup. It is a tracked preexisting
identity, not a new pair container to remove. Once a targeted production switch
has canonically removed that TP2 container, rollback recreates the original
deployment through the canonical lifecycle; it must not adopt an unrelated
container or require the historical Docker ID to be reused. The prerequisite
check must distinguish these two cases and require absence of every new slot
identity while refusing any untracked owned container.

The migration and rollback prerequisite helpers are source mechanisms, not
evidence that installed protected snapshots, absence, restoration, or live
acceptance have been observed on ai-vm.

## Benchmark ordering and pair-state boundary

The existing benchmark owner captures/restores one production selection. This
candidate intentionally does not extend that restoration owner to two slots.
`CampaignOwner.begin()` checks raw `Manager.read_state()` under the canonical
lease, before the host's singleton snapshot projection and before maintenance.
Schema 3 or any `slots` field is refused with
`benchmark_pair_state_unsupported`, even if both slots are stopped or legacy
singleton fields are also present. Unknown state versions are refused as well.
The sanitized snapshot validator independently rejects pair records. The same
raw-state guard precedes restoration so a fresh singleton recovery owner cannot
overwrite pair production after a migration.

Admission refusal releases the lease without stopping production/control or
starting the benchmark clock. A restoration refusal retains recovery ownership
and reports failure. Running another benchmark after pair activation requires
a separately reviewed owner that captures/restores both slots, or an explicitly
reviewed full rollback to singleton production. No capability flag bypasses
this check. These changes apply only to this isolated source candidate; the
separately owned benchmark checkout and its singleton restoration source
are untouched.

## Verification and activation handoff

The focused synthetic command for this benchmark boundary is:

```text
python3 -m unittest tests.test_benchmark_pair_admission tests.test_benchmark_lifecycle tests.test_benchmark_owner
```

It covers raw pair rejection before lossy capture, stopped/empty pair rejection,
malformed and disguised pair records, pure planner refusal, recovery refusal,
and preserved singleton benchmark restoration behavior. The source task receipt
records the exact tested commit and aggregate lifecycle/control coverage.
Local fixture leases are not ai-vm leases; synthetic tests establish neither
GPU admission on the host nor inference, boot or rollback acceptance.

Root reviewed the exact source and saved dual-Q benchmark report. RUN2 used
one discarded warmup per instance and exactly one measured pair: native input
479,408 each, output cap 512, actual output 82 / 87. The pair completed in
258.9091 s without a five-minute cutoff; output windows did not overlap.
The report preserves strict/semantic scoring and sampled-resource boundaries.
No benchmark is rerun by this documentation update.

ACTIVATE's saved final proof supplies installed source and migration evidence,
both authenticated endpoints/aliases, missing/wrong-key 401s, Qwen schema/tool
continuation, peer streams during targeted mode switches, control restart and
warm idempotent boot-owner replay. Exact Q1 identity survived both transitions.
Hardware boot, cold-boot replay and live full rollback remain NOT_TESTED;
preserve the exact manual rollback prerequisites.


The protected migration backup also captures `prior_control_journal` (schema 1
or `null` for a verified absent journal). Migration refuses nonterminal control
operations or a non-singleton prior journal. Preserve this backup: the candidate
control journal becomes schema 2 after slot reconciliation, and older control
source cannot read it. Root drains control before rollback, archives the pair
journal, and restores the captured singleton journal/absence with the old source.
The read-only rollback check also refuses currently nonterminal operations.
