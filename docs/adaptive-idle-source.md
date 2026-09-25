# Adaptive idle native source overlay — H005, 2026-09-25

This source checkpoint binds the 600-second policy to the full pinned text normal
scheduler and diffusion monolithic scheduler. It includes reproducible offline
patch application, source hashes, candidate derived-image recipes and launch
verification. **No image was built, activated or accepted by this task.** Existing
production source/image admission guards remain mandatory and reject changed
source until the separate owner transition receives root review.

## Work and wake semantics

Each scheduler owns a monotonic grace period. Startup/warmup begins grace; actual
work admission and completed processing renew it. A generation lasting more than
600 seconds still gets 600 seconds after final completion. Active, queued,
streaming, draining and pending asynchronous work forbid blocking. Unknown
activity also forbids blocking. Passive status, readiness, metrics and control
traffic may wake a scheduler without renewing grace. At the 600-second boundary,
a genuinely idle scheduler waits indefinitely for input. There is no periodic
sleep on active inference, unload or cache-empty operation.

Text uses the pinned non-overlap, single-rank pair geometry and both native ZMQ
ingress channels. Unsupported scheduling geometries fail closed. The overlay
bypasses upstream `IdleSleeper` entirely, so its `SGLANG_EMPTY_CACHE_INTERVAL`
behavior cannot leak through. The legacy standalone candidate patch remains only
as historical fixture coverage; it is not in either build recipe. Diffusion waits
on its native ZMQ ROUTER ingress with an indefinite poll; both native client
types use REQ sockets to that receiver. Readability remains pending across the
idle check/wait boundary. The binding covers synchronous execution through
result transmission and rejects unsupported asynchronous/disaggregated execution.
Native tokenizer/client and ASGI hooks keep scheduler work pending until both
generation and response drain complete, including client-side completion delayed
after the scheduler reply. The HTTP boundary is the native ASGI application's
completed response send/cleanup, not remote TCP receipt. Both HTTP adapters wrap
the complete native ASGI stack, including framework error responses. Image begin acknowledgments and ordered completion sends remain
owned across ordinary cancellation; healthy cancellation/error paths settle their
drain state. Reservations inhibit waiting without renewing grace; only successful
native model dispatch permits final completion renewal. Only genuinely failed or
unresolved transport/work retains pending state for canonical owner recovery. Text also retains running grammar compilation Futures
after an aborted request leaves the native queue: failed cancellation does not
turn ongoing compilation into idle. Observed final completion starts fresh grace.
Helpers do not alter request contents,
weights, KV format, configured context, cache policy or resource allocation.

Text preprocessing reservations also inhibit waiting, but only a successfully
dispatched native model request can renew grace at response completion. Rejected
validation/over-context inputs release their reservation without changing the
last real-work time. No passive route creates a reservation.

The authenticated native text `/v1/readiness` route reports the exact served alias
and strict internal `ServerStatus.Up` only after existing authenticated warmup.
It never calls native `/health`, generates work or touches scheduler grace.
Readiness is not an idle observation or authority to clear quarantine.

## Exact source boundary

`scripts/runtime/adaptive_idle_sources.json` pins raw SHA256 values at text commit
`0bcd822377da7b5718e674eaf9c870d349424dd1` and diffusion commit
`0cd8be351d0825488f4b81c8931167bbab618eca`. It retains H004 normalized-text hashes
under `historical_normalized_evidence`, without reinterpreting them as raw hashes.
The full bounded source copies and extraction receipts remain outside Git in the
H005 worker task scratch directory.

The 2026-09-25 read-only installed-source snapshot verified stable selected
container identity before/after copying. The manifest names exactly which raw
files matched that snapshot. Additional text and diffusion helper pins are official
revision sources; installed equality is not claimed for unextracted helpers.
The generated Dockerfile checks all raw pins in the parent before any overlay
COPY, so helper drift fails the future build. The repaired diffusion NVML helper
must retain raw hash
`7686af293bc4cb31be87c8a188c10e28e49b011c3acb7bac914ca83c5b9ec9de`;
it is not overwritten or repaired again.

The observed text container `.Image` is `sha256:37bbbd3444732a464bbc68dee4fb0164e0ce9e18e2f027f3fc967f1152d3c262`,
while the runtime profile's historical config digest is
`sha256:e6238090791a938ab86dd21a9a6394192dad15237e815df557cf83524d54b813`.
The exact public OCI manifest was retrieved and its raw SHA256 matched
`37bb…c262`; its config descriptor names `e623…b813`. The worker receipt
`TEXT-IMAGE-DIGEST-PROVENANCE.json` records that relationship without registry
credentials. Container manifest identity and profile config identity therefore
remain distinct, proven fields; neither is reused as a new overlay image ID.

