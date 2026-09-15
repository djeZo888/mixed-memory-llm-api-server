# L2VMP — existing ai-vm activation plan for root review

**PLAN COMPLETE; APPLY NOT AUTHORIZED.** Existing-volume registration and control binding are feasible without stopping or recreating GLM32K. Final root-reviewed L2 source/closure, the current D1-runtime/32K compatibility snapshot decision, and fresh validation of supplied Q38A seal are the narrow remaining gates. This is an ai-vm adoption transaction, not bootstrap or an installer milestone.

Artifact directory for this committed report: [l2vmp-evidence](l2vmp-evidence/README.md). Full task-root plan is `../activation-plan.md`; proposed files and evidence are copied under `reports/l2vmp-evidence/` for standalone bundle review.

## 1. Scope, source authority, and frozen facts

This task changed only worker report artifacts. No VM files, keys, services, units, firewall, containers, models, disks, API requests or GPU state were changed. No key contents were opened/hashed/printed. One compact inventory plus two small source-driven completion reads; no repeated broad audit. Server remains API-only; browser/chat/tool execution belongs on the later frontend VM. No UI/tools absence is a failure.

Reviewed base: `6ffd620db7717eb81c615d77c76e9662dbe30027` (includes U1B). Historical deployed D3 release: `7b541017c3e1b2bda80676bcd31bc87d0a4507bc-d3-20260915`. Focused sources: AGENTS.md; `scripts/lifecycle/{manager,instance_binding,storage_binding,boot_unit}.py`; actual storage/writer modules; `scripts/control/{installation,serve,adapter,discovery,catalog,core,journal}.py`; D3/D3T, Q38S, L1/L1B and U1B reports. External N1 facts and Q38A acquisition plan and final handoff/evidence were read. Frozen `l2-handshake.md` composes base6ffd with Q38B `3a470d2b8c90398be0bffe78bccd13fe1c3a0f2e`; that composition is **not yet reviewed installable source here**. Latest L2 handshake supersedes its earlier six-profile list: five fixed profiles, with final GLM runtime/image/deployment/proof supplied by D3PD/D3T. No WIP checkout imported. `control-source-baseline.json` hashes inspected base files; it is not an approved L2 installation manifest.

Inventory timestamp `2026-09-15T02:30:47.866533+00:00`; see `host-facts.md`, `host-inventory.json`, `host-contract-followup.json`, `host-path-completion.json`.

| Invariant | Exact observed value |
|---|---|
| `/data` | UUID `8daf56f1-5649-4163-9d87-919c2d271875`, ext4, exact mount `/data`, FSROOT `/`, rw, device8:17 |
| `/data/models-large` | UUID `a6d4ab58-84e1-4e48-9a67-13ad1c6f6e0a`, ext4, exact mount `/data/models-large`, FSROOT `/`, rw, device8:33 |
| Root free | 5,219,024,896 bytes /4.861GiB: WARN below6GiB; STOP later apply below4GiB |
| Instance | `ai-vm-d0b`, schema1, `/data/services/llm-manager/deployment-instance.json`, root0600 gid1001; SHA256 `8a5f7787c00319f093656d4fe0b6953c79ae31669b4da7690e6f7386ecad839a` |
| Durable state | `/data/services/llm-manager/active/active.json`, root:root0600, SHA256 `c63de9b1a77aa4d62496880c7dad8cb6a22a10de9736c5305545e3579d576f1f` |
| Recovery journal | `/run/llmctl/recovery.json`, root:root0600, **same SHA256 as durable state** |
| Current state | schema2, selected `glm-5.3-ud-q4-k-xl-32k`, last_selected `glm-5.3-ud-q4-k-xl-8k`, desired running, observed ready, boot_policy manual, container_running true, state_persisted true, failure null, updated_at1789433513604541997 |
| Current container | `bb77b764cb9677f3c04c1e60359d287a15abb304ba289f38703e58b5a6fc0d55`; name `llmctl-glm-5.3-32k`; StartedAt `2026-09-15T00:48:45.235739944Z` |
| Immutable image | `sha256:6866856c573d69d504f82265321b182f631a7b3912a1ed1b4efbf893729d4e62` (also actual Config.Image) |
| Labels | io.llmctl.owner=mixed-memory-llm-api-server; instance=ai-vm-d0b; deployment=glm-5.3-ud-q4-k-xl-32k |
| Endpoint / intent | host127.0.0.1:30002, container0.0.0.0:30002, aliasglm-5.3, context32768, parallel1, bridge, restart=no |
| Existing GLM receipt | `/data/services/llm-manager/acquisition/glm-5.3-ud-q4-k-xl.complete.json`; SHA256 `bcd8d9f85baa9bd1fe54dc65b9022487307190cf11583580ab66af845b53f48b` |
| Native key | `/data/services/secrets/llm-api-key`, root:root0600, single link; metadata only; preserve bytes/path |
| Unit intent | old m6b-post-reboot-verify disabled/active(exited)/MainPID0; llmctl-boot absent; llm-control absent; no drop-ins |

