# Q38FIX — source correction; actual fixture STOP

**Incomplete. No native/auth receipt or model acceptance.** One of three allowed
pair attempts ran; its only container exited 2 at 131072. No 262144 invocation.
The registered post-run guard failed with root free space below 4 GiB. No retry,
unrelated cleanup, real model/key use, production change or installer work followed.

## Frozen correction

Source commit `ea4a02e7135db05f192402a74669210ce07c01be`, based on approved
`dad2d58b57ab2367dee254cff1a885567b0c76f4`. Q38DEV observed
`/dev/nvidia-modeset` character 195:254, alongside nvidiactl 195:255 and the two
UVM controls 511:0/511:1. NVIDIA toolkit's
[pinned global-control discoverer](https://raw.githubusercontent.com/NVIDIA/nvidia-container-toolkit/09ceee5dde66ba9ce25c7cc69b1ebd5e6e3266fa/pkg/nvcdi/common-nvml.go)
lists those four names. The probe now admits only their exact observed character
identities; name enumeration and lstat reject accelerator roots, descendants,
symlinks, other types and per-GPU device numbers without opening nodes.

Host literal `none`, inner `none`/`void`, native zero-GPU, cache/auth/source and
lifetime gates remain unchanged. Only probe/test source and mechanical
provenance, adapter digest and three L2 inventory hash entries changed.
No installed closure was changed by this task.

PASS: 143 focused fixture tests; 18 checks from an immutable committed archive;
read-only source review and whitespace/hash checks. Tests cover observed device
metadata and forbidden variants. No full repository or installer suite ran.

## Actual result and evidence limit

Exact image reference:
`lmsysorg/sglang@sha256:37bbbd3444732a464bbc68dee4fb0164e0ce9e18e2f027f3fc967f1152d3c262`.
Frozen eight-file source and its hashes are in
[source-manifest.json](q38fix-evidence/source-manifest.json).
The unchanged shipped pair driver was called with a task-local reporting observer.

Container `d86f3ddad58dd6e493f60f468fa0f00a6db2ba6058244c15718a9aa040d6ab17`:
created **04:33:58.098719Z**, started **04:33:58.405748Z**, exited **2** at
**04:34:29.849217Z**, destroyed **04:34:29.891880Z**, all 2026-09-15 UTC.
Independent exact ID/name absence and unchanged staged hashes were verified at
**04:36:13.567420Z**. Zero owned containers remain; no acceptance receipt exists.

The postguard failure interrupted the observer before it saved the native fixed
failure and shipped lifetime record. Those details are unavailable; Docker's
exit/destroy events and independent absence are retained. This does **not** prove
native cache/auth success or the next native failure's cause.

Before-run root free space was 5,208,317,952 bytes. After the postguard failure,
read-only df showed 3,629,547,520 bytes, below the 4,294,967,296-byte stop floor.
The growth cause was not investigated outside this task's scope. Final registered
guard status is **FAIL**, not cleanup/guard PASS. No further VM writes occurred.

D3PERFVM's recorded request window, 04:31:48.112009–04:32:15.601556Z, ended before
this fixture. Other owners' overlap is not asserted. No GLM request or mutation
was performed by Q38FIX.

## Handoff

[Phase result](q38fix-evidence/phase-result.json) and
[absence/source proof](q38fix-evidence/final-absence-and-source.json) retain exact
identities and limits. Full preparation scripts, failed preflight, fixed-mode
preflight, VM guard/start records, Docker reconciliation and session output remain
in the worker task directory beside this repository. Protected VM artifacts remain
under `/data/build/q38fix-20260915/attempt-1` and
`/data/logs/q38fix-20260915/attempt-1`.

Root must resolve the storage stop before any further authorized actual run.
Future orchestration must preserve the terminal native result before a postguard
can interrupt its recording. Worker2/root final source/result review remains a
gate before real Qwen model/key/live configuration; no successful pair is available.
