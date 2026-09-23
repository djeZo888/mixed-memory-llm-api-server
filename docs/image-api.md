# Bounded private image API — source integration

The IMAGE21 source task adds an authenticated adapter for `qwen-image-2.1`.
Source/offline fixtures are not SGLang execution, real-image qualification, or a
production release. The shipped qualification manifest contains **no measured
profiles and no runtime image digest**; inference and readiness remain closed.
Worker1 supplies exact runtime/checkpoint/build manifests and qualification after
root review. This does not change text slot implementations or their profiles.

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
| POST `/v1/images/edits` | Multipart request with `image` or `image[]` files, synchronous PNG `b64_json` |

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
The sole optional pad/crop path requires measurement of the exact UHD recipe below.

Limits are 32MiB encoded/file, 64MiB combined encoded files, two references,
64MiB+64KiB total streamed multipart body including its bounded envelope, and
64KiB JSON body. Content-Length, MIME type and uploaded filename never authorize
content. Decode actual PNG/JPEG dimensions and reject malformed/bomb/multiframe
images. Each edit reference must equal the exact qualified public output dimensions.
Maximum dimensions are 3840x2160 and 8294400 pixels, permitted only in a reviewed
profile. One-reference editing and generation are separate profiles. Two-reference
sizes require their own evidence, remain 1024-class until then, and never inherit
the one-reference ceiling. Output must decode as one PNG of the exact selected
native size, then only the explicitly approved bottom crop if present; public output
remains at most8294400 pixels. Re-encoding strips native metadata. Only `created` and `data[].b64_json` are
returned, never raw native errors, revised prompts, paths or URLs.

## Admission and recovery

One process, one active owned operation, zero waiting requests. Admission is taken
before upload parsing. A competing request receives immediate429 with
`Retry-After: 1`; an unready idle service returns503. Invalid requests return400,
encoded limits413, wrong generation media type415, native failure502, deadline504.
Readiness GET and pre-submission admission each use one native `/health` request.
The latter runs after atomic image ownership reservation and validation, immediately
before native submission. A separate health client avoids the image client's busy
single connection: total budget2s, connect/read/write1s, pool0.5s, two health
connections, at most1024 response bytes, fixed loopback URL, no proxy or redirects.
Only the pinned warm-readiness response200 with exact JSON `{"status":"ok"}` passes.
Failure/timeout/invalid health returns503 and latches admission closed; canceling a
readiness probe conservatively latches it closed too. Successful
health alone never reopens it. GET never invokes recovery or cancels active images.
A successful active image also cannot erase a concurrent health-failure latch.
There is no polling daemon. Required helper reconciliation remains the only reopening
path. Busy image contenders still receive429 while any admission probe is pending.

Client cancellation/disconnect does not cancel the supervisor or native operation.
The supervisor strongly retains all upload buffers, CPU decode tasks and native
transport until settlement. CPU image work runs off-loop and remains owned through
cancellation; a monotonic deadline prevents late native submission or late200.

The900s budget includes body receive/validation/native call. A timeout before
submission cancels upload work and releases only after owned validation settles.
An unresolved native timeout, or ambiguous transport/output failure, closes readiness
and invokes the fixed recovery helper once. The504 response does not wait for
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
- Fixed entrypoint `/usr/local/lib/llm-server/image-api/scripts/image_api/serve.py`,
  via the separately pinned venv Python with `-I -B`. No server arguments allowed.
- Config `/etc/llm-server/image-api.json`, root:root0644 with protected ancestry.
- Credential `/run/credentials/llm-image-api.service/inference-key`, mode0400/0600,
  root or service-owned, no symlinks/hardlinks/mutable ancestry. Source is existing
  registered `services/secrets/llm-api-key`; verify its protected metadata and
  exact deployed LoadCredential mapping without printing it.
- Runtime lock `/run/llm-image-api/owner.lock`, owned service uid0600 in0700
  systemd RuntimeDirectory. No adapter data/spool/log/cache writes; uploads are
  memory only. Output/access/error logs and core dumps are disabled.
- Recovery command is exactly `/usr/bin/sudo -n -- /usr/local/libexec/llm-image-backend-recover`.
  Root-owned0755 helper, protected ancestry, zero arguments and900s self-cap.
  Render sudoers root:root0440, run `visudo -cf` on that rendered file. Its `""`
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
residency, and return0 only then. It must also verify the protected API config's
runtime/model pins match the deployed manifests. Nonzero/timeouts leave API closed.
Adapter code contains no container image, checkpoint path, systemctl command or
request-supplied admin action. Worker1 owns helper implementation and runtime launch.

