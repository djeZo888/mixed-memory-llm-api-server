# F1D — Qwen live deployment and API acceptance

## Outcome

**BLOCKED before key provisioning or model start.** The unchanged reviewed F1S
fixture fails in the exact installed SGLang image because its environment
validator rejects that image's inherited build metadata. No canonical API key
was created or read, no deployment instance was created, and no API-ready or
agent-ready claim is made. `auth_gate_passed` remains false.

Independent protected release preparation, obsolete boot-writer retirement and
Qwen integrity sealing passed. The original dirty checkout, old models, three stopped inference
containers and GLM acquisition were preserved. No source correction, driver or
daemon upgrade, additional model download, public bind or reboot was performed.

Protected-state verification was collected at `2026-09-15T00:18:21.064318+00:00`;
the final guard/preservation observation at `00:21:19Z` passed with no inference
running and old dirty-report hashes unchanged. The unchanged legacy record
still claims Qwen30B is active. At `00:21:55.600375Z`, GLM acquisition completion
was observed independently of F1D changes; this is downloader-status evidence,
not an F1D GLM integrity attestation. See [handoff observation](f1d-evidence/handoff-observation.txt)
and [GLM status observation](f1d-evidence/glm-final-observation.json).

## Identities and evidence roots

| Item | Exact identity / location |
| --- | --- |
| Reviewed integration | `e46c788534d5b71e988c2cdf188f37f6214f7514` |
| Reviewed F1S source | `4c56b4668efcfc89494d6c789818dea331305eb3`; supplied through the integration above |
| New protected release | `/data/services/releases/e46c788534d5b71e988c2cdf188f37f6214f7514-f1d-20260915` |
| Preserved old checkout | `/data/services/mixed-memory-llm-api-server` |
| VM task root | `/data/build/f1d-qwen-20260915` |
| Reviewed gate checkout | `/data/build/f1d-qwen-20260915/reviewed-source` |
| VM evidence | `/data/build/f1d-qwen-20260915/evidence` |
| Installed image tag | `lmsysorg/sglang:v0.5.14-cu130` |
| Actual pinned image ID | `sha256:5027e95bf6ec536856b1b52a91d1f35ff5c564ab83e8a94758a169ff09bb8df3` |
| Protected adapter | `/data/services/llm-manager/adapters/sglang_file_auth.py` |
| Adapter SHA256 | `1bf781b83d1a6bf25b63b948550cf2926e16247f48d6f977188954e9a10d212a` |
| Actual-image fixture SHA256 | `9f26ca8cd4f9a5edb3486f669edb023d9b046fd2a3139c39c2589b6cc78471c2` |
| Supplied integration bundle SHA256 | `65b13bd77af17fb5a64d867c9a8def54d3b6673ef75bfce79c1b44f74c9d0d21` |
| Intended key path | `/data/services/secrets/llm-api-key`; absent, not provisioned or accessed |
| Intended deployment instance | `/data/services/llm-manager/deployment-instance.json`; absent, not created |
| Intended API | `http://127.0.0.1:30003/v1`; NOT_READY / no Qwen listener started |

Both required filesystems were checked as actual mounts before changes:

| Mount | Required UUID |
| --- | --- |
| `/data` | `8daf56f1-5649-4163-9d87-919c2d271875` |
| `/data/models-large` | `a6d4ab58-84e1-4e48-9a67-13ad1c6f6e0a` |

Common mount and root-disk guards passed before/after the auth gate and release
preparation. Protected-state verification recorded `5228720128` root free bytes:
warning below 6 GiB,
above the 4 GiB stop threshold. Task files, logs, staging and backups use verified
`/data`; disposable gate caches and temporary files use private container tmpfs.
The final `00:21:19Z` handoff mount/root guards also passed.

## Phase A — actual pinned-image gate failed

Executed from Worker1 through SSH, with no production model, key or GPU mounted:

```bash
ssh ai-vm 'bash /data/build/f1d-qwen-20260915/run-auth-gate.sh'
```

