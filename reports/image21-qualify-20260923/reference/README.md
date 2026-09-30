# Rejected editing evidence

Editing remains **unsupported**. Raw RGBA SGLang, production RGB SGLang, and the completed pinned Diffusers reference all failed the instruction to preserve the scene and lighting. No edit profile is qualified, and Diffusers is not promoted. This report compiles supplied historical evidence without VM contact, image calls, or replay.

| Case | Completed outputs | HTTP seconds | Native inference seconds | Visual result |
|---|---:|---:|---:|---|
| SGLang raw RGBA reference | 1 | 28.638180 | 28.270869 | FAIL |
| SGLang normalized RGB reference | 1 | 27.346664 | 26.988528 | FAIL |
| Diffusers initial cache error | 0 | N/A | unavailable | NOT_TESTED |
| Diffusers corrected reference | 1 | N/A | 30.879442 | FAIL |

The fixed instruction was “Change the red teapot to blue, keeping its shape, table, window, and lighting unchanged.” All completed edits used 1024×1024, 40 steps, true CFG 1, seed 42, n=1, and CPU noise RNG. Actual PNG reviewers observed a navy/purple-blue pot with excessive contrast, coarse texture, changed background detail, and altered soft lighting. Color change was partial task success; fidelity failed. Exact production normalization preserved RGB pixels and did not resolve the failure.

The first Diffusers call failed before denoising because the launcher omitted `TRITON_CACHE_DIR` and the rotary path attempted `/home/ubuntu/.triton` on a read-only filesystem. Its pre-call counter of 1 means one attempted pipeline call, **zero steps and zero outputs**. Its load time was 13.928211 s and combined container wall time 19.209151 s; exact failed-call duration is unavailable. This environmental error provides no visual result or completed-edit capacity qualification.

Root authorized one cache-environment correction using the same image, checkpoint, input, constructor, attention and numerical recipe. All 13 approved cache paths passed writable checks as UID 1000/GID 1001. That call completed 40 steps and one output; load took 13.733035 s and inference 30.879442 s. Primary, independent and root PNG reviews agreed on visual FAIL. The same class of failure occurs in pinned Diffusers, so it is not isolated to SGLang; neither an intrinsic model/checkpoint fault nor a numerical cause is established.

Exact pins, hashes, per-case observations and restoration evidence are in [REJECTED-EDITING.json](REJECTED-EDITING.json); [CASES.csv](CASES.csv) is the compact comparison. Byte-exact supplied [RECIPE.json](RECIPE.json), [DEPENDENCIES.json](DEPENDENCIES.json), [CORRECTION-PINS.json](CORRECTION-PINS.json) and [METRICS-CORRECTED.json](METRICS-CORRECTED.json) preserve the reference details. The archive's [requirements.freeze.txt](requirements.freeze.txt) matches the recorded hash. Inherited archive hashes for 35 distributions remain unavailable; this is not a complete from-scratch dependency lock.

The 11 compact source files are included byte-exact in [source/](source/), including the corrected cache recipe. The full archive (which also contains approval notes) and PNG remain outside Git at task-relative `reference-evidence/reference-corrected-source.tar.gz` and `reference-evidence/output.png`. The source archive SHA256 is `24d7d6c2da98d12ba719096fd640d2032f932fdeb52959d7b1b9f802b343475d`; the PNG SHA256 is `67893b76fe9045e07b1a85a4d25c9f213c2a3467c5d647d31f42f1e3d4ae0422`. [SOURCE-ARCHIVE-RECEIPT.json](SOURCE-ARCHIVE-RECEIPT.json) records archive members, verified source hashes and the historical original bundle receipt. [INPUT-MANIFEST.json](INPUT-MANIFEST.json) records supplied file hashes. Historical SGLang PNG and raw telemetry hashes are retained from receipts; those bulky bytes were not rehashed here.

The supplied restored receipt at 2026-09-23 03:43:33 UTC identifies SGLang container `18caf935baedc917fd2e3ad4e086b589acf3b6ef110f91dfbbe940ab6a873ed8`, run `99c0105a7acf43788fdb0d436660f29b`, fixed recovery/warm exit 0, unchanged text Qwens, stopped reference container/PID 0, released reference GPU context and free canonical lease. It is historical handoff evidence; subsequent qualification deployment receipts govern current readiness.

Device sampling was nominally 200 ms and host/cgroup sampling 1 s. Sampled device use is separate from native allocator peaks; intermediate peaks remain unobserved, and lifetime allocator/cgroup maxima are labeled. Resource margins and successful decoding did not qualify fidelity. Transparency and two-reference editing remain unsupported and untested.
