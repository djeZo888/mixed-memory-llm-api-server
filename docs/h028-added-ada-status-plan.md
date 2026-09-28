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
