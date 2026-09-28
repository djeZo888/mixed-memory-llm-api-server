# H020 — status identity repair and Codex harness planning

## Scope

1. Fix incorrect GLM labels while MiMo is selected/running. Derive status labels and placement from trusted configuration plus observed model identity.
2. Produce an implementation plan for a selectable Codex harness, retaining MiniMax. Do not implement Codex integration yet.

H019 near-950K MiMo is active. No inference, ai-vm mutations, workload restarts, selection changes or benchmark polling. Chat remains paused; status can be deployed independently.

## Initial findings

- ai-harness/config/system-registry.json describes nodes, services, observation transports, capabilities and endpoint references.
- active-frontier.json selects a model separately. system-registry.ts currently rewrites GLM/MiMo display names with hardcoded text.
- Status loads these at startup; H019 changed its unit/drop-in but deliberately did not restart the existing process. It can retain the earlier selection/release.
- The registry does not control every inference address or placement decision. Document this boundary rather than claiming otherwise.

## Bounded execution

- Worker2: trace live status deployment; repair registry/projection/UI identity, add focused configuration-change/missing-node/selected-model checks, prepare isolated status-only release and exact deployment diff.
- Worker1 in parallel: review source and passive DTO model/GPU mapping, identify hardcoding and stale-selection risks, independently verify Worker2 patch/tests. No ai-vm mutation or inference.
- Root: source/result review, publication and Codex architecture plan/research.
- Deploy status only after exact patch review. Confirm API and rendered labels using passive observations; no admin actions.

## Acceptance

- MiMo shown as active frontier with observed GPU/node binding. GLM never inherits MiMo readiness; any retained GLM catalog row is explicitly dormant.
- Names follow registry edits without model-name conditionals in UI.
- Missing/stale backends remain unknown/unavailable; no synthetic readiness.
- Multiple instances remain distinct; unsupported configured nodes stay visible.
- Endpoint references and hardware bindings are coherent and documented; secrets never enter public DTOs. Inventory grants no new admin authority.
- Model/benchmark owner untouched; ordinary chat stays paused.
- Codex deliverable is a plan only, with compatibility gates, phases and acceptance.
