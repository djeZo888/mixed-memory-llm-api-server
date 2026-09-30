# H029 ADMISSION02 — diagnostics, historical cause unresolved

This report records TypeScript commit `7f433726b12987cea96ee290d07b6f11040d1fe2`.
The later separate source-only control correction is in `CONTROL-MASKING-FIX.md`.

Exact base `6d11dc255e003337586306a0ef6a7da5e91853ec`. Native implementation
worker on mac-worker1; coordinator owns review/publication, Worker2 owns the
combined harness deployment. No GitHub push or deployment performed here.

## Exact original failure

Request `75d651ef-86cd-4760-ad04-2867c28c6982`, session `a9678198-c750-4051-9cb7-967af49f44e1`,
run `f9b6dcad-645a-456d-90c1-39e578e57521`: both lanes passed full admission.
Qwen1 took 18.908s and Qwen0 19.129s. Selected Qwen0 then failed
`count/control_before/transport` at 02:18:56.868 UTC after 9.145s. The tokenizer
summary carries the same rejection. No native tokenization, generation or tool
execution occurred. W2 proved settlement; original failures/receipts remain.
All 14 supplied safe diagnostic records are preserved without change here.

The failed predicate is the count-phase control GET availability/decode path,
before any control identity/allocation predicate can run. Retained records do
not distinguish HTTP non200, decode, size, stream or connection failure. The
getter uses 30000ms, and the verifier supplies no caller cancellation signal.
9.145s does not establish a timeout or concurrency/CAS cause. The HTTP server
explicitly retains no request/error log. Historical subtype remains UNKNOWN.

## Authorized observations

Root authorized one same-endpoint read after existing records were exhausted.
From ai-vm, `/control/v1/status/glm` returned HTTP200 in 9.245s at 02:25 UTC,
with fresh/ready/persisted current generation and no current operation.

Root then separately authorized one instrumented read-only sequence from the
actual ai-harness host: both deployed verifier lanes in parallel, then the
selected Qwen0 count verifier. It ran 02:32:08.183–02:32:45.961 UTC using the
existing deployed verifier and protected receipt/credentials, with the same
GET URLs, headers, no pooled agent, 30000ms deadline and 512KiB bound. Only the
getter seam added static HTTP/error projection. Source root was
`h029-deploy01-0d92467974923241a46585850d2bc06f0c8f4b22`; imported verifier dist
SHA256 `ee5d295aefdd147441c8bbfaec93335b2d6aa538f43797f4488b1c73259d5633`.
All 15 GETs returned 200 and all three qualifications passed. Six control reads
took 9.316–9.557s. Zero `/tokenize`, provider requests or retries. This diagnostic
PASS is not acceptance and does not explain the historical failure.

A metadata-hash lookup first failed before start emission or any HTTP call:
installed release has dist files, not source. That original ENOENT stderr is
preserved privately in task output. Correcting the hash path did not replay a
request. No further live sequence/sweep was performed.

## Narrow correction and source finding

The patch adds only safe transport diagnostics to the existing rejected-phase
event: static subtype, bounded HTTP status and exact allowlisted control code.
It preserves all guard predicates, source/receipt/native schemas, 15s freshness,
480000 capacity, deadlines, response bound, public503 message/code and ownership.
The logger independently projects these fields; remote text/body/errors/keys
are never retained. No main.ts/shared deployment edit or runtime policy change.

Source inspection plus a finite local synthetic fixture also demonstrate a
second masking mechanism: `_read` fallback loses pair shape after refresh
failure; scoped lane reads then return409 `target_unavailable`, hiding injected
`stale_state`, `lifecycle_busy` or `deadline_exceeded`. Untargeted reads retain
those codes. This is a demonstrated diagnostic defect, NOT the proved cause of
the original request. Core/adapter are unchanged. A future narrowly reviewed
correction can preserve the original failure status/code on the targeted error
path without admitting a candidate or changing CAS checks.

Competing ordinary status readers do not reconcile or persist state. Full
container inventory/mount identity remains anchored; an external lifecycle
change could invalidate it, but no correlated evidence proves that occurred.
No guard narrowing, retry, latency refactor or runtime correction is justified.

## Checks and handoff

PASS: 11 focused TypeScript tests (4 new transport fixtures), TypeScript
typecheck, independent read-only diff review, and 3 local synthetic masking
cases. Initial test-only status/statusCode and Application.handle argument
mistakes are recorded in private task output, along with original tool traces.
Only the existing pinned dependency tree was copied locally; lockfile unchanged.

Deployment requires only root/W2's reviewed harness build/release. All owner
policy/adapter/manager/core/receipt pins remain baseline. Patch is not deployed.
MiniMax stays default. The original tool gate remains FAIL; follow-up/PDF/
compaction remain NOT_TESTED. Do not use the successful read-only sequence as a
reason to retry inference without root's live schedule.

No ai-vm mutation, starts/stops, source receipt replacement, model/runtime/fan/
power/ECC change, hold/quarantine clearing or inference occurred. Three warm
Qwens and all accepted operations were left alone. Diagnostic process exited0
and owns no accepted operation. MiMo/image starts remain held; their optional
fresh read-only inventory was not performed while admission diagnosis took
priority. Native session ID is recorded by coordinator JSONL.
