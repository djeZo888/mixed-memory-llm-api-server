# mixed-memory-llm-api-server

An API-only local AI server for **GLM5.3 UD-Q4_K_XL** (flagship) and
**Qwen3.8-27B FP8** (fast model). It provides OpenAI-compatible inference and a
separate authenticated control API for catalog, status and model switching.
Select/load the model before inference: **one backend is active at a time**.

**Completion status: PENDING (2026-09-17).** The anticipated deployment
selection is source-only, awaiting live acceptance; it is not an accepted or
active default. Coordinated Worker1 result at **2026-09-17 05:18:10 UTC** on exact source
`821df4a561173c078ed35c9286a07b82867b7953` reports the genuine native no-GPU
fixture pair at **128K and 256K PASS** (report not yet committed; no model
allocation or inference PASS), while actual Qwen model loading/inference,
1M extension acceptance and final live API/switch/network/boot/client
acceptance remain **PENDING**.
See the [current scope](docs/orchestration/2026-09-17-resumed.md) and
[profile/evidence handoff](docs/l2-live-snapshot.md).

## Models and capacity

| Model | Placement and context scope |
| --- | --- |
| GLM5.3 UD-Q4_K_XL | Fast system RAM plus both GPUs; declared/configured context 1,048,576 tokens. [Historical allocation and tiny-response evidence](reports/d3cap4-native1m.md) does not prove occupied 1M context. |
| Qwen3.8-27B FP8 | GPU-resident native baseline, declared 256K (262,144 tokens). The chosen source candidate uses the same weights, both GPUs/TP2 and BF16 KV with official factor-4 YaRN settings for 1,000,000 tokens; acceptance is **PENDING**. |

Configured capacity, allocation and successfully occupied context are separate
claims. The catalog's `context.verified_occupied_tokens` remains `null`; historical 32K
and 2048-output-token checks are not product limits.

## Start here

- [API operations guide](docs/ai-vm-api-operations.md): endpoint/key separation,
  aliases, catalog, asynchronous switch/poll and inference flow.
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

## Historical references

The [installer record](docs/installation.md), [roadmap](ROADMAP.md) and
[reports](reports/) preserve earlier work and its evidence limits. They do not
establish a complete fresh-machine installation or current serving readiness.

## License

Apache-2.0 is intended; the full license text remains outstanding.
See [LICENSE.todo.md](LICENSE.todo.md).
