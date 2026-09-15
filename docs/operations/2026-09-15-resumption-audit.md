# R1: read-only resumption and ai-vm audit

## Result and scope

**Audit completed; no inference endpoint is ready.** The hardware and stored artifacts support a bounded recovery milestone. The immediate operational defect is an enabled historical boot verifier that checks out an obsolete deployment branch. The manager record also incorrectly says the stopped 30B model is active.

- Operator: Mac-Worker1; coordination: Mac-Orchestrator.
- Audit date: 2026-09-15 Europe/Ljubljana; live evidence collected from 2026-09-14 22:14:29 to 22:27:12 UTC. UTC is the preceding calendar date.
- Target: SSH alias `ai-vm`, hostname `llmserver`.
- Isolated source baseline: `717116717fe9e1fc00c6954c17d4f82941dd04ba` (`main`). Initial local working tree was clean.
- Audit branch: `milestone/r1-resumption-audit`. Only this report and its milestone index are committed; no implementation changes or push.
- VM operations were read-only: selected system/process metadata, filesystem metadata, Git inspection with `GIT_OPTIONAL_LOCKS=0`, Docker inspection, streamed reads of package metadata from stopped containers, and six HTTP GET probes. No installs, downloads, builds, service changes, model loads, inference, cleanup, Git fetch/checkout/reset, or writes of audit files on the VM.
- Credentials, private keys, auth files, process environments and complete service configurations were not dumped. Config inspection used metadata/hashes or explicitly selected non-secret fields. Login data-path checks emitted booleans only.
- Interim coordination artifacts: `../hardware-early.md` and `../progress.md`, outside the checkout.

**Evidence labels:** LIVE means checked on ai-vm during R1; REPO means read from the specified Git revision; HISTORICAL means a prior report, without rerunning its tests; INFERENCE means a conclusion drawn from those observations. NOT_TESTED identifies remaining verification explicitly.

## 1. Repository and milestone reconciliation

### Relevant Git revisions

Remote-tracking refs were inspected as provided in the isolated clone; no fetch or push was performed. They are snapshot evidence, not proof that GitHub has no newer commits.

| Ref | Commit | Meaning |
| --- | --- | --- |
| Baseline `main` / `origin/main` | `717116717fe9e1fc00c6954c17d4f82941dd04ba` | M9D merge and pre-M9E handoff |
| `origin/milestone/m9d-large-model-feasibility-plan` | `c3131db02ace63ffca6a8180d9d3ddea5094d2ae` | Large-model selection plan |
| `origin/milestone/m9e-large-model-poc` | `e1845c393fb4535b2a929ab6d67ae540f631b192` | MiniMax download and failed proof |
| `origin/milestone/m9e-r1-minimax-runtime-remediation` | `1f90c3a1c8561195b9b6009c210270f1431234da` | Container dependency repair, further failure |
| `origin/milestone/m9e-r2-sm120-minimax-remediation` | `bee433395f07fa5c971a555416694185c3a4eabd` | SM120 investigation; no working MiniMax API |
| `origin/milestone/m9f-offline-resilience-mixed-memory-plan` | `a653144acf354286b739ded1dff547548ae8cb5d` | Offline/mixed-memory plan; four commits ahead of baseline, zero behind |

Read first: `AGENTS.md`, `docs/current-state.md`, pre-M9/B/C/D/E handoffs, `ROADMAP.md`, architecture, operations and API contract. Later branch reports and added M9F architecture documents were then read with `git show`; they were not merged into this audit branch.

### Live checkouts and pre-existing dirty paths

| VM checkout | HEAD / branch | Dirty paths (preserved) |
| --- | --- | --- |
| `/data/services/mixed-memory-llm-api-server` | `e4907b96a555b9a7a1580f4dc932da51b5e2f3a9`; `milestone/m6b-nvidia-container-toolkit-install` | `reports/m3-root-disk-guard.md`; `reports/m4b-docker-containerd-install.md`; `reports/m6b-nvidia-container-toolkit-install.md` |
| `/home/user/codex-bootstrap/mixed-memory-llm-api-server` | `34ab5a4a8dcfb5bfb18ad0a1944ee68456c37ec9`; `milestone/m2-data-disk-setup` | `reports/m2-data-disk-setup.md` |
| `/home/user/github-access-test/mixed-memory-llm-api-server` | `e3a62ddeb0ecc19ec96ad5c1a039ca7a38cf4752`; `main` | Clean |