## Offline build-context preparation

From this repository, with `TASK_DIR` naming this worker task directory:

```sh
python3 -B scripts/runtime/build_adaptive_idle_overlay.py \
  --root "$TASK_DIR/scratch/native/text" --target text \
  --output "$TASK_DIR/scratch/overlay-text"
python3 -B scripts/runtime/build_adaptive_idle_overlay.py \
  --root "$TASK_DIR/scratch/native/image" --target image \
  --output "$TASK_DIR/scratch/overlay-image"
H005_PINNED_TEXT_ROOT="$TASK_DIR/scratch/native/text" \
ADAPTIVE_IMAGE_SOURCE_ROOT="$TASK_DIR/scratch/native/image" \
python3 -B -m unittest discover -s tests -p 'test_adaptive_*.py' -v
H005_PINNED_TEXT_SOURCE="$TASK_DIR/scratch/installed/text/python/sglang" \
python3 -B -m unittest discover -s tests/lifecycle -p test_pair_readiness.py -v
```

Preparation refuses existing output, missing source, symlinks, raw-byte drift,
unpinned patch targets, patch failures and invalid Python. It transforms copies
only after every input matches, compiles complete output modules without GPU
imports, then publishes the complete build context. Each context contains only
changed native modules, package-local policy/binding helpers, a Dockerfile,
read-only launch verifier and deterministic provenance. The overlay digest binds
upstream revision, immutable parent reference, all input/output hashes, patches,
verifier and preserved installed-file preconditions. It is a **source overlay
digest**, not an image/config/manifest digest.

Candidate Dockerfiles preserve the existing parent and dependencies, add no
packages or model downloads, and do not change entrypoint, environment, weights,
context, GPU/CPU placement, cache or allocation. Future authorized builds must
record the resulting new image identity. They must run through the existing
registered storage/root-disk guards; these recipes grant no VM write authority.

`verify_adaptive_idle_overlay.verify_installed(receipt_path, expected_digest,
target)` is a read-only launch seam. The expected digest must be pinned in reviewed
launch source/configuration, never read back from the receipt or caller traffic.
It rehashes final installed modules (original anchors overridden by transformed
outputs). The candidate image places it at `/opt/llmctl/adaptive-idle/verify.py`
and the receipt at `/opt/llmctl/adaptive-idle/{text,image}.json`. The text pair
and image native launchers check the pinned verifier bytes
before importing it, then check the pinned overlay digest before native startup.
The separately owned lifecycle task must bind the new immutable image identity,
launcher hashes and provenance transition through canonical launch/owner checks;
it may not disable those checks to admit this image.

## Minimal proposed provenance transition

The core/node source checkpoint already changes exact-source identity. This
scheduler overlay additionally changes native source and derived image identity.
Keep the original receipts intact. A root-reviewed replacement receipt must name
new reviewed source commit/hashes, overlay digest, newly built image digest,
unchanged upstream/model revisions and launch/resource configuration, plus the
new offline tests and later bounded live acceptance.

The 2026-09-21 dual-Q report is inherited **historical occupied-context evidence**:
480,000 configured per Qwen, 479,408 input each, occupied 479,490/479,495 for that
measured pair. Those values were not retaken and are not measurements of this
overlay. Preserve its Q1 strict-JSON failure caveat and all original limits.
The 2026-09-23 image Full HD qualification and subsequent guarded-editing evidence
likewise remain dated evidence for unchanged model/geometry behavior; this task
adds no resolution or editing qualification.

Current blockers include `concurrent_source_pin_mismatch`,
`concurrent_acceptance_identity_mismatch`, `concurrent_capacity_evidence_mismatch`
and `concurrent_qwen_actual_auth_evidence_required` where changed source,
launcher or image hashes no longer match historical proofs. The separate owner
source task owns the narrow acceptance transition and canonical wiring. Do not
fabricate old proof, remove these guards or launch under the old runtime identity.
No giant 480K rerun is requested. Root must coordinate a short matching warm
request before/after an at-least-11-minute idle observation, per-scheduler CPU
transition and immediate work wake/renewal across all three resident models.
Image build, live GPU imports, allocation/warm requests, idle CPU, response
latency and live readiness/authentication are **NOT_TESTED** here.
