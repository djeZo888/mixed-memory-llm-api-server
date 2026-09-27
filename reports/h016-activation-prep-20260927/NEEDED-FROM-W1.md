# H016 activation inputs — no readiness inferred

Preparation only. No manifest exists on ai-harness at initial readback. Send the
parent the exact completed `h016-mimo-integration-20260927/QUALIFICATION-TEMPLATE.json`
file path and SHA256, plus its evidence paths/hashes; root reviews before use.
Do not manufacture this document from benchmark progress.

The application qualification document is distinct from the production owner's
schema2 manifest at `/data/services/mimo-h016-20260927/manifest.json`.
Current source hardcodes `/etc/ai-harness/mimo-qualification.json`, but the
parent is root:root0700 and must remain unchanged. Receipt placement/access is
HELD pending later narrow source review; a separate root-owned traversable
directory for this nonsecret hash-pinned document is preferred. No replacement
path is invented here. Retain root-owned protected ancestry, no links, one link,
no group/other writes and at most65536 bytes. Preserve any prior receipt.

Required application fields (names are exact):

- `serviceId=mimo-v2.6-pro-rl`, `privatePort=30012`;
  `full17ToolRosterQualified`, `strictNestedSchemasQualified`,
  `serialCompletionQualified` all true from actual qualification.
- `capacity`: `published=1048576`, actual `configured`, `allocated`,
  `occupiedTested` (positive, below allocated). Configured >= allocated;
  allocated equals `qualification.identity.actualSlotContext`.
- `nativePins`: exact native `buildInfo`, `modelPath`, effective
  `chatTemplateSha256` equal to loadedTemplateSha256, and
  `toolTemplateSha256` (actual SHA256 or null for absent property).
  Raw3867-byte and effective3866-byte template identities are distinct.
- `qualification.qualified=true`, actual `evidenceSha256`.
- `qualification.identity`: `model=mimo-v2.6-pro-rl`,
  `runtimeRevision=7ac59a6e3ad851cd41af00f678effab0598ba9a8`,
  `artifactRevision=ba4eabb78b6c51ffd873ec73b9e12b0f64aced5d`,
  `artifactManifestSha256=6ac4242ac5d4df5b083b133062c78b792f1fdc7716d32c0e0000122e3263744b`;
  actual `runtimeBuildSha256`, `loadedTensorMetadataSha256`,
  `loadedTokenizerSha256`, `loadedTemplateSha256`, `serverInstance`,
  `serverGeneration`, `actualSlotContext`, `maxOutputTokens` (qualified65536),
  `parallel=1`, `contextShift=false`, `speculative=false`, `mtp=false`,
  `multimodal=false`, `assistantPrefill=false`, `jinja=true`, actual boolean
  `kvUnified`, `swaFull=false`.
- `qualification.checks`: `artifactBytes`, `nativePrecision`, `allocation`,
  `reserves`, `templateAndTokenizer`, `textArrayRendering`, `reasoningAndTools`,
  `singleOwner` true; `admissionBound={basis:"pinned-source-s-minus-one",
  arithmeticFixtures:true,shortNativeCountUsageMatch:true}`;
  `generationCeiling={requestedMaxTokens:65536,requestedCeilingAccepted:true,
  largestCompletedOutputTokens:<actual positive completed count <=65536>}`.
  Requested ceiling acceptance and completed output length are different facts.

Production identity must bind the CURRENT clean supervised owner, not the R5
benchmark container. Supply protected manifest hash, installed source hashes,
selection.json selected_frontier=MiMo/generation/manifest_sha256, state/guard/
proxy-state readbacks, current boot, systemd invocation/supervisor PID, exact
container name/ID/image/native PID/start ticks/StartedAt, proxy PID/start ticks,
RUNNING, request disposition, and timestamped native props/one-slot readback.
Explain the exact mapping from these identities to serverInstance/serverGeneration.
Owner must actually be running and observed. No old adoption ACK/13:40 handoff.

Root/W1 supplies a fresh canonical node DTO with the exact service_id
`mimo-v2.6-pro-rl`: available=true, ready=true, hardware_latched=false,
fresh ok observation and current boot/guard/selection identity. Preserve null
admission/activity when unknown. A missing MiMo entry disables only frontier;
it is not evidence of whole-app failure. W2 prep sends no backend requests.

Initial131072/output65536 is already a reviewed managed-profile tuple, as is
1048576/output65536. If actual selected capacity changes, notify parent of the
minimal exact-content profile migration gap before activation. Never bake the
16K benchmark request limit into the service's allocation/profile.

R5 loaded131072/no-host, small text/tool continuation and measured4096 PASS
(61.08 input tokens/s,0.914 output tokens/s,111.13s) are root-provided context;
16K/64K were pending. They prove neither this static document nor production
identity. W1 alone deploys/observes the backend later. After the reviewed receipt-path/access correction, separate root GO can pair
the host release with the qualified config overlay; no extra permission roundtrip.
