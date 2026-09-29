# Codex integration — H032 checkpoint

Execution window: September 29, 2026, 11:17–13:17 UTC
(13:17–15:17 Europe/Ljubljana). Root coordinated and reviewed; both Mac workers
performed implementation and live checks in recorded native CLI sessions.

**Codex integration is not yet complete.** Model services were recovered and the
updated application was deployed, but specialist workflows exposed further
failures. Public chat remains in maintenance; MiniMax remains the default engine.
The original conversations, project files and historical failure records remain.

## Completed changes

- Recovered MiMo through its existing source-transition record and started the
  same runtime once. Native readiness and its configured 950,000-token capacity
  were confirmed. This is allocation/readiness evidence, not a successful
  occupied-950K benchmark.
- Reconciled the interrupted image startup, preserving the previous failure and
  native logs. Deployment exposed a file-permission defect: immutable archive
  mode `0400` had been carried into operational files that require `0600`.
  A regression using the real storage reader reproduced it. The correction and
  remaining startup completed; the image service became ready and admitting.
- Disabled Codex's unsupported native `view_image` tool in its text-only profiles.
  Preserved the existing logical model policy so retained Codex chats remain
  compatible; changed tool behavior has its own versioned policy identity.
- Corrected image qualification to distinguish the actual runtime platform
  manifest from its parent container image.
- Deployed application source `e9e4f71c53b2caade69c345aadb231f788323a3d` at
  12:19:43 UTC using the existing native image. Histories and completed handoff
  records were preserved. The deployment helper now accepts completed, idle
  handoffs while continuing to reject active or uncertain work.

Affected source suites passed: 68 MiMo checks, 124 initial image checks,
59 image permission/continuation checks and 88 Codex checks. These suites overlap;
the counts must not be added as a unique-test total. Worker reports retain the
source revisions and exact receipts.

## Actual workflow results

| Workflow | Result | Evidence and limit |
|---|---|---|
| Original PDF task | **PARTIAL** | Correct 3.3 V / 250 mA = 0.25 A answer, page-1 citation and readable one-page PDF. Final answer falsely claimed no tool failures. |
| Codex image generation | **FAIL** | Qwen supplied invalid arguments to an empty-object capability tool. Stopped and settled; zero image jobs or artifacts. |
| Image follow-up edit and image child | **NOT TESTED** | Generation did not reach the image backend. |
| Codex MiMo child | **FAIL** | Real native child created; gateway rejected the token-count response before generation. |
| MiniMax MiMo delegation | **FAIL** | Real delegated child reached the same count-response failure. |
| Native ownership after these tests | **PASS** | Both parent sessions idle, child requests settled, no new quarantine; all acceptance tickets removed. |

The original failed runs remain failed even if a later regression passes.
Parent arithmetic text is not evidence that a MiMo child performed the task.
Specialist capability gates remain closed until actual complete workflows pass.

### PDF: useful output, incorrect failure reporting, excessive latency

Run `b950d17e-d3f2-45a0-bf06-adf8cab7e6f4` completed in **812.436 seconds**
(13 minutes 32 seconds), measured from durable timestamps. Earlier 12:35 UTC
completion observations were collection time; actual completion was 12:34:30.603.
The summary PDF was 30,612 bytes, one page, visually reviewed by root and Worker2.
Its checksum is `fae46bd0467b4214f10c66c9725b3ed91c9f39346936c7bb2f98d1d64286dd35`.

The final answer was identical across the model response, Responses translation,
native Codex and Sova. It incorrectly said there were no tool failures despite
a PDF command missing its required output argument and a search returning exit 1.
The unsupported image-viewing declaration was absent, confirming that the new
profile was actually used. No second PDF attempt was made.

Existing timing records for 13 inference requests show:

| Recorded interval | Total |
|---|---:|
| Lane admission, accounting for overlapping checks | 255.292 s |
| Token-count wrapper, including before/after verification | 482.943 s |
| After count until request settlement | 69.205 s |
| Native tool call to tool output | 3.539 s |