Bounded discovery used documented `/data/services` and `/data/build`, then `.git` directories under those roots and `/home/user` to depth four. No additional worktree is registered in the documented deployment checkout. This does not exclude repositories outside the bounded search. **`scripts/llmctl` is absent in the live M6B checkout.** Do not follow the current-state recovery command there without first reconciling deployment ownership/revision.

### Architecture and remaining work

REPO: `scripts/llmctl` plus declarative model/runtime profiles is the intended control surface. SGLang has implemented smoke/30B lifecycle support. KTransformers and ik_llama profiles exist but are experimental; their presence is not an implemented, tested lifecycle integration. KTransformers' profile still says `openai_compatible: false`, although the later experiment uses an SGLang-KT API frontend. Capabilities need review per runtime path.

LIVE: compose deployments and `active.json` live outside Git under `/data/services/llm-manager`. Persistent weights, caches, container storage and logs are on `/data`. One model/backend should run at a time. Host bindings are localhost-only; the processes' `0.0.0.0` arguments apply inside Docker bridge networks, not to the host publication.

HISTORICAL: M0–M9D are incorporated in baseline main. M9E downloaded MiniMax; initial missing `libnuma.so.1` was repaired in M9E-R1. The next failure was an SM90/SM100 assertion on this SM120 workstation. M9E-R2 did not establish a working path. M9F then proposed Qwen3.5-397B-A17B-FP8 mixed-memory preflight, followed by proof, true long-context testing, memory/RAG, model routing, external agent integration and an authenticated API front door.

Stale assumptions/gates:

- README's “early bootstrap” status, main's “no large model downloaded”, and handoff's “30B healthy” are stale.
- The old M5A STOP text is contradicted by completed driver/toolkit milestones. Its historical approval wording does not undo installed hardware support.
- M9F's “keep the 30B service running” assumption is false today.
- Roadmap numbering differs: baseline M10–M12 focuses on front door/benchmarks/operations; M9F uses M9G–I then M10–15 for memory, routing and agent/front-door work. Use task names and acceptance criteria, not milestone number alone.
- Main's real-model `restart --yes` remains explicitly unsupported in code despite broader lifecycle descriptions; a documentation statement does not add that capability.
- The user's current request supersedes older planning-only/fresh-context approval gates for subsequent bounded tasks. **R1 itself remains strictly read-only.** Storage guards, tested SM120 compatibility, preservation of work, one-active-model policy and authenticated exposure constraints remain technical requirements.
- This VM remains inference/API-only. Browser, scraper, human UI and agent tool execution belong on the other VM/client. M9F agent/RAG ideas are future architecture, not installed capabilities.

## 2. Hardware and runtime inventory

### LIVE hardware

| Item | Observed |
| --- | --- |
| OS / kernel | Ubuntu 24.04.4 LTS; Linux `6.8.0-134-generic`, x86_64, KVM |
| CPU identity | AMD Ryzen Threadripper PRO 9985WX 64-Cores |
| Guest CPU topology | 112 online vCPUs; 7 virtual sockets × 16 cores × 1 thread; 7 NUMA nodes |
| RAM | `924,616,132 kB` total = about 881.8 GiB; sample `918,274,704 kB` available = about 875.7 GiB |
| Swap | `3,083,260 kB` total and free; unused |
| CPU instruction flags | AVX2, AVX512F, AVX512 VNNI, AVX512 BF16 present; AVX512 FP16 and AMX tile absent |
| GPU 0 | NVIDIA RTX PRO 6000 Blackwell Workstation Edition; 97,887 MiB total / 97,249 MiB free |
| GPU 1 | Same model; 97,887 MiB total / 97,217 MiB free |
| NVIDIA driver / compute capability | `595.71.05`; both GPUs `12.0` (SM120) |
| Boot time | 2026-09-14 21:34:44 UTC |

RAM/VRAM availability is a point-in-time sample. Guest NUMA nodes each expose roughly 126 GiB. **Do not mistake seven virtual sockets for seven physical CPUs.** SMBIOS reports one virtual 896 GB RAM device with speed unknown. The user's eight-channel DDR5 platform is a relevant design input, but physical populated channels, DIMM speed and sustained bandwidth are NOT_TESTED from this guest. No memory-bandwidth or NUMA benchmark was run. Physical host access was outside scope.

INFERENCE: approximately 876 GiB available system RAM is a major resource for CPU/expert offload. A candidate exceeding aggregate VRAM is not automatically infeasible. Weight placement, staging/duplicate copies, KV cache, NUMA locality, CPU kernel support, PCIe transfer and bandwidth still need measured budgets. Capacity alone does not prove usable speed or a compatible quantization path.

