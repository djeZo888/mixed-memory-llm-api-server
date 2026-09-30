# H003 editing diagnosis — guarded feasibility, original regression still failed

The exact original teapot input, instruction and seed42 remain a retained **FAIL**.
Changing only its edit seed to43 produced the requested blue teapot while retaining
major geometry, soft background, table and lighting; Worker1 and root accepted
that diagnostic counterpart. Fresh D05 independent-photo and D06 follow-up edits
also passed Worker1 visual review. Their raw/input/delivered PNGs and compact
metrics were made available immediately for independent root review, pending at
this checkpoint. These results support guarded feasibility; they do not establish
an intrinsic repair, full editing support or permission to enable public edits.

The original source was generated using CPU seed42 at the same1024 square size.
The source audit found that omitted edit seeds inherit native42. The unchanged
candidate at implementation commit35b461e2057030774404c23fbda290887217992d draws one
random32-bit seed only after validation when an edit omits it, and reports the
actual seed in additive `data[0].seed`. Explicit seeds, including42, are never
changed. Generation defaults, responses and all six accepted profiles remain
unchanged. Root approved this narrow policy; the candidate is **not deployed**.
The present commit adds evidence only and changes no product code or tests.

The future harness must persist actual seeds, avoid known source/ancestor seeds
for automatic choices, and reject explicit known collisions before dispatch with
`source_seed_collision`. The API has no provenance registry and cannot guarantee
avoidance for unknown provenance. No harness is implemented here.

## Bounded evidence

| Entry | Request | Result |
| --- | --- | --- |
| Original | Exact teapot/recolour/seed42, prior RGBA SGLang, RGB SGLang and pinned Diffusers | FAIL, artifacts and original criterion unchanged. |
| D01 | Staging only, no GPU dispatch | Storage guard rejected root traversal into native-owned evidence. Attempt retained; excluded from GPU budget per root clarification. |
| D02 | Native VAE-only roundtrip of original RGB | One encode/decode, zero denoising steps. Faithful; MAE0.661/255, RMSE1.271/255. |
| D03 | Original source/settings/seed42, identity instruction | 40steps; severe coarse texture/contrast/sharp background. FAIL. |
| D04 | Original source/recolour/settings, only seed43 | 40steps; blue pot and scene preservation PASS counterpart, root agrees. |
| D05 | Independent natural astronaut photograph; orange suit fabric→dark blue; seed45 | 40steps,27.351s HTTP/27.002s native; Worker1 PASS, root review pending. |
| D06 | Exact D04 delivered PNG; blue teapot→green; seed44 | 40steps,27.874s HTTP/27.520s native; Worker1 PASS, root review pending. |

Actual GPU requests **5/6**, with **one reserved**. D05 and D06 each made exactly
one request, unchanged numerical recipe:1024x1024, one reference, n1,40steps,
CPU initial-noise RNG, guidance1/trueCFG1, negative prompt absent, native BF16/FP32,
torch_sdpa/eager, no tiling/offload/approximate cache. No retry, warmup, runtime
sweep, capacity test, model download or source/service deployment occurred.
Each hypothesis, exact input hash, prompt, seed and helper hash was declared in
DIAGNOSTIC-LEDGER.json before its call.

D05 uses the NASA Eileen Collins natural photograph distributed as scikit-image's
astronaut sample. [Official upstream documentation](https://scikit-image.org/docs/stable/api/skimage.data.html#skimage.data.astronaut)
identifies it as public domain. The original512x512 RGB bytes and hash are retained;
root explicitly authorized a test-only, aspect-preserving LANCZOS2x working copy.
There was no crop, padding or model generation. License, pinned source URL,
original/working hashes and preparation are in d05-fixture/PREPARATION.json and
LICENSE.md. This authorization does not change product-upload resize approval.

D05 changed suit fabric to blue while retaining the face, hair, pose, suit shape,
patches, neck ring, helmet, flag, shuttle model, background and lighting
perceptually. Minor texture/detail drift is visible; no severe global contrast,
texture or coherence artifacts. D06 changed the pot to green while preserving its
major body/spout/handle/lid geometry, table, blurred window and soft lighting.
Minor surface/reflection drift remains; no severe artifacts. The D06 reference
is byte-for-byte D04 delivered RGB, without resampling or re-encoding.

The delivered files are opaque1024 RGB. Native outputs remain preserved as RGBA;
D05 alpha ranges248–255 and D06 ranges253–255. Existing RGB normalization drops
alpha without changing native RGB pixel values, verified on both fresh outputs.
No transparency support is claimed. Output hashes and exact prompts/settings are
in the ledger, artifact manifest and compact d05/d06 summaries.

## Margins and restored ownership

D05/D06 each sampled minimum device-free9,602,531,328bytes (**18.64%**) and peak
used41,924,493,312bytes. Host minimum available was97.260%/97.263%; host/cgroup
swap remained0. Device200ms/host1s samples do not observe between-sample peaks.
These satisfy the5% device/15% host margins for these calls, not new geometry or
reference-count capacity qualification. D02 minimum device-free19.30%; D03/D04
18.64%; previous evidence remains intact.

D05/D06 used the canonical lifecycle lease and installed registered-storage/root
checks. They froze only the idle API admissions process. Before thaw, each required
HTTP200 with one decoded PNG, absent diagnostic process and restored native
GPU UUID/PID. Both used corrected in-container TERM840s/KILL5s timeout and outer855s
bound; no ambiguous HTTP-client termination was treated as GPU settlement.
Actual receipts then returned ready/admitting/idle, same API PID/start and container.

Final read-only receipt at2026-09-23T11:22:45.879569Z confirms readiness200,
all six generation-only profiles unchanged, no edit profile, original native
container/scheduler PID and both text container IDs/PIDs/start times unchanged.
Runtime config and spool are unchanged, guards passed and canonical lease was
acquired/released. The image API remains sole owner; independent backend boot
remains disabled. See final-readiness-summary.json and task-root
artifacts/post-d06-preflight.json. No text service was stopped or restarted.

D03 earlier stayed frozen after completion because its identity comparison
included a2MiB VRAM change at the same native PID. Guarded settlement verified
HTTP200,40steps,one output, absent probe and unchanged UUID/PID, then thawed the
same API. D02 completed before root's stronger timeout note was read; that
limitation is retained. D04/D05/D06 used the corrected identity comparison.

## Validation and remaining cause

The existing **13 focused offline tests passed**:5 seed contracts,7 FullHD
geometry/crop tests and1 native-wire test. They were not expanded or rerun in
this continuation because product source is unchanged. Eight earlier exact-artifact
CPU trace checks passed. Fresh receipt/pixel integrity checks verify D05/D06
opaque delivery, unchanged native RGB values and exact D06 parent bytes. None of
these substitutes for live acceptance of the undeployed missing-seed API path.

Faithful VAE reconstruction and raw-before-delivery artifacts weaken a gross
VAE or adapter normalization fault. Seed-only43 success and seed42 identity failure
narrow the issue to reference/noise sensitivity during conditioning/denoising for
this fixture. The exact internal cause is unresolved, and no numerical/runtime
repair is proven. A reporter's [upstream issue9](https://github.com/QwenLM/Qwen-Image-2.1/issues/9)
provides a related symptom, not maintainer confirmation or proof of a general fix.

Next action is root's independent PNG/evidence and exact-source review. The sixth
call remains unspent; there is no automatic next diagnostic or activation. Any
production activation requires its own reviewed concrete procedure, including
advance accounting for unavoidable lifecycle warm. FullHD editing and two-reference
capacity are separate later bounded work. Public edit profiles remain absent.
