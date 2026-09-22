# ai-harness v0.0.2 candidate

Version 0.0.2 was authorized on 2026-09-22. This checkout contains the reviewed
candidate UI source; this task supplies **source and synthetic fixture evidence
only**. It does not establish that 0.0.2 is deployed or accepted on the live
service. See the [0.0.2 plan](PLAN-v0.0.2.md) and
[0.0.2 acceptance report](docs/acceptance-v0.0.2.md) for exact identities,
observations and limits. Production remains separately owned. Fixture review
found a minor status inconsistency: the header/sidebar can say idle while the
run-status strip correctly shows a queued follow-up; root/WEB triage is pending.

## Candidate UI changes

- Progress displays emitted intermediate updates separately from the classified
  final answer. It opens during work, collapses when the final answer is ready,
  and can be reopened. Missing historical phase information stays unclassified.
- Each reply groups its own activity and files. Canonical tool updates retain
  available command, URL, duration and detail. Child counts follow the supplied
  lifecycle summary; zero children alone does not mean a run has finished.
- Generated SVG/image files have per-reply previews and individual downloads.
  Replies with multiple files and a supplied archive route offer **Download all
  ZIP**. Proven shared-file membership is retained; unknown ownership is labelled.
- Attach or drop supported files on the composer. Submitted user messages retain
  their recorded attachment names and download links. Image capability and upload
  errors are visible. Failed submission retains the draft.
- **Enter** inserts a newline; **Ctrl+Enter** or **Cmd+Enter** submits, as does the
  send button. The composer displays this hint. Browser fixture checks do not
  establish platform IME compatibility.
- A follow-up sent while work is active queues for the next turn. It does not
  steer the current native turn. Run status remains visible outside the composer,
  and late answers/files stay with their original run across refresh.
- Only an untouched new chat displays **0 / 480,000 tokens (0%)**. Existing
  unknown and stale context retain those labels. Timestamps use
  **Europe/Ljubljana**, including automatic CET/CEST conversion.

These describe the candidate behavior and contract. Fixture events, uploads,
child counts and file bytes are synthetic. The fixture ZIP is an empty route
response: it proves neither production archive contents nor native generation.
Live engine/server behavior, native child counts, real ZIP contents, migration of
user history and production rendering remain **NOT_TESTED** in this phase.

## Preserved v0.0.1 release history and operating guidance

The following records the previously accepted release and its limits; it is not
a fresh inspection of the running service. The [0.0.1 plan](PLAN-v0.0.1.md) and
[0.0.1 acceptance report](docs/acceptance-v0.0.1.md) remain unchanged.

A shared LAN chat for technical research, PDFs and coding, using MiniMax Code
and the two existing Qwen instances. **Bounded live acceptance is complete with
limitations**, including unexecuted capacity and automatic-threshold cases.
See the [approved plan](PLAN-v0.0.1.md) and [architecture](docs/architecture.md).
The [acceptance report](docs/acceptance-v0.0.1.md) records tested revisions,
live findings, qualifications and unexecuted cases.

## Access and everyday use

The active HTTP port 80 address is `http://10.156.100.61/` (initial live readiness).
There are no accounts, login, settings or model selector. Everyone with access
shares conversations and task access. The operator controls LAN access;
HTTP provides no transport encryption.
This is a shared workspace service with no per-person privacy boundary.

- Choose **New chat**, or select an existing chat from the list, then send a task.
  Follow-ups in one chat run sequentially; separate chats can run concurrently.
- Attach PDFs, source/text files or images; download files from artifact links.
  The image upload/recognition/follow-up path passed a live synthetic-image case;
  the acceptance report bounds the tested PDF and image coverage.
- Expand progress to follow actual browsing, tools, tests, background subagents,
  queueing and compression. Progress is activity reporting, not hidden reasoning.
- Refresh or reconnect to recover saved history and current progress without
  duplicate replies. Closing the browser does not stop server-side work.
- Use **Stop** to stop the native task/container and wait for confirmed cleanup.
  Already dispatched inference may keep draining and temporarily occupy a lane.
  The V2 fix passed a tiny live Stop, same-chat follow-up and final health checks.
  After a proven clean stop, a new explicit prompt continues the same native
  session, preserving history, context and workspace. Cancelled tasks stay stopped.
  Unknown/interrupted work must not silently replay; unresolved cleanup needs
  operator review before the workspace can be used again.
- **Continue in new chat** creates a handoff summary and a new conversation using
  the same project workspace. The old chat and history remain. Runs in linked
  chats serialize because they share project files.
- **Delete chat** cancels active work before hiding metadata and retains project
  files. Corrected active Delete and file preservation passed live; that case still
  emitted the older cancellation error, recorded separately in the report.

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
