# Sova TODO

This is the compact index of future work. A linked plan describes intended work;
it does not establish that the feature is implemented or deployed.
Current release evidence remains in the [project README](../README.md).

- **[status service improvements](status-service-improvements.md)** — planned:
  readable tabs and tables, configurable multi-host sensors, encrypted BMC
  credentials, and a system-wide inference pause that preserves running services
  and resident models.
- **improve fan management service** — investigation and detailed plan pending;
  separate monitoring credentials from fan-control authority, and support
  qualified GPU, chassis, CPU and pump controls across providers.
- **critical handling and system notifications** — detailed plan pending;
  notifications, software incidents, acknowledgement and controlled temporary
  exceptions beyond the hardware safety foundation in the status plan.
- **[organizations, users, permissions](../TODO.md#future-organizations-and-access-control)**
  — tenant, conversation, artifact and administration boundaries.
- **[load balancing mechanisms and horizontal scalability of MiniMax](../TODO.md#future-routing-and-scaling)**
  — ownership, shared admission, durable state and horizontal harness replication.
- **[general model routing and multiple instances](../TODO.md#future-routing-and-scaling)**
  — configurable models, instance placement, compatibility and delegation.
- **[maintenance windows, snapshots and rollback](../TODO.md#future-controlled-maintenance-software)**
  — controlled OS/package/Sova updates; retain the current manual-update policy.
- **[current image workflow qualification](../reports/h038-checkpoint.md)**
  — remaining release gate; keep prior successful and failed evidence distinct.
- **general installer** — deferred until the deployed system and its supported
  configurations are qualified; existing narrow deployment scripts are separate.

[Dated completion records and earlier backlog](../TODO.md) are retained without
rewriting their historical outcomes. Future tasks may be listed here before
their detailed plans exist.
