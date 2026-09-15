# D2 lifecycle source and D3 handoff

D2 is worker-tested source. D3 deploys **only the root-reviewed merged commit**.
No D2 command contacted ai-vm, installed software, downloaded weights, changed a
service, or tested CUDA. [Milestone evidence](../../reports/d2-flagship-lifecycle.md).

## Ownership and profile interface

| Owner | Contract |
| --- | --- |
| D1 | Pinned acquisition/build source, image, final help/source facts, artifact integrity |
| D2 | `scripts/llmctl`, `scripts/lifecycle/`, JSON profiles, lifecycle tests and this handoff |
| D3 | Fill verified deployment instance, remove old boot writer, deploy and measure |
| A1/V1 | Client/protocol/tool acceptance on workers; never tool execution on inference VM |
| I1/I2 | Whole fresh-Linux installer, clean-host dependencies, guard generalization and installer tests |

`llmctl list-deployments` lists executable deployment IDs:

- `glm-5.3-ud-q4-k-xl-8k`: initial 8192 **total** context, one slot.
- `glm-5.3-ud-q4-k-xl-32k`: explicit 32768 measurement preset, one slot.
- `qwen3-30b-a3b-instruct-2507`: retained existing SGLang container adapter.
- `qwen3-0.6b-smoke`: retained existing SGLang container adapter; never a default.

Both GLM deployments serve `glm-5.3` at `http://127.0.0.1:30002/v1`.
Model profile `glm-5.3-ud-q4-k-xl` pins Unsloth repository revision
`346b3591c7f28d1a23716f97a065ecf12ec14771`, eleven exact paths/sizes and SHA256
identities, total **467289116837 bytes**. Load entry remains
`/data/models-large/glm-5.3-ud-q4-k-xl/UD-Q4_K_XL/GLM-5.3-UD-Q4_K_XL-00001-of-00011.gguf`.
Start stats all eleven files; normal status does not inspect or hash weights.
D1 owns full download verification. D2 requires its recorded integrity evidence.

Runtime profile `llama-cpp-v0.4.1-d1` pins `v0.4.1`, source revision
`b29c606e28a01b1bc8c1351026a0fa6e616bf6c4`, tag
`local/llama-cpp:v0.4.1-b29c606-cu132-sm120-d1`, entrypoint
`/opt/llama/llama-server`. Start also pins the **final local image content ID**;
the CUDA base digests are not that ID. No pull/build/download operation exists in
the lifecycle implementation.

D1 final [runtime proof](../../reports/d2-contract-evidence/d1-runtime-proof.json)
and [selected help](../../reports/d2-contract-evidence/d1-cli-selected.txt) establish
build/CUDA/CLI PASS, not GLM inference. The current-host instance pins image ID
`sha256:6866856c573d69d504f82265321b182f631a7b3912a1ed1b4efbf893729d4e62`.
Both visible devices were listed as CUDA0/CUDA1. Source now renders explicit
`--device CUDA0,CUDA1`, `--load-mode none`, CPU MoE, layer split and
`--chat-template-kwargs '{"clear_thinking":true}'`, using the supported pinned flags.
D3 must live-test GLM template/reasoning behavior and actual GPU allocation; the
kwargs setting does not itself prove thinking-history compatibility. No deprecated
mmap flag is rendered. Docker exposes host GPU IDs `0,1`.

Artifact integrity completion and old boot-owner removal are still pending in the
checked-in current-host instance, so **it cannot start GLM yet**. The fresh-host
template also leaves runtime evidence empty, because another local build must be
verified independently. Readiness does not prove inference, tools or hardware fit.

## Instance, state, mounts and secrets

Pass `--instance PATH` on commands, or set `LLMCTL_INSTANCE` to a **path**, never a
key value. Production default is
`/data/services/llm-manager/deployment-instance.json`. No instance is implicitly
selected from the repository. `LLMCTL_CONFIG_ROOT` can point at a reviewed config
root. Existing `LLMCTL_SKIP_*` variables do **not** bypass new lifecycle guards.
Tests inject mocked I/O through Python objects, not production environment switches.

