# mixed-memory-llm-api-server

An API-only local AI server for **GLM5.3 UD-Q4_K_XL** (flagship) and
**Qwen3.8-27B FP8** (fast model). It provides OpenAI-compatible inference and a
separate authenticated control API for catalog, status and model switching.
Select/load the model before inference: **one backend is active at a time**.

**Stage one COMPLETE, with qualifications (2026-09-17).**
[Independent LAN acceptance](reports/apiaccept-lan-acceptance.md) covers both
models, real agent work, Qwen → GLM → Qwen switching and postboot access.
Fast Qwen is selected by default and resumes after reboot.
[Final cleanup is COMPLETE](reports/finalops-reboot-cleanup.md).
GLM functional checks passed, but strict swap-free qualification did
not; neither model has demonstrated its full occupied context maximum. The
[stage-one status report](reports/stage1-ai-vm-status.md) preserves the exact
evidence, source boundaries and remaining qualifications.

## Models and capacity

| Model | Placement and context scope |
| --- | --- |
| GLM5.3 UD-Q4_K_XL | System RAM plus both GPUs; configured context 1,048,576 tokens. Agent and strict-JSON retrieval PASS; retrieval inputs 4,154 then 4,196 tokens. Larger OpenCode input counters are recorded separately. |
| Qwen3.8-27B FP8 | Both GPUs/TP2, FP8 weights, BF16 KV and official factor-4 YaRN; configured/allocated context 1,000,000 tokens. Largest completed retrieval input 144,244 tokens, with real tool use and strict JSON. |

Configured capacity, allocation and successfully occupied context are separate
claims. Neither full occupied maximum is established. The catalog's
`context.verified_occupied_tokens` remains `null` because it has no structured
occupied-context receipt; historical 32K and 2048-output-token checks are not
product limits. Near-cap occupied-context tasks remain NOT_TESTED.

## Start here

- [API operations guide](docs/ai-vm-api-operations.md): endpoint/key separation,
  protected-file examples, aliases, catalog, asynchronous switch/poll and inference.
- [Control API contract](docs/control-api.md): exact fields, concurrency,
  idempotency, interruption and recovery behavior.
- [Direct client networking](docs/direct-client-network.md): approved private
  transport and authentication; [network policy](docs/private-network.md).
- [Agent client contract](docs/agent-client.md), [reviewed OpenCode client](docs/client-install.md)
  and [ordinary-client verification](docs/client-verification.md).
- [Manual Qwen 50–100K context example](examples/qwen-context-test.py) and
  [console instructions](docs/ai-vm-api-operations.md#manual-qwen-context-example):
  one counted retrieval request; offline-checked, NOT_LIVE_EXECUTED.

Real file reads, edits, test execution, browsing and other tools require an
external agent client running as an ordinary user in a trusted workspace.
The model API does not execute tools. A separate frontend VM is future work;
there is no completed human chat UI here. Finish ai-vm first, frontend next,
installer last. **All installer work and tests are paused.**
The [current scope](docs/orchestration/2026-09-17-resumed.md) and
[profile handoff](docs/l2-live-snapshot.md) preserve coordination and source
details; their older pending statements must be read with the dated status report.

## Historical references

The [installer record](docs/installation.md), [roadmap](ROADMAP.md) and
[reports](reports/) preserve earlier work and its evidence limits. They do not
establish a complete fresh-machine installation or current serving readiness.

## License

Apache-2.0 is intended; the full license text remains outstanding.
See [LICENSE.todo.md](LICENSE.todo.md).
