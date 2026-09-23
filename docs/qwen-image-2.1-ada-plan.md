# Qwen-Image-2.1 on RTX 6000 Ada — approved execution plan

Approved 2026-09-23. Mac-Orchestrator plans, reviews and integrates; fresh remote
Codex CLI sessions on both Mac workers implement, build and test. This authority
supersedes earlier new-model exclusions only for this image service and necessary
three-GPU compatibility. ai-harness/MiniMax integration and installer work remain
deferred. First-party additions remain MIT; model license is tracked separately.

## Current bounded follow-up

The original execution and ladder below are historical. The Full HD follow-up
supersedes the public ceiling: 1920x1080 / 2073600 pixels, with exactly native
1920x1088 / 2088960 pixels followed by removal of eight bottom rows. Preserve the
five smaller opaque profiles. Editing/transparency remain unqualified; UHD and
public1088 are refused. Both original text Qwens and the image model remain
resident. No new memory benchmark, runtime/model changes or repeated inference;
see [current report](../reports/image21-fhd-20260923/RESULT.md).

## Historical facts and first tasks

Read-only inventory found driver 595.84, 72 guest vCPUs and three GPUs. Blackwell
UUIDs are GPU-88058d9d-08e5-cb1e-a77a-04cbc1488237 and
GPU-69acfa26-8b60-61b5-702d-aee252c163cc. Ada is
GPU-5d895991-b794-2b4c-b9c4-5f1b668afd23 with 49140 MiB VRAM. Both text containers
are stopped and llmctl-boot.service failed. Two-GPU-count/ordinal assumptions in
concurrent_profiles.py must be replaced with required-UUID validation and memory
lookup. Existing GPU assignments and 480000 contexts remain unchanged. Critical
source receipt changes require a reviewed amendment, not a hash-check bypass.

Worker1 first uses an EXISTING tool (NVIDIA nvbandwidth or CUDA bandwidthTest)
for host-to-device and device-to-host measurements on all three GPUs. No bespoke
benchmark implementation. Warm up, use available 32/256/1024 MiB pinned-memory
cases with five samples, report median/range and tool-supported pageable data if
available. Same CPU/NUMA policy; capture loaded PCIe links. No disk/network time
in transfer rates. Measurement budget about ten minutes; omit unsupported optional
cases rather than coding another utility. Device-to-device/NUMA tuning is deferred.
Worker2 prepares the compatibility fix in parallel. After root review, Worker1
deploys the fix and restores both Qwens; tiny API checks replace old large tests.

## Resident image runtime

Separate pinned SGLang-Diffusion container on Ada only, selected by UUID:
- SGLang 0cd8be351d0825488f4b81c8931167bbab618eca.
- Qwen/Qwen-Image-2.1 790c92633540aa0cb11d9abf19eb46d861714758.
- Freeze dependency lock, checkpoint hashes and built image digest.
- Native BF16/FP32, torch_sdpa, eager, all components resident. No CPU offload,
  quantization, model swaps, approximate caches or graph/compile tuning initially.
- One active image/one output, 40 steps, CFG 1; initial CPU mask 8-15,
  host cap 96 GiB, no container swap. Existing text limits remain unchanged.
- Preserve the agreed 15% host-memory headroom. GPU headroom is separate: user
  revised the Ada minimum to 5% of observed total VRAM (2457 MiB at this inventory).
- All writes use registered model/data/service/log roots and existing guards.
  Retain ordinary least-privilege service ownership and protected credentials.
- Dedicated systemd owner, warm on start, retain residency after acceptance.
  No SSH keeper or changes to existing text runtime/driver.

One diagnosed SGLang repair is allowed, then one isolated Diffusers reference
trial for runtime failure (8b3c707ebd3ec4881f4190cf42931da07eaf3b65, separate
dependencies). No runtime sweep; no automatic CPU offload to force larger sizes.

## Resolution and memory qualification

