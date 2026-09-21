# L1 registered lifecycle source report

Status: **REVIEWABLE SOURCE; integration acceptance STOP on shared-owner gaps**.
Branch: `milestone/l1-registered-lifecycle`. No production apply is authorized.

## Source and APIs

Prepared base `5612f2aabef05d4ca6383e504b7c0fe66c0dcb45` combines reviewed F1S
integration `e46c788534d5b71e988c2cdf188f37f6214f7514` and explicitly provisional
I1 storage `722050fdcb6de4a9f56a5488b705998a1d82ce85`. Canonical lease was published
as `9c34d78a358831a47430ac7a2492a7857b67ab04` and independently reviewed by root.
Reviewed I1b `6e04a510b4f882ea4958765710992f67e78d2ea5` is now merged through
`d93e72670f300bedf2e6bbe7e3e2e1d729b577a1`. Reviewed package integration
`6920fa445bd9ea8d41f59e7f052a83e7322497bf` (I1R
`a540b67a552897512a0fff1940ed9fd476830609`, reviewed I1P pin correction and F1E2)
is merged as `efc5d8b3fb374ba3b190c14779fc27fd6e2112e8`. Full `taskroot/L1.bundle` is refreshed
immediately after each commit. Final source commit is the commit containing this
report; exact delivery hashes are also recorded in taskroot/progress.md.

L1 owns the canonical lease, Manager/path binding, boot renderer, affected
profiles, tests and documentation. No `scripts/install` file was edited by L1;
those files enter only from the reviewed I1b/I1R integration merges. No U1 implementation.

Public imports and migration details: [L1 handoff](../docs/lifecycle/l1-handoff.md).
Early callable handshakes: taskroot `lease-api.md` and `U1-MANAGER-API.md`.

- `common.lifecycle_lease.acquire_lease(*, blocking=True, system_root=Path('/'),
  trusted_uid=0)` yields `LifecycleLease`; `lease.validate()` checks active minted
  same-process provenance, live FD, trusted canonical inode and fixture scope.
  `blocking=False` raises `LeaseBusy.code == 'lifecycle_busy'` atomically.
- `Manager.dispatch(action, deployment_id=None, boot_policy=None, dry_run=False,
  *, lease=None)` accepts only the active minted lease; never recursive flock,
  owner close or raw FD. Direct API arguments are validated before state I/O.
- Internal `_export_package_watcher_fd(lease)` returns an owned duplicate of the
  same open-file description. Keep it for the entire Runner/package-use scope,
  close in finally before outer lease exit. All release is close-only; watcher
  inherits independently through quiescence, including parent SIGKILL.
- `RegisteredStorageBinding` consumes protected fixed schema1 registration and
  shared Storage. Stable identity excludes observed source/device/parent fields.
  All host paths derive from role + normalized suffix; container paths stay fixed.
- Actual `install.storage_io.MountedStorageGuard` and `AnchoredRoot` perform
  persistent writes. L1 wraps the guard with stable-identity and full-boundary
  checks. No duplicated persistent writer or preflight-only write authorization.
- `render_fresh_instance` is pure. `import_historical_instance(binding, *, lease,
  storage_io)` preserves historical paths/evidence and changes only explicit
  binding/import fields. `render_boot_unit` requires exact mounts and protected
  start/recovery source; tiny recovery code remains available outside lost data.
- Package admission calls the frozen authoritative
  `install.prerequisites.assert_package_admission(data_dir, storage_guard)` under
  the canonical lease. Missing callable or any unknown state fails closed with
  `package_transaction_recovery_required`. No marker-only acceptance or package
  policy restoration by Manager. Actual reviewed I1R source is merged; worker admission integration uses that function.

## Worker validation