The retained script records the full Docker invocation: exact image ID,
`--pull never`, `--runtime runc`, `--network none`, read-only root/source,
`--log-driver none`, dropped capabilities, no published port, and private tmpfs
at `/models`, `/run/secrets`, `/cache` and `/tmp`. Its payload is the unchanged
reviewed `tests/lifecycle/sglang_fixture/run_pinned_image.py --actual-image
--repo /fixture`.

Result: **exit 2**, with exact stdout:

```json
{"code": "actual_image_fixture_failed", "status": "FAIL"}
```

Image/source identity checks passed. Credential-free frame-only diagnosis
located `run_pinned_image.py:401` → `sglang_file_auth.py:98`:
`validate_environment()` rejects any environment name starting `SGLANG_`.
The immutable image supplies:

- `SGLANG_BUILD_COMMIT=49e384ce9d304648e9959666ecb8ce8cd98d0deb`
- `SGLANG_BUILD_URL=https://github.com/sgl-project/sglang/actions/runs/28210048245`
- `SGLANG_IMAGE_TAG=lmsysorg/sglang:v0.5.14`

Failure occurs before native application startup and before creation of the
synthetic sentinel. This is an **actual installed-image failure**, not an auth
PASS, import-only PASS or mock result. Diagnostic frame evidence is supplemental
and does not replace the unchanged gate. No environment removal or runtime
source patch was applied.

Evidence under the VM evidence root:

- `auth-image.txt`, `auth-gate.stdout`, `auth-gate.stderr`, `auth-gate.exit`
- `auth-diagnostic.stdout`, `image-environment-blocker.json`
- `auth-pre-mount.txt`, `auth-post-mount.txt`
- `auth-pre-root-guard.md`, `auth-post-root-guard.md`

### Root/F1S correction recommended; not applied

Reconcile the exact immutable build metadata with the rejection contract while
preserving rejection of functional SGLang switches/plugins. Review and commit
the correction, refresh launcher provenance, then rerun the actual-image gate.

The shipped helper also lacks actual signal delivery, native `/model_info`
missing/wrong/correct-key route tests, and actual-image negative key-file and
rejected-mode cases. Uvicorn capture leaves native application lifespan
untested. Required native application/startup, signal/cleanup and auth assertions
must pass before `auth_gate_passed` can become true. Actual model loading and GPU
execution remain separate Phase C gates.

Static cache review found installed `srt/environ.py:557,894` uses
`expanduser('~/.cache/...')` for DeepGemm/SGLang caches. The F1S runtime sets
`XDG_CACHE_HOME` but not `HOME`, CUDA cache, Torch extensions or FlashInfer
workspace paths. Review exact inherited values and explicitly bind required
cache locations to `/cache` with existing tmpfs for temporary files. This is a
source/path-contract concern; no actual model cache write or kernel failure was
observed. F1A's tiny kernel used explicit overrides; see
[F1A contract](f1a-sglang-contract.md). No cache correction was applied here.

## Phase B — protected release and obsolete boot writer

The task-specific preparation script supported `--help` and required its
`--dry-run` report before `--apply`. It checked both exact mount UUIDs, common
guards, bundle/source identities, target absence, and the obsolete unit/script
hashes before changes.

Completed preparation:

- Created the new isolated release at the exact reviewed detached commit;
  release checkout was clean.
- Changed ownership/write permissions only on the existing `/data/services`
  and `/data/services/llm-manager` parent inodes. Their previous metadata was
  backed up. No recursive ownership change was made to `/data`, models, GLM or
  the old checkout.
- Created protected acquisition/adapter directories and installed the exact
  reviewed adapter root-owned mode `0644`. The reviewed `protected_bytes`
  ancestry/file/hash check passed.
- Preserved legacy `active.json`; no deployment instance or canonical key was
  created. No lifecycle state was blindly replaced.
- Backed up and disabled only `m6b-post-reboot-verify.service`, then completed
  `systemctl daemon-reload`. Its old checkout-switching script was retained.
  No reboot or other unit disablement occurred.

The three preserved dirty reports are `m3-root-disk-guard.md`,
`m4b-docker-containerd-install.md` and
`m6b-nvidia-container-toolkit-install.md`. Their recorded hashes remained
unchanged after preparation.