Recorded source device paths `/dev/sdb1` and `/dev/sdc1` are mount observations, not write targets. Never pass them to mount, format, partition, fstab or disk commands. Reobserve exact UUID/mount/root/ancestry in fresh apply; duplicate UUID, bind/subvolume, wrong parent, missing mount, or changed identity => STOP. No filesystem, fstab or new-disk changes belong to this plan.

## 2. Exact proposed files and metadata

All entries below are **later proposed writes**, not writes performed by L2VMP. Existing paths must match the observed bytes/metadata; unexpected presence is a review stop, not permission to overwrite. Root source is a small reviewed recovery code exception; model/build/cache/log/service payload stays on registered data. No recursive copy of repository or ownership changes.

| Target | Proposed action / schema / mode |
|---|---|
| `/etc/local-ai-server/` | Absent → root:root0700; required private parent for actual mounted writer |
| `/etc/local-ai-server/storage.json` | Absent → `proposed/storage.proposed.json`, schema1, root:root0600, single-link atomic file; exact existing mounts only |
| `/data/services/installer/` | Absent → root:root0700, empty. Required existing `roots.state` compatibility path; no installer flow or markers |
| `/data/services/llm-manager/deployment-instance.json` | Reviewed historical import only; add exact stable identity and historical_import=true. Keep root0600; preserve gid1001 when safe writer creation inherits it. Record actual post metadata |
| `/data/services/llm-manager/active/active.json` | **No write**; keep original bytes, path, owner, mode, mtime/ctime, JSON updated_at and container identity |
| `/run/llmctl/recovery.json` | **No write**; keep original bytes, mtime/ctime and JSON updated_at; do not replace with newly generated state |
| `/run/llmctl/lifecycle.lock` and parent | Existing root0600 /root0700; reuse exact canonical lease, never unlink/recreate held lock |
| `/data/services/llm-control/` | Absent → root:root0700, explicit parent for actual journal writer |
| `/data/services/llm-control/operations.json` | Absent now. Do not preseed. First authorized control refresh may create valid schema1 journal through reviewed writer; becomes root0600 service data |
| `/etc/llm-server/` | Absent → root:root0700; shared parent with N1S, preserve if N1VM created correct protected parent first |
| `/etc/llm-server/control.json` | Absent → `proposed/control.proposed.json`, L2 schema1 + optional advertised policy, root:root0600 |
| `/etc/llm-server/control-api-key` | Absent now. Fresh apply privately rechecks; reuse suitable existing dedicated CONTROL key; otherwise create once root:root0600. No value/hash in reports |
| `/usr/local/lib/llm-server/` | Absent → root:root0755 |
| `/usr/local/lib/llm-server/control-api/` | Absent → protected root-filesystem closure detailed below; directories root0755, Python/JSON/evidence files root0644, invoked shell scripts0755, single links, no symlinks |
| `/usr/local/lib/llm-server/control-api.manifest.json` | New sibling **operator evidence**, root0644; exact reviewed commit and per-file SHA256/size/mode. Not a runtime config or loader; include all closure/profile/evidence files |
| `/etc/systemd/system/llm-control.service` | Absent → exact reviewed template with only registered-data substitution, root0644; local127.0.0.1:30000 |
| `/run/credentials/llm-control.service/control-api-key` | systemd-managed volatile credential created on later service start; do not manually populate; root0400/0600 |
| `/data/services/llm-manager/adoption/l2vm-existing-host-20260915/` | Proposed exclusive root0700 transaction backup/report directory; refuse reuse/overwrite. Raw nonsecret originals, metadata/absence manifest, exact proposed/post hashes, guard reports under data only |
| `/data/services/llm-manager/acquisition/qwen38-27b-fp8.complete.json` | Separate later receipt publication only after Q38A seal; exact schema in §6, root0600 |
| `/data/services/llm-manager/evidence/` | Create root0700 only when later valid Q38B runtime receipt is published |
| `/data/services/llm-manager/evidence/sglang-qwen38-0.5.19.auth.json` | **Deferred**, actual approved Q38B receipt only. No manufactured flags/PASS from source tests |

