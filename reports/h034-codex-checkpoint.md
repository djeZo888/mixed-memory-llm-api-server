# H034 — Qwen/Codex compatibility checkpoint

**Qwen works with Codex.** This window repaired the repeated image-tool argument
failure and passed both the original image-generation regression and generation
by a fresh native child. Full Codex integration remains **partial**: an approved
edit completed correctly, but its parent final retained a stale approval state.
MiniMax remains the default; public chat stays in maintenance as authorized.

Window: September 29, 2026, **17:09:44–19:09:44 UTC**. Mac-Orchestrator reviewed
and published; Mac-Worker1 and Mac-Worker2 implemented and tested in bounded,
isolated native CLI sessions. Final application source is
`7b83be2d1f7bc6abcac82dd5b2ef203ded9b9aed`, activated at 18:39:15 UTC.
The [machine-readable result](h034-codex-results.json) retains exact identities,
hashes, timings, settlement and worker terminal receipts.

## What changed

- Replaced the ambiguous empty-object image-capability tool with an explicit
  `query: "capabilities"` contract. Updated its descriptions, installed skill
  and catalog; preserved actual model argument/error bytes. Strict handling
  applies only to the exact reviewed Qwen tool schema. Other tools are unchanged.
- Added bounded stopping after three repeated identical schema failures in an
  owned turn, using the existing cancellation and settlement path.
- Cold-resumed parents and newly spawned children now receive current trusted
  instructions. Historical messages and existing children are preserved.
- Delivered current tools through immutable, hash-checked overlays. The native
  engine image was not rebuilt. Known old skill files migrate with backups;
  unknown local edits are refused.
- Corrected the narrow handling of a failed close operation on a historical
  child. It does not invent ownership of unknown children or accept unknown
  active/success outcomes. Focused regression checks passed; the final live
  continuation did not emit that close call, so direct live coverage is absent.

The provider probes showed the explicit contract succeeds where the real-context
empty-object contract failed. Strict mode alone did not establish a repair.
No model, weights or GPU changes were required.

## Actual live results

| Case | Outcome | Evidence |
|---|---|---|
| Unchanged original image request | **PASS** | One 1024×576 image, correct capability arguments, no schema errors, final inline/download references, settled. |
| Fresh native child generation | **PASS** | Exactly one child and one 1920×1080 image; current instructions; final references and settlement correct. |
| Retained edit before lifecycle fix | **FAIL, settled** | A historical cancelled-child close returned not found; host interrupted before a new child or image job. |
| Retained edit after fix | **PARTIAL** | One fresh child, one real edit job, explicit browser resize approval, correct 1536×864 green-sail image; final handoff failed. |

All three actual new image outputs received independent visual review. The edit
preserved the original upload and retained the scene, lighting and composition
while changing red sails and their reflection to green. Its approved resize was
1920×1080 to 1536×864 with unchanged aspect ratio and zero padding. This is visual
fidelity evidence, not a pixel-identical reconstruction claim.

The edit initially requested unsupported 1920×1080, received a real rejection,
then naturally selected supported 1536×864. Thus **two edit tool calls created
one GPU job**; the fixture requiring exactly one tool call did not pass. An
incorrect skill-resource lookup also recovered through the filesystem. Neither
failure was hidden by rewriting arguments or supplying a rescue prompt.

### Remaining approval handoff defect

The operator approved the normal UI card at **18:46:52.757**. The parent final
was created at **18:47:20.538** and its run ended at **18:47:28.463**. The image
completed at **18:47:28.989**, 526 milliseconds later.

The parent's “pending approval” was already stale. Its statement that no image
had yet been produced preceded actual image completion; that statement is not
being relabelled as fabrication. The image was subsequently associated with the
correct reply, but the final text never obtained its inline image and download
link. The original failed handoff remains visible. A possible read-only follow-up
was skipped when its admission deadline passed; it is **NOT_TESTED**.

## Verification and operating state

Selected source checks passed: 91 guard/resume checks, 57 delivery/migration
checks, 80 compatibility checks and 27 narrow historical-close checks, plus
provider/adapter tests and targeted type checks. These suites overlap and are
not an additive count of unique tests. Earlier actual coding, research,
continuation and frontier-delegation evidence was reused where the implementation
remained compatible; no new MiMo benchmark or frontier live run is claimed.

Final VM/application readback at **18:51:05 UTC**:

- Public chat **HTTP 503**; status **HTTP 200**; maintenance restored.
- Active runs, task containers, acceptance tickets, pending provider requests
  and image jobs: **zero**.
- Codex frontier access remains enabled through reviewed evidence reuse.
  Full image qualification remains disabled; native media input is unsupported.
- Original histories, files, two historical uncertain owners and three
  quarantines are preserved.
- All worker CLI sessions have ended. Worker1's four sessions exited 0.
  Worker2's source session reached its own deadline after exporting work
  (SIGTERM/-15); its final deployment/acceptance session exited **0 at
  18:53:43.929202 UTC**, without deadline termination. An earlier capacity-related
  launch failure is retained separately; it did no implementation work.

## Why this window was needed

The main delays were the repeated image-tool argument failure, discovering that
old adapters/skills were still baked into execution containers, and a resumed
session closing a historical child. Fixing those exposed the remaining async
approval/result handoff instead of a general inability of Qwen to run Codex.
There were three actual new image jobs, not an open-ended image sweep.

The [next bounded plan](h034-next-execution.md) targets the approval handoff,
operation-specific edit dimensions, PDF final-answer honesty and remaining
release checks. Historical failures are preserved; full completion is not claimed.
