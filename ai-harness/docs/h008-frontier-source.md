# H008 native frontier source candidate

This change adds one native MiniMax custom child `frontier` beside the unchanged
Qwen coordinator/ordinary worker and two Qwen inference lanes. It does not activate
services. The H008 worker stopped `ai-harness.service` and
`ai-harness-searxng.service` on ai-harness; root integration alone may restore them.
The task parent holds the before/after receipt, exact restore command and test logs.
Status/admin/nginx/egress were left running. No ai-vm contact was made by this worker.

## Native routing and ownership

The pinned source is MiniMax `ae65651df5f97ae1085ab4e19964f4b78c769a4e`
(version 0.5.1), with the reviewed 0001..0009 patches and new
`0010-frontier-model-accounting.patch`. All patch and affected-file identities,
the Containerfile admission hash, and launcher pin are synchronized.
The existing 151-minute gateway-origin HTTP timeout patch applies unchanged to
`http://10.0.2.2:8081/frontier/v1` because it matches the same origin.

The private per-session profile seeds `agents/frontier/agent.md`, which uses
`custom_provider:frontier/glm-5.3-flash`, high effort, configured context 480000 and
output ceiling 65536. Native `task(agent_name=frontier)` resolves the target model
before parent inheritance and resets the model budget. Explicit task model
overrides retain the native higher priority. No `agents.frontier.features` field
is invented. Tools, MCP and skills inherit the approved inventory; `task` and
`task_append` are denied for frontier. Existing custom-file conflicts fail rather
than being overwritten. Existing AGENTS.md text is preserved and the routing policy
is appended once; histories and frozen task bindings are not rewritten.

Qwen remains the default for coding, agentic work and coordination. Frontier is
selective deep research, multi-document analysis, hard reasoning or independent
diagnosis. Exceptional stuck coding requires a justification and Qwen verification.
Native foreground/background ownership, cancellation and result reuse remain in
charge. Both children share a workspace; code writes must be foreground or have
explicit disjoint ownership. There is no blanket superiority claim.

## Fixed host contract and admission

The gateway accepts only the fixed model at `/frontier/v1/chat/completions`.
The upstream is fixed `http://10.156.100.60:30010/v1`; no client URL, provider,
model, template or host credential injection is accepted. Native session bearer
identifies the parent session; the host reads its separate protected upstream key
lazily from `AI_HARNESS_FRONTIER_KEY_FILE` (the scrubbed server launcher accepts
`--frontier-key-file ABS` and passes only the path). Missing configuration/key/counting
isolates frontier and does not stop Qwen startup or change image routing.

`config/frontier.json` remains `qualified:false` in this source candidate.
Root must review backend evidence and explicitly enable it during coordinated
activation. The frozen weight/tokenizer/template repository revision is
`eb9eb208eb0d988989d07a6a12d0fdeb5f52574a`. Authenticated POST `/v1/tokenize`
takes the same complete normalized inference payload, including all messages,
tools and history. It must return:

```json
{"count": 123, "tokenizer_revision": "eb9eb208eb0d988989d07a6a12d0fdeb5f52574a", "template_revision": "eb9eb208eb0d988989d07a6a12d0fdeb5f52574a", "context_limit": 480000}
```

The count must represent the actual rendered prompt, tools and generation prefix;
it excludes future output. Every call, including child compaction, is counted.
The host checks exact identities/capacity, integer bounds, a 15-second timeout and
16KiB response limit. The gateway normalizes `reasoning_effort=high` and
`chat_template_kwargs.clear_thinking=true`; output is at most 65536 inclusive of
reasoning and is reduced to remaining context if needed. Errors or zero output
room reject before inference. Native store/cache hints are stripped consistently
from both count and generation payloads. Request content/credentials are not logged
or written into the ownership journal.

The root-frozen round boundary is configured **480000**, with **actual live
rendered inputs limited to 16000**. This is an explicit acceptance restriction,
not evidence of a model product limit or full occupied-context qualification.
The host enforces `maxPromptTokens:16000` for this candidate. A later qualification
change must be reviewed as source config; increasing context occupancy is not part
of this handoff. Warm-load/peak-VRAM evidence belongs to Worker1 and is not inferred
from this worker's build/tests.

The native v2 patch changes only the model-aware estimator selection in dynamic
output, checkpoint fitting and local compaction footprint. Flash uses UTF-8 sizing
with per-message margin as a **local scheduling heuristic**, not its exact tokenizer
or a proven rendered-template bound. Qwen and other providers keep their original
estimator instance. The exact host admission is authoritative and fails closed if
the heuristic underestimates. Native compaction/continuation fixture evidence is
synthetic and does not establish occupied-model capacity.

