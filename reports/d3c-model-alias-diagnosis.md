# D3C — pinned runtime model-alias diagnosis

Date: 2026-09-15. **Diagnosis: PASS; strict A1 protocol aggregate: FAIL.**
Source/report only, based on reviewed repository `4ab862f829a560e00ae3f40d9358456db0a4c0e9`.

## Decision

**No supported native flag/config in this pin enforces the requested strict
served alias in single-model chat. Recommend a small native, standalone-only
chat request validator, subject to root's policy review.** No implementation,
rebuild, deployment or validation request is included in D3C.

Root supplied the observation: an invalid `model` on `/v1/chat/completions`
returned HTTP 200 with `model: "glm-5.3"`. This matches the pinned implementation
and upstream test expectations. It is a stock compatibility limitation against
the project's stricter contract, not evidence of model inability or an
established upstream regression. Ordinary chat/SSE passed; the full protocol
aggregate remains FAIL. D3's earlier proof predates that aggregate result.

A1 requires returned identity equality and invalid-ID HTTP 400/404/422
([acceptance.py:90–92,175–185](../scripts/agent/acceptance.py)); its explicit
silent-alias regression case requires aggregate FAIL
([test_agent_acceptance.py:385–388](../tests/test_agent_acceptance.py)). A1 does
not currently require a particular error `type`/`code`; the detailed shape below
is a proposed server contract. Keeping stock behavior would require an explicit
root compatibility decision, retaining the failed check and recording the
exception. It must not be turned into a passing harness result.

## Identity and evidence boundary

- llama.cpp pin: `b29c606e28a01b1bc8c1351026a0fa6e616bf6c4`, release `v0.4.1`;
  recorded binary `0.4.1-dev (build 62, commit b29c606)`.
- Recorded D1/D3 image:
  `sha256:6866856c573d69d504f82265321b182f631a7b3912a1ed1b4efbf893729d4e62`.
- [D1 proof](d1-runtime-proof.json), [D1b contract](d2-contract-evidence/d1b-runtime-contract.md)
  and [D3 proof](d3-glm-live-proof.md) supply installed identities; D3C did not
  inspect the VM or rerun binary help.
- Worker-side primary source files were fetched from the exact GitHub commit;
  every downloaded Git blob was recomputed against its pinned tree entry.
  [Manifest](d3c-evidence/source-manifest.json) records hashes, URLs and scope.
  Source line numbers below are one-based lines of those verified files.

### Actual flag finding

The saved binary excerpt at [d1-cli-selected.txt:40–41](d1-cli-selected.txt)
documents `-a, --alias STRING`: comma-separated API names; `LLAMA_ARG_ALIAS` is
the equivalent environment setting. The pin's
[arg.cpp:3006–3017][arg-alias] only strips/inserts names into `model_alias`.
It adds no request-validation policy. The current command already supplies
`--alias glm-5.3`; repeating or renaming it cannot reject an invalid ID.

The excerpt also documents `--models-preset PATH` at lines 68–70. The complete
pinned argument definitions [arg.cpp:3628–3657][arg-router] additionally define
`--models-dir`, `--models-max`, `--models-autoload` / `--no-models-autoload` for
router mode. These are not single-model validation switches. The full argument
source, parameter definitions and request paths reveal no strict-model option.
This negative finding comes from source inspection, **not** an assertion that
the selected help excerpt is exhaustive.

The selected TXT is **8,247 bytes**, matching D1's recorded selected-file hash.
D2 “verbatim” JSON decodes to 8,287 bytes: the only difference is 40 spaces
on blank line 13. Normalized lines agree; the two representations are not
byte-identical. Neither is full help.
Full installed help is documented as 58,136 bytes, SHA256
`a144e0605fbd0092e6e68cc51d1cdc3c3f8ea75bb63e2f53e4478ab2cde9e8a5`;
its full bytes were not recovered in the bounded worker artifact search.

## Pinned request/response trace

