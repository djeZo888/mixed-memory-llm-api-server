# Minimal source correction proposal — explicit seeds unchanged

Root's ROOT-D05-D06-REVIEW.md supersedes my provisional deterministic remapping.
That draft was removed before commit/VM deployment; production source is unchanged.

Propose only these API changes, proposed before implementation; now prepared offline for exact source review:

1. After an edit is validated against a reviewed profile, preserve any explicit
seed byte-for-byte. If an edit omitted seed, choose secrets.randbits(32) once in
validate, store it in the owned Validated.native request, and dispatch that exact
seed once. Generation behavior (including missing seed) remains unchanged.
2. For successful seeded edit responses, add the OpenAI-compatible optional
`data[0].seed` integer giving that actual native seed. Keep created/b64_json and
all existing decoding/size protections. No seed in error/log output; caller gets
truthful reproducibility metadata. No chosen/effective remap or secret provenance.
3. Document that root/harness must persist that actual seed with the artifact.
The future harness chooses random seeds avoiding known source/ancestor seeds and
rejects an explicit known collision with source_seed_collision before dispatch.
Unknown provenance cannot guarantee collision avoidance. No registry in image API.
4. Focused fixtures: omitted seed generated once, explicit0/42/max passed unchanged,
chosen seed reported exactly, no hidden retry/redraw, generation wire/response
unchanged, and unqualified edits rejected before randomness/native submission.

Current source finding: deployed protocol.validate omits native seed when absent;
native request parsing inherits its SamplingParams default. Confirmed SamplingParams.seed defaults to42 at line281; native build_sampling_params
strips None values before defaults apply. This proposal repairs
only the missing-seed path; it does not repair an explicitly reused42 at the native
model. Preserve fail42/pass43 regression evidence and document that boundary.

Candidate code is now prepared offline with13focused passing fixtures; no
production deployment. It will remain unactivated until exact root review. Existing six generation profiles
and no-edit qualification remain protected and unchanged.
