# Pinned local engine

Build from `ai-harness/deploy` after the user completes the reviewed host
bootstrap:

```sh
podman build --pull=always --tag localhost/ai-harness-engine:0.0.1-ae65651df5f9 --file Containerfile .
podman image inspect localhost/ai-harness-engine:0.0.1-ae65651df5f9 --format '{{.Id}}'
```

The PREP build context remains `ai-harness/deploy`. Root's later tools/skills
integration will embed its reviewed assets in the image and must update all
build-context commands, Containerfile COPY paths and related documentation
together. It is not a prerequisite for completing this source-only PREP.

The build starts from official MiniMax source at
`ae65651df5f97ae1085ab4e19964f4b78c769a4e`, applies the two recorded identity-checked patches
under `deploy/patches` (request budgets and ACP compaction notifications), uses its frozen pnpm lock and
official release-packaging script, then installs that source-built runtime
archive. No upstream engine tree is committed here. The final image contains
the runtime bundle, external dependencies and licenses, not the build checkout.
`pins.json` records the registry-verified Node 24 base and external pins.
The official source manifest is version 0.5.1; this harness remains version 0.0.1.

`mcode-tools` 0.0.4 is an external prebuilt artifact extracted from the pinned
public npm `@minimax-ai/code@0.3.11` archive by
`scripts/lib/mcode-tools-artifact.mjs`. Upstream verifies archive SHA-512 and CLI
SHA-256. It retains `embedded/mcode-tools/manifest.json` and
`MCODE_TOOLS_NOTICES.md`; the official package step also retains `LICENSE`,
`NOTICE`, `LICENSE-STATUS.md`, `THIRD_PARTY_NOTICES.md` and dependency licenses.
The media integration is disabled, but its required build artifact and notices
remain unchanged. No claim that this external artifact is source-built.

The base/source and direct supplemental versions are pinned. Apt and additional
transitive resolutions are not a reproducible snapshot. Preserve the built
image ID, `/opt/minimax/package-lock.json`, source pnpm lock, release receipt and
`/usr/local/share/ai-harness-{dpkg.tsv,python.txt,npm.json}` with acceptance evidence.

## Local model and services

The image entrypoint accepts no command overrides. It requires a nonroot UID,
canonical isolated `MINIMAX_DATA_DIR` and `HOME=$MINIMAX_DATA_DIR/home`, plus
`AI_HARNESS_GATEWAY_URL`, `AI_HARNESS_GATEWAY_TOKEN` and
`AI_HARNESS_SESSION_ID`. It writes private `config.yaml` atomically and starts
`node /opt/minimax/cli.js acp` on stdin/stdout. It never prints the token.
The bearer value is a per-runner inference-only gateway token; it is persisted
only in the protected conversation profile and replaced on restart. Backend
revocation must make the old value unusable. No real upstream or lifecycle key
belongs in this profile, image, environment or mount.

Custom provider `harness` uses OpenAI completions at
`http://10.0.2.2:8081/v1`, logical model `qwen3.8-27b`, `limit.context=480000`
and `limit.output=65536`. These are the actual source config keys: the resolver
maps them to contextWindow/maxTokens; unknown custom models otherwise fall
back to 200K/16K. Both `defaultModel` and `defaultLightModel` select
`custom_provider:harness/qwen3.8-27b`. Native child sessions inherit the
selected model; compaction uses that session's resolved provider. Main,
auxiliary and summarizer requests all select the same logical Qwen gateway.
65,536 is the model output ceiling; native title requests keep their smaller
1,000/1,024-token budgets, and native summary output budgeting is unchanged.
Live acceptance must inspect actual requests and verify the main/model ceiling.

The custom selection avoids Token Plan login. These are dedicated unauthenticated
profiles: never import MiniMax account/login state or host home files. Native
media (`beta.mcodeTools=false`), builtin media tools, native managed search,
website publishing, cloud speech, Codex OAuth, prompt auto-updates and telemetry
are disabled. ACP invokes no CLI updater and the launcher makes the image
read-only. Managed connectors have no account credentials: in the pinned source,
their cloud transport rejects `AUTH_REQUIRED` before fetch and their runtime
returns no bindings. This is source evidence, not an egress firewall claim.
Do not log into MiniMax within this local-only profile.

Native delegation remains enabled. Curated PDF/search skills and SearXNG MCP
will be embedded by root's subsequent integration task; no paid native-search
fallback is enabled.
The two shared inference slots are admitted by the host gateway, not by the
container. The profile sets `agentStop.maxActiveSpanMs=0`. The pinned config schema and
parser document and accept zero as disabling its forced producer-active
AgentStop backstop, while retaining natural idle handling. The full pinned
source audit found no consumer beyond config declarations/parser; this is
configuration evidence, not an observed cancellation guarantee. Explicit server
cancellation and separate gateway queue/active budgets remain authoritative.

`beta.browserUseTooling=true` explicitly activates the native Chromium provider.
The native `tools` list filters only `AGENT_BUILTIN_TOOL_IDS`; Browser is added
by the browser capability and is not in that list. Likewise `task` and
`task_append` are feature-owned (`features.delegation=true`), while
`task_query`, `task_output`, `task_stop` are explicitly retained. The browser's
capability-owned `control-in-app-browser` skill is retained independently of
the standalone skill allowlist.

## Request budget patch

`patches/0001-gateway-request-budget.patch` changes two narrowly scoped
source sites. `engine/pins.json` records its SHA-256 and pristine/patched SHA-256
for every affected file. The original upstream extraction remains outside Git.

