# Bounded private image API — source integration

The deployed Full HD service exposes six opaque generation sizes: **1024x1024,
1024x576, 1216x704, 1472x832, 1760x992 and 1920x1080**. The public hard ceiling
is **1920x1080 / 2073600 pixels**. Full HD uses the already-qualified native
1920x1088 workload (2088960 pixels) and removes exactly eight bottom rows;
there is no resize. The five smaller profiles retain native=public and crop0.
Public 1920x1088 and UHD are refused. Editing and transparency remain unqualified.

See the [Full HD change report](../reports/image21-fhd-20260923/RESULT.md) for
current deployment and single-call acceptance. The [prior qualification report](../reports/image21-qualify-20260923/RESULT.md)
is immutable historical native workload evidence, including 53.3355 s and
44776.3125 MiB sampled device peak for 1920x1088. This change does not claim a
new memory benchmark. The protected manifest binds the Full HD crop evidence to
that same qualified native workload; smaller-profile evidence hashes are retained.

The generic `qualification.empty.json` source template still contains **no measured
profiles and no runtime image digest**. Deploying that empty template keeps
readiness and inference closed. The protected measured deployment manifest is
separate. Source and offline fixtures alone do not establish runtime or image
acceptance. The image service preserves both existing warm text slots and their
480,000-token profiles.

## Public contract

Adapter `127.0.0.1:30006`; private socket proxy `10.156.100.60:30006`; unauthenticated
native backend **only** `127.0.0.1:30007`. Every route requires a Bearer inference
credential, including health/catalog and unknown routes. Reuse the existing
protected inference key, supplied through systemd `LoadCredential`; no key argv,
environment, access logs or backend forwarding.

| Route | Behavior |
|---|---|
| GET `/health/live` | Adapter event loop responds |
| GET `/health/ready` | 200 only after reconciliation, nonempty reviewed profiles and a fresh bounded native `/health` check; reports busy/admitting |
| GET `/v1/models` | Model alias `qwen-image-2.1` |
| GET `/v1/image-capabilities` | Exact pinned model/runtime revisions, actual reviewed image digest, measured profiles and state |
| POST `/v1/images/generations` | JSON request, synchronous PNG `b64_json` |
| POST `/v1/images/edits` | Multipart schema exists; valid edits currently return 400 `unqualified_profile` because no edit profile is accepted |

Allowed scalar fields: `prompt` (required, UTF-8 <=16384 bytes), `model` (alias),
`size` (default `1024x1024`), `n` (exactly integer 1), `seed` (optional integer
0..9223372036854775807), `response_format` (`b64_json`), `background` (`opaque`
default, or separately qualified `transparent`). Steps and both native CFG fields
are fixed to 40/1/1. Both native routes set `generator_device=cpu` for initial noise
RNG only; model CPU offload is unchanged and caller overrides are rejected.
Unknown fields, queries, URLs, server paths, runtime settings,
masks, duplicate fields, mixed image/image[] lists and other formats are refused.
Masks are not pixel-preserving inpainting: the upstream native implementation
ignores its mask parameter. No resizing, downsampling, public URLs or stored jobs.
The source candidate also supports the explicit one-reference Full HD transport
padding/crop below. This does not qualify or enable any public edit profile.

Limits are 32 MiB encoded/file, 64 MiB combined encoded files, two references,
64 MiB+64 KiB total streamed multipart body including its bounded envelope, and
64 KiB JSON body. Content-Length, MIME type and uploaded filename never authorize
content. Decode actual PNG/JPEG dimensions and reject malformed/bomb/multiframe
images. Each edit reference must equal the exact qualified public output dimensions.
Maximum public dimensions are 1920x1080 and 2073600 pixels, permitted only in a reviewed
profile. One-reference editing and generation are separate profiles. Two-reference
sizes require their own evidence, remain 1024-class until then, and never inherit
the one-reference ceiling. Output must decode as one PNG of the exact selected
native size, then only the explicitly approved bottom crop if present; public output
remains at most 2073600 pixels. Re-encoding strips native metadata. Only `created` and `data[].b64_json` are
returned, never raw native errors, revised prompts, paths or URLs.

## Admission and recovery