| Stage | Primary source evidence and consequence |
| --- | --- |
| Dispatch | [server.cpp:134–137,200–229,255–260][routes]: an explicit model path selects non-router mode; both `/chat/completions` and `/v1/chat/completions` share `post_chat_completions`. |
| Parse | [server-context.cpp:4930–4943][chat]: parses JSON, then calls `oaicompat_chat_params_parse`. No model comparison occurs. |
| Carry, then ignore | [server-common.cpp:1414–1424][copy]: remaining fields, including `model`, are copied into completion parameters. [server-schema.cpp:519–551][schema] evaluates registered fields; its schema has no `model` field/validator. `model` is not used to select weights. |
| Queue and identity | [server-context.cpp:4315–4342][queue]: evaluates task parameters, unconditionally assigns `oaicompat_model = meta->model_name`, then posts tasks. |
| Canonical alias | [server-context.cpp:1372–1383][name]: first element of the alias **set** becomes `model_name`; otherwise model name/file fallback. With the sole configured alias this is `glm-5.3`. Multiple aliases use set order, not CLI order. |
| Nonstream | [server-context.cpp:2124–2129][final-copy] copies task identity; [server-task.cpp:414–445][final-json] serializes it into the response. |
| SSE | [server-context.cpp:2071–2074][partial-copy] copies the same identity; [server-task.cpp:1111–1131][partial-json] emits it in partial chunks. [server-task.cpp:470–512][final-stream] uses it for final/usage chunks too. The HTTP SSE transition is [server-context.cpp:4380–4414][sse]. |

Upstream's [chat tests:10–45,82–106][upstream-tests] use a tinyllama fixture,
submit unrelated `codellama70b` and explicit null values expecting 200, and
verify the configured alias on a stream with omitted `model`. The comments
also record that reflecting the input name was removed. These tests were
**read, not run**. The [README:1308–1314][readme-chat] expressly limits its
OpenAI compatibility claim. Its explicit ignored-model wording at
[README:1445–1455][readme-control] belongs to the **control endpoint**;
the chat conclusion rests on the code and tests above.

### Why router controls do not solve this deployment

[server-models.cpp:1849–1874,1962–1990][router-validation] validates the body
model, resolves aliases, and may load the selected child; unknown/missing
names use HTTP 400 with numeric error code 400. Autoload defaults on and the
query parameter can override its setting. `--models-max 1` would still be
router lifecycle policy, not the existing one-slot concurrency contract.
Adding router configuration alongside the explicit model path does not
replace the single-model handler. Switching modes introduces child lifecycle
and routing; it is not recommended or authorized here.

Router aliases also matter to a future patch: child startup overwrites its
alias with the canonical name ([server-models.cpp:527–535][child-alias]), while
the proxy forwards the original body ([1539–1571][proxy-body]). A validator
in every child would reject some router-valid aliases, even if it accepted
the child's local alias set. Preserve that path by restricting the new policy
to standalone single-model serving.

## One recommended native change, for later review

**Scope:** only POST `/v1/chat/completions` and `/chat/completions`, both
nonstream and stream. Add a small native guard around their existing shared
handler in `tools/server/server.cpp`, installed only when
`!is_router_server && !child.is_child()`. Reuse the existing child distinction
([server-models.cpp:1666–1669][child-mode]); it is startup process state, never
a request-header bypass. This is a local handler guard, not another service.

Parse the original body as a JSON object and compare its top-level `model`
against the cached declared served ID and alias set exposed by `routes.get_model_info()`
([server-context.cpp:4543–4550,4646–4647][metadata]). Do not hard-code GLM, use
query fallback, trim/case-fold IDs, accept hidden model paths, or route/download
anything. Preserve omitted-field behavior explicitly:

| Provided value | Proposed result before any inference |
| --- | --- |
| Field omitted | Delegate unchanged; serve the loaded model and return its canonical alias. |
| Exact declared served ID or alias (allowlist here: only `glm-5.3`) | Delegate unchanged; preserve existing nonstream/SSE identity and generation behavior. |
| Other nonempty string, including whitespace/case variants or undeclared paths | HTTP **400**; `error.type="invalid_request_error"`, `error.param="model"`, `error.code="model_not_found"`, a bounded message such as “Requested model is not served by this server.” |
| Empty string, explicit null, boolean, number, array or object | HTTP **400**; `error.type="invalid_request_error"`, `error.param="model"`, `error.code=null`, message stating that model must be a nonempty string. |
| Invalid JSON or non-object body | HTTP **400**, same error envelope, `param=null`, `code=null`; no generation. |

