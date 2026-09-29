# H036 IMAGE-FLOW02 — FAIL, settled

The exact fresh prompt ran once against production source `cbaf28409a30fc3329a6ed05a9466d7db2f3d332`. It performed three preparatory tools, then ended with a promise to spawn a child. There was **no child, image-edit call, approval card, image job, or output image**. The approved retrieval follow-up was **NOT_RUN** because no completed job existed. No retry or rescue prompt was sent. Both earlier H035 promise-only failures remain FAIL.

## Actual boundary

The parent received `image_edit` and `spawn_agent` declarations in all three normalized requests. `image_capabilities({"query":"capabilities"})` returned ready=true, admitting=true and supported one-reference edit profiles 1536x864 and 1024x1024. It did not say editing was unavailable. The other tools read the current local skill and returned the uploaded PNG's dimensions `(1920, 1080) RGB`; both command calls exited 0. Only the parent catalog was observed.

The final provider response used finish_reason=`stop`, with no tool call. Its exact text matches the Responses stream, native task_complete, and app final:

> The reference is 1920x1080, but the supported edit canvases are only 1536x864 and 1024x1024 — so the canvas must change (nearest match, same aspect: 1536x864). I'll spawn one fresh child to submit the edit; the size change will require an approval card.

This is a model stop after preparatory tools, not a missing translation of a spawn call. It is distinct from a zero-tools failure. The evidence does not establish why the model stopped.

## Identity and closure

- Operator native session: `01a0ef1a-cd1f-7f00-b7be-69801f27ae0c`.
- Fresh app session: `a07fa515-21ae-447a-86a6-e279a02c716f`; run: `a8f6cb7f-a1e9-44db-9ed5-f82f5876f740`.
- Parent native session: `01a0ef1e-200c-78c1-b3d2-9a2c482813b1`; no child ID.
- POST accepted: 2026-09-29T21:42:03.498Z. App run completed: 2026-09-29T21:44:17.343Z.
- Original upload SHA-256: `2b066cc3d4c03c1aebf8a7c4d2d66ede8f17a00301f904881561fb8b974b9bb7`; exact download hash preserved.
- Unchanged source-bound settlement reader passed: native ownership idle, active turn null, done event present, no active own runs, provider requests or image work pending, no own quarantine.
- Only own ticket removed at 2026-09-29T21:45:13.072130+00:00; remaining tickets zero. Policy hash restored to the initial hash. Own SSH tunnel closed.
- Final scoped readback: 2026-09-29T21:48:16.369621+00:00; public chat503/status200. Approval window was never opened; no watcher was started and no approval was submitted.

## Limits and evidence

An extra retained deployment-wide readback failed at `preservation(True)`, fixed historical event-count assertion `len(added)==6`, after this acceptance added events. Its failure is preserved and is not a successful global preservation receipt. No reader was weakened or retried. The exact per-session settlement reader independently passed again after ticket removal. Initial idle readback preserved two historical uncertain owners and three quarantines; no actions targeted them.

`FAILURE-BOUNDARY.json` contains exact actual arguments/results, parent declarations, final boundary evidence, and the stop decision. `FINAL-SCOPED-READBACK.json`, `DISPATCH-PLAN.json`, and `RESULT.json` provide compact receipts. The private capture retains normalized/provider/Responses/native/app records (archive SHA-256 `a82b3e97b13733a73b3ee5773970e009ff02a24359451a909a6d9daad0dcaf3d`). Raw captures remain outside Git.

No source, deployment, application configuration, model, runtime, hardware, or qualification changes. No native visual-understanding claim. No image artifact exists for visual review. This session is closing early; the wrapper will record its actual exit afterward, and no premature exit0 is claimed.
