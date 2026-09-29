# Ordinary message submission identity (H029)

The web client supplies `submissionId` for every ordinary `POST
/api/sessions/:id/messages`. The server accepts 1–80 ASCII letters, digits,
underscores or hyphens; the browser generates a fresh UUID for each explicit
new submission. This is separate from a compaction `actionId`.

A chat session plus submission ID identifies one accepted run. Matching retries
return HTTP 202 and that original `runId` whether queued, active, completed,
failed, cancelled or interrupted. They do not append another user message/event,
re-enqueue, restage files or relaunch inference. Restart reconciliation remains
unchanged: interrupted work is retained and is never automatically replayed.
A changed accepted payload returns HTTP 409 `submission_conflict`, without
logging the payload or fingerprint. A different owned chat has its own keyspace
and cannot retrieve the original chat's run by reusing the ID. Deleted/deleting
chat and existing authentication/Host protections still apply.

The version-1 fingerprint is SHA-256 of a JSON object constructed in the fixed
order `version`, `text`, `attachmentIds`, `imageReferences`. HTTP object key order
is irrelevant. Text is exact (no trim or Unicode normalization); array order is
semantic and preserved. Omitted/null attachment/reference arrays normalize to
empty under the existing API contract. Attachment and image reference IDs are
part of the fingerprint; mutable file contents/paths are not reread on replay.
First acceptance still validates actual file type and chat ownership. No
per-message model, engine, generation or other options are supported; unknown
fields (including `options`) are rejected with HTTP 400 `invalid_body`, never
silently excluded. Engine selection is immutable chat metadata. A future accepted
option must explicitly extend the canonical payload and its compatibility tests.

`h029_message_submissions` is an additive companion table with primary key
`(session_id, submission_id)` and a unique run reference. `BEGIN IMMEDIATE`
serializes lookup, conflict comparison, synchronous broker admission, run and
image-reference creation, user message/metadata, context/title/status changes,
and initial durable events. Failure rolls the whole operation back and consumes
no ID. EventEmitter publication and broker queuing occur only after COMMIT;
only a result marked newly created enters the queue. Replay is checked before
asynchronous image capability observation, again on an observation failure, and
inside the transaction, covering a matching request committing during that await.

For old non-browser clients only, omission of `submissionId` remains supported:
each call creates a fresh server-generated ID/run. Such clients have no retry
protection and must not retry an uncertain accepted request. New UI always sends
an ID. Rolling back to an older server removes this new API guarantee; deploy
client/server together. No existing rows, histories, native IDs, files or old
compaction mappings are rewritten by this migration.

Before sending, the browser saves the exact body and ID in tab-scoped
`sessionStorage`. A storage failure prevents HTTP. Reload recovery is exposed
only after an owned-chat snapshot succeeds. Network errors, unknown errors,
5xx, unreadable acknowledgements and conflicts retain the saved attempt. SSE
reconnect and reload perform reads only; the user chooses **Retry saved
submission**. Its exact saved body is independent of the current draft and file
selection. New submission is blocked while acknowledgement is uncertain.

A valid run acknowledgement clears the saved attempt; an explicit new/repeated
prompt then gets a new UUID. Known HTTP 400 pre-admission validation errors
(`invalid_body`, `invalid_id`, `invalid_message`, `invalid_attachment`,
`invalid_image_reference`, `unsupported_slash_command`,
`codex_media_unsupported`, `codex_image_tool_unavailable`) are authoritative
nonacceptance and also unlock correction while retaining the editable draft.
Unknown/proxy/auth errors are not classified this way. Explicit chat deletion
removes its browser recovery record. Browser storage clearing/tab loss cannot
recover an ID that the browser no longer retains; this is not cross-device
submission recovery or automatic request retry.
