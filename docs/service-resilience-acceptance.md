# H005 service resilience acceptance — 2026-09-25

**PARTIAL / PENDING acceptance; Draft PR7.** This offline publication checkpoint
adds supplied repair, action and recovery receipts through **21:48:30 UTC** and root
steering through **21:49 UTC** on September 25. Qwen0's canonical recovery, one
settled healthy-peer chat, image restart, passive control readiness and typed
control restart are evidenced. Both failed Qwen0 starts and the original unknown
main stop remain historical outcomes.

**First reboot automatic restoration FAILED.** The supplied receipts confirm ai-vm changed boot
from `37e425eb…` to `56fe4c47-0751-44ed-916d-a052ef4a134c` and the canonical reboot
owner reconciled, but Q1 automatic restore failed before native startup with
`hardware_target_unknown`; `llmctl-boot.service` exited 1 at 21:37:53 UTC.
The historical probe subtype was not retained; an NVML timeout is unproven. The first readback's
stopped image was a startup delay, not an image failure: Q0, image and control
subsequently became ready independently. A single explicit manual Q1 recovery
succeeded at **21:47:54 UTC**, owner `79c32ac21e04471fa4d2deca8afa4345`.
`Q1-RECOVERY-ACCEPTANCE.json` confirms all three models and control fresh/ready,
holds empty at **21:48:30.455212 UTC**, and Q0/Ada generations unchanged. The
21:47:54 completion time comes from root steering; manual recovery does **not**
turn failed automatic restoration into PASS.

A bounded boot-only pre-start UNKNOWN-validation fix is under preparation/review.
No second reboot, harness reboot, formal 665-second quiet window or final wakes
are yet evidenced. A plan, READY state, accepted POST or SSH disconnect does not
close those gates. Earlier pre-reboot acceptance applies only at its receipt time.

The exact reviewed combined input is
`fc6896f56b1999d46ca6448ab3e6f9f9332f5acf`, from the verified supplied bundle.
It includes reviewed code through passive control readiness. Root reports the
remote PR7 head as `ac8f71a927b4eb1635936edd6eba19997e213527`, stacked on
`feature/ai-harness-v0.0.3`. The earlier `ec9943f` publication is historical.
Combined repository HEAD is not the deployed identity of every component; the
separate source and runtime identities below remain authoritative at their
receipt times. This bounded docs delta is **unpublished pending root's exact final
review and GO**. No VM/harness contact, live mutation, build, product test or model
call occurred in this task. PR7 stays draft; no PR6 update or main merge is included.

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
| Harness status/credential repair | Status component active with schema 1; credential mount/ACL compatibility repaired | Earlier activation receipt alone did not prove actions or independence; later live receipts below do |
| Local helper and typed main actions | Reviewed CAP_SETUID unit and stop-proof component active; later main stop/start succeeded, retaining then releasing the scoped hold; original unknown plus separate recovery retained | Does not close ai-vm/Qwen-peer/image or every advertised action |
| Local status/main independence | Main stayed HTTP200 during status restart; status stayed HTTP200 while main was stopped; local idempotency/CAS refusals passed | Observed HTTP availability at these boundaries, not model-serving or all-node independence |
| Qwen0 repair and peer serving | Canonical recovered start with matching stop-hold release; one ordinary Q1 chat completed while Q0 stayed held | Two failed starts preserved; no live child/compaction, capacity or reboot claim |
| Image and control restart | Typed owners succeeded with actual scoped hold release; image old-container absence/new native identity; authenticated control process identity and fresh node projection | Model readiness does not prove model inference or clear unrelated uncertainty |
| Later watcher/admin readback | Root records watcher PASS; fresh restored-policy attestation and trusted-LAN admin exposure receipts supplied | Restored raw nft digest is not comparable across deliberate table recreation; remaining typed scopes and reboot acceptance remain pending |
| Packet-causal task denial | Root accepted host rejection of the owned Slirp connection with trusted connections successful before/after | Client timeout alone was not proof; this narrow causal result is not the complete container/watcher/lifecycle matrix |
| Dated transfer measurements | Brief copy-engine bandwidth and sampled core temperatures for four cards | No sustained thermal, platform maximum, D2D/P2P or model-capacity claim |

