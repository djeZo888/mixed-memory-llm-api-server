# Q38VR3 — one actual fixture attempt FAIL; bounded task complete

## Result

**131072 FAIL. 262144 NOT_RUN. No receipt. Installer STOPPED.**

One unchanged shipped `tests/lifecycle/sglang38_fixture/run_fixture.py` invocation
ran through Worker1 `ssh ai-vm`, using exact integration
`56aae9ea64a15bb582f89cd20a770985e8d70eac` and reviewed Q38EF
`498f6977becf31fd9747154f50e33e6b01b90e9e`. The integration adds report/history
ancestry; fixture/runtime bytes match Q38EF. No source edits or pin overrides.

Actual fixture invocation UTC window:
**2026-09-15T04:18:22.027258+00:00–2026-09-15T04:18:22.787051+00:00**,
measured elapsed **0.757678 seconds**. This is the actual shipped
fixture invocation including its container lifetime, not preparation time;
individual native import/cache subphase timestamps are not exposed.
Outer exit **1**; fixed outer code `q38s_image_fixture_failed`;
outcome **ATTACH_FAILED**. Attach CLI and observed container exit were **2**.
No signal was established by either retained signal field.

The first concrete terminal result was immediately written before postchecks or
narrative packaging to `../phase-result.md`, its committed
[copy](q38vr3-evidence/phase-result.md), and ai-vm
`/data/logs/q38vr3-20260915/phase-result.md`. The unchanged internal loop gates
262144 on every first-context acceptance check and exact cleanup. It stopped
on this first failure; there was one launch and no retry.

## New fixed diagnostic and evidence boundary

| Field | Observed value |
| --- | --- |
| Cache child fixed code | `gpu_device_node_present` |
| Cache child safe origin | `cache_probe.py:190`, `ProbeError` |
| Enclosing fixed code | `actual_image_fixture_failed` |
| Enclosing safe origin | `run_pinned_image.py:599`, `FixtureFailure` |
| Host runtime inspection | `PASS_HOST_INSPECT`, context131072 |
| Failure kind / phase / operation | `CLI_NONZERO_EXIT` / `ATTACH` / `START_ATTACH` |
| Inner stdout | COMPLETE, 331 bytes; SHA256 `0b02141789ead6a4bba31c5639136feca9a1c9f45c27d3b0d1c08f2148ac5379` |
| Inner stderr | COMPLETE, 0 bytes |

Static mapping of the exact shipped origin identifies `relevant <= CONTROL_NODES`.
It filters discovered names beginning `/dev/nvidia` or `/dev/dri/`, plus
`/dev/kfd` and `/dev/dxg`, and allows only `/dev/nvidiactl`, `/dev/nvidia-uvm`,
and `/dev/nvidia-uvm-tools`. The observed failure establishes that this
name-set predicate rejected at least one discovered name. **The exact name,
filesystem object type, usable GPU access, and underlying cause are unknown.**
The fixed code itself does not prove device type or GPU usability. No device
inventory or new diagnostic was performed. Host inspection still reports no
DeviceRequests or host device maps; that does not substitute for the inner gate.

This is distinct from historical Q38VR2 `no_gpu_runtime_environment_required`.
Q38EF admits measured inner `none`/`void` without modifying the environment;
this run reached the later device-name gate. Individual inner environment
values were not captured. Neither this failure nor the earlier Q38VR cache-child
boundary establishes a common underlying cause. No raw errors, exception text,
locals, environment, output, keys or prompts appear in the report or committed
evidence. Full safe record: [fixture-execution.json](q38vr3-evidence/fixture-execution.json).

## Exact owned cleanup

- ID: `216f7d148354dd85bc5c1c2225c5b3021d10d9645eedb86d16a002b29e29e44d`.
- Name: `q38b-fixture-2b459dcbf992ee743e37a5d1602b6ac5`.
- Shipped cleanup: **QUIESCENT_REMOVAL_VERIFIED**, including exact ID/name/label/
  image ownership, quiescence, non-force removal, and absence verification.
- Independent Docker listings filtered by the exact full ID and exact name both
  exited0 with zero stdout/stderr bytes. **Created1, removed1, remaining0.**
- Additional cleanup mutations: **0**. No unresolved owned identity remains.

