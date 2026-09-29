# H030 SPECIAL01 — offline specialist contract review

Reviewed source `64a0693b7a5e925483370870c42cc5c3c010cfab`, 2026-09-29 07:23 UTC.
Read-only source review. No VM/network requests, inference, tests, source edits,
service changes, gate changes or owner reconciliation were performed by this reviewer.
`../INBOX.md` records the W2 ordinary follow-up settlement gap and conditional GO;
the parent worker owns all recovery actions and their live receipts.

## Exact acceptance configuration

Keep the ordinary Codex global gates closed. The reviewed entry point accepts
`codex-preview-main.js <absolute-reviewed-receipt> <output-cap> image-jobs-unqualified <absolute-owned-policy>`;
the cap must be 1..65536, and the entry point always passes
`frontierResponsesQualified=false`. Preserve the deployed cap and service arguments.
Do not use `image-jobs-reviewed` to conduct a temporary acceptance.

The existing protected policy supports this exact shape (placeholders below are
documentation only, not a deployable grant):

```json
{"schema":1,"tickets":[{"id":"<fresh-ticket-uuid>","sessionId":"<exact-session-uuid>","expiresAt":0,"image":false,"frontier":true}]}
```

For an image-only run use `image:true, frontier:false`. Set `expiresAt` to a real
future integer Unix millisecond timestamp no more than 30 minutes away when the
run is accepted. The policy file must be owned by the app UID, a regular one-link
file, private to that UID, and in the protected real directory. Precreate the
ticket directory with the same private ownership. The runtime creates exclusive
`binding.json` and `diagnostics.jsonl`; ticket reuse, changed ticket, expiry,
restart rebinding and a changed active run fail closed. `closed.json` explicitly
does **not** claim specialist settlement. Each follow-up run requires a fresh
exact ticket if it needs specialist permission. No secret belongs in the policy.
Anchors: `server/src/codex-preview-main.ts:4`, `owned-acceptance.ts:8`, `:18`,
`:53`, `:74` (all source anchors below relative to `ai-harness/`).

Image reference staging can use the unused exact image ticket before a run UUID
exists; staging alone never permits execution. The host chooses
`config-image-jobs.toml` for a launch with active image acceptance, exposing
`image_capabilities`, `image_generate`, `image_edit`; ordinary configuration only
exposes capabilities. This launch-time choice must actually be present in the
acceptance runner; a previously warm runner with capabilities-only configuration
is not proved to have gained image tools by creating a later ticket.
Anchors: `server/src/codex-host.ts:40`, `:45`,
`deploy/run-codex.sh:34`, `:42`, `deploy/codex/config.toml:45`,
`deploy/codex/config-image-jobs.toml:45`.

## MiMo provider and delegation

The existing reviewed contract is:

| Field | Required value |
|---|---|
| Model | `mimo-v2.6-pro-rl` |
| Provider / wire | `sova` / Responses through existing shared gateway |
| Configured/allocated context | 950000; no full occupied-context claim |
| Maximum output / auto-compaction limit | 65536 / 880000 |
| Reasoning | `mimo-plaintext`; preserve actual continuation reasoning |
| Tool policy | explicit serial emission (`parallelToolCalls=false`) |
| Token accounting | `mimo-native-input-tokens`; complete rendered input + reserved output |
| Private upstream | existing `http://10.156.100.60:30012/v1` |
| Native capacity | one slot, `id=0`, `n_ctx=950000`, no speculation |

Qwen remains root/routine child model; child policy remains maximum four threads,
depth one, default `qwen3.8-27b`. Deliberate MiMo child must retain parent ancestry,
provider `sova`, exact model and immutable model binding. Temporary frontier
acceptance makes MiMo a permitted child model but does not globally advertise
frontier as qualified. No Ada routing change is implicated.
Anchors: `server/src/codex-provider.ts:13`, `codex-host.ts:43`,
`codex-children.ts:42`, `:95`, `:107`, `deploy/codex/config.toml:53`.

Do not install the repository's raw `config/active-frontier.json` or
`config/mimo-candidate.json` during recovery: these remain disabled source
templates (GLM selected / MiMo disabled), not observations of deployed state.
The existing deployment must retain selected MiMo and its reviewed
`/etc/sova-qualification/mimo.json` SHA binding. `loadActiveFrontier` requires
enabled+qualified candidate, exact receipt digest, matching 950000/65536 profile,
full-17-tool roster, strict nested schemas and serial-completion qualification.
Receipt ancestry is root-owned, non-writable and symlink-free. A rejected MiMo
selection stays MiMo unavailable; it is not silently replaced with GLM.
Anchors: `server/src/active-frontier.ts:14`, `:26`,
`mimo-frontier.ts:42`, `:97`, `main.ts:184`.

