# Pinned local OpenCode client

V0 provides the reusable **client component** for the fresh Linux installer.
Tools run on the client machine in an explicitly selected user workspace. The
inference VM supplies an OpenAI-compatible API. V0 made no SSH connection, VM
change, inference request, Docker installation, or clean Linux installation.
See the [V0 report](../reports/v0-client-bootstrap.md) for measured results and
[A1 client acceptance](agent-client.md) for the separate protocol harness.

## Pin and prerequisites

The pin is **`opencode-ai@1.18.31`**, published 2026-09-14, verified against the
[official installation documentation](https://opencode.ai/docs/#install),
[npm release metadata](https://registry.npmjs.org/opencode-ai/1.18.31), and
[official release](https://github.com/anomalyco/opencode/releases/tag/v1.18.31).
The official tag resolves to `014614d35b397775e5d397a490fc72368c894ec2`.

The full installer must provision these prerequisites before this helper:

- Python **3.10+**, standard library only; Ubuntu 24.04 target is Python 3.12.
- Node **24.x, at least 24.15.0**, and npm **10+** on `PATH`. Worker execution
  used Node **24.21.0**, npm **11.19.0**, and Python **3.14.7**. This is the
  bootstrap's supported range, not an upstream OpenCode engines claim: the
  OpenCode wrapper declares no engines; locked `ini@7.0.0` requires a recent
  Node release. The exact lock was tested with the worker versions only.
- macOS arm64/x64 or glibc Linux arm64/x64. The x64 client selects the upstream
  baseline binary, avoiding an AVX2 assumption. Linux runtime execution remains
  NOT_TESTED in V0. Windows/musl are outside this helper's supported targets.
- Outbound HTTPS to `registry.npmjs.org` for installation and CA certificates.
  No sudo, global npm install, compiler, Bun installation, GPU package, Docker,
  or model weights are required. Provision Git and project-specific test tools
  separately for agent work.

[`package.json`](../scripts/client/package.json) pins OpenCode and
`@opencode-ai/plugin` to 1.18.31; the committed
[`package-lock.json`](../scripts/client/package-lock.json) locks all 45 package
entries and their registry SHA-512 integrities. The plugin dependency is real:
this OpenCode release otherwise installs it during config loading, even with
external plugins disabled. Installing it in the private config directory makes
startup reuse the locked dependency tree.

The helper uses local `npm ci --ignore-scripts --no-audit --no-fund
--include=optional`. It invokes the official native package binary directly,
so the wrapper's postinstall cannot trigger fallback package installations.
Other lifecycle scripts are also skipped; no build occurs. The wrapper's
`node_modules/.bin/opencode` placeholder is intentionally unused. Invoke the
generated launcher below.

## Install or plan

Run from the repository root. Choose an existing parent directory and a new,
private, dedicated prefix. Do not put it in the repository. These placeholders
must come from the runtime handoff; there are no model or endpoint defaults:

```sh
export CLIENT_PREFIX='/absolute/private/client-prefix'
export CLIENT_WORKSPACE='/absolute/user/workspace'
export CLIENT_API_BASE='http://127.0.0.1:30002/v1'
export CLIENT_MODEL='REPLACE_WITH_EXACT_PUBLISHED_API_MODEL_ID'
export CLIENT_CONTEXT='REPLACE_WITH_PUBLISHED_CONTEXT_LIMIT'
export CLIENT_OUTPUT='REPLACE_WITH_AGREED_OUTPUT_LIMIT'
export CLIENT_KEY_FILE='/absolute/private/llm-api-key'

python3 scripts/client/bootstrap.py --help
python3 scripts/client/bootstrap.py \
  --prefix "$CLIENT_PREFIX" --base-url "$CLIENT_API_BASE" --model "$CLIENT_MODEL" \
  --context-tokens "$CLIENT_CONTEXT" --output-tokens "$CLIENT_OUTPUT" \
  --api-key-file "$CLIENT_KEY_FILE" --dry-run
```

Repeat the final command without `--dry-run` to install. The dry run validates
inputs and existing managed state without writes, network, subprocesses, or
opening the key reference. The prefix's parent must already exist. An existing
prefix must be owned by the current user with mode 0700, and empty or an
identical completed installation. Repeating the identical install verifies the
manifests, launcher, settings, package versions and real CLI version without
reinstalling packages. A failed/incomplete install is retained for review and
refused on retry; choose a fresh prefix after diagnosing it. The helper never
recursively deletes or overwrites an unrelated directory.

Use **one** authentication mode:

- `--api-key-file "$CLIENT_KEY_FILE"`: records only the absolute path reference;
  the file may be nonexistent during bootstrap and config checks. At real
  launch, require an owned private regular file without symlinks/hard links,
  a mode-0700 parent, and 1–8192 printable ASCII bytes (33–126) with **no newline**.
- `--api-key-env LLM_API_KEY`: records the variable **name**; securely supply its
  value through the calling environment for real launch. Never put the value
  on a command line, in a report or committed `.env`. No variable is needed for
  version/help/check/plan commands.
- `--auth-disabled`: explicitly omits the provider API key. Use only when the
  operator has published disabled authentication for this localhost endpoint.
  It does not prove authenticated access.

Private file bytes are never trimmed or rewritten. The launcher rejects
whitespace instead of silently fixing it. It JSON-escapes the accepted bytes
and opening braces into a dedicated child-only environment reference. This is
necessary because 1.18.31's config interpolation expands environment text
before JSON parsing and file substitutions. It preserves quotes, backslashes
and literal `{file:...}` text without reading the named file. The generated
config contains only `{env:V0_LOCAL_API_KEY_JSON}`, never a secret value.
See the pinned [variable implementation](https://github.com/anomalyco/opencode/blob/v1.18.31/packages/opencode/src/config/variable.ts).

Use A1's [protected key entry procedure](agent-client.md#protected-key-file)
during coordinated V1. V0 used a nonexistent local reference and did not fetch
the VM key.

## Optional explicit reasoning effort (A2O / Q38C)

Add **`--reasoning-effort none`** or **`--reasoning-effort low`** when the backend
handoff requires it. Only those exact strings are accepted; `none` is an explicit
selection, distinct from omission. Omitting the option preserves V0's generated
configuration and manifest shape.
It does not assign an effort default to every model or expose a token budget.

The optional manifest field is `bootstrap.json` → `reasoning_effort`.
The generated model option is
`provider.local.models[exact_model_id].options.reasoningEffort`, using the same
selected literal `none` or `low`.
OpenCode **1.18.31**, with bundled `@ai-sdk/openai-compatible` **2.0.41**, maps
that option to request **top-level `reasoning_effort`**, with that exact value. See the
[pinned primary-source review](../reports/a2o-provider-source.md) and
[actual-process synthetic wire evidence](../reports/a2o-opencode-reasoning.md).

The dry-run JSON includes `reasoning_effort` only when selected. An identical
bootstrap verifies the manifest, generated config and installed helper; changing
between omitted, `none` and `low` requires a **new private prefix**. Never hand-edit
installed config/manifest files. This is a bootstrap setting; the launcher has
no effort override. Existing V0 installations remain usable with their copied
V0 launcher; rerunning changed helper source against them requires a new prefix,
as before.

For the reviewed D3 GLM handoff, V1's initial selection is exact model
`glm-5.3`, context **32768**, output **2048**, and **`--reasoning-effort low`**.
Keep the endpoint and protected key reference from the operator handoff. These
are that service's initial values, not defaults for other models. Root must
review A2O before V1 creates its new config. Actual GLM read/edit/test acceptance
and continuation remain V1 work; A1's reasoning replay policy is unchanged.

For the reviewed Q38 fast-no-thinking profile, use exact model `qwen3.8-27b`
and **`--reasoning-effort none`**, with limits from the authorized runtime handoff.
Pinned SGLang **0.5.19** maps that top-level value to false thinking switches;
the reviewed server also supplies `--default-chat-template-kwargs
'{"enable_thinking":false}'`. No per-request template field is required for this
exact combination. The client adds no arbitrary body fields. See the
[Q38C source proof and actual CLI wire report](../reports/q38c-client-none.md).
This proof does not qualify native Q38 formatting, thinking behavior or live
agent quality; those remain **NOT_TESTED by Q38C**, pending Worker1/V1 gates.
Do not silently reuse GLM's `low` selection for Q38.

## Launcher and local provider

```sh
"$CLIENT_PREFIX/bin/opencode-client" --help
"$CLIENT_PREFIX/bin/opencode-client" --workspace "$CLIENT_WORKSPACE" version
"$CLIENT_PREFIX/bin/opencode-client" --workspace "$CLIENT_WORKSPACE" help
"$CLIENT_PREFIX/bin/opencode-client" --workspace "$CLIENT_WORKSPACE" run-help
"$CLIENT_PREFIX/bin/opencode-client" --workspace "$CLIENT_WORKSPACE" config-help
"$CLIENT_PREFIX/bin/opencode-client" --workspace "$CLIENT_WORKSPACE" check
"$CLIENT_PREFIX/bin/opencode-client" --workspace "$CLIENT_WORKSPACE" --plan chat
```

`check` actually runs installed `debug config` and `models local`, captures
their output, compares config and the single exact model selection, and tests
interpolation using a synthetic key. It never loads the configured real key.
It may initialize private runtime state, but sends no model inference request.
Use `--plan` for no mutation. These are **help/config checks, not agent E2E**.
Do not invoke raw `debug config` with a real key: upstream prints the resolved
key. Use only the launcher for the isolated setup; raw CLI calls omit its
environment controls.

For actual interactive work after the endpoint handoff:

```sh
"$CLIENT_PREFIX/bin/opencode-client" --workspace "$CLIENT_WORKSPACE" chat
```

The installed native executable is
`$CLIENT_PREFIX/xdg/config/opencode/node_modules/opencode-<os>-<arch>[-baseline]/bin/opencode`.
The wrapper always supplies `local/<exact API model ID>`. It configures
`@ai-sdk/openai-compatible`, `options.baseURL`, the exact `models` map and
both `model` and `small_model` to the local selection. Context/output limits
are operator inputs; V1 must verify them against the serving backend. The
config uses Chat Completions, not the Responses API.
[Official custom providers](https://opencode.ai/docs/providers/#custom-provider)

Only literal `http(s)://127.0.0.1:<port>/v1`, `localhost`, or `[::1]` bases are
accepted; credentials, query strings and fragments are refused. For a remote
backend, establish the **operator-coordinated V1 tunnel** using the port that
Worker1 publishes:

```sh
export CLIENT_BACKEND_PORT='REPLACE_WITH_PUBLISHED_PORT'
ssh -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 \
  -o ServerAliveCountMax=3 -N \
  -L "127.0.0.1:30002:127.0.0.1:${CLIENT_BACKEND_PORT}" ai-vm
```

This is a later operator procedure, not a V0 action. Keep the forwarding
listener and backend on loopback. A broader API listener needs API-key auth
and documented firewall/TLS policy. The helper does not create tunnels,
install services, discover models remotely, or change a server.

## Private state and verified isolation controls

All generated files and child processes use a private prefix, without changing
the parent's environment, `HOME`, `CODEX_HOME`, npm/git configuration, or auth
stores. Only basic terminal/locale variables, `PATH`, and the unchanged `HOME`
are inherited. Cloud credentials, proxy variables, npm overrides, and external
OpenCode config variables are not inherited. The selected key alone is encoded
into the child environment for real work; child tools can inherit that key.

| Prefix-relative location | Use |
| --- | --- |
| `bin/opencode-client`, `bin/client_common.py` | Copied standalone launcher/support |
| `bootstrap.json`, `opencode.json`, `models.json` | Secret references/settings, generated config, empty external model catalog |
| `xdg/config/opencode` | Locked npm installation and isolated OpenCode config directory |
| `xdg/data`, `xdg/cache`, `xdg/state` | OpenCode database, sessions, logs and cache/state |
| `npm/cache`, `npm/logs`, `npm/userconfig`, `npm/globalconfig` | Private npm cache/logs and empty config files |
| `tmp`, `bun-cache` | Private temporary files and Bun package cache |
| `discovery-home`, `managed` | Empty redirected discovery/managed roots |

The prefix is 0700; generated settings are 0600 and launcher 0700. Session and
tool output can contain workspace content; keep this state private. No real
credentials should be put into prompts, committed files or debug output.

For this exact release the launcher uses:

- `enabled_providers:["local"]`, explicit main/small model, a private empty
  `OPENCODE_MODELS_PATH`, and `OPENCODE_DISABLE_MODELS_FETCH=1`.
- `autoupdate:false`, `OPENCODE_DISABLE_AUTOUPDATE=1`, `share:"disabled"`,
  snapshots/LSP/formatters disabled, empty MCP/plugin config, and `/bin/sh`
  selected explicitly to avoid the macOS default shell's user startup files.
- `OPENCODE_DISABLE_PROJECT_CONFIG=1`, `OPENCODE_PURE=1`, and the supported
  disable-default-plugins, external-skills, Claude-Code, LSP-download, embedded
  web-UI and file-watcher flags. Workspace project configs/plugins are skipped;
  repository instructions and source content still require trust.
- **Version-specific upstream test hooks** `OPENCODE_TEST_HOME` and
  `OPENCODE_TEST_MANAGED_CONFIG_DIR`. XDG and project-config disabling alone do
  not prevent 1.18.31 from discovering home-level `.opencode` or system managed
  configuration. The launcher refuses new files in these private roots.
  macOS MDM plists have no bypass: their presence causes refusal after an
  existence check only; their contents are never read by the helper.

These controls were checked against the pinned
[flags](https://github.com/anomalyco/opencode/blob/v1.18.31/packages/core/src/flag/flag.ts),
[runtime flags](https://github.com/anomalyco/opencode/blob/v1.18.31/packages/opencode/src/effect/runtime-flags.ts),
[config paths](https://github.com/anomalyco/opencode/blob/v1.18.31/packages/opencode/src/config/paths.ts),
[global paths](https://github.com/anomalyco/opencode/blob/v1.18.31/packages/core/src/global.ts),
[managed config](https://github.com/anomalyco/opencode/blob/v1.18.31/packages/opencode/src/config/managed.ts),
[npm startup](https://github.com/anomalyco/opencode/blob/v1.18.31/packages/core/src/npm.ts)
and the actual installed config/model output. The
[compiled build](https://github.com/anomalyco/opencode/blob/v1.18.31/packages/opencode/script/build.ts)
also disables dotenv/bunfig autoload. This is configuration isolation, not
an OS sandbox, network firewall, or protection against hostile executable code.

## Permissions and workspace trust

OpenCode's normal tools are broader than the A1 fixture. This launcher defaults
to denying tools except read/glob/grep, with **edit and bash asking permission**;
external-directory access is denied. Interactive `chat` can request approval.
In ordinary noninteractive `run`, this release automatically rejects permission
requests. Upstream `--auto` approves requests not explicitly denied, but the
launcher does not expose it or the dangerous aliases. Consult
[official permissions](https://opencode.ai/docs/permissions/) and
[the pinned run implementation](https://github.com/anomalyco/opencode/blob/v1.18.31/packages/opencode/src/cli/cmd/run.ts).

For deliberate automation, `--allow-edit` allows edits and
`--allow-test-command 'one exact command'` grants that bash command for the
current invocation only. The latter rejects wildcard/newline permissions.
Run prompts are read from `--prompt-file` and passed over stdin; results are
OpenCode JSON events. No server/auth/upgrade command or arbitrary CLI override
is forwarded by the launcher.

**Selecting a directory does not sandbox arbitrary tools.** Commands and test
code run as the client OS user, may access files/network outside the workspace,
and can inherit the encoded key. Allowed edits can change code that a permitted
test command executes. OpenCode permissions do not make hostile repositories
safe. Use a trusted workspace; use a separately provisioned disposable OS
sandbox for untrusted code. V0 proves neither arbitrary-code isolation nor
live tool behavior.

## V1 real read/edit/test acceptance — NOT_TESTED in V0

After Worker1 publishes the exact endpoint/model, limits, authentication,
reasoning/tool-parser mode and protected key procedure, make a **new** prefix
configured with those values. Establish the coordinated tunnel. Run A1's live
protocol acceptance separately; its success does not establish OpenCode E2E.

For OpenCode, create a fresh private disposable directory outside the repository
with `text_utils.py` containing a deliberately buggy implementation:

```python
def word_count(text):
    return len(text.split(" "))
```

Create `test_text_utils.py` with immutable `unittest` cases for `"one two" == 2`,
`"  one\ttwo  " == 2`, and `"" == 0`. Record its SHA-256, retain the original
implementation, and run `python3 -I -B test_text_utils.py` to record the actual
initial failure. Put this prompt in a private file outside the workspace:

```text
Read text_utils.py and test_text_utils.py. Fix word_count to count words
separated by arbitrary whitespace. Edit only text_utils.py; do not change
tests. Execute exactly python3 -I -B test_text_utils.py after your edit.
Explain the change and the observed test result.
```

Then run locally with a supervised V1 time budget (for example 900 seconds),
keeping event output private:

```sh
umask 077
"$CLIENT_PREFIX/bin/opencode-client" \
  --workspace "$V1_WORKSPACE" --allow-edit \
  --allow-test-command 'python3 -I -B test_text_utils.py' \
  --prompt-file "$V1_PROMPT_FILE" run >"$V1_RUN/opencode-events.jsonl"
```

Stop a timed-out run and mark it FAIL/incomplete. Review actual JSON tool events
for both file reads, a real implementation edit, a model-requested test command
with successful output, and a final answer. Independently rerun the test, compare
the implementation diff, and verify the immutable test hash. Record configured
and returned model identity, installed version, elapsed time, parser/reasoning
behavior, errors and usage when available. Claimed-only success, missing tool
events, edited tests, or a passing independent test without a model-requested
test is not a pass. Preserve evidence with secrets redacted; do not assume
OpenCode JSON output is automatically credential-redacted.

V1 must also verify live provider requests, authentication, tool-call
continuation and limits. **Clean Linux installation belongs to the full
installer's clean-machine acceptance and remains NOT_TESTED here.**

## Regressions and upgrade policy

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -W error::ResourceWarning -m unittest discover \
  -s scripts/client/tests -p 'test_*.py' -v
PYTHONDONTWRITEBYTECODE=1 python3 -W error::ResourceWarning -m unittest discover \
  -s tests -p 'test_agent*.py' -v
git diff --check
```

The existing CI checks are preserved; an Ubuntu 24.04 / Python 3.12 job runs
both real suites. Standard client tests use no network or package installs.
Set `V0_CLIENT_PREFIX` to an existing isolated installation when running the
client suite to enable its real installed version/config check (otherwise that
single test is explicitly skipped).
An actual pinned CLI install/help/config test must also be run on clean Linux
by the installer owner; CI's stdlib suite does not substitute for that test.

The opt-in **actual OpenCode-to-synthetic-server** fixture is separate from
offline unit tests. Choose a new absolute path outside Git under an existing
parent, then run:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -W error::ResourceWarning \
  scripts/client/tests/wire_fixture.py --help
PYTHONDONTWRITEBYTECODE=1 python3 -W error::ResourceWarning \
  scripts/client/tests/wire_fixture.py \
  --work-root /absolute/private/new-q38c-wire-run
```

This installs the committed npm lock into five fresh private prefixes (HTTPS
to npm is needed for installation), starts a loopback synthetic HTTP listener,
and runs the actual pinned launcher. It preserves default GLM and low GLM/generic
regressions, adds default Qwen and explicit `none` Qwen, and checks ordinary
requests, identified title requests, all auxiliary requests, and real two-round
`read` tool continuations. The fixture contents are disposable; no
host project, real key, inference backend, network tool or bash/edit permission
grant is used. It preserves the launcher's environment and permission controls.
This remains configuration isolation, not an OS sandbox.

Every received request must have the expected top-level effort presence/value,
with no template/body override. Received and validated counts must match; the
report records request and CLI event counts plus installed package versions.
The synthetic server asks OpenCode to read a file containing an unpredictable
marker, then verifies the matching tool result in its next request. The runner
also requires an actual completed read event and final text event. It caps
requests per invocation and wall time, cleans child process groups and its
listener, removes its generated key, and retains only allowlisted evidence in
`wire-evidence.json`. Raw headers, bodies and CLI transcripts are not emitted.
The private npm/OpenCode state remains for inspection; the runner never reuses
or deletes an existing work root.

The pinned CLI agent uses `streamText` for these requests. Its `--format json`
controls event output, not HTTP transport; there is no supported ordinary-agent
nonstream switch in this pin. SDK nonstream serialization is source-reviewed,
not claimed as actual OpenCode nonstream execution. A synthetic response is
not real LLM agent acceptance or proof of live GLM behavior.

Upgrade only in a reviewed change updating the exact package pins, full lock,
`VERSION`, official source links and isolation review together. Reverify the
test hooks, key interpolation, disabled providers/plugins/downloads and actual
CLI help/config. Install into a new prefix; never use `latest`, `opencode
upgrade`, global npm installation, or curl-pipe-shell. Preserve the previous
prefix for rollback. Changing endpoint/model/limits/auth/effort also uses a new prefix,
keeping existing installations deterministic. No automatic migration of
sessions or credentials is performed.
