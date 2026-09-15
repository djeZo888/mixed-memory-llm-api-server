# Q38B bounded pre-live source corrections

2026-09-15 · source worker2 · session `01a0a2bb-a9de-7863-9171-e7edcb2827ba`.
Reviewed base `6cffccbf1927ff610c21cfc6a0bea3b2f14bd85a`;
branch `milestone/q38b-runtime-gates`.

**PASS: bounded Q38 source corrections and 150 focused tests.**
**PENDING: final root review and separately owned integration gaps.**
**NOT_TESTED: actual pinned image, native serving lifespan, GPU/model execution,
live/client acceptance and occupied-context performance.**

## Source changes

1. **Final provenance pin repaired and traced.** The final Q38S output-path
   safety correction happened after its reported 81/282 test runs, rehashed
   fixture provenance, and left the adapter pin stale. Exact one-line
   reconstruction reproduces the old hash. The first Q38B correction changed
   only that pin and verified the actual committed tree; the legitimate
   output-path check is retained. [Full evidence and timestamps](q38b-pin-finalization.md).
2. **Disposable lifetime made explicit.** Docker create obtains a unique name,
   ownership token and immutable ID. All mutations require fresh exact
   name/token/image/ID verification and target only the ID. Actual container
   state must show successful exit, PID zero and no running/paused/restarting
   state. Cleanup uses bounded stop, fresh quiescence inspection, non-force
   removal and independently confirmed absence. Timeout, signals, CLI death,
   output overflow, start failure and identity drift cannot produce PASS.
   Unknown creation completion or daemon failure remains safely unverified.
   Combined CLI output is capped at 128 KiB, without root-disk spooling.
3. **Two proven cache overrides added.** Exact SGLang 0.5.19 source independently
   defaults its base and JIT cache to HOME. Only `SGLANG_CACHE_DIR=/cache/sglang`
   and `SGLANG_JIT_CACHE_DIR=/cache/sglang/jit` were added. HOME is unchanged;
   unrelated overrides remain refused. The native resolver probe verifies
   exact effective paths and private writes, driver-library loading, no GPU
   nodes, and native zero-device discovery. It runs in a separate bounded
   Python child to avoid contaminating the auth fixture's platform/architecture
   caches. [Primary source research and boundaries](../docs/q38b-cache-research.md).
4. **OCI identity domains fixed.** The exact platform manifest `37bbbd...`
   describes config `e623...`; small public manifest/config bytes were freshly
   hashed, without fetching layers. The outer profile/receipt config pin stays
   unchanged. An explicit nested Docker block records observed config or
   platform-manifest ID and domain, exact relationship, platform, source,
   default entrypoint and workdir. Manifest-domain inspect additionally requires
   its matching Descriptor. Installer evidence, auth proof, current inspect and
   container identity must agree; tags, indexes, arbitrary IDs and cross-domain
   substitutions fail closed. [I1c handshake](../docs/q38b-oci-contract.md).
5. **Narrow Manager seam composed after handoff.** Incoming explicitly released
   the seam after frozen L1B `9cb93959105468ea0e140598b51493ee0d13ce9e`, which was
   merged exactly. Dispatch covers declaration, completion, evidence, launcher,
   digest creation, reuse and readiness. Canonical lease, storage/persistence,
   pre-stop checks and recovery invariants remain. Q38 dependencies load only
   when selected, preserving the minimal offline recovery import closure.
6. **Control source closure refreshed under the later explicit handoff.** Root
   stopped installer work and assigned this live source dependency to Q38B.
   Root-reviewed U1B `702e147326868e9b942eee77ce3f75c2b74248f4` was composed.
   Only the closure manifest, matching fixed normal-file list in
   `scripts/control/installation.py`, and focused closure tests are Q38B edits.
   Normal Q38 adapter/runtime/fixture/provenance/manifest dependencies are
   protected by the existing root-file checks. Recovery retains its minimal
   file list and requires neither Q38 files, profiles, data nor inference keys.

The original model/acquisition manifest and both deployment files remain byte
identical: TP1/GPU0, native 131072/262144 contexts, no MTP/1M, port30004.
Current approved publication roster is exactly GLM5.3 and Qwen3.8-27B FP8 per
incoming. L2 owns the separately queued publication/read guard; historical Coder-Next
source/tests remain deferred. No new model or permanent max-two rule was added.
The later Q38 no-thinking client preset remains separate from A2O low-only GLM.

## Actual-image gate shipped, not executed

The fixed fixture mode uses the pinned NVIDIA 1.19.1 `none` contract with
`--runtime nvidia` and `compute,utility` driver capabilities. Before start,
host inspect requires no GPU requests/devices, network none, fixed process,
read-only root, exact private tmpfs/mount policy and resource limits. Native
proof permits only reported global control/UVM nodes and requires successful
loading of `libcuda.so.1` / `libnvidia-ml.so.1` with zero torch devices. This
does not reuse F1DX's unresolved runc/void execution or claim that imports work.