Use [the current-host example](../../configs/deployments/instances/ai-vm-d0b.json)
or [the fresh-host template](../../configs/deployments/instances/instance.template.json).
Required fields include:

- Two exact mount targets, filesystem types and UUIDs. This host's `/data` UUID is
  `8daf56f1-5649-4163-9d87-919c2d271875`; `/data/models-large` UUID is
  `a6d4ab58-84e1-4e48-9a67-13ad1c6f6e0a`. These identities appear only in the explicit
  host example, not generic lifecycle logic or the fresh-host template.
- `runtime_evidence.llama-cpp-v0.4.1-d1`: `image_id` (`sha256:` plus 64 hex digits),
  `flags_verified: true`, `supported_flags` covering the runtime profile's full
  list, exact supported `load_mode`, and nonempty reference(s) to D1 final evidence (already supplied for this host).
- `model_integrity.glm-5.3-ud-q4-k-xl`: `verified: true`, exact model `revision`,
  and a nonempty reference to D1 completed integrity evidence.
- `obsolete_boot_owner_disabled: true` and `obsolete_boot_owner_evidence` after the
  removal procedure below. These are operator attestations, not automatic research
  or permission substitutes. Do not set them just to bypass a failed prerequisite.

| Host path | Container path | Policy |
| --- | --- | --- |
| `/data/models-large/glm-5.3-ud-q4-k-xl` | `/models` | Read only; new models disk |
| `/data/models-large/runtime-cache/llama-cpp` | `/cache` | Runtime scratch; no duplicate HF weights |
| `/data/logs/llmctl/glm-5.3` | `/logs` | Data disk |
| `/data/services/llm-manager/glm-5.3` | `/service` | Data disk |
| `/data/services/secrets/llm-api-key` | `/run/secrets/llm-api-key` | Regular file, mode0600, read only |

Only the key **path** enters Docker argv. The Python probe reads the key in memory,
sends it directly to localhost over HTTP, disables redirects/proxy inheritance,
and never prints headers, bodies, keys or raw exceptions. Token bytes must have
no trailing newline, matching the A1 client contract. Docker subprocesses get
a minimal environment and suppressed stderr. Do not put the key in environment
variables, command substitutions, shell arguments, state, reports, or Git. D3 must
provision the secret through its existing protected route and validate D1's key
handling; D2 does not create or rotate a real secret.

Before start, exact mount target/UUID/device checks run before artifact access or
Docker. Both filesystems must differ from root and from one another. Existing
`require-data-mounted.sh` and `root-disk-guard.sh` run before and after starts;
selection also runs these guards around state writes. Root guard remains WARN
below 6GiB and HALT below 4GiB. Its bounded latest report is
`/data/logs/llmctl-root-disk-guard.md`. Docker root must be `/data/docker`.

The state root is `/data/services/llm-manager/active`; a global process mutex at
`/run/llmctl/lifecycle.lock` covers complete mutating transitions, including
readiness waits and a re-read of state after locking. Unique temporary files,
fsync and atomic replace protect state updates. State schema2 records selected
profile, desired running/stopped intent, observed stopped/starting/ready/unhealthy/
failed, immutable container ID and image ID, ownership labels and safe error codes.
Newer emergency stopped intent in `/run/llmctl/recovery.json` overrides stale disk
state until it can be persisted. This recovery journal is small volatile control
metadata, not model/service payload storage.

`select`/`activate` only select and leave stopped. `start` launches explicitly.
`stop` preserves selection and records intentional stopped intent; `deactivate`
writes a no-selection tombstone so old legacy state cannot resurrect smoke.
`--no-wait` is refused. Readiness requires a running owned container, valid effective
loopback bindings, expected image/launch/mount/GPU/log contract, healthy API, exact
served model ID, successful authenticated request and unauthenticated rejection.
An open port or historical `active` flag is insufficient.

