# Derived runtime image receipt

This source-only extension records the UUID repair build reported at `2026-09-23T02:47:57.723137+00:00` in the task's `evidence/uuid-repair-build.jsonl`. The derived Docker image ID matches the observed `RUNTIME-CONFIG.json`:

`sha256:dafbccb763cff6a6aa3777c7c0a8cc185d838bd4b9f61bec8007f57f2c7233f8`

Its exact parent is `sha256:4029affd6e90f49e03aa0d132c077508eedbfc266cde12589584da4bbb9d6e83`. The original `BUILD-REPRODUCIBILITY.md`, `build-reproducibility.json`, build records and `image-identity.json` remain unchanged historical records of that parent.

## Single upstream repair

The pinned source remains SGLang commit `0cd8be351d0825488f4b81c8931167bbab618eca`, with the one authorized repair consumed. The patch inserts seven lines, deletes none, and changes only `device_id_to_physical_device_id` in `python/sglang/multimodal_gen/runtime/platforms/cuda.py`. Full GPU UUIDs resolve through NVML's UUID handle and current index, with balanced initialization/shutdown; existing numeric and unset behavior remains unchanged. Errors propagate without a fallback.

| Artifact | SHA256 |
| --- | --- |
| Original `cuda.py` | `c0a99f13fe1d54e1c9d85cc90ea32c09dbd1ca27451159e0c64953881dd82e9f` |
| Repaired `cuda.py` | `7686af293bc4cb31be87c8a188c10e28e49b011c3acb7bac914ca83c5b9ec9de` |
| `sglang-nvml-uuid.patch` | `9522814f5c5c1ccc0e3fc1704172b9249f2551a755a4a70f5397d7e439008c6e` |
| `Dockerfile.uuid-repair` | `58aedcf0f543d3c71efa500c4cd304ffd315292646fa3778ecc72fdafad470b9` |

The Dockerfile checks the source commit and original installed-file hash, applies the patch to the source tree, copies only the repaired Python file into the installed package, and writes a hash receipt. Copies of the Dockerfile, patch and repair receipt accompany this report. The build record reports zero model loads or requests.

## Inherited dependencies and identity limits

The derived recipe performs no package installation or dependency resolution. Its first 23 filesystem layers exactly match the parent's 23 layers; two layers are added. The parent's 240 installed Python distribution versions, OS package inventory, dependency artifact hashes and tool versions therefore remain the dependency evidence, with the installed SGLang `cuda.py` modification explicitly recorded above. See `requirements.freeze.txt`, `python-dependency-inventory.json`, `pip-archive-hashes.json`, `dpkg-versions.tsv` and the original reproducibility receipt. The original SGLang wheel hash describes the unmodified build artifact. No new dependency inventory was exported for this extension; the parent's archive-hash coverage limitations still apply.

Local image metadata separately reports `Id` as the derived image ID above and `RepoDigests` containing `local/qwen-image21@sha256:dafbccb763cff6a6aa3777c7c0a8cc185d838bd4b9f61bec8007f57f2c7233f8`. These are observed local metadata, without a registry publication or pullability claim. The reported image is Linux/amd64, 9,035,673,023 bytes, created at `2026-09-23T02:47:57.504594658Z`.

This extension used local source and build evidence only. Its author made no VM contact, build, GPU request or live readback of the installed repaired file. The repaired-file hash is the exact patch result and configured expected value. Device residency, generation/edit transport, decoded images, visual success and memory margins belong to the parent task's separate runtime evidence and are not asserted here. `derived-image-receipt.json` records input hashes and machine-readable limitations.