| Backup / result | Location beneath `/data/build/f1d-qwen-20260915` |
| --- | --- |
| Manager, exact unit/script and enablement symlink; numeric ownership, ACLs/xattrs | `backups/release-pre.tar` |
| Archive SHA256 record | `backups/release-pre.tar.sha256` |
| Parent/model/old-checkout identity and permission metadata | `backups/release-metadata-pre.json` |
| Previous unit state | `backups/m6b-unit-before.txt` |
| Original dirty report hashes | `backups/old-dirty-reports.sha256` |
| Reviewed dry-run | `evidence/release-dry-run.txt` |
| Disable output and current unit state | `evidence/m6b-disable.stdout`, `m6b-disable.stderr`, `m6b-unit-after.txt` |
| Preparation result | `evidence/release-result.txt`: `PASS_PREPARED_AUTH_BLOCKED` |
| Pre/post root guards | `evidence/release-pre-root-guard.md`, `release-post-root-guard.md` |

Original unit SHA256:
`eb89d7312a0b870163e79e44b9c7f552aeb0b631f9d07fba943c393eddc07ede`.
Original script SHA256:
`35515bdc2158be054fc3474fc4efa6ca9badeeb3d5ef72c56f1c69664187be76`.
Both exact originals are retained in the backup; the script remains at
`/data/services/m6b-post-reboot/m6b-post-reboot-verify.sh`.

Backup archive SHA256:
`51456f7ba636d240acb256e3ba2127ab1605b5cc8543d1e44434d6e46735cded`.
`evidence/release-verification.json`, collected at
`2026-09-15T00:16:12.125072+00:00`, confirms old state equals the backup, the
release is clean, and the canonical key/default deployment instance are absent.
Final source, adapter, unit and script hashes plus permission/inode records are
in [release verification](f1d-evidence/release-verification.json), `files`.
The original unit/script hashes above still match; disablement changed the
enablement state, not their contents. The unit remained `active/exited` with
`UnitFileState=disabled`; it was not restarted or executed.

## Qwen completion and narrow protection

**PASS_SEALED.** Acquisition completion semantics, exact computed hashes and
fresh stat identities were rechecked before narrow protection. The acquisition
owner had finished; the lock was held during sealing. No writable descriptors,
unexpected/partial entries, unsafe path/symlink or inode aliases were accepted.

Required model identity: `Qwen/Qwen3-Coder-Next-FP8`, revision
`da6e2ed27304dd39abadd9c82ef50e8de67bdd4c`, at
`/data/models-large/qwen3-coder-next-fp8`; 48 artifacts, comprising 40 weight
shards and 8 assets, totaling `80407722953` bytes. Immutable manifest SHA256:
`022674d4daf63fa57c2798a30fea80c6dde7b1b2e73630ae3c3aa94e45debb9e`.

Supplied M1 evidence reports `PASS_ALL_48_VERIFIED`, with manifest/hash/size/stat
alignment and inactive/unloaded acquisition owner. F1D reused acquisition
worker computed hashes after rechecking source/evidence identity and all 48
file stat identities. **F1D did not independently reread all weight bytes.** It
independently hashed all eight small assets and checked native Qwen3Next/FP8
config, tokenizer/no-remote-code contract and exact 40-shard index references.
Source acquisition
status is `/data/build/f1a-qwen-20260915/evidence/acquisition-status.json` and
the acquisition unit is `f1a-qwen-fast-acquire-20260915.service`.

Protection scope: the `/data/models-large` mount inode `2` and the new Qwen
directory are `root:ai`, mode `2755`; the 48 Qwen artifacts and acquisition lock
are `root:ai`, mode `0644`. Only listed targets were protected. Pre/post identity
and metadata are recorded; payload device/inode/size/mtime were preserved.
Final checks verified all 48 payload write denials and directory/mount write
denials for the download user. GLM's child remained writable and owned by the
download user, group `ai`, mode `2755`, inode `169607169`.

