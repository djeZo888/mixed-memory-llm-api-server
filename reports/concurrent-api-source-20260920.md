# Concurrent production API — Worker1 source handoff

Historical handoff at `862ea01`: its two-empty-inventory reconciliation and
anon-only resident credit are superseded by the
[final review correction receipt](concurrent-api-source-final-seams-20260920.md).
The 601 checks below describe the prior implementation only.

Status: **source candidate complete; activation unaccepted**. Tested implementation
commit `6ccc3b53c9da472b38bfafb836621bdcb44abdc1`, based on `a2186a4a5417e980f9560807da942d7272e055d5`. Fresh native session
`01a0bdbd-0467-7430-ae53-12cb90bc8a30` on **mac-worker1** in the isolated
`CONCURRENT-API-SOURCE-20260920/repo` checkout. No ai-vm/Proxmox/Worker2 contact,
live lease, inference, deployment, service restart, model/image download, push,
installer implementation/composition/tests, or benchmark checkout mutation.

## Candidate change

- Explicit schema-3 fixed GLM/Qwen slots, independent desired/observed state,
  generation, immutable deployment/container identity and boot intent. Migration
  first protects the original v2 state, source/boot attestation and singleton
  control journal in `active/pre-slots-v2.json`; no API-side implicit migration.
- Existing global lease, registered storage/anchored writer, mutation executor,
  idempotency journal, keys, aliases and private endpoint policy are retained.
  Targeted start/switch/stop/restart preserve the peer; ambiguous legacy mutations
  fail clearly. The catalog exposes separate endpoint/readiness and declared,
  accepted configured, and occupied-context metadata.
- Closed candidate G1/Q1 profiles pin UUIDs, disjoint guest CPU sets, runtime,
  weights, cache/defaults, ports and no-swap caps. GLM **480,000** and Qwen
  **700,160** are **UNVALIDATED** declarations. No live receipt was created.
  TP2/1M profiles remain explicit mutually exclusive alternatives.
- Root-review corrections: pending create is persisted before Docker create;
  returned ID is saved before inspection. Canonical stop reconciles the exact
  planned name, requiring two successful absence snapshots before clearing only
  its pending intent. Errors/mismatches retain ownership. Selection immediately
  refuses unresolved pending state. A delayed daemon create after a snapshot is
  still possible; subsequent unknown-owner/name admission remains fail-closed.
- Start/create/reuse requires current host/GPU memory admission using freshly
  inspected resident identities, cgroup anonymous memory and zero swap, without
  double-crediting reclaimable cache. Current native allocation metadata must
  establish the actual GLM context or Qwen pool/input limit before Ready; argv,
  saved receipts and health/alias alone cannot. Native observations are bound to
  the same trusted container/start identity; concrete safe failures remain visible.
- The single boot owner replays GLM then Qwen explicit resume intents; partial
  failures retain both identities and process the independent peer. Docker
  restart stays disabled. Both recovery-source protection closures are updated.
- Read-only rollback prerequisites require exact new-container absence, current
  operation drain, backup/source/storage identity agreement and no untracked
  owners. Only an exact untouched stopped original container may be retained.
  Restoration remains a root-reviewed manual procedure through canonical lifecycle.
  Future singleton benchmark owners reject migrated slot state; the running
  benchmark's checkout/source/arm was untouched and was not integrated here.

## Final source checks

`python3 ../run-source-checks.py` at the implementation commit above:

| Group | Passed | Failed / errors / skipped |
| --- | ---: | --- |
| Lifecycle/profile/boot/recovery/native capacity | 368 | 0 / 0 / 0 |
| Control API/CAS/journal/catalog/source protection | 200 | 0 / 0 / 0 |
| Future benchmark admission/restoration boundary | 33 | 0 / 0 / 0 |
| Total executions | **601** | **0 / 0 / 0** |

These are synthetic Worker1 checks, including actual Manager/ManagerSession
logic with controlled dependencies. They establish no live inference, occupied
context, stream survival, systemd/reboot or rollback acceptance. No installer
suite ran. The control source-protection checks exercise existing startup file
validation only. Whitespace and scoped diff secret-pattern scans passed.
A retained Python 3.14 multiprocessing fork deprecation warning did not fail
checks. The auxiliary aggregate runner's initial import-path/main-guard errors
were corrected; their logs and the final clean receipts are retained separately.

Durable task artifacts (alongside the checkout): `session-id`, `status.json`,
`status.md`, `working-source.diff`, `source-manifest.json`, `test-receipt.json`,
`run-source-checks.py`, `*-final-source-tests.log`, per-owner status and logs.
Final packaging adds `candidate.diff`, `candidate-summary.txt`, `rollup.bundle`
and `bundle-receipt.json`. The bundle includes this API task's commits only,
with the reviewed base as prerequisite; no push or cross-task cherry-pick.

## Root activation decisions and next actions

1. Review favorable benchmark performance/correctness/resource evidence and
   freeze accepted GLM/Qwen configured capacities, largest occupied contexts,
   Qwen host cap (currently provisional 32 GiB), and measured margins. A changed
   capacity/cap requires a newly reviewed closed profile; no arbitrary launch args.
2. Validate the additive Qwen wrapper's actual native auth checks, current cgroup
   and metadata shapes, and requested native pools in the separate activation
   workflow. Supply the protected receipt and instance digest/source binding
   described in [the evidence contract](../docs/concurrent-profile-acceptance.md).
3. After the live benchmark restores singleton production, integrate benchmark
   PREP and API commits in a **fresh Worker1 copy**, run affected checks and review
   the combined source. Do not move or modify live RUN source while executing.
4. In a separately authorized activation session, refresh installed source/guard
   identities, preserve protected prior source/recovery/state/control-journal/
   boot snapshots, drain control, explicitly migrate, and use canonical lifecycle.
   Keep credentials, storage registration, original Qwen TP2 and D1 rollback
   evidence intact. See [migration/rollback](../docs/concurrent-api.md).
5. Prove simultaneous authenticated private endpoints/aliases, missing/wrong-key
   and wrong-model denial, streaming, schema output, tool continuation, targeted
   restart during a peer stream, control restart persistence, both-slot boot
   replay and exact rollback. Label physical reboot acceptance separately if
   unexecuted. No source test or declared capacity closes these live gates.

Exact endpoint/body examples: [control API](../docs/control-api.md).
No unresolved source implementation blocker is claimed closed by a live receipt;
all live decisions above remain root-owned and pending.
