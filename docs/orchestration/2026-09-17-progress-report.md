# AI server progress report

Prepared 17 September 2026. This report separates completed work from remaining acceptance. The last recorded VM trials were on 15 September; this recap does not itself run a new live VM health check.

## Overall result

**The two-model AI server is not finished.** GLM 5.3 has served real requests and successfully started with a **1,048,576-token configured context**. Qwen3.8-27B FP8 is downloaded, but has **not yet loaded or served a real request**. The private GLM endpoint was exposed; the complete two-model catalog/switching service and boot recovery still need live acceptance.

Work is paused at your requested handoff. No new implementation or model retries are part of this recap. The next phase remains **ai-vm only**; frontend work comes afterward, and the installer remains postponed until the frontend works.

## Completed and demonstrated

| Area | Completed result | Evidence limit |
| --- | --- | --- |
| Hardware audit | Ubuntu 24.04.4, about **882 GiB RAM**, **two RTX PRO 6000 Blackwell GPUs, about 95.6 GiB each**, 112 vCPUs identified. | The stated 400 GB/s RAM bandwidth has not been measured. |
| Storage | The additional **3,000 GiB disk was initialized, formatted as ext4 and mounted at `/data/models-large`**. Persistent mount configuration and storage checks were installed. Docker, model, build and log data use `/data`. | Boot after a real reboot remains untested. Root storage is still tight: about 4.85 GiB free at the last checks. |
| Model acquisition | GLM 5.3 UD-Q4_K_XL downloaded and integrity sealed: about **435.2 GiB**. Qwen3.8-27B FP8 downloaded and sealed: about **28.75 GiB**. | Having weights does not establish runtime readiness. |
| GLM runtime | Built and pinned the CUDA runtime for the GPUs; configured a hybrid RAM/GPU deployment and single-request operation. GLM passed authenticated generation, streaming, model-name validation, and a real tool call with continuation at 32K. | Final client acceptance must be repeated on the chosen final context profile. |
| GLM maximum allocation | A later trial reached ready with **one 1,048,576-token slot**, about **402 GiB process memory**, and **48/45 GiB GPU cache allocations**. Model and container swap were zero. A small request returned HTTP 200 and `READY`. | This proves startup/allocation and a small request, **not useful generation over an occupied million-token prompt**. |
| Private API | Authenticated GLM transport configured at **`http://10.156.100.60:30002/v1`**, limited to the private network. Earlier direct worker-client authentication, streaming and agent/tool tests passed. | This is trusted-LAN HTTP. Current final-profile access and future frontend connectivity still need verification. Control and Qwen endpoints remain inactive in the last recorded state. |
| Agent integration | An earlier GLM runtime completed an ordinary OpenCode read/edit/test workflow; the newer runtime also passed a smaller real tool continuation. Qwen client request formatting was tested separately. | The Qwen formatting tests did not run the real Qwen model. Final two-model agent acceptance is outstanding. |
| Lifecycle/control source | Declarative model/runtime profiles, lifecycle ownership, catalog/switching API code and boot-policy handling were developed and received focused checks. | Some reviewed fixes are not yet deployed into the live protected source installation; end-to-end switching and reboot recovery are not complete. |
| Repository and handoff | Work, source reviews, failure reports, task prompts, remote session IDs and recoverable Git bundles are retained. Development uses the existing draft PR. | A draft branch and passing focused tests do not mean the whole system or full CI is passing. |

### Measured speed

The best directly comparable recent **GLM 32K** observation generated **64 tokens at 9.69 tokens/second**. That request used 1,370 input tokens, including 173 cached tokens, and took about 27.5 seconds total including prompt processing. This is one short observation, not a sustained or million-token benchmark.

Earlier runs with intrusive memory monitoring measured about 0.55 tokens/second. The large improvement strongly suggests monitoring overhead mattered, but cache history and measurement details also differed, so it is not a clean causal benchmark. **There is no measured Qwen speed yet**, and the tiny 1M-profile smoke request is too small for a useful throughput figure.

## Why this took too long

I made the verification process too elaborate and split work into too many small implementation, review and evidence-packaging cycles before securing the simplest two-model end-to-end result. That orchestration overhead consumed unnecessary time and tokens. I should have simplified and validated the monitoring and fixture assumptions earlier.

The main technical delays were:

