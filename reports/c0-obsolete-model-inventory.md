# C0 — obsolete model inventory and conditional cleanup plan

**Inventory complete within the stated bounds. C1 remains STOP pending replacement acceptance, root review and immediate reference revalidation. No deletion or other VM mutation occurred.**

The three old model trees occupy **506,380,369,920 allocated bytes (471.603 GiB)**. No substantial duplicate old-model blobs were found in the fully inspected `/data/hf-cache`: it occupies only **36,880,384 bytes (35.172 MiB)** and contains no weight files, snapshots or blob directories. No additional cache deletion target is proven exclusive; preserve shared caches.

## Provenance and scope

- Source host: SSH alias `ai-vm`, observed hostname `llmserver`; collector: Mac-Worker2.
- UTC observation window: **2026-09-15 00:14:41–00:26:24**. Filesystem model accounting: **00:17:17**; Docker/services: **00:18:46–47**; cache and protected-state follow-up: **00:26:24**. These are separate moving snapshots, not an atomic transaction.
- Source base: `75a6bf915f30a1582348071eb733d05c33e10eb7`; branch: `milestone/c0-obsolete-model-inventory`.
- Session: `01a0a269-ef98-7920-a75c-3266fa861151`.
- [Structured inventory](c0-obsolete-model-inventory.json) contains exact identities, byte counts, safe reference metadata and observation times.
- Read [AGENTS](../AGENTS.md), [current coordination](../docs/orchestration/2026-09-15-status.md), [R1](../docs/operations/2026-09-15-resumption-audit.md), [R2](r2-model-refresh.md), [F1A continuation](f1a-continuation.md), [F1A runtime contract](f1a-sglang-contract.md), and [F1S handoff](../docs/lifecycle/f1s-handoff.md).

Current user scope supersedes historical indefinite weight-retention advice: retain GLM plus only 2–3 accepted fast/lower-memory models, currently Qwen3.8-27B and CoderNext roles. No DeepSeek installation. C0 does not rank or accept replacements. Worker1 exclusively owns live acquisition, deployment and eventual C1.

Inspection used existing SSH trust, bounded filesystem metadata, selected small non-auth model/config metadata, and filtered Docker/systemd metadata. The final protected JSON inspection used authorized read-only sudo and emitted only safe IDs, paths and evidence flags. No credential/auth files, key values, headers, environment or process argument values were read/output. No weight contents or weight hashes, raw unit/config dumps, service operations, inference, tests, builds, installation or guard-report writes were performed.

## 1. Observed filesystem identities and model bytes

Both model parents were confirmed to exist on distinct ext4 `rw,relatime` mounts before walking their contents. Every listed old model root is an ordinary directory whose **realpath equals the exact displayed path**. No nested device, traversal error, symlink, or regular file with link count greater than one occurred in the three old trees or the fully inspected HF cache.

| Mount | Source / device | UUID | Kernel mount ID / parent |
| --- | --- | --- | --- |
| `/data` | `/dev/sdb1`; `8:17`; `st_dev=2065` | `8daf56f1-5649-4163-9d87-919c2d271875` | `48 / 31` |
| `/data/models-large` | `/dev/sdc1`; `8:33`; `st_dev=2081` | `a6d4ab58-84e1-4e48-9a67-13ad1c6f6e0a` | `65 / 48` |

Mount IDs, device numbers and inode identities describe this boot/snapshot; C1 must resolve them again, rather than treating numbers as durable authorization. UUID, canonical mountpoint and filesystem identity must match the reviewed deployment.