Return `{"error":{...}}` as `application/json`, even with `stream=true` or a
conversation/session header. No SSE headers, role delta, usage, `[DONE]`,
task allocation, wake, template/media processing or session registration may
precede rejection. Use an ordinary `server_http_res` and an explicit
`server_http_res_ptr` return type. Accepted requests delegate to the original
handler, which keeps its normal response/sleep lifecycle; a second JSON parse
on accepted requests is the small cost of preserving that handler unchanged.

Coordinator Revision2 prefers HTTP 400: it satisfies A1 and follows the pinned
router's unknown-model status precedent. This is an OpenAI-shaped error contract,
not a claim that every OpenAI service uses identical status/code semantics.
Two implementation details keep the proposal bounded:

1. Guard before `create_response()`: it can wake a sleeping backend
   ([server-context.cpp:4229–4237,4650–4652][sleep]). Likewise `set_req()` occurs
   at line 4270, before queuing, and can register a stream session
   ([server-stream.cpp:597–614][session]). Read only cached identity metadata
   in the guard, never inference context or template references.
2. Set numeric HTTP status separately from JSON `error.code`:
   [server-context.cpp:4243–4245][error-code] currently assumes that code is an
   integer. Do not globally change that formatter. The HTTP error handler
   [server-http.cpp:145–159][http-error] currently overwrites every 404 body;
   the pinned [httplib.cpp:8612–8619][httplib-error] invokes it for error statuses.
   **Use 400 and leave that HTTP handler unchanged.** A 404 proposal would need
   another preservation change and route regression checks; it is not recommended.

Keep existing readiness/auth middleware and route registration order
([server-http.cpp:196–243,276–306][auth]). In ready state missing/wrong keys
must still produce 401 before model diagnostics; preserve existing loading
503 and OPTIONS behavior. Preserve router/child handlers, auth headers and
successful chat behavior. Preserve exact declared aliases deliberately: they all resolve to the canonical
response ID, with no promise to echo a secondary alias. A1's configured ID stays
the canonical `glm-5.3`; this is caller correctness for a model catalog.

**Profile seam:** `endpoint.served_model` already supplies `--alias`
([32K profile:8–13,95–98](../configs/deployments/glm-5.3-ud-q4-k-xl-32k.json),
[manager.py:770–791](../scripts/lifecycle/manager.py)). No flag-only edit exists.
A reviewed implementation would need a separately pinned patched runtime/image
and new runtime/profile evidence, retaining D1 as rollback provenance. Preserve
32K, parallel 1, all launch arguments, key handling and image identity checks;
do not overwrite the old D1 proof to describe a patched image.

### Reproducible build and installer integration (proposal only)

Use a reviewed, clean **derived native Git commit** based exactly on the pin,
with an archived patch SHA256 and resulting tree identity. Record upstream
base, patch, derived commit, source repository/bundle, build recipe hashes and
new image ID separately; do not mislabel modified source as clean upstream.
Actual new hashes can only be recorded after that separate source task.

- [Dockerfile:3–45](../containers/llama-cpp/Dockerfile) and
  [build-runtime.sh:33–63](../scripts/d1/build-runtime.sh): retain clean-tree,
  exact-commit and Jinja-ancestor checks; point a new reviewed build invocation
  at the derived commit and a new tag. Update OCI source/revision/version labels
  (Dockerfile:40–42) to match the derived-source provenance and actual binary
  version; runtime `_image_ok` checks the source/revision labels. Preserve CUDA base digests, package
  snapshot, compiler/CMake options and jobs. Reuse existing Docker base/package
  layer cache without pruning or `--no-cache`. The changed source invalidates
  the current monolithic compile layer; **object-cache reuse is not established**
  and must not be promised. No CUDA or concurrency tuning belongs in this patch.
- New runtime/profile, deployment-instance image binding and build/help proof
  must agree. Retain old D1 artifacts; select the new runtime only in a later
  approved deployment. Lifecycle's existing image/command checks remain enforced.
- Installer pins are in `scripts/install/versions.lock.json` → `runtimes.glm`
  (recipe/profile/proof hashes, source revision/repository, image tag/reference
  ID). [runtime.py:33–75,235–245,375–395,467–504](../scripts/install/runtime.py)
  validates those identities, fetches/builds and probes them. Its current
  hard-coded upstream repository/profile/proof allowlist must be deliberately updated
  for the reviewed derived source and new proof path (currently hard-coded
  `reports/d1-runtime-proof.json`), never relaxed to arbitrary sources.
  Update the selected profile mapping in `scripts/install/host.py:69` and
  bundled source ownership in `scripts/install/main.py:50–51` together.