### LIVE installed/runtime identities

| Component | Verified identity / method |
| --- | --- |
| Docker | `29.6.1`; Docker Root Dir `/data/docker`; storage driver `overlayfs`; default runtime `runc`; NVIDIA runtime registered |
| containerd | `v2.2.5`, commit `e53c7c1516c3b2bff98eb76f1f4117477e6f4e66`; persistent root `/data/containerd/root`, state `/run/containerd` |
| Compose | `v5.3.0` |
| NVIDIA Container Toolkit | CLI `1.19.1`; toolkit/base/libnvidia-container packages `1.19.1-1` |
| Host driver package | `nvidia-driver-595-open 595.71.05-0ubuntu0.24.04.1` |
| Host Python | `3.12.3`; selected inference packages absent from system Python distribution metadata |
| Host inference binaries | `nvcc`, `llama-server`, `llama-cli`, `ik_llama`, `sglang`, `vllm`, `ktransformers`, `kt` not found on inspected nonlogin PATH |
| SGLang stopped image | `lmsysorg/sglang:v0.5.14-cu130`; package metadata `sglang 0.5.14`; torch static version `2.11.0+cu130`, CUDA `13.0` |
| MiniMax stopped image | `local/minimax-m3-ktransformers:0.6.3-post1-r1`; `sglang-kt 0.6.3.post1`, `kt-kernel 0.6.3.post1`, `sgl-kernel 0.3.21`, `transformers 5.13.0`, `flashinfer-python 0.6.3`; torch metadata `2.9.1`, static build version `2.9.1+cu128`, CUDA `12.8` |

The NVIDIA-SMI banner reports CUDA **13.2 driver capability**, not an installed host CUDA Toolkit. No host Toolkit was found in selected package/PATH checks. Arbitrary private virtual environments were not scanned. Container packages were read through `docker cp CONTAINER:.../METADATA -` or `torch/version.py` into a memory-only tar reader: no container was started and no Python framework import or kernel ran.

Image identities (LIVE local image store; not registry revalidation):

- SGLang ID/digest: `sha256:5027e95bf6ec536856b1b52a91d1f35ff5c564ab83e8a94758a169ff09bb8df3`.
- MiniMax R1 ID/digest: `sha256:362917ee2a4188bdb827c5b97d0f9a8a5c5dd1663b2ea43ad1ef6daa55a0a768`.
- MiniMax label references KTransformers source commit `cb9f47d142a507cac5d74450b30463d2e8d1cf58`; this is build-label provenance, not proof of a native source checkout.
- Additional retained images: initial MiniMax `0.6.3-post1`, SGLang `v0.5.14-cu130-runtime`, `nvidia/cuda:13.2.1-base-ubuntu24.04`, `hello-world:latest`. No pulls or deletions.

## 3. Storage, model files and headroom

### LIVE storage

| Filesystem | Size bytes | Used bytes | Available bytes |
| --- | ---: | ---: | ---: |
| `/` ext4, `/dev/mapper/ubuntu--vg-ubuntu--lv` | 15,186,501,632 | 9,194,246,144 | 5,198,483,456 (4.84 GiB) |
| `/data` ext4, `/dev/sdb1` | 2,163,348,520,960 | 647,146,545,152 | 1,406,234,140,672 (about 1.28 TiB) |

`/data` is separately mounted `rw,relatime`, label `AI_DATA`, UUID `8daf56f1-5649-4163-9d87-919c2d271875`. `require-data-mounted.sh` passed with exit 0. Required directories exist. `/etc/fstab` uses that UUID with `defaults,nofail,x-systemd.device-timeout=30`. Root inodes are 18% used; data inodes about 1% used. No quota mount options are visible and `quota` is not installed; per-user/project/storage-backend quotas are NOT_TESTED, not asserted absent.

Bounded allocated-byte directory totals (`du -sx --block-size=1`):

| Path | Allocated bytes |
| --- | ---: |
| `/data/models` | 506,380,374,016 |
| `/data/hf-cache` | 36,880,384 |
| `/data/docker` | 4,784,128 |
| `/data/containerd` | 140,721,016,832 |
| `/data/build` | 327,680 |
| `/data/logs` | 1,232,896 |
| `/data/services` | 6,365,184 |
| `/data/backups` | 4,096 |

Most container data is in containerd, explaining the small Docker directory; do not budget from `/data/docker` alone or sum image virtual sizes. `/data/backups` had no files within depth two: no operational rollback archive was established by this audit.

### Guards and limitations

