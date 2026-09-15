# Q38A bounded Qwen3.8 acquisition

**PASS: all81 payload hashes, root rehash/seal, pinned image acquisition and reviewed image identity.**
**HANDOFF REQUIRED: protected lifecycle completion receipt.**
**NOT_TESTED: Q38B actual helper/authentication, model load, inference, continuation and occupied context.**

Work ran through worker SSH `ai-vm` on2026-09-15. Final roster remains GLM5.3 + Qwen3.8-27B FP8. No installer/runtime source edits, container launch/import, GPU allocation, key operation, model selection/start, installed-service restart, driver/daemon/storage configuration change or deletion occurred. Existing selected/deferred weights and partials were preserved.

## Model result

| Item | Verified result |
| --- | --- |
| Model/destination | `qwen38-27b-fp8`; `/data/models-large/qwen38-27b-fp8` |
| Repository/revision | `Qwen/Qwen3.8-27B-FP8` / `017b9c7af6b5689d5dd426a76e0bc077eb5ca20a` |
| Immutable manifest SHA256 | `726012378a40f648a104230d3f5ed5d6bc505cbd09b32918fc29aa81c0f075f2` |
| Actual artifacts/bytes | **81/81;30,890,049,597 bytes**;66 weights/30,866,866,928 weight bytes |
| Download |02:19:25–02:24:51UTC;3 bounded streams; final unit `q38a-weights-20260915-r2.service`, PID179777, inactive/dead/exit0 |
| Root rehash/seal | Completed02:27:48UTC; every payload SHA256 recomputed as root; ordinary Git payload SHA1 also checked |
| File protection | All81 root:root0444, single-link; model root:root0555; download user write denial PASS |

[Exact per-file hashes and before/after stat evidence](q38a-sealed-evidence.json) is a byte-identical copy of protected VM evidence:
`/data/models-large/.q38a-evidence-20260915/sealed-evidence.json`.
SHA256 **`a9b1ee9c80ca7030b79387b64f63d494159d0db7966f6510737e20c568584cfe`**.
The evidence directory is root0700 and evidence files root0600. It binds the original expected manifest to each actual hash, device/inode/size/mtime/ctime/owner/mode/link count. Post-seal comparison of every saved stat passed. Root `/proc` checks before and after sealing found zero writable payload descriptors, zero shared writable payload mappings and zero unreadable entries.