Fresh readiness is separate. `createCurrentMimoProvider` obtains a fresh
canonical `boot_id:generation` stamp and substitutes only ephemeral
server-instance/generation receipt fields. It requires canonical MiMo ready,
availability available, hardware latch false, exact deployment/profile/output
and GPU UUID; then matches native props/slots to immutable build/model/template
pins. It rechecks the same stamp around native observation, counting, dispatch
and terminal drain. Changed generation or boot refuses the request rather than
replaying it. Loading/ready transitions may change the stamp; W2 must obtain a
fresh capsule after load and must not reuse one held across recovery.
Anchors: `server/src/mimo-current-owner.ts:12`, `:29`, `:36`,
`mimo-frontier.ts:68`, `gateway.ts:939`, `:1160`.

## Queues and settlement

MiMo has its own one-lane admission, at most eight queued requests, 128 MiB queue
body bound and existing 30-minute queue timeout. Existing per-dispatched-request
budget is eight hours; this is not authorization to cross H030 deadlines or
change the budget. Its durable lane uses the existing frontier storage key;
retained active/quarantined ownership blocks admission across restart/provider
changes. A descriptor or fresh readiness cannot clear history or ownership.
Anchors: `server/src/gateway.ts:37`, `:540`, `:556`, `:1299`.

Parent inference slots should be observed released when it waits for a specialist.
The gateway retains MiMo tool fragments until complete SSE/HTTP and unchanged
owner validation, then settles native work **before** delivering the tool result.
Disconnected consumers drain with bounded capture; no automatic replay. Capture
request IDs, canonical request hash, token count, receipt hash, server instance /
generation, backend response ID, child terminal events and final durable owners.
Native tool completion alone does not prove a child terminal or image settlement.
Anchors: `server/src/gateway.ts:783`, `:817`, `:953`, `:1158`,
`codex-children.ts:58`, `:154`.

Image broker owns a separate durable single lane (one active/eight queued);
it neither acquires nor releases text slots. Normal owner settlement and current
readiness are needed to reconcile prior uncertainty; never edit lane rows or
delete historical image records. Required live readback is `ready=true`,
`admitting=true`, `busy=false`, plus canonical availability and profile capability
match. Keep active/unknown job ownership when the native text turn ends.
Anchors: `server/src/image-broker.ts:153`, `:336`, `:984`,
`image-upstream.ts:170`.

## Full HD image acceptance requirements

- Model stays `qwen-image-2.1`; generation defaults to public `1920x1080`, zero
  references. Use the exact currently advertised, SHA-qualified operation/size/
  reference-count profiles. The public codec rejects dimensions above
  1920x1080; do not substitute internal 1920x1088 canvas dimensions.
- Edits use one or two owned references only when that profile is advertised;
  retain original bytes and hashes. Geometry normalization or canvas changes
  remain subject to the existing user approval card, not model/tool approval.
- New seeds must differ from known source/ancestor seeds; omitting the seed lets
  the broker choose and persist a fresh one. Same accepted job is retrieved,
  never regenerated for display or validation.
- Record raw capability/tool arguments, translated request, MCP result and
  continuation. Preserve malformed `__ns`, `ns`, `__v` evidence; no stripping or
  silent altered-prompt rescue. Ordinary generation, follow-up edit and one
  child path each need actual artifact/preview/download inspection and distinct
  native/text/image owner settlement evidence.

Anchors: `server/src/image-codec.ts:10`, `image-upstream.ts:136`,
`image-broker.ts:450`, `:479`, `:505`, `tools/image/image-mcp.mjs:25`.

## Focused test candidates and honest acceptance status

No tests were run in this review. If implementation changes require validation,
the following existing fixtures provide relevant targeted coverage; select the
specific changed contract rather than running a broad suite:

- Pure fixture candidates: `server/test/mimo-current-owner.test.ts` owner stamp
  and generation-change cases (exclude its local HTTP transport case when a
  strict no-network test mode is required); `codex-current-owner.test.ts`
  deliberate MiMo child/model-policy case; `codex-children.test.ts` bounds,
  foreign ancestry and late/overlapping terminal cases.
- Translation-only cases in `codex-mimo-native.test.ts` preserve reasoning and
  historical tool-call identities while rejecting second newly emitted tool;
  its pinned-native case is separately gated by `CODEX_NATIVE_FIXTURE_BINARY`
  and launches a local fake server, so must not be misreported as live MiMo.
- Service-fixture candidates for W2's authorized test environment:
  `mimo-codex-gateway.test.ts` serial admission/count and retained drain;
  `codex-specialist-upload.test.ts` closed global gate/exact ticket/replay;
  `image-broker.test.ts` queue, fresh seeds, approval, unknown completion and
  exact owner reconciliation. These are not actual specialist workflow passes.

For this task, actual Codex MiMo tool/delegation and Full HD generation/edit/child
acceptance remain **NOT_TESTED by this reviewer**. Root/W2 schedule protected
acceptance only after lifecycle launch transitions are settled, current native
readiness/identity is verified, historical holds remain respected, and ordinary
tool/follow-up prerequisites are accepted. Loading itself is not readiness;
950000 remains configured capacity, not a passed occupied-context test.
