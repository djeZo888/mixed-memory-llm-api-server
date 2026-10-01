# Sova TODO

This is the compact index of future work. A linked plan describes intended work;
it does not establish that the feature is implemented or deployed.
Current release evidence remains in the [project README](../README.md).

- **[context compaction reliability](context-compaction-reliability.md)** —
  first priority: Qwen baseline, exact technical retention, repeated cycles,
  durable source recovery and fault handling.
- **[technical image understanding](technical-image-understanding.md)** —
  drawings, schematics, diagrams and technical documents through a specialist
  image-to-text tool; model research recorded, deployment pending.
- **[Project mode and durable project memory](<../docs/Vision for future regarding this project.md#4-project-mode-orchestrator-and-bounded-workers>)**
  — accepted future direction; minimal task briefings, separate worker contexts,
  ownership and reviewed integration.
- **[agentic API and headless Linux workers](<../docs/Vision for future regarding this project.md#5-headless-linux-workers-and-a-public-agentic-api>)**
  — accepted future direction; durable remote shell/file jobs and scoped tools.
- **[status service improvements](status-service-improvements.md)** — planned:
  readable tabs and tables, configurable multi-host sensors, encrypted BMC
  credentials, and a system-wide inference pause that preserves running services
  and resident models.
- **improve fan management service** — [H040 narrow GPU thermal policy](../reports/h040-fan-artifact-live.md) has configured lifecycle readback; hot thresholds remain untested. Broader investigation and detailed plan pending;
  separate monitoring credentials from fan-control authority, and support
  qualified GPU, chassis, CPU and pump controls across providers.
- **critical handling and system notifications** — detailed plan pending;
  notifications, software incidents, acknowledgement and controlled temporary
  exceptions beyond the hardware safety foundation in the status plan.
- **[organizations, users, permissions](../TODO.md#future-organizations-and-access-control)**
  — tenant, conversation, artifact and administration boundaries.
- **[load balancing and horizontal scalability of the selected harness](../TODO.md#future-routing-and-scaling)**
  — organization ownership, shared admission, durable state and horizontal
  harness replication; the older MiniMax-specific backlog remains historical.
- **[general model routing and multiple instances](../TODO.md#future-routing-and-scaling)**
  — configurable models, instance placement, compatibility and delegation.
- **[maintenance windows, snapshots and rollback](../TODO.md#future-controlled-maintenance-software)**
  — controlled OS/package/Sova updates; retain the current manual-update policy.
- **[current image workflow qualification](../reports/h038-checkpoint.md)**
  — deferred on 1 October in favor of compaction; the H038 gate remains closed
  and its prior successful and failed evidence is preserved.
- **[programmatic CAD and specialist extensions](<../docs/Vision for future regarding this project.md#7-cad-through-geometry-and-programmatic-tools>)**
  — research direction; geometry APIs, deterministic validation and qualified
  format handling.
- **general installer** — deferred until the deployed system and its supported
  configurations are qualified; existing narrow deployment scripts are separate.

[Dated completion records and earlier backlog](../TODO.md) are retained without
rewriting their historical outcomes. Future tasks may be listed here before
their detailed plans exist.

The [future vision](<../docs/Vision for future regarding this project.md>)
records organization-centered permissions, selectable service placement and
AI-authored first-party development. Codex/MiniMax interoperability is no longer
a requirement; do not remove the existing engine or conversations without a
separate retirement plan.
