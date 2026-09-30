# H036 finite acceptance preparation

Source/fixtures only. Nothing in this packet grants deployment, a model request,
count/tokenize request, a ticket or a VM operation. Root grants the later session
after image repair. Worker2 then owns app deployment/admission; Worker1 owns native
MiMo allocation. MiniMax stays the frontend default. Preserve all original records,
the two historical uncertain owners and three quarantines.

## Prepared changes and activation boundary

The harness MiMo successor is 480000 context / 400000 auto-compaction / 65536 max
output. Qwen stays 480000 / 400000 / 65536. These are configured limits, not occupied
context evidence. Managed profile migration recognizes 480000 while retaining every
older exact managed tuple; unknown user edits still reject. Native allocation,
protected profile proof, configured limits and occupied-context evidence are four
separate claims. No native runtime/profile/GPU/weights change occurs here.

The checked-in active-frontier.json and mimo-candidate.json remain historical,
disabled templates. Do not deploy those templates over the actual MiMo selection.
Use the existing protected /etc/sova-qualification/mimo.json mechanism only after
fresh 480K native identity/allocation/reserves evidence. Bind its exact file SHA in
active-frontier selection, context480000 and output65536. Current owner validation,
source/model/template/tokenizer/hardware checks, single owner, serial completion,
max output and tokenizer admission stay mandatory. Update the managed MiniMax
frontier profile from that selection. No GLM restoration or alternate fallback.

Changing the provider profile changes CODEX_SPECIALIST_PINS. The unchanged H035
protected specialist record and an outer-only repin reject. Preserve all H033/H034/
H035 receipt bytes. Old 950K results cannot be renamed 480K. The existing schema1
fresh-evidence shape is supplied as a disabled successor template; actual workflow
run IDs/transcript/settlement hashes and final combined pins are required later.
Historical schema2 compatibility is confined to its explicitly reviewed source and
pin agreement; a new profile is not an implicit review. Do not invent a broad new
qualification format to keep a stale gate open. Image qualification remains separate.

Required later activation pins: combined reviewed app commit and bundle SHA;
exact built app/source manifest; Codex binary/version/runtime image and host tool
policy; both runtime Codex model catalog capacity fields; pinned Qwen source/owner
policy (unchanged); native MiMo480K allocation/current generation + runtime/model/
tokenizer/template identities; new protected native receipt SHA; active selection
and candidate/profile bytes; actual specialist evidence and protected record SHA.
Readiness/smoke prove allocation and short behavior, never occupied480K correctness.

## Normal input transport

Messages alone accept at most2,000,000 UTF-16 code units and8MiB JSON. Other routes
keep1MiB; uploads keep existing50MiB/file and file/count protections. Browser pending
submissions use the same limits and fail before HTTP if persistence/quota fails.
No automatic resend on reload/SSE reconnect. Exact token admission remains decisive:
transport capacity is not token capacity. A very escape-heavy JSON payload can hit
8MiB before2M characters. Actual browser quota/large Markdown rendering remain a
later UI check; local store/route fixtures are not a browser acceptance claim.

## One automatic Qwen compaction case

Pinned source064c6b8c737f5b41d171fdda80bd9ef10ad06eb3, retained locally, establishes:

- protocol/config_types.rs: default AutoCompactTokenLimitScope is Total.
- core/src/session/context_window.rs: compare active context >= configured limit;
  protocol/openai_models.rs additionally clamps the configured limit to90% of the
  model window. min(400000,432000)=400000. No reserved-output addition here.
- core/src/context_manager/history.rs get_total_token_usage uses last reported actual
  input+actual output plus estimated appended history (and uncounted reasoning where
  applicable). It is not the lifetime cumulative sum or input+reserved65536.
- core/src/session/turn.rs: pre-turn compaction checks exhausted budget. Mid-turn
  compaction also requires a pending/model follow-up. Post-turn threshold defaults0
  (disabled). Thus a short final after a large first turn may compact only when the
  next normal user turn arrives. Do not press Compact or send thread/compact/start.
