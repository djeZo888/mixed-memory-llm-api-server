# H014 MiMo disabled adapter — 27 September 2026

**Offline implementation complete; candidate DISABLED, UNWIRED and UNQUALIFIED.**
Base `ac176853b784a3678ec68b33cd2229fa87b51053`; branch `worker2/h014-mimo-adapter`.
Native Worker2 session `01a0e1b0-0b4e-7962-af5b-470f9fca1774`.
Wrapper start `2026-09-27T07:06:45Z`; hard deadline `2026-09-27T07:31:45.896641+00:00`.
Post-commit source SHA, bundle SHA256 and final status are in task `../DELIVERY.json`
and `../HANDOFF.md`, avoiding recursive commit/bundle hashes.

## Changed files and behavior

- `ai-harness/server/src/mimo.ts`: specific typed protocol adapter; no listener,
  URL, credentials, model selection, registry import, queue or automatic retry.
- `ai-harness/config/mimo-candidate.json`: disabled review candidate, all thirteen
  exact shard pins and runtime pin, null live context/output ceiling/loaded hashes.
  Port 30012 is only a proposal; no ownership/freedom/live check was performed.
- `ai-harness/server/test/mimo.test.ts`: ten focused offline tests with synthetic
  receipts, intercepted native count transport and chunked SSE fixtures.
- This report directory: validation, status and test output.

Closed request grammar requires the exact alias and a positive explicit output
reservation. Unknown native controls, model/URL/template overrides, media,
conflicting aliases, nonfinite/unsafe integers and malformed history fail before
transport. Developer roles and pure text arrays remain intact for pinned native
normalization; no string/array equivalence is claimed. Reasoning and matched tool
history/IDs survive without changing caller data. Tool schemas/arguments remain
bounded JSON data. Tools use auto, n=1 and no parallel calls. Thinking defaults on;
explicit off normalizes to enable_thinking=false. High/low effort, GLM
clear_thinking, nonstreaming, other tool choices and caller prefill are excluded.

A frozen serialized canonical body and SHA256 cover count and generation.
`countMimo` sends exactly POST `/v1/chat/completions/input_tokens`; strict native
integer parsing rejects extra/duplicate fields, fractional/exponent spellings,
invalid UTF-8 and oversized replies. Fresh trusted observations are compared before
and after count and again before dispatch. Only successful native count can mint
an admission, which can produce one generation descriptor. Qualified immutable
W1 evidence must provide actual slot context, output ceiling, full loaded identity,
server instance/generation and required runtime/check flags. Static config and HF
metadata are not accepted as that evidence. Admission checks P+O <= S-1 using
subtraction to avoid unsafe summation; output is never shortened.

SSE validation checks HTTP status/content type, observed alias/response ID,
fingerprint consistency when present, UTF-8 and event framing, reasoning/content
and indexed tool deltas, native finish reason, final usage-only chunk/counts,
[DONE] and HTTP drain. Empty text/reasoning fragments are valid. Tool calls are
returned only after complete drain, matched identity, known name, actual ID and
complete JSON-object arguments. A length/stop finish with tool fragments fails
closed; no partial tool call is returned for execution. Plain length finish is
preserved. Transport completion explicitly reports nativeSettled=false.

The owner-policy function maps timeout, active abort, EOF, native5xx, uncertain
cancel and protocol failure to quarantine + owner hold, with no replay/switch.
Consumer detachment and complete transport retain active ownership. It is a
fixture-tested mapping, **not installed lifecycle integration or GPU-idle proof**.
No independent MiMo queue exists. Receipt authentication, immutable evidence
storage and fresh observation production remain trusted-owner integration gates;
a caller-provided boolean or this candidate file cannot supply them.

Implementation bounds: 16 MiB request JSON, depth32/100000 JSON nodes,
4096 messages/parts, 128 tools/history calls; 16 KiB count response and 15-second
count deadline; 1 MiB SSE event and 32 MiB total stream. These are defensive
parser limits, not model token capacities. Native output int32 range is checked
separately and never advertised as a qualified output ceiling.

## Validation and preservation

Matching preinstalled H008 server dependencies were temporarily symlinked locally
(Node24.21.0, tsx4.20.6, TypeScript5.9.3, @types/node24.7.2). No installation,
bootstrap, application/image build or full unrelated suite ran. Symlink removed.

- Initial `tsx --test --test-timeout=15000 .../mimo.test.ts .../frontier-contract.test.ts`:
  11/11 PASS, including two existing GLM 1M/margin tests. GLM tests were not rerun.
- Final `ai-harness/server/node_modules/.bin/tsx --test --test-timeout=15000 ai-harness/server/test/mimo.test.ts`:
  10/10 PASS after edge-case changes; exact output in `mimo-tests.txt`.
