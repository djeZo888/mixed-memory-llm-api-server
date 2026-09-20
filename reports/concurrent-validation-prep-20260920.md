# Closed candidate validation PREP — 2026-09-20

Source-only implementation from integrated base
`4064d149d772e3a2d10e00fd19d278dad8da0a57`, with the separately root-approved
LongPREP commit `efa224e76de3d71e586fcdc15639436d38239fcd` merged as an ancestor.
No VM/Proxmox/Worker2 contact, live lease, image fixture, inference, deployment,
push or measurement clock occurred. The separately dispatched LONGRUN remains
the sole VM writer; its checkout/arm/task were not changed.

The closed helper is `scripts/benchmark/concurrent_validate.py`. It admits only
production GLM480000/GPU0/96CPU/640GiB and Qwen700160/GPU1/16CPU/32GiB no-swap
manifests. It reuses canonical ownership/storage, native count/allocation,
protected evidence, local real tools, client timings and LAN restoration seams.
Production lifecycle/control/runtime/deployment source bytes are unchanged.
Neither this helper nor its fixture can publish production acceptance.

Reviewed corrections included: exact schema-constrained smoke bodies with no
answer constants; native counts hash those actual schema bodies; durable
not-dispatched versus uncertain create state at the subprocess boundary;
empty inventories cannot settle dispatched uncertainty; source/GO-bound saved
execution; and recovery-only output cannot upgrade validation to PASS.

Candidate pressure uses the exact shared `concurrent_host_demand` and
`LinuxHost.concurrent_pressure` from approved LongPREP. It preserves sampled
ESTIMATE/UNAVAILABLE, native historical/current floor provenance, raw current
and peak, unknown reclaimability and numeric latches. The candidate adds both
remaining-cap obligations, disjoint anon+no-swap-shmem credit, explicit no-swap/
OOM checks and Qwen10% comparison. No alternate formula or profiler was added.

Focused verification:65 candidate/fixture tests,15 selected production acceptance,
native-capacity, shared-demand, ownership/recovery and transport regressions,
plus3 final candidate-evidence/scope checks: **83 PASS**. Initial preflight-order
and schema/scorer integration failures were corrected and rechecked. Separate
subtask receipts also exercised the old pinned fixture hashes; no full601/150
suite was invoked. Source compilation, inert CLI help and whitespace checks
passed. All tests use local/synthetic observations and establish no live proof.

The pair auth fixture is a small facade over unchanged, production-pinned
fixture files. It executes the exact production pair binding and requires all19
`AUTH_CHECKS`, actual pinned-image inspection,700160 ModelConfig resolution and
verified fixture cleanup. Actual-image execution has NOT occurred. Its receipt
keeps synthetic model/parser work distinct from loaded-model capacity and real
client tools. See `tests/lifecycle/sglang38_fixture/PAIR-README.md`.

Future root review/dispatch details: `docs/concurrent-candidate-validation.md`.
The task directory contains the exact final commit, local bundle, review diff,
clock-free arm and non-authorizing GO template, test outputs and SHA256 receipt.
Root still needs the current benchmark's restored/released ownership, actual
image auth proof, fresh capacity/resource/schema/tool/timing evidence, and final
LAN/closure restoration proof. Production-default GLM allocation logging may
fail closed if required facts are unavailable; no logging/default override is
allowed. Accepted-receipt interpretation of raw peaks versus required estimates
remains an explicit later root decision, not an invented receipt here.
