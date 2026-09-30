# H016 production timeout audit — early confirmed findings

Source/static only. No timer policy changes, inference or host contacts. Started
2026-09-27T15:33:47.542762Z; hard deadline15:53:47.542762Z. Base864d914e.
Session01a0e380-3f3d-7da1-b9c9-742b4811e528. R9 admission17:00/settlement17:25
are experimental job bounds, not the production defaults below.

**Confirmed production generation cap: two hours (7,200 s).** The host gateway
and MiMo private proxy each impose it independently. Queue and token-count
admission have shorter bounds for their own phases. 1,000,000 /61 =16,393 s
(4.55 h) is linear prefill planning only, not a measured million-token prompt.
It exceeds both two-hour caps even before output. No full-prompt claim follows
from allocated context. Remaining native/SDK gaps below can only shorten or
otherwise affect behavior;151 minutes is not a proven end-to-end allowance.

| Layer and exact source anchors | Limit and units | Meaning / effect |
|---|---|---|
| `scripts/runtime/mimo/private_proxy.py:153-168,182-206,223-245` |7,200 s from authenticated route forwarding;15 s downstream POST body socket timeout;5 s downstream response-write socket timeout | Absolute deadline checked during upstream drain. Upstream connect/read socket timeout is remaining deadline at creation and updated while draining. Body read timeout is socket inactivity, not total upload duration. Downstream write failure detaches and keeps draining; timeout/ambiguous terminal quarantines owner. Before HTTP header parsing, no explicit accepted-socket timeout is set in this handler. No retry. |
| Same proxy `:183-191` |Same7,200 s budget for internal input_tokens then generation | Native chat is recounted before generation. A blocking count/getresponse uses socket timeout established at connection creation; not a strict independent watchdog around every operation. Deadline loop cannot run while blocking. Thus proxy absolute deadline is intent/enforced at loop boundaries, with blocking-operation overrun possible. Host active timer is independent. |
| `ai-harness/server/src/gateway.ts:503-532,265-274,1040-1049`; `main.ts:160-187` |30 min (1,800,000 ms) queued;2 h (7,200,000 ms) active; Fastify requestTimeout=0, connectionTimeout=0 | Main supplies no timeout overrides. Queue timer stops waiting before dispatch. Active timer starts at generation transport creation, after queue/count, fails request, destroys upstream sockets and quarantines lane. It is elapsed time, not reset by tokens/SSE pings. It does not prove native GPU stopped. No global queue+count+generation deadline here. |
| `server/src/mimo.ts:279-304`; `mimo-frontier.ts:80-88`; `gateway.ts:815-823` |15,000 ms count envelope (observe/count/read/reobserve); another15,000 ms observer before generation | Absolute AbortSignal budgets; exact MiMo count endpoint `/v1/chat/completions/input_tokens`. `/props` and `/slots` share each observer envelope. These can reject large inputs before generation. |
| `server/src/frontier.ts:211-241` |15,000 ms default | GLM rollback `/tokenize` request and response body, combined with caller abort. Not MiMo generation deadline. |
| `server/src/gateway.ts:700-724,1069-1074` |Client/token abort is event-driven | Queued/counting work cancels. Once generation dispatches, client disconnect/revocation detaches consumer and preserves drain/settlement ownership. No inference replay or automatic lane release from a dropped socket. |
| `ai-harness/deploy/engine/configure-profile.mjs:18,54,65`; `deploy/patches/0001-gateway-request-budget.patch:17-32` |151 min =9,060,000 ms per provider HTTP call; SDK maxRetries defaults0 | Provider profile and stream timeout option, not a whole foreground task deadline. Explicit timeoutMs overrides default. Exact retained patched provider source matches current identity hash (see provenance). SDK internals/stream timeout lifetime not yet independently verified; do not claim timeout covers the entire stream without that check. |
| `deploy/patches/0004-gateway-fetch-timeouts.patch:15-45` and `0005-gateway-dispatcher-type-bridge.patch` |9,060,000 ms headersTimeout and bodyTimeout | Undici dispatch overrides only origin `http://10.0.2.2:8081`, covering frontier path too. Headers wait and body inactivity are transport phases, not whole-task elapsed time; caller signal remains. Exact dependency implementation semantics still to verify locally. |
| Retained MiniMax `packages/agent-core/src/pi-turn-runner/llm-retry.ts:43-47,189-204,274-281,367-371` |Framework defaults5 retries,1,000 ms base/30,000 ms max delay;120,000 ms retry elapsed budget from first failure | SDK retries0 does not mean framework retries0. Host opts into wrapper; exact compiled6641 opt-in/retry eligibility still to confirm. Retry budget checks after failures, not a2-minute watchdog on a successful in-flight generation. Gateway/proxy quarantine must not be bypassed. |
| Retained MiniMax `packages/agent-tools/src/desktop/local-task.ts:15-22,41,64`; `local-task-control.ts:91-97` |Foreground adapter is awaited; task_output wait capped30,000 ms | Task output wait expiry does not stop background child. Background completion schedules parent continuation. Exact foreground adapter/parent/tool runtime cap is still a gap; no unsupported assertion that it is unlimited. |
| `ai-harness/server/src/engine.ts:1338-1378,1438-1459,1476-1502` |No timeout wrapper around prompt at host callsite; cancellation settlement30,000 ms; shutdown ACP5,000/launcher45,000/kill5,000 ms | Prompt return must include exhaustive native receipt and fresh settlement. Cancellation timeout means unknown settlement, not successful cancellation. Underlying ACP SDK behavior remains to verify. Native completion patch `0007-native-completion.patch:387-418,476-485` waits on native evidence;1,000 ms cancellation drain marks unknown when exceeded. |
| `ai-harness/server/src/app.ts:92,528-607`; `web/src/api.ts:101-126`; `web/src/store.ts:115,136-139,278-290` |App requestTimeout30,000 ms;SSE heartbeat15,000 ms;health poll5,000 ms with2,000 ms read bound | Request timeout is HTTP request receipt, not run lifespan. SSE close cleans listener; browser close explicitly never calls cancel. EventSource reconnect/resync detaches/replays UI, not inference. A >1 MiB pending SSE writer is destroyed without canceling run. Browser reconnect delay is browser-owned (not an app constant). |
| `ai-harness/deploy/nginx/ai-harness.conf:6-7,73-74` |7,200 s client body/read/write/send inactivity limits | Socket/inter-read/inter-write limits, not a2-hour run budget.15 s SSE heartbeat prevents healthy idle SSE timeout. Status proxy5 s and admin route30 s are separate observation/admin routes. |
| Retained llama `common/common.h:623-625`; `common/arg.cpp:3548-3554`; `tools/server/server-http.cpp:215-217`; `scripts/runtime/mimo/launch.json:1-84` |Native defaults read/write3,600 s;SSE ping30 s;no --timeout override in retained production argv | Native HTTP read/write limits, not an established one-hour inference deadline. Exact cpp-httplib blocking/handler semantics not recovered yet. Native stream `tools/server/server-context.cpp:4463-4485` treats ping expiry as keepalive, not task termination. Live W1 final argv/env has not been observed in this source-only task. |