These are wrapper timings, not isolated tokenizer, prefill or decode speeds.
Queue waiting and native prefill/decode were not separately measured. The repeated
admission/verification path is the main latency investigation to finish; no
additional live profiling or PDF rerun was used to obtain these figures.

Retained lower-level timings identify the control-status HTTP requests as the
dominant measured stage: 104 requests, with median durations of 9.7035 seconds
during admission and 9.2595 seconds around counting. Fresh node checks had a
2 ms median and direct native server-info checks a 5 ms median. The selected
count path performs four complete control observations, in addition to four
across the two candidate lanes during admission. A scoped control request still
observes both slots sequentially before returning its projection. Costs inside
that control handler were not separately recorded, so Docker, storage or native
readiness probes cannot yet be ranked. A proposed parallel pair-observation
optimization remains unimplemented and has no measured speedup.

### Image: invalid arguments originated in the model

Run `ca5c50aa-3dae-4ab9-9ab7-b9e1c5c83aae` first tried an unknown MCP resource
server, then called `image_capabilities` with `references: "[]"`, followed by
`skill: "sova-local-tools"`. Its schema requires an empty object and disallows
additional properties. The declaration reached the provider correctly; raw
arguments were unchanged through Responses and semantically unchanged at MCP.
This establishes model/tool-use failure, not an adapter dropping or changing
arguments. Stop was accepted once; settlement completed at 12:42:35 UTC.
There was no image backend job to cancel and no generated artifact.

### MiMo: token-count compatibility

The Codex child and MiniMax child both failed with `mimo_count_malformed` before
MiMo generation. Requested model and medium effort were recorded. Actual MiMo
thinking behavior, shell execution and tool-result continuation remain unproven
by these cases.

One count-only diagnostic at 12:57:25 returned HTTP 200 with 55 bytes:
`{"input_tokens":11684,"object":"response.input_tokens"}`. The pinned native
implementation permits this metadata tag; the Sova parser incorrectly required
exactly one field. This reproduces the compatibility failure without generation.
The native slot remained idle and its proxy had zero active requests afterward.
A narrow parser correction accepts the known tag in either JSON field order
while preserving rejection of duplicate fields, unexpected fields, invalid
numbers and oversized responses. Its final test/deployment disposition is
recorded in the accompanying machine-readable results. All 31 focused tests
passed. Worker2 deployed the correction at 13:05:32 UTC as application source
`c863d4984f4a75c237b6de97b7ce40b8570fca81`; only compiled `mimo.js` changed.
Application health passed and existing rows, files, holds and status service were
preserved. No corrected delegation was submitted before the final cutoff;
**post-fix generation and tool continuation are NOT TESTED**. Deployment/readback
alone does not qualify a delegated generation.

Compact worker evidence: [app and workflow results](h032-deploy-flow02-20260929/REPORT.md),
[original frontier failures](h032-frontier-flow02-20260929/REPORT.md), and
[count repair and regression](h032-count-fix03-20260929/REPORT.md).

The Codex parent also exposed a final-display classification gap: native
`task_complete` carried its final answer and the app retained the text, but the
message phase was unclassified and `run.finalMessageId` was null. No missing-text
or invented-reasoning claim is made.

## Scope and retained state

Three Qwen model processes and their configurations were preserved. No model
download, runtime upgrade, GPU benchmark, 950K retry, GPU/fan/ECC/power change,
GLM restoration or main-branch merge was performed. Historical two uncertain
owners and three quarantines were not cleared. Credentials and bulky raw traces
remain private; compact results and reviewed code are published on the feature
branch and draft PR 10.

Reuse earlier coding, retained follow-up, submission deduplication, small manual
compaction/recall, cross-engine handoff and scoped Stop/reconnect evidence where
contracts have not changed. Those earlier passes do not establish the unpassed
specialist, remaining restart/queue/fallback or final display cases.
