# ai-harness v0.0.3

Version 0.0.3 adds resident Qwen image generation and guarded editing to ordinary
chat and fresh ordinary workers. The bounded edit campaign completed three native
MCP edits, including a follow-up reference and external resize approval across
refresh, with no fallback or retry. Root visual review is recorded in the
[current acceptance report](docs/acceptance-v0.0.3.md) and
[compact evidence summary](docs/acceptance-v0.0.3.json).

See [chat examples](docs/chat-examples-v0.0.3.md) for usable image prompts.
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
- **Continue in new chat** creates a handoff summary and a new conversation using
  the same project workspace. The old chat and history remain. Runs in linked
  chats serialize because they share project files.
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

Each main or child session has a fixed **480,000-token context**. The maximum
output is **65,536 tokens per inference request**, including reasoning where
counted. Input and output share the context window; these are configured limits,
not a claim that full-window occupancy or full-length output has been accepted.

One logical gateway serves both existing Qwens, with **exactly two shared request
slots globally**, one per endpoint. Chats, native background subagents, automatic
compression and auxiliary requests all compete for those slots; extra requests
queue. A waiting parent does not reserve a slot. There is no GLM integration.

After replies and compression, the UI reports **estimated occupied context**,
not cumulative token usage. A stale value describes an earlier observation;
unavailable means no usable measurement, not zero. Native automatic compression
keeps original visible history and archived tool results. There is no user
context setting. The production budget starts normal compression near 412,416
input tokens to reserve output space; tool results may be archived earlier.
Native CLI slash commands such as `/status`, `/context` and `/compact` are
unsupported and rejected in the web integration. Automatic compression remains
supported. A manual native compaction/recall probe passed; production-threshold
compression and web compression rendering remain untested.

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
polls do not renew grace. The formal all-three quiet/wake check remains pending
in the [current acceptance report](../docs/service-resilience-acceptance.md);
VRAM residency alone does not prove cache contents.

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
