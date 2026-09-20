# Fixed GLM + Qwen production slots — source candidate

The 2026-09-20 concurrent-production authorization supersedes the older
single-backend architecture limit for this bounded task. Production activation
still depends on favorable benchmark results, root acceptance of the exact
capacity/allocation evidence, and review of this source candidate. This source
task runs on mac-worker1 only; it does not contact ai-vm, mutate a host, run
inference, or modify the independently running benchmark checkout. Installer,
frontend and future ai-harness work remain outside scope.

## Fixed topology and evidence boundary

The existing lifecycle Manager gains exactly two slots, `glm` and `qwen`. Both
use the existing global lifecycle lease, control mutation executor, operation
journal, authentication, private transport, registered storage and source pins.
There is no inference router or general placement framework. One slot's
targeted transition preserves the healthy peer's container identity and stream.
The sole boot owner replays saved intents in deterministic `glm`, then `qwen`
order. Docker restart remains `no`.

| Slot | Candidate deployment | Guest resources | Configured candidate |
| --- | --- | --- | --- |
| `glm` | `glm-5.3-ud-q4-k-xl-g1-480000` | GPU0; CPUs 0–95; 96 threads; 640 GiB no-swap cap | 480,000 tokens; **UNVALIDATED** |
| `qwen` | `qwen38-27b-q1-700160-yarn4-bf16kv` | GPU1; CPUs 96–111; 16 CPUs; provisional 32 GiB no-swap cap | 700,160 tokens; **UNVALIDATED** |

The exact profiles bind physical GPU UUIDs; each single-GPU container sees its
assigned device as CUDA0. Guest CPU separation is not physical CPU pinning.
The GLM N76/F16 and Qwen FP8/BF16 KV/YaRN4/chunk2048 settings, runtime and weight
pins, cache policy, aliases and model defaults remain explicit. GLM defaults to
low reasoning; Qwen defaults to no thinking. Existing TP2/1M profiles remain
explicit mutually exclusive alternatives and cannot coexist with the pair.
Unknown peers and conflicting identities/resources must be rejected.

Source profile declarations are not live-readiness receipts. Neither candidate
capacity is accepted merely because a profile parses or tests pass. Root must
provide the exact reviewed allocation, GPU margin, host demand/reserve,
occupied-context and inference evidence before activation. If evidence requires
a different context or cap, review a correspondingly pinned profile; do not
pass arbitrary launch arguments or manufacture an acceptance record.

Clients continue using their separate protected base URL/model configurations.
The reviewed private-network policy advertises GLM
`http://10.156.100.60:30002/v1` with alias `glm-5.3`, and Qwen
`http://10.156.100.60:30004/v1` with alias `qwen3.8-27b`. These are deployment
policy values, not reachability claims from this source task. Native host
listeners remain authenticated IPv4 loopback; preserve the existing private
proxy/firewall/TLS policy and unchanged key bytes. Native `/v1/models` remains
endpoint-local. Use the authenticated control catalog for per-model endpoint,
readiness and capability discovery; see [control API](control-api.md) for exact
targeted mutation bodies and asynchronous operation polling.

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
   production and recovery source, the exact backed-up v2 state, and original
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

## Future benchmark admission

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
independently running benchmark checkout and its singleton restoration source
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

Before activation, root must resolve the final accepted GLM/Qwen context values,
Qwen host cap and measured reserve, GPU allocation/margin, benchmark performance
decision, and protected acceptance-receipt identity. A fresh bounded Worker1
activation session must verify installed source closure, guarded migration,
both authenticated endpoints and aliases, missing/wrong-key rejection,
streaming/schema/tool-result continuation, peer survival during targeted
stop/restart, control-service restart persistence, deterministic boot replay and
the exact manual rollback. Distinguish a simulated boot replay from an actual
physical reboot. No source test closes those live acceptance steps.
