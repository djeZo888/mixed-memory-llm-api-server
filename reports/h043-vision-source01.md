# H043 VISION source01 factual results

Implemented a disabled durable technical-vision HTTP service, actual bounded
Qwen/Paddle backend, and trusted owner-facing host interface. This phase remained
source-only in the root-approved isolated checkout. Base `4f1a060ae4cc682244d1be40c4c5f5fd2919a7fa`; source commit
`fef5a2459b5b98c96d683e64c3abc859a4a7a138`. The separate report commit/final HEAD and package hashes are recorded
in `output/RESULTS.json`, avoiding a self-referential commit hash in Git.

The service implements all five H039 v1 routes with private bearer auth, strict
multipart bytes and normalized PNG validation. Private 0700/0600 no-follow,
single-link FD guards and an exclusive writer lock protect frozen bytes/results.
Atomic owner/session/workspace/run/request admission uses canonical content plus
image hashes; duplicates return the original job, changed manifest/question/bytes
conflict. Lookup and clean reopen require no original source paths or inference.
Unfinished restart records preserve original ownership/identity and become
interrupted/unsettled; no replay. Queue/concurrency are 4/1, history 128, storage
256 MiB, metadata/public JSON 1 MiB, total admission body 51 MiB, PNG transport
50 MiB. Execution profile narrows H039 transport to one page / 2,097,152 pixels /
edge 4096 / eight crops / one image per sequential inference.

The concrete backend calls only trusted loopback 18191/18192, authenticates via
host role callbacks and pins both exact revisions. It never starts a runtime,
reads model/source paths, accepts document URLs/argv, follows redirects or retries.
Qwen strict JSON supplies description, uncertainties and separate conclusions.
Paddle raw OCR text retains literal spaces/newlines/units. Protected response
history retains raw genuine HTTP responses, their hashes and source/page/crop
hashes/regions/revisions. Synthetic responses appear only in explicitly named
fake local HTTP fixtures. Known input regions are provenance, not fabricated
text boxes. No OCR-to-component/net graph is invented; electrical nets remain
`not_qualified`.

Explicit owned cancellation of queued work settles immediately. Running Stop
stays cancelling until service-owned calls drain; late results are discarded.
Unknown dispatch or cancellation remains unsettled and blocks further inference.
Ending HTTP/tool observation never cancels an admitted job. Header/body watchdogs
bound total HTTP time, including periodic drips, with a retained actual backend
socket even after Connection:close. Store/worker failures close admission and
retain the last durable unsettled state rather than forging a terminal outcome.
There is no native engine stop/reset implementation or claimed shutdown proof.

Host exports are `createTechnicalVisionHost`, `constructTechnicalVisionHost`,
`PrivateTechnicalVisionHostJournal` and the journal port, with `invoke`, `status`,
`lookup`, `cancel`, `deliverTerminal`. Availability defaults disabled. Claims bind
original run ownership before source read/dispatch; ambiguous/repeated calls only
lookup. Follow-up authorization uses the retained creator, not a later current
run. One immutable terminal outbox event is durable; normal host exactly-once
visible delivery requires `deliverOnce` to atomically deduplicate its stable event
ID in the existing event/database transaction. A lost sink acknowledgement can
offer that same event again; no impossible exactly-once network claim is made.
The exclusive host crash lock requires owned reconciliation before takeover.

Final checks: **26 Python tests and 33 focused TS tests passed**, typecheck and
build exited **0**. The integrated fixture uses real Python service + concrete
backend + fake local model HTTP + existing TS client + trusted host and verifies
literal OCR and byte-exact frozen PNGs. It is not a prediction-accuracy test.
Original argv/cwd/UTC start-end/integer exit and matching original logs are in
`output/logs`; checks and SHA256s are in the JSON companion. Tests used only the
approved `/private/tmp/h043-v01-cznp0ry2` (UID502,0700) per command; observed tsx
socket path is 49 bytes. No global HOME/CODEX_HOME/temp/dependency change.

Preserved failures: receipt wrapper consumed `--test` as executable (no test
child ran), first service circular-reference validation assertion, and later
injected checkpoint failure not latching faulted immediately. Original files were
retained separately; fixes passed subsequent checks. The checkpoint failure run
also preserves BrokenPipe header diagnostics now handled at the response boundary.
Early read/glob/PIL exploration and pinned Paddle README research failures remain
explicitly recorded; early exploratory full-output/timestamps were not captured
to disk and are not represented as complete command receipts. Optional export
metadata `KeyError: log` was corrected without source/test changes. Prior H042
UDS path-limit failures and old candidate/history are preserved.

Root source feedback SHA `a96e955c44e9e76813326df5d9e2a5d357631d1c0628e5f8aa8909aca54c129e` was received
and handled within the original 13-file allowlist. Exact boundary tests, slow
header/body tests, admission/running/checkpoint/final/cap failure tests, worker
failure tests and the disabled fixed-private-ingress proposal cover its four
items. Original feedback bytes are exported. This was no live GO.

`configs/vision/h043-candidate.json` keeps stable Ada
GPU-14c23cbc-12f0-9c61-0fda-7aaf80fbd1bf, exact artifact revisions/paths, loopback
ports, 16K Qwen / 8K OCR / output4096 / concurrency1. `runtime_plan.py` prints
exact proposed argv/private mounts/network/source/model/service/route/readiness,
VRAM telemetry and owned shutdown/rollback graph; execute is always false.
Private key injection is a reviewed future FD-to-VLLM_API_KEY supervisor boundary,
not an invented CLI option or printed secret. Full-device budget must include
weights, KV/recurrent cache, vision activations, allocator/runtime and peak fit.
Nominal .72+.18 fractions prove no fit; >=3440 MiB/7% free and any sequential
residency alternative require measured qualification and a reviewed lifecycle.

The real TS client requires `10.156.100.60:PORT`; loopback fixture success does
not implement remote host integration. The disabled proposal binds a fixed
private ingress 10.156.100.60:18193 and forwards only the authenticated v1 routes
to loopback, with exact multipart preservation, body/deadline limits, fixed host
allowlist, no general proxy and no Authorization/payload logging. Shared
main/gateway/policy/provider/catalog/runtime/artifact files are untouched. Their
precise next-phase construction/registration proposal is in the owned docs.

Missing live gates: exact candidate image architecture/kernel/processor/template/
API/auth correspondence; model alias-to-artifact/native owner binding; current GPU
placement/VRAM/USB4 stability; private ingress; normal authenticated host/MCP
wiring and transactional event sink; exact owned ambiguous engine settlement;
native PDF and technical accuracy/crop reconciliation. Source fsync/rename and
injected failures do not qualify Linux power-loss/noncooperative syscall behavior.
No Linux contact, model work, fan/thermal/lifecycle change or new paid delegate
occurred; existing owners, credentials, runtime pins and histories stay preserved.

Official read-only references and failed research opens are exported in
`output/official-source-references.json`. The
[pinned Qwen card](https://huggingface.co/Qwen/Qwen3.5-9B/blob/c202236235762e1c871ad0ccb60c8ee5ba337b9a/README.md),
[official Paddle tutorial](https://github.com/PaddlePaddle/PaddleOCR/blob/main/docs/version3.x/pipeline_usage/PaddleOCR-VL.en.md),
[vLLM architecture docs](https://docs.vllm.ai/en/latest/models/supported_models/)
and [pinned vLLM key environment source](https://github.com/vllm-project/vllm/blob/8bc31bd21075c5ca8a070e6da84e96e2eaf816ad/vllm/envs.py)
support the source plan; they do not attest compatibility of the candidate digest.