User confirmed 4K means UHD 3840x2160, not 4096x4096. First establish 1024x1024
generation/editing. Then use a 16:9 ladder beginning 1024x576, increasing width
and height approximately 20% per rung (nearest supported alignment; retain actual
dimensions), capped by the exact 3840x2160 endpoint. If exact UHD dimensions are
not natively supported, report that constraint and qualify an explicitly documented
internal pad/crop path, never silently mislabel output resolution.

Use one generation and one single-reference edit per rung, fixed settings and
representative fixtures; record actual dimensions, peak process/device VRAM,
host memory, warm latency and transfer activity. Keep two-reference edits at the
1024 baseline until separately qualified. A supported size requires >=5% VRAM
free at measured peak, decoded output and visual task success. Before each step,
project next demand from prior samples; if likely unsafe, stop rather than force
an OOM. An unexpected OOM marks that rung unsupported, restores image service,
and retains the last passing rung. No binary search or repeated failed attempts.
Stop at UHD or the headroom boundary. Advertise measured supported sizes only.

## Minimal API, no harness changes

Private authenticated image API on 10.156.100.60:30006, matching current private
transport policy, with a loopback-only native backend. Reuse existing protected
API key via file/credential mount, never argv. Current SGLang Diffusion has no
enforced auth and an unbounded internal queue: a thin adapter is required.

- GET /health/live, /health/ready, /v1/models and /v1/image-capabilities.
- POST /v1/images/generations (JSON), /v1/images/edits (multipart).
- Synchronous PNG b64_json responses. No permanent artifact/job platform yet.
- One active request, zero queue; 429 Retry-After when occupied. At most two
  PNG/JPEG references, 32 MiB encoded per file and 64 MiB total. Decoded pixel
  limits follow measured profiles through UHD (at most 8294400 pixels); one-reference
  edits use same-size inputs at each qualified rung, and two references remain
  1024-class unless separately qualified. Validate decoded images, qualified sizes,
  n=1 and allowlisted settings. No server paths, arbitrary remote image URLs or
  runtime overrides. Larger-reference policy only after tests.
- Reject native mask field: upstream declares it but ignores it. Marked-image
  edits are instruction-guided, not guaranteed pixel-preserving inpainting.
- Active request budget 15 minutes. Retain slot through upstream completion even
  after client disconnect. Unresolved timeout closes admission and recovers only
  the image backend; no claim of native cancellation. Adapter restart must not
  reopen admission against possibly active orphan work; reconcile/restart its
  owned backend and warm before readiness.
- Explicit additive network-policy/source-receipt migration preserves current
  control/text ports 30000/30002/30004. Image lifecycle is separate from the
  two-slot text state; reuse canonical lifecycle lock only for mutations.

## Work split, evidence and delivery

Worker1: quick bandwidth, reviewed compatibility activation, checkpoint acquisition,
runtime build/load, resolution ladder and final deployment. Worker2: compatibility
source, then fresh API/service source session, then independent API verification.
Separate task directories, prompts, retained native session IDs and source bundles;
automatic compact synchronization to local orchestration files. Root reviews and
integrates each bounded result before dependent deployment.

Acceptance: generated/edit PNGs with visual checks; transparency/two references
advertised only after passing; auth/busy/input/disconnect/restart behavior; short
requests to both Qwens during image generation; device ownership, cold/warm timing,
RAM/VRAM and no-swap evidence. No replay of 480K text benchmarks. Initial GPU/API
qualification budget 90 minutes excluding downloads/builds; optional higher-size
tests dropped first, missing evidence reported rather than hidden retries.

Publish plan, reviewed code, pins, settings, results and CLI examples in this
repository. Keep keys, weights and bulky raw traces outside Git. Final state:
two Qwens restored warm plus resident image API; then stop before ai-harness work.

Sources: https://github.com/NVIDIA/nvbandwidth ;
https://github.com/QwenLM/Qwen-Image-2.1 ;
https://docs.sglang.io/cookbook/diffusion/Qwen-Image/Qwen-Image-2.1
