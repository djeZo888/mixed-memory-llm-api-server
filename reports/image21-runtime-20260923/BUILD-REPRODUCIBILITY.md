# Qwen-Image2.1 runtime build receipt

This is a source/build metadata receipt compiled from the retained
`IMAGE21-RUNTIME-20260923/evidence/runtime-receipts/` files. It makes no GPU,
model-loading, PNG, visual, readiness, transport, or memory-margin claim. The
receipt compiler performed no VM contact, build, or runtime-source edit.

## Source and image identities

| Item | Recorded identity |
| --- | --- |
| Official SGLang source commit | `0cd8be351d0825488f4b81c8931167bbab618eca` |
| Complete Git tree listing SHA256 | `a7b6342f55b62979a7d88526632a68bce2fd3461dfb7e55eabf109f5a6725522` |
| Final Dockerfile SHA256 | `d8295698cc454210c9a369d29d863c999e0fd1815a74b606f8648e6cd3b45997` |
| NVIDIA CUDA base linux/amd64 manifest | `sha256:a85c9f5af049f0ab679c1669ae6fa8393022886739af7361e85bb96878e8cdd4` |
| Observed Docker `Id` | `sha256:4029affd6e90f49e03aa0d132c077508eedbfc266cde12589584da4bbb9d6e83` |
| Observed `RepoDigests` entry | `local/qwen-image21@sha256:4029affd6e90f49e03aa0d132c077508eedbfc266cde12589584da4bbb9d6e83` |
| Built local SGLang wheel SHA256 | `2b9638e12010800f6c863fe105ce507d88df6bdd24c969877782b2f21cb4d989` |

The Docker ID and RepoDigests entry are separate fields copied from the saved
inspection; their matching hash text does not establish registry publication or
remote pullability. The image record reports Linux/amd64,23 filesystem layers,
9,035,653,882 bytes and creation at2026-09-23T02:28:02.321571757Z.

The saved tree listing's9,573 blob/path identities match the independently cached
official commit tree. Its SHA256 matches both build receipts. The current runtime
Dockerfile matches the final build-complete hash and is copied as
[Dockerfile.built](Dockerfile.built). This checks the recorded committed tree;
it does not independently hash every working-tree file at the original build time.

The build receipt says `BUILT_AFTER_DIAGNOSED_BUILD_ENVIRONMENT_REPAIR`. The initial
Dockerfile hash was `e256c4e09193617de59ab080c565bb4d99bfd0b88136681f5e35bf53ae56895f`;
the final hash above identifies this receipt's build recipe. Original start and
completion records remain unmodified. The recorded288.841909024s duration is
preserved as reported, without treating it as total elapsed time across attempts.

## Exact recorded environment

[requirements.freeze.txt](requirements.freeze.txt) lists all240 installed Python
distributions and matches the240 names/versions in pip inspect exactly. Every
distribution in the205-entry pip installation report has the same installed
version. [dpkg-versions.tsv](dpkg-versions.tsv) inventories the container OS packages.

| Component | Installed version |
| --- | --- |
| Python | `3.12.3` |
| pip | `26.2.1` |
| setuptools / setuptools-rust / setuptools-scm | `84.0.0` / `1.13.0` / `10.2.3` |
| wheel | `0.48.0` |
| SGLang | `0.0.0.dev1+g0cd8be351` |
| torch / torchvision / torchaudio | `2.13.0+cu130` / `0.28.0+cu130` / `2.11.0+cu130` |
| Triton | `3.7.1` |
| transformers / diffusers | `5.12.1` / `0.37.0` |
| sglang-kernel / flashinfer-python | `0.4.7` / `0.6.18` |
| Pillow / nvidia-ml-py | `11.3.0` / `13.610.43` |
| GCC13 / G++13 | `13.3.0-6ubuntu2~24.04.1` |
| CMake / Ninja | `3.28.3-1build7` / `1.11.1-2` |
| CUDA NVCC package | `13.0.88-1` |
| Git | `1:2.43.0-1ubuntu7.3` |

The recipe builds the exact source wheel without build isolation, disables Rust
extension builds through `SGLANG_BUILD_RUST_EXTS=none`, and installs the official
`sglang[diffusion]` dependency group. The saved
[native-help.txt](native-help.txt) is CLI/import evidence from
`sglang serve --model-type diffusion --help`; it is not an inference test.
The final Dockerfile also invokes `pip check`; this receipt does not recreate
that command or extend its coverage to runtime CUDA compatibility.

## Archive hashes and reproducibility limits

[pip-archive-hashes.json](pip-archive-hashes.json) retains every reported install
archive's package/version, filename, SHA256, source hostname and wheel/source
classification. It excludes full download URLs and metadata descriptions.
There are203 wheel archive hashes and two source-distribution hashes:
`cuda_tile-1.6.0rc5.tar.gz` and
`antlr4-python3-runtime-4.9.3.tar.gz`. These are hashes reported by pip; the receipt
compiler did not download those archives again. Source-tar hashes do not identify
the locally built wheels produced from them.

Thirty-five distributions were already installed before the reported pip stage,
including Torch, CUDA dependencies and build tools. Their exact versions are
retained, but their archive hashes are absent from the supplied report. The exact
list is in [python-dependency-inventory.json](python-dependency-inventory.json).
Docker Engine/BuildKit versions, apt archive hashes and apt repository snapshots
are also absent. This is a reproducibility inventory of the completed image,
not a complete hermetic rebuild lock or proof that rebuilding yields the same ID.

[build-reproducibility.json](build-reproducibility.json) contains the structured
identity/coverage result and SHA256/size provenance for all raw inputs, including
the bulky pip inspect/install reports and full tree listing retained in the task.
Small raw receipts were copied byte-for-byte. No checkpoint artifacts are included
in this build receipt; checkpoint hashes belong to the separate acquisition receipt.
