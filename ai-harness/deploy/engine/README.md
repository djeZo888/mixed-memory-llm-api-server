# Pinned local engine

Build with **`ai-harness/` as the context**, from that directory as the ordinary
user after the reviewed host bootstrap:

```sh
podman build --format docker --layers --target runtime --tag localhost/ai-harness-engine:0.0.1-ae65651df5f9 --file deploy/Containerfile .
podman image inspect localhost/ai-harness-engine:0.0.1-ae65651df5f9 --format '{{.Id}}'
```

The `.containerignore` excludes private runtime state and build scratch. The
final `runtime` stage embeds the reviewed tools and six skills, using a digest-pinned
official Python 3.12 slim-bookworm interpreter copied into the same Debian suite.
Its rebuilt venv excludes system-site-packages. Supplemental Python manifests
install with `--require-hashes`; both Node tool lockfiles use
`npm ci --omit=dev --ignore-scripts`. Historical venv/global tools are replaced
in the active final filesystem while their expensive dependency layers stay cached.
`source-base`, `source-deps`, `build`, and `runtime-deps` retain source/package
layers. The isolated `source-deps` stage applies only the two manifest/lock
hunks of pinned `0003`, verifies their original/resulting hashes and installs
with the frozen pnpm lock. Generic ACP/source patches are copied only in the
later `build` stage. It checks pristine nondependency sources and dependency
posthashes separately, applies remaining hunks, checks full patched hashes,
commits deterministically and typechecks/compiles/packages the source. A future
ACP/source patch must rebuild compilation but cannot invalidate pnpm installation.
Patch documentation does not enter either dependency or compilation inputs.
The independent `reviewed-tools` dependency stage also stays cached when native
patches change. Build `runtime-base` only for an explicitly incomplete base-cache check;
all final validation and deployment use `runtime`.

The build starts from official MiniMax source at
`ae65651df5f97ae1085ab4e19964f4b78c769a4e`, applies the recorded identity-checked patches
under `deploy/patches` (request budgets and ACP compaction notifications), uses its coherently patched frozen pnpm lock and
official release-packaging script, then installs that source-built runtime
archive. Upstream packaging requires a clean tree, so the build creates a
deterministic local commit of only the verified patchset before compilation.
`patched-source-revision.txt` and `release.json` retain that derived revision;
the image original-source label remains the pinned upstream revision.
No upstream engine tree is committed here. The final image contains
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

The base/source and supplemental Python/npm lockfiles are pinned. Apt packages
inherit the preserved base build and are not a reproducible repository snapshot.
The PSF license is retained at `/usr/local/share/licenses/python-3.12/LICENSE.txt`. Preserve the built
image ID, `/opt/minimax/package-lock.json`, source pnpm lock, release receipt and
`/usr/local/share/ai-harness-{dpkg.tsv,python.txt,npm.json}` with acceptance evidence.

## Local model and services

The image entrypoint accepts no command overrides. It requires a nonroot UID,
canonical isolated `MINIMAX_DATA_DIR` and `HOME=$MINIMAX_DATA_DIR/home`, plus
`AI_HARNESS_GATEWAY_URL`, `AI_HARNESS_GATEWAY_TOKEN` and
`AI_HARNESS_SESSION_ID`. It writes private `config.yaml` atomically and starts
`node /opt/minimax/cli.js acp` on stdin/stdout. It never prints the token.
The bearer value is a per-runner text/image gateway token; it is persisted
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

The initial permission mode is `default`, external skill ingestion is disabled,
and the supported profile `AGENTS.md` explains two shared inference slots,
independent delegation and queued excess inference. Native delegation remains enabled.
At first initialization, `configure-profile.mjs` copies exactly the six reviewed
skills and MIT license from `/opt/ai-harness/skills` into `${MINIMAX_DATA_DIR}/skills`
through a private staging directory. Reuse requires matching reviewed contents,
owned private directories/files, and no symlinks, hardlinks or additional entries.
The standalone builtin whitelist is `[code-review]`; external skill ingestion is
disabled, and no canonical `configSelection.skills` filter is introduced.
`${MINIMAX_DATA_DIR}/mcp.json` registers the embedded SearXNG and image stdio adapters,
with literal `http://10.0.2.2:8082` (the profile loader does not expand environment
strings). `mcpToolSearch.enabled=false` exposes the reviewed configured search tool
directly. No paid native-search fallback is enabled. The image adapter uses the same
validated session bearer and fixed internal8081 gateway; the protected upstream
key never enters the container. Its MCP timeout is50 minutes. Native main/mavis
and delegated worker roles retain configured MCP, while existing explore/verifier
read-only role ceilings remain unchanged.
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
the standalone skill allowlist. Native `skill` is also retained: it is not in
`AGENT_BUILTIN_TOOL_IDS`, so it is not filtered by `agents.default.tools`.
Adding `skill` would invalidate that whitelist: the strict native parser rejects
it, while the tolerant settings parser discards the invalid tools list.
This follows `packages/config/src/agent-capabilities.ts` and
`packages/local-runtime-v2/src/service/turn-system/agent-host/assembly/local-turn-tool-catalog.ts`
at `ae65651df5f97ae1085ab4e19964f4b78c769a4e`; actual native discovery remains
part of final image validation.

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
node --test deploy/engine/configure-profile.test.mjs
AI_HARNESS_MINIMAX_SOURCE=/absolute/pristine/minimax-code node --test deploy/tests/test-provider-patch.mjs
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


