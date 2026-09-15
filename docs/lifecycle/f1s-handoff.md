# F1S Qwen3-Coder-Next source handoff

F1S extends the reviewed D2 source with an explicit `sglang` backend. This is a
bounded source implementation. **Live inference, GPU fit, pinned-image launcher
execution, parser round trips and real agent acceptance are NOT_TESTED here.**
Worker1/F1D executes those gates on the reviewed merged source. The whole fresh
Linux installer remains I1/I2 work. [Source report](../../reports/f1s-source.md).

## Ownership and installer interface

F1S owns `scripts/lifecycle/manager.py`, `qwen_next.py`, `sglang_file_auth.py`, the
new JSON profiles and their lifecycle/auth tests. I1 owns installation, common
storage guards and systemd provisioning; I1 must not patch lifecycle/profiles.
D2CI owns its CI workflow correction. A1 agent, V0 client, D1 acquisition/build,
common installer files, README and current-state are unchanged by F1S.

The early installer handshake is persisted at taskroot `installer-handshake.md`.
The final interface below supersedes draft implementation details in that file.
Use the new [instance reference](../../configs/deployments/instances/f1s.template.json)
additively: preserve the actual instance ID, mount UUIDs, existing GLM evidence,
D2 state, mutex and recovery paths. A template never authorizes activation.

## Profiles and immutable inputs

| Field | Exact contract |
| --- | --- |
| Deployment and served alias | `qwen3-coder-next` |
| Model / runtime profiles | `qwen3-coder-next-fp8` / `sglang-qwen-next-0.5.14` |
| Repository | `Qwen/Qwen3-Coder-Next-FP8` |
| Revision | `da6e2ed27304dd39abadd9c82ef50e8de67bdd4c` |
| Expected manifest SHA256 | `022674d4daf63fa57c2798a30fea80c6dde7b1b2e73630ae3c3aa94e45debb9e` |
| Artifacts | 48 files: 40 weights + 8 assets; 80407722953 total bytes; 80381394600 weight bytes |
| Image | `lmsysorg/sglang:v0.5.14-cu130` |
| Image content ID | `sha256:5027e95bf6ec536856b1b52a91d1f35ff5c564ab83e8a94758a169ff09bb8df3` |
| Endpoint | `http://127.0.0.1:30003/v1` |
| Container / internal bind | `llmctl-qwen3-coder-next` / `0.0.0.0:30003` |
| GPU and request bounds | IDs `0,1`, TP2, context 32768, tokenizer workers 1, max running requests 1, mem fraction 0.75 |
| Parser and load format | `qwen3_coder`, `safetensors`; FP8 comes from official config |

The [F1A manifest](../../reports/f1s-contract-evidence/f1a-qwen-manifest.json) is an
exact immutable expected-file inventory, **not acquisition completion**. F1A
reported the eight small files verified while weights were still downloading.
Lifecycle never downloads weights or pulls/builds an image. Model command is
`--model-path /models`, independent of historical Qwen30B service identities.

| Host source | Container destination | Access |
| --- | --- | --- |
| `/data/models-large/qwen3-coder-next-fp8` | `/models` | Read only |
| `/data/models-large/runtime-cache/sglang-qwen-next` | `/cache` | Writable cache |
| `/data/logs/llmctl/qwen3-coder-next` | `/logs` | Writable logs |
| `/data/services/llm-manager/qwen3-coder-next` | `/service` | Writable service scratch |
| `/data/services/secrets/llm-api-key` | `/run/secrets/llm-api-key` | Read only file |
| `/data/services/llm-manager/adapters/sglang_file_auth.py` | `/opt/llmctl/sglang_file_auth.py` | Read only file |

I1 installs the exact reviewed `scripts/lifecycle/sglang_file_auth.py` as a
root-owned, nonsymlink regular mode 0644 file; every parent is root-owned and not
group/other writable. Manager compares installed bytes with adjacent reviewed
source and recorded `runtime_evidence.<runtime>.launcher_sha256` at start/reuse.
Stop does not need this file, profile, key or model to remain readable.

