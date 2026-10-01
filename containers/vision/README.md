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