Fixed boot recovery `/usr/local/lib/local-ai-server`, llmctl-boot unit and `/etc/tmpfiles.d/llmctl.conf` were absent. **No boot files/wiring in the initial adoption transaction.** Current shared `/run/llmctl` is sufficient for present session. Enabling control across reboot would additionally require an owner-reviewed shared-directory provisioning contract; do not invent a tmpfiles template or claim reboot acceptance.

N1S/N1VM exclusively owns `/etc/llm-server/network.json`, `/usr/local/lib/llm-server/private-network/private_network.py`, network state/lock, six private transport units and firewall. Those are not L2VM writes. L2 includes identical helper bytes inside its control closure. If N1VM creates shared `/etc/llm-server`, reuse only after exact protected metadata validation.

### Required nonrecursive storage-root metadata delta

Current verifier requires all derived roots root-owned and non-group/other-writable. Registry alone fails. These four changes preserve directory contents/inodes/group/setgid; chown can clear setgid, so restore the exact proposed mode after owner change. No recursive chmod/chown, no model/cache payload modification.

| Existing directory | Before uid:gid/mode | Proposed after | Rollback |
|---|---|---|---|
| `/data/build` | 1000:1001 /2775 | 0:1001 /2755 | restore1000:1001 /2775 |
| `/data/hf-cache` | 1000:1001 /2775 | 0:1001 /2755 | restore1000:1001 /2775 |
| `/data/backups` | 1000:1001 /2775 | 0:1001 /2755 | restore1000:1001 /2775 |
| `/data/logs` | 1000:1000 /2755 | 0:1000 /2755 | restore1000:1000 /2755 |

These revoke ordinary-user direct-child creation. Wait for Q38A sealing/owner release and check no independent job depends on those direct-child writes; do not claim no operational effect. If final L2 verifier retains these requirements, root must include these exact metadata changes in fresh L2VM approval. If it differs, root reviews that concrete difference; never bypass with a different roots mapping. Existing `/data`, model mount, services, secrets, docker/containerd and protected GLM subtrees need no change.

## 3. Reviewable JSON and minimized state diffs

`proposed/storage.proposed.json` contains the full schema1 candidate and observed source/device/parents. The stable identity is exactly `proposed/storage-identity.proposed.json`: schema_version, roots, and role `{path,mount,uuid,fstype}` only. Source/device/parents are observed fields excluded from identity. Capacity/warnings are observations, not permanent authority; final approved registration serializer may include fresh observations without changing stable identity.

Exact roots (all must exist and remain on the registered role mount):

```json
{"hf_cache":"/data/hf-cache","docker":"/data/docker","containerd":"/data/containerd","build":"/data/build","logs":"/data/logs","backups":"/data/backups","services":"/data/services","secrets":"/data/services/secrets","state":"/data/services/installer","models":"/data/models-large"}
```

Instance before has neither binding field. Exact semantic delta (full object in `proposed/instance-additions.proposed.json`):

```diff
+ "storage_identity": <exact contents of storage-identity.proposed.json>
+ "historical_import": true
```

The angle-bracket reference is documentation, not JSON. Actual helper API is `lifecycle.instance_binding.import_historical_instance(binding, lease=canonical_lease, storage_io=actual_reviewed_storage_io)`. It re-reads protected original through anchored descriptor and preserves every other value, including description/notes omitted from public inventory. It reserializes the instance; original byte backup is mandatory. No fresh template, instance-ID substitution or legacy-state synthesis. Base lacks the reduced-role API accepted by actual writer; **do not run this against base6ffd**. L2 must provide tested actual-role integration. Existing storage modules in `install.*` are reviewed imports required by lifecycle; no installer entrypoint or WIP module is invoked.

```diff
# durable active.json, recovery.json, native key, GLM receipt:
# EMPTY DIFF
# selected=glm-5.3-ud-q4-k-xl-32k, desired=running, boot_policy=manual remain.
```

Control actual before is absent, not an existing schema1 file. Planned new contents:

```json
{"schema_version":1,"advertised_endpoint_policy":"private_network"}
```

This extra field is rejected by base U1B and accepted only by reviewed L2. Without the field L2 retains tunnel DTO. Missing/invalid N1 policy is caught as PrivateNetworkError and falls back to tunnel; it must not prevent local authenticated recovery. Unit minimized diff is `proposed/control-unit.diff`; only `ReadWritePaths=-@REGISTERED_DATA_ROOT@ /run/llmctl` → `ReadWritePaths=-/data /run/llmctl`. Full proposed unit is `proposed/llm-control.service.proposed`.

## 4. Can Manager adopt GLM unchanged? Resolved comparison

