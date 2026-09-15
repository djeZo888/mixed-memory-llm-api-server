# I1R — package process ownership

Date: 2026-09-15. Worker: Mac-Worker1 (Darwin, Python 3.14.7).
Base: `722050fdcb6de4a9f56a5488b705998a1d82ce85`.
Branch: `milestone/i1r-package-process-ownership`.

**Status: bounded SOURCE fix complete; parent review and I1b integration required.
Production execution is not approved by this report.**

## Problem and resulting behavior

The previous package timeout waited only for apt. Surviving dpkg/maintainer
processes could outlive both policy-rc.d inhibition and the CLI's lifecycle flock.
A crashed CLI left only saved policy bytes, without durable process ownership.

The mutating package path now uses a uniquely named, root-managed transient
systemd service. Before the service can exec apt, the installer persists its exact
identity and transfers continued custody of the existing lifecycle lease to a
detached watcher. The watcher shares the original flock open-file description;
it never acquires another lock or explicitly unlocks the borrowed description.
Recovery restores policy only after exact transaction quiescence and a clean
`dpkg --audit`. Package/version postconditions remain the caller's responsibility.

## Execution and recovery contract

1. Recover any earlier marker under the canonical lifecycle lease. Validate the
   borrowed descriptor before creating a new inhibitor or package service.
2. Persist schema-v2 marker with original policy bytes/mode and allocated UUID,
   unit name and boot identity. Install the inhibitor. Start only a waiting
   Python gate worker; no apt process exists yet.
3. Observe and persist the manager's InvocationID, exact cgroup path and inode.
   Start a detached watcher outside that cgroup, inheriting the same lease FD.
   The package gate cannot open until the watcher acknowledges initialization.
4. Atomically write the execution gate on verified data storage. The service
   checks its own InvocationID before exec of `/usr/bin/apt-get` with a controlled
   environment. No package output is forwarded through the CLI or journal.
5. Observe recursive `cgroup.events` population plus the exact retained manager
   invocation. Failed units with populated cgroups remain live. Missing manager
   identity, boot mismatch, reused inode, malformed fields and inspection failures
   are unknown, never proof of exit.
6. On error/interruption, terminate only through `cgroup.kill` opened relative to
   the pinned, identity-validated cgroup directory. Replacing its pathname cannot
   redirect that FD to another cgroup. No PID, broad pattern, shared service or
   unit-name kill is used. The systemd deadline also survives CLI SIGKILL.
7. Restore original bytes and permission bits only after confirmed quiescence and
   clean audit; fsync policy retirement, remove execution gate, then retire marker.
   An interrupted restoration can be retried. Unclean audit retains a repair
   checkpoint; no unpinned automatic `dpkg --configure -a` is introduced.

Service settings are `Type=exec`, `ExitType=cgroup`, `RemainAfterExit=yes`,
`CollectMode=inactive`, `Restart=no`, `KillMode=control-group`, `SendSIGKILL=yes`,
`RuntimeMaxSec=<timeout>`, `TimeoutStopSec=5`, `Delegate=no`, null stdout/stderr.
No `--collect`, `systemctl stop` or `reset-failed` discards evidence before
recovery. Retained terminal unit metadata is intentionally left for review;
there is no automatic unit garbage-collection operation in this fix.

A missing kernel cgroup is accepted only with the exact retained terminal
invocation and `MainPID=0`: the manager may remove an empty cgroup. A missing
unit is always unknown. `ExecMainPID` is historical and never authorizes signaling
or liveness decisions. The watcher retains the lease on unknown inspection,
even after the package processes have exited, until evidence becomes available.

### Safe recovery statuses

| Status/code | Required next action |
| --- | --- |
| `package_scope_live_recovery_required` | Keep inhibitor/marker; allow the owned manager deadline to finish; retry after exact quiescence. |
| `package_ownership_unknown`, `package_ownership_incomplete`, `package_ownership_marker_missing` | Preserve evidence and inhibition. Inspect recorded unit, invocation, boot and cgroup under operator review. Do not infer ownership from a PID or delete the marker to proceed. |
| `package_database_repair_required` | Scope is quiescent, but dpkg needs review. Retain checkpoint/inhibitor; review a pinned repair through the owned boundary. |
| `existing_policy_changed` | Preserve externally changed policy; reconcile it with the recorded original before recovery. |
| `package_transaction_recovery_required` | Canonical admission is blocked by pending marker/gate or orphan inhibitor. Select explicit recovery under the same lease, then recheck admission. |
| `package_borrowed_lifecycle_lease_required` | Integrate the caller's canonical borrowed lease; do not create a fallback lock. |

