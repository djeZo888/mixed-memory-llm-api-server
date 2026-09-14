# Fresh Linux installer completion plan

Scope: reproducible Ubuntu 24.04 amd64 installation from this public repository to a ready local inference service and working coding-agent client. The current user authorizes installation and GitHub publication; historical planning-only approval gates do not require fresh per-stage permission. Disk destruction still requires an explicit target and opt-in, and no public listener is implied.

This is a source review of the existing main snapshot, not an executed test. Model names/capacity targets below come from the current deployment plan; I1 must use D1's actually verified artifact/runtime identities.

## Existing components: reuse after adapting

- Reuse the storage/root-disk guards, Docker storage verification, NVIDIA container smoke verification, declarative model profiles, lifecycle manager, and worker-produced agent client.
- `require-data-mounted.sh` hardcodes ai-vm's UUID and label; fresh hosts require a registered UUID from root-owned installation state, not that global constant. Guards must fail closed on a changed/missing filesystem and cannot trust arbitrary environment overrides in installed services.
- `prepare-data-disk.sh` is specific to `/dev/sdb` and approximately 2 TB. Do not invoke it blindly or infer a destructive target from enumeration order.
- `vm-preflight.sh` requires Codex and noninteractive sudo, neither appropriate for an otherwise fresh inference host. The installer preflight needs only root or working sudo and documented Ubuntu base prerequisites; no cloud account/Codex subscription.
- Docker/toolkit scripts install available apt candidates, assume `/data` exists, and contain historical milestone text. Add exact version selection/availability checks and safe idempotency. Preserve existing Docker/containerd configuration, services, and data.
- Host NVIDIA driver installation exists as a report, not a reusable installer. Add an explicit supported-driver stage with boot/resume verification.

## Concrete public interface

Provide an executable `./install.sh` wrapper over a testable installer module; no curl-pipe-shell bootstrap. From a pinned release checkout:

```bash
./install.sh plan --profile flagship-hybrid --data-dir /data
sudo ./install.sh apply --profile flagship-hybrid --data-dir /data --yes
sudo ./install.sh resume --yes
./install.sh status
./install.sh verify
```

`plan` is read-only and reports support/capacity, chosen versions, data policy, stages, expected downloads, and restart/reboot effects. `apply` accepts a validated config file as an alternative to flags. Default storage mode uses an already mounted dedicated filesystem. Offer an explicit existing filesystem mount option (`--data-uuid UUID`) with backed-up fstab changes.

An optional blank-disk path must require `--initialize-empty-disk /dev/disk/by-id/ID --confirm-disk-id ID --yes`; plan records serial/WWN/size, and apply revalidates that same identity. Refuse signatures, partitions, LVM/RAID members, holders, mounts, root/boot ancestry, and ambiguous identities. Never offer an implicit overwrite of a populated disk. Handle NVMe partition names correctly. The live ai-vm uses existing storage only.

## State, pinning, and resumability

- Keep only a tiny root-owned bootstrap locator/config under `/etc/local-ai-server`; after mount, place installer state, artifacts, logs, backups, builds, caches, and service data under `/data`. No model/build/Docker payload may fall back to root.
- Use an exclusive installer/lifecycle lock. Store atomic stage records with schema version, installation ID, input/config hash, software lock hash, start/end/status, and sanitized error. Never mark a stage complete until its postcondition passes.
- Resume rechecks postconditions; it does not trust a completed marker or blindly repeat destructive work. Changes to disk identity or incompatible config fail closed with a concrete explanation. A second identical run is a verified no-op.
- Commit a version lock: Ubuntu compatibility, NVIDIA package branch/version, Docker/toolkit exact packages, runtime source commit or container digest, model repo+revision+filenames+size/hash manifest, quantization, Python/client dependencies, launch flags/template/parser. No `latest` or floating source checkout. If a pinned apt package is unavailable, fail clearly rather than silently change it.
- Resolve downloadable manifests and total required bytes before downloading. Resume partial downloads by the pinned identity; validate completion and hash/size before atomic promotion. Avoid duplicate model and Hugging Face cache copies where possible.
- Install a supported driver only when absent/incompatible; do not replace a working compatible driver gratuitously. Record `reboot_required`, exit with documented distinct code (e.g. 75), and print `resume`. Never reboot automatically by default. After boot require matching loaded module/userspace, both expected GPUs, and a successful GPU container check. Detect Secure Boot/module-signing intervention and report it precisely.

## Stages in order