The Docker entrypoint is explicitly `python3`. Readonly container root, writable
`/tmp` tmpfs (1GiB) and private `/dev/shm` (8GiB) avoid image-layer writes. Workdir
is `/service`; inherited image healthcheck is disabled. Logs rotate 20 MB x 3 on
`/data/docker`; no raw logs are relayed by llmctl. HF offline/cache, XDG, Triton and
TorchInductor variables have exact nonsecret `/cache` settings.
`DISABLE_OPENAPI_DOC=1` disables native Swagger/ReDoc/OpenAPI UI routes at import. Reuse requires
exact inherited image environment plus these overrides, launch, image ID, mounts,
GPU IDs, logging, process and security settings. Unknown launch options fail.

## Completion and auth evidence gates

Instance `model_integrity.qwen3-coder-next-fp8` requires `verified:true`, exact
`revision`, nonempty `evidence`, `manifest_sha256` equal to the immutable F1A hash,
and `completion_manifest` under `/data/services/llm-manager/acquisition/`.
Recommended name: `qwen3-coder-next-fp8.complete.json`.

That root-owned protected regular file must contain:

```json
{
  "schema_version": 1,
  "complete": true,
  "repo_id": "Qwen/Qwen3-Coder-Next-FP8",
  "revision": "da6e2ed27304dd39abadd9c82ef50e8de67bdd4c",
  "model_root": "/data/models-large/qwen3-coder-next-fp8",
  "manifest_sha256": "022674d4daf63fa57c2798a30fea80c6dde7b1b2e73630ae3c3aa94e45debb9e",
  "artifact_count": 48,
  "total_bytes": 80407722953,
  "artifacts": []
}
```

The empty list above is deliberately **invalid**. Worker1 fills exactly 48 records
`{path,size_bytes,sha256,verified:true}`, matching each immutable artifact after
hashing all downloaded files and checking index/config. Missing, partial,
false or mismatched completion fails start before Docker creation/start. Start
then stats every file for exact size and no symlink; it does not rehash 80 GB.
Status does not inspect the weights. Integrity remains an operator attestation
backed by completed acquisition evidence; protect files against later mutation.

Instance `runtime_evidence.sglang-qwen-next-0.5.14` requires exact `image_id`,
`flags_verified:true`, all profile `supported_flags`, nonempty `evidence`, exact
`launcher_sha256`, `auth_gate_passed:true`, and nonempty `auth_gate_evidence`.
**Only F1D's actual pinned-image sentinel launch/setup proof may satisfy the auth
gate.** The template keeps it false. Source AST/mock tests cannot turn it on.

## Authentication and startup

The reviewed launcher keeps both `ServerArgs.api_key` and `admin_api_key` None.
In guarded main, it validates nonsecret arguments, reads the separate protected
file, installs the *native* `add_api_key_middleware` onto the actual module-global
FastAPI app and directly calls `http_server.launch_server`. Setup retains that
app and may layer a second native empty-key middleware for admin-force endpoints.
Both layers are tested together. Spawn imports do not read keys or register/launch.

Key file contract matches A1/D2: owned regular mode 0600, O_NOFOLLOW, bounded
1..4096 printable ASCII bytes, no spaces/newlines; readonly mount. Existing key
files are never provisioned or rotated by F1S. Key bytes never enter Docker config,
argv, environment, YAML, ServerArgs, GPU worker arguments, state or evidence.
Native startup repr and `/server_info` therefore retain model identity and
nonsecret options without leaking the key. Diagnostics are generic.

Custom warmup holds the separate key, sends authenticated `/model_info` then a
tiny `/generate` request, and marks `ServerStatus.Up` only after success. It has a
600-second deadline; the launcher/model startup has a 7200-second deadline. No
temporary bypass or requests-global mutation exists. Failure closes the launcher
process tree; manager startup failure also stops only the recorded owned container,
retaining its identity and truthful running/unknown state if cleanup fails.
D2's GLM failure semantics are retained.