- Refresh installer proof/profile/recipe hashes, expected CLI/source version,
  runtime validation fingerprint/registry evidence, and source tests in
  `tests/install/test_runtime.py`; reject stale upstream-only proof, wrong
  patch/commit, dirty tree, recipe drift and wrong image. Coordinate these
  installer changes with its owner. Existing deployed protected state is not
  an input to mutate during D3C. All later builds/service work require the
  prescribed mounted-data/root-disk guards before and after.

This proposal intentionally makes **no all-endpoint strictness claim**.
Legacy completions, `/v1/completions`, Responses, embeddings, rerank, token
counting, control and other APIs retain their stock contracts. Extending the
guard to those routes is a separate root policy decision, not hidden scope.

## Bounded verification and handoff

Performed here: pinned blob/hash verification; D1 selected-help hash and verbatim normalized-line
agreement (the 40-byte whitespace discrepancy is recorded); complete pinned argument and chat call-path inspection; independent
contract/router review; report/reference checks; `git diff --check` and local
grep-based secret scan. No production source/config changes, native tests,
backend invocations, model/API requests, builds, GPU allocation, SSH/ai-vm
access, protected-state reads, service operations or disk mutations occurred.
The source copy is a small worker-side research artifact, not a backend build.

Future verification **requires a separately authorized implementation task**:

1. Pure native validator cases for every row above, both chat paths and both
   stream values, plus a declared secondary alias and an undeclared catalog ID;
   assert numeric HTTP status and exact error keys/types.
2. In-process route tests with a fake downstream handler and counters: rejected
   calls never reach generator/wake, tokenizer/template, queue or stream-session
   setup. Include a conversation ID; prove no existing session is replaced.
3. Exercise HTTP response serialization with the pinned HTTP layer: unknown-ID
   HTTP 400 preserves `model_not_found`, content type stays JSON,
   `is_stream=false`; missing-route 404 remains unchanged. A validator-only
   test cannot establish this.
4. Test readiness/auth order and successful handler delegation unchanged;
   prove the guard is absent for router and child paths, including a
   router-valid alias different from the child's canonical ID. No real child
   process or model is needed for these source/unit checks.
5. Only after source review, new immutable image evidence and separate runtime
   authorization, let the exclusive lease owner perform bounded exact-alias,
   invalid-ID and omitted-ID chat checks (nonstream/SSE) and rerun unchanged A1.
   No new test-model launch is proposed. Keep actual generation/protocol
   evidence separate from pure unit checks.

**Next action:** root chooses policy and whether to commission the bounded
native patch. D3C itself is complete as diagnosis only. V1G2 retains the sole
GLM request lease on the unchanged 32K baseline. Coordination Revision2 was reread and incorporated before commit. Root was informed early via
task-root `coordination-output.md`; final task-root handoff and incremental
`D3C.bundle` identify the report commit and required reviewed base.