The earlier exact Q38VR ID `411f949b60cd102390123cd75eddc6f2ca0abe186e1c6225bbfaa4a56d048e9a`
and Q38VR2 ID `a176ead245adb6824d7e6d962838c751436c5eaf8a1212f337c5469420b6cf5f`
and their exact names were independently absent before launch. Prior paths were
preserved. No force removal, arbitrary deletion, pruning or unrelated container
action occurred. [Final checks](q38vr3-evidence/final-checks.json).

## Exact source and storage authority

Source: `/data/build/q38vr3-20260915/source`, **1000 committed files**,
tree `1de3f03cb7ccdf428eb09b28f88fe1aac62281ba`. Archive SHA256
`266751d46455cde481edf185ba6147c6966f6ab5edbd38ce42cba5e5c33265a4`; source-manifest SHA256
`5ababe872b915ce8cdefd00d849c010c997a5158d95b2eab81eaf772e5db9248`.
All current snapshot file hashes, sizes, modes, single links and protected
ancestry passed staging/prelaunch; final fixture/provenance/adapter/launcher/OCI
hashes and task identities passed. Source root device2065/inode44434382,
root:root0555; files0444 or executable0555. New build/evidence/temp parents are
root:root0700. Existing parent metadata was preserved.

Final shipped pins, verified without regeneration:

| File | SHA256 |
| --- | --- |
| provenance.json | `82d8cdfa209fcc914c18394d260ca978d970ff423e87545a9f69f97a8a583987` |
| cache_probe.py | `f7fcdb1f81fe5f2e1a5be91e8274b1918e64cc622703fd3fb5d2d88cbd26b1c3` |
| scripts/lifecycle/qwen38.py | `29f10ad5dab7f7835611c35b552dfaa1e5cafb929416a56b2cf4923f5a2c6276` |

The authoritative installed guard remained fixed at
`/usr/local/lib/llm-server/control-api/scripts/common/registered-storage.py`,
SHA256 `21cf082a841aeab9470bd6704b77104961b9d4afcaec696d90aa22b65f5b6f3d`,
with dependency `scripts/install/storage.py`, SHA256
`4f834e92d149ea1955e79d34c53c18bf8c5846a4121d779e135a50d31a615505`.
Both unchanged source identities and protected ancestry passed pre/post. The
`installed_closure` evidence key contains only these two guard files; it is not
a full installed-control closure audit. D3N32 owns that current closure.
Corrected D3 hashes from [VM-GUARDS.json](q38vr3-evidence/VM-GUARDS.json) passed
as external source checks; no legacy fallback ran.

Fixed registration `/etc/local-ai-server/storage.json` remained root:root0600
under parent0700, SHA256
`626db7130b644199f5f632b2ac3c04f86cdd382121573aa6f3825bbca8de9c27`.

| Check | Result |
| --- | --- |
| Registered data/root guards preflight, prestage, prelaunch, postfixture | PASS |
| Data whole-volume UUID | `8daf56f1-5649-4163-9d87-919c2d271875` |
| Models whole-volume UUID | `a6d4ab58-84e1-4e48-9a67-13ad1c6f6e0a` |
| Exact registered mountpoints, ext4, fsroot `/`, derived roots | PASS pre/post |
| Root available bytes preflight / postfixture | 5208530944 / 5208526848 |
| Root STOP below4GiB | Not triggered; below6GiB warning retained |
| `/data/logs` | uid0/gid1000/mode2755/inode47972353 preserved |
| `/data/build` | uid0/gid1001/mode2755/inode21757953 preserved |
| Shipped provenance and reviewed OCI relationship | PASS |
| Native fixture / larger context | FAIL131072 / NOT_RUN262144 |
| Native model/generation/client acceptance | NOT_TESTED |

Already-pulled image
`lmsysorg/sglang@sha256:37bbbd3444732a464bbc68dee4fb0164e0ce9e18e2f027f3fc967f1152d3c262`
was used with no pull. Shipped OCI validation accepted platform-manifest-domain
image ID and config digest
`sha256:e6238090791a938ab86dd21a9a6394192dad15237e815df557cf83524d54b813`,
linux/amd64, source revision `0bcd822377da7b5718e674eaf9c870d349424dd1`.

## Verification and boundaries