**Yes, with the exact historical instance binding and retained32K profile; no start/stop/recreate call is needed.** Manager construction loads/validates identity and initializes memory only. `load_manager` reads fixed registered instance. Import writes only that instance. Durable/recovery schema2 does not require storage_identity, so no state transformation is justified.

Current historical path resolution preserves all five mount tuples: model → `/models` read-only; historical runtime-cache/llama-cpp → `/cache`; historical logs/llmctl/glm-5.3 → `/logs`; services/llm-manager/glm-5.3 → `/service`; existing native key → `/run/secrets/llm-api-key` read-only. Without `historical_import:true`, modern profile suffixes change cache/log/service paths and reuse validation fails. Do not “fix” that by recreating container or editing live state.

Observed command/entrypoint, image, alias, context, label identity, bridge/loopback publication, restart=no, three exact required nonsecret environment values, GPU DeviceIDs0,1 and bounded json-file20m/3 contract match reviewed GLM32K behavior. Source-only profile uses role objects/historical suffixes; its raw bytes differ from D3 old profile, but resolved launch values match. Original state bytes and IDs need zero change. There is no profile hash label to regenerate. D3T tuning/GLM final-context differences are explicitly pending and excluded.

`_start` can reuse an exact running container without Docker create/start, but it saves starting/ready state and performs key/readiness probes. **Do not call start as an adoption check.** `status` probes with inference key; control GET can write its own journal. Initial control startup reads control credentials, reads existing operations journal if available and starts an idle worker. No automatic model transition/replay or active-state write occurs at startup. First GET may create/update operations journal, acquire lease and mark interrupted pending operations. Later acceptance must explicitly allow those bounded effects.

Recovery identity uses `/run/llmctl/recovery.json`, strict container/image/name/labels and live Docker identity. It does not need model files/key/profile to stop the trusted container. This plan tests no stop. In source state selection, a newer failed-persistence journal can override primary by updated_at; preserving both byte snapshots, mtime/ctime and JSON updated_at matters. No timestamp reset or merging.

## 5. Exact root control closure and model allowlist

Final L2 owner must deliver reviewed commit and frozen per-file hashes with synchronized `installation.RECOVERY_FILES`, `NORMAL_FILES`, `scripts/control/source-closure.json`. Deploy only the resulting explicit union, with below required inputs accounted for. Do not treat baseline hashes as final approval. Final source/manifest hashes are intentionally pending, not invented.

Base mandatory control recovery files (18), beneath `/usr/local/lib/llm-server/control-api/`:

```text
scripts/control/__init__.py
scripts/control/serve.py
scripts/control/installation.py
scripts/control/adapter.py
scripts/control/core.py
scripts/control/protocol.py
scripts/control/journal.py
scripts/control/catalog.py
scripts/control/discovery.py
scripts/control/http.py
scripts/common/lifecycle_lease.py
scripts/lifecycle/__init__.py
scripts/lifecycle/manager.py
scripts/lifecycle/runtime_io.py
scripts/lifecycle/storage_binding.py
scripts/lifecycle/qwen_next.py
scripts/install/__init__.py
scripts/install/storage.py
```

Known normal/source-evidence/operator inputs to account for in final exact union:

```text
scripts/install/storage_io.py
scripts/install/prerequisites.py
scripts/common/require-data-mounted.sh
scripts/common/root-disk-guard.sh
scripts/common/registered-storage.py
scripts/lifecycle/sglang_file_auth.py
reports/f1s-contract-evidence/f1a-qwen-manifest.json
scripts/control/source-closure.json
scripts/control/private_network.py
scripts/lifecycle/qwen38.py
scripts/runtime/sglang38_file_auth.py
scripts/lifecycle/instance_binding.py
reports/q38r-source-weight-manifest.json
reports/q38s-acquisition-manifest.json
tests/lifecycle/sglang38_fixture/provenance.json
tests/lifecycle/sglang38_fixture/run_fixture.py
tests/lifecycle/sglang38_fixture/run_pinned_image.py
tests/lifecycle/sglang38_fixture/auth_native.py
tests/lifecycle/sglang38_fixture/chat_template.jinja
```

Fixture files above are hash/read inputs of runtime evidence verification, **not executed tools** in L2VM binding. `instance_binding.py` is the one-time explicit adoption helper. `root-disk-guard.sh` is needed for mandatory later checks; final owner manifest must cover it even if not imported at control startup. Private helper must match N1S standalone bytes exactly. Root source/key/config protection and actual Python import closure must work without `/data`; no symlink into a data release or unreviewed user checkout.

Latest L2 five-profile operator allowlist `configs/control/ai-vm-live-snapshot.json` (not a runtime loader) must enumerate exact sources/hashes:

