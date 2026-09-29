# ai-harness v0.0.3

Version 0.0.3 adds resident Qwen image generation and guarded editing to ordinary
chat and fresh ordinary workers. The bounded edit campaign completed three native
MCP edits, including a follow-up reference and external resize approval across
refresh, with no fallback or retry. Root visual review is recorded in the
[current acceptance report](docs/acceptance-v0.0.3.md) and
[compact evidence summary](docs/acceptance-v0.0.3.json).

See [chat examples](docs/chat-examples-v0.0.3.md) for usable image prompts.
The [optional Codex harness](PLAN-CODEX-HARNESS.md) is deployed
as a selectable preview beside MiniMax. **Public chat is currently in maintenance
while complete Codex integration is finished.** The pinned Codex 0.158.0 integration
uses local Qwen through Sova's shared gateway, without OpenAI model login or
paid inference. MiniMax remains the default. See the
[execution record](../docs/h021-codex-execution.md) and
[historical preview acceptance report](../reports/h021-codex-preview.md) for
earlier checks. The [H035 checkpoint](../reports/h035-codex-checkpoint.md)
retains the successful H033 MiMo tool execution and complete child/parent replies
through both engines; ordinary Codex frontier access is enabled. H035 adds
read-only image-job status and durable result-delivery code, and the live PDF
regression now passes with accurate error disclosure and recovery. Original and
native-child image generation passed in H034. Its guarded edit produced the
correct image but an incomplete final handoff; both H035 follow-ups stopped with
a promise and no actual tool call. Codex's full image gate remains closed.
Native visual recognition is unsupported. See
[remaining work](../reports/h035-next-execution.md). The
[H032 checkpoint](../reports/h032-codex-checkpoint.md) preserves earlier failures
and partial PDF acceptance.
Real Stop, same-thread
follow-up and reconnect passed on the final Codex repair.
The [earlier worker-path failure](docs/acceptance-v0.0.3-historical-worker-failure.md)
remains historical evidence. [v0.0.2 acceptance](docs/acceptance-v0.0.2.md)
records earlier chat/progress/download/ZIP checks; [v0.0.1](docs/acceptance-v0.0.1.md)
records earlier PDF/search/lifecycle checks. Those checks were not rerun by the
three-edit campaign.

## Current UI behavior

- Emitted intermediate updates appear separately from the classified final;
  completed final answers collapse progress, and reopening retains the updates.
  This reliable separation applies to new replies with proven native metadata.
  Old merged text remains original/unclassified; no retroactive perfect split is
  promised. Progress reports actual activity, not hidden reasoning.
- Each reply owns its activity, previews, downloads and per-run **Download all
  ZIP**. Follow-ups submitted during work queue for the next turn. Refresh
  restores saved messages and progress.
- Attach or drop supported files. Submitted messages retain recorded attachment
  names and download links. **Enter** inserts a newline; **Ctrl+Enter** or
  **Cmd+Enter** submits. Ctrl+Enter passed live; platform IME and Cmd+Enter remain
  outside this live acceptance.
- An untouched new chat starts at **0 / 480,000 tokens (0%)**. Later context is
  an estimate with explicit unknown/stale states. Timestamps use
  **Europe/Ljubljana**; actual displayed times and the independently verified
  host timezone agree.

The earlier v0.0.2 WEB corrections fold compatibility heartbeat rows into the existing
**Additional activity** section, suppress stale finish/duration on nonterminal
activity, set the attachment's explicit download name and omit whitespace-only
assistant rows. History, nonempty partial text and canonical status remain.
The saved active snapshot verifies the timing correction; deployed settled
readback verifies 43 primary / 156 Additional activity rows and reply grouping.
Drag/drop has fixture coverage; actual file-chooser upload passed live, without
OS drag automation. Focused tests, build/typecheck and the saved snapshot fixture
remain distinct from actual deployed evidence.

For v0.0.2, Worker1 independently verified deployment at a closed-admission
barrier: 68 messages, 30 SQL file rows and 72 regular files (825,197 bytes), with
matching paired message/file fingerprints. The earlier activation separately
preserved 61 messages, 27 SQL file rows and 66 regular files. These are bounded
barrier comparisons, not a later all-user history audit. The earlier CI and D2 checks passed;
the unchanged deferred installer fixture retains one TMPDIR-regex failure,
detailed in the acceptance report.

## Access and everyday use

The active HTTP port 80 address is `http://10.156.100.61/` (verified final deployment).
There are no accounts, login, settings or model selector. Everyone with access
shares conversations and task access. The operator controls LAN access;
HTTP provides no transport encryption.
This is a shared workspace service with no per-person privacy boundary.

- Choose **New chat**, or select an existing chat from the list, then send a task.
  Follow-ups in one chat run sequentially; separate chats can run concurrently.
- When the Codex preview is enabled, choose **Harness: MiniMax / Codex** for a
  new chat. Existing chats retain their engine for follow-ups. An engine's
  capability panel distinguishes qualified features from pending or unsupported
  ones; a Codex preview does not imply that every MiniMax feature is qualified.
