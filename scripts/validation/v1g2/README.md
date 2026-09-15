# V1G2 ordinary-workspace fixture

This is the deliberately faulty starting fixture for the reviewed OpenCode
measurement. `text_utils.py` contains `word_count(text)` with the exact
`len(text.split(" "))` bug. The tests cover ordinary two-word input, leading and
trailing whitespace, tabs, newlines, mixed whitespace, and the empty string.

The test script explicitly loads its sibling implementation through
`importlib.util.spec_from_file_location` and `exec_module`. It therefore works
under Python isolated mode without relying on the working directory appearing
on `sys.path`.

## Verify the intended baseline

From this directory, run:

```sh
python3 -I -B test_text_utils.py
```

Expected baseline: exit status `1`, three test methods run, four failing
whitespace subtests and one failing empty-string assertion. The ordinary
two-word test passes. An `ImportError` or `ModuleNotFoundError` is not an accepted
baseline.

## Prepare a private workspace

Run these commands from the repository root on the client worker. The workspace
must stay outside the checkout. Do not place credentials or raw model events in
this repository.

```sh
set -euo pipefail
umask 077
fixture_workspace="$(mktemp -d /tmp/v1g2-fixture.XXXXXXXX)"
chmod 700 "$fixture_workspace"
cp scripts/validation/v1g2/text_utils.py "$fixture_workspace/text_utils.py"
cp scripts/validation/v1g2/test_text_utils.py "$fixture_workspace/test_text_utils.py"
chmod 600 "$fixture_workspace/text_utils.py"
chmod 400 "$fixture_workspace/test_text_utils.py"
shasum -a 256 "$fixture_workspace/text_utils.py" "$fixture_workspace/test_text_utils.py"
```

Archive the initial source and both hashes in task-private evidence before the
model runs. Verify the expected assertion failures in this workspace with the
same exact command, `python3 -I -B test_text_utils.py`. Use the reviewed client
launcher with this workspace explicitly trusted and that exact test command
allowed. The model must actually read both files, edit only `text_utils.py`, run
the exact test command through its tool, and produce a final answer. The human
or coordinator must not repair the implementation.

After the bounded model run, verify the test hash is unchanged, inspect the
implementation diff for a real arbitrary-whitespace fix, and independently run
`python3 -I -B test_text_utils.py` again. A passing independent run alone does
not establish agent success: the observed read, edit, and successful exact test
tool sequence are also required. Preserve these repository files as the faulty
baseline; the observed model change belongs to the private workspace and its
sanitized measurement report.

## Reproduce the two unchanged A1 measurements

Networking requires the coordinator's explicit request lease and a verified,
task-owned SSH tunnel. The VM remains unchanged. Run from the repository root
on the client worker. Replace the placeholders below with this task's free
local tunnel port and canonical absolute private directory outside Git. The
private directory and `a1-workspaces` must already exist with mode 0700; the
existing API key must have been transferred directly into its owned 0600
regular file without a newline, symlink, or hard link. Never print its contents.
Every report/log path below must be new.

```sh
set -euo pipefail
umask 077
v1g2_tunnel_port='REPLACE_WITH_OWNED_TUNNEL_PORT'
v1g2_private_root='/absolute/private/REPLACE_WITH_TASK_DIRECTORY'
v1g2_base_url="http://127.0.0.1:${v1g2_tunnel_port}/v1"
v1g2_key_file="$v1g2_private_root/protected-api-key"

if python3 -B scripts/agent/acceptance.py \
  --base-url "$v1g2_base_url" --model glm-5.3 \
  --api-key-file "$v1g2_key_file" --auth enabled \
  --reasoning-effort low --max-tokens 2048 \
  --request-timeout 300 --overall-timeout 1800 \
  --workspace-parent "$v1g2_private_root/a1-workspaces" \
  --report "$v1g2_private_root/a1-normal.json" \
  >"$v1g2_private_root/a1-normal.stdout" \
  2>"$v1g2_private_root/a1-normal.stderr"; then
  v1g2_a1_normal_exit=0
else
  v1g2_a1_normal_exit=$?
fi
```

Let the unchanged CLI finish its ordinary checks, including its genuine agent
loop. Review its private result and incoming coordination messages before the
next phase. The known invalid-model probe receives HTTP 200 and the served
`glm-5.3` identity; its check and the A1 aggregate remain **FAIL**, with expected
CLI exit status 1. Capturing that exit code does not waive or reclassify any
failure. Do not stop the ordinary checks solely because of this known failure.

