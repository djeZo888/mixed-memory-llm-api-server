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
reasoning. Input plus the full requested output reservation must be <= configured
context with the root-frozen native margins; overflow rejects rather than silently
shrinking output. The count includes all template/tool/history/generation-prefix
tokens. SGLang-KT revision `541ddc37cbc92c60dc748db5ff1a2aad0b069a80`
(tp_worker.py267-271, scheduler.py1395, utils.py101) still imposes input <=479993
and input+requested output <=479998 for context/pool480000. Source constants retain
7 input tokens and 2 total tokens of margin. These margins are source-derived,
root-approved; actual native pool/readback and HTTP parity remain activation gates.
Native scheduling separately retains its existing 16K compaction reserve, which
is unrelated to the round test-input ceiling. Native store/cache hints are stripped consistently
from both count and generation payloads. Request content/credentials are not logged
or written into the ownership journal.

Production configured context is **480000** with no permanent 16000 input cap.
The **<=16000 live input ceiling applies only to this round's test harness**.
Largest live input tested by this worker: none (zero inference calls). The supplied
offline tokenizer fixtures have a largest exact rendered input of 212 tokens;
synthetic protocol boundary counts are not measured model occupancy. No effective
480K occupied-context acceptance is claimed. Warm-load/peak-VRAM evidence belongs
to Worker1 and is not inferred from these builds/tests.

Flash initially accepts only text messages and text content blocks. A closed
message grammar rejects OpenAI image_url, image/video/audio/input_audio/file and
unknown nested content before tokenization/inference, without echoing content.
Browser/search/PDF text/OCR and image generation/edit MCP tools remain available;
main Qwen vision is unchanged. Valid pure-text arrays are preserved identically
for count and inference, including user/tool arrays. Worker1 confirmed the pinned
GLM OpenAI-format template emits text parts with no inserted separator; generic
SGLang space-join normalization does not apply. The actual pinned MiniMax provider
capture covers multiple user text parts without a network request. Its reasoning
model system prompt is emitted as `developer`. The pinned GLM template omits that
role, so Worker1 owns identical backend `developer` -> `system` normalization on
both tokenize and inference routes before native processing. Gateway/native role
selection is preserved; backend role parity remains an activation gate. No multimodal
qualification is attempted.

The native v2 patch changes only the model-aware estimator selection in dynamic
output, checkpoint fitting and local compaction footprint. Flash uses UTF-8 sizing
with per-message margin as a **local scheduling heuristic**, not its exact tokenizer
or a proven rendered-template bound. Qwen and other providers keep their original
estimator instance. The exact host admission is authoritative and fails closed if
the heuristic underestimates. Native compaction/continuation fixture evidence is
synthetic and does not establish occupied-model capacity. UTF-8 scheduling can
compact prose 3-5x earlier than actual token capacity; that is a heuristic warning,
not a proven bound. Fixed per-message margins can dominate smaller fixtures.

Complete Worker1 fixture provenance and input bytes are preserved unchanged in
`server/test/fixtures/h008/tokenizer-fixtures.json` (revision, wheel/file hashes,
package versions, rendered-prompt and input-ID hashes). SGLang normalizes JSON
tool-call argument strings into objects before template application. The offline
native probe maps these original wire fixtures to deterministic equivalent Pi
histories and compares actual current native estimates:

| Fixture | Exact count | Dynamic estimate / ratio | Compaction footprint / ratio |
| --- | ---: | ---: | ---: |
| prose | 36 | 438 / 12.17x | 761 / 21.14x |
| multilingual | 42 | 447 / 10.64x | 447 / 10.64x |
| tools_history | 212 | 2041 / 9.63x | 2434 / 11.48x |

These three small fixtures do not prove safety for all inputs, full tokenizer
parity, or effective 480K context. Exact gateway admission remains authoritative.
The HTTP fixture accepts the exact four-field count responses; live backend HTTP
parity remains pending. Existing meaningful native current-v2 compaction and
continuation evidence is preserved without a broader native refactor.

Follow-up TODO: integrate tokenizer-aware native Flash scheduling/compaction
budgeting so large-document use can approach the configured 480K capacity. Keep
exact host admission authoritative and qualify the actual pinned tokenizer/template
and compaction/continuation behavior before replacing the current heuristic.
The small-fixture ratios above are not universal scaling factors; no asynchronous
context-accounting refactor is included in this round.

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
quarantine. The gateway now has an explicit exact `glm-5.3-flash` owner-settlement
path; Qwen/image/generic aliases and passive readiness cannot clear it. The existing
admin wire contract still grants no Flash lifecycle action: the exact settlement
seam requires future reviewed backend owner proof, not a new public bypass. Existing
whole-ai-vm reboot holds also stop new frontier dispatch, without widening the
canonical action/acknowledgement contract or granting new settlement authority.

`/api/sessions/:id/frontier` exposes bounded per-session activity plus aggregate
frontier slot/queue state under the existing same-origin app policy. The UI renders
it separately and never replaces the main 480K Qwen context meter. Native
`engine.ts` retains its root-session notification guard; foreign child usage cannot
overwrite main context. The registry adds passive `glm-5.3-flash` with endpoint ref
`frontier-private`; it confers no new admin action authority. NodeAvailability
consumes canonical `glm-5.3-flash` from the existing Worker1 node-status service,
including durable hardware latches, without inventing a Flash /readiness endpoint.
Missing/down/unknown Flash holds its own admission independently of healthy Qwen.
The snapshot exposes observed availability separately from durable lane state:
idle is not usable-backend evidence. The child UI labels `backend` availability
and `lane` ownership/quarantine separately. Availability is rechecked after asynchronous
counting and before generation, alongside authorization and dispatch holds.

## Deployment, migration and restore plan — not executed

1. Root reviews the exact source/bundle and Worker1's fixed endpoint/tokenizer and
   runtime receipts. Keep both uppers stopped until coordinated integration.
2. Preserve the stopped release, service unit/drop-ins, protected key path metadata,
   databases with SQLite-consistent backups/sidecars, profiles, histories and files.
   Retain the receipt's original release `/opt/ai-harness/releases/63dcb23ebd0b2cb82a295bea78192f3e1a433a6e`.
3. Build the native Linux image using the updated Containerfile and pinned patch
   manifests; run the existing launcher/image identity and actual-container egress
   checks. Round-02 Linux candidate build receipts live in the task parent
   `LINUX-BUILD-02.md/json`; a build is not deployment or inference acceptance.
   Use a unique source-commit candidate tag and immutable image ID for offline
   probes: run-engine.sh still selects the production tag, so do not invoke it
   against this candidate until root authorizes promotion. Preserve production
   image/release/unit/data/secrets. Reuse reviewed rootless layers and verified
   native caches; no host bootstrap or OS update.
4. Provision the protected frontier upstream key through existing host credential
   policy, without placing it in task profiles, images, argv, browsers or Git.
   Append `--frontier-key-file ABS` to the reviewed server ExecStart; an ambient
   environment variable is intentionally scrubbed by the launcher. Session profiles
   still receive only ephemeral session bearers.
5. After accepted backend evidence, set the reviewed `qualified` flag true and install the reviewed server/web/registry/image together,
   and restart only under root integration coordination. No new backend URL flag.
6. Verify real parent->Flash child in foreground and background, research and ordinary
   Qwen coding, cancellation/reconnect/result reuse, tools/MCP, compaction continuation,
   status/UI and missing-Flash isolation. This round live test inputs stay <=16000;
   that ceiling belongs to test dispatch, never production configuration.
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
