# Q38VERIFY — actual pinned native fixture FAIL

One authorized pair invocation ran on unchanged source
`1e95cfef94f86f9396fd35f6c1026d61025cbb34`.
**131072 failed with native/container exit 2; 262144 did not run. No receipt or
native fixture acceptance exists.** The single owned container was removed and
independent exact ID/name absence passed. No retry or source correction followed.
Prior Q38FIX's three failed 131072 attempts and missing receipts remain unchanged.

## Actual result

The native launch failed with public code `actual_image_fixture_failed` and
`LaunchError`; retained individual operands are `result=1`, `captured=0`,
`engine_calls=0`. The public fixed failure origin is `run_pinned_image.py:161`.
The first underlying existing failure code and private frame coordinates were
forwarded immediately through task-root `first-cause.json`, `live-status.md` and
`quiescent-handoff.md`, outside Git. No environment variable/value was dumped;
these records do not identify the offending environment entry.

- Actual context window: **2026-09-15T05:42:02.161901+00:00–2026-09-15T05:42:27.548368+00:00**.
- Container: `1d4f7266122cee91eba3ce9f72855fc3d683bbf18b6c2eff79d81fbb70bef5c7`.
- Name: `q38b-fixture-511c3b32921bd637aaa5958e39311071`; uniquely owned by the shipped
  `local-ai-server.q38b-fixture-owner` label/token checks and immutable-ID cleanup.
- Shipped cleanup: `QUIESCENT_REMOVAL_VERIFIED`; independent ID/name absence PASS
  at context terminal and final normal cleanup verification.
- Final quiescent release: **2026-09-15T05:43:45.077135+00:00**. No more VM operations.

## Exact source and conditions

[Eight-file manifest](q38verify-evidence/source-manifest.json) binds committed
bytes, Git blobs, sizes and protected staged modes. Input `Q38NEXT.bundle`
SHA256 `8ace2d758acbfe74dd2ccf28229d40bba0e348b747f76b88a1667535fc7a6b20`.
Required author and committer were verified. Reviewed 162 focused checks and 67
pins were accepted from the supplied source handoff; no broad test rerun or new
source review was used as a launch gate. Later Worker2 source was not adopted.

Exact cached image:
`lmsysorg/sglang@sha256:37bbbd3444732a464bbc68dee4fb0164e0ce9e18e2f027f3fc967f1152d3c262`;
config digest
`sha256:e6238090791a938ab86dd21a9a6394192dad15237e815df557cf83524d54b813`.
The shipped driver performed its OCI relationship/source gates and host runtime
inspection. The existing Q38FIX task-local observer/capture ordering was reused
with new task paths, a bounded deadline and immediate live-status events. Raw
native streams were transported to worker-private 0600 files before postguards.

Host inspection passed: NVIDIA runtime, literal device visibility `none`, exact
`compute,utility`, empty CUDA visibility, no GPU/device request/maps, network
`none`, no ports, read-only source/root, empty private model/key tmpfs, fixture
cache/tmpfs, unchanged image HOME, OpenBLAS threads 1, PID 128 / memory 8 GiB / shm 64 MiB limits,
core 1:1 and existing signal/deadline cleanup. No limits or auth/device gates were
widened. A failed fixture supplies no complete inner native/auth/cache/containment
receipt and no real model/key/GPU/inference acceptance.

## Storage, cleanup and retained evidence

Canonical installed registered guard/dependency identities matched the supplied
SHA256 pins and root 0755 / root 0644 modes with protected ancestry. Full registered
data/root guards passed before staging/start and after terminal/final cleanup.
Both registered ext4 UUIDs and all staged source identities/modes remained exact.
Root free at final verification: **5208813568 bytes**;
6 GiB warning remains, admission above 4 GiB. No new/changed Apport files appeared.
Final verifier observed Linux `6.8.0-134-generic` and host process core 0:0;
fixture core 1:1 was checked before start. Protected ROOTSPACE archives were not
touched. The small root-space variation is not assigned to this task.

- [Context result](q38verify-evidence/context-terminal.json) retains fixed safe
  native failure metadata, runtime gate result, cleanup and postguards.
- [Final normal verification](q38verify-evidence/final-verification.json) retains
  source, protected evidence identities, final guards and exact absence.
- VM source: `/data/build/q38verify-20260915/attempt-1/source`.
- Protected VM records: `/data/logs/q38verify-20260915/attempt-1`.
- Worker task directory: `tasks/Q38VERIFY-20260915/`; `attempt-1-vm.py`
  SHA256 `8b97bbde97e3212678b78c995ae659a804267e945b9f964b61b8706eaf736293`.
- Private stdout 270 B SHA256
  `e4c6a7f9cf5013a6f644493ec3930a1453f07c4367bce683f5f0a785e5e2ddce`;
  private stderr 605 B SHA256
  `210309547fce3dfed09d0bacda5a040c1b1b198495dcdf7614b93190cb78abbb`.
  Raw streams and private exception/stack values remain outside Git in
  `worker-private-attempt-1/` 0700 / files 0600.

Q38VERIFY ended with zero owned containers/processes/auxiliary background work
and no lifecycle/request lease held. D3CAP4 session 01a0a38f retained separate GLM
ownership; only noGPU/noModel/noRealKey/noNetwork fixture overlap was authorized.
No production GLM state is asserted here. No live closure/instance/registry,
services/API/network, real model/key, production HOME/core policy, installer or
CoderNext changes occurred. Root DRAIN THEN STOP steering was consumed before
final quiescent release. Local report-only packaging follows; no further VM
verification, retry, fallback or task phase is scheduled.

Validation for this report: safe-evidence JSON/source-hash reconciliation,
quiet secret/raw-record scan, diff/whitespace/scope/commit metadata and bundle
verification. No test suite is needed for these report-only additions.
