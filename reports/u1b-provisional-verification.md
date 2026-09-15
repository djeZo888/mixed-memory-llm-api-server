# U1B isolated provisional candidate verification

Source-only worker verification. No original lifecycle, installer, or other owned production file was changed. No installed host, model, real key, Docker process, or GPU was used.

## Inputs

- Worker control source copied from `repo` to `verification-copy`; `.git` and Python caches excluded.
- `L1B-CANDIDATE.patch` SHA256 `937e90a9ecf4c2f41cbe47d06d828cb67393c882abcdcf2a470dc6921b1ab647`; applied with `git apply --check` then `git apply` in the copy only.
- `I1C-STORAGE-FROZEN.patch` SHA256 `4a2ecd75e94d0724cd5428ed383ec2687a473f212f95192dd5be03f2de3e8148`; applied with `git apply --check` then `git apply` in the copy only.

L1B was subsequently published as commit `9cb93959105468ea0e140598b51493ee0d13ce9e`. The two tested production modules and author role test are byte-identical to that commit, as recorded in `verification-committed-l1b.json`. Final L1B/combined review remains pending. I1c remains the supplied uncommitted frozen overlay; this composition has no production approval. The copy-only HTTP fixture default is `actual_writer=True`; its expected-failure decorator is removed. No production writer or role guard bypass is enabled.

## Direct actual role-verifier check

- Copied author test fixture `../L1B/repo/tests/lifecycle/test_real_storage_roles.py` read-only into isolated copy. SHA256 `a102b4f611e77cdc20d07495a99a0660eb881de47aaf3d3b0593a24b6956ead1`.
- Fixture `LocalPathStorage` overrides only path mapping. Actual `Storage.verify`, `guard`, `_snapshot`, `_mount`, `_capacity`, and `_role_snapshot` execute. Only raw read-only Linux command responses, mountinfo text and ordinary-user writer UID are synthetic.
- Command: `python3 tests/lifecycle/test_real_storage_roles.py -v` in the isolated copy. Exit 0. Detailed output: `verification-real-roles.log`.
- Initial strict U1B HTTP run: 16 tests, 16 ERROR before fault injection because retained `LocalStorageFixture` supplies no raw discovery runner for the new reduced-role code path. This was not a safety pass. The completed result below uses the corrected copy-only raw-discovery fixture.

## Completed candidate result

**PASS, isolated provisional-source worker verification only.** The initial
pre-injection errors above were corrected by adapting the copied tests to raw
Linux discovery responses, without changing any production verifier or writer.
The current worker `scripts/control/*` and control test files were refreshed
immediately before the final run; only the two explicit copy-only fixture
adaptations were preserved. Every tested input still matches the recorded
manifest after completion.

| Run | Result | Time | Scope |
| --- | --- | --- | --- |
| `python3 tests/test_control_production.py -v` | 16 PASS, 0 fail/error/skip/expected failure | 5.996 s | Actual Manager, canonical OS lease, package admission, I1c role verifier, I1W writer and real localhost HTTP/subprocess recovery, with synthetic Docker/storage/probes |
| Full `test_control*.py` aggregate | 180 PASS, 0 fail/error/skip/expected failure | 9.348 s | All current control tests, including strict candidate HTTP fixtures |
| `python3 tests/lifecycle/test_real_storage_roles.py -v` | 4 PASS, 0 fail/error/skip/expected failure | 0.364 s | Actual role verifier/writer equal-root persistence, split model loss, and denied model-root writes |

The aggregate preloads production packages to avoid the existing `tests/lifecycle`
package-name collision:

```sh
python3 -c "import sys,unittest;sys.path.insert(0,'scripts');import lifecycle,install;s=unittest.defaultTestLoader.discover('tests',pattern='test_control*.py');r=unittest.TextTestRunner(verbosity=2).run(s);raise SystemExit(not r.wasSuccessful())"
```

## Assertions and evidence boundaries

- The strict HTTP fixture defaults to `actual_writer=True`. It asserts inherited
  actual `Storage.verify`, `_snapshot`, `_role_snapshot`, `_blocks`, `_mount`,
  and `_capacity`; data-only verification reports `verified_roles:['data']`.