Schema2 `q38b_actual_image_auth` requires all 18 checks, both context results,
cache/device evidence, both distinct verified removed container lifetimes,
launcher/fixture/support-source hashes and the exact observed OCI block. Native
model/engine work remains stubbed; configured context is not occupied proof.
No real key may precede this gate. [Callable commands](../tests/lifecycle/sglang38_fixture/README.md).

No host installation, service activation, disk mutation, reboot, ai-vm access,
image/model/layer download, inference build/runtime execution or real-key work
occurred. Source-worker subprocess tests run only tiny controlled local programs.

## Verification and limitations

| Check | Result |
| --- | --- |
| All eight Q38 test modules | **150 PASS** |
| Exact control normal/recovery closure and protection suite | **17 PASS**, including isolated copied-source happy path and drift rejection |
| Control suite before composing U1B | **133 PASS**, historical intermediate result |
| Full composed U1B control diagnostic | **180 run; 15 setup ERRORs, 1 unexpected success**, from provisional integration fixtures / obsolete expected-failure marker; no aggregate PASS |
| Full lifecycle suite | **554 run; 1 FAIL, 2 ERROR**, entirely pending I1c dependency cases below |
| Recovery isolated snapshot import and Q38 Manager suite | **15 PASS** after lazy-import correction; also included above |
| CLI help, JSON parsing, explicit source/fixture pins, unchanged model/context/manifest/lockfile checks | **PASS** |
| Actual-image and live gates | **NOT_TESTED** |

Full lifecycle unresolved cases are retained without skip/xfail/bypass:

- `RealStorageRoleIntegrationTests.setUpClass`: committed Storage lacks
  `roles=` on `verify`, `guard`, `root_payload_guard`; three methods do not run.
- `test_shared_verifier_gap_data_only_allows_missing_model_volume`: current
  full-only Storage cannot satisfy data-only verification.
- `test_shared_verifier_gap_unregistered_duplicate_mount_alias`: current
  shared verifier accepts the extra alias. This is the one failing assertion.

These are the documented L1B/I1c integration gaps. No uncommitted installer
overlay was used, and installer/shared0.5.14 source was not changed. Control
changes are restricted to the explicitly reassigned closure/file-list seam.
The full suite is explicitly **not an aggregate PASS**. The earlier full Q38B
run also caught the recovery import regression; that owned defect was corrected
and rerun rather than folded into the dependency failures.

The composed U1B diagnostic uses an explicit production `lifecycle.manager`
import before discovery to avoid the test directory's same-name package shadowing
it. Its retained integration fixtures lack the separately supplied provisional
owner fixture changes; the old expected-failure marker now unexpectedly succeeds
with frozen L1B. These are recorded, without changing broader control tests or
gates. Installer work is stopped; its complete test matrix is not a prerequisite
for the independently authorized live-VM source work. The required focused Q38
normal/recovery closure tests are delivered and verified separately.

Reproduce focused source verification:

```sh
python3 -B -m unittest tests.lifecycle.test_qwen38 tests.lifecycle.test_qwen38_image_fixture tests.lifecycle.test_sglang38_file_auth tests.lifecycle.test_qwen38_cache_probe tests.lifecycle.test_qwen38_fixture_lifetime tests.lifecycle.test_qwen38_manager tests.lifecycle.test_qwen38_oci tests.lifecycle.test_qwen38_final_source -q
python3 -B -m unittest discover -s tests/lifecycle -p 'test_*.py' -q
python3 -B -m unittest tests.test_control_installation -q
python3 tests/lifecycle/verify_qwen38_git_source.py --commit HEAD
git diff --check
```

Final commit/tree identities, postcommit and imported-bundle Git-source
happy/drift results, full source test logs, author/committer, filename-only
secret scan, credential-free remote check, feature push, clean-tree and bundle
verification are recorded outside Git in taskroot `final.md`, `session.json`
and publication evidence. This avoids self-referential evidence hash cycles.
The first verified full bundle was created immediately after the focused pin
checkpoint; it is replaced by the final full-history `Q38B.bundle` at delivery.

## Next action

Root reviews this source; the control closure refresh is owned and completed
here, not deferred to installer work. Worker1 later verifies the protected
fixed-root closure and runs the actual image/cache/auth gate before any real
key/model, then live/client and occupied-context acceptance. L2 owns approved
two-model publication/read checks, and D3T owns the untouched llama-specific
placement/context validator and argv bodies. Installer flows remain stopped.
Existing GLM priority and separate client ownership remain in force.