Provenance: current harness source at864d914e; compiled MiMo overlay expected
`6641df04cf4e8375029639a67c22da7c3ff4719d2b8e58748572f049de8fb022`.
Retained MiniMax source cache is sibling task
`H008-FRONTIER-20260926/native-source`, based on upstream
`ae65651df5f97ae1085ab4e19964f4b78c769a4e` plus reviewed patches. Its defaults SHA
`1977a0947a4a036adea9e1f5677c41984cea49bfd4f3a6b2a03782510ba074fc` and provider SHA
`ac725f4baa2a923a704b0250165b389f7745139231bf108f3ac3df3a0541e35a` match current
`ai-harness/deploy/patches/identity.json`. Other cached MiniMax file lineage
must be verified before treating it as exact6641 compiled behavior.
Retained llama source: sibling task `H016-DECODE-RESEARCH-20260927/public-source`,
fetch receipts pin`7ac59a6e3ad851cd41af00f678effab0598ba9a8`; runtime imagecdb6efd.
No raw vendor dumps or credentials are included in this report.

## Authorized source delta after early publication

Root subsequently authorized MiMo active8 h (28,800,000 ms), provider8 h31 min
(511 min /30,660,000 ms). This supersedes the initial no-change scope; the table
above is the unchanged864d baseline audit, not a claim that the patch is deployed.
Queue remains30 min; count/observation15 s and Qwen/GLM2 h/151 min stay unchanged.
`gateway.ts:33-35,524,1049` now chooses MiMo active timeout per dispatched request.
`configure-profile.mjs:18-19,55,66` chooses only MiMo's provider budget.
The shared reviewed-origin Undici dispatcher must permit511 min inactivity;
model-specific gateway/SDK limits remain authoritative for Qwen and GLM.