- Attach PDFs, source/text files or images; download files from artifact links.
  Earlier PDF and image coverage is recorded in the
  [v0.0.1 report](docs/acceptance-v0.0.1.md).
- Expand progress to follow actual browsing, tools, tests, background subagents,
  queueing and compression. Progress is activity reporting, not hidden reasoning.
- Refresh or reconnect to recover saved history and current progress without
  duplicate replies. Closing the browser does not stop server-side work.
- Use **Stop all** to stop the native task/container and wait for confirmed cleanup.
  Already dispatched inference may keep draining and temporarily occupy a lane.
  The earlier Stop and follow-up acceptance is recorded in the v0.0.1 report.
  After a proven clean stop, a new explicit prompt continues the same native
  session, preserving history, context and workspace. Cancelled tasks stay stopped.
  Unknown/interrupted work must not silently replay; unresolved cleanup needs
  operator review before the workspace can be used again.
- **Continue in new chat** lets you choose an available engine, then creates a
  handoff summary and a fresh native conversation in the same project workspace.
  The source engine is selected initially. The old chat and history remain;
  native history is never resumed by another engine. Runs in linked chats
  serialize because they share project files.
- **Delete chat** cancels active work before hiding metadata and retains project
  files. Earlier Delete acceptance and its cancellation-message limit remain in
  the v0.0.1 report.

## Image generation and editing

| Operation | References | Supported output sizes |
|---|---:|---|
| Generate | 0 | 1024×1024, 1024×576, 1216×704, 1472×832, 1760×992, 1920×1080 |
| Edit | 1 | 1024×1024, 1536×864 |
| Edit | 2 | 1024×1024 |

Each creative request produces one opaque PNG through the resident image model.
Full HD **editing**, masks and transparency are unavailable. Full HD generation
uses native 1920×1088 with the bottom eight rows removed; public output stays
1920×1080. The public ceiling is 2,073,600 pixels. The
[measured qualification](../reports/h003-edit-capacity-20260923/RESULT.md) excludes
Full HD editing because it fell below the required 5% free-memory reserve.

Attach a source image to ask for a concrete change. **Use for next edit** stages a
result as the next reference. Originals remain unchanged and each completed edit
has a separate artifact with its own preview, download, dimensions and seed.
When a resize/canvas change is needed, review the real card's original/working
sizes, padding and target. **Reject change** cancels before image dispatch;
**Approve resize** starts that exact saved proposal. Refresh preserves a pending
card, and its job can complete after the assistant turn without another message.
An assistant statement of approval does not replace the user's card decision.

Omit the edit seed for a fresh one. Known source/ancestor-seed collisions are
rejected before dispatch, never silently replaced. Imported images may lack
history, including images uploaded into a new chat. Fresh seeds are a workaround
for the retained seed42 failure, not an intrinsic repair or a promise of
pixel-exact preservation. Do not repeat an uncertain accepted request; review its
saved job state. Main chat and fresh ordinary workers have the creative tools;
explore/verifier/custom restrictions remain unchanged.

## Capacity and context

Qwen main and child sessions have a fixed **480,000-token context**.
**MiMo V2.6 Pro-RL** is the selected frontier with **950,000 configured tokens**.
Actual MiMo tool continuation and child-to-parent completion through both Codex
and MiniMax passed in H033; H035 retains those results through an explicit
compatibility review. The earlier near-950K occupied-context test failed and is
not running. Short workflow acceptance does not qualify the full context window.
GLM's retained **1,048,576-token** profile is dormant. Histories and files are
preserved. See the [frontier acceptance](../reports/h033-codex-checkpoint.md)
and [retained long-test result](../reports/h022-950k-status.md).
The maximum
output is **65,536 tokens per inference request**, including reasoning where
counted. Input and output share the context window; these are configured limits,
not a claim that full-window occupancy or full-length output has been accepted.

One logical gateway serves both existing Qwens, with **exactly two shared request
slots globally**, one per endpoint. Chats, native background subagents, automatic
compression and auxiliary requests all compete for those slots; extra requests
queue. A waiting parent does not reserve a slot. Qwen remains the default for
coding and ordinary agents. A parent may selectively delegate an independent
subtask to the native `frontier` child on a separate inference lane; the parent
then reviews the returned result. The selected MiMo release permits eight hours
of active inference plus a separate 30-minute queue. Current readiness is checked
independently of retained workflow acceptance. Qwen retains its existing limits;
historical GLM acceptance is recorded separately below.

The [H009 native acceptance](../reports/h009-frontier-20260926/ACCEPTANCE-02.md)
passed one full-roster code workflow: Flash read, patched and tested a file,
then Qwen independently reviewed the edit, reran the checks and returned the
final answer. A separate Qwen completion overlapped occupied Flash. The actual
Flash inputs were11,555–12,439tokens, with a2,048-token test output ceiling.
Those historical tests preceded the later GLM promotion to1,048,576 context;
the65,536 production output ceiling is unchanged.
The result does not qualify full-window occupancy, every exposed tool, or new
cancel/reconnect behavior. First-request latency included substantial prefill;
use Flash selectively, not as the default coding agent.

