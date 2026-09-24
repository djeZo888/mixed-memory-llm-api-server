# Root GO — one exact production-path RGB comparison

Root independently viewed the raw-RGBA reference edit and agrees PARTIAL / visual quality failure: dark blue/purple plus strong sharpening, lighting and background change. Do not qualify that edit as passing. Generation remains passing.

Bounded diagnosis now authorized:

1. Record source/output alpha extrema and opaque fraction from preserved raw generation/edit PNGs.
2. Produce the reference through the EXACT reviewed production opaque API generation-output normalization: `protocol.decode_image(..., output=True, transparent=False)` yielding RGB PNG. Use reviewed source07d2a495c648c5cfbad21a5b15fec4b7fc7b4a58 available in taskroot/root-api-publication (verified checkout HEAD). Do not invent an approximate conversion or modify that checkout.
3. Perform ONE comparison edit using that exact normalized reference, same prompt, seed42,40steps, CFG1, runtime/model/settings, and normal sampled telemetry/temp-cleanup evidence. This tests the actual intended production RGB path; it is not a prompt/seed sweep or another runtime/model selection. Preserve the original raw-RGBA result separately.

If this comparison still has poor edit fidelity, stop editing qualification and return failure evidence. Root will decide whether a separate reference-runtime comparison is needed. No further retries, parameter sweeps or edit ladder in this task. No public API deployment is authorized by this comparison.