[arg-alias]: https://github.com/ggml-org/llama.cpp/blob/b29c606e28a01b1bc8c1351026a0fa6e616bf6c4/common/arg.cpp#L3006-L3017
[arg-router]: https://github.com/ggml-org/llama.cpp/blob/b29c606e28a01b1bc8c1351026a0fa6e616bf6c4/common/arg.cpp#L3628-L3657
[routes]: https://github.com/ggml-org/llama.cpp/blob/b29c606e28a01b1bc8c1351026a0fa6e616bf6c4/tools/server/server.cpp#L134-L260
[chat]: https://github.com/ggml-org/llama.cpp/blob/b29c606e28a01b1bc8c1351026a0fa6e616bf6c4/tools/server/server-context.cpp#L4930-L4943
[copy]: https://github.com/ggml-org/llama.cpp/blob/b29c606e28a01b1bc8c1351026a0fa6e616bf6c4/tools/server/server-common.cpp#L1414-L1424
[schema]: https://github.com/ggml-org/llama.cpp/blob/b29c606e28a01b1bc8c1351026a0fa6e616bf6c4/tools/server/server-schema.cpp#L519-L551
[queue]: https://github.com/ggml-org/llama.cpp/blob/b29c606e28a01b1bc8c1351026a0fa6e616bf6c4/tools/server/server-context.cpp#L4315-L4342
[name]: https://github.com/ggml-org/llama.cpp/blob/b29c606e28a01b1bc8c1351026a0fa6e616bf6c4/tools/server/server-context.cpp#L1372-L1383
[final-copy]: https://github.com/ggml-org/llama.cpp/blob/b29c606e28a01b1bc8c1351026a0fa6e616bf6c4/tools/server/server-context.cpp#L2124-L2129
[final-json]: https://github.com/ggml-org/llama.cpp/blob/b29c606e28a01b1bc8c1351026a0fa6e616bf6c4/tools/server/server-task.cpp#L414-L445
[partial-copy]: https://github.com/ggml-org/llama.cpp/blob/b29c606e28a01b1bc8c1351026a0fa6e616bf6c4/tools/server/server-context.cpp#L2071-L2074
[partial-json]: https://github.com/ggml-org/llama.cpp/blob/b29c606e28a01b1bc8c1351026a0fa6e616bf6c4/tools/server/server-task.cpp#L1111-L1131
[final-stream]: https://github.com/ggml-org/llama.cpp/blob/b29c606e28a01b1bc8c1351026a0fa6e616bf6c4/tools/server/server-task.cpp#L470-L512
[sse]: https://github.com/ggml-org/llama.cpp/blob/b29c606e28a01b1bc8c1351026a0fa6e616bf6c4/tools/server/server-context.cpp#L4380-L4414
[upstream-tests]: https://github.com/ggml-org/llama.cpp/blob/b29c606e28a01b1bc8c1351026a0fa6e616bf6c4/tools/server/tests/unit/test_chat_completion.py#L10-L106
[readme-chat]: https://github.com/ggml-org/llama.cpp/blob/b29c606e28a01b1bc8c1351026a0fa6e616bf6c4/tools/server/README.md#L1308-L1314
[readme-control]: https://github.com/ggml-org/llama.cpp/blob/b29c606e28a01b1bc8c1351026a0fa6e616bf6c4/tools/server/README.md#L1445-L1455
[router-validation]: https://github.com/ggml-org/llama.cpp/blob/b29c606e28a01b1bc8c1351026a0fa6e616bf6c4/tools/server/server-models.cpp#L1849-L1990
[child-alias]: https://github.com/ggml-org/llama.cpp/blob/b29c606e28a01b1bc8c1351026a0fa6e616bf6c4/tools/server/server-models.cpp#L527-L535
[proxy-body]: https://github.com/ggml-org/llama.cpp/blob/b29c606e28a01b1bc8c1351026a0fa6e616bf6c4/tools/server/server-models.cpp#L1539-L1571
[child-mode]: https://github.com/ggml-org/llama.cpp/blob/b29c606e28a01b1bc8c1351026a0fa6e616bf6c4/tools/server/server-models.cpp#L1666-L1669
[metadata]: https://github.com/ggml-org/llama.cpp/blob/b29c606e28a01b1bc8c1351026a0fa6e616bf6c4/tools/server/server-context.cpp#L4543-L4647
[sleep]: https://github.com/ggml-org/llama.cpp/blob/b29c606e28a01b1bc8c1351026a0fa6e616bf6c4/tools/server/server-context.cpp#L4229-L4237
[session]: https://github.com/ggml-org/llama.cpp/blob/b29c606e28a01b1bc8c1351026a0fa6e616bf6c4/tools/server/server-stream.cpp#L597-L614
[error-code]: https://github.com/ggml-org/llama.cpp/blob/b29c606e28a01b1bc8c1351026a0fa6e616bf6c4/tools/server/server-context.cpp#L4243-L4245
[http-error]: https://github.com/ggml-org/llama.cpp/blob/b29c606e28a01b1bc8c1351026a0fa6e616bf6c4/tools/server/server-http.cpp#L145-L159
[httplib-error]: https://github.com/ggml-org/llama.cpp/blob/b29c606e28a01b1bc8c1351026a0fa6e616bf6c4/vendor/cpp-httplib/httplib.cpp#L8612-L8619
[auth]: https://github.com/ggml-org/llama.cpp/blob/b29c606e28a01b1bc8c1351026a0fa6e616bf6c4/tools/server/server-http.cpp#L196-L306
