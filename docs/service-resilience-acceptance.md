# H005 service resilience acceptance — 2026-09-25

**PARTIAL / PENDING acceptance.** This publication checkpoint records sanitized
repair receipts through the activation's last VM contact at **19:44:30 UTC**,
plus the latest root-supplied watcher/admin/image-lane readbacks on September 25.
All three models were ready at 19:41:16 UTC: both Qwens retained their invocations,
the repaired image service was warm, and node/control processes were active.
Root now records watcher failure/restore PASS and trusted-LAN admin OPEN;
typed lifecycle, serial reboot and formal quiet/wake acceptance remain pending. A bounded task's PASS is not a final H005 PASS.

This report was prepared offline from combined source
`62d9f0e188b03a9183d281fbe55345806f23650d`. It does not claim that this combined
Git commit was deployed wholesale. The 18:18 acceptance draft is a historical
outline, superseded by the receipts below. No VM contact, deployment, build,
inference or service-dependent test occurred during this documentation task.
Root review and later publication are separate; no push, PR6 update or main merge.

## Implemented behavior and evidence boundary

The [source contract](service-resilience-contract.md),
[scheduler policy](adaptive-idle-source.md) and
[harness checkpoint](../ai-harness/docs/h005-source.md) implement independent
status, typed scoped actions, durable operation/dispatch holds and boot hardware
latches. Status and readiness are passive; unknown telemetry, busy backpressure,
hardware absence and uncertain request ownership remain distinct. Readiness alone
cannot clear a hardware latch or reconcile an uncertain image request. Actions
require boot/generation checks and canonical settlement; unknown operations and
interrupted work are never automatically replayed.

Each native scheduler retains its busy grace for **600 seconds after the last
real work completes**, including response drain and pending asynchronous work.
Active, queued, draining or unknown work prevents blocking. Passive status traffic
does not renew grace. Once genuinely idle beyond grace, the scheduler waits for
an event; weights/cache allocations are preserved by policy. Ordinary work wakes
it and renews grace. These source semantics are implemented; their full three-model
live transition, retained cache/VRAM and immediate wake are still acceptance gates.

| Evidence class | What the available evidence establishes | Limit |
|---|---|---|
| Source/offline fixtures | Scheduler timing/drain/event logic; independent collectors; typed action, boot-latch, scoped hold, idempotency and uncertainty handling at fixture boundaries | Injected owners, clocks and browser/network fixtures are not live lifecycle or containment acceptance. Overlapping suite counts are not summed. No suites rerun here. |
| Actual repaired-image CPU check | Production UID 1000:GID 1001 read and verified the exact derivative's overlay files; native serialization/drain checks with no CUDA initialization | No model load, readiness, generation, GPU or idle/wake proof from this fixture |
| Refreshed actual-text-image CPU auth | Both slot receipts passed with the new global binding and synthetic engine/model seams; final source validated those receipts without rerunning them | No model/GPU execution or new capacity measurement; driver control nodes were present, GPU device nodes were absent |
| Real short text checks, Phase B | Both loaded Qwens returned `OK`, 17 prompt / 2 completion tokens each, seed 42, temperature 0; authenticated passive readiness passed | Short functionality only; not main/child workflow, long-context, throughput or sustained acceptance |
| Real repaired-image checks | Canonical warmup plus exactly one public 1024×1024 generation; final all-three-ready readback | No fresh edit, Full HD, visual-content or sustained benchmark acceptance |
| Harness status/credential repair | Status component active with schema 1 and unchanged healthy main identity; credential mount/ACL compatibility repaired | Does not prove action execution or independence during downtime |
| Later watcher/admin readback | Root records watcher PASS; fresh restored-policy attestation and trusted-LAN admin exposure receipts supplied | Restored raw nft digest is not comparable across deliberate table recreation; typed action/reboot acceptance remains pending |
| Packet-causal task denial | Root accepted host rejection of the owned Slirp connection with trusted connections successful before/after | Client timeout alone was not proof; this narrow causal result is not the complete container/watcher/lifecycle matrix |
| Dated transfer measurements | Brief copy-engine bandwidth and sampled core temperatures for four cards | No sustained thermal, platform maximum, D2D/P2P or model-capacity claim |

