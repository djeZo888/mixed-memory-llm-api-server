# H009 — Flash integration completion and ECC policy

Execution: 26 September 2026, 19:52:27–21:52:27 UTC (two hours).
Mac-Orchestrator coordinates/reviews; fresh bounded native Codex sessions on
Mac-Worker1 and Mac-Worker2 implement and test using isolated copies.

## Goal and limits

Qualify the existing GLM-5.3-Flash runtime and make it usable through Sova's
native frontier worker. Qwen remains the main coordinator and preferred coding
and agentic model. Flash is an optional specialist for difficult research,
document analysis and reasoning. This is a routing policy, not a claim that
one model wins every benchmark in those categories.

Keep configured context/cache capacity at 480000, output ceiling65536 and
at least7% free GPU memory at observed peaks. Actual Flash test inputs are
limited to4096 and16384; no64K or larger occupied-context tests. Preserve both
Qwen services, image service, stored conversations, files, credentials and
rollback artifacts. No installer, Proxmox or driver-upgrade work.

## Parallel work

Worker1 owns ai-vm and the Flash inference lane initially:

1. Trace the previous300-second incomplete stream through client, middleware
   and native runtime, retaining partial timings and native phase evidence.
2. Inspect KT thread-pool configuration/code, actual thread affinity and NUMA
   memory placement. Correct the restriction to guest CPUs0–23. Target coverage
   of all64 physical cores using verified guest/host topology; do not assume
   guest CPU numbering maps directly to host CPU numbering. Affinity eligibility,
   actual CPU use and memory bandwidth are distinct measurements.
3. Correct the demonstrated tool-call failure and prove valid automatic tools.
4. Discard a warm-up, then measure fresh4K and16K requests with bounded output,
   correctness checks, timings, RAM/VRAM and CPU telemetry. No blind retries.
5. Hand the Flash lane to Worker2 for native Sova acceptance.

Worker2 owns ai-harness:

1. Reuse the built H008 candidate and fix its acceptance preflight. Avoid another
   layer of task receipt/approval machinery.
2. Verify native profile, provider selection, tools, queue/cancellation and
   separate child context. Preserve uncertain job records; no blind replay.
3. After lane handoff, exercise a real Qwen parent invoking Flash, useful child
   tool execution, and the result returning to the parent. Verify Qwen capacity
   remains available while the child runs.
4. Deploy the qualified candidate, or retain/restore working Sova with explicit
   remaining failures. Readiness alone does not qualify the model.

Routine in-scope fixes, rebuilds/reloads and deployments are authorized. Existing
storage/lifecycle guards remain required. Root reviews bounded source changes
and results; no repeated approval gates for task metadata corrections.

## ECC

Final user decision during execution: keep ECC enabled on the three Blackwells,
but disable it on Ada to retain the qualified Full HD image profile and its 5%
reserve. A second coordinated guest restart is authorized after inference settles.
This decision supersedes the initial uniform-ECC preference below.

Prefer system-level ECC enabled on supported cards for reliability, following
[NVIDIA guidance](https://nvidia.custhelp.com/app/answers/detail/a_id/5873/kw/installation).
On-die ECC is distinct and cannot be toggled by the user. Capture all four GPUs'
current/pending modes and error counters first. Apply supported UUID-scoped
ECC-enable settings, preserving counters, and distinguish active from pending.
Do not reset/reboot during live Flash work solely to make the display uniform.
If activation requires a restart, record it explicitly and coordinate a bounded
maintenance step; no unsupported mode or firmware workarounds.

## Deadline and deliverables

Target backend handoff by20:50, final tests by21:40 and worker receipts by21:45.
Stop starting work that cannot finish before21:52:27. Preserve incremental
results and report missing measurements honestly. Publish reviewed source and
compact evidence in the existing draft PR10; retain raw traces privately.