- core/src/compact.rs: automatic path sets trigger=auto, reason=context_limit;
  emits contextCompaction started/completed. Original rollout stays append-only.
  ContextWindowExceeded may trim oldest history and retry even with transport retry0:
  that is a failed planned case, not success via silent trimming.
- core/src/responses_metadata.rs: original pre-normalization client_metadata carries
  JSON in x-codex-turn-metadata with request_kind=compaction and compaction fields.
  Capture that before adapter normalization; generic contextCompaction alone cannot
  distinguish manual from automatic. Analytics disabled is not a reason to enable it.

Budget: target405000–410000 **actual complete input tokens**, including instructions,
tools, history, template and current user message. With65536 reserved output this is
470536–475536 total, leaving4464–9464 tokens before480000. Hard admission ceiling is
414464 for Qwen; MiMo separately uses414463 because its native rule is P+O<=S-1.
Compaction request must separately fit the same reserve; its tools list is empty but
summary prompt/history overhead must be counted, never guessed away. Do not lower
output reserve or400K trigger. Request a terse READY and recall answer; production
max remains65536, actual outputs should be small.

The generator emits400361-byte compact ASCII numeric data at default200000 items,
with four distinct facts spread from start to final quarter. **Item count and byte
count are not token count.** Default corpus is unmeasured. It is only a plausible
starting size; use --numbers after real tokenizer measurement in the later grant.
Do not upload the corpus and merely read a truncated excerpt: paste its entire exact
bytes through the ordinary composer. Keep the local original file and SHA private.

Later finite execution procedure:

1. Root pins one session/thread/lane, source/profile/corpus hash, output65536,
   threshold400000, native count permissions, stop deadline and admission owner.
   Existing H035 owned-acceptance/collection/settlement helpers may be reused; create
   no private history injection, alternative engine or direct generation bypass.
2. At most3 native **count-only** measurements, no inference, may tune one candidate
   against the full prospective normal request, including the actual instruction/tool
   envelope. Retained small request captures can prepare the envelope, but the final
   gateway count of the real dispatched request is authoritative. Keep count bodies,
   count responses and hashes; stop if full-envelope measurement is unavailable.
3. Start fresh Codex/Qwen chat C; paste the candidate normally. Save exact user text,
   submissionId and actual native threadId. Require the actual request count in the
   target band, full count/generation byte agreement and <=65536 output reservation.
   One large initial inference only, reply READY. If count is out of band, rejected,
   output grows unexpectedly, or tools/children appear, stop; no larger second prefill.
4. Preserve a native rollout prefix/hash and session snapshot. Send one same-chat
   follow-up: 'Without rereading the original corpus or an uploaded file, recall the
   four labelled project facts. Use Python to compute power in watts from the recalled
   supply/current and save artifacts/retained-power.txt. Return the facts and path in
   at most120 words. If any fact is unavailable, say so rather than guessing.'
5. Require AUTO/context_limit metadata on the native compaction request, canonical
   started/completed events in this thread, lower active usage, all four facts correct
   after compaction, and a subsequent successful Python/tool artifact0.825 W.
   No oracle in the active request/workspace; no original-file reread for recall.
   Summary quality is tested by facts/continuation, not a claim of lossless memory.
6. Normal browser shows progress and then restored history after reload/reconnect;
   no duplicate user submission or result. Verify original file hashes and native
   rollout prefix, and exact original user text in persisted history. UI lifecycle
   and actual AUTO metadata are separate evidence. inspect-compaction.py emits
   review facts from these files; it never awards a PASS.

Bounded dispatch budget: one initial large inference, one necessary compaction
inference (the second unavoidable long-history prefill), at most3 short post-summary
provider completions for recall/tool/final, no children. At most5 provider requests
in this case, excluding at most3 explicit count-only probes and ordinary per-request
admission counts. Total actual completion output target<4096 (initial<=64); retain
production65536 limit. Root should choose a60-minute case wall budget, no new turn
in the last10minutes and a separate10-minute settlement reserve before wrapper exit.
This is a proposed bound, not authorization or a performance guarantee. If budget
cannot accommodate the actual service, mark NOT_RUN rather than start unbounded work.