On startup timeout/failure the container may remain running. State records this
honestly; use `stop --yes` before retry/rollback. It does not delete weights, images,
containers or unrelated deployments. `status` and `active` return schema2 JSON, replacing the historical text format.
The retained smoke planning verifier is functional offline and consumes
`status --offline`: saved intent is separate from live observation, which is null
and labelled `not_performed_offline`. It never invokes Docker or the API. Other
historical live `scripts/sglang/verify-*` parsers are not D2 live verifiers; use
this handoff and A1/V1 acceptance. `status` observes cheaply without persisting its
snapshot. It calls a long cold load `starting` only while the actual transition
mutex remains held; an abandoned starting flag becomes unhealthy. A preflight failure may leave `container_running: null` when the
storage guard deliberately prevents a new Docker observation.

## Exact D3 execution sequence

Run these **on the VM as the Worker1/D3 operator after root review**, not on a Mac.
The checked-out source commit must be the reviewed integration containing both D1
and D2. Set `REVIEWED_COMMIT` to the review's exact commit; do not use an unreviewed
branch tip. No command below fetches a model or builds an image.

```bash
cd /data/services/mixed-memory-llm-api-server
REVIEWED_COMMIT='<root-reviewed-merged-commit>'
test "$(git rev-parse HEAD)" = "$REVIEWED_COMMIT"
scripts/common/require-data-mounted.sh
scripts/common/root-disk-guard.sh --report /data/logs/d3-pre-lifecycle-root-guard.md
sudo -n install -d -m 0700 /run/llmctl /data/services/llm-manager/active
sudo -n install -d -m 0755 /data/models-large/runtime-cache/llama-cpp
sudo -n install -d -m 0755 /data/logs/llmctl/glm-5.3 /data/services/llm-manager/glm-5.3
```

**Remove the R1 obsolete boot writer before persistence work.** R1 identified
`/etc/systemd/system/m6b-post-reboot-verify.service`, which executes
`/data/services/m6b-post-reboot/m6b-post-reboot-verify.sh` and checks out
`milestone/m6b-nvidia-container-toolkit-install`. Preserve the original unit/script
in the D3 backup. Never execute that script to verify it.

```bash
sudo -n install -d -m 0700 /data/services/llm-manager/d3-boot-backup
sudo -n cp -an /etc/systemd/system/m6b-post-reboot-verify.service /data/services/llm-manager/d3-boot-backup/
sudo -n cp -an /data/services/m6b-post-reboot/m6b-post-reboot-verify.sh /data/services/llm-manager/d3-boot-backup/
sudo -n systemctl disable --now m6b-post-reboot-verify.service
sudo -n rm /etc/systemd/system/m6b-post-reboot-verify.service
sudo -n systemctl daemon-reload
sudo -n systemctl mask m6b-post-reboot-verify.service
sudo -n systemctl is-enabled m6b-post-reboot-verify.service || true
```

Expected final old-unit state: **masked**. If already removed, verify the backup
and masked state instead of repeating the copy/remove commands. Do not enable
another Docker restart policy, Compose supervisor or model-specific boot unit.

Copy the instance once, then edit its **nonsecret** remaining prerequisite fields
from D1 artifact completion and D3 boot-removal evidence. The current-host image
ID/CLI evidence is already filled from the supplied final D1 build proof. Retain the exact UUIDs only for this host. Inspect final image
identity using structured metadata only:

