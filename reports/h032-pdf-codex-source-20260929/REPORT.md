# H032 PDF-CODEX01 source/build handoff

Source-only implementation complete on mac-worker2. Native worker session `01a0ecf9-f793-79d0-985f-7f482154b73d`, started `2026-09-29T11:43:19.427801Z`, hard end `2026-09-29T12:25:00Z`; source target 12:15 and early checkpoint 11:52 were maxima. Exact packaging time and source commit are recorded in manifests. This worker closes after handoff and does not wait for deployment.

## Cause and correction

The pinned Codex 0.158.0 source, revision `064c6b8c737f5b41d171fdda80bd9ef10ad06eb3`, declares ViewImage stable/default-enabled in `codex-rs/features/src/lib.rs:959-964`. `core/src/tools/spec_plan.rs:1283-1295` registers the tool based on environment plus feature flag, independently of model input modalities. `core/src/tools/handlers/view_image.rs:98-110` rejects execution when image modality is absent. The retained config schema accepts `features.view_image` boolean and root `developer_instructions` string (inserted as a developer role message). PINNED-CAPABILITY-PROOF.json records exact local source hashes/lines and the native binary hash. OpenAI Docs skill applied under the user's explicit local-pinned-first instruction; local evidence was sufficient, so no online documentation fallback was needed.

Both mounted profiles now explicitly set `view_image = false`. Both carry the same general completion instruction: finish requested work/artifacts and provide actual results/paths or concrete failures/blockers. It includes no fixture answers, original prompt, fabricated phase/reasoning tags, retry or rescue logic. Catalog, image modalities, Responses adapter and tool namespace behavior are unchanged. No new vision path is introduced.

Cached native image/label is independently checked from the updated host-mounted policy hash. No image rebuild is needed or performed. Containerfile label is synchronized for a prospective future build only. See DEPLOY-PROPOSAL.md for exact install/pin details and a single later original-PDF rerun.

## Retained-session compatibility and specialist identity

Model/context/protocol remain unchanged, so persisted logical model policy remains v2. The early diff's v3 proposal was corrected before handoff: it would reject existing v2 chats at the router/engine exact-match checks. No history rewrite, migration or broader compatibility was introduced. Separate `toolPolicySha256` now binds future specialist evidence to the changed mounted tool/instruction profile. Missing/old tool-policy evidence fails closed.

The image qualification pin previously used parent layer `dafbccb7...`; it now binds actual native OCI platform manifest `50a3bfd2...`, its identity domain and config digest, retaining parent reference separately. Focused tests compare these fields with existing `configs/runtimes/h005-runtime-binding.json` and reject wrong/parent-only identities. W1 confirms native image/profile unchanged; W1 recovery service/config/source remains separate. No protected qualification/PASS receipt is synthesized.

## Validation

88 focused checks passed, zero skips: 67 server/native/capability/persistence/qualification tests, two broker/engine follow-up tests, 19 fake-Podman launcher tests. The exact hash-pinned native Mac binary reproduces default tool advertisement and unsupported-input error, then verifies both candidate profiles omit view_image, retain exec_command and include the completion instruction. Synthetic provider stop returns native phase null; metadata is not invented. Three fixture native processes exited. All responses are loopback synthetic data, with container-only MCP services disabled in the Mac fixture; this is not a live Linux declaration capture or PDF/model acceptance.

The old-v2 fixture seeds and closes an actual SQLite store with a literal prior v2 profile, original native thread, prior user message and workspace file, then reopens through createApp/broker/router/CodexEngine. Two synthetic turns resume the same thread, preserve original history/file bytes and policy, and never select MiniMax. Old-config specialist receipts fail closed separately.

Host `npm run build` passed using unchanged lockfile and cached dependencies, Node v24.21.0. No web code changed, so no web build was needed. HOST-DIST.tar.gz and BUILD-MANIFEST.json identify all compiled artifacts; no dependencies/binaries/private traces are bundled. Initial new fixture setup errors (HTTP header order and absent synthetic usage frame) were fixed and retained in initial logs; they were not product failures. TESTS.json lists exact focused files/results.

## Original failure remains

Independently verified retained provider, Responses, native and app final strings are exactly equal: 83 UTF-8 bytes, SHA256 `20d7e8d2cd82b8086d0a1162a81cbe9080142d45e2f7b9c75008c438711d9c21`. Eight original provider requests; seven exec successes and one unsupported view_image call. Final provider stop contained no tool delta. The original 702-byte source still matches SHA256 `7cd11f7c4a0369ce2a8f4c57cd375a1149df9e3b593ac22bf3de7e692b42f03e`. No source, oracle or original failure evidence was altered.

H031 PDF remains FAIL: no numeric final and no summary PDF. The configuration fixes the demonstrated unsupported-tool advertisement, and the instruction requests completion; it does not prove why the model stopped or guarantee later completion. No adapter text loss is claimed. Replies.tsx:418-440 includes unclassified text as a response and falls back to the last response when finalMessageId is null; no demonstrated display defect warranted a UI change. Prior corrected render-review attribution stays corrected.

No VM access, live inference, deployment, image/runtime rebuild, model/weights/hardware change, subagent or push occurred. Public maintenance, MiniMax default, image/frontier/candidate gates, histories, historical uncertain owners and quarantines remain outside this source-only task. Next exact step is root review of this packet and coordinated deployment under the separate proposal, then at most one authorized unchanged original-PDF rerun.
