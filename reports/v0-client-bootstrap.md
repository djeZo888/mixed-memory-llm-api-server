# V0 pinned general client bootstrap

Date: 2026-09-15. Worker: **Mac-Worker2**, Darwin arm64.
Branch: `milestone/v0-client-bootstrap`. Integration base:
`cbd9dadbf270413c70492deed489e84cb931e124` (reviewed A1).

**PASS: client bootstrap, actual installed CLI/config verification and worker
regressions.** V1 real OpenCode read/edit/test acceptance, target Ubuntu runtime
execution, and clean Linux installation remain **NOT_TESTED**.

## Delivered ownership

- `scripts/client/bootstrap.py`, `client_common.py`, `launch.py`: reusable
  prefix-local installer and standalone copied launcher for any explicitly
  supplied trusted workspace. Literal localhost API/model/limits are required;
  key-file/env references or explicit disabled auth are supported.
- `scripts/client/package.json`, `package-lock.json`: exact OpenCode/plugin pin
  and complete integrity lock. No global install, installer download pipe,
  package build, auto-update, or model download.
- `scripts/client/tests/test_bootstrap.py`: offline regression suite plus an
  opt-in actual installed CLI check.
- [`docs/client-install.md`](../docs/client-install.md): exact usage,
  prerequisites, private paths, tunnel integration, permissions, pin/upgrade
  policy and later V1 procedure.
- `.github/workflows/ci.yml`: appended Ubuntu 24.04/Python 3.12 job for the real
  A1 and client suites. All preexisting checks remain unchanged.

No A1 implementation/tests, lifecycle helpers, llmctl, profiles, D1/D2 files,
README, current-state or AGENTS files were changed. No concurrent-task files,
global configuration, VM disks or services were changed; no user auth files
were directly read. Existing gh authentication is used only through the
specified push credential helper. No SSH, VM key retrieval, inference, or Docker installation occurred.
VM `/data` guard scripts do not apply to this authorized worker-only install.

## Official pin and integrity

