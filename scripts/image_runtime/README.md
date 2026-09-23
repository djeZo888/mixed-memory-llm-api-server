# Qwen-Image 2.1 runtime owner

This directory contains the bounded native runtime and its worker-only request
and telemetry helpers. It does not implement the public image adapter or establish
image acceptance. Live readiness, measured memory margins, decoded outputs and
visual results belong to the task's current receipts and handoff.

## Fixed ownership and storage

`llm-image-backend.service` is the only systemd owner of container
`llm-image-backend`. `service.py` runs as root to validate protected configuration,
use installed storage guards and perform narrowly scoped Docker mutations. The
native container runs as UID1000:GID1001, with Docker restart policy `no`, CPU8-15,
a96GiB memory cap and equal memory/swap limits. It uses only Ada UUID
`GPU-5d895991-b794-2b4c-b9c4-5f1b668afd23`. Text model ownership, contexts,
containers and state remain with the existing text lifecycle.

The protected runtime root is
`/data/services/image21-runtime-20260923`. Its `config.json` binds the immutable
image ID, checkpoint receipt, owned Docker network ID and installed Python source
hashes. The source pins are SGLang `0cd8be351d0825488f4b81c8931167bbab618eca`
and Qwen-Image2.1 checkpoint
`790c92633540aa0cb11d9abf19eb46d861714758`. Actual dependency/image identities are
read from the reviewed runtime/build receipts, not inferred from these filenames.

The one authorized SGLang repair is consumed: the seven-line patch
[`patches/sglang-nvml-uuid.patch`](patches/sglang-nvml-uuid.patch) resolves a full
`GPU-` visibility value through NVML before returning the current physical index.
Numeric/unset behavior is unchanged, and UUID lookup errors propagate without
fallback. The patch SHA256 is
`9522814f5c5c1ccc0e3fc1704172b9249f2551a755a4a70f5397d7e439008c6e`;
the exact before/after hashes are recorded in
[`patches/sglang-nvml-uuid-repair.json`](patches/sglang-nvml-uuid-repair.json).
The derived image ID is
`sha256:dafbccb763cff6a6aa3777c7c0a8cc185d838bd4b9f61bec8007f57f2c7233f8`.
The original image and first-failure evidence are retained. Packaging/cache
bootstrap fixes and the container network correction below are separate from
this single pinned-runtime repair; they do not authorize another runtime repair.

The authoritative `/etc/local-ai-server/storage.json` and installed registered
storage/root-disk guards determine usable mounts and roots. Persistent service
state and telemetry use anchored storage APIs. Native cache, evidence and
invocation-specific temporary files are under the registered runtime root; the
checkpoint is under the registered model root. No credentials are passed in
command lines, and no model/image pruning is part of this owner.

## Reset and warm interface

The sole adapter-facing privilege boundary is the root-owned executable:

```text
/usr/local/libexec/llm-image-backend-recover
```

It accepts **no arguments**. The API task owns an exact allowlist for this helper;
it must not grant broad `systemctl`, Docker or arbitrary script privileges. No
HTTP payload controls a command, path, image, unit, device or launch argument.

The boundary validates and settles only the container whose full ID, image,
owner/invocation labels, name, Ada assignment and resource policy match protected
state. It removes that container, then restarts the fixed backend unit. Mutations
use the existing canonical `/run/llmctl/lifecycle.lock`; the helper releases its
lease before invoking systemd because the unit takes that same lease in a separate
process. Callers must not hold the lease while invoking the helper.

The unit waits for native HTTP readiness, issues one deterministic warm generation,
and verifies decoded output, owned Ada residency, sampled device/host headroom and
absence of observed container swap. Only then is protected state marked warm and
the boundary allowed to return success. Raw native `/health` alone is not this
admission signal. Failure stays unready and does not trigger an automatic retry.
Recovery tries exact-unit stop/kill and exact-owned Docker settlement; it never
uses a broad process kill or touches a text container.

Deadline budgets are measured from the relevant process entry:

| Boundary | Active budget | Settlement / outer limit |
| --- | --- | --- |
| Fixed recovery helper |840s across reset, restart and verification |remaining budget to900s for failure settlement |
| Systemd backend start process |775s |settlement to835s; unit `TimeoutStartSec=840` |
| Backend stop process |100s command budget |unit `TimeoutStopSec=120` |
| Worker native request helper |840s request alarm |service caller further caps its Docker-exec wait to the remaining start budget |
| Telemetry child termination |SIGTERM and5s wait |exact child kill and2s wait; unsettled outcome is retained |

Subprocess timeout or client disconnect is not proof that inference stopped.
The owner must inspect/settle the exact workload and preserve failure state. These
budgets do not promise preemption of an uninterruptible kernel/driver operation.

## Boot and API ordering

The backend unit is installed **disabled**. Its `WantedBy` section is not an
instruction to enable it independently. It is ordered after `llmctl-boot.service`
and depends on the registered data/model mounts; an `After` relation establishes
ordering, not proof of text readiness.

