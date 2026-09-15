# I1W — anchored descendant mount correction

Status: **source ready for review; L1 integration and actual Linux acceptance
remain gated**. Source-only worker, 2026-09-15, Darwin arm64 / Python 3.14.7.
Base: `c0e1a1dff0ac1647ed5207f05247ff63f72f7cc7`.

## Change

`MountedStorageGuard.check_path(path)` checks every operation component against
the captured registered mount entries, including the final file/directory and
intermediate ancestors before a nested registered model mount. Same-device
bind observations cannot pass merely because `st_dev` stayed unchanged.
`AnchoredRoot` and `GuardedFile` now use those path checks around directory/file
operations and both sides of promotion, while retaining held descriptor,
parent-name, ownership, registry-byte/inode and device checks. Unrelated Docker
descendant mounts remain allowed; existing managed-root checks stay active.

The minimal I1c role draft was consumed once after the coordination Revision2
ownership ACK. Default scope remains both roles. Data-only snapshots cannot
authorize a distinct model subtree, including a more-specific service root
inside it. Specific service roots still work when data/model roots coincide.
Models-only access through a distinct unverified data-mount ancestry is refused;
sibling model mounts remain supported. I1c still owns Storage/State/integration.

The exact public signatures and required Storage/wrapper contracts are frozen
in [writer-api.md](../docs/orchestration/writer-api.md). Mounted guard snapshots
carry `path_validation_required: true`; wrappers must forward `check_path`
while preserving their own identity checks. Missing forwarding fails closed.

## Results and evidence limits

| Check | Observed result |
| --- | --- |
| Original supplied L1 fixture with reviewed baseline writer | 9 methods: 8 passed, reported descendant regression failed |
| Final local writer suites | 67 tests: 66 passed, 1 actual-Linux test skipped |
| New focused path tests (included above) | 29 passed; synthetic mountinfo, actual local descriptor operations |
| Original L1 snapshot with only final writer overlaid | **FAIL:** 9 methods, 2 failure records and 8 error records (including layout subtests) |
| L1 mounted-guard interface tests in same snapshot | 8 passed |
| Full final installer suite | **FAIL:** 270 tests, 3 failure records, 12 error records, 4 Linux-only skips |
| Container suite with immutable baseline writer injected in memory | 23 tests: the same 2 container failures and 11 container errors reproduce |
| Actual Linux bind/mount-loss acceptance | **NOT RUN** here; delegated I2S gate |

The original L1 `_BoundMountedGuard` drops `check_path`. Its historical fixture
also projects a guard through a lambda that drops this method. Final writer
refusal therefore occurs **before** the supplied regression's mount insertion.
That method's `ok` is not evidence of a corrected L1 integration. The snapshot's
successful-path and race assertions expose the missing adapter contract. No
private-wrapper unwrapping, adapter edits, or substituted discovery were used
to manufacture a pass.

The full installer's container errors are the preexisting package-recovery
ownership block; its two failures concern policy restoration and postcondition
expectations. The final full run also recorded a package-process fixture
inspection failure and supervisor-cleanup failure on one test. These are
reported separately, not dismissed as writer success. A single-test recheck
passed with both the final writer and immutable baseline writer. The supervisor
failure did not reproduce; its exact cause remains unproven. Package/lease
source was not changed.

Machine-readable identities/counts are in
[i1w-writer-evidence.json](i1w-writer-evidence.json). Candidate writer SHA256:
`5ba1b1356519bbb4922b563662a605459862a84b81ce4f521dfbce293d97302a`.
The task-private baseline/final logs and comparison JSON are retained beside
the isolated checkout for root review. The provided L1 archive SHA256 was
verified as `a7d6963d5a414a833d9a80b894d860ddfe64246a39fbeba79ada40ebf373cd2a`;
every extracted source file except the overlaid writer still matches it, and
the supplied test is unchanged. The archive is uncommitted L1 test dependency,
never a merge or deployment input.

## Reproduction

From this checkout (no host configuration, disk or service operation):

```sh
python3 -B -m unittest discover -s tests/install -p 'test_storage_io*.py' -v
python3 -B -m unittest discover -s tests/install -v
git diff --check
```

For the supplied L1 dependency, verify its SHA256, extract into a task-private
protected directory, copy the supplied test to `tests/lifecycle/test_real_storage_io.py`
if necessary, and overlay **only** this candidate's `scripts/install/storage_io.py`.
From that private extraction:

```sh
python3 -B -m unittest discover -s tests/lifecycle -p test_real_storage_io.py -v
python3 -B -m unittest discover -s tests/lifecycle -p test_mounted_guard.py -v
```

These are actual implementation tests with explicit synthetic mount discovery;
they are not Linux mount tests. The existing optional namespace test skips on
this Darwin worker. No ai-vm access, host mount/format, package installation,
service activation, model download, or reboot was performed.

## Next required action

1. Root reviews this bounded writer/API/test commit. L1 implements public
   `check_path` forwarding through its identity/error adapter and updates its
   historical test projection. Rerun the actual writer fixture and confirm the
   descendant fault injection is reached before refusal.
2. I2S runs real same-device bind insertion after preflight/before operation,
   descendant replacement, lazy mount loss with no root fallthrough, unrelated
   Docker mounts, legitimate model mounts and fixed registry tamper in its
   approved disposable Linux fixture. Use protected held-FD assertions as well
   as mountinfo assertions; no synthetic result closes this gate.
3. Keep stage claims/full apply gated. No source here authorizes deployment or
   changes other owners' Storage, lifecycle, State, package, or lease modules.
