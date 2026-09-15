# L1B bounded lifecycle integration corrections

Date: 2026-09-15. Reviewed base: `4ab862f` (L1 `bed7532`, I1W `bb007686`).
**Source corrections complete; combined integration acceptance remains pending.**
Worker-only source and synthetic tests: no ai-vm access, host installation,
services, disks, model acquisition, real keys, inference or live claims.

## Corrections

1. `_BoundMountedGuard.check_path` forwards the actual absolute operation path
   through I1W, retains stable registration identity comparison, copies the
   returned snapshot and sanitizes errors. Missing path capability fails closed.
   The historical fixture now projects paths with a public capability-bearing
   object instead of a lambda. Actual writer tests establish a successful write,
   successful preflight, opened anchor, deliberate same-device descendant mount
   insertion, and refusal with unchanged prior JSON. Exact phase assertions
   exclude an unrelated early exception. Existing detach, mount-ID, descriptor
   cleanup, historical evidence and truthful recovery tests still pass.
2. `persistent_json` anchors the most-specific registered containing services,
   installer-state or logs root, checks the normalized data-relative and
   anchor-relative suffix, and avoids `mkdir('.')` for direct log reports.
   Equal data/models roots no longer require opening their ambiguous common
   root for service writes. I1W still owns final role/path authorization; no
   model subtree is reclassified. Recovery fixture paths were updated to the
   same declared-root contract and relative suffix.
3. Non-legacy `prepare_start(target)` calls the existing read-only
   `create_args(target)` image/argument checks before a switch consumer can stop
   the old backend. Missing image, retagged ID and wrong entrypoint each reach
   image inspection with zero old stop/create/start/remove calls. The positive
   sequence borrows one canonical lease, retains one active backend, and repeats
   validation during start and before create. Late image drift refuses creation.
   Legacy compose behavior and existing source/auth/evidence guards remain.

The public pre-stop interface was frozen in taskroot `handshake.md` before test
integration; its durable form is [L1B handoff](../docs/lifecycle/l1b-handoff.md).
No new preflight framework, lease, writer, profile or runtime environment exists.

## Executed verification

All Python commands used `python3 -B -m unittest`. Logs are delivered beside the
full task bundle, outside the repository. Failures were retained, not marked as
expected successes or bypassed.

| Command / scope | Result |
| --- | --- |
| `tests.lifecycle.test_mounted_guard tests.lifecycle.test_real_storage_io tests.lifecycle.test_recovery_storage tests.lifecycle.test_start_preflight -v` | **42 PASS**: 12 forwarding, 11 actual-writer, 13 recovery/admission, 6 image preflight |
| `discover -s tests/lifecycle -p test_real_storage_roles.py -v` | **1 full-role preparation PASS; 1 explicit class setup ERROR** for absent I1c role API; 3 role integration methods did not execute |
| Same role command in isolated copy with supplied frozen I1c Storage | **4 PASS: provisional actual-source evidence**, including all 3 role methods |
| `discover -s tests/lifecycle -v` | **485 executed, 482 PASS, 1 FAIL, 2 test ERROR; plus 1 class setup ERROR** (unittest summary: failures=1, errors=3) |
| Same lifecycle command in isolated copy with frozen I1c Storage | **488 tests: 487 PASS, 1 unchanged Qwen38 pin ERROR**; role/alias failures close provisionally |
| `discover -s tests/install -p 'test_storage_io*.py' -v` | **66 PASS, 1 actual-Linux SKIP** |
| `discover -s tests/install -v` | **313 tests: 296 PASS, 2 FAIL, 11 ERROR, 4 Linux SKIP** |
| `bash tests/shell/test-llmctl-lifecycle-static.sh` | PASS |
| `bash tests/shell/test-llmctl-static.sh` | PASS |
| `git diff --check` | PASS |