Legacy schema-v1 markers have no trustworthy scope identity and fail closed.
A crash before identity persistence also fails closed, even though its gate worker
cannot have started apt. These conditions need operator reconciliation, not an
automatic conversion into successful package state.

## Exact I1b caller API

**I1R2 correction:** import the reviewed lease module canonically and validate
the expected root/UID before exporting. This example documents the internal
caller contract; I1c still owns production admission and storage handoff glue.

```python
import os
from common.lifecycle_lease import (
    acquire_lease, _validate_borrowed_lease, _export_package_watcher_fd,
)
from install.core import Runner
from install.prerequisites import Prerequisites, assert_package_admission

with acquire_lease() as lease:  # production canonical root/UID defaults
    _validate_borrowed_lease(lease)  # same expected production scope
    exported_fd = _export_package_watcher_fd(lease)
    try:
        runner = Runner(writable=True, package_lease_fd=exported_fd)
        packages = Prerequisites(config, runner, storage_guard)
        packages.recover_policy()  # before admission / completed-stage checks
        assert_package_admission(config["data_dir"], storage_guard)
        packages.package_transaction(
            ["apt-get", *reviewed_data_backed_apt_options, "--no-download", "--yes",
             "--no-install-recommends", "--no-remove", "install", *exact_version_pins],
            timeout=3600, env=reviewed_package_environment,
        )
        # Verify versions/postconditions and finish ALL later stages using runner
        # inside this try, with admission before each ordinary mutation.
    finally:
        os.close(exported_fd)  # before outer lease exit; NEVER LOCK_UN
```

The caller owns `exported_fd`; Runner borrows it and does not close it. Keep it
open throughout Runner's **entire package-use scope**, including failure cleanup
and later transactions/stages. `run_package()` validates it after watcher READY;
closing it at READY is premature and fails with
`package_borrowed_lifecycle_lease_invalid`. `package_identity()` and
`prepare_package()` also reuse it. The watcher inherits its own duplicate of the
same flock open-file description and retains it independently until exact
quiescence. Neither caller nor watcher may use `LOCK_UN`; no reopened lock or
raw-FD Manager capability replaces the canonical export.

L1's read-only admission API requires no installer config or versions lock:

```python
from install.prerequisites import assert_package_admission
# Inside the canonical lease, before every ordinary mutating transition:
assert_package_admission(registered_data_dir, storage_guard)
```

This checker returns `None` only with no pending marker/gate or orphan inhibitor;
otherwise it raises `package_transaction_recovery_required`. Even a quiescent
marker blocks until explicit recovery has restored policy and retired the marker.
It acquires no lease, executes no package commands, and restores nothing. An
explicitly selected recovery operation runs `recover_policy()` under the same
canonical lease before repeating admission. Watcher export uses L1's validated
internal close-only descriptor export, not raw-FD borrowing by its Manager.

Public signatures:

- `assert_package_admission(data_dir, storage_guard, *, policy_path=None) -> None`.
- `Runner(writable=False, *, package_lease_fd=None, package_scope=None)`;
  existing `run(argv, *, timeout=120, env=None)` signature preserved.
- `Prerequisites(config, runner, storage_guard, lock_path=None, *, policy_path=None)`.
- `Prerequisites.package_transaction(argv, *, timeout=120, env=None)` and
  `Prerequisites.recover_policy()`.

`config["data_dir"]` derives one shared `services/installer` state directory,
`package-service-policy.json` marker and `package-execution-gate.json` gate.
The production policy path stays `/usr/sbin/policy-rc.d`. `package_scope` and
`policy_path` injection support disposable tests, not a production fallback.
Callers supply an already-reviewed pinned command and data-backed apt options.
The base/driver mutating calls use this same boundary; container stages must reuse
it. Plain Runner apt/dpkg mutation commands are refused; existing update,
simulation and download-only preparation shapes are parsed exactly.

**Integration gap:** existing I1 `main.py` does not bind the borrowed descriptor,
so real package mutation now refuses until I1b wires it. I1b/L1 must preserve
close-only lease release and reconcile this marker at every canonical mutation
admission, including completed-stage paths and recovery if the detached watcher
itself is externally lost. No second lifecycle owner was implemented. The
watcher covers hard CLI-parent death; this source task does not claim global
admission integration or protection against an operator killing all owners.
The early API was published in `../package-transaction-api.md`; the container
reuse requirement in `../coordination-input.md` was incorporated and rechecked.

## Verification and evidence classes

Final source commands on Mac-Worker1:

