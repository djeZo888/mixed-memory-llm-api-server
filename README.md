# mixed-memory-llm-api-server

An API-only local AI server for **Qwen3.8-27B FP8** and **GLM5.3 UD-Q4_K_XL**.
Reviewed source `04143b18cca7aca724d9a4a4bcf943fe86c040db` defines **dual-qwen**
as the default: one Qwen instance per GPU. Optional **glm-qwen** replaces only
GPU0 with GLM; returning to dual-qwen replaces GPU0 with Qwen again.

**Production activation acceptance is PENDING.** These are source-reviewed
operating instructions, not a live readiness receipt. ACTIVATE separately owns
installation and VM work; source installation and schema 3 migration alone do
not prove serving, switching, boot replay or private-client acceptance.

| Placement / control target | Deployment ID and public instance ID | Inference alias / port |
| --- | --- | --- |
| GPU0 / `glm`, default | `qwen38-27b-q0-480000-yarn4-bf16kv` | `qwen3.8-27b-gpu0` / 30002 |
| GPU1 / `qwen`, both modes | `qwen38-27b-q1-480000-yarn4-bf16kv` | `qwen3.8-27b` / 30004 |
| GPU0 / `glm`, optional | `glm-5.3-ud-q4-k-xl-g1-480000` | `glm-5.3` / 30002 |

All three configure **480,000 tokens** on the existing **72-vCPU guest**.
Both Qwen instances share guest CPUs 0–7 (union 8); optional GLM uses 0–71,
sharing 0–7 with GPU1 Qwen. These are guest affinity masks, not exclusive cores
or physical host pinning. [Model matrix](docs/model-matrix.md) records resources
and the distinction between configured, accepted and measured occupied context.

The [one-pair dual-Q benchmark](reports/dualq-480k-20260921.md) completed in
258.9091 s: occupied context 479,490 / 479,495. Both semantic checks passed;
Q1's outer JSON fence failed strict formatting. Output windows did not overlap.
Its STOPPED/manual restoration is historical benchmark state, not production
state or activation acceptance.

## Use the APIs

Control uses `http://10.156.100.60:30000/control/v1/...`. Clients discover and
explicitly address separate inference bases on ports 30002 and 30004, each
with `/v1`; the aliases above identify the loaded instance. There is no common
inference router or automatic fallback. Native listeners stay authenticated
IPv4 loopback behind the reviewed private transport.

- [API operations and examples](docs/ai-vm-api-operations.md): discovery,
  separate credentials, targeted switch/poll and inference.
- [Control contract](docs/control-api.md) and [inference contract](docs/api-contract.md).
- [Operations](docs/operations.md): durable VM ownership, guards and recovery.
- [Mode, migration and rollback contract](docs/concurrent-api.md).
- [Private client transport](docs/direct-client-network.md) and
  [protected credentials](docs/agent-client.md#protected-key-file).

`mutation_busy` describes lifecycle work. Inference running/queued counts and
external backlog remain unknown; Ready does not mean idle. A future harness
owns its dispatch, backlog and drain before a targeted switch. Switching a
running target requires `allow_interrupt:true`, fresh identity/generation and
operation polling; the server provides no atomic drain guarantee.

The production source assigns control, private transport and boot lifecycle to
ai-vm services, with no Worker1, SSH or benchmark-keeper lifetime dependency.
Final activation evidence must establish installed ownership and replay; this
source contract does not claim a passed physical reboot.

Tools, browsing and file work run on ordinary external clients in trusted
workspaces. A separate frontend VM is future work. **Installer implementation
and tests remain paused.**

## Historical evidence

The prior [singleton acceptance](reports/apiaccept-lan-acceptance.md),
[stage-one qualifications](reports/stage1-ai-vm-status.md),
[cleanup report](reports/finalops-reboot-cleanup.md) and
[installer record](docs/installation.md) retain their original scope. Earlier
TP2/1M configurations and success statements do not establish current dual-Q
acceptance. Historical reports are unchanged.

## License

Apache-2.0 is intended; the full license text remains outstanding.
See [LICENSE.todo.md](LICENSE.todo.md).