Exact artifact names and raw SHA256 provenance are in the
[compact evidence index](../reports/h005-service-resilience-20260925/acceptance-evidence.json)
and [machine-readable acceptance table](../reports/h005-service-resilience-20260925/acceptance-table.json).
External originals remain retained by their named task; raw traces, private path
metadata, credentials, chats and backups are not copied into this public package.

## Deployment lineage and current model identities

The initial permission-repaired ai-vm successor used source
`5b20f26b36e8caedfd62ce42060ecdbe32126224`. Later host-only repairs progressed
through peer admission `91f44888e2c1ba8ce039d395a5ebef0099a442bb`, mount ordering
`014e294fdeab91942a046fa7b0b9d7f833951e82`, and control readiness
`aaa643fcd90ac4ae0a50e4a8e1a3df19ca0ebcc3`, all integrated in the combined input.
At the last pre-reboot publication, VM node/control and future-boot host source
were `aaa643f`; the image runtime host closure remained `014e294`. These repairs introduced no new runtime
build or capacity benchmark. Runtime image identities below are unchanged.
The [runtime binding](../configs/runtimes/h005-runtime-binding.json) raw SHA256 is
`9da2236e927c44e2af618e0862ee84f54d4645ec0bcb1e93c25c0d98b45ee6ae`.
The initial immutable successor release preserved its predecessor; its receipt records
136 release files and 215 installed source/config/receipt destinations checked.
These are closure counts, not independent test totals.

| Resident deployment | OCI platform manifest / receipt image ID | OCI config digest |
|---|---|---|
| Qwen3.8-27B FP8 on GPU0, alias `qwen3.8-27b-gpu0` | `sha256:0aa2afe62c04fdd4f06a38229e6941cb1e47f6b7c0863698b708f299d4f15ddf` | `sha256:8f9a45a8a4de689280c054867103fc072f064703427212aeb6d603551a86f4b2` |
| Qwen3.8-27B FP8 on GPU1, alias `qwen3.8-27b` | Same unchanged text image | Same unchanged text config |
| Qwen-Image-2.1 on dedicated Ada | `sha256:50a3bfd20fc931f05fc5fc919b0445abbce30d5c7716424d697a7ab6708c08ef` | `sha256:3f6178faa74c4a9bcb95ed4304dbee57473efa8913a793e067014af4a98281ad` |

Both Qwens retain 480,000 **configured** tokens, FP8 weights/BF16 KV, shared guest
CPUs 0–7, 32 GiB memory each with no additional swap allowance, radix cache disabled
and Mamba cache 1. Image retains CPUs 8–15 and 96 GiB memory with no additional
swap allowance. At the historical 19:41 readback, the unchanged Qwen starts were 18:45:29.790881105Z and
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

The helper's hardened unit repair is source
`45e2ee1c4ce588d2d486162e84fb51aa8795d146`, activated at 20:09:47 UTC; the stopped-owner
proof component is source `03a1c422007c15078f3b1878d72882ba3017f9b0`, activated at
20:20:29 UTC. These are distinct from the main `63dcb23`, status `c640b9c`, combined
`fc6896f`, current VM node/control `aaa643f`, image runtime host `014e294` and
image `50a3bfd` identities. The unit retains ambient `CAP_SETUID` for its fixed ordinary-user transition; activation
readbacks retain NoNewPrivileges=1 and seccomp mode 2. Main/search/status/egress/nginx
invocations were unchanged during each component activation. Later owned main
and status actions deliberately changed their invocations.

At the historical repair readback, node authenticated status returned 200 and
missing/wrong credentials were denied, but control projected availability
`unknown`, ready `null`, reason `observation_unavailable`. That conservative
unknown accurately reflected a missing passive control readiness endpoint; an
active systemd process alone was insufficient. The subsequent `aaa643f` fix and
live/typed restart proof below supersede the gap without rewriting that receipt.

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