- Guard defaults: root STOP below 4 GiB, WARN below 6 GiB; high-risk path WARN at 512 MiB and STOP at 2,048 MiB; suspicious model/archive threshold 128 MiB. **Current root space is in the warning range.** A next build/install must preserve margin and stop if guards fail.
- Full root guard was **NOT_TESTED**. Source inspection found a report write (default tracked report), `/tmp/root-disk-guard-require-data-mounted.*` writes, `sudo -k`, and a broad root scan. Even `--report /dev/stdout` would not remove all side effects. The audited VM/local guard SHA-256 hashes match.
- `verify-docker-storage.sh` writes reports and invokes that guard; the GPU verifier runs a container; `llmctl doctor` invokes them. Live verifiers submit inference. None was run in R1.
- Direct read-only equivalents confirmed separate mount/storage roots, required directories, root/data free space, absent `/var/lib/docker` and `/var/lib/containerd`, and ten expected AI/Hugging Face data-path variables (boolean comparisons only).
- Targeted root usage: `/var/log` 410,697,728 bytes; old bootstrap 1,298,432 bytes; `/home/user/.cache` 4,096; `/tmp` 81,920; `/var/tmp` 45,056; `/opt` 16,384; `/srv` 4,096. `/root/.cache` absent. This bounded check does not certify all root paths clean.
- Docker daemon log settings are `json-file`, `max-size=100m`, `max-file=5`. Existing container logs are under `/data/docker/containers`; mounted application logs use `/data/logs`.
- Docker/containerd have no explicit `RequiresMountsFor=/data` in their live unit properties. With `nofail` on `/data`, boot behavior when the data disk is missing is an unresolved storage risk. The M6B verifier itself has an implicit data mount dependency through its working directory. Mount-loss behavior was not tested.

Next-task budget recommendation (INFERENCE): preserve all existing weights/images, calculate actual free space before each operation, reserve download/cache/build/unpack/rollback peaks separately and retain at least 20% of current data filesystem capacity as an operational reserve unless the orchestrator selects another explicit budget. This is a proposed headroom policy, **not an installed quota**. M9D's 500–650 GB reservation was for its original MiniMax work, not unused reserved capacity today. RAM planning must also reserve OS/service space and account for copies/KV cache; no large-model fit is certified here.

### Model inventory

All inventoried weight files are top-level safetensors in these directories. Ancillary configuration, tokenizer, license and model index files also exist; none is an authentication file.

| Model directory | Weight files | Weight bytes | Allocated directory bytes | Current state |
| --- | ---: | ---: | ---: | --- |
| `/data/models/qwen3-0.6b-smoke` | 1 | 1,503,300,328 | 1,519,300,608 | Retained; stopped |
| `/data/models/qwen3-30b-a3b-instruct-2507` | 16 | 61,066,575,656 | 61,084,520,448 | Selected in stale state; stopped |
| `/data/models/minimax-m3-mxfp8` | 31 | 443,749,077,256 | 443,776,548,864 | Failed experiment retained; stopped |

Index-to-filename checks found every referenced shard (16/16 and 31/31), with no extra top-level weight shards. This is a presence check, not checksum/integrity verification. MiniMax index `metadata.total_size` is 451,543,283,200 bytes, different from file-size sum; index totals alone must not be used as downloaded-byte verification. No full-weight hashing or payload validation was done.

Exact weight filenames/sizes are in the appendix below.

## 4. Services, configuration ownership and rollback

### LIVE lifecycle

| Container | State / exit | Last finish UTC | Host publication | Restart policy |
| --- | --- | --- | --- | --- |
| `sglang-qwen3-30b-a3b-instruct-2507` | Exited / 0 | 2026-07-09 07:31:24 | `127.0.0.1:30001` → 30000 | `no` |
| `sglang-smoke-qwen3-0.6b` | Exited / 0 | 2026-07-05 15:04:04 | `127.0.0.1:30000` → 30000 | `no` |
| `minimax-m3-mxfp8-poc` | Exited / 137 | 2026-07-08 20:32:41 | `127.0.0.1:30002` → 30000 | `no` |

All have `OOMKilled=false`; exit 137 alone is not proof of OOM. All use Compose project `compose`, working directory `/data/services/llm-manager/compose`, bridge network `compose_default`, read-only `/data/models` mounts and writable cache/log mounts. Future compose operations must target the reviewed service/profile: a project-wide command can affect sibling deployments.

