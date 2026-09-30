# One count-only comparison — prepared, NOT_TESTED

No idle/readiness/source grant arrived during this task's review/preparation.
Do not delay W2 deployment for profiling. No live request was made. If the c863
baseline opportunity is lost, report the comparison NOT_TESTED; never substitute
the H032 PDF walltime or call an after-only sample a speedup.

`count-once.mjs` uses the actual running application's installed production
verifier/counter and protected credential reader. It makes one counter invocation
per explicitly granted case, with default transports and all production guards.
The script does not perform ordinary lane admission or extra readiness sweeps.
Its only POST is the counter's `/v1/tokenize`; no generation, retry or app write.

Both cases use this exact short request, including tools/output reservation:

```json
{"model":"qwen3.8-27b-gpu0","messages":[{"role":"user","content":"Reply with OK."}],"reasoning_effort":"none","tools":[],"max_tokens":64,"stream":false}
```

Body SHA256: `0abfb2b98ef4baf9e199f6227fac8a1ea436d0008b155b5d00a7ceb7e806011a`.
Counter body SHA256 after the existing stream-field removal:
`51ea587124ba8c0552c5f01e70b7aa485b5345ebca8999cab098f44dd3825254`.

Execution remains coordinator-owned, only after an explicit W2 grant in INBOX:

1. Before deployment: grant idle/readiness and exact c863 binding. Save one
   exclusive local intent and private stdout/stderr files before launch; refuse
   an existing intent, failure or uncertain attempt. No retry.
2. Invoke the source through SSH stdin on the existing `ai-harness` host as
   `node --input-type=module - <base64-binding-json>`; write no remote script.
   Use argv-safe subprocess invocation, a local timeout of 130 seconds, and
   record the actual return code before cleanup. Read INBOX immediately before
   launch and require its hash to match the binding. No raw credentials/config
   in arguments, output, report or Git. Node has a 120-second process bound and
   the counter a 90-second signal; production individual request bounds remain.
3. After W2 deploys and grants ready/idle with exact new source/build binding,
   require the first case's PASS receipt and identical body/alias/receipt.
   Save a distinct one-shot intent; run the same script once. Abort on any
   count, source, identity or freshness failure and preserve its partial stages.

Binding JSON fields: `task: "H033-REVIEW-TIMING02"`, `idleReadyGrant: true`,
`case: "before" | "after"`, `expiresUtc`, `inboxSha256`, `source`, `serverDir`,
`sourceManifestPath`, `buildReceiptPath`, `buildReceiptSha256`, `receiptSha256`,
`bodySha256`; after also requires `beforeResultSha256`. These fields document
an existing explicit grant; creating a JSON file does not grant permission.
The source-manifest/build-receipt source hashes and all five imported compiled
module hashes are checked before use; running PID, manifest, receipt and compiled
bytes are checked again afterward. Credential/receipt paths come from the actual
process environment/argv, using existing protected readers. Nothing imports or
starts the application main entrypoint.

Known retained baseline: source `c863d4984f4a75c237b6de97b7ce40b8570fca81`,
server directory `/opt/ai-harness/releases/h032-count-update-c863d4984f4a75c237b6de97b7ce40b8570fca81/ai-harness/server`,
source manifest `../H032-SOURCE-MANIFEST.json` relative to that directory,
build receipt `/home/user/.cache/h032-count-update-release/BUILD-RECEIPT.json`,
SHA256 `99ba0cf476a982e3e324c549ff9f1603fca18a2c8f87e67ddfd4b82df2adff0c`.
These are retained preparation pins, not a new live binding/readiness claim.
New installed binding must come from W2; no expected after-deploy hash is invented.

Observer output retains individual control/node/native stage counts and times.
`counterElapsedMs` is monotonic total production-counter time, including its
verification; observer `tokenize.elapsedMs` likewise includes verification and
is not isolated tokenizer compute. Report individual before/after values only;
one sample each supports no median or general performance claim. Source predicts
control/node reads 4→2 each and native checks 2→2. This is theoretical only.

Validation: `node --check` passed and independent read-only review found no
blocker. No live/runtime test or PERF01 rerun. Hard cutoff remains 15:45 UTC;
any later work requires a fresh bounded task and explicit grant, not automatic
extension of this script or session.