| Exact old path = realpath, all on mount 48 | Root inode | Allocated bytes | Apparent file bytes | Payload artifacts / weight shards | Total regular files / directories |
| --- | ---: | ---: | ---: | ---: | ---: |
| `/data/models/minimax-m3-mxfp8` | 12320800 | 443,776,548,864 | 443,776,023,939 | 52 / 31 | 159 / 7 |
| `/data/models/qwen3-30b-a3b-instruct-2507` | 12320782 | 61,084,520,448 | 61,084,266,282 | 27 / 16 | 56 / 4 |
| `/data/models/qwen3-0.6b-smoke` | 12320770 | 1,519,300,608 | 1,519,210,490 | 10 / 1 | 22 / 4 |
| **Unique union of these three trees** | — | **506,380,369,920** | **506,379,500,711** | **89 / 48** | **237 / 15** |

Allocated bytes sum `st_blocks × 512`, once per `(device,inode)`, including directory blocks. Apparent bytes sum regular file lengths; no symlinks were present. Both columns matched independent GNU `du -sx -B1` / `du -sx --apparent-size -B1` observations. Payload artifact counts exclude `.cache`; total regular files include local download metadata and lock files. Local `.cache` is already included in each model tree and must never be added again. The parent `/data/models` directory itself is excluded from reclaim.

Weight sizes alone are MiniMax **443,749,077,256**, Qwen30B **61,066,575,656**, smoke **1,503,300,328** bytes. Index metadata references 31/31 and 16/16 present shard names respectively. Presence/size/index checks are not integrity verification.

### Identity from local metadata, not assumed from research

| Model identity | Observed architecture | Revision recorded in local download metadata and HF `refs/main` |
| --- | --- | --- |
| MiniMaxAI/MiniMax-M3-MXFP8 | `MiniMaxM3SparseForConditionalGeneration` | `ca165902e868fd015fab5acaff776643be00dc6e` — all 52 artifact metadata records, including 31 weights |
| Qwen/Qwen3-30B-A3B-Instruct-2507 | `Qwen3MoeForCausalLM` | `0d7cf23991f47feeb3a57ecb4c9cee8ea4a17bfe` — all 27 records, including 16 weights |
| Qwen/Qwen3-0.6B | `Qwen3ForCausalLM` | `c1899de289a04d12100db370d81485cdf75e47ca` — all 10 records, including one weight |

MiniMax's local recorded revision differs from R2's later research revision `c5454eb03678d8710e54a4e0fc681b9f3b4a3dba`. C0 makes no claim that stored bytes match either revision cryptographically; it read only revision lines from small download metadata and safe model/index fields.

## 2. Cache accounting and duplicate-download assessment

The complete bounded HF walk covered **65 directories / 181 regular files**, with no errors, symlinks, hardlinked regular files, weight-extension files or individual file at least 128 MiB. Therefore hundreds of GB of duplicate old weights are **not present in this inspected cache**. This conclusion is bounded to the named roots; no global filesystem cleanliness claim is made.

| Exact cache root/subtree | Allocated bytes | Apparent bytes | Classification / disposition |
| --- | ---: | ---: | --- |
| `/data/hf-cache` | **36,880,384** | **36,180,588** | Shared by all three legacy container mounts; preserve whole root |
| `/data/hf-cache/home` | 20,688,896 | 20,119,920 | Runtime/compiler caches; exclusive obsolete ownership unproven; preserve |
| `/data/hf-cache/home/.cache` | 18,378,752 | 18,142,460 | Included in `home`; preserve |
| `/data/hf-cache/home/.triton` | 2,277,376 | 1,977,460 | Included in `home`; preserve |
| `/data/hf-cache/xet` | 16,064,512 | 16,044,807 | Mostly the three-log subtree: 16,052,224 allocated bytes including its directory; CAS subtree is empty directory metadata, 8,192 bytes; preserve |
| `/data/hf-cache/modules` | 57,344 | 10,268 | Cached source/modules, not weight blobs; preserve |
| `/data/hf-cache/hub` | 40,960 | 120 | Three model-specific `refs/main` files; no `snapshots` or `blobs`; preserve |
| `/data/build/pip-cache` | 4,096 | 0 | Empty directory; shared build root, outside obsolete downloads; preserve |
| `/data/build/f1a-qwen-20260915/runtime/cache` | **at least 1,568,768** | **at least 1,470,713** | Retained new-Qwen runtime proof cache; protected `cuda` descendant unreadable; preserve and mark total incomplete |
| `/data/models-large/runtime-cache` | absent at 00:26:24 | — | Reserved retained-runtime location; preserve if created by F1D/later deployment |