The separate Ada preliminary receipt sampled **19:56:32.783893–19:56:37.916861 UTC**
for **5.132964 seconds**, after more than 600 seconds of witnessed inactivity.
The unchanged image scheduler accumulated 3 whole-process ticks, approximately
**0.584% of one CPU**; its main thread accumulated zero ticks, state S, in
`do_poll.constprop.0`. Process VRAM stayed **32,226 MiB**, with core temperature
38 °C. Thus the three preliminary whole-process values are Q0 0.389%, Q1 0.195%,
and Ada 0.584%, each measured over its own short interval, not simultaneously.
Witnessed inactivity and resident VRAM do not establish native asynchronous-work
counters, the formal 600-second transition, a common 660-second quiet window,
cache-retention acceptance or immediate wake/renewal. No mutation or inference
was performed in that Ada readback.

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
identities, settled test fixtures and no private state reset. That earlier local harness/search
projection was unknown; later main functionality and status/main independence
are proved below. The historical VM control ready-null gap is resolved by the
separate process-API proof below. `IMAGE-LANE-READBACK.json` reports idle, uncertainty zero,
and all 18 preexisting terminal image jobs (17 completed, 1 cancelled); root
confirms those jobs unchanged. The shutdown-only image-lane marker legitimately
auto-reconciled with uncertainty false plus ready **and** idle. This was not an
uncertain-owner clear, passive availability alone was insufficient, and no image
request, explicit reconciliation action or SQL state reset was performed by that
task. Historical workspace quarantine count **1** remains. Do not describe every
old image quarantine marker as unchanged.

## Local helper and typed lifecycle acceptance

The original local UID-transition failure is superseded by the reviewed
CAP_SETUID unit repair and actual helper activation. The later stopped-owner fix
handles normal systemd retention of the last InvocationID: successful blocking
stop must be followed by loaded, **inactive/dead**, **MainPID=0**, **ControlPID=0**
and **no pending job**. InvocationID may be empty or exactly the captured old
identity; an unrelated identity is rejected. A retained old InvocationID alone
neither means running nor proves settlement. Source fixes and their local live
outcomes are separate from source fixtures, whose counts are not repeated here.

| Exact local receipt | Observed outcome, UTC | Scope and retained limitation |
|---|---|---|
| `REPAIRED-TARGETS.json` | Repaired target catalog advertises typed actions | Catalog availability is not successful execution; unknown activity/null counters stay unknown |
| `MAIN-STOP.json` | Original stop accepted 20:10:44.149, ended **UNKNOWN** 20:10:45.848 with dispatch frozen | Original operation `be7ee28d…` remains unknown; later source fixes do not rewrite it |
| `MAIN-RECOVERY.json` | Separately confirmed restart `2069390e…` succeeded 20:11:30.879 and released its hold | Observer expected HTTP202 but received HTTP200; a read recovered the existing operation, with no second POST or automatic replay |
| `IDEMPOTENCY-CAS.json` | Exact repeat returns the original **UNKNOWN**; mismatched key gets 409 `idempotency_conflict`; stale generation gets 409 `node_action_conflict` | No new lifecycle operation accepted; readiness did not settle the original uncertainty |
| `STATUS-RESTART.json` | Status restart succeeded 20:18:21.420; observed status outage then HTTP200, while main remained HTTP200 | Status scope only; demonstrates main availability during status downtime |
| `MAIN-STOP-ACCEPTANCE.json` | New typed main stop succeeded 20:20:41.480, dispatch hold retained | Exactly harness scope; successful current operation is separate from the historical unknown |
| `MAIN-DOWN-STATUS-UP.json` | At 20:21:04.634, status HTTP200 while main HTTP502; fresh main unavailable/ready null and dispatch frozen | Demonstrates status availability while main is down; never calls an unreachable main idle |
| `MAIN-START-ACCEPTANCE.json` | Typed main start succeeded 20:21:11.493, dispatch hold released | Canonical action completion and validated start, not passive readiness alone, release this maintenance hold |

Root accepts the local helper, main stop/start with hold release, and both
status/main independence directions as **LIVE PASS within these scopes**.
Original unknown outcomes, separate confirmed recovery and historical workspace
quarantine remain evidence. This is not acceptance of one-Qwen peer continuity,
every advertised target or reboots. Later scoped VM evidence follows.

## Qwen0 failed starts, canonical recovery and healthy-peer serving

