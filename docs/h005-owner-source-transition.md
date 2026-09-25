# H005 reviewed source and runtime transition candidate

> Historical source checkpoint — 2026-09-25. The text below preserves its original
> evidence boundary. See the [current H005 acceptance report](service-resilience-acceptance.md)
> for later repair/deployment receipts and PARTIAL / PENDING live acceptance.

This is a **source/offline activation package**, not deployment or activation GO.
The Worker1 binding task starts at integrated `afebf390666674b2a84f7147cf156f80600bdfc9`
and preserves the runtime overlay bytes from
`f9d9b5191534581d854067507922af2b56790710`. Root owns exact final review and serial
activation. Installer remains paused. No second lifecycle or new model is added.

## Completed build lineage, distinct digest domains

The completed `H005-ADAPTIVE-BUILD-20260925/BUILT-IMAGES.json` raw SHA256 is
`5d896fdb52aa3a5d55ed42ba6dc7f402de1da9f98b3cee22bdf4f62f076fe9dc`;
`FINAL-HASHES.json` SHA256 is
`e6ac2e4d63e972ca900a7fc01ee65dcb530c2e5fbf9f1cd26b1ac5aff08f0420`.
The binding task verified both plus the complete mirrored receipt/context hashes
without contacting ai-vm. The build preserves each parent's complete layer prefix.

| Target | Immutable local Docker ID / OCI manifest | OCI config digest |
|---|---|---|
| Text | `sha256:0aa2afe62c04fdd4f06a38229e6941cb1e47f6b7c0863698b708f299d4f15ddf` | `sha256:8f9a45a8a4de689280c054867103fc072f064703427212aeb6d603551a86f4b2` |
| Image | `sha256:f01aafc2fefb4a5f961c73b7435ccfbdf5a801ccc55a9112d50fc5d45beb3a0f` | `sha256:e0a3d6b3b0e55583feb272dac0c0f3caedbabf65bb19f60efbf7f13c3591b51f` |

No derived registry publication is claimed. Local tags are provenance only and
are never runtime selectors. Text parent remains manifest
`sha256:37bbbd3444732a464bbc68dee4fb0164e0ce9e18e2f027f3fc967f1152d3c262`,
config `sha256:e6238090791a938ab86dd21a9a6394192dad15237e815df557cf83524d54b813`.
Image repaired parent remains manifest/local ID
`sha256:dafbccb763cff6a6aa3777c7c0a8cc185d838bd4b9f61bec8007f57f2c7233f8`,
config `sha256:d8bb36563e0cdfa7d315417cf4a9dbf064c86ccc5b16d21a60f3216d71e150da`.

`configs/runtimes/h005-runtime-binding.json` records those relationships, build
receipt hashes, original source pins, full final native-file hashes, verifier
and overlay hashes. `runtime.h005_runtime_binding` verifies its exact raw bytes.
The two pair declarations alone receive an effective runtime copy selecting the
new immutable local ID. Parent runtime/model/deployment JSON remains unchanged;
legacy singleton/TP2 profiles retain their historical selectors. Current pair
startup always requires a new protected per-slot actual-image auth receipt.
The image Runtime requires the same fixed binding's image ID in protected config.

Text overlay: `b7f03476fe13779ed4867e4ca509dcba2861431210b6a264cf551558b5927a27`.
Image overlay: `dda84e200adcc6a1ee8915e0e993627695477a346c5848fc27f9251c34d04b3b`.
Both launchers retain their f9d9b5 bytes and independent baked-overlay verifier
checks. Complete native originals and final files remain bound; no hash guard
is disabled or supplied through an environment override.

## Source closure and noncircular hashes

1. Freeze runtime overlays and completed build receipts; transcribe only their
   verified immutable IDs into the binding JSON.
2. Hash that raw JSON into `h005_runtime_binding.BINDING_SHA256`. Hash that module,
   JSON and final pair launcher into `concurrent_profiles.PINS`. No file embeds
   its own hash. Fixture file hashes go into `provenance.json`, whose raw hash
   goes into `qwen38.PROFILE_HASHES`.
3. Freeze all code. `concurrent_profiles.source_identity()` hashes the union of
   exact profile pins, owner files, complete control recovery/normal closures and
   node closure. Closure declarations list paths, not hashes of themselves.
4. Generate external `CRITICAL-SOURCE.json`, `SOURCE-MANIFEST.json` and image
   config templates from the final commit. These artifacts are outside the Git
   tree and bind that commit plus raw file hashes; their own digests belong in
   the task result/root review. Acceptance receipts consume these source hashes;
   source never hashes an acceptance receipt back into itself.

Task `tools/generate-package.py` reproduces the external outputs locally. It has
no host mutation/network/Docker calls. Its `--check` mode compares regenerated
bytes. Commit and bundle hashes are recorded only after the source is committed.
Root may merge the binding delta onto its newer harness commit, then regenerate
external integrated metadata; owned critical bytes must remain identical or be
reviewed and tested anew. This task does not edit the peer harness tree.

Control and node static validation include every runtime helper, patch,
manifest and owner dependency. The image service fixed `RELEASE` is
`/data/services/releases/h005-activation-binding-20260925`; publish that complete
reviewed directory once and refuse a nonidentical existing directory. Do not
edit an old immutable release. Image protected config requires exactly the four
runtime files and all `RELEASE_SOURCE_FILES` via `source_sha256` and
`release_source_sha256`. The image closure also records the unchanged API files,
units and fixed recovery helper for the external delivery manifest. Small
protected source/config/unit writes remain distinct from registered data writes;
reusing storage APIs is not authorization to resume installer work.

## Explicit acceptance transition