- Equal data/model roots are used. The actual Manager writes through actual
  I1W `AnchoredRoot` objects anchored below registered service/log roots, and
  tests assert all real guard/anchor resources close. No `check_path` bypass or
  manufactured `verified_roles` attestation is used.
- Missing local target image, mismatched image ID, and wrong entrypoint all
  reach actual candidate `prepare_start`/`create_args` checks before any old
  container stop. Canonical lease, durable admission, CAS, interrupt consent,
  idempotency, package gate, and storage-loss trusted stop remain exercised.
- Raw `findmnt`, `lsblk`, `df`, and mountinfo responses are synthetic worker
  fixtures. Only fixed-path mapping and ordinary-user UID are adapted. Docker
  inventory/actions and inference readiness responses are controlled synthetic
  objects. The one-byte artifact and inert fixture credentials are test data.
- HTTP TCP sockets, threads, canonical flock, fsynced worker files, and the fresh
  subprocess after loss of temporary data/config/key paths are real process and
  network behavior. These tests do not establish real Linux detach or systemd
  boot/reboot, real Docker/GPU/image/auth execution, occupied context, two-model
  inference, installer completion, or combined production approval.
- Original `scripts/lifecycle/manager.py`, `scripts/lifecycle/storage_binding.py`,
  and `scripts/install/storage.py` remain byte-identical to reviewed `4ab862f`.
  Candidate production overlays exist only under `verification-copy`.

## Reproduction and hashes

Create a fresh copy of the final U1B worker source outside the repository,
excluding `.git` and Python caches. Apply `L1B-CANDIDATE.patch`, then
`I1C-STORAGE-FROZEN.patch`, then `verification-fixtures.patch` in that copy only.
Each patch was checked before application. `git apply --check` confirms the
fixture patch applies to current original worker source without mutation.
The fixture patch adds the exact author role test file and the two copied
control test adaptations; it changes no original source. Do not commit its
embedded lifecycle test as U1B-owned implementation.

`verification-input-sha256.json` records every tested control source/test plus
the three overlaid production modules and author role fixture. Output and patch
hashes follow:

- `L1B-CANDIDATE.patch`: `937e90a9ecf4c2f41cbe47d06d828cb67393c882abcdcf2a470dc6921b1ab647`
- `I1C-STORAGE-FROZEN.patch`: `4a2ecd75e94d0724cd5428ed383ec2687a473f212f95192dd5be03f2de3e8148`
- `verification-fixtures.patch`: `7976d69373800daf998cd33bf0f3c831c1bf3cd2a00d91b7efe90e2430ca57b9`
- `verification-input-sha256.json`: `44bcc982f5d054768dfb39846eb230a816241fb959a1986fd75ace14157e9215`
- `verification-http.log`: `bcca8d227b685c58d017bee182e8faec435f9ae81313f56e6163d37e82eeee0a`
- `verification-control-all.log`: `3e4c92bd021f9c640bdd24202f39a18ad3b98fa706e08bc22c9f71a8a8caff72`
- `verification-real-roles.log`: `08f81a3eb80480b7ace94f0bf0bf96ff8ffd510af9cad526b45b8ff5ecf8a036`

Provisional candidate composition passed these worker tests. Final L1B review, committed/reviewed I1c integration, and independent combined review remain required before production use.

Committed-L1B byte comparison SHA256: `9408cc61f14b416eb857d0179ed96e21f9a9cf4afb2dcd38c672dae2429de7b3`. No rerun was needed because every compared tested source byte is identical.

Repository evidence copies use the `reports/u1b-` prefix: `u1b-provisional-verification.md`, `u1b-verification-fixtures.patch`, `u1b-verification-input-sha256.json`, `u1b-verification-output-sha256.json`, `u1b-verification-committed-l1b.json`, and the three `u1b-verification-*.log` test outputs. The original dependency patches remain supplied external inputs with hashes above.

The whitespace-clean fixture patch was applied to a disposable copy of the original test files; all three reconstructed test files match the tested copy byte-for-byte.
