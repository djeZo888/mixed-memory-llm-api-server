# H028 — added Ada, fan policy, status recovery and Qwen capacity

User confirms SSH recovered on both VMs after adding a second Ada 48 GB.
Requested: verify the added card and PCIe Gen4 x16; apply integrated fan boost
at >=70 C; evaluate about 250,000-token Qwen capacity with 7% VRAM reserve;
repair status page and the underlying failure after hardware changes.

Root coordinates, reviews and publishes. Both workers use isolated copies and
fresh bounded native CLI sessions. Initial task window ends 2026-09-29 00:10 UTC;
stop new inference by 00:00, reserve final ten minutes for settlement and report.
No paid sessions merely waiting. Preserve histories, credentials and old failures.

Worker1: sole ai-vm live writer. Verify network MAC/stable name and network-bound
units after recovery. Inventory all five GPUs by UUID/current PCI address, exact
SKU/usable VRAM/ECC, supported and negotiated PCIe width/speed. Distinguish idle
link downshift from loaded negotiation using one short isolated workload on the
new Ada only. Reuse existing transfer tool if readily available, no new benchmark
framework. Record temperature/errors, no multi-GPU stress or power-policy changes.
Extend existing NVIDIA fan controller by exact UUID, 100% at >=70 C and return to
firmware profile at <=65 C for30s; preserve CHA_FAN1/BMC and CHA_FAN3 policy. Fix
stale PCI/fan mappings through discovery, not a replacement hardcoded GPU index.

Worker1 capacity: reuse exact installed Qwen FP8 artifacts, runtime if SM89 supports
it, BF16 KV initially. Derive weights/cache/workspace budget from current memory
and existing evidence. Reserve7% of actual usable VRAM. One short load/allocation
and 4K or16K input bounded generation/tool continuation if candidate is feasible.
No full250K prefill, no long benchmark, no simultaneous stressing. If250K exceeds
budget, derive a lower safe cap and report it instead of forcing an OOM. Distinguish
configured allocation from occupied-context validation. Do not silently quantize
cache or change weights. New endpoint stays out of480K routing until per-instance
context admission is correct; no pretense that a smaller slot serves480K sessions.

Worker2: status diagnosis/recovery on ai-harness and source fix. Read-only ai-vm
inspection is allowed; any ai-vm mutations/deployments go through Worker1. Determine
actual failure (boot after missing network, stale PCI/index assumptions, unexpected
inventory count, parser/global health coupling), do not assume adding a GPU is the
only cause. Status must show every discovered GPU and each subsystem independently;
unknown/unassigned/absent/unhealthy devices must not crash the whole page or erase
healthy services. Preserve UUID identity and update live PCI mapping. Keep unavailable
models accurately unavailable. Fix bounded boot/network retry where needed, avoiding
busy loops and fabricated readiness. Restore the page, verify current APIs and test
added/removed/reordered/missing GPU fixtures relevant to the demonstrated failure.
Do not start/repair frontier models or weaken admission/owner checks for green status.

Shared interfaces: W1 sends inventory/fan facts and any node status error early.
W2 owns status/node projection source; coordinate patch application with W1.
Existing dual Qwen480K/image profiles and all fan/power policies otherwise remain.
No host/Proxmox/BMC reconfiguration, ECC toggles, driver upgrades, new model downloads,
full-context or PSU stress tests. Added Qwen deployment beyond bounded qualification
must be scoped to the new card and its proven context; no expansion into generic
scheduler redesign. Publish reviewed fixes and compact evidence to current branch,
not main. Explicitly list incomplete work if the window closes.

## User steering: third Qwen and external fan

The user explicitly selected 200,000 tokens for a third Qwen instance on the new
Ada, with at least7% usable VRAM free. Deploy and warm it if qualification passes;
retain both existing480K instances. Register the new instance and endpoint with
its real capacity. Eligibility must include input plus requested output allowance;
a200K backend must not receive oversized480K-session requests. Reuse existing
count/admission logic. If safe heterogeneous routing needs a broader redesign,
keep the new API/status entry available but exclude it from the shared480K pool
and report that limitation rather than misrouting requests.

User also reports CHA_FAN3 apparently80% while server Blackwell is idle. W2 owns
checking/restoring the existing harness-side controller feedback, with W1 node
endpoint cooperation. Existing40% at<=65C for30s,80% at>=70C and stale-data safe
80% policy remains. Do not force40% without fresh temperature/identity evidence.
CHA_FAN1 remains exclusively BMC/user controlled.

## Final scope clarification

The user explicitly postpones harness/upper routing work. Deliver the status page
with current hardware/model facts and a working dedicated Qwen200K API on the new
Ada, with a short benchmark. Do not alter shared gateway/engine routing. Keep
existing480K lanes as configured and new200K endpoint separately discoverable.
Private API socket recovery and appropriate bounded boot recovery remain in scope.
Do not load/repair the frontier solely to make status appear green.