Exact artifact names and raw SHA256 provenance are in the
[compact evidence index](../reports/h005-service-resilience-20260925/acceptance-evidence.json).
External originals remain retained by their named task; raw traces, private path
metadata, credentials, chats and backups are not copied into this public package.

## Deployment lineage and current model identities

The repaired ai-vm successor uses source
`5b20f26b36e8caedfd62ce42060ecdbe32126224`, integrated in the combined source above.
The [runtime binding](../configs/runtimes/h005-runtime-binding.json) raw SHA256 is
`9da2236e927c44e2af618e0862ee84f54d4645ec0bcb1e93c25c0d98b45ee6ae`.
The immutable successor release preserved its predecessor; the receipt records
136 release files and 215 installed source/config/receipt destinations checked.
These are closure counts, not independent test totals.

| Resident deployment | Immutable manifest / local Docker ID | OCI config digest |
|---|---|---|
| Qwen3.8-27B FP8 on GPU0, alias `qwen3.8-27b-gpu0` | `sha256:0aa2afe62c04fdd4f06a38229e6941cb1e47f6b7c0863698b708f299d4f15ddf` | `sha256:8f9a45a8a4de689280c054867103fc072f064703427212aeb6d603551a86f4b2` |
| Qwen3.8-27B FP8 on GPU1, alias `qwen3.8-27b` | Same unchanged text image | Same unchanged text config |
| Qwen-Image-2.1 on dedicated Ada | `sha256:50a3bfd20fc931f05fc5fc919b0445abbce30d5c7716424d697a7ab6708c08ef` | `sha256:3f6178faa74c4a9bcb95ed4304dbee57473efa8913a793e067014af4a98281ad` |

Both Qwens retain 480,000 **configured** tokens, FP8 weights/BF16 KV, shared guest
CPUs 0–7, 32 GiB memory each with no additional swap allowance, radix cache disabled
and Mamba cache 1. Image retains CPUs 8–15 and 96 GiB memory with no additional
swap allowance. The unchanged Qwen starts were 18:45:29.790881105Z and
18:47:38.530847547Z; generations 23/17 and running/resume intent were preserved.
Exact native container identities remain in the retained deployment receipt.
The Server Blackwell remains unassigned; ECC settings were unchanged.

Harness main release source is `63dcb23ebd0b2cb82a295bea78192f3e1a433a6e`.
The separately activated status component uses
`c640b9c9c3b9a41fb639eeb92018d34470041ad3`; its 19:27:39 UTC receipt records active
status, schema 1, unchanged main identity/dependencies and no state reset. The
systemd read-only credential mount and service-UID ACL were verified without
reading or recording credential bytes, hash or length. Admin was CLOSED in that
earlier receipt; the later `ADMIN-EXPOSED.json` explicitly records OPEN on the
reviewed trusted LAN. This is exposure evidence, not typed action success.

Node authenticated status returned 200 and missing/wrong credentials were denied.
All three models were observed ready. **Control projection remains limited:**
control's process was active, but node reported availability `unknown`, ready
`null`, reason `observation_unavailable`. No newer supplied receipt resolves this.
This conservative unknown is intentional until API proof exists; it is not a
declared source bug. Active systemd state does not prove node-observed readiness
or control independence.

## Image permission failure, repair and proof transition

Phase B's image `sha256:f01aafc2fefb4a5f961c73b7435ccfbdf5a801ccc55a9112d50fc5d45beb3a0f`
(config `sha256:e0a3d6b3b0e55583feb272dac0c0f3caedbabf65bb19f60efbf7f13c3591b51f`)
failed before model load, exiting after 0.157 seconds. The verifier and image
manifest were root:root `0600`, unreadable to production UID 1000:GID 1001.
The approved verifier bytes matched. Failure preceded backend-log creation;
there is no surviving traceback to claim. The owner recorded
`native_exited_during_load` / `reset_warm_failed_no_retry` and settled the failed
invocation. This failure remains historical evidence.

The image derivative changes file permissions only: six native overlay files plus verifier
and manifest become `0644`, and two exact directories become `0755`; no recursive
package chmod or code/weight/runtime redesign. The actual derivative CPU fixture
ran as UID 1000:GID 1001, verified **15 production overlay files**, and actually
read all 17 checked files (including verifier/manifest), root-owned and not
writable to that UID. Eighteen ancestors were safely traversable. GPU devices and
CUDA initialization attempts were absent. Local packaging fixtures alone would
not establish this production-user file access.

