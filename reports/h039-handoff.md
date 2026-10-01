# Sova handoff — 1 October 2026

## Start here

Read this file, [H039 execution plan](h039-execution-plan.md), and
[H039 worker sessions](h039-worker-sessions.json). Adopt existing sessions/jobs
before starting duplicates. H039 source preparation is authorized; shared live
integration needs root review of the resulting candidate. Sova may remain down.
Creative image generation is deferred; compaction is the first priority.

Repository: [djeZo888/mixed-memory-llm-api-server](https://github.com/djeZo888/mixed-memory-llm-api-server).
Integration checkout: `/Users/agent/Documents/LLMServer/orchestration/h005-integration`.
Working branch: `feature/h037-codex-default-ada-image`.
[PR #11](https://github.com/djeZo888/mixed-memory-llm-api-server/pull/11) remains
draft and unmerged; default branch is `main`. The checkpoint before this handoff
is `c73a853abbf46ecede65d0dae04dd2e5ac8e5c37`.

## Requirements that take precedence

- Reliable lengthy technical conversations/projects through repeated context
  compaction. Use the current fast Qwen by default; a fluent but inaccurate
  summary is not a pass. Preserve authoritative project facts and recoverable
  original sources separately. Do not promise universal lossless summarization.
- Technical image-to-text specialist: approved Qwen3.5-9B BF16 plus
  PaddleOCR-VL-1.6 on one 48 GB Ada, subject to measured combined runtime fit.
  Prepare/download now. The user is bringing the external Ada online and trying
  20 Gbps for stability; do not assume it is present.
- The smaller Ada 200K Qwen may be removed, and keeping Sova available is not
  required. Verify actual roles: H038 already retired that Qwen and assigned
  the internal Ada to creative images. Coordinate reassignment explicitly.
- No Codex/MiniMax history interoperability is required. Codex is the preferred
  harness; MiniMax retirement is separate and must preserve old conversations.
- New first-party Sova code is to be written by AI, with human requirements and
  review. Do not make this authorship claim for upstream dependencies.
- Organizations/users/permissions, horizontal scaling, Project mode and a
  headless Linux agent API are future work, not prerequisites to this release.

The detailed [future vision](../docs/Vision%20for%20future%20regarding%20this%20project.md)
and [TODO index](../todo/README.md) are already published. The separate
[status/sensor/safety plan](../todo/status-service-improvements.md) is documentation
only: 2,000 ms polling, secret references/encrypted credential handling,
configurable host/GPU sensors and critical admission pause preserving resident
models. It is not implemented by this handoff.

## Last verified deployment — retained H038 evidence

No fresh operational acceptance is implied by this list. The latest actual
qualification is [H038](h038-checkpoint.md) and [its results](h038-results.json).

| Component | Retained state / scope |
| --- | --- |
| Harness | Codex 0.158.0 is new-chat default; MiniMax selectable; existing engine IDs/history preserved |
| Qwen | Two Qwen3.8-27B FP8 instances, 480K, fast Blackwell and server Gen3 x4 Blackwell |
| Frontier | MiMoV2.6 Pro-RL, RAM plus fast Blackwell, 480K, eight decode threads |
| Context | 400,000 Codex auto-compaction threshold; 65,536 output ceiling; templates/tools/output also reserved |
| Creative image | Internal Gen4 x16 Ada backend startup ready; chat tools gate closed; current-placement workflow acceptance deferred |
| External Ada | Intentionally excluded after unstable Core X link; user is repairing it |
| Updates | Manual maintenance policy; no automatic OS/runtime/model upgrades |

The Mac CLIs are 0.159.2. Updating them does not update Sova's separately pinned
0.158.0 native runtime. A large upstream-main upgrade was intentionally held:
[upstream audit](h037-upstream-codex-audit.md).

## Codex completion: evidence and remaining work

| Feature | Evidence / remaining task |
| --- | --- |
| Default engine, new chat, attachments as files, Python calculation, file output, follow-up | Fresh H038 pass |
| Qwen and MiMo child tool execution, continuation, parent handoff, settlement | Fresh H038 pass for MiMo; retained Qwen evidence |
| Python/C++/Node coding, search/browser, PDF extraction/OCR and basic creation | Retained passes; no native pixel understanding claim |
| Ordinary persistence, cold resume, browser reload, event replay, queued Stop and duplicate protection | Retained scoped passes; restart during active owned work still needs specific qualification |
| Context compaction | Native mechanism exists; small recall passed but one factual error exists; large AUTO metadata and isolated summary-only quality remain unqualified |
| Repeated technical retention / authoritative project memory | H039 A/B source work and new small live suite are first priority |
| Missing usage events | Must remain unknown until measured; no fabricated zero |
| Active-process Stop, restart during streams, saturation/lane fallback, overlapping parent/child admission | Focused follow-up qualification still needed; do not extrapolate queued Stop evidence |
| Mid-turn steering | Queued follow-ups exist; true active native steering remains pending |
| Technical vision bridge | H039 C/D preparation; GPU/runtime/normal chat acceptance still pending |
| Creative image chat workflows | Deferred by user, not a current compaction blocker |
| Upstream Codex update | Separate source/protocol qualification task; do not casually pull main into production |
| PR CI and merge | Resolve failed installer fixture evidence, then review and merge; no current merge authorization from this handoff alone |

### Exact compaction gaps

H030 recalled four facts without tools but misstated a 22-byte file as 18 bytes.
H036 compacted 402,104 input tokens to 237 summary tokens; raw AUTO trigger
metadata was absent. Its follow-up also read an answer-bearing fact file, so
summary-only recall was not isolated. MiMo child tool work does not qualify
MiMo compaction quality. Existing fixtures do not prove native transactional
rollback under every failure. See the [full priority plan](../todo/context-compaction-reliability.md).

H039 uses a new 50–100-fact corpus and three small cycles with corrections,
critical-fact scoring, isolated summary-only recall, source retrieval and a real
technical continuation. Audit exact native replacement/persistence before
choosing the recovery mechanism. One new automatic-trigger case is justified
only after the smaller suite passes. Never repeat the old 950K benchmark or the
unchanged four-fact large paste.

The previously failed installer fixture was
`test_quiescent_transaction_with_incomplete_dpkg_audit_retains_inhibitor`:
[run/job](https://github.com/djeZo888/mixed-memory-llm-api-server/actions/runs/36781380288/job/110112205715).
It reported a disposable process fixture deadline and unavailable package
inspection; root cause is unproven. Check current PR checks before deciding
whether a new source repair or one controlled rerun is warranted.

## How the tandem actually works

**Mac-Orchestrator** is the root coordinator. It writes bounded briefs and
interface ownership, dispatches work, reviews actual diffs/evidence and publishes
integration commits. It does not pretend that a local collaboration subagent is
a remote Mac worker.

Actual work is performed in native **Codex CLI sessions** reached through SSH
aliases `mac-worker1` and `mac-worker2`. Each task uses its own directory and
checkout under `/Users/agent/CodexProjects/llm-orchestration/H039-20261001/` on
the assigned Mac. Two independent sessions may run on each Mac. They receive a
minimal brief and links, not the complete long orchestration conversation.

The root sends initial prompts over SSH and writes concise `INBOX.md` follow-ups;
workers read them at bounded phase boundaries and export `OUTBOX.md`. Completed
tasks can receive a specifically addressed `codex exec resume SESSION_ID` task
or a fresh session, never an ambiguous `--last`. Each launch retains actual
session ID, model/effort, PID, deadline, private JSONL events, final message and
native/outer exit receipts. A live PID is not a passing task.

Workers access **ai-vm / 10.156.100.60** for model/runtime storage and lifecycle,
and **ai-harness / 10.156.100.61** for the harness/tool service. Aliases and
protected credentials already exist. Never copy secrets into prompts, Git or
browser responses. Passwordless sudo is authorized but normal files should be
created by the ordinary user; use sudo only for required administrative actions.
Proxmox host access is not assumed; the user runs host-side commands when needed.

Only one named owner changes each shared deployment. Source work and protocol
fixtures can run in parallel; shared inference/GPU loads/deployments cannot be
freely parallelized just because there are spare Mac sessions. Downloads use a
bounded durable VM job and the paid CLI closes instead of waiting. Resume by
reading its actual unit/receipt/manifest, preserving partial artifacts.

Root-local private launch records live under
`/Users/agent/Documents/LLMServer/orchestration/tasks/H039-20261001/`.
Public session metadata appears in the linked JSON; private events and passwords
remain outside Git. Git publication uses mac-worker2's already authenticated
GitHub helper from an isolated repository; credentials are not copied to root.

## New-chat starting brief

> Continue Sova from reports/h039-handoff.md and
> reports/h039-worker-sessions.json on feature/h037-codex-default-ada-image.
> First collect/adopt the existing four bounded Mac worker sessions and vision
> download job; do not launch duplicates. Compaction reliability is priority one.
> Review source/fixtures before coordinated live integration. Technical vision
> preparation runs in parallel. Sova may stay offline; the smaller Ada Qwen may
> be retired. Keep original chats/files/credentials and failed evidence. Root
> orchestrates; mac-worker1 and mac-worker2 implement using GPT 6.1 Sol Ultra.
> Read the future vision and TODO plans. Report actual passes and gaps; creative
> image acceptance and upstream Codex upgrades remain deferred.