30B recorded launch: TP 2, context 32,768, static memory fraction 0.75. No `--tool-call-parser` or `--api-key` argument is present. MiniMax recorded launch: TP 2, context 8,192, static fraction 0.55, `mxfp8`, CPU inference 64, threadpool count 7, GPU experts 8, MiniMax tool/reasoning parsers. Those values describe configurations, not successful serving or recommended tuning.

Docker/containerd are enabled and running; NVIDIA persistence and QEMU guest agent are running. No failed systemd units were reported. No inference auto-start unit was found in the bounded service inventory; all model containers have restart policy `no`. QGA process activity is not a fresh Proxmox host ping test.

**Boot verifier defect:** `/etc/systemd/system/m6b-post-reboot-verify.service` is enabled, active/exited, `Type=oneshot`, `User=user`, `RemainAfterExit=yes`, `WantedBy=multi-user.target`. It ran from 21:34:56 to 21:35:19 UTC this boot. Its command is `/data/services/m6b-post-reboot/m6b-post-reboot-verify.sh`; that script:

- enters the deployment repo and runs `git checkout milestone/m6b-nvidia-container-toolkit-install` at line 43;
- runs report-writing root guards at lines 46 and 83 and the GPU container verifier at line 48;
- deletes/recreates its PASS/STOP markers rather than making an existing PASS marker a one-time completion gate.

LIVE code and unit activity support the INFERENCE that this verifier caused the old checkout and likely the modified reports. Prior history is not reconstructed completely. It must be retired or redesigned in a subsequent authorized task before relying on reboot persistence; do not execute it as an audit check.

`active.json` says profile `qwen3-30b-a3b-instruct-2507`, runtime `sglang`, status `active`, started `2026-07-08T20:34:01Z`, endpoint `http://127.0.0.1:30001/v1`. Docker is exited and the API refuses connections. **The record is stale by the current manager's documented semantics.** `llmctl status` itself was not run because the live checkout lacks the script; state was derived from selected record fields plus Docker/socket/HTTP evidence.

### Configuration identities

| Path under `/data/services/llm-manager/` | Owner/group, mode | SHA-256 |
| --- | --- | --- |
| `compose/sglang-qwen3-30b.compose.yml` | `user:ai`, 0664 | `1e18f9a575a57657dee24ce643fd1d3a6cdd3c6aa0d6de7b7266b409f0f56bfd` |
| `compose/sglang-smoke.compose.yml` | `user:ai`, 0664 | `e550f0c00f0d08d0445b45b8e7eed683449eacb15c1c241385feb8dfb0dd5050` |
| `compose/minimax-m3-poc.compose.yml` | `user:ai`, 0664 | `b28767cf49321fc7ca294f05d1400e66a6ade88abb81a836e3b0f4269afde9e2` |
| `active/active.json` | `user:ai`, 0664 | `bd34931c6ed9cc0c887795dcefaebd65b4ceec95f061374938b09443a5c47a78` |

Data model/cache/build/services/backups directories are `user:ai` 0775; `/data/logs` is `user:user` 0755; Docker is `root:root` 0710; containerd is `root:root` 0711. Secrets-directory metadata only: `user:ai` 0770; its contents were not inspected. Docker/containerd/fstab config files are `root:root` 0644. Boot unit is root-owned 0644; verifier script is `user:user` 0755. Configuration write ownership and service execution ownership should be preserved or intentionally revised in the next task.

### Rollback reality

HISTORICAL M9E-R1 recovery stopped failed MiniMax and used `llmctl start --yes` to restore 30B. The current image, weights and compose file are still present, so they are a viable recovery target. **That recovery procedure is not directly runnable from the current M6B checkout, and no rollback was tested in R1.** No active/history archive was found within the inspected active-state directory.

Before subsequent mutation, preserve all dirty files and capture a deployment/config manifest under `/data/backups` with restricted handling for any secrets. Use a new isolated deployment checkout/release path or reviewed reconciliation; never reset/clean existing checkouts. Pin existing image identities and retain a documented route back to 30B or to a stopped state. Avoid live VFIO snapshots: historical Proxmox reports say migration/snapshot support failed; offline snapshot feasibility remains a host-side, NOT_TESTED item. Historical correctable PCIe AER warnings also need monitoring during later load tests; no Proxmox access occurred in R1.

## 5. API readiness and exposure

At 2026-09-14 22:16:22 UTC, these read-only probes all returned **connection refused (Errno 111)**:

| Port | `GET /health` | `GET /v1/models` |
| --- | --- | --- |
| 30000 smoke | Refused | Refused |
| 30001 30B | Refused | Refused |
| 30002 MiniMax | Refused | Refused |