The eventual sole enabled image boot owner is the separately owned
`llm-image-api.service`. On API startup and after its900s upstream timeout, the
adapter must close admission and invoke the same no-argument reset/warm boundary.
Admission remains closed until that boundary succeeds. This directory does not
claim that the adapter has been installed or qualified. There is no SSH keeper,
Docker auto-restart owner or competing image boot start.

## Native launch and worker requests

The container uses the dedicated ordinary Docker bridge
`llm-image-backend-private` (`Internal=false`), with the sole published mapping
`127.0.0.1:30007:30007/tcp`. `native_server.py` binds HTTP to `0.0.0.0:30007`
inside that container namespace. The host readiness and eventual adapter endpoint
remain `http://127.0.0.1:30007`; the worker request helper uses container-local
`127.0.0.1:30007`. Ports 30008, 30009 and 30010 are unpublished. In particular,
PyTorch's wildcard TCPStore listener on 30009 stays inside the container network
namespace. Docker manages the bridge's own networking rules; this owner adds no
ad hoc host firewall rule and changes no text network.

Protected configuration binds the network's full ID. Startup/residency checks
require its exact name, owner label, local bridge driver and `Internal=false`,
reject foreign network members, and require the backend's sole attachment to
that ID. Container checks require exactly the loopback port mapping in configured
bindings and, while running, effective bindings. The owner does not adopt or
recreate a missing or conflicting network during recovery.

A GPU-free probe on the installed Docker 29.6.1 showed that a dedicated
`--internal` bridge retained the requested binding in `HostConfig.PortBindings`
but returned `{"30007/tcp": null}` in `NetworkSettings.Ports`: the in-container
dummy server answered while host loopback refused the connection. The selected
ordinary bridge supplies the required published endpoint. It does not restrict
container outbound traffic or host access to the container's private IP. The
network is reserved for the exact owned backend; attaching another container is
outside this interface. Live listener checks and external refusal evidence
belong to the deployment receipts, not these source assertions.

Changing from host networking requires settling/removing the old exact owned
container with the old policy checks before installing the new network checks,
then one cold load and the fixed warm generation. Retain the earlier generation
and diagnostics. This is a deployment configuration correction, not a PyTorch
patch or an additional model/runtime repair.

The pinned SGLang launch requests all components resident, native BF16/FP32,
`torch_sdpa` and eager execution. CPU offload, synthetic startup warmup, approximate
caches, compile/graph tuning and VAE tiling/spatial parallelism are disabled. Empty
output/input path CLI values resolve to disabled persistence in the pinned server;
per-request temporary files use the invocation's registered TMPDIR.

The worker-only `native_request.py` accepts only `--mode generation|edit` and a
32-character lowercase hexadecimal `--run-id` naming a pre-created owned evidence
directory. Each mode has one attempt per invocation: existing attempt artifacts
cause refusal before another HTTP request. Generation is fixed at1024x1024, n1,
40steps, CFG1, seed42 and PNG b64 output. Editing uses the decoded generation PNG
and validates its summary/hash linkage before sending one reference. It does not
download an input or retry a failed request.

Each attempt retains its private request, raw response, summary, decoded PNG when
available and native performance trace when supplied. A transport/decode pass
explicitly leaves visual verification `NOT_TESTED`. Native peak reserved allocator
memory is reported separately from sampled device memory. A warm output can serve
as the generation baseline only after the task owner verifies the required
settings, telemetry and actual image visually; no duplicate equivalent inference
is required by this helper.

Invocation evidence and failure diagnostics are retained across reset. Temporary
cleanup occurs only after the exact owned backend has been removed and targets
only that invocation's temporary directory. It does not remove retained evidence,
other invocation directories, model weights or shared runtime caches.

`telemetry.py` samples the fixed Ada at200ms and bounded host/cgroup counters at1s.
The guarded caller passes an already-open private output descriptor and keeps its
anchor alive. The sampler never opens an output path for writing. Native return
codes, missing metrics, timing gaps and skipped sample slots are recorded; sampled
extrema are not continuous, per-process or allocator peaks.

## Known fail-closed condition and offline checks

If Docker creates a container but the create response or subsequent ID persistence
is interrupted, protected state can remain `creating` with no recorded full ID.
The fixed recovery boundary then refuses the unrecorded named container. This
condition occurs before this owner starts inference and requires a fresh exact
ownership diagnosis. Do not adopt or remove a container by name alone, guess an
identity, or retry around the refusal. A pending-create reconciliation extension
is not implemented here.

From the repository root, run the source-only service checks with:

```sh
python3 -B -m unittest discover -s tests/image_runtime -p test_service.py -v
```

The suite uses offline command/process mocks to check fixed arguments, ownership
rejection, Ada isolation, deadline caps and timeout/child-settlement branches. Its
shell check supplies an extra argument and exits before the VM helper can execute.
It performs no VM, Docker, systemd, NVML or inference work. Passing it does not
establish deployed permissions, real process settlement, warm residency, visual
success, supported resolutions, public transport or full API acceptance.