- `packages/agent-core/src/pi-turn-runner/defaults.ts`: main composed request
  timeout from 20 minutes to 151 minutes (9,060,000 ms).
- `third_party/pi-mono/packages/ai/src/providers/openai-completions.ts`: the
  request-options fallback is also 151 minutes when `options.timeoutMs` is
  absent. Direct `streamSimple`/`completeSimple` summaries otherwise inherit
  the SDK default, bypassing the main wrapper. Cancellation signal and zero
  automatic retry default remain unchanged; explicit options still win.

Native session-title and archive-title constants remain 10,000 ms and 15,000 ms,
respectively. They feed both the SDK option and `AbortSignal.timeout` in
`title-model-completion.ts`; explicit bounded title timeouts override the common
fallback. Their output-token limits remain 1,000/1,024. Title failure stays
nonfatal and cancellation removes queued requests; the portal names chats.
The native `checkpoint-provider.ts` forwards its original cancellation signal
and no explicit shorter timeout; the legacy `generateSummary` implementation
in `third_party/pi-mono/packages/agent/src/harness/compaction/compaction.ts`
uses `completeSimple` without a timeout override. Its original reserve-token
output calculation is preserved. The profile provider timeout is likewise
151 minutes, allowing 120 minutes active + 30 minutes queue + 1 minute transport.
This is a request ceiling, not an overall conversation/tool-execution deadline.

Offline checks (Node 24; pristine extraction required):

```sh
node --test engine/configure-profile.test.mjs
AI_HARNESS_MINIMAX_SOURCE=/absolute/pristine/minimax-code node --test tests/test-provider-patch.mjs
```

The provider fixture verifies patch/source identities and application, executes
the actual request-options expression and native type-stripped title adapter
with a fake stream, and checks the 151-minute default/fallback, exact bounded
native title timeouts and preserved token budgets. It does not wait 151 minutes,
make an SDK/network call or establish live gateway reachability. Profile
success/failure CLI tests assert no token,
environment-derived path or raw filesystem error reaches stdout/stderr.

## Chromium and technical tools

Chromium and `chromium-sandbox` use `/usr/bin/chromium` under the nonroot UID.
The official transport adds its normal headless flags; it only inserts
`--no-sandbox` when UID=0, which this entrypoint refuses. No sandbox-disabling
flag or privilege/capability escalation is configured here. Rootless Podman
must permit the nested Chromium user-namespace sandbox on the actual Ubuntu
kernel/AppArmor/seccomp configuration. After bootstrap, verify actual browser
launch and navigation through MiniMax, and check rootless `unshare -Ur true`.
If Chromium cannot create its sandbox, report the exact failure to root; do not
disable the sandbox, disable AppArmor globally or force a reboot.

Use the launcher's keep-id mapping, read-only root filesystem and writable
profile/workspace, `/tmp`, `/run` and sufficient `/dev/shm`. The private gateway
candidate needs `slirp4netns:allow_host_loopback=true`; verify access to host
loopback 8081 before claiming this path works. No host container socket or
private credentials are mounted. Slirp host-loopback access itself is broader
than port 8081 and must remain documented in deployment review.

The image includes Poppler, English Tesseract, pypdf/pdfplumber/reportlab,
Python virtualenv/pip/pytest/numpy/scipy/pandas/sympy/matplotlib, GCC/Clang,
CMake/Ninja/GDB, Node/npm/TypeScript and Playwright. Playwright reuses system
Chromium with `executablePath: '/usr/bin/chromium'`; downloading a separate
browser is disabled at build time. No Office/CAD/simulator stack is included.
Image input is enabled through the native `modalities.input=["text","image"]`
and `capabilities.support_image=true` schema after root reported both deployed
Qwens passed the separate image probes. These fields are read by native
`capabilitiesFromModelConfig`. This PREP performs no inference; image upload
and final image-file-read routing remain separate live acceptance work.

## Checked evidence and limits

2026-09-22 source inspection: official pinned checkout `package.json`,
`docs/installation.md`, `scripts/build.mjs`, `scripts/package-cli-release.mjs`,
`scripts/lib/mcode-tools-artifact.mjs`, `packages/config/src/{config.ts,byok-config.ts,agent-capabilities.ts}`,
`packages/local-runtime-v2/src/service/model-system/resolution/model-resolver-byok.ts`,
`packages/local-runtime-v2/src/service/plugin-system/{cloud-transport.ts,app/runtime.ts}`,
and `packages/tui/src/runtime/browser/headless-chrome-transport.ts`.
Additional behavior pointers: `packages/tui/src/application/login-gate.ts`
does not require login for a selected BYOK route;
`packages/tui/src/runtime/browser-provider.ts` requires the explicit browser
beta switch; `packages/local-runtime-v2/src/service/turn-system/agent-host/assembly/local-turn-tool-catalog.ts`
separates capability-owned Browser/delegation tools from the native allowlist;
`packages/agent-modules/context-manager/src/manager.ts` passes the current
`input.model` and `input.apiKey` to summary generation.
Registry metadata verified the base digest and supplemental package versions.

Local Node syntax and profile fixture tests cover explicit limits/custom
selection, managed-feature flags, private writes/token replacement, bad gateway
and malformed identity refusal, and unsafe config/home rejection. Shell syntax
checked. The actual image has **not** been built in this PREP subtask; no claim
of installed native modules, container start, model inference, ACP acceptance,
gateway reachability, sandboxed Chromium or PDF/tool acceptance follows from
these source checks. Run those bounded checks after root review/bootstrap.