```text
configs/models/glm-5.3-ud-q4-k-xl.json
configs/models/qwen38-27b-fp8.json
configs/runtimes/sglang-qwen38-0.5.19.json
configs/deployments/qwen38-27b-128k.json
configs/deployments/qwen38-27b-256k.json
```

**Narrow unresolved existing-state requirement:** normal current-GLM observation requires both unchanged reviewed `configs/runtimes/llama-cpp-v0.4.1-d1.json` and `configs/deployments/glm-5.3-ud-q4-k-xl-32k.json`. Latest L2 fixed final selection explicitly excludes the old D1 runtime/image; do not silently put them back into that allowlist. Root/L2 must supply an explicitly reviewed temporary existing-host adoption snapshot or other owner-supported compatibility contract retaining those exact current identities; until then normal control adoption is gated. Registration/instance facts remain frozen independently. Do not replace current bytes/IDs with D3PD/D3T. Final GLM runtime/deployment source/hash, measured patched image ID, proof and recipe/import closure all stay null/unpublished until owner review. There is no hidden-only profile flag in current discovery: it enumerates all installed deployment JSON. An authorized compatibility snapshot retaining32K would not add a third model identity; it preserves the current GLM context entry. Old8K, Coder-Next, oldQwen/SGLang0.5.14 deployment profiles are not published. last_selected8K remains unchanged historical state metadata.

Final identities are `unsloth/GLM-5.3-GGUF` and `Qwen/Qwen3.8-27B-FP8`; Q38 profiles use aliasqwen3.8-27b, port30004, contexts131072/262144. No model router, extra active backend or final-context claim. Receipt absent => known unavailable target, omitted from installed listing. Valid receipt + source/runtime checks can make a profile available for guarded later start, but Ready requires fresh trusted live container/authenticated model probe. Occupied context remains unknown/null; configured size is not live occupancy proof.

Boot source is a separate fixed tree `/usr/local/lib/local-ai-server`, with base exact11 files: `scripts/llmctl`, lifecycle `__init__.py,manager.py,runtime_io.py,qwen_next.py,storage_binding.py`, common `lifecycle_lease.py`, install `__init__.py,storage.py,storage_io.py,prerequisites.py`. `boot_unit.render_boot_unit` requires byte equality with a protected data source and rejects extra files; manifests go outside it. Q38B may change imports. **Do not deploy this stale boot set or render/enable boot unit here.** boot-stop would stop GLM; boot-start only replays running+resume intent. Manual must stay manual and absent unit must stay absent. Root-resident control recovery supplies the bounded immediate recovery interface independently.

## 6. Q38 receipt publication from acquisition evidence

This is separable from registration/control. Q38A owns exact destination `/data/models-large/qwen38-27b-fp8`, repo `Qwen/Qwen3.8-27B-FP8`, revision `017b9c7af6b5689d5dd426a76e0bc077eb5ca20a`,81 artifacts/66 weights/30,890,049,597 bytes, pinned manifest SHA256 `726012378a40f648a104230d3f5ed5d6bc505cbd09b32918fc29aa81c0f075f2`. Observed root0555 directory alone is not completion proof. Do not infer finished status from old progress, permissions or downloader exit.

Q38A now supplies exact sealed evidence from commit `d42b885ecc25e092dfb0ea1bbc0247b8f91f0b89`: `/data/models-large/.q38a-evidence-20260915/sealed-evidence.json`, SHA256 `a9b1ee9c80ca7030b79387b64f63d494159d0db7966f6510737e20c568584cfe`; protected `acquisition-complete.json` SHA256 `970b026bbb8a4d500f1aee146c3ffaf51f64ca7d0eb3c3a24237e6a51c35f8c5`. L2VMP validated the exact committed copy hash, all81 computed tuples versus full pinned manifest, and recorded root0444/single-link sealed stats on worker. `q38-receipt-mapping-verification.json` records that scope. Full proposed receipt `proposed/qwen38-27b-fp8.complete.proposed.json` SHA256 `2020e3d4b19a3d4a7221dfbf37a4f558ed98dcbd73e302b716ab95fb04e17dce` is review-only and was not published. Exact companion instance addition is `proposed/qwen38-instance-model-integrity-addition.proposed.json`. Actual auth/model proof remains NOT_TESTED.

After owner release and fresh revalidation of those protected bytes/stats, a later bounded publisher validates every computed digest and byte count against pinned manifest, unique exact81 membership (including .gitattributes and zero-byte safetensors-md5sum.txt), revision, destination, whole-volume UUID, sealed no-write/single-link stats and acquisition lock ownership/quiescence. Current stat identities must match Q38A seal; otherwise STOP and return to acquisition owner. Do not confuse LFS pointer Git SHA1 with payload hash. Retain richer status/seal bytes unchanged in protected transaction evidence. No acquisition/installer loop is required.

