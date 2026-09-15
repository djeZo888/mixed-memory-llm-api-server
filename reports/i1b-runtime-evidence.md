# I1b runtime artifact stage

Date: 2026-09-15. Scope: source and explicit worker fixtures only.
Status: **bounded runtime source implemented; whole installer remains incomplete**.
Normal dispatcher mutation through runtime remains fail-closed until the reviewed
L1 authorized lease-export and I1R package-transaction recovery/admission code are
integrated. Their current handshake documents are not implemented approval proof.

## Interface and immutable inputs

`RuntimeStage(config, runner, guard, *, repo=None, uid=0, lock=None)` exposes
read-only `check()` and mutating `apply()`. The dispatcher must retain the same
installer/lifecycle global lease and complete the container stage first. This
module adds no lease and does not alter lifecycle or runtime launch profiles.
`runtime_plan(config, repo=None, lock=None)` provides read-only artifact effects
and exact lock entries for the selected GLM/Qwen runtimes.

- GLM reproduces the reviewed D1 Dockerfile and Dockerfile-specific ignore file,
  with their exact SHA256, llama.cpp commit
  `b29c606e28a01b1bc8c1351026a0fa6e616bf6c4`, Jinja-fix ancestry, clean source,
  both CUDA13.2.1 base digests, SM120a build settings, eight build jobs and the
  D1 Ubuntu snapshot `20260914T000000Z`. This build snapshot is deliberately
  D1's reviewed recipe, distinct from the host prerequisite Ubuntu snapshot.
- Reuse requires actual Docker image inspection. The exact reviewed D1 image ID
  is accepted for fresh probes; a newly built image requires the installer input
  identity label and exact source/release/architecture labels. A conflicting
  mutable image tag fails without overwriting it.
- SGLang pull selects the exact F1A repository digest
  `lmsysorg/sglang@sha256:5027e95bf6ec536856b1b52a91d1f35ff5c564ab83e8a94758a169ff09bb8df3`.
  A matching mutable tag is insufficient. Inspection checks the locked image ID,
  repository digest, Linux and amd64; sandboxed probes verify the four installed
  package versions, 14 source hashes/sizes and the exact F1A argument contract.
- The lock records 100GiB GLM / 40GiB Qwen minimum free build reservations.
  Read-only primary registry manifest verification recorded exact compressed
  config/layer descriptors in [registry evidence](i1b-runtime-registry.json).
  Deduplicated transfer bytes are **3,653,618,310** for both GLM CUDA bases,
  **13,197,815,873** for SGLang, and **16,851,434,151** for their combined union.
  These exclude small index/manifest metadata, Git history and in-image build
  package traffic; filesystem/build capacity reservations remain separate.

The pinned SGLang reference resolves to an OCI index; its linux/amd64 manifest is
`sha256:9611bd4c5624b0e9e17829506188a12f17205f2083de0dd44d6c521733553a50`
and its config digest is
`sha256:8b60bc989525e7352f7e59a05dc3f7dd8d66d20635990143f7db9fe03d50bcb7`.
These distinct registry identities are preserved alongside F1A's observed
Docker29 image-store ID. The registry requests verified computed SHA256 of each
fetched immutable manifest; no image/config/layer blobs were downloaded. The
read-only metadata check follows the [primary registry API](https://distribution.github.io/distribution/spec/api/).
All manifest URLs, layer/config descriptors, platform identity and UTC check time
are recorded in the linked machine-readable evidence and version lock.

## Storage, evidence and resumption

Local source, recipe, temporary files and Docker client configuration are beneath
registered `build`; append-preserved command logs are beneath registered `logs`;
mode0600 completion contracts are beneath registered `services/installer/runtime`.
The shared `storage_io.AnchoredRoot` supplies protected directory/file descriptors.
Subprocess cwd and cache variables use inherited `/proc/self/fd` anchors; a guard
monitor stops work on observed mount loss. No historical UUID or fixed `/data`
root is embedded in the runtime stage.

Commands run with a clean environment, no inherited cloud credentials, no
network for disposable probes, no model mounts, no published port, a read-only
container filesystem and bounded tmpfs. Actual production probes execute through
the concrete writable Runner path. An injected test runner writes a contract
explicitly marked `SYNTHETIC_FIXTURE`; it cannot verify as a production contract.

The llama probes check binary commit/version, every required existing-profile
CLI flag, exact source commit inside the image, CUDA CMake settings, compiler and
package evidence, and the configured number of CUDA devices. This is artifact,
CLI and device-enumeration proof only: model inference and tool calls remain
`NOT_TESTED`. Native SGLang sentinel/auth proof remains `PENDING_I1C`.

Resume reopens protected contracts and hashes their durable evidence files, then
inspects the actual immutable image ID/platform/identity. It never treats a stage
marker alone as completion. Failed probes preserve prior logs and do not seal a
contract; source or image conflicts are refused. Existing recipe bytes are
compared, never silently replaced. A verified whole runtime stage is a no-op.

The narrow Linux process adapter terminates its process group on interruption,
timeout or guard failure, and waits until no group member can still write before
releasing descriptors. A successful parent with surviving descendants is also
refused. Docker daemon storage and server-side build cancellation remain the
container engine's responsibility; I2 must exercise cancellation during an
actual disposable Linux build. The shared Runner/prerequisite I1R ownership fix
remains required independently; this adapter does not modify that owned source.

## Validation

Command:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests/install -p test_runtime.py -v
```

macOS synthetic fixtures: **18 PASS**, covering exact source/recipe/lock checks,
pinned image reuse/pull, mutable-tag/platform/digest refusal, dirty source,
build-without-image refusal, CLI/source/capability failures, daemon root mismatch,
interruption/resume with preserved logs, evidence hash drift, false markers and
fixture-versus-production evidence separation. The stage implementation and its
command boundaries are exercised directly, with no parallel fake installer.

Linux `/proc` inherited-FD/process-group integration: **3 tests present, skipped on
macOS**. Genuine Linux source fetch/build, container start/probe, GPU enumeration,
SGLang auth, service activation and model inference: **NOT_TESTED in this task**.
The D1/F1A historical proof files supply immutable inputs, not current worker GPU
acceptance. Full fresh-host GPU installation and reboot acceptance: **NOT_TESTED**.

Next action: integrate dispatcher and read-only Docker command shapes with the
reviewed I1R boundary; run the Linux fixture in a disposable worker environment,
then I1c consumes protected runtime IDs through reviewed L1/F1S lifecycle APIs.
No live ai-vm operation, installation, model activation or download occurred.
