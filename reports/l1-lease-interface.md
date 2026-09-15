# L1 early canonical lease interface

Status: **PASS — 37 portable worker lease tests; integration remains open**.
Branch: `milestone/l1-registered-lifecycle`.
Prepared base: `5612f2aabef05d4ca6383e504b7c0fe66c0dcb45`.
This early source publication lets I1R/I1b consume and review the lease while
registered Manager/writer integration continues in the same bounded L1 task.

Canonical import: `common.lifecycle_lease` with reviewed `scripts` on sys.path.

- `acquire_lease(*, blocking=True, system_root=Path('/'), trusted_uid=0)` context
  yields active `LifecycleLease`; `lease.validate()` checks same-process minted
  provenance, trusted canonical inode and live private owner descriptor.
- `blocking=False` atomically attempts the same exclusive flock and raises
  `LeaseBusy`, `.code == 'lifecycle_busy'`, for future U1 HTTP409. No U1 code here.
- `_validate_borrowed_lease(lease, *, system_root=Path('/'), trusted_uid=0)` adds
  the expected caller scope check. Manager accepts only the active object.
- `_export_package_watcher_fd(lease)` validates and returns `os.dup` of the same
  open-file description. I1R retains the duplicate for the entire Runner/package-use
  scope and closes it in finally before outer lease exit, including failure.
  The watcher closes its inherited copy independently at quiescence (root revision8).
  The private owner descriptor is never exported. No raw FD can mint a
  lease or authorize Manager borrowing.
- Context cleanup closes only, never LOCK_UN. A watcher retains the same lock
  after the parent context closes or the parent is killed, until its last
  inherited descriptor closes. `transition_in_progress()` observes without
  creating paths or waiting. Fixture root/uid arguments have no CLI/env exposure.

Verification: `python3 -m unittest tests.lifecycle.test_lease -q` — 37 PASS.
Real local flock/multiprocessing/subprocess cases cover blocking competitors,
nonblocking busy/reacquire/new-file creation, invalid trusted paths/modes/inodes,
closed/stale/fabricated/wrong-PID/wrong-scope leases, owner error cleanup,
watcher retention after context exit and parent SIGKILL, failed handoff cleanup,
exported FD close/reopen on the same inode, and zero explicit LOCK_UN calls.
`git diff --check` passed. No real credentials, services, disks or packages used.

NOT_TESTED: Linux systemd/cgroup package execution, actual installer integration,
actual mount detach, boot, GPU inference, model acquisition, host installation.
I1R/I1b own their package Runner/core changes and final anchored writer. No
production apply or whole L1 PASS follows from this early interface commit.
Next action: root reviews this bundle; L1 completes registered Manager/boot/
import tests and merges the author-frozen writer/compatibility handoffs.
