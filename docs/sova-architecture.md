# Sova architecture

The deployed harness, image and status features described here are documented
from `feature/system-topology` (PRs 5–8) and are **not yet merged into main**.
Their current source/configuration/evidence links explicitly target that
feature branch; this main-based change adds documentation only.

Sova names the whole system; existing source paths, VM names and runtime IDs
remain unchanged. This H007 document separates current source behavior from the
**accepted design for future routing and scaling**. It implements no routing,
relocation or distributed MiniMax runtime and makes no new capacity claim. See
the [overview diagram](../README.md) and [work queue](../TODO.md).

## Current implementation

The [engine profile](https://github.com/djeZo888/mixed-memory-llm-api-server/blob/feature/system-topology/ai-harness/deploy/engine/configure-profile.mjs) configures
one Qwen model family, `qwen3.8-27b`. Both `defaultModel` and `defaultLightModel`
use that same gateway model. The profile retains MiniMax's native delegation
tools; main sessions, child agents, compression and auxiliary inference calls
share the gateway. Configured context/output limits are described in the
[harness capacity guide](https://github.com/djeZo888/mixed-memory-llm-api-server/blob/feature/system-topology/ai-harness/README.md#capacity-and-context); configured
limits do not establish measured occupancy or throughput.

The [gateway](https://github.com/djeZo888/mixed-memory-llm-api-server/blob/feature/system-topology/ai-harness/server/src/gateway.ts) accepts that single model ID
and requires exactly two reviewed Qwen upstream aliases, on ai-vm ports 30002
and 30004. There are **exactly two globally shared inference slots**, one per
endpoint, with a bounded FIFO queue and durable lane settlement/quarantine.
The gateway enforces one `MODEL` alias and selects an eligible idle lane from
the two configured lanes; this does not select among arbitrary models.
A waiting parent does not reserve an inference slot. These are global to the
current harness deployment, not a distributed admission implementation. There is
no GLM harness integration or arbitrary-model routing. Direct ai-vm inference
endpoints remain separate; ai-vm has no common inference router.

The [run broker](https://github.com/djeZo888/mixed-memory-llm-api-server/blob/feature/system-topology/ai-harness/server/src/broker.ts) owns session runners,
supplies their gateway authorization and serializes runs sharing a workspace.
The profile exposes a separate image MCP tool path through the gateway's image
job routes to the [image broker](https://github.com/djeZo888/mixed-memory-llm-api-server/blob/feature/system-topology/ai-harness/server/src/image-broker.ts) and
[image upstream](https://github.com/djeZo888/mixed-memory-llm-api-server/blob/feature/system-topology/ai-harness/server/src/image-upstream.ts). Its durable image
lane neither acquires nor releases the two text slots. Image generation/editing
is a specialist tool operation, not general-purpose agent delegation. Existing
[image limits and worker restrictions](https://github.com/djeZo888/mixed-memory-llm-api-server/blob/feature/system-topology/ai-harness/README.md#image-generation-and-editing)
continue to apply.

Status and administration use deterministic software and typed lifecycle
operations. Models reason and request permitted tools; they do not own lifecycle
authority. Current operations retain their ownership, admission holds, leases,
confirmation and recovery boundaries; see [operator guidance](https://github.com/djeZo888/mixed-memory-llm-api-server/blob/feature/system-topology/ai-harness/README.md#operator-use)
and the [control contract](https://github.com/djeZo888/mixed-memory-llm-api-server/blob/feature/system-topology/docs/control-api.md).

## Accepted future model and routing design

The following logical entities are design requirements, not an implemented
configuration schema or API:

| Entity | Responsibility |
| --- | --- |
| ModelDefinition | Logical identity, family/version, general-purpose or specialist role, capabilities, context limits, and quantization/runtime compatibility policy. |
| ModelInstance | One loaded runtime endpoint of a ModelDefinition, its health and free/busy state, admitted capacity and owning node. Readiness and free capacity are separate observations. |
| Node | A host or VM's placement, resources and runtime/storage/network prerequisites, independent of model identity. |

The design supports multiple general-purpose and specialist ModelDefinitions,
each with N compatible ModelInstances on suitable nodes. A different version or
quantization is not automatically interchangeable: the definition's explicit
compatibility policy must permit it. Configuration and current observations must
remain distinct; an unknown instance is not proven healthy or free.

One configured delegation model **MUST be general-purpose, never an image
specialist**. Each delegation selects a healthy, compatible, free instance of
that same configured model. If none is free, it queues under a bounded, fair
policy with cancellation, deadlines and explicit overload/unavailability
outcomes. There is no silent fallback to a different model. Specialist tools
select only definitions compatible with their operation; an image tool does not
become a general-purpose child agent.

Deterministic code must validate requested context, capabilities and
quantization/runtime compatibility before admission. Shared global admission
must account for GPU, RAM and instance capacity across colocated workloads to
prevent oversubscription. Main sessions and all subagents use the same routing
and admission authority, including auxiliary calls; adding agents or harness
replicas must not multiply the admitted slots. This is a future contract, not a
claim that today's fixed gateway implements a general resource scheduler.

In this future design, "free" must come from shared authoritative admission and
leases, never readiness alone or a racy status-page sample. Reserve capacity
atomically across harness replicas. Release the inference slot before awaiting
subagents so a parent cannot retain capacity needed by its children. Unknown
capacity is not idle.

An optional model recommendation may propose a suitable model. Deterministic
software validates the choice and permitted operation; a recommendation cannot
grant administrative permissions, bypass admission or trigger arbitrary host
actions. Lifecycle control remains deterministic software.

## Placement and horizontal scaling

The current deployment places chat, agents, tools, gateway, data and status on
the ai-harness VM, and text/image inference plus model control on the ai-vm VM.
Logical roles do not require that split. A compatible single host/VM can colocate
services; future deployments may use many VMs and multiple instances per model.
Those placements need explicit deployment work and accepted resource capacity:
compatible CPUs/GPUs/RAM, pinned runtime/driver/model versions, registered guarded
storage, ordinary task users and containment, protected credentials, private
transport and approved network/security policy. This document qualifies no new
placement or capacity.

A load-balancer layer is **FUTURE / OPTIONAL — not deployed**. It is an optional
logical extension, not an always-required hop or a substitute for shared
ownership. Horizontal harness scaling first requires:

- Explicit session/run/workspace ownership so two replicas cannot execute or
  mutate the same work concurrently.
- Shared durable metadata and artifacts with consistent history, file access
  and recovery; today's local storage is not a distributed data layer.
- Consistent gateway admission, cancellation, response drain and reconnect
  behavior across replicas, with durable uncertain-operation recovery and no
  silent replay.

MiniMax is not claimed to be distributed today. Adding a load balancer alone
does not deliver these properties or establish performance.

## Registry and evidence boundaries

The [registry](https://github.com/djeZo888/mixed-memory-llm-api-server/blob/feature/system-topology/ai-harness/config/system-registry.json) and its
[loader](https://github.com/djeZo888/mixed-memory-llm-api-server/blob/feature/system-topology/ai-harness/server/src/system-registry.ts) provide the existing
observation and placement foundation. Node observation transports are consumed
from configuration, while workload endpoint references remain informational;
current inference consumers retain their existing bindings. Registry edits do
not move workloads/data, implement model selection or grant lifecycle actions.
Follow the [H006 configuration and extension guide](https://github.com/djeZo888/mixed-memory-llm-api-server/blob/feature/system-topology/ai-harness/docs/status-registry.md)
for the actual credential, observer and action boundaries.

The [H006 closeout](https://github.com/djeZo888/mixed-memory-llm-api-server/blob/feature/system-topology/docs/h006-closeout-20260926.md) and
[dated topology plan](https://github.com/djeZo888/mixed-memory-llm-api-server/blob/feature/system-topology/docs/system-topology-plan.md) retain their historical facts,
including the then-undecided name and enabled package updates. H007 selects Sova;
the [manual-update policy](../TODO.md#immediate-h007-policy) is now verified on
the two current VMs. The linked policy report defines its actual coverage and
limitations. This architecture document remains a design contract, not acceptance
of a distributed deployment or new routing implementation.