**Do not add parent and child rows.** The shared HF root is only 35.172 MiB in total. Its remaining small subdirectories and exact counts are in the JSON. Bounded direct-child discovery in known MiniMax, D1, D1b, F1A and F1D task roots found no additional directly named model/cache/snapshot/blob roots; this is not a recursive audit of all task data. No Docker/containerd layer or build/log cleanup is proposed.

### Separate model-specific HF namespaces

Each following realpath is a plain directory on `/data`, device 2065 / mount 48. Each contains **two directories and one 40-byte regular `refs/main` file**, allocated **12,288 bytes**, apparent **40 bytes**, no symlinks/hardlinks, snapshots or blobs:

| Exact namespace | Root inode | Current disposition |
| --- | ---: | --- |
| `/data/hf-cache/hub/models--MiniMaxAI--MiniMax-M3-MXFP8` | 16777426 | Retain; possible metadata-only C1 follow-up after references are cleared |
| `/data/hf-cache/hub/models--Qwen--Qwen3-30B-A3B-Instruct-2507` | 16777233 | Retain; possible metadata-only C1 follow-up after references are cleared |
| `/data/hf-cache/hub/models--Qwen--Qwen3-0.6B` | 16777225 | Retain; possible metadata-only C1 follow-up after references are cleared |

Their combined **36,864 allocated bytes** are already included in `/data/hf-cache`. Naming and tiny contents indicate old-model metadata, but do not establish exclusive operational ownership: the cache has broad container references and incomplete process/release visibility. **No cache target is currently proven eligible; additional expected cache reclaim is zero.** Root may separately review these exact namespaces in C1 only after Worker1 proves no retained model/runtime/job reference. Do not delete the shared parent, compiler cache, Xet tree, or presumed shared blobs.

## 3. Observed reference graph and recorded state

| Source / identity | Outgoing reference | Observed state / consequence |
| --- | --- | --- |
| `minimax-m3-mxfp8-poc`, container `634daeb70a3ae9aa7403ec8d2256984de9cfe8b5521b839de16a1707164f7522` | MiniMax image below; broad `/data/models` read-only, `/data/hf-cache` and `/data/logs` read-write | Exited, PID 0, restart `no`; preserve container by default |
| `sglang-qwen3-30b-a3b-instruct-2507`, container `321ee2110e2e0130739ca51fe192b23d746ecefca76e746c9e2df3fd8a799153` | Retained SGLang image; same three broad mounts | Exited, PID 0, restart `no`; preserve container by default |
| `sglang-smoke-qwen3-0.6b`, container `6cfa91273417ad7f5ae23a471aaf7b2f5be47bfab74550df93b71587fb3fb71f` | Retained SGLang image; same three broad mounts | Exited, PID 0, restart `no`; preserve container by default |
| `/data/services/llm-manager/compose/minimax-m3-poc.compose.yml` | Exact MiniMax model path | Current stored configuration reference |
| `/data/services/llm-manager/compose/sglang-qwen3-30b.compose.yml` | Exact Qwen30B model path | Current stored configuration reference |
| `/data/services/llm-manager/compose/sglang-smoke.compose.yml` | Exact smoke model path | Current stored configuration reference |
| `/data/services/llm-manager/active/active.json` | Qwen30B profile, model path and container; runtime `sglang`; saved `status=active` | **Recorded selection only; not proof of a running model.** Contradicts the exited-container observation. Worker1/root reconcile after replacement acceptance |
| `d1-glm53-acquire-20260915-d1b-p4.service` | Workdir `/data/build/d1-glm53-20260915`; known GLM acquisition destination on `/data/models-large` | Active/running, PID 49253; preserve acquisition and its inputs/partials |
| `f1a-qwen-fast-acquire-20260915.service` | Initial Qwen acquisition unit | Not found/inactive/dead at 00:18:47; absence is not live acceptance evidence |
| `m6b-post-reboot-verify.service` | Historical checkout workdir | Disabled, active/exited, PID 0; differs from R1 enabled snapshot. C0 made no change |
| `d1-llama-build-20260915.service` | GLM build workdir | Failed/failed, PID 0; historical unit status, not evidence that the stored image is unusable |

