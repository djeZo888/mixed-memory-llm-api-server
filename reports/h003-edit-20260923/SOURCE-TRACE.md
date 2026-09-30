# Exact source/data trace

Scope: base8376682, current pinned resident SGLang, protected native source copies
and retained Diffusers source from the stopped, image-ID/owner-verified reference
container. No reference runtime execution. Full source is taskroot artifacts;
source-audit-manifest.json binds hashes. Old failures remain immutable.

- Original raw generation d055af... (RGBA),1024square, CPU seed42. Explicit prior
RGB conversion9756c5... preserves every RGB pixel. Both files are rehashed; no
EXIF orientation metadata. The original generation receipt is retained.
- `uploads.py` appends multipart images in order; `backend.py` forwards original
validated bytes and generated filenames. `protocol.py`152–186 validates actual
PNG/JPEG/full dimensions and only normalizes when output=True. Input validation
216–217 returns the original image list224. No adapter resize/colour correction.
- Native `vision.load_image` applies EXIF transpose then RGBA conversion.
`QwenImage21EncodingStage` computes output-area/multiple32 reference geometry,
uses LANCZOS, and shares the result with VLM and VAE. At1024square it preserves
pixels. VLM white-composites alpha; original RGB gives alpha255. Prefix image1
and reference ordering are preserved. VAE reads all4channels, float/255→[-1,1]
BF16, posterior mode, channel mean/std normalization, flatten2/transposition.
- Native Qwen3VL explicitly stores decoder hidden states before final RMSNorm.
Pinned Diffusers pipeline297–310 explicitly neutralizes that norm through a
forward hook to preserve pre-final-norm semantics under Transformers5.17.
No missing norm compatibility repair was established. Actual tensor parity
between runtimes was not measured.
- Native model default components BF16/FP32, allresident/torch_sdpa/eager; no
precision/offload/cache policy changed. D02 strict-loads the same native VAE
class/weights/config in the existing container; its temporary copy fully exits.
No latent-stat metadata override was present. Its single encode/decode roundtrip
is faithful, with maximum BF16 inverse-normalization error0.125latent units.
This weakens gross VAE damage; it cannot exclude mutually-inverse conditioning
scale errors or errors specific to generated latent distributions.
- Native prepare_sigmas and pinned Diffusers use linspace1→1/40. Both calculate
mu from target4096tokens and checkpoint dynamic-shift config(base256,max8192,
shifts0.5→0.9,terminal0.02); source formula gives mu0.6935483871. Native passes mu
and sigmas to request-local scheduler.set_timesteps. This establishes source
recipe agreement, not bitwise trajectory equality. CFG is active only if
true_cfg_scale>1 AND negative prompt is non-None. Explicit trueCFG overrides
ordinary guidance. CFG1/negative-absent was preserved in every edit here.
- Native exact prefix KV caches are request-local. No approximate cache setting
was enabled. No cache-disable comparison or model/runtime sweep was run.
- Native denoiser outputs target stream; inverse normalization/std+mean, BF16
VAE decode, range map/clamp and PNG follow. Public1024output only converts to RGB
and re-encodes. Offline actual public_output reproduces all RGB pixels of both
D02 and D03 delivered images; the coarse artifact already exists in raw D03.
- Deployed SamplingParams.seed is42 by default(line281). Native
build_sampling_params removes None so omission inherits that value. Both original
generation and failed original editing therefore used the same CPU noise seed.
Original source provenance plus D02clean/D03identityfail/D04seed43pass supports a
seed-reuse interaction for this case, consistent with reporter issue9. No internal
denoising defect or general seed-independent fidelity guarantee is established.

Generation-only FullHD native1920x1088→top1080 crop is unchanged. No input resize,
FHD editing/padding, transparency or two-reference capacity was tested/enabled.
