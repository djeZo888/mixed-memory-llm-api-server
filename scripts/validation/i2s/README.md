# I2S disposable Linux storage matrix

This source runs only in a fresh GitHub-hosted Ubuntu 24.04 amd64 VM after the
reviewed I2P context/capability guard. The Mac performs source and safety checks.
There is no SSH, physical-device argument, package install, model/image download,
production storage access, service activation or reboot.

## Review and launch once

1. Review all new I2S source/tests and the exact unchanged I1S loop wrapper.
   Run the local commands below and a filename-only changed-file secret scan.
2. Commit source/tests/workflow with `[skip ci]`, immediately create a full
   `I2S.bundle`, and push only `milestone/i2s-storage-linux` using existing gh
   authentication. The first push deliberately triggers no workflows.
3. Add `scripts/validation/i2s/launch.json` with the reviewed implementation SHA
   and scope. Commit and push that marker separately. This triggers one actual
   I2S job without changing the old I2P workflow's watched paths. The marker
   commit is the actual tested SHA. Refresh the full bundle after that commit.
4. Observe the exact run and collect its sanitized artifact outside Git:

```sh
gh run list --repo djeZo888/mixed-memory-llm-api-server \
  --workflow i2s-linux.yml --commit TESTED_SHA \
  --json databaseId,headSha,status,conclusion,url
python3 scripts/validation/i2s/runnerctl.py status --run-id RUN_ID --head TESTED_SHA
python3 scripts/validation/i2s/runnerctl.py collect --run-id RUN_ID --head TESTED_SHA \
  --destination /absolute/private/taskroot/evidence/RUN_ID
```

The collection parent must already be private0700 and owned by the caller. The
collector reuses I2P's existing `gh api` interface, checks exact workflow/branch/
run/SHA/attempt and rejects unexpected ZIP paths or oversized files before writing.
No auth-file reads or raw environment/log dumps occur. The artifact contains only
`evidence.json`, `source-manifest.json`, and `plan.json`, retained for14 days.

## Actual scope and evidence

`run.py --apply` repeats I2P's real Ubuntu/VM/systemd/cgroup/loop capability check,
records actual tools/kernel/image versions, and calls the **unchanged** shipped
`tests/install/loop_disk_transaction.sh --dry-run` before its `--apply`.
The source review of that exact scope is recorded in the I2S review report.
Its return code, bounded output and independent parent-namespace cleanup
observations are preserved even on failure.

New loop cases use at most six sequential256 MiB sparse files, plus the shipped
256 MiB allocation:1792 MiB aggregate, below the2 GiB budget. Backing files live
on existing `/run` tmpfs. The stronger new guard checks kernel loop backing
inode/device and zero offset/size limit before mutations and cleanup. Actual
GPT/ext4 tool commands, `/proc/self/fd` descriptors, busy checks, fsck and UUID
mounting retain production behavior. Loop type/serial/root and drift observations
are explicit fixture adapters. Production root exclusion is not proved.

Writer cases use three sequential16 MiB blank tmpfs filesystems and only their
scratch descendants. They establish a valid preflight/anchor before a same-device
nested bind, check an unrelated Docker-style sibling, and detach before/during a
real anchored write. The actual kernel mount table is used; the registration and
Storage discovery snapshot are fixture-owned. No real Docker/model mount is used.

The process adapter invokes real `DiskIO.command` and `transaction_lock`, kills
one exact owned initializer while its harmless child is live, and checks the
disk-local lock lifetime. It is separate from exceptions injected **after** real
disk tool completion. It does not establish real disk-tool harddeath behavior,
canonical global admission or the pending I1O autonomous child deadline.

Every ambiguous cleanup fails and preserves state. Outer output/deadline bounds
stop further cases and leave unknown ownership for whole hosted-VM disposal;
that is reported INCOMPLETE, never successful scoped cleanup. No broad kill,
unmount, reset or prune is used. Workflow and stage bounds also limit the job.
A production defect is reported to the coordinator and is never patched here.

## Worker-local checks

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests/validation -p 'test_i2s*.py' -v
python3 scripts/validation/i2s/run.py --dry-run
python3 scripts/validation/i2s/loop_matrix.py --dry-run
python3 scripts/validation/i2s/writer_probe.py --dry-run
python3 scripts/validation/i2s/process_probe.py --dry-run
bash -n tests/install/loop_disk_transaction.sh
git diff --check
```

These do not execute Linux disks/mounts on the Mac. See the source-review report
for the existing local disk-suite cleanup error. Actual hosted results, warnings,
failures and NOT_TESTED gates belong in the execution report. No skip or expected
failure becomes PASS. Fresh production installation, package/GPU/model/image
installation, physical4Kn and reboot remain NOT_TESTED.
