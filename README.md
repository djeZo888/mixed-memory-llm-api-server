# mixed-memory-llm-api-server

An API-only local AI server for **GLM5.3 UD-Q4_K_XL** (flagship) and
**Qwen3.8-27B FP8** (fast model). It provides OpenAI-compatible inference and a
separate authenticated control API for catalog, status and model switching.
Select/load the model before inference: **one backend is active at a time**.

**Stage one status: DRAFT / completion PENDING (2026-09-17).** Published evidence
establishes [Qwen authentication, chat, streaming and real tool continuation](reports/q38retry-tp2-1m.md)
and the [private control API with the exact two-model catalog](reports/apideploy-control-ready.md).
Root also reports a Qwen 144,244-token agent retrieval PASS and independent
OpenCode read/edit/test PASS after replaying saved events with the corrected
verifier; durable report links are pending. The new Qwen alias guard still needs
fresh native/extension proofs and live rejection checks. Final GLM, switching,
reboot and cleanup acceptance remain pending. See the
[stage-one status draft](reports/stage1-ai-vm-status.md) for evidence boundaries
and the remaining plan.

## Models and capacity

| Model | Placement and context scope |
| --- | --- |
| GLM5.3 UD-Q4_K_XL | Fast system RAM plus both GPUs; declared/configured context 1,048,576 tokens. [Historical allocation and tiny-response evidence](reports/d3cap4-native1m.md) does not prove occupied 1M context. |
| Qwen3.8-27B FP8 | Selected profile uses both GPUs/TP2, FP8 weights and BF16 KV with official factor-4 YaRN settings; configured and allocated context 1,000,000 tokens. Published small-task PASS; coordinated 144,244-token retrieval PASS awaits its report link. |

Configured capacity, allocation and successfully occupied context are separate
claims. Neither full occupied maximum is established. The catalog's
`context.verified_occupied_tokens` remains `null` because it has no structured
occupied-context receipt; historical 32K and 2048-output-token checks are not
product limits. Fast Qwen is the intended default after final acceptance.

## Start here

- [API operations guide](docs/ai-vm-api-operations.md): endpoint/key separation,
  protected-file examples, aliases, catalog, asynchronous switch/poll and inference.
- [Control API contract](docs/control-api.md): exact fields, concurrency,
  idempotency, interruption and recovery behavior.
- [Direct client networking](docs/direct-client-network.md): approved private
  transport and authentication; [network policy](docs/private-network.md).
- [Agent client contract](docs/agent-client.md), [reviewed OpenCode client](docs/client-install.md)
  and [ordinary-client verification](docs/client-verification.md).

Real file reads, edits, test execution, browsing and other tools require an
external agent client running as an ordinary user in a trusted workspace.
The model API does not execute tools. A separate frontend VM is future work;
there is no completed human chat UI here. Finish ai-vm first, frontend next,
installer last. **All installer work and tests are paused.**
The [current scope](docs/orchestration/2026-09-17-resumed.md) and
[profile handoff](docs/l2-live-snapshot.md) preserve coordination and source
details; their older pending statements must be read with the dated status draft.

## Historical references

The [installer record](docs/installation.md), [roadmap](ROADMAP.md) and
[reports](reports/) preserve earlier work and its evidence limits. They do not
establish a complete fresh-machine installation or current serving readiness.

## License

Apache-2.0 is intended; the full license text remains outstanding.
See [LICENSE.todo.md](LICENSE.todo.md).
