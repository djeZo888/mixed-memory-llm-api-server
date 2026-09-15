# F1Db Phase A — cache PASS; auth FAIL

Final status: **CACHE_PASS_AUTH_FAIL**. After the root-authorized complete staging correction, the unchanged cache helper passed and the unchanged auth helper failed. **The production auth gate remains false and was never updated.** No inference, model or lifecycle readiness follows from this report.

## Final actual helper results

| Check | Result |
| --- | --- |
| Complete source preflight inside the restricted container | PASS: all 437 archive entries (377 tracked files and 60 directories) readable; file hashes match the reviewed archive |
| Cache helper | PASS_RESOLVERS_AND_FILESYSTEM_ONLY; exit 0, 9.509 s, empty stderr |
| Auth helper | FAIL, `actual_image_fixture_failed`; exit 2, 8.597 s, empty stderr |
| Exact task-owned container cleanup | PASS: all eight recorded IDs removed, including historical attempts and inspections |
| Pre/post common storage guards | PASS; 4 GiB STOP threshold retained |

Cache executed the real installed SGLang, FlashInfer and Torch extension resolvers and bounded owned create/fsync/read/remove probes. Installed resolver source hashes matched pinned provenance, and `HOME` remained unchanged. Returned paths include `/cache/sglang`, `/cache/deep_gemm`, `/cache/flashinfer/.cache/flashinfer/0.6.12/{cached_ops,generated}` and `/cache/torch_extensions/f1c_cache_probe`. All resolved/configured writable paths were beneath private `/cache` tmpfs. The full map is in the cache receipt.

**CUDA driver JIT-cache use and model-cache behavior remain NOT_TESTED.** Successful filesystem access to `/cache/cuda` does not prove GPU JIT use.

Auth exposes only its fixed failure from `tests/lifecycle/sglang_fixture/run_pinned_image.py:1000-1007`. Its inner phase, exception class and originating file/line are suppressed. No case-specific completion receipt was emitted. The corrected failure must not be attributed to the earlier, resolved source-permission defect, and does not establish a specific launcher/backend logic defect.

No further helper retry or source patch was performed. The [diagnostic proposal](f1db-auth-diagnostic-proposal.md) identifies exact source locations for bounded phase/class/path/line diagnostics, without exception text, locals, captured logs, argv, environment or sentinel leakage. It requires source review and separate execution authorization; it has not been applied or run.

## Reviewed identity and authorization

| Item | Identity |
| --- | --- |
| Approved launch source | `c0e1a1dff0ac1647ed5207f05247ff63f72f7cc7` |
| Branch | `milestone/f1db-actual-auth-cache-proof` |
| Exact installed image | `sha256:5027e95bf6ec536856b1b52a91d1f35ff5c564ab83e8a94758a169ff09bb8df3` |
| Launcher SHA256 | `93ddd96d6a3d346b3e62b0eec08d6666c70c1ebc7b2cc727d02c191c9d50a5b2` |
| Cache helper SHA256 | `6ca8ed2ffdf98e6f4e33271204f42abcf1140ee8f8a3421b3e8d216c2f973749` |
| Auth helper SHA256 | `c08ae64da3b04abcebdf241920adb40fbfaf8a93daa075dffd64d5f86013cfc7` |
| Runtime JSON SHA256 | `54a276babcd2518125aabd8338b68beaae571d8b3e5b1270be00afec78d0decc` |
| Reviewed archive SHA256 | `8c172da15574a0c41a2476a28e580b276eee1d6f9a9130ae0c0f708477f06519` |

The supplied `../scoped-overlap-ack.md` is titled “D3 scoped overlap acknowledgement” and has SHA256 `26307699dce9184157c3bdd0ff6f960594608f8ba1c54befcd4ef25cfbd3bda2`. It matches the no-GPU/no-network/no-real-key/no-model/no-inference scope. Coordination was reread at phase boundaries. Revision2 expressly authorized a complete task-source permission correction, full readability/hash preflight and one corrected attempt per helper. That allowance was consumed. All VM operations originated from Worker1 through SSH `ai-vm`; independent review was local only.

## Isolation and inherited environment

Every container used the exact already-installed image, `--pull never`, `runc`, network `none`, read-only root/source, `--cap-drop ALL`, no-new-privileges, no Docker logging and a unique name/CID file. No GPU devices, host model/key mounts or published ports were supplied. Auth's `/models` and `/run/secrets` were empty disposable tmpfs, as required by its reviewed command. No `--init` was added: the intended auth controller remained PID1. Cache retained its reviewed 4 GiB/2 CPU/128 PID limits and private 128 MiB cache/tmp tmpfs.

Both helpers explicitly received all **12** entries read from the reviewed runtime environment map. No environment gate was bypassed. The three public inherited SGLang build metadata entries matched the reviewed values. `HOME` was never overridden on host or in Docker; independent inspection observed container `HOME=/root`. The image has no healthcheck. Its inherited NVIDIA entrypoint was replaced by the reviewed explicit `python3` entrypoint. No image pull, model/package download, compilation, runtime build or service activation occurred.

Independent read-only inspection additionally confirmed four expected package versions and 18 distinct pinned source-file hashes. This was separate from the subsequently successful cache helper; it does not pass auth.

