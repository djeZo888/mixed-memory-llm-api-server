# ai-harness 0.0.1 — approved implementation plan

Approved by the user on 2026-09-22. This is the active scope for ai-harness;
historical frontend exclusions in parent guidance do not block this work.
Mac-Orchestrator coordinates and reviews; mac-worker1 implements and tests
through fresh bounded remote Codex CLI sessions in isolated working copies.

## 1. Confirmed decisions

MiniMax supports background subagents. Both Qwens serve independent delegated
tasks and separate chats. A shared gateway admits two simultaneous inference
requests overall; additional requests wait.

| Setting | Decision |
| --- | --- |
| Models | Existing two Qwen instances; no GLM integration |
| Context | Fixed 480,000 tokens per main/subagent session |
| Maximum output | 65,536 tokens per inference request, including reasoning where counted |
| Website | http://10.156.100.61/ on HTTP port 80 |
| Access | Single user, no login; user manages LAN restriction |
| Search | Always available; the model decides when to use it |
| Isolation | Lightweight rootless containers |

Input and output share the context window. With a 65,536 output allowance,
MiniMax's reviewed production budget starts normal compression around 412,416
input tokens (85.92%); tool-output archiving may occur earlier.

## 2. Engine and context

- Pin MiniMax source revision `ae65651df5f97ae1085ab4e19964f4b78c769a4e`.
- Configure one logical Qwen provider through a shared ai-harness gateway.
  GPU0 uses `http://10.156.100.60:30002/v1`, model `qwen3.8-27b-gpu0`;
  GPU1 uses `http://10.156.100.60:30004/v1`, model `qwen3.8-27b`.
- Translate endpoint model aliases while preserving messages, tools, streaming
  and usage. Apply one generation slot per endpoint to main agents, background
  subagents and compression. Release slots between requests; never hold a slot
  while a parent waits for a child. Queue wait is cancellable and bounded.
- Enable native background subagents and explain the two shared inference slots
  in concise agent instructions. Keep model weights, runtimes and placement
  unchanged; leave both existing Qwens warm at 480K.
- Permit up to two hours of active generation, handling queue wait separately.
  Browser disconnection does not terminate the task. Do not retry partially
  emitted responses or replay tool side effects. An ambiguous upstream stop must
  not be mistaken for an idle GPU; retain/drain its slot until settlement.
- Reuse native automatic compression and its snapshots/archived tool results.
  Preserve original visible history. Display actual compression progress and
  failures and prevent endless overflow retries.
- Display estimated occupied context after each reply and compression, e.g.
  `Estimated context: 123,456 / 480,000 tokens — 25.7%`. Distinguish estimates,
  stale/unavailable measurements and cumulative inference usage. Validate against
  the deployed tokenizer during acceptance.
- Provide Continue in new chat, using a handoff summary and retaining the old
  conversation and project files. The new chat shares the intended project
  workspace; serialize mutations if both linked conversations are active.

## 3. Browsing, PDFs and technical work

- Enable MiniMax's local Chromium integration and private SearXNG search through
  a small MCP adapter. No paid search API or MiniMax account is required.
- Support public-page research, JavaScript rendering, links and downloads.
  Search is available without a toggle or mandatory use on every message.
  Return source links. Exclude logged-in website actions and publishing.
- Support PDF uploads/downloads, text extraction, page rendering and OCR using
  Poppler, pypdf/pdfplumber and Tesseract. Reuse the PDF skill without cloud
  vision fallback. Create basic PDFs from HTML/Markdown with Chromium.
- Test small image inputs on both existing Qwens. Enable image uploads only if
  successful without material runtime/model changes or reduced context;
  otherwise report the limitation explicitly. No new model downloads.
- Reuse MiniMax shell/file/Git/review/task tools. Install GCC/Clang, CMake, Ninja,
  GDB; Python virtualenv/pip/pytest and numerical/plotting libraries; Node.js/npm,
  TypeScript and browser testing tools.
- Curate local skills for code investigation/review, technical research, PDF
  work, calculations and datasheet analysis. Load detailed skill instructions
  only when relevant. Skip other Office formats/languages, CAD and simulators.

## 4. Web application

Use React/Vite, TypeScript/Fastify, SQLite metadata and filesystem storage.
Connect to MiniMax using ACP. A minimal reverse proxy serves HTTP port 80.

- Left: chat list, New chat and Delete chat. Right: full conversation, composer
  and streamed replies; collapsible real progress for browsing, shell/tests,
  subagents, queueing and compression; context occupancy after replies.
- Include Stop, attachment uploads, artifact downloads and Continue in new chat.
  No accounts, registration, settings, model selector or context selector.
- Refresh/reconnect restores progress without duplicates. Follow-ups in a chat
  execute sequentially; different chats can execute concurrently.
- Deleting an active chat cancels it first and preserves generated project
  files. Restarted service marks interrupted jobs instead of blindly replaying
  commands. Progress must reflect real events, not invented internal reasoning.
- Keep backend/admin credentials and host management sockets outside rootless
  task containers. Retain browser-origin/host checks. Everyone who can access
  the no-login UI shares conversations and task access.
- The application API covers session CRUD, messages, streaming events,
  cancellation, uploads, artifacts and handoffs. The inference gateway remains
  internal. No model lifecycle credentials are needed.

## 5. Execution, verification and publication

1. Publish this plan and README before implementation.
2. Build pinned MiniMax/runtime and the shared gateway.
3. Implement the ACP chat application and context reporting.
4. Integrate Chromium/search/PDF/coding tools.
5. Perform bounded acceptance and publish reviewed version 0.0.1.

Retain task prompts, native session IDs, source commits and compact evidence in
project state. Keep bulky traces and all secrets outside Git. Synchronize worker
commits automatically for review. First-party additions are MIT; preserve all
third-party notices. General all-in-one installer work remains deferred.

Acceptance must demonstrate: concurrent chats and native background subagents;
queueing/cancellation/session isolation; 65,536 output-setting acceptance and no
hidden 16K clamp; long-running streams; compaction and continued work with original
history retained; technical web research/JS pages; PDF OCR/read/create; meaningful
Python/C++/Node edit-and-test tasks; browser reconnect and service restart; and an
explicit result for optional vision. Use bounded live cases and protocol fixtures,
not a forced full 64K output or repeat of the completed GPU benchmark campaign.

## Source references

- [MiniMax Code](https://github.com/MiniMax-AI/minimax-code)
- [Pinned context budget](https://github.com/MiniMax-AI/minimax-code/blob/ae65651df5f97ae1085ab4e19964f4b78c769a4e/packages/agent-modules/context-manager/src/provider-budget.ts)
- [SearXNG API](https://docs.searxng.org/dev/search_api.html)