All three legacy containers carry Compose project `compose`, with the exact service/config paths captured in JSON. Their broad parent mounts create shared references; a stopped container alone is not exclusive ownership evidence. Do not use a project-wide Compose action to clear them.

At 00:26:24, protected Qwen completion metadata at `/data/services/llm-manager/acquisition/qwen3-coder-next-fp8.complete.json` records `complete=true`, **48 artifacts / 80,407,722,953 bytes**, revision `da6e2ed27304dd39abadd9c82ef50e8de67bdd4c`. This is an operator artifact attestation, not a C0 checksum, inference or agent-acceptance result. The canonical `deployment-instance.json`, legacy `state/active.json`, and `/run/llmctl/recovery.json` were absent at that same sample. F1D is underway; another active release/location or later deployment state must be reconciled in C1.

The historical VM checkout still reported `e4907b96a555b9a7a1580f4dc932da51b5e2f3a9` on `milestone/m6b-nvidia-container-toolkit-install`. The newer release directory `/data/services/releases/e46c788534d5b71e988c2cdf188f37f6214f7514-f1d-20260915` existed but its contents were not inspected. Current installed catalog/selection coverage is therefore incomplete. Local source `configs/models/catalog.yaml` and old YAML profiles describe supported/historical profiles, not proof of installed weights; these docs/fixtures may remain. The future installed catalog must mark removed models absent, not installed/ready.

A bounded unprivileged `/proc` metadata check considered 1,123 PIDs and found no visible matching old/new model or HF-cache references. **This cannot clear process ownership:** only 5 FD directories and 4 cwd links were readable; 1,118/1,119 were inaccessible or raced, and 30 maps reads failed. No argv/environment was inspected. Worker1 must establish complete required process/job visibility in C1.

## 4. Preservation set and image inventory

**Mandatory preservation:** all `/data/models-large` contents, including GLM/Qwen finals, partials and locks; Qwen3.8-27B artifacts wherever Worker1 subsequently stages them; retained runtime caches, all active acquisition data, service/release/adapter/evidence files, shared HF caches, Docker/containerd data, credentials and historical dirty checkouts. No third fast-model download is selected here.

At 00:17:17, CoderNext root inode **119275521**, device 2081 / mount 65 contained **48 artifacts plus one lock**, 40 weights, no partials; allocated **80,408,006,656**, apparent **80,407,722,953** bytes. GLM root inode **169607169**, same device/mount, contained **9 final GGUF shards, 2 partials and one lock**, allocated **459,265,257,472**, apparent **459,264,979,205** bytes. GLM was actively changing; these are not final totals. `/data/models/glm-5.3-ud-q4-k-xl`, the old R2 suggested destination, was absent. No Qwen3.8 directory was observed among the immediate children of the two model roots at 00:20:48; this does not exclude later acquisition or other approved roots.

