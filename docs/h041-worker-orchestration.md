# H041 worker orchestration

Run orchestration from `mac-orchestrator`. Root assigns, stages, reviews, integrates
and publishes; application implementation, builds and tests run on `mac-worker1`
and `mac-worker2`. Each future assignment starts a **new `codex exec` session** in
its own protected checkout, lasts 30–45 minutes, and closes before its successor
starts. Do not use `exec resume`, `--last`, or an old session ID.

This is the continuation procedure requested at H041 wrap-up. Earlier H041
launchers often resumed an adopted session; their receipts remain historical
evidence, not templates for session reuse. Read the current [working rules](../AGENTS.md) and compact
[final handoff](../reports/h041-final-handoff.md) first. Open old phase plans only
when their specific evidence is needed; their authority is historical.

## Roles, authority and time

| Actor | Owned work |
| --- | --- |
| Root on mac-orchestrator | Assignments, source/interface review, integration, publication, and exclusive issuance of concrete shared-Linux GO |
| mac-worker1 / A | Runtime, server, receipts, launcher, deployment and runtime tests; shared-Linux actions only within an exact root GO |
| mac-worker2 / E | Acceptance adapter, controller, scorer, consumer/browser acceptance wiring and its assigned tests |

List exact files in each assignment. A shared file has one owner; transfer it
explicitly before another worker edits it. An interface export lets the other
worker consume reviewed source without taking ownership. Root does not implement
application fixes during coordination.

Use existing SSH host aliases, pinned known-hosts configuration, Git credentials
and authenticated Codex accounts. Keep credentials outside the checkout; do not
regenerate, print or copy them into prompts, bundles or reports. Source-only Mac
authority does not authorize Linux lifecycle, inference, cleanup or deployment.
Root GO identifies the concrete reviewed source/config/helper graph, current
owner/route/process tuple, scope, deadline and permitted invocation count. Keep
existing lease, freeze, ownership and authenticated admission guards. An expired,
spent or failed approval cannot authorize a retry.

Keep the agreed Sova pins: native Codex `0.158.0`, upstream `064c`, context
`480000`, automatic compaction `400000`, and output limit `65536`, with the
reviewed provider/model/route and original histories intact. The Mac CLI version
recorded by H041 is `0.159.2`; it is a separate executable and does not upgrade
Sova. A change to any pin requires its own reviewed scope.

Record the user's overall end time in UTC. Reserve its final **15 minutes** for
closure, collection, review and handoff. A worker's hard deadline must fall before
that reserve; target source export several minutes before its hard deadline.
Start another 30–45 minute task only if the remaining authorized window also
allows its closure and the wrap reserve. Stop paid sessions during dependency or
model-loading waits. Missing time produces a partial result, not an extension of
the user's cap.

## Private layout and prompt contract

The verified H041 layout is:

```text
mac-orchestrator:
  /Users/agent/Documents/LLMServer/orchestration/h005-integration
  /Users/agent/Documents/LLMServer/orchestration/tasks/H041-20261001/<new-phase>/
mac-worker1 or mac-worker2:
  /Users/agent/CodexProjects/llm-orchestration/H041-20261001/<new-phase>/
    repo/                     isolated source checkout
    output/                   bundles, checks and final evidence
    PROMPT.md                 bounded assignment
    AUTHORITY.json            current source scope/deadline
    CANDIDATE.json            exact base commit and bundle SHA-256
    native-wrapper.py         owns the CLI process and deadline
    outer-waiter.py            owns the wrapper and records its exit
```

Create a distinct phase directory with `exist_ok=False`, mode `0700`, under an
already protected worker-owned parent. Protect prompts, wrappers, receipts and
logs with `0600` and `umask 077`. Validate ownership, resolved paths and parent
protection; do not fix a shared parent by weakening or changing its permissions.
Clone with `--no-hardlinks` into `repo/`, check out the exact candidate, and keep
the original checkout unchanged. Any reused dependency tree must be identified
and treated as immutable; use an isolated copy for dependency mutations. Never
carry uncommitted work implicitly: seal it, or adopt an explicit owned-file patch
and hash manifest while preserving the original evidence.

The prompt contains only what the worker needs:

