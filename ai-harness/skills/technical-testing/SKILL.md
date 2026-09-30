---
name: technical-testing
description: Build and test small C, C++, Python and JavaScript changes with the image's local technical toolchain.
---

# Technical testing

Use the project's documented build and test commands when present, after checking
their scripts and targets for external side effects. Keep build directories,
virtual environments, fixtures, logs and outputs inside the workspace. Tests run
as the ordinary container user; do not request host sockets, host mounts, sudo,
credentials or a disabled browser sandbox.

Available by image contract: GCC/G++, Clang/Clang++, CMake, Ninja and GDB;
`/opt/ai-harness-python/bin/python` with pytest and numerical libraries; Node 24,
npm and TypeScript. Check an actual command's availability and report a missing
tool instead of claiming a test ran. Project packages must be pinned by their
lockfile; do not use `npx` to fetch an unpinned tool or install globally.

Representative commands, when the named project files exist:

```sh
# C / C++: choose the project's language and standard.
cc -std=c17 -Wall -Wextra -Wpedantic test.c -o build/test-c
c++ -std=c++20 -Wall -Wextra -Wpedantic test.cpp -o build/test-cpp
cmake -S . -B build -G Ninja
cmake --build build --parallel 2
ctest --test-dir build --output-on-failure

# Python / Node: narrow to relevant tests first.
/opt/ai-harness-python/bin/python -m pytest -q tests/test_changed_feature.py
node --test test/changed-feature.test.mjs
/opt/ai-harness/tools/runtime/node_modules/.bin/tsc --noEmit
```

Create `build/` first for direct compiler examples. Match the repository's actual
standard and flags; successful compilation alone does not exercise behavior.
Cover a meaningful normal case and relevant boundary/failure cases. Use known
input/output checks, not assertions that merely restate implementation text.
Run newly created executables with bounded inputs and the native shell's timeout
facility. Avoid indefinite fuzzing, unrestricted benchmarks or external service
tests without task authorization. GDB availability does not imply container
ptrace permission; report restrictions rather than weakening the container.

Use MiniMax's native browser for interactive inspection of an authorized local
app. The image's pinned Playwright package is project test tooling only; existing
automated browser tests must select `MCODE_CHROME_PATH` and keep Chromium's sandbox
enabled. Do not download a second browser, add a Playwright MCP, or copy a browser
launch configuration that disables sandboxing.

The shared package is at
`/opt/ai-harness/tools/runtime/node_modules/@playwright/test`. For an ESM test,
either use the project's own pinned local dependency or load that installed
package through Node's `createRequire`:

```js
import { createRequire } from 'node:module';
const requireRuntime = createRequire('/opt/ai-harness/tools/runtime/package.json');
const { test, expect } = requireRuntime('@playwright/test');
test.use({ launchOptions: {
  executablePath: process.env.MCODE_CHROME_PATH,
  chromiumSandbox: true,
} });
```

Confirm `MCODE_CHROME_PATH` is set before running the tests. Run with the shipped
`/opt/ai-harness/tools/runtime/node_modules/.bin/playwright test` CLI or the
project's equivalent pinned script. Adding a directory to `PATH` exposes its CLI
but does not make bare ESM imports resolve; `NODE_PATH` is not an ESM fix.

Record command, platform, pass/fail/skip counts and relevant failure output.
Distinguish real tool execution from fixtures/mocks. A macOS result is not Linux
container acceptance; unavailable tools, public service behavior and native-agent
integration remain NOT_TESTED until exercised in their intended environment.