Run the second unchanged invocation once, with streamed tool rounds:

```sh
if python3 -B scripts/agent/acceptance.py \
  --base-url "$v1g2_base_url" --model glm-5.3 \
  --api-key-file "$v1g2_key_file" --auth enabled \
  --reasoning-effort low --max-tokens 2048 \
  --request-timeout 300 --overall-timeout 1800 \
  --workspace-parent "$v1g2_private_root/a1-workspaces" \
  --report "$v1g2_private_root/a1-stream-tools.json" --stream-tools \
  >"$v1g2_private_root/a1-stream-tools.stdout" \
  2>"$v1g2_private_root/a1-stream-tools.stderr"; then
  v1g2_a1_stream_exit=0
else
  v1g2_a1_stream_exit=$?
fi
```

**OpenCode gate:** both genuine A1 agent loops must pass, and all other
authentication, model-list, chat, SSE and protocol checks must pass. The known
invalid-model failure alone permits the independently authorized OpenCode
measurement. Any other auth/protocol/runtime failure stops dependent OpenCode
work. Preserve a bounded diagnostic for length, timeout, protocol or runtime
failure; do not retry, raise budgets or tune the VM. Keep the original V1G A1
aggregate FAIL and report each V1G2 aggregate honestly.

## Reproduce the reviewed pinned OpenCode measurement

After the A1 gate and phase-boundary coordination review, bootstrap through the
unchanged reviewed implementation and committed package lock. This installs
actual OpenCode 1.18.31 in a fresh private prefix. The worker must already meet
the documented Node/npm prerequisites. Do not manually edit generated config.
Use the private fixture prepared above and a private UTF-8 prompt file instructing
the model to read both files, edit only the implementation, execute the exact
allowed test command, and explain its observed result. Raw prompt contents stay
outside Git.

```sh
v1g2_client_prefix="$v1g2_private_root/opencode-client"
v1g2_prompt_file="$v1g2_private_root/opencode-prompt.txt"

python3 -B scripts/client/bootstrap.py \
  --prefix "$v1g2_client_prefix" \
  --base-url "$v1g2_base_url" --model glm-5.3 \
  --api-key-file "$v1g2_key_file" \
  --reasoning-effort low --context-tokens 32768 --output-tokens 2048 \
  >"$v1g2_private_root/bootstrap.stdout" \
  2>"$v1g2_private_root/bootstrap.stderr"

python3 -B "$v1g2_client_prefix/bin/opencode-client" \
  --workspace "$fixture_workspace" version \
  >"$v1g2_private_root/client-version.stdout" \
  2>"$v1g2_private_root/client-version.stderr"

python3 -B "$v1g2_client_prefix/bin/opencode-client" \
  --workspace "$fixture_workspace" check \
  >"$v1g2_private_root/client-check.stdout" \
  2>"$v1g2_private_root/client-check.stderr"
```

Verify the actual version is 1.18.31 and the check passes for exactly the
configured local provider/model before inference. **The run command below must
be executed under an external, verified 1800-second supervisor that owns the
complete child process tree and terminates only that tree on timeout or exit.**
The reviewed launcher itself supplies no wall-time bound or process-tree
cleanup. The following is the supervised child command, not a standalone
bounded runner:

```sh
python3 -B "$v1g2_client_prefix/bin/opencode-client" \
  --workspace "$fixture_workspace" --allow-edit \
  --allow-test-command 'python3 -I -B test_text_utils.py' \
  --prompt-file "$v1g2_prompt_file" run \
  >"$v1g2_private_root/opencode-events.jsonl" \
  2>"$v1g2_private_root/opencode.stderr"
```

Run once. Preserve actual native JSON events privately; do not substitute
unavailable tools, edit tests, repair the source manually, retry, or increase
the budget. The required actual tool and independent-test evidence remains as
specified above. Record observed token usage, elapsed time, finish reason and
tool order. If provider usage is absent, record **NOT_REPORTED**; client event
counters alone must not be relabeled as provider-supplied usage. A 32768 context
configuration does not prove a large occupied context, fresh Linux installation
or reboot. Installer/server readiness remains pending the explicit model-name
compatibility decision.

Publish only allowlisted, sanitized measurement evidence after scanning against
the actual key in memory without displaying matches. On completion, stop the
owned client process tree, close only the task-owned tunnel and write the lease
release indicating zero active requests and tunnel closed.