Native policy is precise:

- Ordinary `/v1/models`, `/v1/chat/completions`, `/model_info`, `/generate`,
  `/server_info`, `/get_server_info` require a correct Bearer key. Missing/wrong
  keys receive 401; correct-key requests reach actual route handlers.
- Native exemptions are **all paths beginning `/health` or `/metrics`, plus all
  OPTIONS requests**. These pass the auth layer, and the routed handler controls
  final status. `/health` is a generation-based health probe and returns 503 while
  Starting; exemptions do not mean every such path exists or returns 200.
- Non-OPTIONS admin-force requests remain denied 403 because no admin key is
  configured (native OPTIONS/probe-prefix exemptions still apply).
- Every WebSocket scope is rejected, including `/v1/realtime`, for this chat-only
  profile. HTTP SSE bodies and disconnect events pass unchanged.
- Multiple tokenizer/HTTP workers, Ray, gRPC, encoder-only, HTTP2, reload, tool
  server/plugins and other nonreviewed launch paths are refused. There is one
  published loopback port. Tool execution, browsing and UI live on another VM.

## Shipped actual-image auth fixture

Run the shipped helper in the exact pinned image before any real key/model. It
imports installed SGLang and real FastAPI/Starlette; actual-image mode must fail
if those dependencies/source identities are missing. It does not fall back to
the copied AST fixtures. Model/engine/worker startup is stubbed and HTTP handlers
return synthetic content; this proves auth wiring, not inference. The native
parser and ServerArgs normalization run; only explicit CUDA discovery probes and
engine/model/worker collaborators are synthetic. Uvicorn is captured, so native
lifespan model-serving initialization remains NOT_TESTED. The helper also tests
real native health Starting 503/Up 200 and actual child-process cleanup.

The helper creates a generated sentinel in private tmpfs using exclusive create
at `/run/secrets/llm-api-key`, mode0600, and refuses an existing file. No host key
or model directory is mounted. Output is fixed safe PASS/FAIL evidence only.
There is no GPU, published port, external network or Docker logging. Loopback
inside the isolated container is available for synthetic warmup HTTP requests.

Worker1/F1D command, after verifying the reviewed checkout commit:

```bash
set -euo pipefail
cd /data/services/mixed-memory-llm-api-server
scripts/common/require-data-mounted.sh
scripts/common/root-disk-guard.sh --report /data/logs/f1d-auth-pre-root-guard.md
sudo -n docker run --rm --pull never --runtime runc \
  --network none --read-only --log-driver none \
  --cap-drop ALL --security-opt no-new-privileges:true \
  --env NVIDIA_VISIBLE_DEVICES=void --env CUDA_VISIBLE_DEVICES= \
  --env DISABLE_OPENAPI_DOC=1 --env HF_HUB_OFFLINE=1 --env TRANSFORMERS_OFFLINE=1 \
  --env HF_HOME=/cache/huggingface --env XDG_CACHE_HOME=/cache \
  --env TRITON_CACHE_DIR=/cache/triton --env TORCHINDUCTOR_CACHE_DIR=/cache/torchinductor \
  --tmpfs /tmp:rw,nosuid,nodev,size=512m \
  --tmpfs /cache:rw,nosuid,nodev,size=512m \
  --tmpfs /models:rw,nosuid,nodev,mode=0755,size=16m \
  --tmpfs /run/secrets:rw,nosuid,nodev,mode=0700,size=64k \
  --mount "type=bind,source=$PWD,target=/fixture,readonly" \
  --workdir /fixture --entrypoint python3 \
  sha256:5027e95bf6ec536856b1b52a91d1f35ff5c564ab83e8a94758a169ff09bb8df3 \
  /fixture/tests/lifecycle/sglang_fixture/run_pinned_image.py --actual-image --repo /fixture
scripts/common/require-data-mounted.sh
scripts/common/root-disk-guard.sh --report /data/logs/f1d-auth-post-root-guard.md
```