1. **Preflight:** Ubuntu/architecture/kernel, root-or-sudo, package-manager locks, network/DNS, CPU/ISA, RAM, GPU IDs/VRAM/driver, root capacity, data identity/capacity, existing services/listeners, and current install ownership. No model mutation.
2. **Storage:** adopt the explicit existing filesystem or provision the explicitly identified blank disk; back up fstab, mount by UUID, create private service/secrets directories and all cache/build/log roots, register expected UUID, run guards.
3. **Base dependencies:** install the documented minimal tools and isolated Python/client environment. Place package caches and large temporary/build files under `/data` once it is mounted; bound unavoidable OS package/root usage.
4. **Driver and reboot checkpoint:** install locked compatible Ubuntu packages when needed, preserve rollback information, resume only after actual driver verification. No host CUDA toolkit unless the selected pinned runtime explicitly needs it.
5. **Container/build runtime:** adapt Docker/containerd installers to configure `/data` before first service start, preserve existing config, install locked NVIDIA toolkit, and verify GPU containers. For native runtimes, build/install the locked revision under `/data`; no unnecessary Docker dependency if the selected runtime is native.
6. **Model:** choose the capacity-compatible profile, fetch pinned weights, verify manifest and available space, install exact prompt/tool-parser settings. One active inference backend; do not silently downgrade model or quantization.
7. **Service:** create the selected deployment through one lifecycle owner, unprivileged where feasible; systemd ordering requires the data filesystem and verified runtime. Persist selected/stopped intent, enforce localhost binding, bound restart attempts/log growth/start timeout, and ensure stop/rollback are usable.
8. **Client/access:** install a runnable client and documented command, model ID, context/budget defaults, tool execution policy, and SSH tunnel helper. API remains localhost-only. Agent tool execution occurs as an ordinary client user inside an explicit workspace, never as installer root or inference service user. No cloud key is required for local inference.
9. **Acceptance:** health/live versus health/ready, listed model identity, bounded generation, streaming, structured tool call/result continuation, then a real client code-edit/test loop. Print a ready summary only when all selected required checks pass, with exact commands/locations and measured limits.

Secrets: public models should need no HF token. If a gated artifact requires one, accept a private file or interactive stdin; never put it in argv, state JSON, Git, generated command output, or logs. Reuse generated API credentials if the service uses them. SSH is the default encrypted/authenticated remote access path; a LAN gateway is a separate explicit configuration, with auth and its own tests.

## Hardware profiles and capacity decisions

- `flagship-hybrid`: current planned GLM-5.3 artifact about 435 GiB, mixed RAM+VRAM on the verified dual-96-GB GPU hardware. Derive minimum RAM and GPU reservations from D1's actual settings and observed peak, including model staging, CPU expert memory, GPU KV cache, workspace, and OS reserve. Do not equate model file size with required free RAM. A provisional 512-GiB-RAM class must pass those measured budgets before becoming a published minimum.
- `fast-gpu`: current planned Qwen 80B FP8 artifact, with exact repository/revision supplied by deployment. Publish the measured supported GPU topology, context and concurrency; approximately 80B FP8 weight size is not by itself proof that an arbitrary 80/96-GB card can serve it.
- `smoke`: small public model for installer/protocol diagnosis on constrained hardware; explicitly identify its limited capability and never label smoke-only installation as flagship completion.
- `plan` shows detected capacity against each selected profile. Defaults may select a fitting supported profile only if displayed clearly before apply. Disk budget includes selected artifacts, temporary/cached duplication, runtime/build space, logs, and free-space reserve; downloading both large and fast models must be an explicit model-set choice.
- Document validated hardware separately from estimated compatible hardware. Fast eight-channel RAM supports the hybrid rationale; throughput and context remain measured properties of the deployed model/runtime.

## Worker tasks and acceptance evidence

### I1 — implementation, fresh Worker1 or Worker2 session

Own installer entrypoint/module, lock/config/profile schema, generic storage registration, prerequisite/driver stages, reproducible model/runtime deployment plumbing, client provisioning, operations/install docs, CI wiring, and milestone report. Integrate already reviewed D1/A1/L1 work; do not recreate their implementations. Use a feature branch and isolated copy. Split into two fresh sessions at the prerequisites/deployment boundary if context grows.

Required output: installer runs through all applicable stages without manual undocumented commands; it pauses only for actual reboot/external requirements, then resumes; installs client and service; verifies ready status; supports a second no-op run; reports failures honestly. A launcher that assumes model, runtime, or driver already exist does not meet this scope.

### I2 — independent verification, opposite worker and fresh session

- Review I1 diff and CLI/help/plan contract before live adoption. Use a disposable Ubuntu 24.04 container/rootfs for genuine package/bootstrap/client paths possible there; isolate network/download budgets and persist reports in the worker copy. Container results cannot prove GPU drivers, systemd boot, physical disk handling, or hardware inference.
- Mock host integration to cover stage order, unsupported OS, insufficient capacity, disk identity changes, root/boot/RAID rejection, absent mount, driver reboot/resume, interrupted stages, secret redaction, unavailable pins, concurrent runs, and failed readiness. Assert real effects/command boundaries, not merely matching implementation strings.
- Use disposable loopback devices only in a disposable Linux test environment for actual blank-disk layout/mount/fstab tests, if available. Never run disk-provisioning tests against ai-vm block devices. Do not simulate their results as live validation.
- After review, perform a non-destructive adoption/idempotency pass on ai-vm from the worker, preserving its selected model and credentials; verify service/client behavior and exact commit/lock identity. Coordinate any restart with the model deployment owner.
- Run the real coding-agent acceptance from a worker over SSH forwarding. Record live generation/tool results and actual edit/test outcome independently of mock tests.
- If no disposable GPU VM exists, state: **full fresh-host GPU installation and reboot acceptance NOT_TESTED**. Report container bootstrap, mocked host integration, optional loopback storage, live existing-host idempotency, and live agent loop as separate evidence classes. Do not present them as a wiped/reinstalled server test.

Publishing gate: reviewed feature commits, relevant test evidence, secret scan, and accurate README quickstart/support matrix. A reproducible installer may be delivered with the above explicitly stated fresh-GPU-host test limitation; it must not claim a complete fresh-host end-to-end pass that was never executed.
