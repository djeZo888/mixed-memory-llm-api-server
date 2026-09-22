# Technical tooling contract

First-party manifests/tests are MIT; dependencies retain their own licenses.
The engine image supplies Node24 and Python **>=3.12** in
`/opt/ai-harness-python`. Install the two hash-locked PDF/runtime requirements in
a single pip invocation, and install each Node package-lock with `npm ci
--omit=dev --ignore-scripts`. No global npm install or additional browser download.

OS package names (versions/base snapshot are PREP-owned):
`build-essential clang cmake ninja-build gdb git ripgrep python3-venv python3-pip
poppler-utils tesseract-ocr tesseract-ocr-eng chromium fonts-dejavu-core
fonts-liberation`. Make `/opt/ai-harness-python/bin` and
`/opt/ai-harness/tools/runtime/node_modules/.bin` available on PATH. Use
`MCODE_CHROME_PATH=/usr/bin/chromium` and preserve its sandbox. GDB may be installed
but ptrace can be restricted by the container; this does not authorize weakening
container isolation.

`typescript` and `@playwright/test` are pinned project testing tools. The
MiniMax native browser is the interactive browsing interface, with no redundant
browser MCP server. For ESM imports from the shared package directory use
`createRequire('/opt/ai-harness/tools/runtime/package.json')` or the project's
own pinned dependency; PATH and NODE_PATH do not resolve bare ESM imports.
Playwright tests must set `launchOptions.executablePath` to
`process.env.MCODE_CHROME_PATH` and `launchOptions.chromiumSandbox=true`.

Python lock generated on macOS Python3.14 using pip25.3/pip-tools7.5.3 from the
explicit requirements.in; hashes include published artifacts for other platforms.
This does not establish Linux wheel availability or Linux runtime acceptance.
Reproduction uses a task-local venv and writable cache:

```sh
python3 -m venv .venv-lock
.venv-lock/bin/python -m pip install pip==25.3 pip-tools==7.5.3
PIP_CACHE_DIR="$PWD/.cache/pip" .venv-lock/bin/python -m piptools compile \
  --cache-dir .cache/pip-tools --generate-hashes --strip-extras \
  --output-file requirements.lock requirements.in
```

Worker smoke checks (paths from repository root; build outputs outside source):

```sh
python -m pytest -q ai-harness/tools/runtime/test/test_calculations.py
node --test ai-harness/tools/runtime/test/calculation.test.mjs
ai-harness/tools/runtime/node_modules/.bin/tsc --noEmit --target es2022 \
  --module nodenext ai-harness/tools/runtime/test/calculation.ts
cmake -S ai-harness/tools/runtime/test -B ../evidence/runtime-build -G Ninja
cmake --build ../evidence/runtime-build --parallel 2
ctest --test-dir ../evidence/runtime-build --output-on-failure
```

Results and platform limitations are recorded in task evidence, never inferred
from installed package names. No full native-agent or Linux acceptance is claimed.

## Native MiniMax selection fragment (PREP-owned integration)

At exact pin `ae65651df5f97ae1085ab4e19964f4b78c769a4e`, the native settings
file is `${MINIMAX_DATA_DIR}/config.yaml`. Deep-merge the JSON-compatible mapping
in `minimax-settings.fragment.json` into PREP's existing settings; it is not a
complete replacement config. Preserve provider settings, other beta/features
and the separate PREP choice for `agents.default.features.mavis`.

`agents.default.skills: [code-review]` selects standalone **builtin** skills;
it suppresses builtin Office/PDF advice while permitting curated profile/global
skills. `builtinTools: []` and `features.webSearch: false` suppress Matrix
capabilities/search; `features.delegation: true` keeps delegation available.
`skills.external.enabled: false` disables workspace and host external ingestion,
while native `${MINIMAX_DATA_DIR}/skills` remains a global source. At first profile
initialization copy only the five curated directories there: `technical-research`,
`code-investigation`, `calculations`, `technical-testing`, `pdf`, plus the
first-party `LICENSE-MIT.txt` notice. The global `pdf`
shadows the builtin by source precedence, in combination with builtin suppression
and external ingestion disabled. Profiles must contain only reviewed agent/global
skill roots; no additional host mounts are needed.

Canonical execution-profile `configSelection.skills` is a different selector:
it filters **all standalone skills**, including curated ones. Prefer leaving it
absent. If PREP explicitly supplies it, the corresponding fragment is:

```json
{
  "configSelection": {
    "skills": [
      "technical-research", "code-investigation", "calculations",
      "technical-testing", "pdf", "code-review"
    ]
  }
}
```

That fragment belongs to the canonical execution profile, not top-level
`config.yaml`. The optional `configSelection.extensionSkills` must likewise be
absent or include the five curated names. A selector only narrows ready skills;
it cannot enable an unavailable capability.

Keep `beta.browserUseTooling: true` and the native browser provider. Its `browser`
tool and `control-in-app-browser` skill are capability-owned injection, separate
from these standalone skill selectors. Do not put the browser skill in the
builtin whitelist or add a Playwright MCP. Private SearXNG is the configured MCP
search entry; `features.webSearch: false` disables Matrix search, not SearXNG.

Profile MCP lives at `${MINIMAX_DATA_DIR}/mcp.json` and takes literal environment
values. The workspace alternative `.mcp.json` supports environment expansion.
See `../search/README.md` for distinct examples. All choices above are backed by
reviewed pinned source; the live native roster remains NOT_TESTED until the
separate integration acceptance.

These settings are defaults: explicit per-role capability overrides take
precedence. PREP must ensure configured roles inherit or retain the reviewed
restrictions, and check delegated-agent effective rosters during native acceptance.
This source fragment does not constrain unknown overriding agent definitions.
