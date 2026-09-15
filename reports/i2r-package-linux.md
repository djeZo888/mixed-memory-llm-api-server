# I2R package ownership verification

Status: **source harness delivered; actual hosted execution NOT_TESTED**.

Reviewed base: `6920fa445bd9ea8d41f59e7f052a83e7322497bf`.
Owned branch: `milestone/i2r-package-linux`.

## Reviewed dependency integrated

Coordinator Revision3 supplied and approved I1R2
`18644f3df91f38e23bbf19889f5c03302b898047`, merged at
`a833afeff52768b453e214f6aebade4137f96b0e` without modifying its source.
The only executable production change accepts the exact sandbox option.
All **51 I2R methods PASS**, plus **4 affected package preparation** and
**4 canonical export retention** tests PASS. The initial source-base failures
below are resolved by that reviewed dependency; actual hosted execution remains
pending and is not inferred from these checks.

Current ownership: **I1O** owns scope storage/source/key/cache/log/temp and
gate/marker lifetime conversion; **I1c** owns final caller/stage integration.
Older I2R evidence field names containing I1c refer to the same unresolved work,
not evidence that it passes. Public installer/Manager caller integration remains
separate from the harness's real canonical module use.

The new [I2R harness](../scripts/validation/i2r/README.md) runs shipped package
ownership code with the real system manager/cgroup v2 and canonical lifecycle
lease on a fixed disposable GitHub-hosted Ubuntu 24.04 runner. Coordinator
incoming.md Revision2 approved temporary read-only bindings of deterministic
fake apt-get/dpkg; underlying originals are retained and verified after cleanup.
No worker host installation, ai-vm access or production operation is performed.

## Evidence boundaries and source gaps

| Area | Status |
| --- | --- |
| Worker safety/source tests | 51 I2R + 8 affected dependency methods PASS |
| Actual systemd, canonical export, package matrix | NOT_TESTED pending hosted run |
| I1b exact sandbox option | Reviewed I1R2 integrated; local preparation tests PASS; hosted pending |
| Manager borrowed-lease integration | NOT_TESTED: base dispatch lacks lease keyword |
| Public installer canonical export | NOT_TESTED: base main still calls raw-FD exclusive context |
| I1O scope-owned anchored storage and mount-loss gate/marker writes | NOT_TESTED: implementation unfinished |
| Real package compatibility, fresh GPU install, reboot | NOT_TESTED |
| Docker daemon ownership, agent readiness | NOT_TESTED |

The source harness and final evidence report are separate deliveries. A source
commit or mocked/portable unit result cannot establish actual Ubuntu PASS.

Initial base checks: dedicated `test_i2r*.py` discovery (51 methods), Python syntax,
run/guardian/matrix dry-run, help, whitespace, owned-file scope and filename-only
grep secret scan. Guardian 23, matrix 14 and orchestration 6 tests pass; six of
eight preparation methods pass. The two failing preparation methods exercise
the real ContainerPackages option list against the real Runner parser. On this
base, update/simulate/download are rejected and Runner raises
`owned_package_transaction_required`; no real package command executes.
No failure is marked xfail, skipped or promoted to PASS. Source review corrected
the new harness cleanup ordering before any hosted execution; production source
is unchanged.

Next action: publish this reviewed integration and execute the approved workflow
at the exact published source SHA, then append actual evidence and cleanup status.

The new harness checks `cgroup.kill` on non-root owned cgroups; this matches the
[kernel cgroup v2 interface](https://docs.kernel.org/6.7/admin-guide/cgroup-v2.html).
Feature-branch push is used because manual dispatch availability depends on
workflow registration; see [GitHub workflow events](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows).