Keep schema-2 `root-reviewed-dualq-480k`, all existing resource/source/auth gates
and `concurrent_pair_acceptance={path,sha256,reviewed_source_commit}`. SHA256 here
is canonical JSON (`receipt_sha256`), while backup hashes also cover raw bytes.
Copy the original receipt unchanged to registered data suffix
`services/llm-manager/evidence/h005-predecessor/dualq-480k.accepted.json` first.
The successor requires `h005_transition` with:

- `kind: inherited-capacity-new-runtime-auth`;
- exact runtime binding hash and f9d9b5 runtime source commit;
- the archived predecessor canonical receipt digest;
- original measurement date (`capacity_observed_at`, YYYY-MM-DD);
- `live_acceptance: SEPARATE_RECEIPT_REQUIRED`.

The validator compares all predecessor slot proof keys and values unchanged
except Qwen `runtime_image_id`, `pair_launcher_sha256`, `native_auth_checks`.
It also preserves original host usable memory, vCPUs, headroom policy, GPU
inventory and concurrency review, plus every original evidence reference.
GLM proof values remain unchanged. New evidence may be appended. Thus old
`allocation`, `short_inference`, `correctness`, occupied-context and working-set
rows are explicitly inherited historical measurements, not fresh tests of the
changed runtime. Root must review that bounded inheritance assumption; a changed
capacity assumption stops the transition rather than manufacturing a PASS.

Both fixed Qwen slot tuples require fresh **CPU-only actual-image native auth**
receipts via `run_pair_fixture.py --adaptive-overlay --slot gpu0|gpu1`.
The explicit mode selects the built immutable image, verifies all native raw
pins and the installed baked overlay, and requires exact
`GenerationDrainMiddleware` identity plus `wrapper.app is server.app`.
Requests continue through the outer middleware; metadata comes from the inner
native app. Image full-source fixtures similarly assert exact
`DiffusionDrainMiddleware` and underlying native app; no identity assertion is
skipped. Historical unwrapped mode cannot satisfy revised production admission.

Protected new receipts live at registered data suffixes
`services/llm-manager/evidence/h005-gpu0.auth.json` and `h005-gpu1.auth.json`.
The instance adds `h005_pair_runtime_evidence`, keyed by exact deployment ID,
with `{path,sha256}` canonical JSON references. The production adapter checks
the entire actual-image receipt including slot, model alias, port, launcher,
fixture/source hashes, immutable image/domain, supported checks and settled
CPU fixture-container lifetimes. Old parent auth receipts stay untouched.
Model execution/native lifespan/live inference fields in CPU receipts remain
NOT_TESTED. Live authenticated readiness is checked after canonical model start
and warmup; it is not a circular prerequisite to initial start.

Neither this source task nor the BUILD helper-only checks have run those CPU
native auth fixtures. Full native package import and native msgspec codec are
also NOT_TESTED. Build-only never implies activation GO.

## Once-only latch initialization and guarded publication

`RegisteredLatchStore.initialize()` is explicit activation preparation, never
called from startup, polling, restart or recovery. Under the borrowed canonical
lease, it reads the protected fixed
`services/llm-manager/evidence/h005-latch-first-install.reviewed.json` review.
That review must attest no prior state across retained releases and bind its
absence evidence hash and reviewed source commit. The parent must preexist.

The initializer runs registered root-payload and mounted guards, creates
`hardware-latch.initialized.json` exclusively, fsyncs file and parent, then
creates `hardware-latch.json` exclusively and fsyncs it. Existing state or marker
refuses; a partial marker or missing state after initialization stays closed
for root-reviewed recovery. No silent retry clears hardware history. Empty state
means UNKNOWN until current-boot exact-UUID positive validation. Existing
current-boot positive latches survive source/service restart and reset; prior
boot protection clears only through the reviewed exact-target proof.

Root assigns a fresh activation owner/window. First capture current active work,
intent, operation journals, boot, exact owned containers/images/config/source,
old receipts and installed guard identities. Coordinate target-scoped harness
freeze/ACK, preserve request quarantine, and obtain required interruption
confirmation. Direct clients need settlement too. Use current installed guards
and registered paths, protected anchored writers and the canonical lifecycle
lease before/after writes. No old-checkout guard fallback, alternate lock,
protected write, service action or network contact occurs in this source task.

Publish complete source/config/receipt/instance in maintenance; individual
fsync/rename replacements are atomic but the collection is not one transaction.
Re-read all hashes, reload consumers without mixed imports, and verify full
closure/admission before starting through existing Manager/image owners.
Model order is Qwen0, Qwen1, then Ada image, serially and according to captured
intent. Preserve both480000 contexts, weights, BF16 KV/cache,72vCPUs, shared CPU
masks, no-swap caps,15% sampled working-set margin, UUID placement and Ada FHD/edit.
No giant context retest, relocation or architecture expansion.

The task's `DEPLOYMENT-PLAN.md` gives exact installation/write targets, commands,
rollback and all poststart gates. The one final at-least660s all-three quiet
window follows lifecycle/self-reboot checks, retains passive5s observations,
requires each scheduler below5% of oneCPU after its600s grace, then immediate
short wake requests and renewed busy grace. All live fields in
`IDLE-ACCEPTANCE-TEMPLATE.json` remain NOT_TESTED.

Rollback preserves and restores a matched old source/image/config/receipt set
through canonical owners/guards, retaining failed candidate evidence. Never
restore old journals over newer work or clear latch/quarantine. Retain all three
old images and D1 recovery artifacts. Byte restoration alone proves no readiness;
if the old set cannot safely admit current hardware/state, stop for root review.