- Metadata backup: `/data/build/f1d-qwen-20260915/backups/qwen-metadata-pre.json`.
- Protected receipt: `/data/services/llm-manager/acquisition/qwen3-coder-next-fp8.complete.json`;
  SHA256 `5cd9737ba138962f05a83745ea646debd04adfd41dcbc40780269406df915471`.
- Protected proof: `/data/services/llm-manager/acquisition/f1d-qwen-seal-evidence.json`;
  SHA256 `0d6cfcd28abe2094b7b6cfd7188bb3b79b71a73e835eb3f9bbc7efee5883aa16`.
- Evidence class:
  `acquisition_worker_computed_sha256_m1_and_current_stat_alignment_protected_payload`.

The reviewed completion and launcher validators passed during final
verification. Local copies: [seal result](f1d-evidence/qwen-seal-result.json),
[seal proof](f1d-evidence/qwen-seal-evidence.json) and
[completion](f1d-evidence/qwen-completion.json). This integrity/protection
attestation does not open the failed auth gate or prove model inference.

## Phase C — not started; measured baseline only

No Qwen inference container or lifecycle start was attempted. All three old
inference containers remained stopped. The retained runtime intent was TP2 on
GPUs `0,1`, alias `qwen3-coder-next`, context `32768`, one tokenizer worker,
`qwen3_coder`, memory fraction `0.75`, one running request, host loopback port
`30003`, restart policy `no`, startup deadline `7200s` and authenticated warmup
`600s`. These remain proposed reviewed settings, not a tested live deployment.

Baseline collected at `2026-09-15T00:16:12.125072+00:00` in
`/data/build/f1d-qwen-20260915/evidence/release-verification.json`:
each GPU reported `97887 MiB` total; GPU0 used
`2 MiB`, GPU1 used `34 MiB`. RAM total was `946806919168` bytes and available
RAM `934705438720` bytes.
No model load time, CPU load during inference, model GPU/RAM allocation, cache
allocation, latency, throughput or token counts were measured.

At `00:18:21.064318Z`, GLM acquisition was still active as PID `49253`, invocation
`55ab64073abe462189f82c54ce8e299e`. It subsequently completed independently:
the `00:21:55.600375Z` read-only observation found status
`PASS_ALL_11_COMPUTED_SHA256`, updated `00:19:39Z`, 11 verified shards,
`467289116837` bytes and no active shards. Its unit was inactive/dead/not-found,
MainPID `0`; the prior PID no longer existed. F1D never stopped or restarted GLM
and did not perform GLM payload stat/hash alignment or a completion attestation.
See [GLM status observation](f1d-evidence/glm-final-observation.json).

All three inference containers remained stopped. Their retained IDs/names are
`634daeb70a3a` / `minimax-m3-mxfp8-poc`, `321ee2110e2e` /
`sglang-qwen3-30b-a3b-instruct-2507`, and `6cfa91273417` /
`sglang-smoke-qwen3-0.6b`. See [release inventory](f1d-evidence/release-verification.json)
and [final verification](f1d-evidence/final-verification.json), whose running
container list is empty.

Chosen operator state: all inference stopped. No new deployment instance or
boot unit exists. The unchanged legacy `active.json` records `status=active`
and `model_profile=qwen3-30b-a3b-instruct-2507`, despite no running inference
container. Its preserved SHA256 is
`bd34931c6ed9cc0c887795dcefaebd65b4ceec95f061374938b09443a5c47a78`.
This is a stale legacy record, not validated lifecycle desired/boot intent.
The obsolete m6b writer is disabled. There was no API-ready
notification or V1 lease because the API was not ready. Stop/start preservation,
stopped boot intent through the new lifecycle, GLM switching and boot recovery
were not exercised.

## Checks and acceptance status

