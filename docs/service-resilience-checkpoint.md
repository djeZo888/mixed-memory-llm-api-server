# H005 Worker1 core/node source checkpoint

This source checkpoint adds UUID-scoped text/Ada pre-create admission and an
independent protected passive node API candidate. No deployment or live
acceptance was performed. Initial plan publication is separate; implementation
commits remain local pending root review. ai-harness/installer code is untouched.

Text admission now queries only the exact target UUID for identity and actual
VRAM. Host memory reservations still account for proven resident allocations.
Historical pair evidence retains its two-device identity requirement. Cold boot
continues to the healthy slot if the other fails. Ada pre-create memory/process
checks query its exact UUID; malformed/ambiguous/unknown target proof fails.
The image host-port preflight reserves only its published30007; protected bridge,
container ownership and exact publication checks are preserved, allowing node30008.
Shared-driver failure remains a limitation. Image `verify_resident` still uses a
global cross-device process ownership proof; complete image startup isolation
from failed global inventory is not established.

`node_serve.py`, its fixed source closure and service template provide a standalone
loopback30008 process. Existing private transport source adds protected .60:30008.
GET uses cached memory with independently bounded boot/inventory/service/CPU/
memory and four UUID-specific GPU collectors.2s collector deadlines,5s scheduling,
15s staleness and one outstanding worker per collector prevent hung replacement
growth. Failed/stale evidence does not become absent hardware or zero activity.
Only scoped sanitized fields are projected. No native health/inference request,
lifecycle manager, storage guard or state-reconciling GET is used by collectors.
The service does not depend on chat/control/Docker/data availability.

The frozen contract and exact fixtures are in `service-resilience-contract.md`
and `tests/fixtures/service_resilience/`. The pure/protected-injected boot latch
has tested restart/reset/new-boot semantics. The typed action boundary rejects
arbitrary input and requires a durable canonical-owner receipt. Both are reusable
source components, not installed owner integrations.

## Required completion before activation

1. Wire protected latch persistence into existing canonical text/image owners,
   including boot restore/manual start/image recovery. Preserve old latch across
   service restarts and use boot identity plus fresh successful complete inventory.
   Node currently reports latch/canonical-generation unknown and does not enforce
   the new latch on existing lifecycle calls.
2. Provide independently bounded passive backend readiness, installed capability/
   profile and canonical generation adapters. Running Docker/systemd state does
   not mean ready/idle; production node intentionally reports readiness/activity
   and unknown installation fields conservatively. Disk/network rates are null.
   Harness must not use this aggregate telemetry as its sole readiness gate.
3. Complete canonical typed actions under existing lease/owners: replay-before-
   stale checks, protected audit, affected-lane freeze, boot/generation comparison,
   control service management, image owner delegation, dedicated reset safety,
   orderly self-reboot and later changed-boot completion. Default actions here
   return422. Injected fixture owner behavior is not production dispatch proof.
4. A fresh runtime task must bind the600s policy to exact complete native text/image
   schedulers and asynchronous work/event sources. See `adaptive-idle-source.md`.
   Its current policy/patch is inactive; no runtime/config/weights/context altered.
5. Root must review the exact critical source/runtime bytes and a minimal protected
   provenance transition before deployment. **These lifecycle/control/image source
   changes already change acceptance identities**, independently of future runtime
   overlays. Existing acceptance receipts must be preserved; regenerated offline
   fixture receipts are not deployed acceptance. Do not bypass hashes, forge
   source receipts or relabel historical occupied-context measurements.
6. Review additive network policy/receipt/source migration for node30008. The new
   fixed policy intentionally differs from currently installed policy; copying
   source alone is insufficient. No installer or host activation is included.
7. Fresh authorized deployment/live acceptance must cover partial hardware, API
   integration and interruption handling, serial lifecycle/reboot, and the planned
   >=11-minute idle/wake/cache checks. None was run in this source task.

Offline validation includes actual loopback authenticated HTTP, fake clock/event
and hanging collector fixtures, target-specific NVIDIA command assertions,
partial cold-start continuation, empty-success versus failed inventory, boot latch
persistence, and durable fixture action idempotency. Private transport checks are
fixtures; no firewall, systemd, Docker or GPU host mutation was executed.
