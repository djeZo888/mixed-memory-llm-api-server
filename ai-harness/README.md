# ai-harness v0.0.2

Version 0.0.2 is deployed at `cacfdd43`, including the four WEB corrections
exported as `42612a5`. Bounded deployed acceptance is complete with explicit
limits: one owned main request and queued follow-up, genuine progress, one
background child, refresh/reconnect, separate reply files, two SVG previews and
byte-verified downloads/ZIP passed. Final readback confirmed folded Additional
activity, retained history and no blank responding row. Chromium downloaded
`načrt.txt` with the exact 85 bytes under the combined UTF-8 process locale and
`sl-SI` browser context. Earlier literal `download` observations remain a utility
configuration finding; the individual locale variables were not isolated.
The child's public browser result is model-reported; neither native nor fallback
browser execution was independently proven.

See the [current acceptance report](docs/acceptance-v0.0.2.md),
[machine-readable results](docs/acceptance-v0.0.2.json) and
[release plan](PLAN-v0.0.2.md) for exact revisions, verification and remaining
limits. [Version 0.0.1 acceptance](docs/acceptance-v0.0.1.md) remains the historical
record for earlier PDF, search, lifecycle and capacity checks.

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

The deployed WEB corrections fold compatibility heartbeat rows into the existing
**Additional activity** section, suppress stale finish/duration on nonterminal
activity, set the attachment's explicit download name and omit whitespace-only
assistant rows. History, nonempty partial text and canonical status remain.
The saved active snapshot verifies the timing correction; deployed settled
readback verifies 43 primary / 156 Additional activity rows and reply grouping.
Drag/drop has fixture coverage; actual file-chooser upload passed live, without
OS drag automation. Focused tests, build/typecheck and the saved snapshot fixture
remain distinct from actual deployed evidence.

Worker1 independently verified the final deployment at a closed-admission
barrier: 68 messages, 30 SQL file rows and 72 regular files (825,197 bytes), with
matching paired message/file fingerprints. The earlier activation separately
preserved 61 messages, 27 SQL file rows and 66 regular files. These are bounded
barrier comparisons, not a later all-user history audit. Current CI and D2 pass;
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

For the deployed service, run these ordinary service commands as
the existing `user` account on the ai-harness host. Choose the needed action;
stop/restart can interrupt active tasks and must not trigger automatic replay.

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
