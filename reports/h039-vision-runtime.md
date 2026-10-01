# H039 C — isolated vision artifact/runtime preparation

Source preparation **PASS**. The original durable download **FAILED** at
00:42:30 UTC with `TimeoutError`; it did not complete. Complete weight verification, runtime fit and
technical accuracy are **NOT_TESTED**. No GPU model was loaded or stopped,
registry/route activated, existing conversation/file/credential changed, image
service replaced, package installed, upstream runtime upgraded or GitHub work
published. The actual native session is
`01a0f4d8-a09f-7922-b970-ce7c401cc220`, mac-worker1, GPT 6.1 Sol Ultra,
CLI 0.159.2, branch `h039/c-vision-artifacts`. The persisted launch receipt
confirms those settings. Native deadline: 01:08:52.694982 UTC on 1 October.
The final source commit is recorded in the task's outside-Git `output/RESULTS.json`.

## Actual placement observation

Read-only GPU identity/process and native Docker ownership were collected at
00:24–00:25 UTC; PCIe link fields at 00:37:37 UTC. No availability wait loop.
Driver reported 595.84; no driver change was made.

| GPU UUID | Guest PCI bus | Current role / owner | Native GPU PID | PCIe maximum; observed current |
| --- | --- | --- | --- | --- |
| `GPU-14c23cbc-12f0-9c61-0fda-7aaf80fbd1bf` | `01:00.0` | Creative Qwen Image, `llm-image-backend`, `IMAGE21-RUNTIME-20260923` | 1028911 | Gen4 x16; Gen1 x16 |
| `GPU-88058d9d-08e5-cb1e-a77a-04cbc1488237` | `02:00.0` | Qwen3.8-27B FP8 q0, 480K, llmctl owner | 74251 | Gen5 x16; Gen1 x16 |
| `GPU-69acfa26-8b60-61b5-702d-aee252c163cc` | `03:00.0` | MiMo RAM plus Blackwell, `H016-MIMO-PERSISTENT-20260927` | 778307 | Gen5 x16; Gen1 x16 |
| `GPU-93dbfca8-ef3a-9628-a798-6a4afd0af528` | `05:00.0` | Qwen3.8-27B FP8 q1, 480K, llmctl owner | 33860 | Gen3 x16 maximum; Gen3 x4 current |

The sole visible Ada is SM8.9 with 49,140 MiB, 32,238 MiB observed used
(32,224 MiB attributed to the diffusion scheduler). No external Ada or smaller
Ada Qwen running container appeared. This agrees with retained H038 retirement
evidence but does not claim a new owned-stop action. Current PCIe generation
readings do not qualify loaded bandwidth or link stability.

Concrete proposal: both BF16 specialists on the existing internal Ada UUID,
**only after root coordinates creative-image reassignment**. It is unavailable
for this pair now. Initial Qwen fraction 0.72 plus OCR 0.18 leaves a nominal
10%; measure at least approximately 7%, 3,440 MiB, free at accepted peaks.
Start one serial crop per inference and 16K total Qwen tokens; extend to 32K
only after the first profile passes. The proposed two-megapixel crop and 4K
output caps need bridge enforcement; the plan generator does not implement
request admission. No same-card memory fit is asserted.

## Official artifact pins and storage

