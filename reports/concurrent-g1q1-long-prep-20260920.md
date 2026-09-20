# G1/Q1 long-only source preparation — 2026-09-20

Base `1002331266abaa0bd515115aea670a80fc80fa16`; source/saved evidence only. No ai-vm, Worker2 or Proxmox contact, deployment, benchmark, profiling, installer or API work occurred in this PREP.

Root's task `incoming-latest.md` clarifies the required working-set **ESTIMATE**:

```
D(sample) = max(anon + kernel + max(file_mapped, shmem),
                sum(owned process RSS) + kernel,
                pinned native host-weight + workspace floor)
D(peak) = maximum sampled D for the current owned container
accept headroom only if 5 * D(peak) <= 4 * cap
```

This is not an exact disjoint union or a proof of instantaneous reclaimability. RSS may double-count shared pages; mapped and shmem overlap. Missing required cgroup/RSS inputs prevent admission; known numeric floors can still latch pressure. Sampled demand violations remain latched through later low or missing observations. Raw current and lifetime peak remain separate, with a numeric hard-cap latch. Existing 640/32 GiB no-swap caps, OOM/swap detection, pre-load 688 GiB available reservation, 16 GiB host/GPU reserve and drain/cancellation paths remain effective. The old generic `MEASURED_COMPONENTS` helper is bypassed only for this closed campaign.

The historical same-pin G65536 floor is 429039864250 B: `ceil((409012.22 + .005) * 1048576)` for the rounded native CUDA_Host weight label, plus native exact host workspace 159461408 B. The 0.005 MiB allowance accounts for display rounding, not measurement precision. Source: `reports/glm-g1-ladder-20260920.json`, `/loads/1/native_memory`, report SHA256 `f9ed5c46c57ceb44e7af2d78838f4c65fb1bdfb1abd8734687a27401815d6cdc`; saved raw-log receipt SHA256 `f2272149566ee0892384d6b7b62432a7e1d5cfa2d71ac55897043fd7d1c2d49a`. Current accepted native allocation can increase this floor. Until readiness, the floor is explicitly historical; the aborted predecessor G64 load did not prove current allocation. Qwen's native host-weight floor remains unavailable; its observed cgroup and RSS branches remain required, with no fabricated host allocation value.

Saved predecessor `CONCURRENT-G1Q1-RUN-CONT1B-20260920/results.jsonl` SHA256 `7f6be2a7544850e672f038cbca0bfcadd6e8b57a7fccd8edfa7ee4055c407e91`, first STOP line 952, remains unchanged. Its raw current/peak was 549898883072 B. Formula replay gives 431320940544 B (401.698929 GiB), and 25% headroom gives 539151175680 B (502.123661 GiB). The 118685192192 B file-minus-max(mapped,shmem) remainder is extra charged file/cache of unproved reclaimability. Dirty/writeback/unevictable and a disjoint mapping union were not saved; no new counter claim is made. Replay is not a retroactive PASS.

The fresh fixed identity is `benchrun-concurrent-g1q1-long-20260920`, with its own `/data/services/<campaign>/source` and owner/log paths. There are exactly two admitted manifests: G65536 and Q700160. Load, warm and prove both; dispatch G near65008/schema256 alongside one near700K Q then fresh near256K fillers in the same700160 pool, maximum8 Q requests including the first. Stop filler admission when G finishes and drain. Then run one matched near700K Q with G resident idle. At most one scientific512 decode pair is allowed only if actual decode overlap was absent. No initial G16/Q256 measurements, G480, tuning or model/runtime/settings changes.

GO must retain start `1789890954.308154` and deadline `1789896354.308154` (09:25:54.308154 UTC). Both worker and host validate these exact values. A fresh RUN session is required; existing execution-arm/no-rerun protection remains. The predecessor four short PASS results, original failure and restoration receipts are separately hashed in the new arm; INITIAL progress contains no completed or inflight measurements.

Required package files are explicit in `arm.json`: arm and receipt, INITIAL progress, predecessor evidence and the private frozen G65536 fixture. Copy all of them together with the exact committed source. Preparation must be followed by the requested local stub-host constructor check before handoff. Private fixture remains outside Git. The source checks cover only formula/missing inputs/pressure latches, unchanged numeric safety behavior, closed long dispatch/profile and package initialization; they establish no live readiness or inference.

Remaining live prerequisites are root review of the concrete source/arm, current restoration/ownership/guard review and a fresh bounded Worker1 RUN within the original deadline. Saved predecessor final-restoration PASS is evidence, not a new live verification by PREP. Operator note from root: if RECOVERY_REQUIRED occurs, use the existing direct canonical recover path; do not repeat known failing restore wrappers. Preserve the underlying cause when cheap, then perform authenticated LAN verification/finalization and host/tunnel closure. No restoration source redesign is included.