| Check | Result |
| --- | --- |
| `python3 -B -m unittest discover -s tests/install -p 'test_*.py'` | **PASS: 134 tests**, 32.204 s |
| Existing installer coverage within that suite | **PASS: 90 tests**; relevant fake runner and two recovery markers updated for owned v2 identity |
| New `test_package_processes.py` | **PASS: 17 real POSIX process/lease tests**, included above |
| New `test_package_systemd.py` | **PASS: 27 mocked adapter tests**, included above |
| `python3 -B -m unittest discover -s tests/lifecycle -p 'test_*.py'` | **PASS: 116 tests**, 4.010 s |
| `python3 -B -m unittest discover -s tests -p 'test_agent*.py'` | **PASS: 75 tests**, 4.400 s |
| Compile changed Python source/fixtures without emitting bytecode | **PASS** |
| AST comparison to base: `core.exclusive`, shared protected/atomic/read helpers, `State`, prerequisite `protected_path`/`atomic_bytes` | **PASS: unchanged** |
| Scope diff, `git diff --check`, grep-based secret scan, credential-free remote check | **PASS** |
| Post-suite process inventory | **PASS: no live package fixture/worker matches** |

Real POSIX cases use an independent, token-authenticated disposable supervisor,
a real fake apt parent, and a real child with output redirected away from captured
pipes. They cover normal completion, nonzero exit, parent timeout with a child
ignoring SIGTERM, CLI SIGKILL, SIGINT, recovery while live and after exit, unknown
inspection retaining the lease after exit, reused identity refusal with a live
unrelated process, opaque policy bytes/mode, absent policy, audit repair,
legacy/missing/incomplete records, missing lease, missing READY, and SIGKILL during
the READY handshake. Additional architecture windows cover CLI death before any
watcher exists, after READY but before gate opening, and death of the actual
CLI-owned watcher followed by CLI death while the fake apt descendant remains.
A fresh lease holder is still refused admission with a live or quiescent pending
marker; only explicit recovery clears it. Cleanup asserts no live fake package descendants remain.
The fixture supervisor's process group is deliberately not a production backend.
Its discovery/audit answers and forced inspection outage are synthetic.

Adapter tests mock every systemctl/systemd-run command and use ordinary temporary
files for cgroup.events/cgroup.kill. They check retained unit settings, identity,
PID semantics, empty fields, liveness, gate/env restrictions, inode reuse, pinned
FD behavior, duplicate population fields, timeout refusal, and command boundaries.
They do **not** exercise the Linux kernel cgroup manager.

Additional check warning: broad `unittest discover -s tests -p 'test_*.py'`
returned two import errors (`lifecycle.manager`) from the discovery namespace
collision between `tests/lifecycle` and `scripts/lifecycle`. The separate lifecycle
suite and explicit agent fixture suite above pass. Unrelated discovery layout was
not modified. No passing aggregate result is claimed for that broad invocation.

**NOT_TESTED:** actual Ubuntu 24.04/systemd 255/cgroup-v2 execution, kernel
cgroup.kill semantics, real apt/dpkg/maintainer scripts or audit, I1b canonical
lease/admission integration, fresh-host installation, reboot or production
acceptance. No disposable Linux target was available through this task's local
execution environment. No ai-vm access, real apt, host service change, disk
mutation, model work or download interference occurred.

## Source basis and next action

Ubuntu Noble documents the chosen [service lifecycle and runtime deadline](https://manpages.ubuntu.com/manpages/noble/man5/systemd.service.5.html),
[whole-control-group termination](https://manpages.ubuntu.com/manpages/noble/man5/systemd.kill.5.html),
and [retained unit collection semantics](https://manpages.ubuntu.com/manpages/noble/man5/systemd.unit.5.html).
The [kernel cgroup-v2 documentation](https://www.kernel.org/doc/html/v6.14/admin-guide/cgroup-v2.html)
describes recursive population and cgroup.kill; [flock documentation](https://man7.org/linux/man-pages/man2/flock.2.html)
describes inheritance of the same open-file description across fork.
[systemctl show](https://manpages.ubuntu.com/manpages/noble/man1/systemctl.1.html)
and [systemd D-Bus properties](https://manpages.ubuntu.com/manpages/noble/man5/org.freedesktop.systemd1.5.html)
support `--all` and the distinction between MainPID and historical ExecMainPID.
These are design sources, not execution evidence.

Next: parent reviews this commit/bundle; I1b integrates the public boundary and
canonical admission contract; run real systemd/cgroup acceptance with disposable
fake packages on a disposable Ubuntu 24.04 host. Full installation remains
fail-closed. No production use is authorized by the passing Mac fixtures.
