# Q38FIX — three attempts exhausted; no native acceptance

**STOP: all three allowed actual pair attempts were used, with three containers total.**
Every 131072 invocation failed; 262144 never ran. Neither context has native PASS,
and no auth/acceptance receipt exists. The original execution bound was
2026-09-15 **04:27:37Z–05:57:37Z**. Final cleanup verification completed at
05:17:10.912442Z. Q38FIX operations are stopped; **Q38NEXT source ownership is Worker2**.
This publication changes reports only and makes no VM calls.

## Source and focused checks

Approved base: `dad2d58b57ab2367dee254cff1a885567b0c76f4`.
Final executed source: `a0d70509759927a1acde8f12d1149eeac4e4a034`, subsequently
reviewed/merged by root. Exact image:
`lmsysorg/sglang@sha256:37bbbd3444732a464bbc68dee4fb0164e0ce9e18e2f027f3fc967f1152d3c262`;
image config ID `sha256:e6238090791a938ab86dd21a9a6394192dad15237e815df557cf83524d54b813`.
Final provenance SHA256:
`4f8ac18cab3ea1fb58ec625c7a0cb77f22105bac1761ce196a3eb05f91b3809e`.

The fixture admits the observed modeset character device 195:254 while retaining
accelerator/symlink rejection. Final UVM handling permits dynamic majors; the
attempt1 current-boot major511 constraint was removed. Host NVIDIA `none`, inner
`none`/`void`, native zero-GPU, isolated cache, auth, secret and lifetime gates remain.
Later corrections enforce core1:1, retain bounded fault stderr privately before
postguards, and set fixture-only `OPENBLAS_NUM_THREADS=1`; pids128 remains fixed.
No production launcher/runtime/Manager/installer behavior was changed.
Primary support: [NVIDIA control names](https://raw.githubusercontent.com/NVIDIA/nvidia-container-toolkit/09ceee5dde66ba9ce25c7cc69b1ebd5e6e3266fa/pkg/nvcdi/common-nvml.go),
[Linux6.8 piped-core limit1 short-circuit](https://raw.githubusercontent.com/torvalds/linux/v6.8/fs/coredump.c),
[OpenBLAS startup thread control](https://www.openmathlib.org/OpenBLAS/docs/runtime_variables/).

[90 final focused tests](q38fix-evidence/final-focused-tests.txt) and
[15 transport checks](q38fix-evidence/final-transport-tests.txt) passed during execution.
[Source integrity](q38fix-evidence/final-source-integrity.json) verifies the frozen
closure, mechanical adapter/provenance/L2 synchronization and exact task attribution.
It is source-only evidence. No source bytes changed after attempt3; packaging ran no tests.

## Actual results

All times below are 2026-09-15 UTC, from context start through cleanup verification;
attempt1 ends at the retained Docker destroy event.

| Attempt | Executed source | Window | 131072 result |
|---|---|---|---|
|1|`ea4a02e7135db05f192402a74669210ce07c01be`|04:33:58.044989–04:34:29.891880|Exit2; removed; postguard STOP; native output UNKNOWN|
|2|`a27948661c3f295dcb74a8ffbdf515c2d9990d22`|05:11:01.865150–05:11:09.529132|Exit2; OpenBLAS thread creation failure; removed; guards PASS|
|3|`a0d70509759927a1acde8f12d1149eeac4e4a034`|05:14:51.785098–05:15:17.354216|Exit2; combined launch-setup predicate failed; removed; guards PASS|

**Attempt1 remains historical, unchanged:** [phase result](q38fix-evidence/phase-result.json),
[source manifest](q38fix-evidence/source-manifest.json),
[Docker terminal events](q38fix-evidence/docker-terminal-events.txt) and
[independent absence](q38fix-evidence/final-absence-and-source.json).
Its postguard interrupted recording before native output/lifetime details were saved.
Root free space fell from 5,208,317,952 to 3,629,547,520 bytes, below4GiB; that
historical guard remains FAIL. ROOTSPACE later performed separately authorized
recovery and root cleared the pause after full guards passed at05:00:12.981924Z.
Correcting unpublished attribution did not change the original executed `ea4` reference.

**Attempt2:** [terminal](q38fix-evidence/attempt-2-terminal.json) and
[manifest](q38fix-evidence/attempt-2-manifest.json).
Retained private stderr identifies OpenBLAS pthread creation failure at thread63/64
while installed SciPy imports `_fblas`, ending in KeyboardInterrupt. This supports
the final fixture-only thread-demand correction; it does not recover attempt1's output.

**Attempt3 / current known gap:** [terminal](q38fix-evidence/attempt-3-terminal.json) and
[manifest](q38fix-evidence/attempt-3-manifest.json).
`run_pinned_image.py:758` rejected
`result == 0 and len(captured) == 1 and len(engine_calls) == 1`
after `launcher.main(argv)` returned. Which operand failed and any swallowed launcher
exception are **UNKNOWN**. Stderr is empty. Reaching this later check establishes
partial progress only; it is not cache/auth acceptance. No fourth attempt ran.

## Cleanup, storage and ownership

[Final independent verification](q38fix-evidence/final-cleanup-and-guards.json),
05:17:10.434465Z–05:17:10.912442Z, records all three exact container ID/name pairs
absent, every staged source matching its executed commit, no receipts, and full
registered data/root guards PASS. Root free space was **5,208,211,456 bytes**.
Attempts2/3 used checked core1:1 and produced no new/changed Apport files;
both monitored directories were empty. Attempt3 root delta was0;
attempt2 delta was−163,840 bytes, without Apport growth. Concurrent root variation
is not attributed to the fixture. Historical attempt1 cleanup/guard evidence is preserved.

No GLM request or mutation was made by Q38FIX. D3PERFVM's request window
04:31:48.112009–04:32:15.601556Z ended before attempt1. Coordinator-recorded D3CAP2
transition start05:09:01Z overlaps attempt2's window; precise request overlap and
subsequent D3CAP activity remain the owner's evidence.

Raw native streams, synthetic inputs and crash archives remain outside Git; selected
records contain only safe terminal metadata, hashes and guard/absence facts.
The complete local final-verification artifact has SHA256
`32f9b320828530dd1cf98d52f0c5db754d398b1a52c55eea0892e973efc1c5bd`.
Q38FIX owns no surviving container or real server lifecycle/request work.
Worker2 owns Q38NEXT source investigation. **No real Qwen model/key/live configuration
activation follows from these failures; independent final review and actual acceptance remain required.**
