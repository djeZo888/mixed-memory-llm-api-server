# H040 E source portability closure

The four adapter test files now import B from the same repository. All three prefix readers use `new URL('./fixtures/h040-native-prefix.json', import.meta.url)` and assert the audited text length and digest before fixtures execute. No fallback or outside-repository lookup remains in the tests. Runtime adapter, B, controller/schema and root handoff/roster were not modified. Activation remains disabled; native acceptance is **NOT_TESTED**.

Source commit: `d810de4f97f056319681c7402fecb8136bbaca40`; base target: `112a4d93b001762c8b6582d995c529036257efc6`. The report successor is exported as the final candidate in `../output/RESULTS.json` and the bundle. Only four tests, one fixture and these two reports are owned.

The exact supplied JSON fixture was copied from H040 `E-native-collector/native-prefix.json`: container 504 UTF8 bytes, SHA256 `b056de35f831e736f1ddb01260d750c4559c52dc320664fa6d7aed419563d278`. Its pinned independently audited Rust constant text is 399 UTF8 bytes, SHA256 `e9b088e794a6bb9082ac053fcc760bd818d7e720ee4bcdc72c6e480de7b7cb0e`. No facts, oracle or private history are included. Container and selected text digests are distinct and both checked.

Validation in this phase:

- Strict standalone adapter compile: `./node_modules/.bin/tsc -p ../acceptance/compaction/native-adapter/tsconfig.json` from `ai-harness/server`, exit 0.
- Four changed TypeScript files: parse, transpile and `node --check` all pass. All 41 relative module/fixture inputs resolve inside this repository. Builtin/package dependencies retain the supplied node_modules symlink; no reinstall.
- Exact fixture bytes/text hashes pass. `git diff --check` exits 0.
- Actual in-repository B imports succeed, but scorer lacks `validateCollectorManifest` and controller lacks `bindReviewedEnvelope`. The combined 32 tests are **DEFERRED / NOT_TESTED**. No source fixture pass or native pass is claimed.
- First `node output/verify-portability.mjs` invocation exited 1 with MODULE_NOT_FOUND because the checker had been written to the parent output directory. The checker was moved to this task's output directory and the corrected invocation exited 0. No source test ran in the failed invocation. Exact commands, current B hashes, changed source hashes and resolved inputs are in the JSON report.

Adopted native session `01a0f4fa-aee1-7cb0-8b3d-9fa0577a26c9`, gpt-6.1-sol / ultra, mac-worker2. No new session was created. Prior owned source `866809c86277573f1f16831dc20fdeacdbf33021` and report `fb6592eb930153a1f81adf27e834951d980024a1` were integrated by root as `7798b18`/`112a4d9`. Root supplied the prior phase's native0/outer0 closure at 03:39:29 UTC. Its 32 passes cover only that original worker composition. Current phase exits remain unknown until outer receipts arrive after closure.

Retained source settings are Codex 0.158.0/upstream 064c, 480000 context, 400000 automatic compaction threshold and 65536 output. No installed runtime, model, provider, mount/egress, live native identity, production browser/UI, rollback or retrieval qualification was performed. No VM, deployment, inference, credentials read, enable flag or literal attestation was added.

Root must integrate sealed final H040 B, record the exact coherent A/E/B commit and B/controller/scorer/evidence/schema hashes, then run the 32 source fixtures and required combined compile checks once with repository-local inputs. Root then reviews that coherent candidate. Any native probe requires separate concrete review/GO and current ownership/window gates. This finite source phase closes without waiting for B; target 03:55 UTC, hard 04:03 UTC.
