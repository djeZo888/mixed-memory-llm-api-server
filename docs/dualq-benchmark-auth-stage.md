# Dual-Q actual-image auth stage — command proposal, not execution

Prepared in native task `DUALQ-BENCH-PREP-20260921`, session
`01a0c17f-962e-70f1-8411-f65ffa187d3f`, from production candidate
`f130ec46ebd9a27319d84e0d372746e0489a9972`. No VM contact, fixture/container
execution, receipt acceptance or production activation occurred in PREP.
The future RUN source/arm and this finite fixture stage require root exact-source
review. Production source, profiles, native fixture and provenance stay unchanged.

## Ownership and order

The fixture drivers create Docker containers but do **not** acquire a lifecycle
lease themselves. No reviewed coexistence/adoption interface exists for the
retained keeper. Run this stage **after canonical old-owner RELEASE and fresh
STOPPED/manual plus lease-free proof, before any new Qwen load**. Never call the
fixture CLIs beside the old keeper merely because they use no GPU.

Bind release to `REAL72-FOLLOWUP-B3-RUN-20260920`: campaign
`benchrun-p72b3-20260920`, source
`b69bd5c2a34adb462ee87333e2a238bd1c05436d`, native session
`01a0c0b6-2901-7943-acbd-dd02d87b7e29`, keeper/SSH `71966/71972`, remote owner
`1292520` with start ticks `2770655`, historical lease device/inode `[26,1989]`,
and exact containers:

- G: `9e494eaaa089ffe9fb41e2052d0456e8c5c5b3b8384077d92d4a55147c61747a`
- Q: `2306a57bd1b5f984185a7c11056d1b32d01c6798d6d89d00044e24189eba7ccf`

The private task root is
`/Users/agent/CodexProjects/llm-orchestration/tasks/REAL72-FOLLOWUP-B3-RUN-20260920`.
Its saved `release.template.json` was `NOT_AUTHORIZED`; the submission path is
`release.json`. Refresh and review the existing template, warm-hold SHA256,
run-control/status and actual identities when evaluating the release chain.
Do not fabricate a release here, signal a PID, remove either container directly,
or acquire/adopt the old owner's lease. Preserve the original receipts off VM.

Updated local snapshot: `run-outcome.json` and `final-restoration-receipt.json`,
mtime2026-09-21T03:10:53+02:00, now report restored true, STOPPED/manual and both
tunnels closed, with production acceptance `NOT_GRANTED`. These are saved
external-task results, not live verification by PREP. Review the root-approved
release chain and obtain fresh proof before proceeding; **do not re-release an
already restored owner**.

After release, require canonical `RESTORED`, selected/container/failure null,
desired stopped and boot policy manual, exact old containers/owner absent,
and canonical lock free. The freshly dispatched Worker1 controller must hold
the installed `common.lifecycle_lease.acquire_lease(blocking=False)` capability
for the whole guarded auth stage, including staging/output writes and cleanup.
The same-process capability is validated at boundaries; it is not an arbitrary
FD, a shell `flock`, or a bypass flag. Nested lifecycle helpers borrow it.
Release that scope only after verified cleanup, then permit the one reviewed
temporary Q/Q owner to acquire its own canonical lease. No production migration
or protected acceptance receipt is needed or allowed in this auth stage.

## Exact source, image and commands

Stage only the reviewed full source package at
`/data/services/benchrun-dualq72-20260921/source`; verify its final arm source map
before importing any fixture. Use the already installed image, never pull:

- Reference: `lmsysorg/sglang@sha256:37bbbd3444732a464bbc68dee4fb0164e0ce9e18e2f027f3fc967f1152d3c262`
- Config-image ID: `sha256:e6238090791a938ab86dd21a9a6394192dad15237e815df557cf83524d54b813`
- Native source: `0bcd822377da7b5718e674eaf9c870d349424dd1`
- Base launcher SHA256: `e507ed81d1e3954afea1d31eb9f0bc7ef7ab8b9a76bb571499e1a5f9c53c7da4`

The driver checks the actual image/OCI relationship and pinned native files.
Pair provenance binds both production profiles, model/runtime, base/pair
wrappers, fixture adapters and exact alias/port argv. Q0 selects
`qwen38-27b-q0-480000-yarn4-bf16kv`, `qwen3.8-27b-gpu0`, port30002;
Q1 selects `qwen38-27b-q1-480000-yarn4-bf16kv`, `qwen3.8-27b`, port30004.
These are fixture configuration identities; no host listener is published.

Run these existing commands sequentially **inside the lease/guard scope above**.
`EVIDENCE_DIRECTORY` is proposed as
`/data/logs/llmctl/dualq-auth-20260921`, admitted by the installed registered
binding and created through its anchored writer (root-owned0700). Each output
must be new; the driver publishes0600 and refuses replacement/symlink/rebinding.