The permission-only rebuild still changed Dockerfile/provenance and the **global
binding hash**. Old text auth receipts correctly failed the new binding identity,
even though text image/code were unchanged. Two fresh existing CPU auth fixtures
passed for GPU0/GPU1 against `eca326800e495e5fa56f0561df0a29fb8b6b9e00` and the new
binding. Both receipts then validated against final successor `5b20f26` without
another run. Their raw and canonical hashes are separately indexed. Synthetic
engine/model seams and zero native CUDA devices remain explicit; NVIDIA driver
control nodes in text fixtures do not mean GPU execution. No inherited PASS was
relabeled, no text rebuild was needed, and the original capacity predecessor was
preserved. The final successor proposal/config identities, not intermediate
proposal hashes, are the publication lineage.

Canonical old-image removal proved exact old-container absence at 19:36:48 UTC;
its prior PID 0 settlement was retained. Fresh image readiness at 19:40:26 UTC
preceded public generation. That receipt is input to root/Worker2 quarantine
reconciliation, **not authority to clear uncertain ownership by readiness alone**.
Historical uncertain results and pending approvals were preserved without replay.

## Short live checks and preliminary idle observation

The canonical image startup warmup used 1024×1024, 40 steps, seed 42: native
inference 23.742 s, total call 23.910 s. The subsequent single authenticated public
generation used the same geometry/steps/seed, CFG 1 and n=1, returning a valid
898,215-byte RGB PNG in **24.859 s**, with no crop. Output SHA256:
`2f5522ef4fbec5ee1f79ab3d77c1ffd0857d749979848c238761dc9131f54620`.
Geometry/signature checks passed; visual content was NOT_TESTED. Warmup and public
generation are two distinct operations, not two public acceptance requests.

Ada monitoring retained 19 samples from **19:39:23.648959 to 19:40:51.483076 UTC**:
33–72 °C and 9.20–299.54 W; bounded stop threshold 85 °C. No captured kernel GPU
errors or telemetry loss occurred. Canonical warmup sampled cgroup swap at zero.
This is a short warm/load interval, not sustained thermal or memory-peak proof.

The incidental 19:43:07–19:43:12 UTC Qwen observation measured **5.138 seconds**.
At 100 ticks/s, scheduler PIDs accumulated 2/1 process ticks: approximately
**0.389% / 0.195% of one CPU**, respectively. Main threads stayed in
`do_poll.constprop.0` with zero thread-tick delta; thread sets were unchanged.
Each scheduler retained **61,008 MiB process VRAM**. This is **PRELIMINARY**:
no formal 600-second transition, all-three quiet window, retained cache proof,
immediate wake or renewed busy interval is established by it.

The repair activation's last VM contact was **19:44:30.006989Z**, and its window
closure receipt was emitted at 19:44:56.947265Z. No active task/lease remained.
The final guard passed with the existing below-6-GiB root-free warning; this does
not authorize storage cleanup or changes to the paused installer.

## Inherited qualifications, not fresh H005 capacity acceptance

The [2026-09-21 dual-Q measurement](../reports/dualq-480k-20260921.md) remains
historical: 480,000 configured tokens per Qwen, 479,408 input each, occupied
479,490/479,495. Q1's strict-JSON outer-fence failure remains, despite its semantic
pass. Those measurements were not retaken on the H005 runtime. No large-context,
simultaneous decode, new throughput or capacity claim follows from short checks.

The [dated generation qualification](../reports/image21-qualify-20260923/RESULT.md),
[Full HD report](../reports/image21-fhd-20260923/RESULT.md),
[edit capacity report](../reports/h003-edit-capacity-20260923/RESULT.md) and
[guarded editing acceptance](../ai-harness/docs/acceptance-v0.0.3.md) remain inherited.
Generation profiles: 1024×1024, 1024×576, 1216×704, 1472×832, 1760×992 and
1920×1080. Public ceiling remains 2,073,600 pixels; Full HD uses native 1920×1088
with eight bottom rows cropped (native cap 2,088,960 pixels). Qualified editing
is one reference at 1024×1024 or 1536×864, or two references at 1024×1024, opaque
output only. No masks, transparency, UHD or larger edit qualification is added.
The historical original-seed failure and ancestry/seed workaround limitations
remain. Capabilities retain historical qualification runtime digest
`sha256:dafbccb763cff6a6aa3777c7c0a8cc185d838bd4b9f61bec8007f57f2c7233f8`;
that is **not** the running repaired image identity. H005 newly exercised only
the existing default generation geometry; the final bounded edit sanity is pending.