Current official sources were checked on **2026-09-15**:
[installation](https://opencode.ai/docs/#install),
[CLI](https://opencode.ai/docs/cli/),
[configuration](https://opencode.ai/docs/config/),
[custom providers](https://opencode.ai/docs/providers/#custom-provider),
[permissions](https://opencode.ai/docs/permissions/),
[npm metadata](https://registry.npmjs.org/opencode-ai/1.18.31) and
[release v1.18.31](https://github.com/anomalyco/opencode/releases/tag/v1.18.31).

- Exact published version: **`opencode-ai@1.18.31`**, published
  `2026-09-14T17:47:43.078Z`; tag commit
  `014614d35b397775e5d397a490fc72368c894ec2`.
- Root package SHA-512 SRI:
  `sha512-J95feefeWwtIaw3irx76WjzWcgQXxmuHmDVphvs5ep9X30fBJ6T6bFhw50i9Kx50MG/xPn5w2pafXIfNtdry9w==`.
- Actual Darwin arm64 package SRI:
  `sha512-IN642oFENleWVDNqMnXi8NQLsZnA8hMswJ6X+GWz+CfBFuCpotjDb5OHgE2HBdC6r5wjG6v0mATb+Mn8xXCp1A==`.
- Lock SHA-256:
  `eb4f16892e1e7d955fc8aa5e949f8c31b6c6d26d98acb3eb2f9be26d2673d3b7`.
  All 45 package entries have exact versions, official registry HTTPS URLs and
  SHA-512 integrity. npm checks tarball integrity during `ci`.
- Installed Darwin arm64 executable SHA-256:
  `16c960ba77421da11b53e785f359b73f328a86118b48feb4af143db5d9afb198`.

Node **24.21.0**, npm **11.19.0**, Python **3.14.7** were already installed.
The helper supports Node 24.x >=24.15.0/npm 10+ for this dependency lock;
upstream `opencode-ai` declares no engines. The installer must provision those
prerequisites and the target's project test tools separately.

The exact CLI is installed at:
`/Users/agent/LLMServer-orchestration/20260915/V0/client/xdg/config/opencode/node_modules/opencode-darwin-arm64/bin/opencode`.
The reusable launcher is
`/Users/agent/LLMServer-orchestration/20260915/V0/client/bin/opencode-client`.
No worker path is hard-coded in the committed scripts. The worker-only config
uses `http://127.0.0.1:30002/v1`, model `v0-not-serving`, placeholder limits
32768/2048 and a **nonexistent key reference**. These are config-test inputs,
not a claim that any endpoint/model is serving.

## Isolation and permission findings

Version-specific source review found that XDG and disabling project config are
insufficient by themselves: home `.opencode` and managed configuration still
load. The launcher uses the pinned upstream home/managed test hooks, refuses
macOS managed plists by existence check, uses an empty local model catalog,
scrubs inherited provider/npm/proxy settings, and disables default/external
plugins, external skills, Claude config, auto-update and model refresh.
Source links and complete path/control mapping are in the installation guide.

OpenCode config startup also installs `@opencode-ai/plugin`; V0 preinstalls the
real locked dependency tree in its private config root. Native binaries are
invoked directly after `npm ci --ignore-scripts`, preventing wrapper fallback
installs. XDG, npm and temporary state stay beneath the prefix. Repeated
bootstrap/config checks reused the same locked tree.

Key references are not opened during bootstrap/help/plan/config verification.
Real launch validates A1-compatible newline-free ASCII bytes, never trims or
rewrites files, and safely encodes environment interpolation. Actual installed
config validation restored synthetic quote/backslash/brace key bytes exactly
without expanding a fake file reference. Raw resolved config is captured and
not printed; real credentials were never involved.

Default policy allows reads/search, asks for edits/bash, and denies other tools
and external-directory access. Ordinary noninteractive OpenCode rejects asks;
the launcher offers deliberate edit and exact test-command permissions for V1,
without `--auto` or arbitrary CLI forwarding. It selects `/bin/sh` explicitly.
**A workspace and tool permissions are not an OS sandbox.** Allowed tests can
execute edited code and inherit the encoded key. Live tool behavior and
credential-redacted event capture require V1 review with trusted fixtures.

## Checks run

| Check | Status / evidence |
| --- | --- |
| Clean isolated branch/base, AGENTS and A1 docs/report read first | PASS |
| Official package/source/pin review and npm integrity-locked local install | PASS |
| Actual installed `--version` | PASS: `1.18.31` |
| Actual `--help`, `run --help`, `debug config --help` | PASS; help captured from stderr (4119/3053/565 output characters) |
| Actual `debug config` and `models local` via launcher | PASS: exact config and sole `local/v0-not-serving` selection; no inference |
| Key interpolation and config validation using synthetic punctuation | PASS; no real reference loaded |
| Client suite with `V0_CLIENT_PREFIX` set | PASS: 21 tests, 3.271s, no skips |
| Offline client suite | PASS: 20 tests; installed-only test explicitly skipped |
| Exact reviewed A1 suite with ResourceWarnings as errors | PASS: 75 tests, 6.316s, Python 3.14.7 |
| Bootstrap fresh-prefix dry-run; installed dry-run and launcher plan | PASS: no filesystem mutation |
| Two repeat installs after completed implementation | PASS: no reinstall or private-tree mutation; actual version checked |
| Fresh final-helper install into a prefix containing spaces | PASS: separate exact URL/model and absent env-key reference; actual CLI config check passed |
| Workspace with spaces/punctuation, invalid project configs and conflicting cloud/config environment | PASS: ignored by actual CLI; workspace unchanged |
| Newline/whitespace/invalid key, symlink/hardlink/public file, unsafe URL/prefix/reference tests | PASS; failures are explicit and preserve source bytes |
| Python 3.10 grammar, locked package metadata review | PASS; grammar is not Linux execution |
| Staged ownership, credential-free remote, local rg secret scan, `git diff --check`, markdown link CI check | PASS; scan allowed only two exact synthetic test literals |
| Ubuntu 24.04/Python 3.12 container run | **NOT_TESTED**: Docker executable unavailable; daemon/container unavailable |
| Ubuntu GitHub Actions execution | **NOT_TESTED on worker**; real suites wired to added target job |
| VM API/auth/model inference; actual OpenCode read/edit/test E2E | **NOT_TESTED** — V1 |
| Clean Linux installer / Linux native CLI execution | **NOT_TESTED** — installer owner |

Exact commands: the two regression discovery commands in the installation
guide; installed check additionally sets `V0_CLIENT_PREFIX` to the task prefix.
Worker evidence (help outputs and integration checks) is retained under
`/Users/agent/LLMServer-orchestration/20260915/V0/evidence/`.

## Warnings and next action

No remaining worker regression failure is known. A dry-run creation defect and
stderr-only CLI-help capture were found during implementation and fixed before
the final checks. Independent review also tightened private config discovery,
glibc detection and shell selection. No A1 cross-platform defect emerged on
macOS; absence of Linux execution is recorded rather than inferred away.

V1 must use Worker1's actual endpoint/model/parser/auth/limit handoff, a new
configured prefix and protected key, then run both A1 live acceptance and the
documented **actual OpenCode** read/edit/test procedure. The full installer must
provision prerequisites, integrate this helper without weakening storage and
API policies, and prove it on a clean Ubuntu 24.04 machine. Old planning gates
were not treated as new approval requirements for this authorized component.

## Publication

Only owned files are published with attribution
`CodexAIagent <133749519+djeZo888@users.noreply.github.com>` on
[`milestone/v0-client-bootstrap`](https://github.com/djeZo888/mixed-memory-llm-api-server/tree/milestone/v0-client-bootstrap).
Final commit, remote verification, whitespace/secret checks and bundle result
are recorded in `/Users/agent/LLMServer-orchestration/20260915/V0/progress.md`.
The incremental bundle is `/Users/agent/LLMServer-orchestration/20260915/V0/V0.bundle`
relative to `cbd9dad`; the receiver must already have that base. No push to main.