`QWEN-STOP.json` records scoped Qwen0 stop `305542ba…` succeeded at
20:21:51.500 UTC with its dispatch hold retained. The original start
`b5c1acdc…`, canonical owner `1fd56c215c914b18b748570177ca7c83`, failed at
20:22:21.509 with public `operation_failed`. Its own `dispatch_frozen=false`
did not clear the separate stop hold. `CAUSE.json` independently reproduced
`untrusted_concurrent_peer` using installed read-only admission: legacy text-pair
logic rejected the approved dedicated image GPU peer. This is not recovered
original stderr or a replay of the failed operation. The 20:23:18 failed-start
status recorded Q0 unavailable/ready false with Q1 and image ready; the earlier
`QWEN-HEALTHY-PEER.json` proved only peer readiness, not the later actual chat.

The reviewed `91f448` host repair introduced canonical dedicated-image peer
proof. A separately owned start `215894c9…`, owner
`a086e26b44104d8d9d76ad0b5e12e0b2`, then failed on Docker `Mounts` list ordering
alone: all complete entries matched by destination, with state/network identity
unchanged. `014e294` compares complete entries sorted by destination, preserving
cardinality and field validation. Both failed receipts remain failed and retained;
neither was rewritten into the later success.

The fresh canonical owner `094af8cf01974fb6920bbd10e4e12146` succeeded at
**21:10:22.546965 UTC**. It restarted the original Q0 container `ae049b4e…`,
with PID **1654611** and start **21:09:46.328601336Z**, unchanged text image,
and slot generation 26, desired running / observed ready. Q1 and Ada native
identities remained unchanged through these repairs. Worker2's matching validated
start released the original stop hold; the active hold list was empty at
21:10:42.819517. Failed audit rows remained unreleased historical failures, which
are distinct from active holds. No inference or new capacity test occurred in
Worker1's recovery.

Separately, `PEER-SERVING.json` proves one ordinary main chat returned `OK` on
`qwen3.8-27b` while Q0 stayed held, with exactly one messages POST and no
retry/replay, tools or child activity. At **20:43:35.951294 UTC**, the run was
completed, both gateway lanes were idle, active requests and queue depth were zero,
and the Q0 hold remained. The first terminal-run snapshot still had one active
gateway request; the final settlement closes that drain interval without another
POST. Live peer chat is now PASS; child/compaction routing remains fixture-only.

## Typed image restart and passive control readiness

Typed image restart owner `5ac77ee01c9d432c8bd6ae89f35a0686` succeeded at
**21:18:58.405316 UTC** with scoped hold release. Worker1's native proof confirms
exact old container `088d61f2…` absent and new container `398bc85a…`, PID
**1748673**, start **21:18:01.932742426Z**, run
`d7cbbeadca7a46239ba35748cba8a6bb`. The image stays `50a3bfd…` with OCI config
`3f6178…`; Qwen generations/identities and image placement/limits are preserved.
This action sent no public generation. Image lane idle, uncertainty zero, and
17 completed / 1 cancelled historical jobs remain in its acceptance receipt.

Source `aaa643f` adds passive authenticated control process readiness and binds
the node observation to boot ID, systemd invocation and PID. Its supplied offline
validation records **47 focused tests PASS**, not rerun here or added to overlapping
suite totals. At **21:27:26.363256 UTC**, live API identity matched the current
boot and control invocation `008df617…`, PID **1857836**; missing/wrong credentials
both returned **401**. Node control was fresh, available and ready true, while
activity/counters remained unknown/null. Activation preserved native model
identities and introduced no inference, model restart or reboot.

Worker2 then completed a typed control restart at **21:29:48.622 UTC**:
relay `e93cfd55…`, canonical owner `380e058cd9984d91b1540fa97b7586f4`.
The 21:30:16 local-state receipt records actual `validated_owner_readiness` hold
release, no active holds, no task containers and zero nonterminal runs. Root's
supplied summary additionally records 100 node HTTP200 samples and all model
identities unchanged during this restart; those details are root-supplied
acceptance, not a newly executed observation by this publication task.

