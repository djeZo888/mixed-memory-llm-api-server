# H003 editing diagnosis — seed-reuse mitigation candidate, not deployed

The original seed42 teapot editing regression remains a retained FAIL. Changing
only edit seed to43 produced a blue teapot with preserved main geometry, soft
background, table and lighting; Worker1 and root visually accepted that diagnostic
counterpart. The original image was itself generated using CPU seed42 and the
same1024x1024 geometry. This establishes useful case-specific seed sensitivity,
not an internal denoiser repair or a blanket editing qualification.

The candidate corrects one demonstrated source path: omitted edit seed inherits
native42. `protocol.validate` now selects fresh random32-bit once only for a
validated edit without an explicit seed. Explicit seeds remain exact, including42.
Successful edit `data[0].seed` reports the actual native value. Generation requests,
defaults, output contract and all six accepted geometry profiles stay unchanged.
No installed source, runtime image, model, text service or manifest was changed.

The future harness must persist actual seeds, avoid known source/ancestor seeds
for automatic choices, and refuse an explicit known collision before dispatch
with source_seed_collision. The API has no provenance registry and cannot prevent
unknown-source collisions. This work does not implement the harness.

## Bounded evidence

|Entry|Request|Result|
|---|---|---|
|D01|Staging only; no GPU dispatch|Installed storage guard rejected root traversal into native-owned evidence. Retained, excluded from GPU budget per root clarification.|
|D02|Native VAE-only roundtrip of original1024 RGB|One encode+decode, zero denoising steps. Visually faithful; MAE0.661/255,RMSE1.271/255.|
|D03|Same source/settings/seed42; identity instruction|40steps/one output; severe coarse texture/contrast/sharp background repeats. FAIL.|
|D04|Exact original source/recolour instruction/settings; only seed43|40steps/one output; blue colour and scene fidelity PASS counterpart, root agrees.|

Actual GPU requests3/6, remaining3. No automatic inference retry or lifecycle warm.
D05 independent already-retained non-teapot image and D06 follow-up of D04 at44
are authorized by root, but D05 needs a suitable retained1024square fixture;
neither was run at this checkpoint. No image was resized or generated to fill
that gap. The remaining call is reserved; no capacity stage starts here.

D02 device sampled minimum free9,942,990,848bytes(19.30%); D03/D04 minimum
9,602,531,328bytes(18.64%). Host minimum available≥97.09%, host/cgroup swap0.
Device200ms/host1s sampling does not see between-sample peaks. D02's separate
VAE probe peak allocator is not native edit capacity evidence. Compact ledger
retains per-call elapsed time/output hashes and raw receipts are taskroot artifacts.

## Validation and operational boundary

13 focused offline tests pass:5seed contracts,7existing FullHD geometry/crop tests,
and1native-wire test. Eight exact-artifact CPU checks pass for source hashes,
normalization/geometry identity, original adapter bytes/settings and native-to-public
RGB pixel identity. These source fixtures do not establish live candidate acceptance.
Source trace and exact source hashes are retained separately.

D03's timeout-safe runner initially stayed frozen because its identity comparison
included used VRAM(2MiB changed at the same native PID). An explicit guarded
settlement proved HTTP200,40steps,one output, no diagnostic process and unchanged
GPU UUID/PID, then thawed the same adapter; ready200 was verified. The corrected
D04 runner settled before thaw and returned ready/admitting/idle. D02 completed
successfully before root's stronger timeout note was read; that limitation is
retained, not hidden. No backend/text restart occurred.

The pinned SGLang image/checkpoint, GPU placement, precision, residency, guards,
canonical lease, disabled independent backend boot and sole image API owner remain
unchanged. Editing public profiles remain absent. Source requires exact root review
before deployment. FullHD edit geometry and two-reference capacity remain later
separate work. The current seed42 failure is a documented model/runtime same-noise
limitation mitigated by orchestration, never relabeled as a repaired native result.

Reporter [upstream issue9](https://github.com/QwenLM/Qwen-Image-2.1/issues/9)
identified the same repeated-source-noise symptom. It is not maintainer-confirmed;
our local provenance and seed-only counterpart are the evidence for this fixture.