All rows remain. `.gitattributes` is1,570 bytes; `safetensors-md5sum.txt` is a real zero-byte file with computed SHA256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`.67 LFS pointer Git identities remain separate from payload hashes. No pointer SHA was compared with payload Git SHA. No partials or extra files remain inside the model tree.

The original acquisition completion is also copied into that protected evidence directory as `acquisition-complete.json`, SHA256 `970b026bbb8a4d500f1aee146c3ffaf51f64ca7d0eb3c3a24237e6a51c35f8c5`.

## Image result and exact ID domains

Image reference: `lmsysorg/sglang@sha256:37bbbd3444732a464bbc68dee4fb0164e0ce9e18e2f027f3fc967f1152d3c262` (`v0.5.19-cu130`, linux/amd64).

| Domain | Actual verified identity |
| --- | --- |
| Config digest / outer `image_id` | `sha256:e6238090791a938ab86dd21a9a6394192dad15237e815df557cf83524d54b813` |
| RepoDigest / platform manifest | `sha256:37bbbd3444732a464bbc68dee4fb0164e0ce9e18e2f027f3fc967f1152d3c262` |
| Docker observed `.Id` | Platform manifest above; `image_id_domain=oci_platform_manifest` |
| Docker Descriptor | Exact platform digest; `application/vnd.oci.image.manifest.v1+json`;13,686 bytes |
| Stored config payload |65,818 bytes; actual computed SHA256 matches config digest above |
| Public source/defaults | SGLang `0bcd822377da7b5718e674eaf9c870d349424dd1`; expected source labels, NVIDIA entrypoint, null command and workdir all matched |

The pull completed with exit0 under `q38a-image-20260915-r2.service`, parent PID176326 / Docker CLI PID176777. Public manifest lists70 layers/15,098,528,761 compressed layer bytes. Docker reports size15,098,608,265 bytes; this is its image-store size field, not measured network traffic. Docker and containerd data roots were verified on `/data`; no second pull was needed.

The governing [image identity evidence](q38a-image-evidence.json) comes from **exact reviewed Q38B checkpoint `3a470d2b8c90398be0bffe78bccd13fe1c3a0f2e`**, using its pure `verify_image`, `verify_registry_bytes` and `validate_evidence` functions in an isolated protected copy. Module SHA256 `f2059445f3a06b15e710bc7d65866bc8d821ca3a78ef900f3d94ce4866accc2f`. The nested `docker_inspect` block preserves the actual manifest-domain ID; outer `image_id` stays the config digest. Full public image environment equality was checked in memory; no environment values were emitted. Stored manifest/config bytes independently matched both hashes and the exact descriptor relationship.

Image evidence SHA256: **`1d95386094ffa6ca875a22b7232698b67cb2318d547e40c6c746e485ace3ef89`**. Protected copy: `/data/models-large/.q38a-evidence-20260915/image-reviewed-q38b.json`. This is acquisition identity evidence, not a native runtime/auth receipt.

## Storage and unchanged state

Both exact actual ext4 mounts passed: `/data` UUID `8daf56f1-5649-4163-9d87-919c2d271875`; `/data/models-large` UUID `a6d4ab58-84e1-4e48-9a67-13ad1c6f6e0a`. No symlink containment or foreign destination was accepted. Task locks, anchored writes, exact response range/length/encoding checks, atomic state and repeated mount/root capacity checks protected acquisition.

| Free bytes | Before | After |
| --- | ---: | ---: |
| Root |5,227,765,760 |5,219,045,376 |
| `/data` |1,394,084,306,944 |1,341,879,795,712 |
| `/data/models-large` |2,621,781,004,288 |2,590,890,348,544 |

Common require-data/root-disk guards passed before and after. Exact root minimum4GiB stayed satisfied. Warnings: root below6GiB and two existing small historical root paths. No STOP remained.

Protected deployment-instance and active-state JSON hashes **and stats** were identical before/after. GLM32K container `bb77b764cb9677f3c04c1e60359d287a15abb304ba289f38703e58b5a6fc0d55` remained running with the same image/start timestamp and restart count0. No inference request was issued.

## Source verification and bounded corrections

[Task tool documentation](../scripts/q38a/README.md) records exact paths, commands and boundaries. New source is confined to `scripts/q38a/`; reviewed D1 common guards are reused unchanged. **62 fixtures PASS on Mac and ai-vm**:26 acquisition,13 image,23 seal. VM fixture commands use `TMPDIR=/data/build/q38a-20260915/tmp`. CLI help, dry-run readiness, real stored-image contract, real seal/write-denial and `git diff --check` passed.

The first image attempt stopped before pull on inherited-setgid directory semantics; its check was corrected to retain root-only protection while allowing0700/2700. A transient initial metadata request failed before any payload; bounded retries were added. The successful image pull initially hit a config-only ID check; read-only reconciliation and the supplied reviewed Q38B validator establish the correct manifest/config relationship. Linux fixture modes and timestamp assumptions were corrected; production seal protections were retained.

Initial small VM fixtures did not explicitly set TMPDIR and removed their temporary files on exit. All subsequent/final fixture runs used the task data path. No model/image payload was written to root. This scope deviation is recorded rather than claiming every initial temporary byte was under `/data`.

## Receipt handoff and next action

Live `/etc/local-ai-server/storage.json` is absent, so the canonical registered lifecycle binding cannot safely be loaded. **No** `/data/services/llm-manager/acquisition/qwen38-27b-fp8.complete.json` was published. No canonical registry or protected instance was invented/installed/edited.

The reviewed live-deploy owner must validate the protected seal and expected manifest, then publish the exact Q38S mapping under its canonical lifecycle lease and anchored writer. Preserve all81 rows and metadata-bound integrity evidence; keep richer proof separate from the strict lifecycle receipt. Model selection/start and Q38B native/auth/model gates remain separate.

Task source: `/data/services/q38a-20260915/repo`; isolated reviewed OCI module: `/data/services/q38a-20260915/q38b-reviewed`. Durable acquisition/image status and guard reports: `/data/build/q38a-20260915`. A local grep-based secret scan over all12 new source/report files found no matches; remote URLs were checked without printing credentials. Taskroot plan/job-status/handoff and incremental `Q38A.bundle` carry publication details. Branch `milestone/q38a-acquisition`; correct CodexAIagent attribution; no push.