Stop immediately on admission/identity/hardware mismatch, missing/corrupt count,
uncertain owner, a second compaction, context trimming/retry, manual compaction,
unexpected creative/delegated work, or output/request/time budget exhaustion. Use
normal Stop once; revoke the owned grant through existing controls and wait for
actual physical settlement. A UI cancelled/terminal state is insufficient. Collect
actual active runs/native containers/tickets/provider requests/image jobs, preserve
historical uncertainty separately, and have the wrapper record Popen.wait rc. Never
kill a shared model or release an uncertain owner to make this case appear settled.

Failure packet: exact original prompts/files and SHA256, session/run/thread/request
IDs; pre-normalization native request + metadata; canonical count/generation bodies;
count/usage/admission diagnostics; provider/native/app terminal bytes and real tool
errors; AUTO start/end or its absence; summary/recall/tool artifact; original/before/
after history hashes; elapsed time/Stop/settlement receipts. Preserve initial failure
if a later separately authorized recovery passes. No fixture result becomes live proof.

## Three normal fresh chats, finite follow-ups

No exhaustive engine/model/attachment cross product. Image acceptance remains W1's
separate owned existing-case workflow. New chats begin only after root's grant.

| Chat | Initial normal task | Same-chat follow-up | Evidence and limits |
|---|---|---|---|
| A: Codex Qwen | Upload power.py + source-data.json. Correct mA-to-A bug in a new copy; run assertions for3.3V/250mA and zero current; preserve uploads. | Deliberately ask one MiMo480K child to independently verify with Python, return result to parent, and close. | Reuses passed H021 coding/H033 frontier workflow shape; one short480K child/tool/parent proof, not480K occupied proof. MiniMax child workflow may be reused only with an explicit root compatibility decision; otherwise existing schema1 requires its fresh bounded proof too. |
| B: default MiniMax/Qwen | Upload exact retained source.pdf and source-data.json; extract voltage/current, cite page1, compute watts and return a concise answer. Do not rerun the whole passed PDF creation/recovery regression. | Upload scan.png and scene.png normally. Ask OCR transcription of scan.png with method named, then describe shapes/colors/relative placement in scene.png using actual image pixels if supported, otherwise report limitation. | Original PDF SHA matches H035. OCR is text extraction. Pixel recognition requires real image blocks reaching Qwen plus an answer against private oracle; filename/metadata/text or generated-image success is insufficient. Neutral filenames; do not upload generator/oracle. |
| C: Codex Qwen | The measured exact compaction paste above; short READY. | Recall plus useful Python artifact in the same native thread. |400K production AUTO event, lower context, preserved history, recall and continuation; no manual Compact substitution. |

Fresh data fixture intentionally shares H0353.3V/250mA oracle. Existing passed Python/
C++/Node coding, research/frontier and PDF failure/recovery evidence remain referenced;
this small new task extends fresh-chat/follow-up coverage only. Fixtures are original
local deterministic assets, not image generation or paid-model output. Source PDF is
byte-identical retained H032/H035 fixture, regenerated from its embedded exact bytes.

## Existing visual capability truth

Codex: both catalog models have input_modalities=[text]; view_image=false in both
runtime profiles/requirements. codexInput rejects image/audio/video attachments as
native media; special image references are opaque specialist-edit references. The
Responses adapter permits only input_text/output_text content and rejects media and
image tool output. MiMo identity requires multimodal=false and native modalities
vision/video/audio=false; frontier profile input is text only. No pixel route exists
through this Codex adapter. PDF extraction/rendering does not change that fact.

