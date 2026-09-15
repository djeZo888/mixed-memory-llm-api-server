# I2S independent source and fixture review

Reviewed source at `e6c77debb4989ada0c7a563159f8df45aa89f7b5`, together with
taskroot `I1S-REVIEW.md`, `I1S-HANDOFF.md` and `incoming.md` revision 1. This
review itself performed no privileged operations, disk changes or hosted runs.

## Execution scope

The exact shipped `tests/install/loop_disk_transaction.sh --dry-run`, followed
by `--apply`, is appropriate **only within the approved I2P-guarded ephemeral
GitHub-hosted Ubuntu 24.04 job**. The wrapper rejects external device arguments,
creates its own 256 MiB backing and loop, and requires a different private mount
namespace (`loop_disk_transaction.sh:42-60,130-143`). Its scratch is private
root-owned `/run` storage, and cleanup validates the recorded backing, owned
partition/mount UUID and sysfs bind before scoped unmount/detach/removal
(`:79-123`; `loop_disk_transaction.py:53-155`). No command authorizes a physical
device, existing service, package installation or production storage operation.

The shipped ownership check binds the current backing pathname's inode, device
and size to its record, then verifies the loop pathname association, zero offset,
zero size limit, loop major and sysfs backing path (`loop_disk_transaction.py:75-113`).
It does **not** independently compare kernel `BACK-INO`/`BACK-MAJ:MIN` against
the record or retain a loop descriptor. That narrower evidence is not equivalent
to I2P's direct loop/backing inode proof (`scripts/validation/i2p/loop_probe.py:154-171`).
The difference does not block running the already reviewed, internally allocated
fixture: the root-owned 0700 scratch and unchanged recorded inode prevent an
ordinary-user pathname substitution, and the fixture never replaces its backing
after allocation. Do not claim resistance to an independent privileged actor or
direct kernel backing-inode equality for the shipped wrapper. New I2S fixtures
should include that stronger equality. No shipped helper is patched or bypassed.

## Real-tool and recovery boundaries

- `DiskIO` passes inherited block and disk-lock descriptors to child commands and
  retains real exclusive-use probes. The probes are released before real tools
  claim devices; there is no force-format or busy-check bypass
  (`scripts/install/disk_init.py:150-178,228-253,373-411`). Actual
  `/proc/self/fd`, `sfdisk --lock=nonblock`, BLKRRPART, udev, UUID mounting and
  e2fsprogs compatibility still require the hosted run.
- The shipped fixture injects a Python exception **after successful tool exit**
  for sfdisk and mkfs, before their durable receipt (`loop_disk_transaction.py:288-319`).
  This is not parent SIGKILL, cancellation or interruption while a tool is active.
  Mount and registration interruptions need additional new fixtures.
- The production validator checks both raw GPT headers/arrays/CRCs and exact
  geometry, ext4 UUID/label/4096-byte blocks/zero reserve, and read-only fsck
  (`disk_init.py:303-371,401-403,640-665`). Record actual output and versions;
  regular-file synthetic metadata tests cannot supply Linux tool evidence.
- The shipped completed replay compares journal/fstab and mutation counters but
  does not snapshot registry bytes or write a payload sentinel
  (`loop_disk_transaction.py:326-329`). New matrix evidence must include both.
  Missing completed mount, fstab or registry is a refusal, not automatic success
  restoration (`disk_init.py:668-693`).
- Direct `transaction_lock` ownership is disk-local (`disk_init.py:557-584`).
  It does not establish canonical global admission, exclude other storage modes,
  or provide an autonomous child deadline after initializer SIGKILL. I1O remains
  a distinct required gate. A separately named harmless process adapter may
  demonstrate inherited disk-lock lifetime; it cannot prove real disk-tool
  descriptor retention or integrated canonical ownership.
- Test serial/by-id/root adapters and injected topology drift as fixture
  discovery. The shipped runner deliberately filters global UUID discovery to
  its loop (`loop_disk_transaction.py:277-280`); do not label this production
  root exclusion or global duplicate-device discovery.

## Local verification

