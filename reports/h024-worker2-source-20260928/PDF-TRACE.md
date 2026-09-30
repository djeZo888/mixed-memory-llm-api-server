# H024 PDF retained-byte trace

Read-only offline investigation at 2026-09-28 17:00 UTC. Source baseline:
`4b631d0b44ef1c471d39129b273f1753b373298b`. No VM access, inference, deployment,
acceptance retry, shared-source edit or raw-capture copy was performed.

## Proven outcome and boundary

Both original PDF workflows remain **FAIL**. Native completion and settled
inference ownership are established; successful user-task completion is not.
Neither retained native log includes a raw upstream `finish_reason`, and the
reviewed evidence directories contain no raw Chat/Responses wire capture for
these two PDF runs. The evidence does not prove a model-versus-provider stop
cause or a source translation defect.

Evidence paths below are relative to
`/Users/agent/CodexProjects/llm-orchestration/tasks/`.

### ACCEPT05

- Native thread: `01a0e702-4a57-79b1-a21c-cbc4eb17c506`; turn:
  `01a0e702-4a72-7b70-8be4-a291797c3504`; app session:
  `a83ba652-4d3b-446e-b718-eb101c3663fb`; run:
  `1a847142-e958-4d6a-885c-b7cda7ae8f07`.
- `H021-ACCEPT05-20260928/evidence/CODEX-PDF-native.jsonl` lines 35-41 retain
  the two rejected relative `--workspace .` calls and their exact failed
  results. Lines 45/49 retain corrected extraction call/result
  `call_434e1a758e9349baa84ae86b`; lines 46/51 retain corrected render
  call/result `call_c0876425b1fe4d06accc3696`. Both corrected calls exited 0.
  Extracted text says `Supply voltage 3.3 V; current limit 250 mA`.
- Line 54, at `07:57:05.767Z`, is message
  `msg_41f52af3-6838-4005-bbe1-f37fc7facf95`: “Both operations succeeded. Let
  me visually verify the rendered page.” Line 56 reports 14,119 input and 13
  output tokens for that response. Line 57 is native `task_complete` at
  `07:57:05.770Z`, with exactly that final message.
- All eight native function calls have matching output IDs; no unresolved call
  appears in the retained native trajectory. All six native assistant message
  IDs/texts exactly match the app snapshot. Snapshot phases remain
  `unclassified`, and `finalMessageId` is null.
- `CODEX-PDF-CAUSE.json` retains final gateway request
  `49cdf774-aebf-4236-9392-6987ae0c0a9f`, settled at `07:57:05.762Z`, with
  14,119 prompt / 13 completion tokens and 1,024 reserved output tokens. This is
  accounting/settlement evidence, not the missing upstream finish reason.

### ACCEPT06

- Native thread: `01a0e728-1c83-7720-a412-73df2aea5b46`; turn:
  `01a0e728-1cb1-7272-bf12-774d0babbe30`; app session:
  `f33c4c84-8e55-4b80-a396-14b7d02e61b9`; run:
  `ee75488e-ef83-48ed-a060-1deda96e3634`.
- `H021-ACCEPT06-20260928/evidence/PDF-NATIVE.jsonl` lines 43/46 retain
  extraction call/result `call_ba0c1f04e8c04cacbf8af06e`. At
  `08:38:33.383Z` it exited 0 and returned the same numeric text. No subsequent
  render invocation is present in this run. All seven native function calls
  have matching output IDs.
- Line 49 at `08:38:53.677Z` is message
  `msg_770949ac-a71b-4b51-9ecf-24a5dc5fcc07`: “Text extracted successfully.
  Now rendering page 1.” Line 51 reports 16,120 input / 11 output tokens. Line
  52 is native `task_complete` at `08:38:53.681Z`, retaining that text.
- All four native assistant message IDs/texts exactly match the app snapshot.
  App event 93 completes the same message, event 101 marks the app run
  completed, event 103 marks done. No numeric final answer or summary PDF is
  in the snapshot. Only the extracted text artifact exists. Native phases are
  unknown; app phases are `unclassified`; `finalMessageId` is null.
- `pdf-regression/settlement-0.json` lines 115-125 retain final gateway request
  `e1b52eac-4e3e-4ac8-9cc1-3ef1278041bc`, settled at `08:38:53.672Z`, with
  16,120 prompt / 11 completion tokens and 65,536 reserved output tokens.
  Previous request `39972fdb-66af-4129-bd6c-6f647dea6fb0` settled before the
  extraction tool ran. The temporal/token-accounting match supports correlation;
  it is not captured proof that the exact output bytes were sent in the next
  Chat request.
- `pdf-regression/REVIEW.json` lines 20-31 preserves extraction PASS and render,
  summary-PDF, numeric-final-answer, page-citation FAIL. It records original
  prompt/source preservation, no rescue, and a 65,536 output ceiling. Neither
  run demonstrates output-cap exhaustion.

## Source review

References use baseline source line numbers (before H024 edits):

- `ai-harness/server/src/codex-responses.ts:195-226`: request history maintains
  call IDs, rejects duplicate/unmatched outputs and maps output bytes into Chat
  `role: tool`, `tool_call_id`. Actual PDF next-request bodies are absent, so
  this source property cannot substitute for historical transport proof.
