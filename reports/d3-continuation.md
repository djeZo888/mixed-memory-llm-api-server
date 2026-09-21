# D3 continuation / D3b boundary

**32K GLM baseline is ready and passed live API plus independent nonstream/SSE read-tool continuation. Overall READY remains pending A1/V1 and remaining lifecycle gates.** See [D3 report](d3-glm-live-proof.md).

## Ownership and exact current state

- Request lease released to root/Worker2 V1. Task-root `client-lease.json` and `v1-handoff.md` record the handoff. No D3 generation requests or request tunnels remain active. **Do not stop/restart/switch/tune or issue competing requests until root/V1 explicitly releases the lease.**
- D3 retains real inference/lifecycle ownership; root separately allowed F1Db uniquely named disposable noGPU/noNetwork/noRealKey/noModel fixtures only. Task-root `scoped-overlap-ack.md` is the exact boundary; it does not authorize SGLang/Qwen activation.
- Selected `glm-5.3-ud-q4-k-xl-32k`, served `glm-5.3`, endpoint `http://127.0.0.1:30002/v1`, desired `running`, boot policy `manual`.
- Protected instance `/data/services/llm-manager/deployment-instance.json`; protected native key path `/data/services/secrets/llm-api-key`. Preserve exact bytes; never put the key in argv, logs or evidence.
- Protected release `/data/services/releases/7b541017c3e1b2bda80676bcd31bc87d0a4507bc-d3-20260915`; exact reviewed source `7b541017c3e1b2bda80676bcd31bc87d0a4507bc` (root merge `83668a913bb1bb2f4f5629fc6af7169ab3aa0658`).
- Container `bb77b764cb9677f3c04c1e60359d287a15abb304ba289f38703e58b5a6fc0d55`; process PID149976 at handoff. Recheck ID/state/PID before diagnostics.
- Image `sha256:6866856c573d69d504f82265321b182f631a7b3912a1ed1b4efbf893729d4e62`; llama.cpp v0.4.1/b29c606, unchanged CPU-expert/CUDA0+CUDA1/none-load/Jinja/no-webui contract. Runtime112 inference threads; root prohibited tuning before baseline/V1.
- Both owned load supervisor units (`d3-glm53-load-{8k,32k}-20260915.service`) finished and are inactive. The model container is the only continuing D3 operation, tracked by protected manager state. 8K rollback container is stopped/exit0 and retained.
- Final sample: 32K PSS411.9926GiB, RSS411.9926GiB, MemAvailable450.0233GiB, VRAM16804/12940MiB, processswap0; root available4.869GiB (WARN<6, aboveSTOP4).

## Read-only continuation commands (via Worker1 SSH only)

```bash
ssh ai-vm 'sudo -n env PYTHONDONTWRITEBYTECODE=1 python3 /data/services/releases/7b541017c3e1b2bda80676bcd31bc87d0a4507bc-d3-20260915/scripts/llmctl status --instance /data/services/llm-manager/deployment-instance.json'
ssh ai-vm 'sudo -n cat /data/build/d3-glm53-20260915/evidence/load-32k.json'
ssh ai-vm 'sudo -n python3 /data/services/llm-manager/d3-ops/snapshot-d3.py --name llmctl-glm-5.3-32k'
```

The snapshot emits bounded nonsecret metrics and timing lines, not raw logs. Initial load snapshots were sequential/non-atomic; final stable samples govern fit claims. Do not rerun a load because a transient completed unit is now unloaded. The protected manager's container state is authoritative.

## Remaining work

1. Root reviews the tiny A1 source follow-up in task-root `a1-follow-up-request.md`: optional top-level `reasoning_effort=low` on every request, plus retained length/usage diagnostics. Independent D3 low requests did not require a reasoning-budget override. Do not substitute omitted/default effort or silently change runtime args.
2. Worker2 V1 performs the real OpenCode multi-step edit/test/repair task with actual schema/token headroom at32K. Record its source/config, request reasoning behavior, tool IDs/results, real client latency and final acceptance. All tools execute on the worker, never the VM.
3. Run reviewed A1 harness once the request knob is reviewed, including full local repair fixture in both tool-stream modes, missing/wrong/correct chat authentication and required protocol/error cases. D3 reused the reviewed parsers but did **not** run the full harness.
4. After explicit client lease release, finish allowed lifecycle proof: same-profile stop/start, Qwen↔GLM switch only after SGLang's separate auth gate passes, and truthful failed/timeout behavior without destructive fault injection. No natural start timeout/failure occurred in D3; source tests are not live timeout evidence.
5. New protected boot owner is NOT_INSTALLED. Old `m6b-post-reboot-verify` is disabled/active(exited), backed up byF1D. Stock unit targets the original dirty checkout; do not install it unchanged. No daemon change/reboot was made. Coordinate any boot-owner deployment and actual reboot separately with root.
6. Keep the selected running32K baseline per root's V1/tuning priority until a different final state is explicitly selected. Future D3T tuning requires its own reviewed single variant and released lease; no D3 tuning comparison occurred.

Preserve all old models/containers, the dirty original checkout, F1D/Qwen seal and D3 GLM seal. Before/after any future authorized deployment, verify exact UUIDs and run the reviewed common guards. Never infer integrity from load success: D3 receipt validates acquisition-computed hashes against immutable R2; no independent435GiB cryptographic reread occurred.

## Operator helper provenance

[Operator source manifest](d3-evidence/operator-source-manifest.json) records exact helper hashes and archived source text. These are execution evidence, not additional deployed manager/profile changes. Original runnable worker scripts remain beside the task's `repo/`; VM snapshot/load helpers are under protected `/data/services/llm-manager/d3-ops/`. Source text is archived without executable installation assumptions.

Verification performed: worker AST/compile syntax and `--help`; preparation `--dry-run` then `--apply`; actual metadata extraction, both bounded load supervisors, both ordinary probes and the four-request tool probe. All shell operations used the reviewed guards. Snapshot collection is sequential and reports sampled failure-pattern counts, not exhaustive kernel tracing. The full low-effort requests and raw bounded tool responses are retained without authentication headers or key bytes.
