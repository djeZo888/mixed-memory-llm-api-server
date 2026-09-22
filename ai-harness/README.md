# ai-harness v0.0.1

A shared LAN chat for technical research, PDFs and coding, using MiniMax Code
and the two existing Qwen instances. This guide describes the approved scope
and current design; **deployment and live acceptance are still in progress**.
See the [approved plan](PLAN-v0.0.1.md) and [architecture](docs/architecture.md).
**Acceptance report — placeholder:** [future reviewed report](docs/acceptance-v0.0.1.md).
That target does not exist yet; the coordinator will update it after live tests.

## Access and everyday use

The planned address is `http://10.156.100.61/`. There are no accounts, login,
settings or model selector. Everyone with access shares conversations and task
access. The operator controls LAN access; HTTP provides no transport encryption.
This is a shared workspace service with no per-person privacy boundary.

- Choose **New chat**, or select an existing chat from the list, then send a task.
  Follow-ups in one chat run sequentially; separate chats can run concurrently.
- Attach PDFs or source/text files. Download generated files from artifact links.
  Optional image uploads are enabled only after deployment acceptance of that
  path; this guide does not establish current image availability.
- Expand progress to follow actual browsing, tools, tests, background subagents,
  queueing and compression. Progress is activity reporting, not hidden reasoning.
- Refresh or reconnect to recover saved history and current progress without
  duplicate replies. Closing the browser does not stop server-side work.
- Use **Stop** to cancel active work and wait for confirmed cleanup. After a
  proven clean stop, a new explicit prompt continues the same native session,
  preserving history, context and project workspace. Cancelled tasks stay stopped.
  Unknown/interrupted work must not silently replay; unresolved cleanup needs
  operator review before the workspace can be used again.
- **Continue in new chat** creates a handoff summary and a new conversation using
  the same project workspace. The old chat and history remain. Runs in linked
  chats serialize because they share project files.
- **Delete chat** cancels active work first and waits for confirmed cleanup.
  Deleting conversation metadata retains project files; it is not file cleanup.

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
supported.

## Work supported by the approved scope

Ask for public web research, JavaScript-rendered pages and source links using
private SearXNG search and local Chromium. Search is available without a toggle;
the model chooses when to use it. Logged-in website actions and publishing are
outside scope. PDFs support upload, text extraction, page rendering, OCR and
basic generation from HTML/Markdown. Coding work includes investigation, edits
and tests with Python, C++ and Node.js. Office formats, CAD and simulators are
outside v0.0.1 scope.

## Operator use

After reviewed deployment and activation, run these ordinary service commands as
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