Exact canonical receipt object has **only** these fields:

```text
schema_version: 1
complete: true
repo_id: Qwen/Qwen3.8-27B-FP8
revision: 017b9c7af6b5689d5dd426a76e0bc077eb5ca20a
model_root: /data/models-large/qwen38-27b-fp8
manifest_sha256: 726012378a40f648a104230d3f5ed5d6bc505cbd09b32918fc29aa81c0f075f2
artifact_count: 81
total_bytes: 30890049597
artifacts: exactly81 objects {path: exact path, size_bytes: exact integer, sha256: verified computed digest, verified: true}
```

No extra acquisition status/timestamp/metadata fields are accepted by current exact Q38 check. Do not write a completion JSON from manifest expectations alone. Under canonical lease plus final reviewed actual MountedStorageGuard/AnchoredRoot, publish root0600 receipt, then append only this instance.model_integrity entry:

```text
qwen38-27b-fp8: {
  verified: true,
  revision: 017b9c7af6b5689d5dd426a76e0bc077eb5ca20a,
  manifest_sha256: 726012378a40f648a104230d3f5ed5d6bc505cbd09b32918fc29aa81c0f075f2,
  completion_manifest: /data/services/llm-manager/acquisition/qwen38-27b-fp8.complete.json,
  evidence: exact retained nonempty sealed-evidence reference string
}
```

Evidence must be a **string** for Q38, unlike existing GLM evidence list; preserve GLM list unchanged. Receipt first, instance link second gives an inert orphan if interrupted before link. Rollback uses pre-stage instance bytes, not a guessed inverse. No select/start/boot/readiness fields change. Leave Q38 runtime entry absent until actual Q38B auth evidence; receipt-only listing stays unavailable if runtime checks fail. When actual auth proof is later linked it can become available but remains unready until live loading/probing. No unsupported `enabled:false`, fake failure or fabricated readiness receipt.

Q38B actual-image receipt is independently required at fixed path from §2, with exact OCI manifest/config/containerd identity relationship, approved source/launcher/fixture hashes and checks. Earlier Q38S single-image-ID shape is not assumed current; root must supply accepted Q38B source/receipt. Image pull success is not auth, model load or Ready. No Q38B fixture/load/model switch occurs during GLM-preserving registration/control binding.

## 7. Ordered later apply (fresh L2VM authorization required)