Record the safe result, exact image ID and launcher SHA256 in F1D evidence. A
nonzero exit, unexpected output, or an incomplete case is a STOP before the auth
gate. The exact same command is **NOT_TESTED on mac-worker2**, where Docker is
unavailable. Worker-side syntax/control-boundary tests do not change that status.

## Worker1/F1D next actions

On the reviewed integrated commit and under Worker1's existing authorization:

1. Run common data-mount/root guards before and after provisioning/deployment.
   Keep exact `/data` and `/data/models-large` instance UUID checks, Docker root
   `/data/docker`, single D2 boot owner and `restart=no`.
2. Run the shipped actual-image fixture above (the retained F1A inspection
   harness is additional evidence only), with a generated sentinel and no real
   key/model/GPU. Execute F1S guarded launcher, real installed setup and final
   FastAPI/Starlette chain captured at Uvicorn. Test all auth/exemption/WS/admin,
   repr/asdict/server-info/log/workerargs nonleakage, SSE/disconnect, child import,
   rejected modes, warmup timeout/failure and process cleanup. Record evidence
   and launcher hash. Stop on any mismatch; do not merely replay the mocks.
3. Complete all 48 artifact hashes and native index/config validation; write the
   separate completion receipt. Merge evidence into the existing instance.
4. After pinned-image auth PASS, preserve existing production key exact bytes.
   Stop the active backend via D2; select `qwen3-coder-next --boot-policy manual`,
   review `start --dry-run`, then explicitly `start --yes`. Commands are
   `python3 scripts/llmctl ... --instance /data/services/llm-manager/deployment-instance.json`.
5. Verify live missing/wrong/correct-key models/chat/server_info, unauthenticated
   WS rejection, and no sentinel/key in metadata, startup logs or server-info.
   Confirm exact image, mounts, launcher hash, context/GPU/parser and loopback
   publication. Measure startup, CPU/RAM/GPU allocation, latency and true tokens.
6. Run A1/V0 from a worker: nonstream chat; complete SSE including DONE and client
   disconnect; forced parser tool call with structured arguments; execute the
   tool on the worker; send matching tool_call_id result; obtain final answer.
   Then a real multi-step agent task (inspect files, edit, run tests, observe a
   failure, correct it and finish) with several tool turns, valid schemas and no
   tool execution on the inference VM. Record model/tool IDs, outcomes, token
   headroom and latency without credentials.
7. Verify GLM/Qwen cross-backend exclusion, explicit stop/reselect/restart,
   failure cleanup and D2 recovery-stop. Review boot resume separately after
   measured acceptance. Rollback selects the retained reviewed GLM/Qwen30B
   deployment after stopping this container; no prune/deletion is needed.

No readiness claim substitutes for these model/agent acceptance steps.

SGLang uses the explicit `runtime_io.probe_sglang` path: missing-key and wrong-key
`/v1/models` must reject; authenticated `/health` must return 200; authenticated
`/v1/models` must return exactly the selected alias. All four calls share one
request deadline, itself capped by the remaining overall startup deadline.
Models metadata while health is 503 remains not-ready. Native health is exempt
from auth, so health success alone never opens readiness. GLM keeps its existing
probe behavior. Probe failures emit safe codes without response payloads.

## Final launcher source identity

`scripts/lifecycle/sglang_file_auth.py` SHA256: `1bf781b83d1a6bf25b63b948550cf2926e16247f48d6f977188954e9a10d212a`.
Provenance: `reports/f1s-contract-evidence/launcher-provenance.json`.
I1 must copy these exact bytes to the protected readonly-mounted launcher path
and record this hash; F1D must bind its actual-image auth evidence to this hash.
The runtime additionally sets `DISABLE_OPENAPI_DOC=1` to disable documentation UI.
Current D2 two-mount scope is preserved; arbitrary data-root portability is L1.
