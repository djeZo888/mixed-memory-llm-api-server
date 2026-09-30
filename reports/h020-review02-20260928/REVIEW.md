# H020 REVIEW02 — exact status candidate

**PASS: source and local synthetic contract checks** for declared W2 source `739462b7e246f92a3c4161c4535a1a2d8a0886f2`. This is not deployment GO or a production-readiness claim.

Full patch SHA256 `fe301953a4e20903a46516b78e70c8b754bbc2308ab7b003004a212ccc972191` was independently verified, applied to a separate detached checkout at base `e256814c6f2b9cc421ba68cde3febd1e0a6c9aa8`, and all eight resulting source hashes matched the supplied manifest. The source commit ID is W2's declared pin; the locally reviewed tree is its verified full-patch reconstruction. Initial `4e05c1b70cede85a1374360abc3170516b2775d9` was preserved separately and is not approved. No implementation was applied to this report branch.

## Checks and findings

- Corrected candidate: **19 focused tests + 6 inherited independent fixtures + 6 new independent fixtures passed**, with no failures. `tsc --noEmit` from `src/status-main.ts` passed; `git diff --check` passed. Exact commands, exit codes and complete outputs are adjacent JSON/TAP files. Only trailing whitespace in the initial failure report copy was normalized; its untouched original and both hashes are recorded in raw-output-preservation.json.
- Inherited fixtures were copied to the same relative report location in each isolated candidate so their imports resolve candidate source. Prior REVIEW01 results were treated as baseline only.
- New review fixtures reproduce root-known behavior on initial source (3 pass, 3 fail) and pass all six checks on corrected source. Initial failure output is retained. These are confirmation of root's findings, not new independent discoveries.
- Registry labels are preserved without display-name conditionals. Configured model, instance, host, endpoint and selection stay separate from observed alias, service/node, deployment and readiness. Missing observations have null observed identities. Unknown selection, missing/wrong alias and stale/unavailable evidence cannot certify model readiness.
- Root's endpoint correction is present at `ai-harness/docs/status-registry.md:156`: GLM `30010/v1`, MiMo `30012/v1`. These match unchanged local fixed workload clients. Qwen expected aliases match `gateway.ts:98-99` and `backend-readiness.ts:7-14`. Registry endpoint references remain descriptive; the documentation does not claim universal routing ownership.
- Corrected `status-projection.ts:69-75` requires projected `s.ready === true` for GPU ready dependencies. Both-frontiers-ready and unknown-selection cases pass. Dormant native `ready=true` is retained in `observed_model.ready`, with separate `selection_conflict`; it does not enter ready dependencies. GPU telemetry freshness is independent, joins use exact UUIDs, and required UUIDs never synthesize hardware rows or imply process occupancy. Existing action-impact IDs remain unchanged.
- Unsupported nodes and distinct instances remain visible. Configured node order and GPU indices are not used as identity fallbacks. Fresh service plus stale GPU produces no ready GPU join without falsifying service readiness.
- Public metadata is explicitly allowlisted by registry validation and native sanitization. Synthetic credential/transport sentinels do not enter JSON. UI uses textContent, projected readiness, separate observed identity and conflict labels. No generic registry/transport/credential object is serialized.
- Native `configured_context_tokens` and `max_output_tokens` retain their existing observed-service meaning and observation envelope, including under alias mismatch; missing values stay null. They are not populated from configuration or deployment-name suffixes. The UI currently does not display model capacity; this review does not claim that it does.
- Seven fixed action-service identities, node/observation pins, confirmations, action security, operation flow, queues, dispatch freeze and credential/transport clients remain unchanged. Byte-equal boundary file hashes are recorded in REVIEW.json. Existing focused authority assertions run through the corrected service-count test successfully.

No new source blocker was found.

## Deployment evidence boundary

The supplied manifest lists a status overlay: registry, three JS files, three declarations, plus identical inherited selection bytes. It declares preserved deployed MiMo selection SHA256 `6fac2925b81e0c40154635643a327f8f3149f7211cf8b78a4f321f6d5b09dc22`, not the repository GLM default. This is a W2 report; Worker1 did not read staged/live bytes.

Initial staging metadata differed; the final 04:17 delivery reconciles the source release and drop-in SHA to `1dd0a243708343390e41ecb127728bce18f1c043461fc76ac622132409006d78`. Superseded metadata remains preserved. Exact drop-in and activation script were read and hashed. `sh -n` passed; nothing was executed.

The drop-in changes only status WorkingDirectory/ExecStart to this release's `status-main.js`. The prepared script checks status PID, app inactive state, loaded status directory, absent target drop-in, every overlay hash and both old/new deployed selection hashes before installing the exact drop-in, daemon-reload and restarting only `ai-harness-status.service`. No workload or credential mutation is present. **Static procedure review PASS.** Root retains deployment GO; W2 owns activation and passive post-activation verification. Worker1 has not independently read compiled overlays or actual staged/live bytes. W2 process-trace evidence remains outside Git and is not replayed as fresh status.

Worker1 performed no live VM/ai-harness/status reads, inference, benchmark polling, deployment/restart, installation/build, model/provider/hardware/credential changes, GitHub push, Codex research or application400 investigation. W2's synthetic Chrome desktop/mobile/admin PASS remains attributed evidence, not an independently rerun browser result. Historical private DTOs were not copied into Git.
