# H003 bounded diagnostic plan

Read ROOT-PLAN.md and current source/evidence on 2026-09-23. Base is exactly
8376682ec47e59ff9c9e5dcffec3b0534d4b4ded. Session
01a0cdd6-5726-7852-823a-2abf603b3fcd. Worker1 retains implementation, test and VM
ownership; one local read-only advisory source reviewer performed no mutations.

## Established trace and hypotheses

The adapter validates upload pixels/dimensions but forwards original bytes in
multipart order. Its 1024-square output drops alpha and re-encodes RGB; it does
not resize. The prior normalized RGB file is byte-exact and has no orientation
metadata. Native load applies EXIF transpose, RGBA conversion, then a shared
VLM/VAE resize to output area/multiples32. For this square1024 reference that
resize is identity. VLM white-composites alpha; the VAE receives four channels,
[-1,1] BF16, posterior mode, channel mean/std normalization and flattened latents.
Native decode reverses scaling, decodes BF16, clamps and maps [-1,1] to [0,1].
The old Diffusers result bypassed the adapter and failed similarly. Adapter
corruption alone and RGB normalization are therefore weakened hypotheses.

H1: The pinned RGBA VAE reconstruction/normalization itself creates harsh texture
and contrast from this specific image. A native VAE-only reconstruction removes
prompt/denoiser causality. H2: If H1 is weakened, prompt/VLM conditioning or the
reference-conditioned denoising distribution creates the artifacts. Scheduler,
precision and latent-statistics source parity will remain explicit uncertainties.
No CFG requirement or defect has been established. Negative prompt at CFG1 would
not discriminate. Do not replay the old full edit or runtime comparison unchanged.

## Initial request (D01, one ledger entry)

Exact input artifacts/original-rgb.png SHA256
9756c58b989a7656162e8777bb98fcd20671c58a9c79ae4c2d1744a63fb0d575.
Native SGLang VAE only, from the pinned resident image/checkpoint, one encode(mode)
and one decode. Native conditioning conversion, mean/std normalization, layout
roundtrip and native inverse scaling; BF16, eager, no tiling/offload/approximate
cache. 1024x1024, one reference. Prompt absent (original prompt retained in
ledger), seed42 recorded but no stochastic latent sampling/noise, zero denoising
steps. Save input-conditioning PNG, raw RGBA reconstruction and delivered RGB,
latents/normalization statistics, elapsed time and sampled resource margins.

Use a short-lived docker-exec probe in the currently owned native container;
all three production models remain resident. The extra VAE copy is diagnostic
only, bounded by a CUDA allocation cap below available device margin. No new
model/runtime/container/service architecture. Keep image admissions quiescent
by freezing the idle adapter under the canonical lease, then thaw its exact
unchanged process; this avoids a service restart and its lifecycle warm call.
Check the existing proxy/adapter state and idle status before freezing; no other
worker is authorized to submit. Recheck native ownership and guards before/after.
Failure consumes the entry; no retries. Restore readiness without invoking the
recovery helper unless required and separately coordinated/count-budgeted.

Discriminator: severe reconstruction damage supports H1; a faithful roundtrip
weakens gross VAE reconstruction damage and supports concentrating on H2. It
cannot rule out mutually inverse but inappropriate latent scaling or errors only
on denoiser-generated latents. Raw sound/RGB damaged would isolate delivery.

Subsequent calls are adaptive and must be declared individually before execution.
Reserve three calls for original-regression, independent natural-image edit and
follow-up acceptance if an attributable candidate emerges. No Full HD editing,
two-reference capacity, production deployment, or public profile enablement here.
Production candidate requires committed exact source, patch/bundle/tests and root
review before activation; finish this session at that checkpoint.

## D01 staging failure; explicit D02 correction

D01 failed before docker-exec GPU dispatch, at the installed anchored guard's
rejection of traversal through the native UID-owned evidence parent. Counted as
one consumed attempt conservatively, with zero GPU calls/steps/outputs. No service
was frozen or restarted. D02 has the same scientific hypothesis and numerical
recipe; staging now uses the established native_request.open_run_directory and
write_exclusive inside the owned container as UID1000, with surrounding registered
root checks. Root-owned telemetry/receipt stay under protected receipts. This is
an explicit corrected attempt, not a hidden retry. Three acceptance calls can
still remain after D02 plus one further discriminating request.

## D03 identity-edit discriminator