The actual writer fixtures use local descriptors with synthetic discovery and
mountinfo. The original fixture's constructor intentionally defaults to full
verification and does **not** establish data-only acceptance. The new role
dependency fixture inherits real Storage `verify`, `guard`, `_snapshot`, `_mount`
and `_capacity`, supplies only local path mapping/read-only command responses,
and passes roles into the real I1W guard. Its default full-verifier/writer smoke
passes equal/nested/sibling layouts. No verifier or role attestation is invented
by that role fixture. The older snapshot-discovery fixture explicitly retains
its full-only verifier signature, calling the real superclass full verifier;
it cannot attest partial roles. This preserves its existing full guard when
the frozen I1c API is overlaid, while actual partial verification belongs to the
new independent role fixture. The first overlay aggregate exposed this seam
mismatch; no production guard was changed to address it.

## Separately owned blockers

### I1c Storage source: provisional actual-source PASS, committed integration pending

The committed base's `Storage.verify`, `guard` and `root_payload_guard` lack
`roles=`. New integration setup intentionally errors with that exact dependency.
Existing `test_shared_verifier_gap_data_only_allows_missing_model_volume` errors;
`test_shared_verifier_gap_unregistered_duplicate_mount_alias` fails because the
extra alias is accepted. Neither historical guard was removed or weakened.

During verification, taskroot `incoming.md` supplied `I1C-STORAGE-FROZEN.patch`,
SHA256 `4a2ecd75e94d0724cd5428ed383ec2687a473f212f95192dd5be03f2de3e8148`.
Its hash and single-file scope were verified, then it was applied only in
taskroot `i1c-verification-copy`; owned checkout `scripts/install/storage.py`
is unchanged. It is **uncommitted frozen dependency TEST INPUT**, not reviewed
production source. All four role/writer tests pass there, using actual inherited
Storage verification and actual I1W. This closes the provisional consumer test
case, not committed integration or runtime acceptance.

Required final handoff: committed reviewed I1c Storage implementing the published roles
contract, full stable registration identity, explicit verified roles, omitted
unverified model device/capacity, data-only unavailable-model persistence and
alias rejection. Consume that source without editing it, then repeat the three
integration tests: equal-root normal save/host-report/trusted stop;
split missing-model data-only save/report/stop with full host guard refusal;
and denied data-only model anchors/paths for equal/nested/sibling layouts.
These methods pass only against the isolated frozen source at this point;
the committed L1B base deliberately retains its explicit dependency error.

### I1O installer callers/completion: separate failure

The unchanged installer aggregate retains **2 FAIL + 11 ERROR** in
`test_container.ContainerTests`. Current `_inhibit`/`recover_policy` callers hit
the authoritative package ownership gate (`PrerequisiteError`); lifecycle does
not weaken that gate or restore policy. I1O must integrate the canonical lease
and package watcher export/caller lifetime, then finish source/instance/recovery/
boot installation and selected-stage acceptance. Full installer readiness
remains false. No install/common source was changed by L1B.

### Qwen38 source pin: separate unchanged source failure

`test_receipt_schema_and_source_fixture_checks_agree` errors with
`qwen38_source_profile_pin_mismatch` while reading SGLang38 provenance.
`scripts/lifecycle/qwen38.py`, its provenance and the test are byte-unchanged
from `4ab862f`; L1B has no ownership of their source/evidence pins. Route this
to the Qwen38 source owner. Do not bypass or update the pin in this patch.

## Preserved gates / next action

Canonical borrowed lease and close-only OFD export, pending package admission,
one active backend, UUID/mount/instance/evidence validation, historical import,
auth-image checks and recovery `state_persisted:false` remain mandatory.
Restore storage and repeat a failed durable stop before trusting reboot intent.

Review and consume this bounded source bundle immediately; U1B can use the frozen
pre-stop contract. Integrate published I1c source and I1O callers separately and
rerun the declared failures. Actual Linux bind insertion/lazy loss, installed
systemd boot/reboot, package cgroups, auth-image execution, GPU inference and
fresh-install acceptance remain **NOT_TESTED** on this worker.
Incoming GLM32K/output2048 guidance was read: those are baseline test limits;
this patch changes no context/output profiles or readiness claims.
