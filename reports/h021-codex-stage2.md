# H021 stage 2 — protocol, sessions and tools

September 28, 2026. This checkpoint records source and fixture qualification; it
does not declare the preview deployed or real-model acceptance passed.

## Source and execution

- Codex 0.158.0, source `064c6b8c737f5b41d171fdda80bd9ef10ad06eb3`.
- Worker1 source `7745bac2ece47e9d58b86679cf93459fe0529915`, including
  Worker2 core `805f9d64321b5720909a17cbbcf3846838205d25`.
- Worker2 final implementation `d0b3465a57578569bb3b9c852174e05e39ec6e1f`.
- Worker2 native session `01a0e68f-e6c4-7cd1-855c-37f0a87187d5` exited 0
  at 06:23:30 UTC after 33m45s. Worker1's session was still active at this
  checkpoint; its terminal receipt follows separately.

## Results

| Check | Result and limit |
|---|---|
| Native subagents and compaction | Actual pinned Mac App Server, eight synthetic model requests through the shared gateway. Child ID, successful wait, terminal ordering and automatic/explicit compaction passed. This is transport evidence, not model quality. |
| Admission settlement | Eight token-count calls; both fixture lanes idle, no remaining owned work or queue. |
| Native context overflow | One terminal failure, zero upstream generation requests, no automatic retry. |
| Linux rootless runtime | Effective managed configuration, rejected provider overrides, edit/test/resume and exact-container cleanup passed with synthetic replies. |
| Adapter and storage | 476 baseline server checks, 20 final affected checks, 183 web checks and builds passed. Histories/files remain readable when Codex is disabled; Codex follow-ups do not switch engines. |
| UI | Owned localhost render passed. A capability panel overflow and misleading Ready label for disabled Codex were corrected. Deployed UI acceptance remains pending. |
| Matched coding fixtures | Original Python/C++/Node defects fail independent tests; temporary reference repairs pass. Agent performance is not established by these fixtures. |

Qwen's exact template rejects developer-role messages and later system messages.
The adapter therefore collects ordered system/developer policy into one initial
system envelope, retaining role, text and translated-message position. The
original priority is stated explicitly; ordinary conversation order is retained.
This is a documented adaptation, not native developer-role support.

Codex tool namespaces are mapped reversibly into Chat function names, preserving
namespace guidance, call IDs and history. Captured native subagent transport
passes. The first real-Qwen pilot stopped before counting or generation; the
deployed MCP catalog exposed additional namespaces that need a narrow follow-up
repair. The original attempt did not capture the native error detail; a fixture
reproduced that specific catalog incompatibility. Native/container/gateway cleanup
and restoration of the original inactive app unit were confirmed.

Raw captures, initial failures and full logs stay in the private H021 task
directory. Worker2 delivery bundle SHA-256:
`8744f46712715ba196d12d6e41365d6d5117bc3d979dce56a4bb90c0e0ae1853`.
Worker1 stage-2 review bundle SHA-256:
`fda4935efdc9aa8857ee53cf824783fa2a5cb5c8a6af4e0b76e947647a6a4f5d`.

## Remaining

Pass the short real Qwen tool/follow-up gate, qualify operational specialist
tools and actual application workflow, then deploy the reviewed optional preview.
MiniMax remains default. MiMo live Codex acceptance remains deferred while the
independent 950K benchmark runs. This task has neither polled nor modified it.