| Public official repository | Immutable HF revision | Files / weight files | Expected bytes, including metadata |
| --- | --- | --- | --- |
| [Qwen/Qwen3.5-9B](https://huggingface.co/Qwen/Qwen3.5-9B) | `c202236235762e1c871ad0ccb60c8ee5ba337b9a` | 16 / 4 | 19,329,393,661 |
| [PaddlePaddle/PaddleOCR-VL-1.6](https://huggingface.co/PaddlePaddle/PaddleOCR-VL-1.6) | `c5630abae1d940eafe0697512a0325494b02ab42` | 20 / 1 | 1,930,462,423 |

The lock lists all 36 official files, sizes, SHA256 and Git blob IDs. LFS SHA256
comes from official public HF metadata; non-LFS files were fetched at the pin,
checked against Git blob IDs and SHA256 calculated. These are **expected
checksums**, not claims that VM weights are verified. Weight files total
21,223,566,848 bytes; all files total 21,259,856,084 bytes. Both pinned configs
specify BF16. Existing top-level storage/cache inventory found no matching
artifact directory. Existing validated files are hashed and reused by the job;
mismatched files and incomplete partials are preserved without overwrite.

Registered model mount `/data/models-large`, UUID
`a6d4ab58-84e1-4e48-9a67-13ad1c6f6e0a`, had 1,731,744,206,848 bytes available;
data UUID `8daf56f1-5649-4163-9d87-919c2d271875` had
1,789,517,221,888 bytes. Root capacity was 5,380,825,088 bytes: the mandatory
4 GiB guard passed and the existing less-than-6-GiB warning is retained.
Registered-storage and root-payload guards passed. Downloads remain on the
model mount and stop before its free space falls below 64 GiB.

The protected installed guard successor at
`/data/services/releases/h005-boot-restore-20260925/scripts` supplies the
canonical lifecycle lease, registered binding, mounted guard and descriptor
anchored writer. The job holds the canonical lease throughout its transaction;
other lifecycle transitions may be busy until settlement. Root should coordinate
integration around it. Root privilege is needed for these protected roots and
registry; no protected configuration is rewritten. Existing system Python
standard-library tools suffice; no system or service venv was modified.

The CPU-only installed-guard selfcheck hash-verified only the two `config.json`
files, 3,126 and 2,059 bytes. Zero weight shards were verified by that check.

## Runtime candidate and remaining support gates

The inspected upstream vLLM source revision
`8bc31bd21075c5ca8a070e6da84e96e2eaf816ad` lists native
`Qwen3_5ForConditionalGeneration` and `PaddleOCRVLForConditionalGeneration`
architectures. Qwen's pinned card describes multimodal serving and its
`qwen3` reasoning parser. Paddle's card demonstrates BF16 element recognition
and an optimized serving path. See the official
[Qwen card at the pin](https://huggingface.co/Qwen/Qwen3.5-9B/blob/c202236235762e1c871ad0ccb60c8ee5ba337b9a/README.md),
[Paddle card at the pin](https://huggingface.co/PaddlePaddle/PaddleOCR-VL-1.6/blob/c5630abae1d940eafe0697512a0325494b02ab42/README.md), and
[vLLM architecture registry at the inspected source](https://github.com/vllm-project/vllm/blob/8bc31bd21075c5ca8a070e6da84e96e2eaf816ad/vllm/model_executor/models/registry.py).

[NVIDIA identifies RTX 6000 Ada as SM8.9](https://developer.nvidia.com/cuda/gpus),
which exceeds [vLLM's documented CUDA device minimum](https://docs.vllm.ai/en/latest/getting_started/installation/gpu/).
That is a hardware eligibility check. Exact BF16, FLA/Mamba, attention,
CUDA/PyTorch and compiled kernel compatibility remains **NOT_TESTED**.

The candidate pins the official vLLM linux/amd64 image manifest
`sha256:5f5e535216848d0c52159c8c13a0af04be5f6fe1a84e79914300610796f76d40`;
no image pull/build was performed. Its correspondence to the inspected source
revision is unknown and must be checked later. The Dockerfile default prints
plans only; it cannot load either model. Separate endpoints, BF16, concurrency
one and immutable local artifact paths are proposed. Remote-code execution is
disabled pending reviewed need and code audit.

OCR recognition returns raw structured task text; D's service envelope must
retain source/page/crop coordinates, revisions, exact labels, evidence and
uncertainties, with derived interpretation separate. Full-page Paddle parsing
usually requires a separate layout model, as the
[official vLLM Paddle recipe explains](https://docs.vllm.ai/projects/recipes/en/latest/PaddlePaddle/PaddleOCR-VL.html).
That third artifact was not downloaded or enabled. No claim of full-page parser,
electrical connectivity, CAD reasoning or Codex native pixel support is made.

## Validation and handoff

**PASS:** 11 isolated tests; Python syntax compilation; 16K/32K dry-run plans;
installed guarded CPU public-config download/hash selfcheck; Git whitespace
check. Tests cover immutable approved-pair/path boundaries, reuse without
network, exact-range resume, retained hash failures and partials, expiry,
storage failure before network, two-hour launch/no retry/log redaction, combined
reserve and closed activation gates. They do not qualify new native placement.

The durable job's exact unit/PID/deadline and immediate state are recorded in
the matching JSON and outside-Git `output/download-launch.json`. Its manifest,
incremental bytes and terminal status remain on ai-vm. A pending download is
**NOT_TESTED** for complete artifact integrity. Adoption means inspect those
receipts, not launch a duplicate. No unlimited retry or destructive cleanup.
Terminal `VERIFIED` requires all 36 hashes and a successful supervisor outcome;
bytes, partials and downloaded-but-unhashed files are separate states. Deadline
or stop retains partials. If storage guards prevent receipt writes, preserve
the supervisor failure instead of treating stale state as success.

The paid CLI closes immediately after one launch/handoff snapshot and evidence
commit, without waiting for progress. Its native/outer terminal receipts are
written by the existing wrapper after closure. Next: root reviews C/D, adopts
the bounded job, and schedules a separate reviewed deployment, simultaneous
VRAM measurement and technical accuracy session once hashes and GPU ownership
allow it. No root handoff or roster file was edited.

Durable launch at **2026-10-01T00:40:45+00:00**: unit `h039-vision-20261001-c-01a0f4d8.service`,
main PID **1860339**, deadline **2026-10-01T02:40:45+00:00**.
Immediate artifact status: **RUNNING**;
0 files / 0 weights verified in that
snapshot, 0 recorded bytes. The earlier two-config
selfcheck is separate evidence. RuntimeMax is two hours, restart disabled,
15-second supervisor stop grace. The absolute work deadline is enforced inside
the process; it is independently bounded beyond the initial coordination window.
The running unit's `Result=success` is not a terminal download pass.

Artifact root: `/data/models-large/h039-vision-20261001-c-01a0f4d8`.
Pinned staged manifest: `/data/build/h039-vision-20261001-c-01a0f4d8/artifacts.lock.json`.
Receipt manifest: `/data/logs/h039-vision-20261001-c-01a0f4d8/manifest.json`.
Incremental/terminal receipt: `/data/logs/h039-vision-20261001-c-01a0f4d8/status.json`.

The initial commit attempt failed with exit 128 because this isolated checkout
had no Git author identity. The retry uses a task-specific `Codex H039 C`
identity per invocation; shared Git configuration is unchanged. This failed
attempt is retained in the JSON evidence.

## C-recovery-01 — ready for root review, no retry launched

Exact adopted session remains `01a0f4d8-a09f-7922-b970-ce7c401cc220`,
GPT 6.1 Sol Ultra, native hard deadline 01:08:52 UTC. Root reported the original
native and outer wrappers exited zero at 00:49; that source-preparation exit
never qualifies the background download.

The preserved failed job reports `FAILED` / `TimeoutError`, finished
00:42:29.939831 UTC; systemd records failure at 00:42:30, MainPID 0,
`Result=exit-code`, main exit 1, empty control group. PID 1860339 is absent.
Lease observation and a nonblocking acquisition confirmed no original lifecycle
owner remains. There are 13 hash-verified files including Qwen shard 1,
5,276,436,216 bytes, expected SHA256
`db6f444b43d318c92f360a13a25561a6a65b10c0631b8ed305a426dbaa6c380e`.
Shard 2's `.partial` is retained at zero bytes. No verified artifact or partial
was changed or deleted in recovery preparation. The original did not log the
network phase, so opening-versus-reading timeout is unresolved.

Exact original status, manifest and supervisor JSON are archived, without
rewriting the originals, at
`/data/logs/h039-vision-20261001-c-01a0f4d8/preserved-c-recovery-01/`.
Hashes and a local outside-Git copy are in the recovery output. The original
status hash is `dc8d1cdb22804ecbcdb278506ea74fd7a230886339e545e461ab7a90d8b0c217`.
All approved revision/file pins are unchanged.

Narrow fixes: configurable 1–600-second socket-operation timeout (proposed
180 seconds), clamped to time remaining at connection, with the existing absolute
process alarm enforcing expiry during subsequent reads; incremental `read1`
retention; sanitized network-phase enums; separate attempt receipts and a unique
claim; exact original manifest and device/inode checks before reuse. Existing
final files are rehashed and reused, and failed/partial files retained. The outer
handler previously caught normal `sys.exit(0)` as `BaseException`; corrected exit
handling permits a truthful success. Finalization rejects another invocation's
receipt. None of these changes adds automatic retries.

Proposed unit: `h039-vision-20261001-c-01a0f4d8-recovery-01.service`.
Proposed deadline: **2026-10-01 02:25:00 UTC**, never later; runtime maximum is
clamped to remaining time and at most two hours, restart disabled, 15-second
supervisor receipt/stop grace. Network timeout: 180 seconds. Reuse the original
artifact root `/data/models-large/h039-vision-20261001-c-01a0f4d8`,
registered model UUID `a6d4ab58-84e1-4e48-9a67-13ad1c6f6e0a`,
device 2081, inode 140247041. New build and log roots use the distinct
`h039-vision-20261001-c-01a0f4d8-recovery-01` namespace. No second model root.

**PASS:** 22 isolated tests, syntax compilation, normal CLI help exit, unchanged
pin-manifest comparison and installed guarded failure preservation. The first
expanded test run had three fixture constructor errors; the fixture was fixed,
the failed result retained outside Git, and all 21 then passed; the final suite with an in-place-rerun rejection test passed 22. Full retry,
long network reliability and complete weight integrity remain **NOT_TESTED**.
No candidate retry was staged or launched. The preparation-only launcher emits
concrete argv/properties; executing a recovery requires an explicit reviewed
operator gate after root GO through INBOX. It never waits for that GO.

Recovery handoff: `../C-recovery-01/OUTBOX.md` and
`../C-recovery-01/output/RESULTS.json`, with the actual source commit and diff.
The original C `../OUTBOX.md` remains historical and is linked there. Closing
READY_FOR_ROOT_REVIEW preserves compaction priority and the paid deadline.

Root GO arrived after the source commit, pinning the previously reviewed
21-test artifact-job source. The sealed final source includes the additional
in-place legacy-rerun rejection and its 22nd test. `artifact_job.py` therefore
does not match the GO hash (reviewed `1428220136e01a309bcccee9055c9d3fd59778a39ca832c2467ed2061a61340d`,
current `26a545dee9e51077e0d1984275928b0b4a891c7847c7755f97106dddb91838c6`).
The launch/stage scripts and immutable manifest do match. INBOX explicitly
instructs stop/re-export if source changed. Recovery remains
**READY_FOR_ROOT_REVIEW**, unstaged and unlaunched; no paid wait for updated GO.