## Queue, durable ownership and status

Frontier has one separate inference slot, FIFO queue of eight, 30-minute queue
wait and 128MiB aggregate queue-body budget. Existing Qwen limits and exact-two
model restrictions remain. Each completed HTTP request releases its slot before
parent task waiting; no Qwen slot is reserved on behalf of frontier. Queue disconnect
or session-token revocation cancels immediately. Dispatched client cancellation
retains upstream drain. A complete response (SSE requires `[DONE]`) confirms
settlement; interrupted/ambiguous responses quarantine the frontier slot and are
never replayed. No unreviewed backend cancellation endpoint is assumed.

The existing protected `harness.sqlite` gains an additive `frontier_requests`
table/index containing only request ID, parent owner, fixed model, state, capacity,
counts and timestamp. Queued records recover cancelled; active records recover
quarantined. The existing `gateway_lanes` ledger persists frontier occupancy before
dispatch. There is deliberately no frontier administrative settlement action:
backend owner proof and a reviewed reconciliation procedure are required to recover
quarantine. The Qwen-only reconciliation function cannot clear frontier uncertainty. Existing
whole-ai-vm reboot holds also stop new frontier dispatch, without widening the
canonical action/acknowledgement contract or granting new settlement authority.

`/api/sessions/:id/frontier` exposes bounded per-session activity plus aggregate
frontier slot/queue state under the existing same-origin app policy. The UI renders
it separately and never replaces the main 480K Qwen context meter. Native
`engine.ts` retains its root-session notification guard; foreign child usage cannot
overwrite main context. The registry adds passive `glm-5.3-flash` with endpoint ref
`frontier-private`; it confers no new admin action authority.

## Deployment, migration and restore plan — not executed

1. Root reviews the exact source/bundle and Worker1's fixed endpoint/tokenizer and
   runtime receipts. Keep both uppers stopped until coordinated integration.
2. Preserve the stopped release, service unit/drop-ins, protected key path metadata,
   databases with SQLite-consistent backups/sidecars, profiles, histories and files.
   Retain the receipt's original release `/opt/ai-harness/releases/63dcb23ebd0b2cb82a295bea78192f3e1a433a6e`.
3. Build the native Linux image using the updated Containerfile and pinned patch
   manifests; run the existing launcher/image identity and actual-container egress
   checks. This worker ran a macOS native build, not the Linux image build.
4. Provision the protected frontier upstream key through existing host credential
   policy, without placing it in task profiles, images, argv, browsers or Git.
   Append `--frontier-key-file ABS` to the reviewed server ExecStart; an ambient
   environment variable is intentionally scrubbed by the launcher. Session profiles
   still receive only ephemeral session bearers.
5. After accepted backend evidence, set the reviewed `qualified` flag true, retain
   the 16000 input boundary, install the reviewed server/web/registry/image together,
   and restart only under root integration coordination. No new backend URL flag.
6. Verify real parent->Flash child in foreground and background, research and ordinary
   Qwen coding, cancellation/reconnect/result reuse, tools/MCP, compaction continuation,
   status/UI and missing-Flash isolation. All actual Flash inputs remain <=16000.
7. Restore upper service availability only on root instruction:
   `ssh ai-harness systemctl --user start ai-harness-searxng.service ai-harness.service`.
   Source activation and these starts were not performed here.

For rollback, first stop upper dispatch and obtain backend settlement for active or
quarantined frontier requests. Disabling `qualified` stops new frontier admission
without changing Qwen/image. Restore the reviewed prior release/image/unit source
as a coordinated set, preserve the additive tables and all histories/profiles, and
retain frontier journal evidence. Do not clear a lane merely because the harness
restarted or health looks ready. Preserve/rename managed frontier agent files through
an explicitly reviewed profile migration; do not delete user-customized files or
rewrite historic bindings. Existing Qwen model profile and image runtime recovery
remain unchanged. The stop receipt's exact restore command restores service intent,
not proof of a new candidate's acceptance.

## Local evidence and remaining gates

The task parent RESULT records exact commands, hashes and counts. Tests exercise
actual pinned native custom parsing/rendering/fresh task capture/provider payloads,
current v2 compaction and continuation with fake generation, actual SQLite recovery,
local HTTP queue/drain/accounting fixtures, existing Qwen/image regressions and
synthetic UI. No live parent->Flash child, backend count equivalence, real coding or
research acceptance, Linux deployment/namespace controls, or full occupied context
was tested. Those require root/backend coordination. Installer, unrelated services,
ai-vm mutations, GitHub pushes and upper restart remain outside this source work.
