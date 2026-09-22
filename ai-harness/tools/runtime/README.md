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