1. **Freeze approvals/input bytes.** Read latest coordination. Root approves exact L2 source/closure+hashes, identical N1S helper, current-adoption snapshot contract (five fixed profiles plus separately authorized old runtime+32K compatibility), directory metadata delta, and guarded existing-volume registration operation. D3PD/D3T final runtime/image/deployment/proof slots remain deferred. Do not wait for final tuning to freeze storage/state plan. Q38 receipt stage additionally needs fresh validation of the supplied complete sealed Q38A evidence. Confirm no lifecycle/request/metadata ownership conflict; GLM running is an invariant, not a request to stop it.
2. **Preflight and backups.** Recheck only affected facts/identities and original hashes; STOP if changed. Use root-supplied `VM-GUARDS.json` for **all** guard checks: corrected protected D3 release `7b541017c3e1b2bda80676bcd31bc87d0a4507bc-d3-20260915`, `scripts/common/require-data-mounted.sh` SHA256 `5bd86b1e3f84fe5ca76922ca896289edb723b09bc03b99044b7d1ec320215c4f`, and `scripts/common/root-disk-guard.sh` SHA256 `2f798c28d905fd819b00c550c0fd3cd7ebdac95ebb32f38876bce952dcbaf813`. Verify exact source hashes and root ownership before invocation; never invoke dirty-checkout guard or delete old/tmp artifacts. Run both before writes and after service/data writes, explicit report/temp under verified data, sanitized environment, never root default. These canonical D3 guards remain required after registration; additionally run final L2 registered binding verification, rather than silently replacing canonical guards. Separately require exact models mount and byte-level root>=4GiB. Guard failure stops; do not use fixture/environment overrides. This task ran no guard that writes a report on VM.
3. **Capture exclusive transaction originals.** Before registration, actual RegisteredStorageBinding/AnchoredRoot cannot bootstrap themselves: registry is absent and current root metadata fails verification. Fresh L2VM must first present for root review a tiny fixed-path descriptor-anchored backup/metadata/registration write procedure, guarded by exact existing mount facts and canonical D3 guards; no generic storage.adopt or framework. This is a narrow implementation seam covering steps3/4 only. After registration passes, use the actual reviewed registered writer. Under free canonical lifecycle lease record every affected file's original bytes SHA256/uid/gid/mode/link/inode and explicit absence, including instance, both states and existing GLM receipt. Keep raw nonsecret byte copies root0600 under exclusive data backup directory; fsync+hash verify. For directories capture uid/gid/mode/inode/device, never recurse. Record original unit state and absence. Key files get metadata/absence only; no key backups in worker/report or key hash. Existing suitable control key is untouched. No journal seed or lock replacement.
4. **Stage the reviewed root control source first, with no config/key/unit activation.** Copy the exact approved closure including one-time historical helper and guards to its fixed protected root path; verify hashes, imports, metadata and no unexpected files. This supplies the code used in step5; do not execute from a user checkout. Then **protect exactly the required data root metadata after Q38A owner release**, then create empty private roots.state and control journal parent. Preserve all descendants and running GLM. Create private registry parent immediately before atomic registration; new registered entrypoints require a complete parent/file identity, so do not invoke the L2 registered guard halfway through an incomplete transaction. Canonical VM-GUARDS checks retain their exact reviewed D3 source. Stage reviewable JSON bytes on worker; final bounded root write derives snapshot from reobserved existing mounts and rejects any discrepancy. No Storage.initialize/mount/adopt broad flow, fstab, mkdir of model volumes, package/service operations, or changed root mapping. Root must review the small pre-registration backup/metadata/atomic-registration write method in L2VM before execution; this plan supplies payload/schema, not an unreviewed executable.
5. **Validate registered identity, then import only instance.** Actual reviewed L2 binding and Storage verify both role mounts/whole roots/capacity. Actual data-role anchored writer must pass; no fixture bypass. Invoke exact historical import under same validated canonical lease and actual writer module; no Manager.run start/stop/select. Re-read instance and confirm semantic additions only; durable/recovery/GLM receipt byte hashes and container ID/image/StartedAt/command unchanged. If any mismatch STOP and use conditional rollback.
6. **Finalize reviewed control binding metadata.** Reverify the exact source tree staged in step4; no symlink, bytecode, unrelated deployment JSON or recursive repository archive. Include one-time adoption helper/guards in explicit owner manifest; root-only Python isolation `-I -B`. Verify every hash/size/mode/parent/root-device and no unexpected files. Record companion manifest outside any exact boot tree. Protect configuration with exact L2 field. Reuse dedicated suitable control key or create it once if absent using private descriptor only; never print/hash it or reuse GLM native key. Provision no inference key and perform no rotation.
7. **Bind local control for current session only.** Install exact reviewed unit substitution; `systemd-analyze verify` before daemon-reload. Inspect no unexpected overrides; daemon-reload does not start models. Start only llm-control.service, leaving it disabled initially, preserving absent model boot unit and old disabled oneshot. U1B startup reads control credential and creates systemd runtime credential; no model actions. Do not enable across reboot until reviewed `/run/llmctl` boot provisioning is supplied. Inspect localhost30000 listener and unchanged GLM immutable facts. This future step is service activation, separately approved; no such command ran here.
8. **Accept bounded control behavior.** Under explicit later permission for native key reads/probes and operations-journal write, test missing/wrong control auth, then read status/catalog. No generation or model mutation. Expect current GLM read-only identity/readiness observation; Q38 never Ready from receipt/config alone. First GET may create schema1 operations journal and update generation. Verify no active/recovery state-byte changes and exact GLM StartedAt/ID remain. Confirm separation of control/inference keys privately without output. Keep control disabled if boot persistence unresolved. No POST switch/start/stop/boot-policy in this adoption acceptance.
9. **Receipt stage only after Q38A seal** as §6, independently backed up; no runtime evidence promotion. A later Q38 live task, outside this plan, owns auth/load and eventual one-backend transition after explicit GLM release.
10. **N1S transport separately.** N1VM applies reviewed standalone helper, policy, six systemd TCP-forwarder units and narrow LAN rule. L2 changes only advertised DTO:10.156.100.60:30000 control, :30002 GLM, :30004 Q38; native listeners stay loopback. Valid policy with missing upstream does not prove ready. No firewall/transport commands here or bundled into L2VM adoption. Repeat required guards and record final current model/state hashes; finish without boot/model action.

## 8. Conditional rollback, tied to original bytes

Rollback must run under the same canonical lease and exact registered mount guards. Stop accepting control requests; if control started, stop **only llm-control.service**, never llmctl-boot or Docker. This cannot be promised harmless after a concurrent model operation; compare state/container identity before rollback and STOP on drift.