Native persistent `input_save_path` and `output_path` must be `None`, with cloud
upload disabled, and native tempfile root on dedicated guarded registered data.
The pinned native function deletes its exact generated directory in `finally` but
uses `shutil.rmtree(..., ignore_errors=True)`. **HTTP200 alone is not cleanup
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
| `schema_version` | integer1 |
| `runtime_revision` | `0cd8be351d0825488f4b81c8931167bbab618eca` |
| `model_id`, `model_revision` | `Qwen/Qwen-Image-2.1`, `790c92633540aa0cb11d9abf19eb46d861714758` |
| `runtime_image_digest` | `null` until known; exact `sha256:` OCI digest required for any profiles |
| `profiles` | list of separately reviewed measured cases, initially empty |

Each profile requires `operation` (`generation`/`edit`), public `size`, `references`
(0 generation;1/2 edit), `transparent` (boolean), `conditioning` (empty for opaque;
explicit bounded model conditioning text for transparent), and `evidence_sha256`
(lowercase64-hex digest of reviewed qualification evidence). Optional `native_size`
and `crop_bottom` default to public size and0, preserving existing profiles. These
two effective fields are always exposed in capability records. Duplicate profiles
are rejected. Transparent profiles require both measured alpha and visual task
acceptance; output alpha is checked after any approved crop on every response. Configured
sizes, projected memory or this schema are never measured evidence. The helper
and manifest review bind evidence to exact actual model/runtime/build identity.

The sole nonidentity mapping is an explicit public `size=3840x2160`,
`native_size=3840x2176`, `crop_bottom=16` profile: generation with0 references or
editing with exactly1. Remove exactly the16 bottom native output rows; for the edit,
edge-pad exactly16 bottom input rows by repeating the last decoded public row.
No resize, distortion, arbitrary crop or larger public image admission. Public
input/output limits remain8294400 pixels; only this native recipe allows8355840.
All other profiles require native=public and crop0. Two-reference UHD is rejected
pending separate root authorization/qualification. Native dimensions must match
exactly before cropping; an already-cropped or otherwise wrong response fails.

For example, that future measured edit entry would authorize only same-public-size
one-reference UHD edits with this precise padding/cropping recipe. It says nothing
about transparency or generation support. This is a schema example, **not a shipped
or measured profile**. Worker1 must measure this exact recipe with>=5% VRAM margin
and visual success before publishing any entry. Default profiles remain empty.

## Offline verification and source migration

From the repository using the separate adapter environment:

```sh
uv venv ../.venv
uv pip sync --require-hashes --python ../.venv/bin/python scripts/image_api/requirements.lock
PYTHONDONTWRITEBYTECODE=1 ../.venv/bin/python -m unittest discover -s tests/image_api -v
PYTHONDONTWRITEBYTECODE=1 ../.venv/bin/python -m unittest discover -s tests -p 'test_private_network*.py' -v
PYTHONDONTWRITEBYTECODE=1 ../.venv/bin/python tests/test_control_source_closure.py
python3 -B scripts/control/private_network.py source-check
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
files byte-identical, ports30000/30002/30004, interface/subnet, rule ordering,
terminal DROP, systemd patch validation, no public/wildcard/IPv6 bind, and the
[existing private transport policy](private-network.md). Plain private HTTP has no
on-path encryption; no new TLS termination or TLS acceptance is claimed.

See [reviewed migration procedure](image-api-source-migration.md). Old receipts and
historical evidence are preserved, never edited to pretend new source was accepted.
No source bundle authorizes runtime activation. Live native inference/image quality,
Linux service/sudo/storage, exact native cleanup, runtime pins, firewall and client
acceptance are **NOT_TESTED** by this source task.

## Pinned primary source contract

Inspected official SGLang files at the pinned revision:
[image routes](https://github.com/sgl-project/sglang/blob/0cd8be351d0825488f4b81c8931167bbab618eca/python/sglang/multimodal_gen/runtime/entrypoints/openai/image_api.py),
[request/response schema](https://github.com/sgl-project/sglang/blob/0cd8be351d0825488f4b81c8931167bbab618eca/python/sglang/multimodal_gen/runtime/entrypoints/openai/protocol.py),
[temporary output/upload helpers](https://github.com/sgl-project/sglang/blob/0cd8be351d0825488f4b81c8931167bbab618eca/python/sglang/multimodal_gen/runtime/entrypoints/openai/utils.py),
[pinned warm health handler](https://github.com/sgl-project/sglang/blob/0cd8be351d0825488f4b81c8931167bbab618eca/python/sglang/multimodal_gen/runtime/entrypoints/http_server.py).
Generation sends allowlisted JSON; edit sends allowlisted multipart with generated
PNG/JPEG filenames and actual validated content. The adapter explicitly requests
b64_json because native generation defaults to URL. It sets both `guidance_scale`
and Qwen-specific `true_cfg_scale` to1, with fixed CPU initial-noise RNG. Native `data[0].b64_json` is decoded and all
other native fields are discarded. No native content/download endpoint is exposed.
Captured source hashes and provenance accompany the taskroot evidence package.
