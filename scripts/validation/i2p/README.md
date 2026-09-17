# I2P hosted disposable Linux interface

The coordinator selected a fresh GitHub Actions `ubuntu-24.04` VM for each job.
There is no persistent Mac guest, SSH key, SSH port, disk image, shared host
directory, QMP socket or local VM process. GitHub owns VM creation/disposal;
this harness owns only uniquely named temporary files, transient units and one
file-backed loop device inside that VM. No production server is contacted.

## Launch, observe, collect and stop

1. Review changes on an isolated `milestone/i2*` branch. Run the local commands
   below, scan changed files for secrets and verify credential-free remotes.
   Push through the existing GitHub credential helper. Changes to this workflow,
   its scripts or `tests/validation/` trigger the dedicated workflow. Checkout
   copies the exact event commit; `persist-credentials: false` keeps Git auth
   external. Report-only changes do not trigger a new I2P run.
2. Identify the exact run for that source commit:

   ```bash
   gh run list --repo djeZo888/mixed-memory-llm-api-server \
     --workflow i2p-linux.yml --commit REVIEWED_COMMIT \
     --json databaseId,headSha,status,conclusion,url
   ```

3. Observe, rerun the same commit in a fresh VM, or cancel only that owned run:

   ```bash
   python3 scripts/validation/i2p/runnerctl.py status --run-id RUN_ID --head REVIEWED_COMMIT
   python3 scripts/validation/i2p/runnerctl.py rerun --run-id RUN_ID --head REVIEWED_COMMIT --dry-run
   python3 scripts/validation/i2p/runnerctl.py rerun --run-id RUN_ID --head REVIEWED_COMMIT
   python3 scripts/validation/i2p/runnerctl.py stop --run-id RUN_ID --head REVIEWED_COMMIT --dry-run
   python3 scripts/validation/i2p/runnerctl.py stop --run-id RUN_ID --head REVIEWED_COMMIT
   ```

   The wrapper verifies repository, workflow path, branch, run ID, event and
   exact SHA before acting. Completed runs cannot be cancelled. Cancellation
   uses GitHub's job lifecycle, never PID killing. Probe cleanup runs on normal
   completion/failure; cancellation or a hard timeout can skip Python `finally`.
   Transient services additionally have a 60-second runtime bound, and GitHub
   discards the entire hosted VM at job end. No persistent guest is left running.

4. Collect the current attempt's three sanitized JSON files into a **new**
   directory whose parent is private0700, owned by you and outside Git:

   ```bash
   python3 scripts/validation/i2p/runnerctl.py collect --run-id RUN_ID \
     --head REVIEWED_COMMIT --destination /absolute/private/taskroot/run-evidence
   ```

   Raw runner logs, images, sparse backing files and keys are never artifact
   inputs. The JSON artifact has14-day retention. Collection verifies filenames,
   size bounds and embedded run/SHA/attempt identity. Artifacts expire; preserve
   sanitized evidence outside Git for handoff. The report summarizes observations.
   [Artifacts documentation](https://docs.github.com/en/actions/tutorials/store-and-share-data).

## Actual execution boundary

`run.py --dry-run` describes scope without needing Linux or creating resources.
The workflow then runs it with passwordless sudo and an explicit, minimal
environment. The mutation path refuses missing hosted-runner acknowledgment,
wrong repository, invalid run/SHA metadata, non-Linux/non-root, non-Ubuntu24.04,
non-amd64, non-systemd PID1, missing cgroupv2/loop tools and low temporary space.
These are accidental-misuse guards, not cryptographic proof against a hostile
root user. The workflow's fixed `runs-on` and lack of a `container:` stanza
establish the authorized VM boundary; do not spoof those guards on another host.

Actual primitives:

- Two fake-package process trees run inside bounded transient systemd services.
  A child launcher exits normally or self-SIGKILLs; its descendant remains in the
  same cgroup and holds an exclusive flock while a harmless supervisor remains
  MainPID. After exact InvocationID/cgroup/process-start identity verification,
  stopping the owned unit removes its cgroup and permits lock reacquisition.
- An exclusive64MiB sparse backing file is attached to a newly allocated loop.
  The loop's exact backing identity, absence of signatures/mounts/holders and
  exclusion from root ancestry are checked before formatting. The test mounts
  its own ext4 filesystem, checks identity/UUID and marker contents, then
  identity-checks unmount/detach. The root disk is never a formatting candidate.

No apt transaction, package installation, NVIDIA/GPU/runtime/model work, host
boot change, network listener, privileged container or existing guest edit occurs.
The generated files are0700 directories/0600 files. Services receive no workflow
credentials and write no application journal output. Sparse backing files are
preserved for the job lifetime; cleanup detaches only the exact recorded loop.

## I2R / I2S continuation

Review and integrate source first; do not fetch a floating task branch at runtime.
Add the reviewed package-watcher or storage integration case on an isolated
milestone branch, retaining `run.py` capability gates and the exact source SHA.
Use the new job's private work directory and the primitive identity patterns;
never select a disk by enumeration order or accept arbitrary device input.
Run integration within the same bounded workflow after its capability check.
The existing `systemd_probe.run(workdir, run_id)` and
`loop_probe.run(workdir, run_id)` return JSON PASS/FAIL and clean owned resources.
The main harness treats either FAIL or cleanup ambiguity as failure.

I2P proves Linux primitives only. It does **not** call I1R's package watcher,
borrowed-lease implementation, policy restoration or I1S disk provisioning.
Those cases, real package installation, full amd64 installer and GPU/reboot
acceptance stay **NOT_TESTED** until their own reviewed code actually runs.

## Local verification

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests/validation -p 'test_*.py' -v
python3 scripts/validation/i2p/run.py --help
python3 scripts/validation/i2p/run.py --dry-run
python3 scripts/validation/i2p/runnerctl.py --help
git diff --check
```

Local safety/refusal fixtures do not claim Linux validation. Successful hosted
evidence must separately show actual OS/architecture/PID1/cgroup, both transient
service cases, sparse/allocation bytes, exact loop filesystem identity, cleanup,
source hashes, run URL/SHA and observed image version. `ubuntu-24.04` is rolling;
GitHub does not expose an immutable full-VM checksum pin for this interface.