The normal main drain/stop/start preservation is root-accepted. The supplied
pre-reboot metadata snapshot records 25 sessions, 131 messages, 47 runs and
60 files (48 artifacts / 12 attachments), one historical workspace quarantine,
and 17 completed / 1 cancelled image jobs. It is a non-atomic metadata-count
snapshot, not a content readback, new backup or post-reboot preservation proof.
Original unknown main-stop and both failed Q0 histories remain. Current action
success never authorizes automatic replay of those outcomes.

## First typed reboot failure and distinct manual recovery

`w1-reboot/FINAL-ACCEPTANCE.json` records canonical reboot owner
`a8af1d3585a64d50825aedb819e0a21d` succeeded through dispatch and changed-boot
reconciliation. Automatic model restoration nevertheless failed at
**21:37:53.657238 UTC** under host source `aaa643f`. The confirmed Q1 failure is
`hardware_target_unknown` at its exact-UUID admission probe before native start;
the historical probe subtype was not retained. Stale prior-boot validation in
the failure capture is not proof of a GPU hardware fault. The initialized latch
marker and historical operation semantics were preserved; no latch reinitialization
or implicit retry was performed. By the 21:43:08 read-only view, Q0/image/control
were ready and hardware latch projections were false; Q1 was still stopped.
The initial image delay must not be reported as image startup failure.

That execution closed **HALTED_NOT_ACCEPTED** at 21:44:23.239083 UTC, without
starting harness reboot, quiet measurement or wake requests. Its historical
`final_all_three_warm=NOT_ACCEPTED` is preserved. Later Worker2 acceptance is a
separate **manual recovery PASS**: owner `79c32ac21e04471fa4d2deca8afa4345`, relay
`ff5d5c9b…`, actual validated-owner hold release, fresh readiness at 21:48:30.455212,
no task containers/nonterminal runs and zero model requests or replay. Historical
quarantine count 1 and image jobs 17 completed / 1 cancelled remained. The
recovery window closed with no outstanding requests; it explicitly retains
`reboot_restoration_pass=false`.

## Remaining live gates — PENDING receipt-backed completion

| Gate | Receipt needed before changing status |
|---|---|
| Serial typed self-reboots | ai-vm first, then ai-harness, one at a time; actual changed boot IDs, canonical operation reconciliation, restored desired warm services/history and containment, latches/holds/uncertain outcomes accounted for |
| One formal quiet window | One **665-second** run (at least 660 seconds), all three warm, passive 5-second polling after real work; exact scheduler process and main-TID CPU deltas in units where 100% is one CPU, below 5% after blocking, 600-second transition, block state and VRAM observations |
| Immediate wake and renewed work interval | One tiny normal authenticated request to each exact Qwen endpoint before and after quiet, plus Worker2's qualified 1024×1024 edit through the harness; response/settlement, renewed busy interval and final all-three-warm state. VRAM residency alone does not prove cache contents |

The supplied failure and manual-recovery receipts preserve those distinct
outcomes. Root's latest `STEERING.md` describes a boot-only source correction;
it is not part of this report's reviewed `fc6896f` input. Final gates remain
**PENDING** until actual subsequent execution receipts arrive. No lane-selector
work or assumed second reboot is included, and the first automatic restoration
failure remains failed regardless of later recovery.

Unexercised advertised local/search actions, hardware fault injection, live
child/compaction routing and repeated capacity or sustained GPU stress are not
silently promoted by the accepted scoped actions above.

Root steering retains raw NETWORK and BROWSER results as **INCONCLUSIVE**,
separately from the accepted packet-causal conclusion. PRIVATE accounting is
64 detailed checks; the 65-row summary includes itself and is not an additional
check. Counts from overlapping suites are not added. The accepted packet-causal
denial is narrow: Slirp's owned host connect was rejected with local ICMP
port-unreachable while trusted connections succeeded before/after; Slirp presented
this as a client timeout. Neither source fixtures nor that denial closes a pending
gate. Shared-driver failure remains a limitation.

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
No automatic replay or global reset/cleanup is authorized. Root reports Draft PR7
at `ac8f71a`; reviewed combined input `fc6896f` and this docs-only follow-up remain
unpublished pending exact root review and explicit publication GO. Serial reboot
and formal quiet/wake receipts are still required before final acceptance; the
first automatic-restoration failure is preserved and its source correction/retest
remain pending.