## Historical staging failures and reviewed correction

The initial cache process could not open the helper at all: exit 2, 0.217 s. The known `Permission denied` diagnostic exactly matches its retained stderr length/hash. Correcting only the staged source root's traversal permissions then allowed cache/auth helper entry, but both returned fixed FAIL at preflight (0.247 s / 0.270 s). A separate restricted-container source read confirmed `PermissionError`, errno 13, reading the launcher through `/fixture/scripts`. Original helper tracebacks were not captured.

The worker staging harness created the `scripts` ancestor under umask `077` while extracting common guards, then skipped existing directories during the remaining extraction. `staged-permissions.json` records UID 1000/GID 1001 and mode `02700` on that ancestor. No helper source logic defect was inferred.

Under Revision2, the entire canonical task copy was checked against the reviewed tracked archive, with no symlinks or untracked inputs. Only directories/files in `/data/build/f1db-20260915/reviewed-source` received readable/traversable modes: directories `0755`, files `0644`, tracked executable files `0755`. The outer task directory remained private, mode `02700`. All source bytes remained exact. The same restricted container read/hash-checked all 437 entries before the single corrected helper attempts. Historical failures remain separate receipts and cannot be confused with final cache PASS/auth FAIL.

Two pre-container setup corrections are retained: `/dev/stdout` was an unsuitable root-guard report destination because report text contaminated its captured conclusion; the unchanged guard passed with a task-private report file. An image projection initially referenced absent `Config.User`; optional metadata was read with Docker template `index` before plan publication. An inspection-plan draft with an extra `python3` was corrected before execution and retained as `../evidence/inspection-plan-draft-not-executed.json`.

## Storage, cleanup and evidence

Strict checks verified `/data` UUID `8daf56f1-5649-4163-9d87-919c2d271875`, separate from root, and at least 4 GiB free before staging. The installed mount guard ran before bootstrap staging of unchanged reviewed common guards; the reviewed root guard passed before the rest of the source was staged. Common guards ran before/after fixtures and inspections. Final root availability was **5,227,986,944 bytes**, above the strict **4,294,967,296-byte** stop threshold. Warnings remain for root free space below 6 GiB and the small historical bootstrap/pre-mount backup paths. No cleanup was performed on those or unrelated resources.

All eight exact task-owned CIDs were absent at final inspection; their container PID namespaces no longer exist. This is cleanup evidence, not successful native SIGINT-child proof. No unrelated container was listed/inspected and no prune ran. No protected release, instance, real key, active selection, boot policy, service, lifecycle state, Docker/driver daemon or current GLM container was changed or accessed. No real key was read or created and no production auth gate was updated.

Authoritative structured evidence is outside the checkout at `/data/build/f1db-20260915/evidence`; the Worker1 copy is `../evidence/vm/evidence`. Corrected results are under `revision2/`. See the [sanitized summary](f1db-phase-a-summary.json) and [complete evidence checksum inventory](f1db-evidence-sha256.json).

| Key receipt | SHA256 |
| --- | --- |
| Initial scoped run plan before any container | `4d0630ead68c1ca786d025da9c99b8e32ed0fc509f097e439ed6b36c44729103` |
| Revision2 scoped helper plan | `8481348bb911a81db33517987b49e45d4a608c3ca3a5c693ffd70e71a3806931` |
| Revision2 full-source preflight plan | `016e818a84004b3eff37fb2981c250c20c2a2bafb5ed819ab2bf8d31f9148f4b` |
| Revision2 cache stdout | `179d254f01198052fe3832046e921efc79de4c9f827b4c5dcb03776f977d72d1` |
| Revision2 auth stdout | `7d0072fbcf9652fa6f5814cb62521e663405180055e11c783bf3eb59266f90cb` |

## Remaining gates and handoff

| Required proof | Final status |
| --- | --- |
| Installed cache source bytes, native resolvers, owned private filesystem probes | PASS_RESOLVERS_AND_FILESYSTEM_ONLY |
| CUDA driver JIT-cache use/model-cache behavior | NOT_TESTED |
| Native ASGI chain, ordinary routes including `/model_info`, warmup, sentinel nonleak, WS denial, rejected modes/negative key files | NOT_PROVEN; corrected auth returned only aggregate FAIL |
| Actual SIGINT/Uvicorn/launcher child cleanup | NOT_PROVEN |
| Wrong-owner case | NOT_PROVEN; no capability-skip result emitted; capabilities not expanded |
| Protected host-key ownership | NOT_TESTED; separate later gate |
| Full native CUDA/model/lifespan, real SIGTERM/SIGQUIT, inference and agent acceptance | NOT_TESTED |

Root reviews the diagnostic proposal before further auth work. Preserve the successful cache receipt and immutable source/image identities. Fresh Qwen live/Phase B work still waits for auth proof and D3/client ownership release.

This report-only change was checked through source/hash preservation, complete JSON/receipt/checksum validation, exact-CID absence, common guards, independent evidence review, `git diff --check`, and a grep-based staged secret scan. Production/helper/test/config source is unchanged; regression tests were not rerun for documentation-only changes. Incremental bundle verification and requested author/committer identity are recorded in `../handoff.md`.
