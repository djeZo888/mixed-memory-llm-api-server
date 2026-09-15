# Q38V — FAIL at first actual-image fixture

## Result and owned resources

One unchanged helper invocation failed at context **131072**, after host runtime inspection PASS, with `q38s_image_fixture_failed` / **ATTACH_FAILED**. Helper exit 1, elapsed **0.709 seconds**, `2026-09-15T02:41:54.857551+00:00` to `2026-09-15T02:41:55.566514+00:00`. Context 262144 was not launched. No auth receipt or READY state was produced.

Owned container `3f7a9812c56c72d4f086fdcac29a4d9c6f2cf88d30bdb15ded019b708a76b1b8`: shipped **QUIESCENT_REMOVAL_VERIFIED**, followed by independent exact-ID absence PASS. Created 1 / removed 1 / remaining 0; no unresolved owned identity. The shipped cleanup verifies PID zero and quiescence before non-force removal; no successful fixture exit is claimed. The original container exit code and deeper native category/origin are not retained by the unchanged helper. No raw logs, exception messages/locals, headers, bodies or key values were disclosed. This result does not establish a cache/auth/parser failure cause.

## Verified identities

- Approved Q38B commit `f17ec2c37d4c706752dd3fbe1978519983578b71`; tree `a667371eac8b46642ab87ff8e1d1be26ab501ca4`.
- Root-owned readonly snapshot `/data/build/q38v-20260915/source`; 535 tracked files. Archive SHA256 `47f44a7aa1ef072728fe67e24bc312146e4dc1e5a29730c1b58b00660d5c95a3`; source-manifest SHA256 `4bc0705e36531df5eedababbb3e5b1ff4eb66a0561346445fec6587619a6f5ac`. Pre/post file hashes, ownership, modes, single links and root inode/device all PASS.
- Actual Docker inspect **PASS** via exact reviewed OCI contract: `.Id` `sha256:37bbbd3444732a464bbc68dee4fb0164e0ce9e18e2f027f3fc967f1152d3c262`, domain `oci_platform_manifest`, matching Descriptor. Config remains `sha256:e6238090791a938ab86dd21a9a6394192dad15237e815df557cf83524d54b813`; linux/amd64; image source revision `0bcd822377da7b5718e674eaf9c870d349424dd1`. No pull. Native installed-file hash success was not retained/proven.
- Provenance SHA256 `1f0a49bcbfb0b499d0432b9d4b4b387f6fe5338e084e9e0f7c9578e6f77b1acd`.
- Launcher SHA256 `380da6ca383804f0cb1cad8bf037c9342e69558354ec42d911fb706db716d1be`.
- Host fixture SHA256 `9cdea022e21f1859e097be51094b9d2822dfc1387f8756448dd7b14d8a251d2c`; inner fixture SHA256 `16a1e0b726295e0f0a9f046b5d496dae70f83677f5145ffdb52bfee01671b454`. All other fixture/support hashes are in [source-identities.json](q38v-evidence/source-identities.json).

## Guards and boundaries

Root coordination Revision2 selected the already reviewed protected D3 guard release at commit `7b541017c3e1b2bda80676bcd31bc87d0a4507bc`; both guard/dependency hashes matched Git and protected root-owned executable single-link paths. Corrected data/root guards **PASS pre/post**. Historical obsolete-checkout `/tmp` permission failure remains in separate evidence; no old source or `/tmp` artifact was changed.

Exact `/data` UUID `8daf56f1-5649-4163-9d87-919c2d271875` and `/data/models-large` UUID `a6d4ab58-84e1-4e48-9a67-13ad1c6f6e0a` match pre/post. Exact root free space before stage 5,213,921,280 bytes; postfixture 5,210,636,288 bytes; above the 4 GiB stop threshold. Warnings: below 6 GiB and two small historical root directories. No storage STOP after corrected guard selection.

Host inspect proved the shipped NVIDIA-none/no-device/no-network/readonly/tmpfs/resource policy for context 131072. Actual cache resolver/library/zero-device/auth/parser/template success remains **NOT_PROVEN**. Model load/generation/GPU work, native model-serving lifespan and real model/tool-agent acceptance remain **NOT_TESTED**. Canonical registry remains absent; no protected receipt import. GLM32K, Q38A and D3T were not operated on. No fixture retry, alternative container, source modification or subsequent runtime diagnosis occurred.

## Artifacts and next action

- Private root-owned evidence: ai-vm `/data/q38v-20260915/`; execution record `fixture-execution.json`; raw stdout/stderr and guard reports stay there. Source is separately retained at the path above.
- Final launch plan was published before execution in [fixture-plan.md](q38v-evidence/fixture-plan.md), including exact interpreter/script argv and task paths. Host `-B` suppresses bytecode writes; helper and shipped container command are unchanged.
- Sanitized report/evidence passed a filename-only grep secret-pattern scan before copying into this report-only change. No push.
- **Next action:** separate bounded source/failure-disclosure diagnosis. Inner origin cannot be reconstructed from the surviving sanitized evidence. This FAIL does not authorize model activation or a rerun.

Finalized 2026-09-15T02:44:17.323594+00:00; first actual failure was published immediately, before postchecks. Verification: exact bundle/commit/tree + committed-source verifier PASS; shipped provenance and OCI validators PASS; full source pre/post checks PASS; corrected guards PASS; owned-ID absence PASS; fixture FAIL.