- Restore latest pre-stage instance **raw original bytes** atomically with original root uid/gid/mode; verify original SHA256. Stage1 adoption original is8a5f...; Q38 receipt stage has its own immediate pre-stage bytes. Reversing two fields is not byte rollback. Keep durable/recovery states untouched if their original c63d... hashes still match. If they changed independently, refuse automatic restore; do not resurrect stale intent.
- For receipt-only rollback, restore original receipt bytes or original absence only when target still equals this transaction's recorded posthash; retain Q38A sealed payload/evidence and existing GLM receipt.
- Remove newly created operations journal only if original absence plus exact recorded owned posthash and no later operations; otherwise preserve and return to root. Remove new control unit/config/source files only by recorded exact owned list/posthash, not recursive deletion of shared directories. Reload units after removing own unit. No backend or boot stop.
- Existing dedicated control key remains untouched. A key created by this transaction may be removed privately only with recorded exclusive creation/inode/metadata and root confirmation of no later consumer; never output key bytes/hash. Preserve any preexisting key.
- Restore registry original absence only after instance is restored and control stopped; final registered guard runs **before** removal. Then remove empty private parent created here. Run exact VM-GUARDS D3 checks afterwards with explicit data report; never leave parent-without-registry as a claimed healthy final state. Preserve N1S shared parent/policy/helper/units.
- Restore the four directory uid/gid/modes only if their inode/device and current metadata equal transaction poststate, no dependent newer registration/consumer remains and owner approves restoration; no recursive changes. Remove newly created private directories only when empty and transaction-owned. Backup/evidence remain retained on data for review.
- Immutable final checks: GLM same container/image/StartedAt/argv/port/keys, same state hashes and manual/running intent; old m6b disabled active(exited); llmctl-boot absent. If that equality fails, do not “repair” by starting/stopping/recreating anything.

## 9. Review gates and verification limits

| Gate | Status / smallest missing value |
|---|---|
| Host mount/state/container facts | PASS captured; volatile facts recheck in fresh apply |
| Existing GLM immutable reuse | PASS actual current Manager validate_identity/trusted_container/validate_reused_contract; context drift correctly rejected; no live Manager status/start called |
| Root space | WARN4.861GiB; STOP threshold4GiB |
| Exact registry/identity/control/unit proposals | Supplied outside repo in proposed/; require final L2 verifier confirmation |
| Required storage root protection | Exact four metadata changes + empty private state directory identified; owner coordination pending |
| L2 reviewed source | Pending final commit, actual-role writer tests, synchronized import closure and per-file hashes |
| Current D1 runtime+32K compatibility snapshot | Latest final L2 allowlist excludes both; explicit root/L2 compatibility contract pending, no silent re-addition/replacement |
| Q38A receipt | PASS worker mapping of supplied Q38A exact81 sealed evidence; fresh VM protected-byte/stat validation and metadata-owner release required |
| Q38B runtime proof | Exact composed source/proof contract required later; no invented OCI identity or auth receipt |
| N1S | Frozen no-argument load_policy contract available; final identical helper hash/root review pending |
| Model boot wiring | Deferred to preserve current manual intent; independent exact boot closure/volatile-dir contract needed before boot enablement |
| API/UI/generation/GPU/server tools | Not performed; UI/tools not required on API-only server |

Checks completed for this report: local source/call-graph/schema comparisons, explicit source SHA256s, one sanitized read-only inventory with focused contract/path completion, JSON parsing and report/diff/secret checks. `adoption-verification.json` records exact local Manager comparison results; `worker-verification.json` records proposal consistency checks; no broad backend suite or live acceptance is claimed. Root should review this concrete plan plus L2 source, resolve only the named seams, then issue a fresh narrowly scoped L2VM apply task. No installer framework is needed.

### Final worker checks

- `python3 -B ../verify-adoption.py`: PASS actual Manager identity/trusted-container/reused-contract checks; deliberate context drift refused.
- `python3 -B ../verify-plan.py`: PASS exact proposal JSON/stable identity/roots/mount snapshot/unit substitution/pinned81-row manifest checks.
- Q38A sealed evidence SHA256 and81 computed tuples/stat records: PASS worker mapping; no new host payload/stat proof claimed.
- Four filename-only grep credential-pattern checks across27 report files: PASS, no match values emitted; remote credential check PASS, no push.
- `git diff --cached --check`: PASS. Scope consists only of reports/evidence/proposed payloads; no production source/config changes.
- Independent source reviewer checked startup/journal side effects, write ordering, pre-registration dependency and conditional rollback. Final L2 source, Linux control/boot acceptance and all host writes remain NOT_PERFORMED.