Command, as an ordinary macOS user:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests/install -p 'test_disk_*.py' -v
```

**35 tests run: 34 PASS, 1 ERROR.** Existing
`test_timeout_accounts_for_descendant_after_process_leader_exits` errors in its
final redundant cleanup `os.killpg(leader.pid, SIGKILL)` at
`tests/install/test_disk_transaction.py:667`: `PermissionError: [Errno 1]
Operation not permitted`. The error is not concealed or reclassified as a skip.
The test's first timeout cleanup and lock reacquisition precede that final cleanup
in source; the observed traceback identifies only the final cleanup. This does
not establish why macOS returns EPERM, and the source is outside I2S ownership.
Report it to the coordinator instead of changing it here. All four regular-file
metadata tests passed. No actual Linux claim derives from these local results.

New I2S source/safety tests, syntax checks, dry-run checks, hosted SHA/run results
and final artifact hashes are recorded separately by the execution report.

## Single hosted job launch

The existing I2P workflow watches `tests/validation/**`. To avoid an extra actual
I2P job, push the complete reviewed I2S source/tests in a commit containing
`[skip ci]`, then push a separate marker-only commit changing the dedicated new
I2S launch path. The new I2S workflow should match the exact feature branch and
marker path, retain minimal permissions and pinned actions, scrub the sudo
environment, and reuse the I2P guard. No existing workflow needs modification.
The hosted checkout SHA is the **marker commit**; list the earlier implementation
commit separately and compare source manifests. Create the requested full bundle
immediately after the source commit and refresh the final bundle to include the
tested marker and reporting commits.

**Next action:** complete new bounded fixture guards and local safety review,
then execute the approved actual Linux matrix once. Keep production root/device
discovery, canonical admission/deadline, actual packages/GPU/models and reboot
acceptance outside any fixture PASS claim.

## Final new-harness review disposition

Reviewed new `run.py`, `runnerctl.py`, `loop_matrix.py` and
`.github/workflows/i2s-linux.yml` before publication. The shipped wrapper is
tracked executable (`100755`), so its internal `unshare` execution remains valid
when the outer runner invokes it through Bash. The new workflow selects only
`milestone/i2s-storage-linux` and `scripts/validation/i2s/launch.json`, pins both
actions, uses read-only repository permission, clears the sudo environment and
disables persisted checkout credentials. Collection reuses the existing `gh`
helper; exact repository, workflow, branch, push event, SHA and artifact identity
checks precede extraction of the three fixed JSON filenames.

One blocking orchestration defect was found and corrected before publication:
the namespace child initially returned after an uncertain cleanup without
persisting its stop reason, permitting the parent to continue into new loop
allocations. The final runner persists the stop reason before returning and the
parent independently requires explicit cleanup PASS from both namespace probes
before it can launch the extended matrix. Missing reports and all unrecognized
cleanup statuses stop execution. A production test failure with confirmed owned
cleanup stays FAIL while allowing independent tests to proceed; it is not
converted to success. Regression tests exercise the early return and missing or
uncertain cleanup reports. Independent rerun:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests/validation -p 'test_i2s*.py'
```

**61 I2S portable source/safety tests PASS**, including the 15 new process adapter
safety tests. This does not replace the separately recorded existing installer
test error above. Process adapters call the unchanged `DiskIO.command` and
`transaction_lock`; harness cleanup uses PID/starttime checks plus Linux pidfds,
and never sends a broad group signal. The real production command's caught-error
group handling remains the code under test. The child self-exit bound is supplied
by the harmless adapter, not a production autonomous deadline.

Extended loops add direct kernel backing-inode/filesystem equality, retain the
real tool exclusive-use checks and source validators, and allocate at most six
256 MiB cases sequentially. Including the one shipped fixture, aggregate backing
is bounded at **1,792 MiB**. Unknown loop ownership preserves scratch and stops
further allocation. Expected tool/refusal failures remain failed evidence;
unchanged production `DiskIO.command` does not expose a failing tool's exact
exit code, which the new command records explicitly acknowledge.

**Disposition: no remaining blocking source-review finding for the approved
disposable hosted execution.** Actual Linux results, exact tested SHA and artifact
hashes must still come from that run. The current writer path defect, canonical
admission/deadline, role-aware storage conversion and production device/root
discovery are not cleared by this source review.