| Executed check | Result / boundary |
| --- | --- |
| `python3 -B -W error::ResourceWarning -m unittest discover -s tests/lifecycle -q` | 369 tests: 366 PASS, 2 FAIL + 1 ERROR exposing shared Storage gaps below |
| Canonical lease tests | 37 PASS; real processes, nonblocking busy/creation, borrowed ownership, fork/parent death/watcher, close/error/invalid scope |
| Manager borrowing/direct API | 17 PASS; owner retained, input validation before lock/state/admission, trusted recovery records |
| Actual I1b writer through L1 | 9 tests: 8 PASS, 1 FAIL below; real descriptors and actual guard/writer, synthetic discovery + worker uid; single/equal/nested/sibling writes, deterministic detach surrogates, import, stop and guard/anchor entry failure cleanup |
| Boot renderer | 12 PASS; exact mount escaping/dependencies, complete protected recovery code, hidden per-file mounts, isolated CLI import closure |
| Actual I1R admission through Manager | 9 PASS; actual author function + real shared writer, fixture policy path, marker/gate/orphan/unknown refusal, free-flock denial and trusted stop |
| Retained Manager/GLM/F1S/import/recovery/auth suites | Included in lifecycle total; immutable gates and actual-stop recovery with fake Docker |
| `python3 -B -m unittest discover -s tests/install -p test_storage_io.py -q` | 38 tests: 37 PASS, 1 SKIP (actual Linux namespace mount detach unavailable) |
| `python3 -B -m unittest discover -s tests/install -q` | 241 tests: 224 PASS, 4 SKIP, 2 FAIL + 11 ERROR at old container/package caller integration below |
| Four `tests/shell/test-llmctl-{fixtures,static,lifecycle-fixtures,lifecycle-static}.sh` checks | PASS; offline planning, env refusal, lifecycle CLI source/help checks |
| `python3 -B -m unittest tests.test_agent_protocol tests.test_agent_acceptance tests.test_agent_fixture -q` | 75 PASS |
| `git diff --check` | PASS; publication secret/identity/clean gates recorded in taskroot/progress.md |

Counts in component rows overlap; they are not summed into the broad totals.
Real-writer fixtures use tiny protected worker directories. Linux discovery is
explicitly synthetic; split filesystem rows share the worker's physical fixture
filesystem. Rename/exchange at the actual mkdir/replace syscall deterministically
simulates detach and verifies no file appears in the replacement fallback path.
Historical `/data` import uses a test-only projection into the temporary root.
These tests execute the real writer; they do not prove Linux unmount/boot behavior.
Other retained fixtures inject the writer API and cannot establish integration.

Preservation comparison against reviewed package integration `6920fa4`: F1E
launcher, SGLang runtime JSON, F1A immutable expected manifest and GLM expected
artifact report are byte identical. Both model JSON profiles change only
`model_root` into a role object. F1C-reserved ENVIRONMENT/runtime map remains
untouched. Reviewed upstream changed launcher SHA256 to
`b47a334466e32ca8384478721d77e00352003c5809bdeccf2a0553dc496210a7`; L1 consumes
that correction without changing its bytes or promoting actual-image auth.

## Required shared-owner integration work

1. **Data-only guard (I1c):** actual Storage and MountedStorageGuard verify both
   roles. With only the model mount missing, data-only persistence fails. The
   required test remains an ordinary ERROR, not expectedFailure/skip. Trusted
   volatile stop still works and reports `state_persisted:false` with restore
   volume/repeat-stop-before-reboot warning; no fallback root is created.
2. **Extra mount alias (shared Storage owner):** a data partition with its exact
   registered mount plus `/unregistered-alias` is accepted by shared verify. The
   required regression remains an ordinary FAIL. L1 separately refuses wrong
   UUIDs/root devices, ambiguous registered role aliases, hidden source mounts,
   symlinks, traversal, replaced registration and instance mismatch.
3. **New descendant mount (I1c/shared writer):** after preflight and anchor open,
   a same-device mountinfo entry below data/services/llm-manager is ignored by
   MountedStorageGuard's named-root-only checks. Actual AnchoredRoot permits the
   write. The required real-writer fixture remains an ordinary FAIL. No actual
   mount is performed; discovery is injected, writer/guard implementation is real.
4. **Installer lease/package callers (I1c):** actual authoritative I1R admission
   is merged and consumed by Manager. Installer `core.exclusive` still needs
   canonical minted-lease/export integration. Old container `_inhibit` callers
   use incompatible marker ownership and now fail closed under I1R recovery:
   the broad installer suite has 13 FAIL/ERROR cases. Shared owners must adapt
   those callers and preserve package execution gates. L1 changes no installer
   source. The earlier GLM profile pin mismatch is resolved by reviewed I1P.
5. **Completion/install (I1c):** install protected source and recovery closure,
   explicit bound instance, generated unit and required acquisition receipt
   translation. F1S actual-image auth gate stays mandatory. Root approves U1's
   existing `prepare_start(d)` under the held canonical lease before stopping
   the old target; its anchored guard-report write is accepted. Dry-run remains
   configuration-only. No new preflight framework or U1 catalog/generation code
   is implemented here.

## NOT_TESTED / next action

No ai-vm SSH, host/package installation, disk/ownership mutation, model download,
build/activation, key read/rotation, actual-image auth, GPU inference, actual
package cgroup execution, Linux mount detach, installed systemd boot/reboot or
fresh installation. No production or complete installer PASS.

Next: root reviews the complete L1 bundle; shared owners supply the exact
corrections above, then rerun the required integration tests. L1 will consume
reviewed incoming source before claiming final integrated acceptance. Independent
F1E2/Q38/U1 implementation is outside this task's completion boundary.