| Exact image tag | Exact local content ID | Disposition |
| --- | --- | --- |
| `lmsysorg/sglang:v0.5.14-cu130` | `sha256:5027e95bf6ec536856b1b52a91d1f35ff5c564ab83e8a94758a169ff09bb8df3` | **Mandatory retain: new CoderNext requires it**, regardless of old-container retirement |
| `local/llama-cpp:v0.4.1-b29c606-cu132-sm120-d1` | `sha256:6866856c573d69d504f82265321b182f631a7b3912a1ed1b4efbf893729d4e62` | **Mandatory retain: pinned GLM runtime** |
| `local/minimax-m3-ktransformers:0.6.3-post1-r1` | `sha256:362917ee2a4188bdb827c5b97d0f9a8a5c5dd1663b2ea43ad1ef6daa55a0a768` | Referenced by MiniMax container; retain, outside model-download cleanup scope |
| `local/minimax-m3-ktransformers:0.6.3-post1` | `sha256:f2378ed66d98d97a20d546d096c5926bda923912ae55ba3d019aac62c8bfd65d` | No current container reference in snapshot; retain, layer/build sharing unproven |
| `lmsysorg/sglang:v0.5.14-cu130-runtime` | `sha256:9e436f44523e9f53519c6175fefd1e0d373322bf54b8154bb331a2f5e4840ad2` | Retain; historical rejected runtime is not permission to remove an image |
| `nvidia/cuda:13.2.1-base-ubuntu24.04` | `sha256:7be56e69d8ae7c3648b8fca009fa35980ecd9c6eefaafbff3ee8c224e0043eb5` | Retain runtime/build dependency |
| `hello-world:latest` | `sha256:96498ffd522e70807ab6384a5c0485a79b9c7c08ca79ba08623edcad1054e62d` | Retain; outside obsolete model downloads |

Image inspect size metadata is included in JSON only as non-reclaim size information. CLI image-list and inspect size representations differed; neither establishes exclusive allocated storage or layer reclaim. Do not sum image sizes or remove shared layers/blobs. **All images and containers default retain; any separate retirement needs explicit root/user scope. Never Docker system prune, volume prune, global HF-cache prune, or recursive parent-data deletion.**

## 5. C1 plan — Worker1 only, future gates

This is a reviewable conditional allowlist, **not a deletion authorization or executable cleanup script**. The only substantial model candidates are the three exact paths in section 1. Cache candidates are not proven eligible and contribute zero to the plan's reclaim budget. Unresolved recorded/shared references and acceptance gaps mean **STOP for C1 at this snapshot**.

1. **Root reviews the exact candidates and replacement evidence.** Require completed artifact integrity evidence, actual pinned-runtime launch, live authenticated API/models/chat/SSE/tool continuation, measured resources/latency and real worker-side agent edit/test acceptance for GLM and the selected fast replacement roster. Acquisition status, source tests, saved active state and simple chat do not substitute. Use the bounded acceptance contracts in R2 and F1S; record actual passes and limits for each retained role. Keep only one active model/backend.
2. **Worker1 reconciles lifecycle references after acceptance.** Resolve recorded Qwen30B selection, actual installed catalog, instance/recovery state, registered release paths, services/jobs, retained-model dependencies, and the three Compose/container references. Historical docs/fixtures may remain. Active/job/shared references halt deletion. If resolving dormant broad container mounts requires container/config retirement outside approved download cleanup, return that concrete change for separate root/user scope; C0 does not authorize it. Do not silently restart, remove or alter containers to make the check pass.
3. **Immediately before each target, establish an exclusive maintenance interval.** Worker1 must prevent concurrent acquisition/lifecycle/config changes using the reviewed operational ownership/locking mechanism; do not improvise a competing lock. Run the required mount/root guards in C1 with their reports/temp under verified `/data`, before and after cleanup; halt on failure. C0 did not run these report-writing guards.
4. **Produce C1's fresh dry-run report before deletion.** Re-resolve the exact literal target and all parents; require ordinary canonical directories, expected UUID/mount/device, no nested mounts/devices, no symlink escape, no unexpected contents and no unresolved hardlink sharing. Compare fresh inventory with this report; drift requires review, not a guessed match. Inspect every current container's selected safe identity/mount/restart/state fields, relevant system and user service/job metadata, active/desired/recovery/catalog state, and necessary process FD/mmap references. Unknown required visibility or a concurrent owner means halt. Recheck immediately before applying each approved target, not only at the start of a long batch.
5. **Preserve small review evidence and remove only the approved target.** Keep model identity/manifests/config evidence and source profiles as needed without copying weights. Any actual deletion helper must support `--help` and `--dry-run`, fail closed, stay on the approved filesystem, refuse ambiguous/symlink/shared states and select one exact approved directory; no glob or parent/root cleanup. Never recursive all-data deletion/chown or new-model/required-runtime removal. An optional model-specific cache namespace must independently pass the same ownership/reference gates and receive exact-path approval; broad cache names are insufficient.
6. **Record actual results and reconcile the catalog.** Confirm the approved directory is absent, retained files/mounts/runtime images remain, catalog installation state is truthful, selected state no longer names removed weights, and retained API/agent acceptance remains valid under Worker1's approved verification scope. Measure fresh allocated bytes and filesystem available space; report actual reclaimed bytes, copies retained for evidence, warnings and pass/fail. Keep C1 evidence and final action recommendation under `reports/`.