```bash
sudo -n install -m 0600 configs/deployments/instances/ai-vm-d0b.json /data/services/llm-manager/deployment-instance.json
sudo -n docker image inspect --format '{{.Id}}' local/llama-cpp:v0.4.1-b29c606-cu132-sm120-d1
sudo -n docker image inspect --format '{{json .Config.Entrypoint}}' local/llama-cpp:v0.4.1-b29c606-cu132-sm120-d1
sudoedit /data/services/llm-manager/deployment-instance.json
sudo -n stat -c '%a %U %F' /data/services/secrets/llm-api-key
sudo -n python3 scripts/llmctl status
sudo -n python3 scripts/llmctl stop --dry-run
sudo -n python3 scripts/llmctl stop --yes
sudo -n python3 scripts/llmctl select glm-5.3-ud-q4-k-xl-8k --boot-policy manual --dry-run
sudo -n python3 scripts/llmctl select glm-5.3-ud-q4-k-xl-8k --boot-policy manual --yes
sudo -n python3 scripts/llmctl start --dry-run
sudo -n python3 scripts/llmctl start --yes
sudo -n python3 scripts/llmctl status
scripts/common/require-data-mounted.sh
scripts/common/root-disk-guard.sh --report /data/logs/d3-post-lifecycle-root-guard.md
```

A reported conflict requires stopping the identified other deployment first.
For a missing state/journal with a historical container, do not adopt by name
blindly: inspect **only** ID/name/image/mount/network/ownership metadata for the
known `sglang-*` or `minimax-m3-mxfp8-poc` container; compare to R1/D1. Under Worker1's
exclusive live-operations ownership, record the reviewed full immutable ID, then
stop only that ID. Do not issue project-wide Compose down or stop all containers.

```bash
sudo -n docker ps --no-trunc --format '{{.ID}} {{.Names}} {{.Image}} {{.Ports}}'
# D3 supplies the reviewed full 64-hex container ID from that metadata.
STOP_ID='<reviewed-full-container-id>'
sudo -n docker inspect --format '{{.Id}} {{.Name}} {{.Image}} {{json .HostConfig.PortBindings}}' "$STOP_ID"
# After matching the identity to the historical deployment:
sudo -n docker stop --time 120 "$STOP_ID"
```

D3 next runs A1/V1 authenticated chat/streaming/tool acceptance from a worker and
records real startup, CPU/RAM/GPU use, context counts and latency. After the 8K
proof, explicitly measure 32K:

```bash
sudo -n python3 scripts/llmctl stop --yes
sudo -n python3 scripts/llmctl select glm-5.3-ud-q4-k-xl-32k --boot-policy manual --yes
sudo -n python3 scripts/llmctl start --yes
sudo -n python3 scripts/llmctl status
```

The two presets share the API alias and port but have separate container identities.
Test actual OpenCode tool/schema headroom and true token usage; 32K capacity and
performance are **NOT_TESTED**. Do not infer quality or hardware fit from a ready API.

## Single boot owner

After controlled start/stop/restart passes and the chosen preset is measured, D3
may install [the supplied unit](../../scripts/lifecycle/llmctl-boot.service):

```bash
sudo -n install -m 0644 scripts/lifecycle/llmctl-boot.service /etc/systemd/system/llmctl-boot.service
sudo -n systemd-analyze verify /etc/systemd/system/llmctl-boot.service
sudo -n systemctl daemon-reload
sudo -n systemctl enable llmctl-boot.service
sudo -n systemctl start llmctl-boot.service
```

Default manual selection does not launch on boot. For explicit restart-on-boot,
stop then reselect the **measured** preset with `--boot-policy resume`, and `start
--yes`. The unit invokes `boot-start` only when desired=running AND policy=resume;
selection alone never starts. `boot-stop` preserves desired intent during shutdown.
Ordinary `stop`/`deactivate` persist intentionally stopped intent across normal
reboots. A systemctl service restart follows this same policy; it does not imply
manual deployments should resume.

This is a one-shot intent replayer, not an ongoing crash supervisor. Docker uses
`restart=no`. A crashed backend requires explicit manager restart. Dependencies
order Docker and both `/data` and `/data/models-large` mount units, with mount-loss
stop ordering. Startup has a 7200-second model deadline plus bounded pre/post
checks within a 3-hour unit limit; unit shutdown allows 5 minutes. Docker JSON logs
rotate at 20MB x 3 per retained container under `/data/docker`; only two GLM preset
containers are created by these profiles. No raw Docker logs are relayed by
`llmctl logs --yes` because server text can contain sensitive data. D3 must use a
separate reviewed redaction route for diagnostic excerpts. Unit stdout/stderr are
discarded; structured state holds safe failure codes.