Privileged `ss -ltnp` found only SSH on wildcard IPv4/IPv6 port 22, local systemd-resolved DNS listeners and containerd's localhost listener on 34205. No model port, proxy or API listener was found. `ufw status` is inactive. This is not an audit of upstream firewall, Proxmox rules or remote reachability; no external API exposure is established by these observations.

No inference request, model switch or warmup was issued. `/health/live`, `/health/ready`, chat, streaming and tool calls are NOT_TESTED. Current API contract requirements are future behaviors, not evidence of an available agent endpoint. No `--api-key` launch argument was found; other auth mechanisms were not asserted absent because secret values were not inspected.

## 6. Recommended bounded next tasks

### Next deployment milestone: recover one reproducible localhost 30B endpoint

Use the already stored 30B image/weights to establish a reliable baseline while the orchestrator separately refreshes flagship model/runtime research. This minimizes extra storage and version changes and makes later agent tests attributable to a known backend. It is a recommendation for a subsequent task; **nothing in this section was executed in R1**.

Scope:

1. Preserve every dirty path above, capture config/image/state identities and reconcile the deployed source revision. Keep existing checkouts intact; stage the selected manager revision under `/data/services`.
2. Retire or correct the M6B boot verifier's branch-changing behavior with an explicit rollback copy. Resolve data-mount ordering/guard behavior before adding model auto-start. Correct stale manager state through reviewed lifecycle logic.
3. Run real mount/root/storage guards before and after mutation, directing reports/temp artifacts to `/data`; stop on guard failures. Root space remains a warning requiring headroom accounting.
4. Start only the retained 30B profile on `127.0.0.1:30001`, using reviewed image identity and compose service scope. Keep MiniMax and smoke stopped and retain their files/images.
5. Run basic chat/streaming and lifecycle acceptance; record startup duration and resources. Keep parser/auth/agent changes separately reviewable if they require another deployment revision. No new flagship weights are required for this recovery milestone.

Recovery acceptance:

- Deployment HEAD and dirty-path preservation are documented; `scripts/llmctl` is available at the chosen release path. Boot verification no longer changes that revision or rewrites unrelated milestone reports.
- `/data` identity/storage roots pass, root remains above the hard threshold with documented build/runtime margin, no AI data lands on root, and only one backend owns GPU/API service state.
- `llmctl status` transitions through starting to active only after health/model-list readiness; stopped/exited conditions are represented correctly. Failure returns a clear nonzero result within a declared startup deadline (current manager default is 20 minutes).
- `/health` and `/v1/models` pass repeatedly; expected served-model ID appears; short chat and SSE completion pass; invalid model gets a client error. Record finish reasons, token usage, TTFT, output rate, RAM and per-GPU VRAM.
- A controlled stop/start and recovery from a failed start pass using reviewed supported commands. Do not assume real-model `restart --yes` works. The selected boot policy is documented; if auto-start is included, a separately scheduled controlled reboot must prove data ordering, revision stability, readiness and failure recovery.
- Host publication remains localhost-only. No model/image deletion, uncontrolled pulls, global Toolkit upgrade or Docker/containerd restart is needed unless the subsequent task explicitly includes and tests that change.

### Eventual agentic endpoint: explicit acceptance tests

The endpoint must return structured tool requests; the external agent/client executes approved tools. Chat success alone is insufficient.

1. Pin a model/runtime/chat-template/tool-parser combination and document supported `tools` and `tool_choice` behavior. Test at least 20 deterministic fixtures spanning no-tool answers, one tool call, multi-turn tool-result continuation and malformed/unsupported requests. Report counts and failures; require all protocol fixtures to pass before advertising tool support.
2. Validate JSON arguments against each supplied schema, tool name and call ID, finish reasons, required fields and tool-result association. Confirm the answer continues after a client-provided tool result without duplicate execution. Test forced/automatic/none modes only where explicitly supported; unsupported options must return a clear error.
3. Test both non-streaming and SSE: fragmented tool arguments reassemble into valid JSON, completion terminates correctly, cancellation/timeouts free request capacity, and malformed JSON does not crash or poison the next request.
4. Test actual token-counted 8K and 16K contexts at concurrency one, then a small bounded concurrency test. Record usable limits, RAM/VRAM/KV pressure, TTFT and sustained output rate. The historical “16K” case had only 3,518 prompt tokens; it is not 16K-token evidence. Agree performance targets per model; lower mixed-memory throughput may be acceptable for quality.
5. For access from the separate agent VM, define the transport and auth policy first. Reject missing/wrong API keys, accept the valid credential without logging it, enforce model allowlist/request limits and verify firewall/TLS or tunnel boundaries. Test from allowed and disallowed paths. The backend should remain localhost-bound behind the chosen access layer.
6. Prove offline use with all selected assets already local, including tool parsing/tokenizer assets: no request-triggered downloads, no implicit model load/switch and no browser/scraper/tool execution on ai-vm. Health endpoints must remain lightweight and must not load a model implicitly.
7. Verify backend failure produces a bounded, clear unavailable response; restore the known 30B profile using retained artifacts and re-run readiness/tool protocol checks. Report NOT_TESTED capabilities rather than advertising unsupported agent behavior.

