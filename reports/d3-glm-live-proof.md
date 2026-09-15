# D3 — GLM-5.3 live proof and agent profile

Date: 2026-09-15. Worker: Mac-Worker1; VM operations owned by main D3 through `ssh ai-vm`.
**8K and 32K live load/fit/generation: PASS. Independent stream/nonstream tool continuation: PASS. Full A1 and real V1/OpenCode: NOT_TESTED; overall READY pending.**
The 32K profile remains running/manual. D3 released request ownership to root/Worker2 V1 and will not generate, stop/restart/switch or tune until that client lease is explicitly released back.

## Evidence and coordination boundary

Evidence: [preparation dry run](d3-evidence/prepare-dry-run.json), [applied result](d3-evidence/prepare-result.json), [protection](d3-evidence/protection-check.json), [template](d3-evidence/embedded-template.json), [8K summary](d3-evidence/8k-summary.json), [API probes](d3-evidence/8k-probe.json), [post-generation resources](d3-evidence/8k-generation-snapshot.json), and [8K stop / 32K select](d3-evidence/8k-stop-32k-select.txt).
Final 32K evidence: [load](d3-evidence/load-32k.json), [ordinary API probes](d3-evidence/32k-probe.json), [tool/continuation probes](d3-evidence/32k-tool-probe.json), [post-generation resources](d3-evidence/32k-generation-snapshot.json). Task-root `v1-handoff.md` and `client-lease.json` record the active V1 request lease.
Task-root `coordination-output.md` records exclusive VM mutation handoff from F1D, no inference containers running and downloader inactive/unloaded at preparation. No Qwen client lease exists in this handoff. SGLang remains blocked; its auth fixture has not passed. No Qwen/SGLang start is authorized by that blocked fixture.
Root approved storage-only commit `7b541017c3e1b2bda80676bcd31bc87d0a4507bc`, integrated it as `83668a913bb1bb2f4f5629fc6af7169ab3aa0658`, and authorized launch from the reviewed worker source. Earlier intermediate patch identities are superseded.

## Exact identities and storage gates

| Item | Recorded identity / result |
| --- | --- |
| `/data` | ext4, UUID `8daf56f1-5649-4163-9d87-919c2d271875`; exact mount gate PASS before preparation |
| `/data/models-large` | ext4, UUID `a6d4ab58-84e1-4e48-9a67-13ad1c6f6e0a`; exact mount gate PASS before preparation |
| Root free before preparation | 5,228,605,440 bytes: WARN below 6 GiB, above STOP threshold 4 GiB; volatile snapshot |
| Model | `unsloth/GLM-5.3-GGUF@346b3591c7f28d1a23716f97a065ecf12ec14771`, community `UD-Q4_K_XL` |
| Payload | Exactly 11 GGUF shards, 467,289,116,837 bytes, in `/data/models-large/glm-5.3-ud-q4-k-xl/UD-Q4_K_XL` |
| Load entry | `GLM-5.3-UD-Q4_K_XL-00001-of-00011.gguf`; all 11 siblings required |
| R2 manifest SHA256 | `8e7cb419a9dea83f1978f936455cedace1b964cbbb3580f7be191998f6a999d3` |
| Runtime source | llama.cpp `v0.4.1`, commit `b29c606e28a01b1bc8c1351026a0fa6e616bf6c4` |
| Actual recorded version | `0.4.1-dev (build 62, commit b29c606)` |
| Image tag | `local/llama-cpp:v0.4.1-b29c606-cu132-sm120-d1` |
| Image ID | `sha256:6866856c573d69d504f82265321b182f631a7b3912a1ed1b4efbf893729d4e62` |
| Image contract | ENTRYPOINT `/opt/llama/llama-server`, `LD_LIBRARY_PATH=/opt/llama`; D1 build target `120a-real` |

Exact mount UUIDs and the 4 GiB stop threshold were checked again by the preparation helper before mutation and at its final guard. The helper invoked `require-data-mounted.sh` and `root-disk-guard.sh`; its report and explicit TMPDIR were under `/data`. Build/temp/evidence root: `/data/build/d3-glm53-20260915`. These checks do not establish future free space; repeat guards around live deployment work.

## Completion, sealing and protected control

