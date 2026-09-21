# Q38VR2 — actual cache diagnostic retry FAIL; bounded task complete

## Result

**131072 FAIL. 262144 NOT_RUN. No receipt. Installer STOPPED.**

One unchanged shipped `tests/lifecycle/sglang38_fixture/run_fixture.py`
invocation ran through Worker1 `ssh ai-vm`, using exact reviewed integration
`1e65e17534ae6be3a23ec54bda800ad64fcee7d8` with reviewed Q38VC
`77e232d868bc29082d07d6c143a677b6c1a73e3f`.

Execution began **2026-09-15T03:43:28.295562+00:00** and finished
**2026-09-15T03:43:28.981661+00:00**, elapsed **0.683699 seconds**.
The host fixture exited **1**, fixed code `q38s_image_fixture_failed`, outcome
`ATTACH_FAILED`. Attach CLI and observed container exit were both **2**;
neither retained signal field established a signal.

The first terminal result was published immediately, before independent
postchecks and narrative packaging, to `../phase-result.md`, its committed
[copy](q38vr2-evidence/phase-result.md), and
`/data/logs/q38vr2-20260915/phase-result.md` on ai-vm. The shipped runner exposes
no intermediate 128K PASS event; its unchanged internal loop permits 256K only
after every first-context result check and exact owned cleanup pass.

## Newly observed fixed diagnostic

| Field | Observed value |
| --- | --- |
| Cache child fixed code | `no_gpu_runtime_environment_required` |
| Cache child safe origin | `cache_probe.py:196`, `ProbeError` |
| Enclosing fixed code | `actual_image_fixture_failed` |
| Enclosing safe origin | `run_pinned_image.py:599`, `FixtureFailure` |
| Host runtime inspection | `PASS_HOST_INSPECT`, context 131072 |
| Failure kind / phase / operation | `CLI_NONZERO_EXIT` / `ATTACH` / `START_ATTACH` |
| Inner stdout capture | COMPLETE, 343 bytes; SHA256 `5ede23d097093f0f56c0c4dfb749982e62db8e206a54eb2d1801ace510d72aa6` |
| Inner stderr capture | COMPLETE, 0 bytes |

Static mapping of the reported child origin identifies the conjunction requiring
`NVIDIA_VISIBLE_DEVICES == "none"`,
`NVIDIA_DRIVER_CAPABILITIES == "compute,utility"`, and
`CUDA_VISIBLE_DEVICES == ""`. The observed diagnostic establishes that this
compound predicate failed in the cache child. **It does not establish which
comparison failed, whether a variable was absent, any actual value, or the
underlying cause.** Host inspection PASS describes the container configuration;
it does not establish what the child observed. No environment was captured or
printed to investigate this discrepancy.

The enclosing origin identifies rejection by the cache-child result gate. The
prior Q38VR retained only that enclosing boundary; its underlying cause remained
unknown. This run adds the fixed child code and origin, without claiming a
broader cause or a correction. No raw errors, exception messages, locals,
traceback text, environment values, key material, prompts or child output are
included. Full safe structured evidence:
[fixture-execution.json](q38vr2-evidence/fixture-execution.json).

## Exact owned cleanup

- Container ID: `a176ead245adb6824d7e6d962838c751436c5eaf8a1212f337c5469420b6cf5f`.
- Container name: `q38b-fixture-784d4d9603cb3c8c4ca52eefa1c51021`.
- Shipped cleanup: **QUIESCENT_REMOVAL_VERIFIED**, after exact ownership and
  PID-zero quiescence checks, non-force removal and absence verification.
- Independent successful Docker listings filtered by the exact full ID and exact
  name each returned zero stdout/stderr bytes. **Created 1, removed 1, remaining 0.**
- Additional cleanup mutations: **0**. No uncertain owned identity remains.

The earlier Q38VR exact ID
`411f949b60cd102390123cd75eddc6f2ca0abe186e1c6225bbfaa4a56d048e9a` and its exact
name were independently absent before launch. Prior run paths were preserved.
No arbitrary deletion, forced removal, pruning, retry or alternative invoker
occurred. See [final-checks.json](q38vr2-evidence/final-checks.json).

## Source, registration and guard evidence

The fresh source snapshot is `/data/build/q38vr2-20260915/source`: **870** exact
committed files, tree `98f7f9f59c038025a79b2febc83fe62fcd2dc2a3`, root-owned
directories0555 and files0444 or executable0555. Its new parent is root:root0700;
source device2065/inode44433419. All committed file hashes, modes, single links
and protected ancestry passed staging and prelaunch checks. Final checks
reverified the fixture, provenance, adapter, OCI and launcher files plus private
parent identities. Historical source trees and model weights were not rehashed.

- Archive SHA256: `d1887fb969ce9e3423d4f551fc6d1523b71e37f9df72ebd5da71c4ac1a5c87bf`.
- [Source manifest](q38vr2-evidence/source-manifest.json) SHA256:
  `901e56d00abf0ebedc550ace05fde4fa1a73e23b5f72a63915c9f00e6a6a0cec`.
- Current provenance SHA256:
  `214b1ae26f31718e5acb2d210622d2a745fbc536658c8d589df40e35e178cbfe`.
- Current outer fixture SHA256:
  `954ba40800eed06e3d515d118f24a55ae5755ad8c9632326a8dc4cfd15b2c7ac`.
- Current inner fixture SHA256:
  `b7ab0b200a73267d05e615afef0eaf0e3c277537e7002b1e9c12da853551e643`.
- Current cache probe SHA256:
  `1983823892cf28f9b0ecfffa54c31442774d86e5851cb4d5337dc9537f7c8983`.