MiniMax main Qwen: engine sends upload workspace paths as text. Its pinned native
read tool detects image files and emits base64 ImageContent; the pinned completion
adapter re-emits image tool blocks as image_url data URIs when model.input includes
image. configure-profile.mjs advertises text+image/support_image for main Qwen.
Qwen model revision017b9c7af6b5689d5dd426a76e0bc077eb5ca20a and template
c3cf9e34abf4f9e36c2d72165aa9c132d3e2a725b6c2586aaa3a8af9d7a81041 are pinned;
manifest pins preprocessor_config.json SHA27225450ac9c6529872ee1924fcb0962ff5634834f817040f444118116f4e516.
Retained H035 global visionAvailable=true is a configured path, not new visual
acceptance. Existing MiniMax upload/read/Qwen is the smallest source-supported
candidate: capture image bytes/pixel processing at its normal provider boundary and
count/admission before calling it tested. Do not infer processor loading solely from
manifest presence. Current native processor behavior was not inventoried in this task.

OCR is already available via local Tesseract in the engine tools/runtime inventory.
For PNG, ordinary native shell can call installed tesseract; PDF helper OCR expects
PDF pages. A transcription proves OCR only. No need to enable Codex vision to do
ordinary document extraction. True Codex vision would require a separately reviewed
native image input/tool path, byte/pixel limits, provider translation and image-aware
native count/admission with exact model/processor/template qualification. A catalog
flag alone is unsafe and is not proposed here; no model/image rebuild is authorized.

## Browser reuse and release matrix

Use the existing H035 completed PDF artifact caf59484-655b-46f9-a985-95d2fa6ea6c8,
SHA48596563e161c1712677b1750d9f41b52e0e7a5f7b18c861a97c0e77b7a9646a. Root opens
its saved chat normally, clicks PDF Download once, records browser download event/
path and hashes actual saved bytes. Open the file locally. Click an existing message
ZIP containing at least2files, retain its download event/path, inspect members and
hash each against the unchanged uploaded/artifact files. If no existing multi-file
message is available, ChatA's normal2uploads provide it; no new inference is needed.
Reload/reconnect once, confirm messages, files, approvals/results, context and status;
verify no automatic resubmission. A direct HTTP download/hash is separate from a
browser download action. Retain H035 timeout as NOT_CONFIRMED until this actually passes.

| Gate | Retained evidence | H036 missing work / owner |
|---|---|---|
| PDF extraction/calculation/output and honest recovery | H035 PASS incl root visual review/reload; H032 false no-errors claim remains failed | Reuse, no full regression rerun |
| Coding/research, frontier short workflows | H021/H033/H035 retained passes | Root determines exact unchanged-path reuse;480K actual smoke/protected successor after W1 allocation |
| Image correction + real approval/result handoff | H035 twice promise-only failures; previous generation/child successes retained | W1 actual correction/handoff; no forced retry or changing old test |
| MiMo480K configured/native/profile proof | This packet source only; old950K readiness/9635 occupied observations remain historical | W1 allocation; W2 later activation/readiness + bounded normal smoke; root evidence review |
| Qwen400K AUTO compaction/recall/tools | H030 small manual compaction/recall and H031 cold continuation passed | One bounded actual case above; active/current threshold unchanged |
| Fresh chats/follow-ups/doc/visual truth | Local fixtures only | Three chats above, report supported/OCR/unsupported separately |
| Browser PDF/ZIP/reconnect | H035 UI reload PASS, PDF click unconfirmed, ZIP unattempted | Root actual UI actions with saved paths/member hashes |
| Settlement/preservation | H0350current +2uncertain owners/3quarantines retained | Later readback without erasing historical uncertainty; actual native exit receipt |
| Required repository checks | Focused source tests are local; CI diagnostics separate | Root owns required Linux checks/dependency stack/defaultmain decision |

Do not remove maintenance or merge while a required material gate remains blocked.
Root owns GitHub/default-branch/dependency audit and final publication; this task
commits/exports source only and does not push. Full image/native-media/480K occupied
qualification must not be claimed from this preparation packet.