## Rollback and stop recovery

```bash
sudo -n python3 scripts/llmctl stop --yes
# If primary state is unreadable, use the last trusted /run identity:
sudo -n python3 scripts/llmctl recover-stop --dry-run
sudo -n python3 scripts/llmctl recover-stop --yes
# Return to the already retained 8K proof:
sudo -n python3 scripts/llmctl select glm-5.3-ud-q4-k-xl-8k --boot-policy manual --yes
sudo -n python3 scripts/llmctl start --yes
# Or, after stopping GLM, explicitly choose the retained Qwen30B container:
sudo -n python3 scripts/llmctl stop --yes
sudo -n python3 scripts/llmctl select qwen3-30b-a3b-instruct-2507 --boot-policy manual --yes
sudo -n python3 scripts/llmctl start --yes
```

Legacy smoke/Qwen state migrates to schema2 with identity retained and desired=
stopped/manual, regardless of the old `active` flag. Existing legacy containers
must match exact names, image tag, Compose service and model mount/argument before
adoption. Their runtime Compose file is rendered as JSON and all mappings are
validated. The retained container is started by immutable ID; D2 does not recreate
missing legacy containers or change their reviewed launch arguments. If absent,
D3 must restore the reviewed legacy Compose deployment before selecting it.
Legacy endpoints retain their previous localhost-only authentication contract;
GLM always requires the key file and auth rejection checks.

Stop bypasses artifacts, key reads, network/profile parsing and capacity/start
guards. It checks the recorded full ID, image and ownership before touching Docker.
Broken `/data/models-large` or root-pressure guards cannot prevent this shutdown.
If `/data` itself is unavailable, stop uses the trusted volatile `/run` journal and
reports `state_persisted: false`. **Restore `/data` and repeat stop before reboot:**
volatile recovery cannot preserve changed intent through power loss when the
persistent disk is unavailable. Never turn a journal-write failure into permission
to stop an unrelated container.

## Reuse by the future installer

Dependencies: Linux Python >=3.10 (stdlib only), `flock` via Python `fcntl`, Docker
CLI/daemon with NVIDIA runtime already validated, util-linux `findmnt`, GNU host
guard dependencies, root execution or existing noninteractive sudo, and systemd
only if the boot unit is installed. All data directories, exact artifacts, image,
key and instance evidence must exist; lifecycle creates no model/cache downloads.
Create `/run/llmctl` root-owned0700 and the state root with protected ownership.

The original common host guards still contain historical fixed `/data` UUID/layout
and environment expectations. D2 did not edit those shared files. **I1/I2 must
parameterize them with the same instance contract** for a different fresh host;
the D2 generic mount validator does not bypass those existing guards. They must
also render installation/service paths when using a checkout location other than
the documented `/data/services/mixed-memory-llm-api-server`. Whole-install source
and clean-host reinstall proof remain I1/I2 work.

## Minimal future F1 SGLang adapter boundary

The generic pieces are selection/intent, mutex and atomic state, mount checks,
container ownership, conflicts, bounded observation and safe stop. The current
`Manager.validate_deployment`, `create_args`, `launch_command`, and
`validate_reused_contract` implement the **llama.cpp** deployment contract. The
SGLang path supports only the two historical smoke/Qwen30B identities and their
already-created containers.

F1S must add backend-specific validation, creation/launch and reused-container
validation/authentication for a new declarative SGLang runtime/model/deployment
profile. Qwen3-Coder-Next FP8 needs its own artifact identity, image/flag evidence,
mounts, served alias, authentication/readiness policy, context/GPU limits, and
mocked plus live acceptance. Route by an explicit backend kind while reusing the
existing transition/ownership/stop machinery. Do not label it legacy Qwen30B,
reuse that container identity, or enable/download it through these D2 presets.
No F1 backend implementation, model activation or whole installer is included here.
