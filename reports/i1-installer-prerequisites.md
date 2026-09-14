# I1 — resumable installer prerequisites source boundary

Date:2026-09-15. Worker:Mac-Worker1. Branch:`milestone/i1-fresh-linux-installer`.

**PARTIAL DELIVERY: I1b required.** The full installer requested by the user is
not complete. Root accepted this coherent preflight/storage/prerequisites/driver
boundary in the task coordination input. Full apply/resume remains fail-closed
(exit78) before mutation; no READY output or model/client acceptance is claimed.

## Implemented and pending

| Stage/interface | Source result |
| --- | --- |
| Executable plan/apply/resume/status/verify interface | Implemented; explicit partial `--through` boundary; full apply refused |
| Strict config, model selection and role validation | Implemented; root client user rejected; no implicit smoke fallback |
| Read-only OS/kernel/RAM/GPU observations and disk budgeting | Implemented partial preflight; full service/network/ownership profile gates remain I1b |
| Existing mount adoption / explicit UUID mount + fstab backup | Implemented; generic roots, shared or distinct model filesystem |
| Blank by-id disk safety plan | Implemented read-only identity/exclusion checks; actual provisioning pending |
| Root-owned registry, sanitized environment, generic common guards | Implemented; historical UUIDs only in legacy unregistered paths |
| Atomic schema/hash stage state, process ownership, resume/no-op | Implemented; checks actual stage postconditions each run |
| Exact package lock and private Ubuntu snapshot prerequisites | Implemented source; base and driver stages only |
| Driver/module/userspace/GPU checks and reboot checkpoint | Implemented source; actual GPU container gate pending |
| Docker/containerd/toolkit installation and storage before service start | Pending I1b; exact package pins recorded only |
| Runtime build/import and generic resumable model acquisition | Pending I1b; approved D1/F1A artifacts referenced in plan |
| Safe credentials, lifecycle deployment and boot/rollback | Pending L1/F1S integration + I1b |
| Pinned Linux client provisioning and SSH tunnel helper | Pending I1b/V0 integration |
| Real API and OpenCode edit/test acceptance, READY summary | Pending I1b and live F1D/D3/I2 evidence |

## Important source contracts and limits

The installer owns one `/run/llmctl/lifecycle.lock` lease through prerequisite
mutation. Installed root-owned schema1 registry records stable data/model
`path`, exact `mount`, `uuid`, `fstype`, plus transient source/device/parent
observations and root mappings. Device renumbering after reboot is accepted only
after fresh UUID/topology verification. No config/env value can replace a
registered UUID. Registry/state permissions and layout are rechecked; root/data
capacity is separate. Existing credentials and partial data are preserved.

The common guards route to the fixed trusted registry when its directory exists,
including invalid/missing-registry failures. They do not fall back to historical
ai-vm constants for a registered installation. No legacy live service is adopted
or altered by this source task.

Observed mount loss fails before further data/status writes. **Directory-FD
anchored writes across a detach race are not implemented in I1** and must be a
shared L1/I1b primitive before full installation. Current repeated checks are not
proof against a detach between checking and opening a path. Canonical validated
LifecycleLease borrowing by Manager is also pending; do not release/reacquire or
use a second owner to bypass that integration.

The package stage uses a verified signed Ubuntu snapshot with exact archive
metadata; all164 archive URLs were checked read-only. It refuses missing pins,
unlocked changed dependencies, removals and downgrades. Existing compatible
loaded driver is preserved. New driver uses pinned signed Ubuntu modules/kernel
and headless userspace, without host CUDA Toolkit/DKMS. Package starts are
inhibited and the prior policy is restored, including resumed interruption.
Root reservations are admission estimates, not quotas; real Ubuntu execution is
still required. See [package sources](i1-package-sources.md).

Source mocks never set F1S real auth evidence or claim model fit. Published model
bytes and runtime build/device probes are different from measured RAM/VRAM peaks,
readiness/generation/tools or coding-agent acceptance.

## Validation evidence

Worker evidence is synthetic unless explicitly labeled read-only discovery.
The final command results are recorded below before commit. Tests perform no
package install, disk operation, real model download, inference activation or
client package download.

- Installer fixture suite: **90 tests PASS** (0.396s): CLI8, config13, core19,
  storage26, prerequisites24. Includes actual wrapper execution, cross-process
  ownership, interruption/resume, verified no-op, mount loss, secret preservation,
  pin/dependency/capacity failures, driver checkpoints and service-policy recovery.
- Existing lifecycle suite: **116 tests PASS** (4.238s); no source changes to
  lifecycle/profile/client ownership areas.
- CLI `--help`, fixture plan, uninstalled status and unsafe fixture apply refusal:
  covered by installer tests; actual shell wrapper is exercised.
- Bash syntax + legacy root guard static check: **PASS**.
- Legacy root guard shell fixture: **FAILED ON WORKER ENVIRONMENT** because the
  Mac has Bash3 and the unchanged legacy function uses `local -n`. No Bash4 or
  host package was installed to work around this. Ubuntu target run remains I2.
- Whitespace, staged scope, credential scan, exact attribution and CLI plan:
  final checks recorded in the handoff section below.
- Ubuntu24.04 package/container install, disposable loopback storage, physical
  driver/firmware/reboot, live adoption/GPU container/model/client acceptance:
  **NOT_TESTED**.
- Full fresh-host GPU installation and reboot acceptance: **NOT_TESTED**.

Commands:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests/install -p 'test_*.py' -v
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests/lifecycle -p 'test_*.py' -v
bash -n install.sh scripts/common/require-data-mounted.sh scripts/common/root-disk-guard.sh
bash tests/shell/test-root-disk-guard-static.sh
./install.sh --help
./install.sh plan --profile flagship-hybrid --model-set glm,qwen --fixture-host tests/install/fixtures/ubuntu-host.json
./install.sh status
git diff --check
```

A separate Ubuntu24.04 CI workflow runs installer fixtures and the read-only
fixture plan. Adding it does not claim a remotely executed CI result.

## Source/docs and next recommended action

- [`install.sh`](../install.sh), [`scripts/install/`](../scripts/install/),
  [`tests/install/`](../tests/install/), generic common guard support.
- [Installation](../docs/installation.md), README/AGENTS/current-state updates,
  [package evidence](i1-package-sources.md), [I1b continuation](i1b-continuation.md).
- Task sibling `progress.md`, `integration-gap.md`, `storage-schema.md` are
  coordinator handoffs, not committed project state.

Root should review/synchronize this bounded commit, align L1/F1S/V0 interfaces,
then launch fresh I1b for the remaining source stages. I2 must independently test
appropriate disposable Ubuntu/loopback paths and later coordinated adoption.
No push is performed by I1.

## Final source handoff checks

- Final combined installer suite:90 PASS; lifecycle suite116 PASS.
- Actual wrapper help/fixture plan/status:PASS, `ready:false`; selected missing
  stages explicitly pending. Source plan lock SHA256
  `a829e9cd20c897b79d9cdc85088a1ab2b8d67b1769698d06901d8f570e97213c`.
- `git diff --check`, local Markdown links, owned source scope review:PASS.
- Local `rg` credential-pattern scan:PASS after checking two expected matches:
  unchanged legacy secret-scanner literal and synthetic invalid-URL fixtures.
  No real keys, state, environment files, weights or task handoff files staged.
- Local author/committer config verified as required immediately before commit;
  actual commit identity is inspected after creation and recorded in task progress.
- Remote URL has no embedded credential. No push; root reviews/synchronizes.
