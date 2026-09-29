# H035 — Codex workflow checkpoint

The two-hour September 29 window delivered and deployed useful fixes, but full
Codex integration remains incomplete. **The original PDF regression passed.
The retained image-edit workflow still stops after promising to delegate.**
MiniMax remains default, Codex remains a preview, and public chat stays in
maintenance as authorized. Status remains available. No model, inference
runtime, GPU, fan, power or context-capacity change was made in this window.

Deployed application source:
`cbaf28409a30fc3329a6ed05a9466d7db2f3d332`, activated September 29 at
20:52:39 UTC. Later commits contain documentation only. The compact
[results](h035-codex-results.json) and [worker acceptance packet](h035-acceptance/RESULT.json)
separate actual execution, retained evidence and untested behavior.

Final readback at 21:03:43 UTC confirmed chat HTTP 503, status HTTP 200 and zero
active runs, task containers, admission tickets, provider requests or image jobs.
All five native worker sessions exited successfully; the last closed at
21:05:24 UTC, before the deadline. Two historical uncertain owners and three
quarantines remain preserved. The worker result was written before its own exit;
the separate [closure receipt](h035-acceptance/COORDINATOR-CLOSURE.json) records
the actual process exit without rewriting that earlier evidence.

## Delivered changes

- An authenticated `image_status({jobId})` tool reads an existing owned job
  without resubmitting it, generating another image or granting approval.
- Image completion can create a separate, durable result message with preview
  and download links. Atomic message/event deduplication and restart
  reconciliation preserve the original assistant reply. Historical terminal
  jobs are not indiscriminately backfilled.
- Saved image-job state precedes the current request, identifies its originating
  run, and preserves the user's request and references. It does not force a tool
  call or reinterpret an explicit request to continue an existing job as a new edit.
- Tool instructions distinguish editing sizes from generation sizes. PDF
  instructions require accurate reporting of real tool errors and recovery.
- Managed skill upgrades check exact known content before migration and retain
  unknown user edits. Current instructions reach resumed parents and new children.
- Capability descriptions report the actual acceptance state. Image qualification
  remains false; frontier access stays enabled through reviewed H033 evidence.

See the [image source report](h035-image-handoff01/README.md),
[context correction](h035-image-intent02.md) and
[independent review](h035-release-review01/REPORT.md).

## Actual acceptance

| Check | Result and limit |
|---|---|
| Original PDF extraction, arithmetic and output | **PASS**: 3.3 V, 250 mA = 0.25 A, page-1 citation, saved PDF and exact final delivery |
| PDF failure reporting | **PASS**: the real out-of-workspace verification error was disclosed; a workspace retry succeeded |
| PDF visual review | **PASS**: root independently viewed the rendered one-page output; readable and unclipped |
| PDF conversation reload | **PASS**: final, uploads, per-reply files, context and readiness returned after a normal browser reload |
| Existing image status | **PASS via application API**: completed job and original artifact returned; this was not a native MCP invocation |
| First unchanged guarded-edit request | **FAIL**: promise-only final, zero calls, children, approvals or new image jobs |
| Single retest after context correction | **FAIL**: same promise-only behavior; no additional creative work occurred |
| New image result delivery after approval | **NOT_EXERCISED live**: the two requests never reached a tool; deterministic tests alone do not qualify it |
| Browser PDF/ZIP download action | **NOT_CONFIRMED**: browser automation timed out before a saved path; ZIP was not attempted. Worker HTTP PDF download/hash verification passed separately |
| Current idle deployment/restart preservation | **PASS**: histories, files and protected records retained; all current jobs settled |

The PDF output artifact is `caf59484-655b-46f9-a985-95d2fa6ea6c8`,
SHA-256 `48596563e161c1712677b1750d9f41b52e0e7a5f7b18c861a97c0e77b7a9646a`.
Provider, Responses adapter, native transcript and delivered PDF final matched
exactly. Root rendering review is separate from native vision, which is unsupported.

The image request explicitly asks for one fresh child while also retaining an
existing job identity. That existing edit already completed in H034. Both H035
requests promised a child to retrieve it, then stopped. We retained that ambiguity
and the exact request instead of substituting an easier task or another image.

The offline comparison found all 21 shared tool declarations, including
`spawn_agent`, identical to a successful H034 child request. Provider model,
tool-choice setting, reasoning setting and output allowance also matched.
Both failures originated in the provider response (`stop`, no tool calls), and
arrived unchanged through every layer. This rules out a dropped call in these
captures; it does **not** prove a unique model, instruction or history cause.
No automatic retry, forced call or silent new image submission was added.

## MiMo support

MiMo V2.6 Pro-RL is the selected frontier. The read-only 20:01:49 UTC check found
it ready with the expected native identity. Actual H033 Codex and MiniMax child
workflows executed Python tools, returned results to the parent and completed.
H035 explicitly reviewed compatibility and preserved that evidence; it did not
rerun MiMo inference. Qwen remains the ordinary coordinator/coding model.

MiMo's **950,000 configured tokens are not a qualified occupied-context result**.
The previous near-950K test failed and is not running. Its result remains in
[the original report](h022-950k-status.md). Qwen profiles stay 480K/480K/200K;
the third Ada's 200K service is not part of the two-lane Codex routing.

## Codex compaction: open source and integrated

Sova uses the open-source Codex native compaction path with local inference.
Configured automatic thresholds are **400,000 / 480,000 tokens for Qwen** and
**880,000 / 950,000 for MiMo**. A small actual native manual compaction,
four-fact recall and later same-thread tool continuation passed:
[compaction](h030-flow03-20260929/COMPACTION-RESULT.json),
[recall](h030-flow03-20260929/RECALL-RESULT.json),
[continuation](h031-flow01-20260929/COLD-RESULT.json).

Original chat history and project files remain saved; the active model uses a
summary to free context. The small summary misstated an incidental file byte
count, so the evidence does not imply lossless memory. Automatic triggering at
the near-full thresholds, MiMo-specific compaction quality and web compaction
progress remain untested. Local compaction does not require paid OpenAI
inference and does not promise the same summary quality as hosted OpenAI models.

## Verification, time and remaining work

Both workers used bounded native CLI sessions; root reviewed source, images,
browser behavior and evidence. Focused backend/MCP/UI, migration, compatibility
and context tests passed along with builds/typechecks. Test groups overlap and
are not summed. Three pre-existing image-job test expectations remained stale;
their failures are retained, so this is not an all-tests-pass claim.

The PDF workflow took about 13 minutes. Each unsuccessful image turn settled in
under a minute. Most other elapsed time went to parallel implementation, exact
source/skill deployment checks and tracing the failed request across layers.
We stopped further speculative retries after the bounded retest failed.

The next bounded task should isolate the promise-only image behavior and then
exercise real late result delivery. Do not repeat the already passed coding,
research, PDF, frontier or GPU benchmarks. See [the remaining plan](h035-next-execution.md).
Native visual/audio/video input, Ada routing, occupied 950K qualification and
near-full compaction acceptance remain separate work.
