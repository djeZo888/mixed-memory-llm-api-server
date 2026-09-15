# I2SF bounded disposable Linux fixture rerun

This follow-up runs only in a fresh GitHub-hosted Ubuntu 24.04 amd64 VM after the
existing I2P context/capability guard. The worker performs source and ordinary-user
safety checks. The approved scope is the shipped loop fixture's dry-run, apply and
cleanup, plus focused fixture/orchestrator source safety tests. No physical-device
argument, package installation, model download, service activation or reboot is
part of this task.

## Review and launch once

1. Review the changed fixture, focused tests, orchestrator and workflow. Run the
   local checks below, whitespace/scope/metadata checks and a filename-only secret
   scan of changed files. Preserve the initial I2S failure separately.
2. Commit source/tests/workflow with `[skip ci]`, create a verified full
   `I2SF.bundle`, and push only `milestone/i2sf-loop-fixture` through the existing
   gh credential helper. Confirm the remote contains no credentials before push.
3. Update `scripts/validation/i2s/launch.json` with the reviewed implementation SHA
   and exact affected scope. Commit and push that marker separately. Its path is
   the sole trigger of the I2SF workflow; the marker commit is the tested SHA.
   Do not repeat the marker push to request a broader matrix. Refresh the bundle.
4. Observe the exact run and collect the sanitized artifact outside Git:

```sh
python3 scripts/validation/i2s/runnerctl.py status --run-id RUN_ID --head TESTED_SHA
python3 scripts/validation/i2s/runnerctl.py collect --run-id RUN_ID --head TESTED_SHA \
  --destination /absolute/private/taskroot/evidence/RUN_ID
```

The collector defaults to the exact `milestone/i2sf-loop-fixture` branch. Reading
historical I2S runs requires `--branch milestone/i2s-storage-linux`. The collection
parent must already be caller-owned and private (0700). The collector reuses
I2P's gh API helper and checks exact workflow/branch/run/SHA/attempt. It rejects
unexpected ZIP paths or oversized files. Do not read auth files or dump raw
environments/logs. The artifact contains only `evidence.json`,
`source-manifest.json`, and `plan.json`, retained for 14 days.

## Actual scope and evidence

`run.py --apply --affected-only` repeats the actual I2P Ubuntu/VM/systemd/cgroup/
loop capability guard and records kernel/image/tool versions, including wipefs.
It calls the actual shipped `tests/install/loop_disk_transaction.sh --dry-run`
then `--apply`. The fixture owns one 256 MiB sparse backing file under protected
`/run` scratch. The existing aggregate ceiling is 2 GiB; this bounded rerun's
single allocation is 256 MiB.

The reviewed fixture diagnoses the exact private device node before transactions.
Conditional device-capable tmpfs is restricted to this fixture's own `root/dev`
inside its private mount namespace. The production implementation and real
signature/busy checks remain active. The fixture records exact backing and loop
identity before mutation and cleanup. Unknown ownership preserves scratch.

The orchestrator independently snapshots the original parent mount namespace,
loop associations and exact `/proc/self/mountinfo` bytes before and after the
shipped invocation. Evidence records equality and before/after mountinfo hashes
without copying the host mount table. Any parent change, new retained scratch,
uncertain cleanup or shipped command failure stops the run. A successful cleanup
observation cannot turn failed apply into PASS. This also applies to the retained
legacy matrix path.

`--affected-only` ends after shipped fixture success and parent verification.
Writer/process namespace probes and the extended loop matrix remain NOT_TESTED.
The retained legacy code is not authorized by this bounded follow-up and is never
invoked by the I2SF workflow. Physical 4Kn, pending I1O lifetime/admission cases,
I1c Storage role behavior, package/GPU/model installation and reboot remain
NOT_TESTED. No skip or expected failure is counted as PASS.

A production failure stops the job with sanitized source and return-code evidence;
this task must not patch production code. Output/deadline breaches preserve
uncertain ownership for whole hosted-VM disposal and report incomplete cleanup.
There is no broad kill or unmount operation.

## Worker-local verification

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests/validation -p 'test_i2s_runner.py' -v
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests/install -p 'test_loop_disk_fixture.py' -v
python3 scripts/validation/i2s/run.py --dry-run --affected-only
bash -n tests/install/loop_disk_transaction.sh
git diff --check
```

These are source/refusal checks and do not establish actual Linux disk behavior.
Keep source-test results, initial run 34916701374 failure, and new hosted evidence
separate in the I2SF report. Include exact tested source hashes, run URL, artifact
identity, cleanup status, warnings and the next action.
