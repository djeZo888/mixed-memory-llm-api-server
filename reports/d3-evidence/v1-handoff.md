# D3 -> root / Worker2 V1: 32K baseline request lease

**Request lease released to root/Worker2 V1. No D3 requests active.** D3 ordinary/tool probes completed, all owned request tunnels exited, local fixture removed. D3 will issue no more generation requests and will not stop/restart/switch/tune the model until root/V1 explicitly releases the client lease. D3 retains responsibility for the running reviewed deployment and read-only diagnostics. F1Db overlap is limited by scoped-overlap-ack.md.

## Exact usable endpoint and protected source

- Deployment: `glm-5.3-ud-q4-k-xl-32k`; served alias: `glm-5.3`.
- VM-only endpoint: `http://127.0.0.1:30002/v1`; use worker SSH forwarding through `ai-vm`. One slot, actual server log `n_ctx_slot = 32768`.
- Protected key filename: `/data/services/secrets/llm-api-key`, root0600, exact printable bytes/no newline. Reuse this key through protected client handling; no key content in reports, argv, environment dumps or logs.
- Instance: `/data/services/llm-manager/deployment-instance.json`; desired `running`, boot policy `manual`; new boot owner not installed. No reboot or boot-resume claim.
- Reviewed source: `7b541017c3e1b2bda80676bcd31bc87d0a4507bc`; root integration `83668a913bb1bb2f4f5629fc6af7169ab3aa0658`.
- Protected release: `/data/services/releases/7b541017c3e1b2bda80676bcd31bc87d0a4507bc-d3-20260915`.
- Container: `bb77b764cb9677f3c04c1e60359d287a15abb304ba289f38703e58b5a6fc0d55`; llama PID149976 (recheck PID before diagnostics).
- Runtime image: `sha256:6866856c573d69d504f82265321b182f631a7b3912a1ed1b4efbf893729d4e62`, v0.4.1/b29c606, CPU experts/CUDA0+CUDA1, load-mode none, embedded Jinja, no-webui; unchanged reviewed32K profile and default112 inference threads. No tuning authorized during lease.

## Required request behavior

Send top-level `"reasoning_effort":"low"` on every ordinary/tool/continuation request. GLM embedded template accepts low/high and otherwise uses max. Tested tiny ordinary body used `max_tokens:256, temperature:0, stream:false`; independent tool bodies used `max_tokens:512, temperature:0`, both stream:false and stream:true with `stream_options:{include_usage:true}`. No reasoning-budget override was needed.

Runtime already has `--chat-template-kwargs '{"clear_thinking":true}'`. Client excludes reasoning from replay; replay assistant role/content/tool_calls and matching tool_call_id result. Actual continuation was tested with this policy. Do not silently assume an omitted A1/OpenCode option matches this low-effort proof. A1 follow-up source request is `a1-follow-up-request.md`; unmodified A1 CLI lacks this knob and loses length diagnostics.

## Actual evidence

- 8K ready342.02s, clean exit0 on manager stop. No model/image deletion. 32K ready189.62s; no cache flush, so this is a second load timing, not a cold-storage benchmark.
- 32K missing/wrong/correct models auth401/401/200; servedglm-5.3. Ordinary replies4 with finish_reasonstop,26prompt/3completion tokens. First1.534s, warm0.245s (25cached prompt tokens); tiny samples only.
- 32K postgeneration PSS431961180KiB (~411.95GiB), MemAvailable471695904KiB (~449.84GiB), VRAM16802/12938MiB; processswap0. BothGPU compute activity observed during8K generation. No sampled SIGBUS/illegal instruction/CUDA/SM120/OOM failures.
- Independent nonstream tool call13completion tokens/11.581s -> local read_file(calc.py) -> final26tokens/6.394s. SSE call13tokens/1.586s -> continuation26tokens/6.324s. Valid tool IDs/strictJSON, SSE[DONE], final correctly described a-b. Every request explicitlow; no token exhaustion; all4 requests complete in26.30s.
- This independent probe reused reviewed A1 response parsers, not the A1 Client/harness. Full fixture repair/write/tests and real OpenCode agent evidence remain V1/A1 work. Do not label overallREADY until real V1 acceptance.

Evidence: repo `reports/d3-evidence/32k-probe.json`, `32k-tool-probe.json`, `32k-generation-snapshot.json`; durable VM `/data/build/d3-glm53-20260915/evidence/`.