1. **Qwen startup validation.** The test environment differed from assumptions: NVIDIA changed a no-GPU environment value; a global NVIDIA device node was initially rejected; SciPy/OpenBLAS attempted too many threads. Several fixes were needed before the real remaining startup error became visible. Earlier compound assertions hid the specific failure and caused further debugging cycles. The latest trial identifies **`LaunchError: launch_environment_invalid`**, before engine startup. The exact rejected variable/cause is still unresolved; a known environment-mutation seam is a hypothesis to inspect, not a proven diagnosis.
2. **GLM monitoring interrupted otherwise plausible loads.** Repeated full process-memory scans distorted performance. A strict two-second telemetry rule and later tiny system-wide swap changes caused aborted loads even when GLM itself had no swap and ample RAM remained. Monitoring was changed to cheap live samples with expensive checks at idle boundaries; model/container swap is separated from unrelated host swap. The subsequent 1M allocation and smoke trial passed.
3. **Crash files filled the small root disk.** Qwen fixture failures produced about **1.58 GB of crash artifacts**, blocking further work. The exact files were archived, verified and removed, restoring space. Fixture core-dump containment prevented recurrence; equivalent containment for the real Qwen managed container remains to be implemented before its first load.
4. **Real integration work and large artifacts.** Downloading/sealing the flagship, building a compatible CUDA runtime, preparing storage and reconciling old/new deployment code were substantive tasks. However, the repeated custom validation and packaging loops added avoidable overhead on top of them.

There is no reliable per-task token or billing total in the collected evidence, so this report does not invent a cost breakdown or rank these causes by measured token use.

## Focused plan to finish ai-vm

| Order | Work | Completion evidence |
| --- | --- | --- |
| 1 | Resolve the **specific Qwen startup-environment rejection** using the retained failure, with one source owner. Add the already-planned Qwen container crash containment. Use the existing diagnostics rather than another framework. | The pinned native validation passes, followed by the first real GPU model load and an authenticated generation. |
| 2 | Establish Qwen's single-GPU baseline, then increase its usable context. Start with 128K/256K; evaluate the existing optional 1M extended-context plan only after native operation works. | Real memory/cache measurements, retrieval and tool continuation at the retained context, plus prompt/decode speeds. Publish the largest **verified useful** window, not only the largest configured number. |
| 3 | Finish GLM context acceptance using the existing 1M allocation. Run increasing occupied-context retrieval/tool workloads with cheap monitoring and clear stop limits. | Record the highest window actually passed and realistic latency. Retain a smaller proven default if the largest window is impractically slow or unreliable; keep allocation capacity separately documented. |
| 4 | Deploy the reviewed lifecycle/control fixes, set the two accepted profiles as catalog choices, expose authenticated switching and Qwen inference, and verify boot/recovery. | Worker2 switches GLM → Qwen → GLM through the API, runs a real ordinary-client agent task on each, checks authorization/streaming and confirms selected-model recovery after reboot. |
| 5 | Remove only the reviewed obsolete model trees after replacement acceptance; finish API/operator documentation and synchronize GitHub. | Fresh non-use checks, measured reclaimed space, exactly two current model identities, documented endpoints/keys/context/speed, and a final repeatable acceptance record. |

Use both workers in parallel for independent source/client work, but give Worker1 exclusive ownership of VM changes and model runs. Combine tightly related fixes and their verification into bounded tasks; reuse existing reports and scripts. Avoid new framework work, extra models, unrelated tuning and repeated checks without a concrete failure.

The cleanup plan covers old MiniMax M3, Qwen3-30B, Qwen3-0.6B smoke and Qwen3-Coder-Next trees: about **587 GB historically allocated**, still awaiting deletion. Preserve selected weights, credentials, runtime rollback and useful evidence. Do not run a global prune.

## Final completion criteria

This first phase is complete only when **both selected models serve authenticated API requests from another VM/host**, the catalog and switch operation work, each retained context has real acceptance evidence, agent tool execution works through an ordinary client, restart/reboot behavior is verified, and operator documentation matches the deployed state. The frontend and installer are separate later phases.

See [the paused handoff](2026-09-17-handoff.md) for the continuation entry point and [the draft GitHub PR](https://github.com/djeZo888/mixed-memory-llm-api-server/pull/1) for the accumulated source work.