Acquisition status: `/data/build/d1-glm53-20260915/evidence/acquisition-status.json`; owner unit `d1-glm53-acquire-20260915-d1b-p4.service`. Final downloader record says `PASS_ALL_11_COMPUTED_SHA256`, 11 verified shards and 467,289,116,837 verified bytes. D3 validated every acquisition-computed SHA256 and exact size against immutable R2, plus exact revision, directory contents and supplied filesystem identity/stat evidence, while holding the free acquisition lock. Completion was not inferred from file size or process exit alone.
**Hash scope: validated downloader-computed hashes; D3 did not independently reread/hash the full payload.** D3 read the first shard's metadata separately for the template check below. The recorded status SHA256 is `016265905a10ba18084f93aec1b0b004c5cfb4bc9549f00a3664ceb293695c05`.
Before/after evidence preserves each shard's device, inode, size, mtime and single-link identity. Intentional sealing changed owner/mode/ctime: model directories root `0555`, all 11 files root `0444`, acquisition lock root `0600`. Ordinary-user write checks denied both directories and all 11 files.

| Protected artifact | Recorded result |
| --- | --- |
| GLM receipt | `/data/services/llm-manager/acquisition/glm-5.3-ud-q4-k-xl.complete.json` |
| Receipt SHA256 | `bcd8d9f85baa9bd1fe54dc65b9022487307190cf11583580ab66af845b53f48b` |
| Deployed protected release | `/data/services/releases/7b541017c3e1b2bda80676bcd31bc87d0a4507bc-d3-20260915`; files match the exact Git archive |
| Preparation source/archive | `75a6bf915f30a1582348071eb733d05c33e10eb7`; archive SHA256 `b42a32bf2a96c3d8e2f31dbdb6b187dedaf7bbba8b5f0c4f45d9cd872f8f1545`; separate original protected release retained |
| Canonical instance | `/data/services/llm-manager/deployment-instance.json`, root `0600`; SHA256 `8a5f7787c00319f093656d4fe0b6953c79ae31669b4da7690e6f7386ecad839a` |
| Native API key | `/data/services/secrets/llm-api-key`, root `0600`; provisioned because absent; key bytes omitted |
| Active control directory | `/data/services/llm-manager/active`, root `0700`; ordinary-user writes denied, as for the secrets directory |
| Old state backup SHA256 | `bd34931c6ed9cc0c887795dcefaebd65b4ceec95f061374938b09443a5c47a78` |
| Qwen receipt | Unchanged: independently recorded `true` in protection check |

The protected release was copied from the reviewed archive and files compared with that archive. Source/key/state path protection was checked before handoff. No secrets are included in this report. Existing models/images/releases remain rollback assets; the receipt comparison does not constitute a new full-payload integrity audit of old models. No cleanup/reset of the original dirty checkout, old models or independent jobs is recorded. The prepared release is separate; preservation claims are limited to these operations and captured evidence, not a new byte-for-byte audit of every original checkout/job.

## Embedded template and active 32K invocation

Direct metadata-only inspection reports architecture `glm-dsa`, name `Glm-5.3`, 79 blocks, 256 experts / 8 used. Embedded template: 10,505 bytes, SHA256 `15d2a7176beb599de0a59af8314b4869011e416cff7f65748b314940d3379b0e`. Its source selects low/high explicitly and otherwise max; clear_thinking is supported and defaults false. Low-effort ordinary and native tool continuation requests pass; they emitted no separate reasoning content, so reasoning-rich parsing remains untested.
Active tested profile: `glm-5.3-ud-q4-k-xl-32k`, one slot, actual `n_ctx_slot=32768` in server log and `/v1/models` `n_ctx=32768`. Captured 32K command follows; prior 8K used identical reviewed arguments except `--ctx-size 8192`. No profile or image changed.

```text
/opt/llama/llama-server --model /models/UD-Q4_K_XL/GLM-5.3-UD-Q4_K_XL-00001-of-00011.gguf
--host 0.0.0.0 --port 30002 --alias glm-5.3 --api-key-file /run/secrets/llm-api-key
--ctx-size 32768 --parallel 1 --cpu-moe --jinja --no-webui --n-gpu-layers 999
--split-mode layer --tensor-split 1,1 --load-mode none --device CUDA0,CUDA1
--chat-template-kwargs {"clear_thinking":true}
```