One process, one active owned operation, zero waiting requests. Admission is taken
before upload parsing. A competing request receives immediate 429 with
`Retry-After: 1`; an unready idle service returns 503. Invalid requests return 400,
encoded limits 413, wrong generation media type 415, native failure 502, deadline 504.
Readiness GET and pre-submission admission each use one native `/health` request.
The latter runs after atomic image ownership reservation and validation, immediately
before native submission. A separate health client avoids the image client's busy
single connection: total budget 2 s, connect/read/write 1 s, pool 0.5 s, two health
connections, at most 1024 response bytes, fixed loopback URL, no proxy or redirects.
Only the pinned warm-readiness response 200 with exact JSON `{"status":"ok"}` passes.
Failure/timeout/invalid health returns 503 and latches admission closed. Caller-only
probe cancellation propagates without changing readiness: cancellation is not
backend-failure evidence. The next image still performs its own fresh health probe.
Successful health alone never reopens a failed state. GET never invokes recovery or cancels active images.
A successful active image also cannot erase a concurrent health-failure latch.
There is no polling daemon. Required helper reconciliation remains the only reopening
path. Busy image contenders still receive 429 while any admission probe is pending.

Client cancellation/disconnect does not cancel the supervisor or native operation.
The supervisor strongly retains all upload buffers, CPU decode tasks and native
transport until settlement. CPU image work runs off-loop and remains owned through
cancellation; a monotonic deadline prevents late native submission or late 200.

The 900 s budget includes body receive/validation/native call. A timeout before
submission cancels upload work and releases only after owned validation settles.
An unresolved native timeout, or ambiguous transport/output failure, closes readiness
and invokes the fixed recovery helper once. The 504 response does not wait for
recovery. Admission stays occupied until the prior call settles or exact backend
replacement is proved and the old local transport/CPU work is joined. Failed
recovery stays closed, even if the old call subsequently finishes. No retry loop or
GPU cancellation promise. Restart always reconciles again; a new semaphore alone
cannot admit orphan overlap. A protected process lock rejects a second launcher.

## Worker1 service integration

Templates: [`llm-image-api.service.in`](../scripts/image_api/llm-image-api.service.in),
[`sudoers.in`](../scripts/image_api/sudoers.in). These contain unexpanded placeholders
and are deliberately **not a deployable runtime unit**. Root/Worker1 must substitute
an existing nonroot service user/group and the exact registered services root;
protect source and the separate venv against that user, groups and other users.

- Adapter unit `llm-image-api.service`; backend unit `llm-image-backend.service`.
- Enable only `llm-image-api.service` as the image boot owner, ordered with
  `After=network.target llmctl-boot.service`. No dependency on text boot success,
  and no Requires/Wants that independently starts the backend. The fixed recovery
  helper starts/resets/warms `llm-image-backend.service`; Worker1 installs that unit
  ordered after text boot but does not independently boot-enable it. Text units
  remain unchanged; this is source ordering, not reboot acceptance.
- Fixed entrypoint `/usr/local/lib/llm-server/image-api/scripts/image_api/serve.py`,
  via the separately pinned venv Python with `-I -B`. No server arguments allowed.
- Config `/etc/llm-server/image-api.json`, root:root mode 0644 with protected ancestry.
- Credential `/run/credentials/llm-image-api.service/inference-key`, mode 0400/0600
  root or service-owned; the observed systemd 0440 mode is allowed only root:root.
  No symlinks/hardlinks/mutable ancestry. Source is existing
  registered `services/secrets/llm-api-key`; verify its protected metadata and
  exact deployed LoadCredential mapping without printing it.
- Runtime lock `/run/llm-image-api/owner.lock`, owned by the service UID, mode 0600 in a mode 0700
  systemd RuntimeDirectory. No adapter data/spool/log/cache writes; uploads are
  memory only. Output/access/error logs and core dumps are disabled.
- Recovery command is exactly `/usr/bin/sudo -n -- /usr/local/libexec/llm-image-backend-recover`.
  Root-owned mode 0755 helper, protected ancestry, zero arguments and a 900 s self-cap.
  Render sudoers root:root mode 0440, run `visudo -cf` on that rendered file. Its `""`
  argument constraint means no helper arguments, not an unrestricted argument list.
- Do not combine sudo with `NoNewPrivileges=yes`, private users, restrictive
  capability bounds or filesystem restrictions inherited by the root helper.
  Supplied template explicitly uses `NoNewPrivileges=no`, no PrivateTmp, loopback
  IP filtering, AF_UNIX/INET/NETLINK, ProtectHome and null logs. Worker1 must test
  the effective unit/sudo inheritance on Linux; no claim that a macOS source test
  establishes elevation or registered guards. Template service never auto-restarts.

The fixed recovery interface must acquire the existing canonical lifecycle lock,
use current registered storage/root-disk guards, terminate/remove **only** the owned
image backend, start its reviewed exact image/checkpoint on Ada, wait native
readiness, complete deterministic warm generation, verify decoded success and Ada
residency, and return 0 only then. It must also verify the protected API config's
runtime/model pins match the deployed manifests. Nonzero/timeouts leave API closed.
Adapter code contains no container image, checkpoint path, systemctl command or
request-supplied admin action. Worker1 owns helper implementation and runtime launch.