### Expected reclaim and caveats

The measured, disjoint candidate-tree allocation is **506,380,369,920 bytes**. No repeated inode was found across these trees, and every regular file had link count one, so the total is not a guessed sum of model marketing sizes or HF/cache/image duplicates. The old-tree totals match R1, but were measured again here.

This is **conditional expected model-tree reclaim**, not already freed space or a guarantee of the future `df` delta. Open/mapped deleted files can defer reclaim; filesystem allocation, concurrent Worker1 writes, snapshots/storage-layer sharing and separately retained metadata can affect observed free space. Subtract the measured allocation of any preserved copies. Re-measure in C1. Do not add the same tree's `.cache`, shared-parent totals, image sizes, or the 36,864 metadata-only namespace bytes without separate verified deletion. External symlinks and inaccessible owners remain revalidation gaps; no whole-root search was attempted.

## 6. Checks, limitations and delivery

| Check | C0 result |
| --- | --- |
| Source base/branch and required coordination review | PASS |
| Existing SSH trust; mount/UUID/device confirmation | PASS |
| Three exact old trees: bounded stat accounting, file relationships, config/index metadata, independent `du` cross-check | PASS for metadata inventory; weight integrity NOT_TESTED |
| Shared HF cache / relevant model namespaces | PASS complete accounting; no substantial duplicate weight blobs found in this root |
| New-Qwen proof cache | PARTIAL: protected CUDA descendant unreadable; preserve |
| Docker/systemd/recorded-state references | PASS for selected observed metadata; not live readiness or complete ownership clearance |
| Protected Qwen completion metadata | Read-only safe fields recorded; no independent hash/API/agent validation |
| Global/process/release ownership proof | INCOMPLETE by scope/permissions; mandatory C1 revalidation |
| Tests, API/inference, builds, installs, lifecycle operations, guard reports, deletion | **NOT RUN** |
| Publication checks | Changed-file credential-pattern scan, whitespace/diff review, attribution, clean-tree and bundle/push checks are recorded in the sibling task delivery handoff; they are not model or project tests |

Reproduction of the byte inventory uses exact-path `findmnt -J -o ID,PARENT,TARGET,SOURCE,FSTYPE,UUID,MAJ:MIN`, bounded `lstat`/`scandir` without following links, and `du -sx -B1` / `du -sx --apparent-size -B1` on the three literal candidates. The metadata collector used limits of 10,000 entries/root, depth 16, and 45 seconds overall; the cache follow-up used the same entry/depth bounds and 30 seconds. JSON records methods, timestamps, selected results and errors. Process metadata used 4,096 PID/FD bounds, 2 MiB maps bounds and a 25-second deadline. No model payload was opened.

**Next action:** root reviews this inventory; Worker1 finishes GLM/fast replacement acceptance, resolves recorded/shared references and performs a fresh C1 dry-run. Live state may already have changed while F1D proceeds. C0's snapshot must never serve as the final pre-deletion clearance.