Captured Docker publication is VM loopback `127.0.0.1:30002:30002/tcp`; `0.0.0.0` above is inside the bridged container. Worker1 used an authenticated localhost SSH tunnel, model ID `glm-5.3`. The profile sets one slot, readiness/load timeout 7200 seconds, manual boot policy and Docker restart `no`. CPU experts and both CUDA devices were active; GPU SM work during generation is evidenced below. Load mode is the pinned current `none` contract, not stale mmap/mlock flags.
Guest topology: 112 vCPUs, 7 NUMA nodes × 16 vCPUs, approximately 126 GiB/node; process CPU allowance `0-111`. Actual inference threadpool: **112 threads**, confirmed in startup log. Per root priority, the reviewed runtime defaults were retained with no tuning/binding change; source has no explicit thread/NUMA controls. No guest memory-bandwidth assumption was made.

## Lifecycle and boot ownership

[Legacy stop evidence](d3-evidence/legacy-stop.txt) records a non-destructive dry run followed by persisted `desired=stopped`, `observed=stopped`, `container_running=false`, `boot_policy=manual` for old Qwen30B. Container ID remains `321ee2110e2e0130739ca51fe192b23d746ecefca76e746c9e2df3fd8a799153`; no image/model deletion was planned. This is stopped-state evidence, not a GLM start/switch test.
Manager 8K select/start dry runs, stopped→starting→ready and graceful stop passed. With Worker1 requests complete and no V1 lease, manager stopped 8K (`desired=observed=stopped`, container not running), selected 32K stopped/manual, passed its start dry run and reached ready. The 8K container, image and weights are retained; no overlap is recorded. 32K is now `desired=running`, boot policy `manual`, selected for the root/V1 handoff; no further lifecycle mutation is permitted during that lease.
F1D-retired `m6b-post-reboot-verify.service` remains **disabled, active(exited)** as a historical oneshot. No new `llmctl-boot` unit is installed and no daemon change or reboot occurred. The stock boot-unit source points to the original dirty checkout; a protected boot owner must not be claimed installed. Real failed/timeout behavior, reboot/boot-start, a 32K stop/restart cycle and Qwen↔GLM switching remain NOT_TESTED under the blocked SGLang scope and V1 lease; no destructive fault injection occurred.

## Source checks and remaining client changes

Main D3 coordination records worker source tests **PASS: 198 lifecycle + 75 agent** on reviewed baseline, plus guard static check, shell syntax and `git diff --check`. These are source/synthetic checks, not live inference acceptance.
The manager's sanitized environment exposed an existing root guard's two unused `/tmp` outputs. Final storage-only commit `7b541017c3e1b2bda80676bcd31bc87d0a4507bc`, base `75a6bf915f30a1582348071eb733d05c33e10eb7`, changes one production line to redirect those outputs to `/dev/null`; no runtime/profile change or new framework is included. Author and committer: `CodexAIagent <133749519+djeZo888@users.noreply.github.com>`.
Approved patch SHA256 `e2dc757c188612f6d6d3cc811283ed2ef5391c2a6190ceec30c3afe3c22a0e88`; guard SHA256 `2f798c28d905fd819b00c550c0fd3cd7ebdac95ebb32f38876bce952dcbaf813`; task-root bundle `D3-storage-review.bundle`. Root merge is `83668a913bb1bb2f4f5629fc6af7169ab3aa0658`; deployed worker source is exact `7b541017c3e1b2bda80676bcd31bc87d0a4507bc`. The archive-verified protected release differs from preparation source only by the approved guard line. Manager dry runs/selection/start have proceeded; earlier draft fixture/commit hashes were not deployed.
**Full A1 harness was not run:** its CLI lacks the necessary low-effort knob and loses length/token-exhaustion diagnostics. Task-root `a1-follow-up-request.md` supplies the precise tiny source request. Independent D3 probes used explicit low effort and clear_thinking=true, omitted replayed reasoning, and passed actual continuation **without a reasoning-budget override**. They reused unmodified A1 response parsers, not A1 Client/harness; no A1 PASS is claimed. V1/OpenCode must validate its outgoing low-effort source option and real agent task.

## 8K live load, resources and bounded generation