- Final `ai-harness/server/node_modules/.bin/tsc --noEmit -p ai-harness/server/tsconfig.json`:
  PASS, source typecheck only, no emitted application build. Initial indexing
  type error was corrected before these final checks.
- Existing tracked tree compared against base: byte-identical. GLM adapter/body/
  margins, gateway/lifecycle, Qwen/default delegation, managed/custom profile
  code, registry, history handling and prepared Sova1M artifacts all untouched.
- Staged scope, whitespace, secret-pattern scan and bundle verification recorded
  in CHECKS.json and external DELIVERY.json. No push.

## Exact remaining gates / minimal next diff

1. **W1 native qualification, then root review:** settle H013; freeze verified
   native/proxy port mapping (never30011), protected file auth and private count/
   status routes; registered storage/root-disk guards; exact runtime/build and all
   weight hashes, native MXFP4/BF16/F32 metadata, converter/checkpoint lineage,
   loaded tokenizer/template/tool-template hashes and immutable generation ID.
   Observe single-slot/no-shift/no-prefill/Jinja/KV/SWA modes and actual slot/cache/
   workspace allocation. Prove reserves (7% frontier, 16GiB each Qwen, 5% Ada,
   15% host), <=85C/lower cutoff, no owned swap/OOM. Qualify warmed4K, native
   arrays/developer/special-token/count boundary, reasoning/tools and explicit
   output ceiling; then reviewed16K/64K, and review allocation before full1M.
2. **Native settlement proof:** W1 binds owned work to instance/generation and
   response identity, bounds prefill/decode cancellation and proves no outstanding
   owned native work. Socket end/free slots/DONE are insufficient. Until this is
   reviewed, no owner release or GLM/MiMo switch after active MiMo work.
3. **`server/src/gateway.ts`:** add an explicit MiMo branch within the existing
   frontier admission/lane, pin alias+generation for the request lifetime, call
   prepare/count/one-shot generation descriptor through fixed authenticated
   transport; never rewrite its canonical body after count. Feed upstream SSE
   into the validator while detached consumers still drain. Bind protocol
   failures and ambiguous transport outcomes to existing quarantine. Only a
   future qualified W1 settlement hook may release that shared owner. Do not
   apply the existing GLM transport-complete release predicate to MiMo.
4. **`server/src/frontier-ledger.ts` and `main.ts`:** minimally extend the existing
   durable record identity with selected alias, immutable evidence/request hash,
   instance generation and observed response ID; preserve recovery quarantine.
   Load verified protected evidence/observations separately from candidate JSON;
   reuse existing lazy protected credential access. No parallel provider queues.
5. **`deploy/engine/configure-profile.mjs`, `config/system-registry.json` and
   `server/src/system-registry.ts`:** only after proof, root selection and scoped
   acceptance, expose the honest qualified alias/context/output/tool flags while
   keeping GLM default and preserving managed-file migration/custom histories.
   Coordinate W1 `scripts/control/node_observation.py` actual service/model/
   instance evidence; do not reuse Flash's SGLang capacity validator.
6. Add focused shared-lane/restart/consumer-stop/no-replay/integration fixtures,
   then separately authorized independent client acceptance. Prepared Sova1M
   activation remains a separate task without rebuild. Installer remains paused.

No public research repeated; no subagents, VM/ai-harness/BMC contact or traffic,
inference, download, deployment, application/image build, UI work or push.

## Same-session root review correction

Original phase1 commit `1b9956f93e1b8813cb5664f9528d4b7babe98d66` and
`mimo-tests.txt` are preserved. The narrow follow-up requires actual string
types before message-role and stream finish-reason allowlists; singleton arrays
and other nonstrings cannot pass by coercion. One focused regression test covers
both fields; null remains a nonterminal stream marker, never a terminal reason.

Affected MiMo suite: **11/11 PASS**, command unchanged, output
`mimo-tests-phase2.txt`. Source `tsc --noEmit` **PASS** with reused matching
dependencies; temporary symlink removed. No GLM rerun, build or live contact.
All files tracked at the original base remain byte-identical.

Ordinary native MiniMax full tool-schema compatibility remains **unqualified**.
The closed adapter does not accept every possible function field (for example
`tools.function.strict`) or establish compatibility with the full production
tool roster. No speculative strict support was added. Qualifying the actual
roster/schema payloads and native behavior remains a separate integration gate.

This correction uses original native session
`01a0e1b0-0b4e-7962-af5b-470f9fca1774` and the unchanged original hard bound
`2026-09-27T07:31:45Z`. MiMo remains disabled/unwired/unqualified. Root's Sova
activation uses separately accepted old artifacts and is outside this change.
Replacement bundle includes both commits against the original base; new head
and bundle hashes are recorded in task `../DELIVERY.json`.