## Runtime-build evidence

The H001-RUNTIME-BUILD task records actual Linux build/smoke results separately
from the historical PREP checks above. `deploy/tests/runtime-smoke.py` uses only
owned local HTTP/HTML fixtures and native ACP initialize/newSession; it never
requests generation. Retain its exact image ID, manifest/notices checks,
Chromium sandbox output, gateway receipt and real container termination result.
Full tools/search/PDF, SERVER/Web, inference/vision, compaction and service
acceptance remain later integration tests.


The actual Podman4.9.3 stock profile blocked Chromium's sandbox `chroot` while
`unshare -Ur` succeeded. The launcher now verifies and applies the scoped
[Chromium seccomp profile](../security/README.md) (relative to deploy): only the
`chroot` syscall changes from capability-conditional to allowed; all other
stock rules remain identical. The outer container keeps `--cap-drop ALL` and
`no-new-privileges`, AppArmor remains enabled, and Chromium retains its own
nested namespace and seccomp sandboxes. This is not a global host policy change.


The launcher mounts the supplied profile directory at the identical absolute
path, then sets `MINIMAX_DATA_DIR=<profile>/state` and
`HOME=<profile>/state/home`. This places native `proper-lockfile`'s sibling
`state.lock` inside the writable isolated mount. The initial leaf-dataDir
layout failed actual ACP startup with `agent_name_conflict_migration_failed:lock`;
no parent-directory mount or native migration bypass is used. Later curated
skills/MCP initialization must target `${MINIMAX_DATA_DIR}/skills` and
`${MINIMAX_DATA_DIR}/mcp.json`, now beneath `state/`. Configuration and global
instructions likewise live at `state/config.yaml` and `state/AGENTS.md`.

The launcher refuses recognized legacy root-level profile files rather than
hiding prior history. Existing profiles require an explicit reviewed migration;
this task exercises new isolated profiles only.


A requested TERM/INT/HUP acknowledges cleanup with launcher exit0 only after
exact owned-container absence is verified. Cleanup failure or uncertainty is125;
unexpected engine failures retain their nonzero status. This transport cleanup
acknowledgment is distinct from the ACP task result and emits no stdout marker.

## Workspace browser downloads

Patch `0006` directs native Chromium downloads into
`<workspace>/downloads/browser/<safeSessionId>/<GUID>`. CDP `allowAndName`
avoids collisions and does not trust suggested filenames. Directory components
and destinations reject symlinks/nonregular or multiply linked files; completed
results expose only checked workspace-relative paths in the native compact
`browser` result. Downloads survive normal session disposal. These checks do not
claim atomic protection against concurrent filesystem mutation by the same user.
The native namespace/seccomp sandbox and launcher mount envelope are unchanged.

`deploy/tests/runtime-smoke.py` runs final locked-tool fixtures, shared-library
closure, the private SearXNG MCP route, native browser DOM/PDF downloads and sandbox,
native skill discovery, and ACP initialize/session-new without a generation turn.
Its `native-probes` bundle is built from the exact patched source with upstream
external/module-resolution rules; it is acceptance tooling, not an added agent tool.
Per-turn and delegated-role execution acceptance remains a later root-gated test.

Podman's explicit `/usr/bin/catatonit` init reaps orphaned tool/browser descendants.
Its host version and SHA256 are recorded in `pins.json`; the managed executable
bind carries no host credentials or data. Native completion bridge `0007` preserves
compaction notifications and exposes schema1 settlement receipts; the server must
use the native contract and verified container cleanup rather than infer settlement
from a prompt or cancel acknowledgement. No generation is needed for initialize,
session-new and never-started settlement inspection.


## Additive image tools (v0.0.3 source preparation)

`tools/image` contains the three reviewed MCP tools: `image_capabilities`,
`image_generate`, and `image_edit`. The separate `image-tools` build stage uses
its pinned SDK/Zod lockfile without invalidating existing native/runtime tool
layers. It is copied into the final `runtime` image. No changes to the pinned
MiniMax source, ACP,480000 context,65536 output or two host text lanes are needed.

The image skill is seeded for main and child sessions. Existing profiles with
exactly the prior five unmodified reviewed skills are upgraded additively after
byte/ownership checks; custom or unsafe profiles still fail closed. The image
adapter receives only the fixed gateway URL and the session bearer in private
`mcp.json`, refreshed with the text config on each startup. No backend key,
host address or client-selected session/run identity is supplied to its tools.

Each tool invocation submits once, never replays an uncertain POST and polls
only the accepted job. Approval returns immediately and is performed by a user
click on the stored browser job. Engine/disconnection cleanup does not cancel
accepted host image jobs; explicit cancellation drains already dispatched work.
Final results contain metadata/artifact IDs and relative workspace paths.

Deployment needs Worker1's reviewed server routes, broker, persistence, SSE,
file/reference validation and approval endpoint together with rebuilt web and
final engine images. Reuse existing session-token lifecycle. Do not run the
image adapter against the image VM directly. Run the extended native `roster`
probe after the combined final image build to check actual main/worker MCP and
all-role skill discovery. The source fixtures and profile tests do not prove
runtime discovery, image API compatibility or live generation/editing quality.
