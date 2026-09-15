# I2R package ownership verification

Status: **source harness delivered; actual hosted execution NOT_TESTED**.

Reviewed base: `6920fa445bd9ea8d41f59e7f052a83e7322497bf`.
Owned branch: `milestone/i2r-package-linux`.

The new [I2R harness](../scripts/validation/i2r/README.md) runs shipped package
ownership code with the real system manager/cgroup v2 and canonical lifecycle
lease on a fixed disposable GitHub-hosted Ubuntu 24.04 runner. Coordinator
incoming.md Revision2 approved temporary read-only bindings of deterministic
fake apt-get/dpkg; underlying originals are retained and verified after cleanup.
No worker host installation, ai-vm access or production operation is performed.

## Evidence boundaries and source gaps

| Area | Status |
| --- | --- |
| Worker safety/source tests | 49 of 51 test methods PASS; pending source correction causes 3 failed subtests and 1 error |
| Actual systemd, canonical export, package matrix | NOT_TESTED pending hosted run |
| I1b exact sandbox option | Source correction awaits I1R2 delivery |
| Manager borrowed-lease integration | NOT_TESTED: base dispatch lacks lease keyword |
| Public installer canonical export | NOT_TESTED: base main still calls raw-FD exclusive context |
| I1c scope-owned anchored storage and mount-loss gate/marker writes | NOT_TESTED: implementation unfinished |
| Real package compatibility, fresh GPU install, reboot | NOT_TESTED |
| Docker daemon ownership, agent readiness | NOT_TESTED |

The source harness and final evidence report are separate deliveries. A source
commit or mocked/portable unit result cannot establish actual Ubuntu PASS.

Checks run: dedicated `test_i2r*.py` discovery (51 methods), Python syntax,
run/guardian/matrix dry-run, help, whitespace, owned-file scope and filename-only
grep secret scan. Guardian 23, matrix 14 and orchestration 6 tests pass; six of
eight preparation methods pass. The two failing preparation methods exercise
the real ContainerPackages option list against the real Runner parser. On this
base, update/simulate/download are rejected and Runner raises
`owned_package_transaction_required`; no real package command executes.
No failure is marked xfail, skipped or promoted to PASS. Source review corrected
the new harness cleanup ordering before any hosted execution; production source
is unchanged.

Next action: integrate the bounded source-owner APT correction, finish local
review, then execute the approved workflow at the exact published source SHA.

The new harness checks `cgroup.kill` on non-root owned cgroups; this matches the
[kernel cgroup v2 interface](https://docs.kernel.org/6.7/admin-guide/cgroup-v2.html).
Feature-branch push is used because manual dispatch availability depends on
workflow registration; see [GitHub workflow events](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows).