8K manager readiness completed in **342.02 seconds**, from `2026-09-15T00:40:34.890557Z` to `00:46:16.906857Z`, manager exit 0. Historical unit `d3-glm53-load-8k-20260915.service`, invocation `28778088eec94262b6ebfd2d39376c59`; supervisor PID `139638`, manager PID `139642`, llama-server PID `140535`; container `c25aacfaf71d3fe640ef9cf12fd95ae44cc81b67879b140139b5e020c12bf9b5`. That container is now gracefully stopped for 32K.
Post-generation snapshot: **RSS 411.905 GiB / PSS 411.904 GiB**, host MemAvailable **450.312 GiB**, GPU memory **15,650 / 11,746 MiB**; process swap **0**. This is actual resident memory, largely shared-memory pages, combined with successful inference. Concurrent sampling during tiny generation showed GPU SM work on both devices: peaks **6% / 4%**, sole llama PID. These observations replace the early non-atomic allocation samples for 8K fit.
Process cumulative faults: **107,964,877 minor / 73 major**; host cumulative `pgmajfault=22898`, `oom_kill=0`. These are counters, not per-request fault rates. Root available **5,228,408,832 bytes** remained WARN above STOP. Container `OOMKilled=false`; bounded log sample has zero SIGBUS, illegal-instruction, unsupported-kernel/architecture, CUDA, OOM or assertion markers and no key content. Startup special_eot/eom token warnings remain recorded; ordinary and later tool replies succeeded, broader tokenizer behavior is not established.
At **both contexts**, Worker1 auth/models returned **401 missing / 401 wrong / 200 correct**, exact model `glm-5.3`. Both ordinary requests asked “What is 2 + 2? Reply with the number only.” with `reasoning_effort=low`, `max_tokens=256`, temperature 0, no reasoning-budget override; all returned **content `4`, finish_reason `stop`, 26 prompt / 3 completion tokens**. Missing/wrong authentication on the chat route remains for A1.

| Ordinary request | Cached/evaluated prompt tokens | Prompt ms; tokens/s | Decode ms; tokens/s (`predicted_n=3`) | Wall seconds |
| --- | --- | --- | --- | --- |
| 8K first | 0 / 26 | 1152.033; 22.569 | 705.968; 2.833 | 1.882 |
| 8K warm | 25 / 1 | 350.531; 2.853 | 594.919; 3.362 | 0.970 |
| 32K first | 0 / 26 | 992.058; 26.208 | 521.788; 3.833 | 1.534 |
| 32K warm | 25 / 1 | 74.427; 13.436 | 147.063; 13.600 | 0.245 |

Reported decode rates use the server's `(predicted_n - 1) / seconds` convention. This 26-prompt/3-completion-token sample proves bounded generation, not sustained decode, long-prompt speed or general agent performance; “cold” refers to prompt cache, not a separate cold-weight benchmark.

## 32K fit and independent tool continuation

32K manager readiness completed in **189.62 seconds**, `2026-09-15T00:48:44.017659Z` to `00:51:53.640608Z`, exit 0. This second load had no cache flush and is not a cold-storage comparison. Container `bb77b764cb9677f3c04c1e60359d287a15abb304ba289f38703e58b5a6fc0d55`, llama PID `149976` at snapshot; completed supervisor/manager PIDs `149087` / `149088`. Recheck PID before diagnostics.
Post-generation **RSS/PSS 411.950 GiB**, MemAvailable **449.844 GiB**, VRAM **16,802 / 12,938 MiB**, process swap 0; `OOMKilled=false`, kernel `oom_kill=0`. Process cumulative faults: **107,975,020 minor / 11 major**, host `pgmajfault=22965`; root free **5,228,277,760 bytes**, WARN above STOP. No sampled fatal/error markers or key content. 32K one-slot allocation and actual short generation pass; a full 32,768-token prompt was not tested. Both-GPU compute sampling was performed during the 8K run, not repeated as a 32K kernel benchmark.
Independent four-request tool probe passed both nonstream and SSE modes, all with `reasoning_effort=low`, `max_tokens=512`, temperature 0. Native `read_file` arguments parsed as strict `{"path":"calc.py"}`; returned tool IDs matched each tool-role result. Nonstream ID `BTIelK04Ri0tlLvSForWHevl1U9ZcZVe`; SSE ID `WY0IxDgY839xzSld6Uki1S0kaKb1fK8E`. SSE arguments reconstructed across deltas and both streams ended with `[DONE]`.
Each tool result came from an actual worker-local read of disposable `calc.py` (`return a - b`); both continuations correctly described subtraction and ended with `stop`. Tool replies ended with `tool_calls`; no token exhaustion, metadata/parser error or reasoning replay occurred. No writes/tests or VM tools ran; the local fixture was removed. This is narrower than the A1 repair/read/edit/test workflow and real OpenCode task.