1. Concrete outcome, reviewed base commit, relevant handoff/interface pointers.
2. Exact owned files and explicitly excluded files; required source checks.
3. UTC export target/hard deadline and overall user cap.
4. `gpt-6.1-sol`, reasoning `ultra`, fresh session, source-only authority unless a
   separate exact GO is supplied; existing credentials and fixed runtime pins.
5. Expected export: sealed source/report commits, bundle, changed-file hashes,
   actual command receipts/logs, known failures and `NOT_TESTED` limitations.

Avoid copying a complete old conversation, bulky raw traces, secrets or an old
GO. Preserve those privately and point to the relevant retained evidence.

## Stage and launch over SSH

The following are operator examples for a newly authorized task, not commands
to replay against an old H041 phase. Replace each placeholder from the reviewed
assignment. Prepare the bundle and scripts locally first; no session starts
during staging.

```sh
WORKER_HOST=mac-worker1                 # mac-worker2 for E
PHASE_NAME=A-h041-next                  # a new, unique directory name
LOCAL_PHASE=/Users/agent/Documents/LLMServer/orchestration/tasks/H041-20261001/$PHASE_NAME
REMOTE_PHASE=/Users/agent/CodexProjects/llm-orchestration/H041-20261001/$PHASE_NAME

ssh -o BatchMode=yes -o ConnectTimeout=8 "$WORKER_HOST" 'python3 -' \
  < "$LOCAL_PHASE/check-prior-closure.py" > "$LOCAL_PHASE/PRIOR-CLOSURE.json"
ssh -o BatchMode=yes -o ConnectTimeout=8 "$WORKER_HOST" 'python3 -' \
  < "$LOCAL_PHASE/setup-phase.py" > "$LOCAL_PHASE/SETUP.json"
scp -q "$LOCAL_PHASE/candidate.bundle" "$LOCAL_PHASE/CANDIDATE.json" \
  "$LOCAL_PHASE/AUTHORITY.json" "$LOCAL_PHASE/PROMPT.md" \
  "$LOCAL_PHASE/native-wrapper.py" "$LOCAL_PHASE/outer-waiter.py" \
  "$WORKER_HOST:$REMOTE_PHASE/"
ssh -o BatchMode=yes -o ConnectTimeout=8 "$WORKER_HOST" 'python3 -' \
  < "$LOCAL_PHASE/start-phase.py" > "$LOCAL_PHASE/COORDINATOR-LAUNCH.json"
```

These named coordinator scripts are prepared and reviewed for each task; they
are not a general installer included with this document. The verified historical
implementation is the private
`H041-20261001/launch-source-10.py`: it uses `ssh HOST 'python3 -'`, SCP, an isolated
clone, then the detached launch below. Its old session-resume logic must be
removed for future assignments. Setup verifies the received bundle SHA-256 and
`git bundle verify`, fetches it into a distinct local ref, checks out the approved
commit, and verifies `git rev-parse HEAD` and clean/adopted-file state before launch.
Record source, prompt, authority and wrapper hashes before execution.

Use the actual verified CLI flags, with the fresh-session change applied:

```python
argv = [
    '/opt/homebrew/bin/codex', 'exec', '--json', '--skip-git-repo-check',
    '-m', 'gpt-6.1-sol',
    '-c', 'model_reasoning_effort="ultra"',
    '-c', 'approval_policy="never"',
    '-c', 'sandbox_mode="danger-full-access"',
    '-o', str(p / 'LAST_MESSAGE.md'), '-'
]
```

`p` is the new absolute phase path. The wrapper changes directory to its `repo/`,
sets the recorded H041 PATH
`/opt/homebrew/opt/node@24/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin`,
reads `PROMPT.md` through stdin, and writes stdout to `events.jsonl` and stderr to
`stderr.log`. The trailing `-` supplies the prompt through stdin. There is no
session-ID argument. The historical flags and process pattern are verified;
this fresh-session argv is the required successor configuration, not a claim
that historical resumed phases already used it.

The remote start script uses the verified detached outer launch:

```python
with (p / 'outer.log').open('wb') as out:
    child = subprocess.Popen(
        ['/usr/bin/python3', str(p / 'outer-waiter.py')],
        stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT,
        start_new_session=True)
(p / 'outer-pid').write_text(str(child.pid))
```