### Subsequent mixed-memory research/proof

Refresh official model cards, licenses, revisions, quantizations and release support for current flagship open-weight candidates. Treat the old Qwen3.5/MiniMax/GLM shortlist as history, not a September ranking. Compare KTransformers/SGLang-KT and ik_llama/GGUF paths with actual SM120 kernel coverage and this CPU's instructions/NUMA layout. Include the user-prioritized eight-channel DDR5 bandwidth in physical-host verification and measured CPU-offload tests.

Select one bounded runtime preflight before a large download, pin the full version matrix, prove a tiny kernel/model case on both GPUs and check tool parsing. Then budget retained weights plus new weights/cache/unpacking/runtime/KV/RAM copies and propose one low-context, one-request large-model proof with 30B rollback. MiniMax's historical failure was kernel-path support, not insufficient storage; current upstream support was NOT_TESTED in R1 and must be refreshed before repeating that attempt.

## 7. Checks, evidence commands and limitations

| Check | Result |
| --- | --- |
| Repository/handoff/late-branch reconciliation | PASS; main and live deployment are stale relative to later work |
| CPU/RAM/GPU/driver inventory | PASS; physical DDR5 layout/bandwidth NOT_TESTED |
| Data mount guard | PASS, exit 0 |
| Full root/Docker/GPU verifiers | NOT_TESTED; inspected side effects and used bounded read-only checks |
| Root free space | WARN, about 4.84 GiB; no cleanup performed |
| Model filename/index inventory | PASS presence only; payload hashes/integrity NOT_TESTED |
| Runtime metadata | PASS static package/image identity; imports/kernels NOT_TESTED |
| Services and API readiness | FAIL readiness: all backends stopped, six GETs refused |
| Deployment lifecycle consistency | FAIL: obsolete live branch, missing manager script, stale active record, enabled historical branch-changing boot unit |
| Agent/tool/streaming/context/auth/offline behavior | NOT_TESTED |
| Current flagship/upstream compatibility ranking | NOT_TESTED; reserved for subsequent scoped research, not inferred from July reports |
| Implementation/service mutation in R1 | None |

Representative read-only commands (SSH used `BatchMode=yes`, `ConnectTimeout=10`, `StrictHostKeyChecking=yes`):

```text
git status --short; git rev-parse HEAD; git for-each-ref ...
git show origin/milestone/m9f-offline-resilience-mixed-memory-plan:<document>
GIT_OPTIONAL_LOCKS=0 git -C <known-repo> status --porcelain=v1 --untracked-files=all
GIT_OPTIONAL_LOCKS=0 git -C <known-repo> rev-parse HEAD
lscpu <selected fields>; free -h; selected /proc/meminfo and NUMA meminfo
nvidia-smi --query-gpu=index,name,memory.total,memory.free,driver_version,compute_cap --format=csv,noheader
findmnt -rn -T /data -o TARGET,SOURCE,FSTYPE,OPTIONS; df -B1 / /data; df -i / /data
scripts/common/require-data-mounted.sh
sudo -n docker ps -a --format ...
sudo -n docker inspect <known-container>  # parsed allowlist only, no config/environment dump
sudo -n docker image inspect <known-image>  # selected identity/version fields only
sudo -n docker cp <stopped-container>:<known-package-METADATA-or-version.py> -
systemctl list-units --all --type=service; systemctl show <known-unit> --property=<safe-fields>
sudo -n ss -ltnp; sudo -n ufw status
du -sx --block-size=1 <documented-data-paths-or-selected-root-paths>
```

No global filesystem/secret scan was run on the VM. No process environment, auth file or log body was needed. HTTP probing used Python `urllib.request.urlopen` with three-second timeouts on localhost health/model-list paths only. Read operations may generate ordinary SSH/sudo access logs or filesystem access times; no operational or deployment state was intentionally changed.