After replies and compression, the UI reports **estimated occupied context**,
not cumulative token usage. A stale value describes an earlier observation;
unavailable means no usable measurement, not zero. Native automatic compression
keeps original visible history and archived tool results. There is no user
context setting. MiniMax's Qwen budget starts normal compression near 412,416
input tokens to reserve output space; tool results may be archived earlier.
Codex uses its open-source native compaction with the local inference provider.
The configured thresholds are **400,000 tokens for Qwen** within its 480,000-token
window and **880,000 for MiMo** within its 950,000-token window. A small actual
compaction followed by four-fact recall and continued work passed in
[H030](../reports/h030-flow03-20260929/COMPACTION-RESULT.json) and
[H031](../reports/h031-flow01-20260929/COLD-RESULT.json). Original visible history
and files remain saved; the active model receives summarized context. Summaries
can omit or misstate details, so durable project files remain important.
Native CLI slash commands such as `/status`, `/context` and `/compact` are
unsupported and rejected in the web integration. Automatic compression remains
supported. Automatic triggering at the configured near-full thresholds and web
compression rendering remain untested. This does not claim identical summary
quality to the hosted OpenAI models used by the Codex Mac app.

## Work supported by the approved scope

Ask for public web research, JavaScript-rendered pages and source links using
private SearXNG search and local Chromium. Search is available without a toggle;
the model chooses when to use it. Logged-in website actions and publishing are
outside scope. PDFs support upload, text extraction, page rendering, OCR and
basic generation from HTML/Markdown. Coding work includes investigation, edits
and tests with Python, C++ and Node.js. Office formats, CAD and simulators are
outside v0.0.1 scope.

## Operator use

Use [status](http://10.156.100.61/status) for read-only observations and
[admin](http://10.156.100.61/admin) for normal typed lifecycle operations. Admin
is anonymous within the deployed trusted/shared-LAN scope; there is no per-user
authentication. The optional user-managed `status.ai-harness` DNS alias is
status-only; its DNS configuration is not asserted here.

| Status | Meaning |
|---|---|
| Unavailable | Current evidence says the service cannot serve, for example because it is stopped or failed. |
| Unknown | Evidence is missing, stale or inconclusive; it does not mean zero work or a missing GPU. |
| Latched | Persistent hardware protection is holding the affected target. A service restart or a healthy same-boot observation does not clear it; protected new-boot validation is required. |

A ready service can still be busy. Active or queued work causes backpressure;
that is not unavailability. Check the separate activity and observation freshness.

Each native scheduler keeps a **600-second busy grace after final real work
completes**, including response drain and pending asynchronous work. Active,
queued, draining or unknown work prevents blocking. Once genuinely idle beyond
grace, it blocks waiting for an event while retaining model weights and cache
allocations. Ordinary work wakes it immediately through that event and renews
grace; this is wake behavior, not a zero-latency response promise. Passive status
polls do not renew grace. The measured quiet/wake and reboot checks passed; see the
[September 26 closeout](../docs/h005-closeout-20260926.md). VRAM residency alone
does not prove cache contents.

For normal operations, use the canonical typed admin action, review its affected
services and interruption confirmation, then wait for its terminal receipt.
An accepted request is not completion. After a timeout, inspect the existing
operation; never blindly replay an uncertain action. An unknown/interrupted result
needs confirmed recovery rather than an assumed success. Refresh stale target
boot/generation identity before a distinct, explicitly confirmed new request.
This path preserves operation ownership, scoped holds and receipts.

The direct commands below are **host recovery procedures**, not the normal
operator path. Run them as the existing `user` account on the ai-harness host
when host recovery is needed. Choose the needed action; stop/restart can interrupt
active tasks and must not trigger automatic replay.

```sh
systemctl --user status ai-harness.service ai-harness-searxng.service --no-pager
journalctl --user -u ai-harness.service -u ai-harness-searxng.service -n 80 --no-pager
systemctl --user start ai-harness-searxng.service ai-harness.service
systemctl --user stop ai-harness.service ai-harness-searxng.service
systemctl --user restart ai-harness-searxng.service ai-harness.service
```

An active unit alone does not prove readiness. Use the detailed
[deployment](deploy/README.md), [user runtime](deploy/RUNTIME.md),
[SearXNG operations](tools/searxng/README.md) and
[server recovery guidance](server/README.md) for deployment-specific procedures.
Keep credentials private when reviewing logs. This guide adds no installation
procedure or host/account changes.

## Licenses

First-party additions are MIT: [server](server/LICENSE),
[tools](tools/LICENSE-MIT.txt) and [skills](skills/LICENSE-MIT.txt).
Preserve upstream, tool, dependency and model licenses/notices; see the
[search notices](tools/search/NOTICE.md), [PDF notices](tools/pdf/NOTICE.md) and
[adapted PDF skill notice](skills/pdf/NOTICE.md). SearXNG is a separate
**AGPL-3.0-or-later** service, not relicensed MIT: [notice](tools/searxng/NOTICE.md)
and [license](tools/searxng/LICENSE-AGPL-3.0.txt).
