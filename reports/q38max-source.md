# Q38MAX — one source-only maximum-context candidate

Exact base `636f847fa2729238db9974c0a7b570960e6974d5`, isolated mac-worker2
branch `milestone/q38max-tp2-bf16kv`. No ai-vm, Docker, lifecycle, model download,
frontend or installer operation. No publication or integration by this worker.

The sole added deployment is `qwen38-27b-1000000-yarn4-tp2-bf16kv`: same checkpoint,
model identity, alias and runtime, TP2 GPU0+1, BF16 compute/KV, exactly 1,000,000
context and max-total-tokens, official factor4 YaRN JSON and the one approved
extension environment variable. Profile pins and finite launcher checks reject
partial tuples, arbitrary JSON/environment and FP8 KV. All other tuning remains
native: one request/state slot, 2048 prefill chunks, 0.80 static fraction,
FlashInfer/CUTLASS/Triton, FP32 recurrent state, disabled graphs/radix/overlap and
no speculation. Existing singleton leases, storage, authentication and core1:1
creation/reuse remain in place.

Native128K/256K profile files, model/runtime declarations and public selection
remain byte-identical. Native backend argv/cache environment snapshots remain
fixed. The shared raw/resolved check now rejects changes to only the eight
variant-defining fields; legitimate unrelated native normalization is preserved.
This refusal tightening is not evidence of the historical startup failure cause.

The fixture defaults to the native pair. An explicit extension selector invokes
the same no-GPU lifetime/auth/cleanup/diagnostic paths, with genuine installed
`ModelConfig.from_server_args()` and exact checkpoint metadata. Its receipt binds
profile/config/argv/environment and all launcher/fixture/installed source hashes,
and checks the resolved context and complete YaRN object. Manager first requires
fresh native proof, then a separate extension receipt; native proof alone cannot
accept extension. Q38FIN pre-import environment isolation remains. The new public
config fixture is added to existing control source-closure metadata only.

Root's Worker1 Q38MODE observation (04:10:46 UTC) confirmed exactly one of39
resolved disabled-field violations: `grpc_worker_threads` remains raw `None` and
resolves to exact integer4; the other38 pass. The source guard now distinguishes
that pinned default from an enabled gRPC mode/port or unreviewed thread value.
This observation produced no authentication receipt. Shared native validation
therefore changes narrowly; source argv/environment declarations do not.

The final composed run passed **168 focused tests** once (nine source suites).
Coverage includes closed tuple/refusals, native snapshots, Manager create/reuse,
source-method ModelConfig resolution, receipt identity/drift, owned cleanup,
Q38FIN isolation, diagnostics and the confirmed native default regression.
Command/log: `../focused-command.txt`, `../final-focused-tests.txt`. No broad,
archive/import or installer suites were run. Mechanical source verification is
recorded in `../final-source-integrity.json`.
Historical failures and NOT_TESTED statuses remain intact. Source tests use
synthetic collaborators; they do not mint installed-image acceptance. Actual
capacity, peak allocation, communication behavior, quality, prompt/decode speed,
occupied context, real generation/tools and native lifespan remain unproven.
Worker1 owns fresh exact-source native proof, then separately authorized extension
live gates. No automatic follow-up or deployment.
