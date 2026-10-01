# H039 isolated candidates

Build context, if root later authorizes an isolated build, is the repository
root with `containers/vision/Dockerfile.candidate`. No image was pulled or built
in this source preparation. The default entrypoint prints candidate arguments;
it cannot start inference. There is no Compose activation or production unit.

The immutable official vLLM amd64 image is a candidate, not evidence that its
CUDA/PyTorch/FlashAttention/FLA/Mamba closure supports both pinned artifacts on
SM8.9. Root must inspect its package versions, compiled architectures and BF16
support before an approved load. Do not use Blackwell-only `120a` llama images,
FP8-only profiles, model-card `latest` tags or automatic installation into the
existing image/text services. No upgrade to Sova's Codex 0.158.0 is involved.

Both resident services must share one measured budget: proposed 0.72 Qwen plus
0.18 OCR leaves 10% nominal space, exceeding the requested approximate 7%
reserve. Fractions are an initial experiment, not a guarantee; allocator,
profiling and peer-process memory can still prevent startup. Measure total
device and peak process memory and keep at least 7% (3,440 MiB of the observed
49,140 MiB) free at the worst accepted workload. Try serial crops and 16K total
Qwen tokens first, then 32K only after it passes. Never grant each service 93%.

Only the approved two HF repositories are present. PaddleOCR's full-page
pipeline can download a separate layout model; do not instantiate that pipeline
here. The candidate uses the native vLLM PaddleOCR architecture for element/crop
recognition with processor metadata, text/table/formula/chart prompts. A bridge
must wrap raw recognition text with source coordinates and exact revision;
raw OCR text is not inherently JSON and does not establish connectivity.

Review the pinned official Python files before any remote-code execution.
Candidate argv deliberately omits `--trust-remote-code`: native vLLM support is
listed at the inspected source revision, but exact container compatibility
remains a gate. Fail closed if the pin requires a code path not yet reviewed.

H043 adds a separate disabled `configs/vision/h043-candidate.json`; H039 config,
artifact history and digest are preserved. `runtime_plan.py --config
configs/vision/h043-candidate.json` prints exact proposed model argv and a source,
model, ingress, service, shutdown and rollback owner graph. It executes nothing.
The proposed vLLM key transport is a protected supervisor FD-to-environment
injection (`VLLM_API_KEY`), not a secret in argv. Its support in the candidate
image still requires review; no invented `--api-key-file` option is used. Disable
request/access logs and isolate all other runtime routes behind a private network.

The Python service and backend have no general inference CLI, container launcher,
artifact reader or process stop helper. A later reviewed launcher must construct
`PrivateLedger`, `LocalVisionBackend`, `VisionService`, and `BoundedHTTPServer`
with host-only keys and keep `enabled=False` until live gates pass. Loopback
`18193` is the job service; loopback `18191`/`18192` are the fixed model services.
The existing real TS client accepts only `10.156.100.60:PORT`, so a separately
owned private-interface ingress bridge is required. Proposed ingress binds only
`10.156.100.60:18193`, forwards only the five version-1 routes to loopback,
authenticates the host bearer, allows only the approved host address, caps body
and total request time, preserves exact multipart bytes, and has no general
proxy or secret/payload logs. It is a proposal, not an implemented remote route.

H043 accepts one page up to 2,097,152 pixels, edge 4096, at most eight crop requests
and one image per model prompt. Qwen total context is 16,384, Paddle 8,192,
max output 4096, and service concurrency one. Inputs exceeding this runtime
profile are rejected before dispatch; the wider H039 host transport limits are
not a measured GPU profile. Crop calls are sequential. Qwen content is strict
JSON description, uncertainties and derived conclusions. Paddle returns literal
raw crop text. Known supplied input regions are evidence, never invented text
bounding boxes; component/connectivity extraction stays empty and unqualified.

Budget review must include actual BF16 tensors, vision encoder/activations,
16K/8K KV and recurrent caches, CUDA graphs, allocator/runtime fragmentation,
peer ownership and whole-device peak telemetry. The nominal .72+.18 allocation
is only a proposal. Keep >=7% (3440 MiB of 49140 MiB) free at accepted peaks;
if simultaneous residency fails, separately review sequential residency and its
owned lifecycle before any starts. Stable Ada UUID remains
`GPU-14c23cbc-12f0-9c61-0fda-7aaf80fbd1bf`; external Ada
`GPU-5d895991-b794-2b4c-b9c4-5f1b668afd23` is reserved for Qwen-Image2.1.
No existing owner was contacted, stopped or changed.

The [pinned Qwen model card](https://huggingface.co/Qwen/Qwen3.5-9B/blob/c202236235762e1c871ad0ccb60c8ee5ba337b9a/README.md)
requires a sufficiently recent vLLM source. Current
[vLLM architecture docs](https://docs.vllm.ai/en/latest/models/supported_models/)
list Paddle OCR; that does not qualify the candidate digest. The official
[Paddle tutorial](https://github.com/PaddlePaddle/PaddleOCR/blob/main/docs/version3.x/pipeline_usage/PaddleOCR-VL.en.md)
distinguishes element recognition from the separate layout pipeline. H043 uses
only bounded crop recognition and does not download or construct layout models.
Runtime architecture, processor/chat-template, authenticated routes and kernels
remain pending for the exact pinned artifacts and container on SM8.9.