| Check | Result / evidence class |
| --- | --- |
| Exact mount UUIDs, common mount/root guards | PASS for gate/release changes; actual VM checks |
| Exact installed image and reviewed launcher/source identities | PASS; actual image inspection / file hash evidence |
| Unchanged actual-image auth fixture | FAIL, exit 2 before sentinel/native startup |
| Failure diagnosis | Frame-only actual-image diagnostic; no secret/log payload disclosure |
| Protected release/adapter preparation and old dirty-report preservation | PASS; actual VM mutation/verification evidence |
| Obsolete boot-writer backup/disable/reload | PASS; actual VM unit-state evidence |
| Qwen final integrity/protection receipt | PASS_SEALED; reused acquisition hashes, fresh identities, eight independently hashed assets and protected receipt |
| Real key provisioning and deployment instance | NOT_PERFORMED |
| Healthy loaded backend, authenticated warmup, `/health` Up | NOT_TESTED |
| Missing/wrong/correct live auth, exact `/v1/models` alias, short generation | NOT_TESTED |
| A1 streaming/nonstreaming tool → client tool result → final answer | NOT_TESTED |
| Parallel, malformed and unknown tool handling | NOT_TESTED |
| CUDA/SM120 model kernels, fit and performance | NOT_TESTED |
| Independent OpenCode V1 / overall agent READY | NOT_TESTED / NOT_READY |
| Lifecycle stop/start, GLM switch and boot recovery | NOT_TESTED |
| Actual reboot | NOT_PERFORMED |

Retained F1S worker mocks/source tests remain source-only historical evidence.
They were not substituted for the failed actual-image gate. Local evidence
verification passed: `bash -n` on the three retained shell runners;
`ast.parse` on `diagnose-auth-gate.py` and `seal-qwen.py`; JSON parsing of retained
JSON evidence; and SHA256 checks matching the copied completion/proof to the
published identities above. These are syntax/artifact checks, not additional
live auth or inference tests. Grep-based secret scan and attribution checks
passed; commit/bundle identities are recorded in the task handoff.

## Rollback and safe continuation

Backups preserve the manager tree, exact unit/script and enablement symlink,
plus metadata for the narrowly changed parent inodes. Before any restore,
verify archive hashes, inspect current state and coordinate VM mutation/client
ownership. Restore only selected backed-up paths and exact metadata; do not
extract the entire manager archive over newer lifecycle state. Restoring the
old enabled m6b unit also restores its known branch-regression risk and requires
explicit review of that regression. After unit restoration, run `systemctl
daemon-reload` and verify the intended enablement state. No rollback command
was executed by this task.

For a Qwen permission rollback, first invalidate/remove its
trusted completion receipt, hold the acquisition lock, confirm recorded
device/inode identities and restore only listed ownership/mode/xattrs from the
Qwen metadata backup. Never recursively alter models; ctime cannot be restored.

Root should assign a bounded F1S source correction/review for the environment,
cache and fixture coverage issues. A fresh F1D continuation must recheck mounts,
root headroom, reviewed commit/source hashes, protected Qwen receipt and current
acquisition ownership before rerunning the unchanged corrected fixture. Only
after all prerequisite gates pass may it provision the key/instance and use
reviewed `llmctl` for real start and API/A1 acceptance. Coordinate an active
client lease before stop/start testing; independent V1 remains required before
agent READY. No ad hoc environment bypass or source patch is authorized by this
report.

## Report provenance and handoff

This report covers reviewed integration `e46c788534d5b71e988c2cdf188f37f6214f7514`
and the exact failed image/adapter identities above. Local coordination inputs
were `../coordination-input.md`, `../progress.md`, `../blocker.md` and supplied
F1A/M1/F1S evidence; executable commands and VM evidence live under the task
root. Recommendations above are not applied source fixes.

Persisted session: `01a0a262-5f20-77f0-b5ee-1709b694476a`.
Local JSONL: `/Users/agent/CodexProjects/llm-orchestration/tasks/F1D-20260915/events.jsonl`.

Packaging checks passed: grep-based credential scan, credential-free Git remote,
effective author and committer `CodexAIagent
<133749519+djeZo888@users.noreply.github.com>`, JSON/AST/shell checks and exact
receipt/proof copy hashes. See [packaging checks](f1d-evidence/packaging-checks.json)
and [evidence recipes](f1d-evidence/README.md). No lifecycle source was changed
to bypass the failure. The milestone report commit and incremental bundle
identities are recorded in task sibling `../final.md`; no remote push is part
of this task. The persisted JSONL remains in place.