Native persistent `input_save_path` and `output_path` must be `None`, with cloud
upload disabled, and native tempfile root on dedicated guarded registered data.
The pinned native function deletes its exact generated directory in `finally` but
uses `shutil.rmtree(..., ignore_errors=True)`. **HTTP 200 alone is not cleanup
evidence.** The initial finding is retained in the first delivery and its review
handoff. Root accepted bounded equivalent guarded-spool checks: Worker1 observes
exact owned TMPDIR before/after normal generation/edit and backend restart; fixed
recovery removes only exact owned orphan directories after backend stop under
anchored guards. Do not sweep shared temp roots or delete response-supplied paths.
No upstream cleanup repair or injected live GPU-failure campaign is required.
If actual residual files appear, record exact paths/ownership and make a narrow
correction. A needed helper cleanup-failure fixture may be a small offline source
test, not a new exhaustive deployment gate. Actual observations remain Worker1
integration evidence; the adapter's simulated spool fixture does not establish them.

## Qualification manifest

[`qualification.empty.json`](../scripts/image_api/qualification.empty.json) is the
install-time schema example with zero support claims. Root-protected manifest fields:

| Field | Meaning |
|---|---|
| `schema_version` | integer 1 |
| `runtime_revision` | `0cd8be351d0825488f4b81c8931167bbab618eca` |
| `model_id`, `model_revision` | `Qwen/Qwen-Image-2.1`, `790c92633540aa0cb11d9abf19eb46d861714758` |
| `runtime_image_digest` | `null` until known; exact `sha256:` OCI digest required for any profiles |
| `profiles` | list of separately reviewed measured cases, initially empty |
| `limits` | exact fixed `max_width=1920`, `max_height=1080`, `max_pixels=2073600`, `native_max_pixels=2088960`; missing or different values refuse startup |

Each profile requires `operation` (`generation`/`edit`), public `size`, `references`
(0 generation; 1/2 edit), `transparent` (boolean), `conditioning` (empty for opaque;
explicit bounded model conditioning text for transparent), and `evidence_sha256`
(lowercase 64-hex digest of reviewed qualification evidence). Optional `native_size`
and `crop_bottom` default to public size and 0 for the five smaller profiles. Full HD
requires both explicit mapping fields as described below. These
two effective fields are always exposed in capability records. Duplicate profiles
are rejected. Transparent profiles require both measured alpha and visual task
acceptance; output alpha is checked after any approved crop on every response. Configured
sizes, projected memory or this schema are never measured evidence. The helper
and manifest review bind evidence to exact actual model/runtime/build identity.

The sole nonidentity mapping is public `size=1920x1080`,
`native_size=1920x1088`, `crop_bottom=8`, opaque generation with zero references
or a separately qualified opaque edit with exactly one reference.
Missing mapping, raw native1080/crop0, two-reference Full HD, transparency and arbitrary mappings
are refused for Full HD. Native PNG dimensions must match 1920x1088 exactly
before removing rows1080..1087. An already-cropped or otherwise wrong response
fails. The existing safe PNG decode/crop/re-encode path strips metadata and emits
RGB. For a qualified one-reference Full HD edit, validate the original1920x1080
first, then create a separate PNG containing its unchanged decoded pixels plus
eight copies of its last row at the bottom. No source file changes or resampling
occur. The native reference is1920x1088, so the pipeline's target-area/multiple32
resize is identity. Capabilities expose `input_padding:{top:0,right:0,bottom:8,left:0}`
for this edit mapping (all zero for identity edit profiles). Generation capability
fields remain unchanged. Public input/output keeps the2073600-pixel limit; only
this internal padded reference and exact native output use2088960pixels.

The installed Qwen processor performs a second smart resize, using checkpoint
patch16/merge2 and65536..16777216pixel bounds. The proposed1024x1024,
1536x864 and padded1920x1088 references remain dimension-identical at both stages.
The current Torchvision resize returns its input when dimensions match;
normalization and model encoding still occur. This source audit is not image
fidelity or memory acceptance. All public edit profiles remain absent.

The generic template remains empty. The installed protected six-profile manifest
and hash-bound crop/native evidence are in the Full HD report. Root reviewed
exact source and evidence before activation; the separate live receipt records
the single public acceptance. Offline fixtures remain separate from live evidence. No model/runtime/settings/placement change or new memory qualification
is needed for the identical native workload.

## Offline verification and source migration

From the repository using the separate adapter environment:

```sh
uv venv ../.venv
uv pip sync --require-hashes --python ../.venv/bin/python scripts/image_api/requirements.lock
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tests/image_api ../.venv/bin/python -m unittest -v \
  test_corrections.FullHD test_protection.Configuration \
  test_handlers.Handlers.test_empty_profiles_fail_closed_and_capabilities_distinguish_profiles \
  test_handlers.Handlers.test_unsafe_unknown_fields_and_invalid_model_n_seed_size
```

Direct and transitive dependencies are hash-pinned in the separate
[`requirements.lock`](../scripts/image_api/requirements.lock); regenerate only after
review from its requirements.in using `uv pip compile --generate-hashes --universal`.
No text/runtime environment is modified. Focused fixtures exercise actual async
handlers, ownership, cancellation, decoding, wire behavior and source protection.
The fixture spool proves only simulated temp-directory cleanup, not SGLang/runtime
or image quality. The source-closure test uses direct invocation to avoid the
existing `tests/lifecycle` discovery namespace shadowing `scripts/lifecycle`.

The additive transport changes the protected fixed policy/helper signature and the
control source copy of `private_network.py`. It keeps the six old socket/service
files byte-identical, ports 30000/30002/30004, interface/subnet, rule ordering,
terminal DROP, systemd patch validation, no public/wildcard/IPv6 bind, and the
[existing private transport policy](private-network.md). Plain private HTTP has no
on-path encryption; no new TLS termination or TLS acceptance is claimed.

See [reviewed migration procedure](image-api-source-migration.md). Old receipts and
historical evidence are preserved, never edited to pretend new source was accepted.
A source bundle alone does not authorize runtime activation. The original source-only
task did not establish live inference, image quality, Linux service/sudo/storage,
cleanup, runtime pins, firewall or client acceptance. Subsequent retained deployment
and qualification evidence is recorded in the
[current report](../reports/image21-qualify-20260923/RESULT.md); its scope and limits
apply to those observations. The Full HD report separately records its bounded deployment and single acceptance status.

## Pinned primary source contract

Inspected official SGLang files at the pinned revision:
[image routes](https://github.com/sgl-project/sglang/blob/0cd8be351d0825488f4b81c8931167bbab618eca/python/sglang/multimodal_gen/runtime/entrypoints/openai/image_api.py),
[request/response schema](https://github.com/sgl-project/sglang/blob/0cd8be351d0825488f4b81c8931167bbab618eca/python/sglang/multimodal_gen/runtime/entrypoints/openai/protocol.py),
[temporary output/upload helpers](https://github.com/sgl-project/sglang/blob/0cd8be351d0825488f4b81c8931167bbab618eca/python/sglang/multimodal_gen/runtime/entrypoints/openai/utils.py),
[pinned warm health handler](https://github.com/sgl-project/sglang/blob/0cd8be351d0825488f4b81c8931167bbab618eca/python/sglang/multimodal_gen/runtime/entrypoints/http_server.py).
Generation sends allowlisted JSON; edit sends allowlisted multipart with generated
PNG/JPEG filenames and actual validated content. The adapter explicitly requests
b64_json because native generation defaults to URL. It sets both `guidance_scale`
and Qwen-specific `true_cfg_scale` to 1, with fixed CPU initial-noise RNG. Native `data[0].b64_json` is decoded and all
other native fields are discarded. No native content/download endpoint is exposed.
Captured source hashes and provenance accompany the taskroot evidence package.

## Unactivated editing seed correction

The [H003 diagnosis](../reports/h003-edit-20260923/RESULT.md) retains the failed
same-noise seed42 teapot regression and the successful seed43 counterpart.
This is a model/runtime seed-reuse limitation with an orchestration mitigation,
not a proven denoiser repair. Editing profiles remain unqualified in production.

The source candidate preserves every explicit seed exactly. For a validated edit
that omits seed, it chooses one fresh random32-bit seed and retains it in the
owned request instead of inheriting native seed42. Successful edit responses add
`data[0].seed` with the actual native seed; `created` and `b64_json` are unchanged.
The additive seed field is an image API extension. Generation defaults, explicit
generation seeds and generation response fields are unchanged. No retry redraws
a seed, and rejected unqualified edits do not draw or dispatch.

The harness owns persistence of actual seed provenance with artifacts, avoidance of
known source/ancestor seeds when choosing a missing seed, and rejection of explicit
known collisions before dispatch with `source_seed_collision`. The image API
does not infer provenance or rewrite explicit seeds. Unknown provenance cannot
guarantee collision avoidance. This source candidate is not deployed; exact root
review and separate live acceptance/qualification are still required.