`0011-mimo-request-budget.patch` supplies three exact native source deltas:
model-aware wrapper default in `pi-turn-runner/llm.ts:606-613`; per-call MiMo
framework retries0 in `llm-retry.ts:190-201`; provider511-min timeout/signal and
SDK retries0 plus shared dispatcher511 min in `openai-completions.ts:46,187-203`.
The existing compiled6641 image DOES NOT contain these changes. Native compiled
closure is NOT_BUILT and must be reviewed before a single final overlay. No
native full build, install or model request occurred. Patch application and scaled
SDK stream/transport fixtures pass; these are not deployed long-request proof.
W1 owns the independent production proxy8 h change; local proxy remains7,200 s.
Thus this packet alone does NOT enable8 h end-to-end requests.

## Resolved local-source gaps and remaining boundary

- Retained OpenAI SDK6.26.0 `node_modules/openai/src/client.ts:781-814` starts
  `setTimeout` around fetch and clears it when fetch resolves, normally at
  headers. It is NOT an entire SSE stream deadline. The new MiMo-only combined
  AbortSignal covers response body consumption too. Exact request-options code
  with actual cached SDK and a local80 ms delayed-stream fixture proves abort
  after headers with one physical request. Explicit title overrides still win.
- Retained MiniMax `packages/agent-core/src/pi-turn-runner/turn.ts:139` installs
  the retry wrapper. Baseline SDK retries0 alone did not suppress framework
  retries. `llm.ts`, `llm-retry.ts`, `local-task-runner.ts` match byte-for-byte
  the retained H008 pinned pristine extraction; provider matches current patch
  identity. Prior task H008 RESULT records upstreamae65651. The new MiMo retry
  policy keeps observer/settlement logic but permits no retry; Qwen/GLM unchanged.
- Native foreground `packages/local-runtime/src/api/local-task-runner.ts:122-145`
  forwards parent signal and awaits injected child completion.
  `injected-conversation-task-turn.ts:137-177` waits on accepted completion and
  cancellation failure with no elapsed task timer. `:180-204` cancels the exact
  queued/claimed turn; queue-storage failure does not skip precise abort.
  `local-task.ts:41` background completion resumes the owning conversation;
  `local-task-control.ts:91-97`30 s output read expiry leaves child running.
- Managed profile `configure-profile.mjs:95` sets agentStop.maxActiveSpanMs=0;
  producer-active backstop remains disabled. No timeout policy was added to
  foreground tasks, native completion continuation, bash, MCP or titles.
  Bash120 s default/300 s maximum (`local-pi-tools.ts:584-603`) concerns a Bash
  command, not a native foreground subagent's LLM operation.
- Cached ACP SDK1.3.0 `dist/jsonrpc.js:463-473` returns request.response and
  forwards explicit cancellation; no automatic request timeout is set there.
  Host `engine.ts:1340` supplies no per-prompt timer. Native completion's evidence
  wait persists until terminal proof or cancellation; shutdown/cancellation
  bounds remain distinct and may end the process with settlement UNKNOWN.
- Browser/Nginx timers need no extension for this route: browser sees the app's
  15 s SSE heartbeats. Engine-to-host gateway is direct private HTTP, not Nginx.
  Native llama read/write3,600 s are socket operations;30 s native pings persist.
  Exact vendored cpp-httplib implementation was not in the retained scoped cache;
  no one-hour absolute generation cap is inferred from these socket settings.
- Pending actual proof: W1 proxy8 h hash/argv and16decode/64batch/GOMP0 closure;
  compiled engine bundle/transitive chunk hashes; native actual/props/slots and
  full17/strict/65536/serial/readiness; final root-reviewed selected capacity and
  application acceptance. No4.55 h prompt or8 h deadline was tested.
