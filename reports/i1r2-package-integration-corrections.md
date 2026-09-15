# I1R2 — bounded reviewed package integration corrections

Date: 2026-09-15. Worker: `mac-worker1.local`, Darwin, Python 3.14.7.
Reviewed base: `6920fa445bd9ea8d41f59e7f052a83e7322497bf`.
Branch: `milestone/i1r2-package-integration`.

**Status: bounded source corrections complete for root review. Full installer
regression remains FAILED with the same preexisting container fixture failures
as the exact reviewed base. Full apply remains gated.**

## Changes

- Added only fixed `APT::Sandbox::User=root` to `Runner._package_preparation`.
  No arbitrary APT controls or additional command modes are accepted. Tests use
  the actual `ContainerPackages._install` update/simulate/download argv through
  the real parser, with commands, filesystem preparation and transaction mocked.
  Empty/altered values, other controls, duplicate altered options, mode overrides
  and direct install remain refused.
- Corrected the Runner and `_export_package_watcher_fd` API documentation,
  [L1 interface](l1-lease-interface.md) and
  [package caller example](i1r-package-process-ownership.md#exact-i1b-caller-api).
  The caller retains its validated export throughout Runner's entire package-use
  scope, including post-READY validation, failure cleanup and later stages.
  Close in `finally` before the outer canonical lease exits, never `LOCK_UN`.
  The watcher independently owns its inherited duplicate until quiescence.
- Added four portable tests consuming the actual `common.lifecycle_lease` module:
  two successive public transactions using one export; failure cleanup ordering;
  premature post-READY close rejected before gate execution while the watcher
  retains the flock; and parent SIGKILL followed by canonical reacquisition and
  explicit marker recovery after quiescence. No canonical module copy or raw
  private owner-descriptor access was introduced.

Only executable production change: the exact fixed APT option. The canonical
lease module change is its export docstring only. Runner/process ownership,
installer glue, storage, lifecycle Manager, U1, profiles, client and version lock
remain unchanged.

## Verification

All commands used existing worker Python and disposable fixtures; no installation,
real APT/systemd execution, service activation, disk mutation, reboot or ai-vm use.
Detailed output is retained alongside the task in `../evidence/`.

| Check | Result |
| --- | --- |
| `PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest discover -s tests/install -p 'test_package_preparation.py' -v` | PASS: 4 focused preparation tests |
| Same command with `test_package_lease_retention.py` | PASS: 4 focused canonical-export tests |
| Same command with `test_package*.py` | PASS: 52 tests, 39.099 s |
| `PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest discover -s tests/lifecycle -p 'test_*.py'` | PASS: 268 tests, 7.209 s |
| `PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest discover -s tests/install -p 'test_*.py'` | FAILED: 249 tests, 11 errors, 2 failures, 4 skipped; 76.134 s |
| Same full installer command in detached exact-base checkout | FAILED: 241 tests, same 11 errors, 2 failures, 4 skipped; 69.401 s |
| Baseline/current failure comparison | PASS: identical failure names, tracebacks and messages after checkout-prefix normalization |
| Executable AST comparison to reviewed base | PASS: lease implementation unchanged; core differs only by approved fixed option |
| Changed Python sources and corrected API examples compiled without bytecode | PASS |
| Scope review, `git diff --check`, grep-based secret scan, credential-free remote check | PASS |
| Post-test package fixture/process inventory | PASS: no live matches |

The 13 full-suite failures/errors are all in existing `test_container` fixtures.
Their synthetic package identity/preparation methods return `None`, leaving an
invalid transaction marker that real recovery correctly refuses. The fixture's
own `run` bypasses the real preparation parser. These failures predate I1R2;
no full-installer PASS is claimed and no fixture ownership contract is bypassed.

## Remaining seams and next action

- I1c owns final canonical lease/admission integration and source-owned private
  bind/anchor handoff for package/runtime jobs. Parent `/proc/<pid>/fd` paths,
  source/gate/marker lifetime and mount-loss integration are not solved here.
  The mocked ContainerPackages argv test proves parser compatibility only.
- Runner's raw FD checks do not establish canonical provenance. Trusted internal
  callers must import `common.lifecycle_lease` canonically, validate expected
  root/UID and use its export. No CLI/config/environment FD input is authorized.
- Full apply and bounded package integration checkpoints in `main.py` are
  unchanged; the incomplete status in `docs/installation.md` remains intact.
- **NOT_TESTED:** actual Linux systemd/cgroup-v2, real APT/dpkg/maintainer scripts,
  source/anchor lifetime after parent loss, fresh installation or reboot.
  Portable POSIX and mocked adapter results are not installed-adapter evidence.

Next: root reviews/publishes the incremental bundle; I1c completes its owned glue
and reconciles the existing container fixtures; I2R on worker2 supplies actual
disposable Linux evidence after review. No push or live-host work is part of I1R2.