Final verification at **2026-09-14T22:27:12Z**: all 48 report weight filenames and byte sizes matched a fresh bounded live inventory; all four compose/active-state hashes above remained unchanged; all three inference containers remained exited; all three inspected Git HEADs and dirty-path sets remained unchanged. The three dirty deployment reports have modification times between 21:35:16 and 21:35:19 UTC, before R1 began; the old bootstrap report's modification time is 2026-07-02. This further supports the boot-verifier explanation without claiming a complete historical reconstruction.

Local delivery verification: `git diff --check`, an exact inventory comparison and a grep-based value-shaped secret check over the two new report files passed. Remote URL inspection found no embedded credentials; no push was attempted. No implementation tests were needed for this documentation-only commit; service acceptance tests remain explicitly NOT_TESTED above.

## Appendix: exact weight filenames and byte sizes

### `/data/models/qwen3-0.6b-smoke`

| Filename | Bytes |
| --- | ---: |
| `model.safetensors` | 1,503,300,328 |

### `/data/models/qwen3-30b-a3b-instruct-2507`

| Filename | Bytes |
| --- | ---: |
| `model-00001-of-00016.safetensors` | 3,998,893,112 |
| `model-00002-of-00016.safetensors` | 3,999,974,192 |
| `model-00003-of-00016.safetensors` | 3,997,360,832 |
| `model-00004-of-00016.safetensors` | 3,999,975,056 |
| `model-00005-of-00016.safetensors` | 3,999,975,400 |
| `model-00006-of-00016.safetensors` | 3,999,975,400 |
| `model-00007-of-00016.safetensors` | 3,999,975,472 |
| `model-00008-of-00016.safetensors` | 3,997,362,064 |
| `model-00009-of-00016.safetensors` | 3,999,975,408 |
| `model-00010-of-00016.safetensors` | 3,999,975,400 |
| `model-00011-of-00016.safetensors` | 3,999,975,408 |
| `model-00012-of-00016.safetensors` | 3,987,924,896 |
| `model-00013-of-00016.safetensors` | 3,999,975,088 |
| `model-00014-of-00016.safetensors` | 3,999,975,400 |
| `model-00015-of-00016.safetensors` | 3,999,975,400 |
| `model-00016-of-00016.safetensors` | 1,085,307,128 |

### `/data/models/minimax-m3-mxfp8`

| Filename | Bytes |
| --- | ---: |
| `model-00001-of-00031.safetensors` | 8,303,674,712 |
| `model-00002-of-00031.safetensors` | 16,098,618,792 |
| `model-00003-of-00031.safetensors` | 16,098,618,872 |
| `model-00004-of-00031.safetensors` | 16,098,619,208 |
| `model-00005-of-00031.safetensors` | 16,098,619,672 |
| `model-00006-of-00031.safetensors` | 16,098,619,128 |
| `model-00007-of-00031.safetensors` | 16,098,619,848 |
| `model-00008-of-00031.safetensors` | 16,098,619,768 |
| `model-00009-of-00031.safetensors` | 16,098,619,848 |
| `model-00010-of-00031.safetensors` | 16,098,619,800 |
| `model-00011-of-00031.safetensors` | 16,098,619,800 |
| `model-00012-of-00031.safetensors` | 16,098,619,768 |
| `model-00013-of-00031.safetensors` | 16,098,619,800 |
| `model-00014-of-00031.safetensors` | 16,098,619,768 |
| `model-00015-of-00031.safetensors` | 16,098,619,768 |
| `model-00016-of-00031.safetensors` | 16,098,619,768 |
| `model-00017-of-00031.safetensors` | 16,098,619,768 |
| `model-00018-of-00031.safetensors` | 16,098,619,768 |
| `model-00019-of-00031.safetensors` | 16,098,619,768 |
| `model-00020-of-00031.safetensors` | 16,098,619,760 |
| `model-00021-of-00031.safetensors` | 16,098,619,768 |
| `model-00022-of-00031.safetensors` | 16,098,619,768 |
| `model-00023-of-00031.safetensors` | 16,098,619,768 |
| `model-00024-of-00031.safetensors` | 16,098,619,768 |
| `model-00025-of-00031.safetensors` | 16,098,619,768 |
| `model-00026-of-00031.safetensors` | 16,098,619,768 |
| `model-00027-of-00031.safetensors` | 16,098,619,768 |
| `model-00028-of-00031.safetensors` | 506,815,888 |
| `model-00029-of-00031.safetensors` | 12,246,524,552 |
| `model-00030-of-00031.safetensors` | 2,063,975,528 |
| `model-00031-of-00031.safetensors` | 2,063,975,528 |