| 32K tool request | Prompt total/cached/evaluated | Completion tokens | Prompt tokens/s | Decode tokens/s | Wall seconds |
| --- | --- | --- | --- | --- | --- |
| Nonstream call | 219 / 9 / 210 | 13 | 29.840 | 2.695 | 11.581 |
| Nonstream continuation | 261 / 231 / 30 | 26 | 14.347 | 5.847 | 6.394 |
| SSE call | 219 / 218 / 1 | 13 | 3.020 | 9.769 | 1.586 |
| SSE continuation | 261 / 231 / 30 | 26 | 23.922 | 4.961 | 6.324 |

These are four individual requests with different cache reuse, not a stream-vs-nonstream performance comparison. Reported decode rates use the same `(predicted_n - 1)` convention. Whole probe: 26.30 seconds; all four explicit-low requests completed without a reasoning-budget override or runtime-argument change.
Durable VM evidence remains `/data/build/d3-glm53-20260915/evidence/`, including `load-8k.json`, `load-32k.json`, snapshots, metrics and manager/supervisor outputs. Both load supervisors completed; bounds were manager 7200 seconds, supervisor 7500 seconds, transient unit 7800 seconds. The running reviewed deployment remains D3's responsibility; active request ownership is now root/V1's.

## Remaining live proof

| Required proof | Current result |
| --- | --- |
| 8K load/readiness and bounded generation | PASS, 342.02 seconds; exact source/image/profile and two successful replies recorded |
| 8K resident RAM, VRAM, both-GPU work and error sample | PASS within measured scope above |
| Auth missing/wrong/correct and `/v1/models` | PASS on models route; full A1/chat-route auth pending |
| Cold/warm tiny-request timing | MEASURED above; sustained/long-prompt performance NOT_TESTED |
| 32K one-slot fit and actual generation | PASS within measured short-request scope; actual slot 32768 |
| Stream/nonstream native tool IDs/JSON, local read result continuation/final answer | PASS independent D3 probe; full A1 repair workflow NOT_TESTED |
| A1 harness / real V1 OpenCode agent task | NOT_TESTED; low-knob source follow-up supplied, real V1 evidence pending |
| Lifecycle states and safe stop/start/switch | 8K stopped→starting→ready→stopped and 32K selected→starting→ready PASS; actual failed/timeout, 32K restart and cross-backend switch NOT_TESTED |

## V1 lease and remaining action

At `2026-09-15T00:56:19.740716Z`, task-root `client-lease.json` records **RELEASED_TO_ROOT_WORKER2_V1**, D3 active requests 0, all D3 tunnels closed and fixture removed. This grants root/V1 exclusive requests; it does not release V1 ownership back to D3. Endpoint `http://127.0.0.1:30002/v1`, model `glm-5.3`, selected `glm-5.3-ud-q4-k-xl-32k`, desired running/manual. D3 retains read-only diagnostics/deployment ownership, with no further generation, lifecycle mutation or tuning until explicit root/V1 release. Scoped F1Db fixtures exclude GPU/network/real key/model/protected mutations.
Final post-tool snapshot: RSS/PSS **411.993 GiB**, MemAvailable **450.023 GiB**, VRAM **16,804 / 12,940 MiB**, process swap0; root available **4.869 GiB**, WARN above STOP. [Final state and both guards](d3-evidence/final-state-guards.txt) pass; current model is ready/running/manual and both load supervisors are inactive. [Continuation](d3-continuation.md) records ownership, commands and remaining gates.
Next: root/Worker2 completes the reviewed low-effort client adjustment and actual V1/OpenCode acceptance using `v1-handoff.md`. Remaining lifecycle/boot work needs separate coordination after lease release; SGLang remains blocked. Overall READY and completion of all requested work remain pending actual client evidence and the explicitly untested gates above.