The [launch plan](q38vr3-evidence/fixture-plan.md) records the exact single
command. Reused Q38VR2 preflight/staging/recorder/postcheck preparation was
updated only for new task paths, current committed manifests and current scope:
no historical installed-manifest assumption, GLM/control queries, or broad
historical/weight rehash. Preparation Python was syntax-checked. The fixture's
commands, environment, gate logic, lifetime, ownership, 30s create / 600s attach /
30s cleanup / 2s drain bounds, signals and receipt rules were unchanged.
No new diagnostic framework was introduced.

Root's final source review was accepted. No redundant source test suite or
additional native test was run. Shipped manifest hashes, exact source archive,
OCI reader, registered guards, exact absence checks and report consistency are
the relevant verification. Final report-only whitespace/secret/scope/identity/
bundle checks are recorded in the external handoff.

Authoritative guard commands, with no overrides:

```text
sudo -n /usr/bin/python3 -I -B /usr/local/lib/llm-server/control-api/scripts/common/registered-storage.py --json
sudo -n /usr/bin/python3 -I -B /usr/local/lib/llm-server/control-api/scripts/common/registered-storage.py --root-guard --json
```

Optional report paths were only below the existing protected
`/data/logs/q38vr3-20260915/evidence` parent. All VM task output/temp stayed below
registered `/data/logs/q38vr3-20260915`; only exact source was staged beneath
registered `/data/build`. No shared registry/mount/control/key/source closure
was changed. No model/real-key mount or access, installer, package installation,
model download, runtime build, kernel/inference, API/port/network or service
operation occurred. No GLM calls, stop or restart occurred. D3N32 retained sole
real lifecycle/model/generation ownership; no receipt was published to an instance.

Coordination was reread at staging, launch, result and packaging boundaries.
Its earlier coordinator fetch error is reported as a harmless preparation error
before mutation, not an actual fixture attempt. This worker fetched the supplied
integration bundle with the explicit ref and fast-forwarded successfully.

## Later packaging check — optional VM report mirror STOP

The immediate postfixture registered guards, exact cleanup, and protected-source
checks passed. Later, an optional narrative-report mirror stopped at its
`protected_source` precheck before any report files were written. A bounded
read-only check found the installed `registered-storage.py` mode changed from
**0644** (preflight and immediate postfixture) to **0755** (packaging), with the
same inode833684, owner0/group0, one link, size3378 and required SHA256. Its
storage.py dependency stayed0644 with the required hash; all inspected ancestors
remained root-owned, nonsymlink and non-group/world-writable. The task's expected
0644 comparison therefore stopped the mirror. This task made no chmod or source
metadata correction, and does not establish who changed that mode or when.

The separate read-only registered `--root-guard --json` still exited0 with zero
stderr and root free5208489984 bytes. This did not override the source-mode
precheck or resume VM writes. The optional narrative report, final coordination
copy, and final-report-guard file are independently confirmed absent from the VM;
first-result and original postfixture evidence remain present. The final narrative
and complete report-only package are delivered locally. See
[packaging source metadata](q38vr3-evidence/packaging-source-metadata.json) and
[stopped packaging precheck](q38vr3-evidence/packaging-guard-check.json).

An initial local packaging command continued into its first report-only commit
after the optional mirror failed, creating a premature mirror-PASS annotation.
That annotation is corrected in the final amended report-only commit; no fixture
was repeated and no VM cleanup or source action followed.

## D3N32 timing limitation

Root coordination supplied D3N32 matched-request dispatch **04:15:31Z**.
This actual fixture began **04:18:22.027258Z**, 171.027258 seconds later, and
ended **04:18:22.787051Z**. The supplied coordination did not yet provide the
request completion timestamp. **Actual request/fixture overlap is therefore
UNKNOWN from this task's evidence**, not inferred from concurrent preparation.
No extra synchronization, model query or rerun was performed. Any overlapping
benchmark is a full-configuration sample, not controlled attribution to N76.

## Handoff

Private VM evidence/temp: `/data/logs/q38vr3-20260915`.
Raw outer captures remain private; only safe structured metadata and hashes
are committed. No receipt exists. The first-result and exact cleanup records
are complete. Report-only commit/bundle and correct author/committer attribution
are recorded in `../Q38VR3-handoff.md`.

**STOP after this failure. Root may review the fixed device-name predicate and
assign a separate correction, but this task makes none and performs no further
fixture or model execution. Fixture PASS alone would not authorize native
model/generation acceptance.**