## Latest harness update

Root accepted watcher failure/restore PASS and supplied `WATCHER-RESTORED.json`: a
fresh attestation matches the current complete table, with reviewed source and
initial policy render unchanged. Policy stayed unchanged while the watcher was
stopped. Old/new raw nft JSON digests are not directly comparable across the
intentional restore delete/recreate because kernel handles regenerate. The
restoration receipt is not substituted for unrelated lifecycle checks.

`ADMIN-EXPOSED.json` records trusted-LAN admin OPEN, unchanged main/status source
identities, settled test fixtures and no private state reset. Local harness/search
readiness projection remains unknown and VM control ready remains null, pending
typed functional checks. `IMAGE-LANE-READBACK.json` reports idle, uncertainty zero,
and all 18 preexisting terminal image jobs (17 completed, 1 cancelled); root
confirms those jobs unchanged. The shutdown-only image-lane marker legitimately
auto-reconciled with uncertainty false plus ready **and** idle. This was not an
uncertain-owner clear, passive availability alone was insufficient, and no image
request, explicit reconciliation action or SQL state reset was performed by that
task. Historical workspace quarantine count **1** remains. Do not describe every
old image quarantine marker as unchanged.

## Remaining live gates — all PENDING

| Gate | Receipt needed before changing status |
|---|---|
| Typed scoped actions and independence | Every required scoped action/refusal, idempotency/CAS and canonical settlement; healthy text peer continuity; independent status/control during downtime; local harness/search/status behavior; explicit image quarantine reconciliation while retaining pending approvals/history |
| Serial typed self-reboots | ai-vm first, then ai-harness, one at a time through the typed path; changed boot IDs, restored desired warm services/history, retained containment, latches/holds/uncertain outcomes accounted for |
| One formal quiet window | All three warm for **at least 660 seconds**, passive 5-second polling throughout; exact scheduler PID/TID deltas below **5% of one CPU** after blocking, 600-second transition and retained cache/VRAM demonstrated |
| Immediate wake and renewed work interval | Bounded work for both text schedulers and image immediately after that window; response, renewed busy interval and final all-three-warm state. One qualified bounded image edit may supply the image wake; it has not run |

Worker2 owns the remaining typed lifecycle checks; their completion receipts
were not supplied at this checkpoint. Root steering retains the raw NETWORK and BROWSER
results as **INCONCLUSIVE**, separately from the accepted packet-causal conclusion.
Its PRIVATE accounting is 64 detailed checks; a 65-row summary includes the
summary itself and is not an additional check. These counts are not combined
with other overlapping suites. Root's accepted packet-causal denial is narrow:
Slirp's owned host connect was rejected with local ICMP port-unreachable while
trusted connections succeeded before and after; Slirp presented this as a client
timeout. Source fixtures or that denial alone do not close any gate above.
Hardware fault injection, repeat 480K benchmarking and sustained GPU stress are
outside this acceptance. Shared-driver failure remains a limitation.

## Hardware, preservation and publication

The [dated four-card table](../reports/h005-service-resilience-20260925/hardware.md)
separates measured loaded links from endpoint capability, decimal transfer rates
from capacity, and core sampling intervals from unavailable memory temperatures.
Its first three cards reuse H004; only the Server card has the new H005 brief
transfer sanity. It remains unassigned and ECC is unchanged.

Retain pending approvals, current quarantine state, historical failed/unknown results,
operation journals, boot intent, latch provenance and original qualification
receipts. Rollback must use current canonical owners and matched sources; old
snapshots must not overwrite current journals, intents, latches or chat data.
No automatic replay or global reset/cleanup is authorized. Root reviews this
checkpoint and appends final exact receipts in a follow-up before publication.