- Current adapter SHA256:
  `6a8b1aa41aad22b98ac4da4fd14bc846c1a246d2b92690fd04757c1adabda822`.

The actual authoritative guard was exclusively the fixed installed
`/usr/local/lib/llm-server/control-api/scripts/common/registered-storage.py`,
SHA256 `21cf082a841aeab9470bd6704b77104961b9d4afcaec696d90aa22b65f5b6f3d`,
with actual dependency `scripts/install/storage.py`, SHA256
`4f834e92d149ea1955e79d34c53c18bf8c5846a4121d779e135a50d31a615505`.
Exact hashes and protected ancestry passed before writes, before launch and
after the fixture. Both installed files are distinct from this task's source.

Registration `/etc/local-ai-server/storage.json` remained root:root0600 under
parent0700, SHA256
`626db7130b644199f5f632b2ac3c04f86cdd382121573aa6f3825bbca8de9c27`.
The installed control manifest retained SHA256
`bb0176749bd35deace1643d1a70c42be92a9f0b7bc629d41663c594678365f55`;
its older `5e713441d9ea164b81860ee795c5ef35972ee8e3` closure was not refreshed.
Only the two authoritative guard source files were rehashed there; no renewed
full installed-closure audit is claimed. Corrected D3 hashes in supplied
[VM-GUARDS.json](q38vr2-evidence/VM-GUARDS.json) also passed as external source
checks; they were not used as a legacy execution fallback.

| Check | Result |
| --- | --- |
| Registered data and root guards preflight / prestage / prelaunch / postfixture | PASS |
| Data UUID | `8daf56f1-5649-4163-9d87-919c2d271875` |
| Models UUID | `a6d4ab58-84e1-4e48-9a67-13ad1c6f6e0a` |
| Exact mountpoints, ext4, whole-filesystem root `/`, declared roots | PASS pre/post |
| Root available bytes preflight / final postfixture | 5209874432 / 5209075712 |
| Root STOP below 4 GiB | Not triggered; below-6-GiB warning retained |
| `/data/logs` | uid0/gid1000/mode2755/inode47972353, unchanged |
| `/data/build` | uid0/gid1001/mode2755/inode21757953, unchanged |
| Shipped provenance / reviewed OCI relationship | PASS before launch |
| Selected GLM ID/image/status/PID/start/restart metadata | Exact digest unchanged |
| `llm-control.service` | inactive/dead, disabled, MainPID0 |
| Native fixture / larger context | FAIL131072 / NOT_RUN262144 |
| Native model/generation/client acceptance | NOT_TESTED |

The exact already-pulled image
`lmsysorg/sglang@sha256:37bbbd3444732a464bbc68dee4fb0164e0ce9e18e2f027f3fc967f1152d3c262`
was used without pulling. Reviewed `qwen38_oci` validation passed for its
platform-manifest image-ID domain and config digest
`sha256:e6238090791a938ab86dd21a9a6394192dad15237e815df557cf83524d54b813`,
linux/amd64, source revision `0bcd822377da7b5718e674eaf9c870d349424dd1`.

## Verification commands and preserved boundaries

The [launch plan](q38vr2-evidence/fixture-plan.md) records the exact unchanged
invocation. Shipped runtime options, resource limits, timeout/signal handling,
ownership, PASS assertions and cleanup were preserved. Actual host inspection
confirmed NVIDIA runtime, visible devices `none`, capabilities `compute,utility`,
no GPU/device maps, network none, readonly root/source and private tmpfs for
synthetic model/secrets/cache. No host model or real key was mounted or read.

Authoritative guard commands (no identity or report-root overrides):

```text
sudo -n /usr/bin/python3 -I -B /usr/local/lib/llm-server/control-api/scripts/common/registered-storage.py --json
sudo -n /usr/bin/python3 -I -B /usr/local/lib/llm-server/control-api/scripts/common/registered-storage.py --root-guard --json
```

Optional guard reports were written only inside the existing protected task
parent `/data/logs/q38vr2-20260915/evidence`. Evidence/temp parents are root0700
and files0600. The proven prior staging/recorder/postcheck procedure was reused
with fresh paths and current committed hashes, without fixture source edits or
a new diagnostic framework. A local postcheck preparation substring error
occurred before any VM postcheck invocation; it was corrected locally and did
not rerun or affect the fixture. The prepared Python was syntax-checked.

Independent bounded source review found no launch blocker and confirmed the
reported child predicate. Supplied coordination was reread at staging, launch,
postresult and packaging boundaries; no new blocker was present. Local checks
reconciled all 870 source-manifest entries against the exact Git commit and
validated report/fixture/cleanup evidence consistency. No source test suite was
rerun for this report-only change. Final whitespace, secret, scope, attribution
and bundle checks are recorded in `../Q38VR2-handoff.md`.

No installer action, package installation, model download, runtime build,
service/network change, model load, kernel/inference execution, API request,
client ownership, GLM restart or live instance/receipt publication occurred.
Existing GLM remains at its authorized 32K setting. Historical task artifacts,
shared registry/mounts/control/key/source closure were not changed.

## Handoff

Private VM evidence and temp root: `/data/logs/q38vr2-20260915`.
Raw outer capture stays private; committed evidence contains only the shipped
safe structured result and lengths/hashes. No auth receipt exists.

**Next action: Root reviews the fixed child predicate and decides whether to
authorize a separate bounded source correction. This task performs no correction
or further retry. No native model/generation approval follows from this fixture
result; even full synthetic fixture PASS alone would not grant it.**