D02 faithfully reconstructed the original (RGB MAE0.661/255). Next, exact same
input hash, native resident runtime,1024x1024, n1,40steps, CPU seed42,
guidance_scale1/true_cfg_scale1, negative prompt absent. Prompt:
`Return the input image unchanged.` Single request, no retry. This intentionally
is NOT the original regression and cannot count as repair acceptance.
Prediction: if severe artifacts recur without requesting recolouring, the
reference-conditioned denoising/conditioning path is implicated beyond colour
semantics. If faithful, the original colour instruction is a stronger causal
candidate. It does not by itself separate VLM from denoiser or prove a defect.

Root's late-arriving D01 settlement review has been read. D02 had already
returned0 and proved its diagnostic context gone. D03 uses in-container timeout
TERM840s/KILL5s, outer855s, and requires completed successful response plus exact
original GPU-process list and absent probe process BEFORE API thaw. Any ambiguous
HTTP timeout/error leaves admission frozen for explicit owner settlement: killing
an HTTP client is not native cancellation. There is no automatic recovery/warm.

## D04 seed-collision discriminator (root direction)

ROOT-D04-SEED-HYPOTHESIS.md supersedes the tentative checkpoint. Root identified
https://github.com/QwenLM/Qwen-Image-2.1/issues/9 (reporter observation, not a
maintainer-confirmed defect). Its same-generation/edit-noise hypothesis fits this
fixture: preserved generation-request.json records CPU seed42,1024x1024 and
40steps. Its raw output hash is d055af...; exact RGB normalization is9756c5...
confirmed by the offline trace. D02 roundtrip clean and D03 identity edit damaged
are compatible with a denoising interaction involving the reused source noise.

D04 makes exactly ONE seed intervention: original RGB input hash9756c58b989a7656
162e8777bb98fcd20671c58a9c79ae4c2d1744a63fb0d575, original exact recolour prompt,
1024x1024,n1,40steps,guidance1,trueCFG1,CPU RNG,negative prompt absent; seed43.
No resolution change, negative prompt, model/runtime alteration or sweep.
Prediction: restored soft background/smooth pot and requested blue colour support
seed-reuse sensitivity for this case; same artifacts weaken it. A successful43
counterpart is mitigation evidence, NOT a replacement/pass for the failed42
regression or proof of general editing support. Fresh acceptance remains pending.

Root explicitly clarified a six-actual-GPU-request budget. D01 pre-GPU staging
failure remains recorded but does not consume one of those six. D02 and D03 are
2used/4remaining; D04 will be3used/3remaining. No hidden warm or retry ran.

D03 restoration correction: original settlement check incorrectly compared
used-memory as identity. It stayed frozen, then explicit guarded checks proved
HTTP200,40steps,one output, no probe process, same native GPU UUID/PID; adapter
was thawed and ready200 rechecked. The next runner compares UUID/PID only and
still requires completed successful response. Timeout/ambiguity stays closed.

## D05 declared before dispatch
Licensed NASA/scikit-image natural astronaut photograph, original hash88431cd9653ccd539741b555fb0a46b61558b301d4110412b5bc28b5e3ea6cb5; authorized test-only aspect-preserving LANCZOS512→1024 preparation recorded in artifacts/d05-fixture/PREPARATION.json. Working hash09fc2049a0c52f366a3fa38cc6cf6e2494cdd934147fe3994192965d78d03bf5.
Prompt: Change only the orange fabric of the astronaut's flight suit to dark blue. Keep her face, hair, pose, suit shape, patches, neck ring, helmet, flag, shuttle model, background, and lighting unchanged.
Seed45,1024×1024,n1,40steps,CPU RNG,guidance1,trueCFG1,no negative prompt,opaquePNG. One native request; unchanged deployed runtime. Hypothesis/discriminator and exact helper hashes declared in ledger. Fourth actual GPU call; D06 next, sixth reserved.

## D06 declared before dispatch
Exact D04 delivered RGB inputc718b9feb9c7825cb66b69b69be5e87829b811fb536fcc109346c73533a281bb, no image modification. Prompt: Change the blue teapot to green, keeping its shape, table, window, and lighting unchanged.
Seed44 distinct from known ancestors42/43,1024×1024,n1,40steps,CPU RNG,guidance1,trueCFG1,no negative prompt,opaquePNG. One native request unchanged deployed recipe. Hypothesis/discriminator/helper hashes in ledger. Fifth actual GPU call; sixth reserved.