- `codex-responses.ts:319-364`: text and tools accumulate separately; content
  after a finish is rejected; the observed upstream finish value is retained
  internally. `:369-404` requires usage plus stop/tool_calls/length, rejects
  finish/tool mismatches, and emits all retained text in the terminal output.
  `stop`/`tool_calls` maps to `response.completed`; `length` maps to
  `response.incomplete` with `max_output_tokens`. `:406-411` waits for gateway
  HTTP completion/drain before exposing canonical completion.
- The converter's terminal/text/history logic is unchanged between ACCEPT05
  source `5f95693e8c83bd40ca167b9b8fe2e1520ce51634`, ACCEPT06 deployed source
  `adb763cfd0d0e2b6174dfa28439e117f8a2a03be`, and this baseline. Intervening
  converter differences are the image catalog and namespace alias spelling.
- `ai-harness/server/src/codex-engine.ts:520-574` accepts only terminal native
  turn status, rejects incomplete native items/children, then resolves completed.
  `:647-670` reconciles streamed/final native text; `:633-644` leaves absent
  phase unknown. Exact native/app text equality above finds no UI content loss.
- `gateway.ts:54-57,1068-1073` already offers private upstream `onTrace` and
  bounded static `onError`, with callbacks isolated from transport. `:1124-1138`
  settles native HTTP ownership before `bridge.end()`; preserve that ordering.
- Pinned source archive `codex-rs/codex-api/src/sse/responses.rs:497-506` treats
  `response.incomplete` as an error; `:508-524` maps canonical completed SSE to
  `ResponseEvent::Completed`. This is source semantics, not raw historical
  proof of the PDF upstream event.

## Smallest safe follow-up

1. Optional bounded terminal diagnostic from `ResponsesStream`, carrying
   observed finish reason, generated response/message IDs, mapped terminal type,
   actual usage, output item/call IDs, and text/argument byte counts plus SHA256.
   No raw text, args, schema or fabricated reasoning in ordinary diagnostics.
   Gateway adds existing request/session/lane identity and catches callback
   errors. Include separate terminal-evidence and mapped-terminal fields so a
   failed adapter cannot look like successful completion.
2. At the trusted/private acceptance boundary, retain original Responses request
   and exact translated Chat payload (or a content-free manifest with matching
   call/output IDs and byte hashes), plus raw upstream chunks via existing
   `onTrace`. This proves tool-result-to-next-request identity. Keep all private
   bytes outside Git and never log credentials. A raw trace alone does not prove
   which tool history was submitted.
3. Offline fixture: use the retained ACCEPT06 extract call ID/output shape and
   exact last promise as source-grounded input. Mark synthesized upstream
   `stop`/`length` choices as synthetic, not recovered. Assert call/result ID and
   exact text preservation, stop→completed, length→incomplete, no generated
   render call, and no callback exception affecting drain/terminal behavior.
   Negative cases: missing finish/usage, mismatched call IDs, and tool deltas
   with stop. Existing generic cases cover much of this, but not a PDF-linked
   diagnostic manifest.
4. **No unchanged live PDF retry is justified by this trace.** If a demonstrated
   translation defect emerges, root may authorize one original-prompt/original-
   fixture acceptance after review, requiring numeric `3.3 V`, `250 mA = 0.25 A`,
   page-1 citation, successful render and independently inspected summary PDF.
   Diagnostics alone qualify evidence collection, not the PDF capability.

## Evidence digests

| File | SHA256 |
|---|---|
| ACCEPT05 `evidence/CODEX-PDF-native.jsonl` | `db2fc5e2a74f0d6f59caf2da37c5e89eae363a6922c59867fd4459a99c2cf697` |
| ACCEPT05 `evidence/CODEX-PDF-CAUSE.json` | `87e25b5198092753eb892cca6449bb187a1cbb0be76cf0b414ae7a64cc537651` |
| ACCEPT05 `evidence/matched-live/03-codex-pdf-units/snapshot.json` | `6afdca350ed2e8bc3ef9211e6a2c2598195977bcddd5ec4c8d423c06d667eaad` |
| ACCEPT06 `evidence/PDF-NATIVE.jsonl` | `48e3d583659c9bfc2fbcc53051afa793e56ade2f4b6814ee8e374d1e1633f311` |
| ACCEPT06 `evidence/pdf-regression/snapshot.json` | `598441aa45738c4d275c5f1dfe718db2ab7e5c2278470f7f7c43cdcc68923d41` |
| ACCEPT06 `evidence/pdf-regression/REVIEW.json` | `a6009199f1a26be9ee1c2d3f5b38d1f6f1c2294cdd142a05ba4efa80e6f0d91c` |
| ACCEPT06 `evidence/pdf-regression/settlement-0.json` | `63ac697aeed62febaf02587f6f9d426d172da1fb34b74e9246c80cfa3f217ec6` |

No code tests were run by this investigation. Read-only JSON parsing confirmed
native call/result pairing and exact native/app assistant text identity. This
does not qualify the workflow or recover the missing upstream wire.