```bash
set -euo pipefail
AUTH_SOURCE=/data/services/benchrun-dualq72-20260921/source
EVIDENCE_DIRECTORY=/data/logs/llmctl/dualq-auth-20260921
python3 -B "$AUTH_SOURCE/tests/lifecycle/sglang38_fixture/run_fixture.py" \
  --repo "$AUTH_SOURCE" --profile native-pair \
  --output "$EVIDENCE_DIRECTORY/q38-base.actual-image-auth.json"
python3 -B "$AUTH_SOURCE/tests/lifecycle/sglang38_fixture/run_pair_fixture.py" \
  --repo "$AUTH_SOURCE" --slot gpu0 \
  --output "$EVIDENCE_DIRECTORY/qwen-gpu0-480000.actual-image-auth.json"
python3 -B "$AUTH_SOURCE/tests/lifecycle/sglang38_fixture/run_pair_fixture.py" \
  --repo "$AUTH_SOURCE" --slot gpu1 \
  --output "$EVIDENCE_DIRECTORY/qwen-gpu1-480000.actual-image-auth.json"
```

The base command checks131072 and262144 in two disposable lifetimes; each pair
command checks480000 in one lifetime. The existing bound is600s **per lifetime**,
plus bounded creation/inspection/cleanup, not600s for all three commands.
Use the existing controller's private stdout/stderr capture under the registered
evidence directory; raw diagnostic streams remain0600/off Git and are copied
with receipts to private Worker1 task evidence before any later cleanup.

## Existing guards, resources and cleanup

Before and after each command and all registered writes, refresh installed
source identities and use the current installed guard, never a checkout helper:

```bash
/usr/bin/python3 -I -B /usr/local/lib/llm-server/control-api/scripts/common/registered-storage.py --json
/usr/bin/python3 -I -B /usr/local/lib/llm-server/control-api/scripts/common/registered-storage.py --json --root-guard
```

Enforce the registered root-owned `/etc/local-ai-server/storage.json` binding:
data `/data`, ext4 UUID `8daf56f1-5649-4163-9d87-919c2d271875`; models
`/data/models-large`, ext4 UUID `a6d4ab58-84e1-4e48-9a67-13ad1c6f6e0a`.
The current root-reviewed installed identity receipt governs; historical config
hashes alone do not establish that installed code is unchanged. Require root
payload scan PASS and exact protected operation paths. These are read/guard
commands; their output must be checked, not just an exit code recorded.

Proposed stage admission also observes the current72 online CPUs/eight guest
nodes, current available RAM/root headroom and absence of unexplained active
work. Reserve at least1.15 times the fixture's8GiB memory allowance in available
host RAM; stop on missing or unsafe observations. Record the same observations
after each fixture. This is a fixture-stage admission proposal, not measured
Qwen working-set evidence or a change to the benchmark's15% estimate policy.

The unchanged driver inspects8GiB memory,128 PIDs,64MiB shared memory, no restart,
read-only root and source, capabilities dropped, no-new-privileges and core1:1.
CPU controls are **only** `OPENBLAS_NUM_THREADS=1` and `RAYON_NUM_THREADS=1`;
it does not configure CPU quota/affinity. Do not claim the model's sharedQ8 mask
applies or that host `taskset` constrains Docker. Run one fixture at a time after
keeper release under this disclosed existing CPU contract.

Network mode is `none`, no published ports/host namespace; no GPU/device
requests, `NVIDIA_VISIBLE_DEVICES=none`, empty `CUDA_VISIBLE_DEVICES`, and actual
driver enumeration must find zero GPUs. NVIDIA runtime only supplies existing
driver libraries/control nodes. No profiler, driver change, download or weights.
`/models`8MiB, `/run/secrets`1MiB, `/cache`1GiB and `/tmp`256MiB are private tmpfs;
only synthetic config/key/template data exists. No production key is read or
mounted. The fixture captures Uvicorn/model startup and uses synthetic engines;
it performs native auth/parser/cache checks, never model inference.

Cleanup is the existing exact-container-ID/ownership-token path, including
ordinary timeout/cancellation: bounded stop, quiescence and removal must report
`QUIESCENT_REMOVAL_VERIFIED`. Daemon loss, identity mismatch, SIGKILL/host loss or
unverified cleanup blocks the next stage; reconcile that exact owned container,
never prune or delete by reused name. Retain failure evidence and STOPPED/manual
intent. A missing or failed receipt cannot be promoted to PASS or auto-retried.

Validate fresh base proof with existing base receipt checks and both pair proofs
with `check_pair_receipt(..., slot='gpu0'/'gpu1')`; bind each protected registered
path and raw SHA256 into the final RUN arm. Local content validation is not proof
of trusted publication. Native pool480000, GPU UUID/placement, actual request
bounds and working-set safety still require the later loaded-model observations.
Model/native-lifespan/live-client acceptance stays `NOT_TESTED` here.

## Byte-preservation check for root packaging

Compare against `f130ec46ebd9a27319d84e0d372746e0489a9972`: all production
`scripts/lifecycle`, `scripts/control`, `scripts/runtime`, `configs/models`,
`configs/runtimes`, `configs/deployments`, and `tests/lifecycle/sglang38_fixture`
must have an empty diff. Include unchanged storage/lease helpers and D1 rollback
pins in the source identity check. Benchmark-only wiring and this command plan
do not attest production deployment; any concrete integration delta outside
that boundary requires an explicit root-reviewed source receipt.