Retain that PID, launch UTC, host, candidate, phase path and hard deadline in
`COORDINATOR-LAUNCH.json`. The outer waiter starts
`['/usr/bin/python3', str(p/'native-wrapper.py')]` with `start_new_session=True`,
writes `wrapper-pid`, waits for its real exit and writes `OUTER-TERMINAL.json`.
The native wrapper writes `native-pid` and `DEADLINE.json` with its exact argv,
model, effort, start and deadline, then writes `WRAPPER-TERMINAL.json` from the
actual CLI wait result. Record process birth metadata while the processes exist
so later PID reuse is distinguishable.

The retained wrapper begins TERM 15 seconds before its hard deadline, allows
10 seconds, then sends KILL to its owned process group. Its final reap and the
outer wait are ordinary blocking waits; missing terminal receipts must therefore
remain incomplete and require an owned closure check. Do not describe the timer
alone as proof that every descendant exited or a Linux resource was settled.

## Check, collect and close

Use bounded, read-only checks rather than keeping an SSH connection or paid CLI
alive while waiting. The root-generated checker reads only the selected phase's
receipt/status fields and checks exact process identities; it must not print
credentials or bulk private JSONL.

```sh
ssh -o BatchMode=yes -o ConnectTimeout=8 "$WORKER_HOST" 'python3 -' \
  < "$LOCAL_PHASE/check-phase.py" > "$LOCAL_PHASE/STATUS.json"
scp -q "$WORKER_HOST:$REMOTE_PHASE/DEADLINE.json" \
  "$WORKER_HOST:$REMOTE_PHASE/WRAPPER-TERMINAL.json" \
  "$WORKER_HOST:$REMOTE_PHASE/OUTER-TERMINAL.json" "$LOCAL_PHASE/"
scp -q "$WORKER_HOST:$REMOTE_PHASE/output/candidate.bundle" \
  "$WORKER_HOST:$REMOTE_PHASE/output/RESULTS.json" "$LOCAL_PHASE/"
```

Adapt output names to the exact exported inventory; a missing file is a missing
receipt, not success. Collect originals and compute local SHA-256 before review.
Keep original failed logs, stderr and receipts. Do not overwrite issued review,
approval or receipt bytes; add a distinct correction/addendum.

Capture the new session ID from the actual `thread.started` JSONL event and
confirm the corresponding native session/settings record, including cwd, model,
effort, approval policy and sandbox. A requested model, an invented roster ID or
the SSH launcher PID alone is not proof of adoption. Update the roster from
observed values and retain the original settings/session evidence privately.

Closure requires all of the following:

- Both terminal files contain actual integer exit codes (`bool`, null and a
  prospective value do not qualify), with their recorded process IDs and UTCs.
- The exact CLI, wrapper and outer processes and their owned descendants are
  absent; check birth/command identity rather than killing a reused PID or
  unrelated process. Linux lifecycle settlement is separate evidence.
- The sealed source HEAD, report, bundle, owned-file diff and hashes agree;
  required source checks have actual command exits and retained matching logs.
- Root reviews the candidate and records remaining failures/native limitations.

`0/0` plus these checks closes a successful source task. A deadline termination,
signal exit, missing receipt, failed build or unfinished check remains partial or
failed. A useful partial source bundle can be reviewed conditionally without
renaming its wrapper outcome. Source fixtures and a closed Mac session do not
qualify ordinary native AUTO, restart, recovery, availability or deployment.

After closure, give follow-up work a new phase, protected checkout, prompt,
deadline and **new session ID**. Import the reviewed predecessor bundle and a
short durable handoff. Preserve old phase directories, failures and approvals;
do not resume the predecessor, dispatch into its expired INBOX, or leave a paid
session waiting for another assignment.

## Verified private evidence pointers

The paths below are outside Git and contain original H041 orchestration evidence:

```text
/Users/agent/Documents/LLMServer/orchestration/tasks/H041-20261001/
  launch-source-10.py
  A-compaction-completion-10/native-wrapper.py
  A-compaction-completion-10/outer-waiter.py
  A-compaction-completion-10/COORDINATOR-LAUNCH.json
```

Worker copies use the corresponding phase under
`/Users/agent/CodexProjects/llm-orchestration/H041-20261001/` on the named Mac.
Use the latest [worker roster](../reports/h041-worker-sessions.json) and final
handoff to locate actual closure receipts. These pointers document the verified
mechanism; they do not grant a new execution window or live GO.
