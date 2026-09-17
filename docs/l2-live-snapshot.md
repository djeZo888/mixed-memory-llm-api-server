# L2 current ai-vm profile and evidence handoff

**APISELECT: anticipated source selection only, 2026-09-17.** Based on
`357358ab12914df209d54c895a59c94a41c84580`. Qwen candidate acceptance is **PENDING**;
APIDEPLOY waits for root-reviewed live profile acceptance. No installation,
host access, native execution, receipt creation or service activation occurs
here. Historical evidence retains its original scope. Frontend and installer
work remain outside this task; installer work is paused.

## Exact selected source

[The snapshot](../configs/control/ai-vm-live-snapshot.json) pins exactly six
selected declarations (two deployments, two models, two runtimes), the existing
GLM image proof/recipe closure and the unchanged source-closure manifest.
Control/boot source hashes belong to the
[canonical inventory](../reports/l2-source-closure-sha256.json); the snapshot
references its path without duplicating or hashing that inventory. This is an
operator handoff, not a runtime loader. Source hashes establish no new live
acceptance. Later owner changes, including Q38MAX fixture changes, require
canonical inventory review and receipt compatibility review before composition;
APISELECT does not edit those sources or inventories.

| Offered model | Runtime | Sole selected deployment / declared context |
| --- | --- | --- |
| GLM5.3, `unsloth/GLM-5.3-GGUF`, UD-Q4_K_XL | `llama-cpp-v0.4.1-d3br` | `glm-5.3-ud-q4-k-xl-n76-native1m` / 1,048,576 |
| `Qwen/Qwen3.8-27B-FP8` | `sglang-qwen38-0.5.19` | `qwen38-27b-1000000-yarn4-tp2-bf16kv` / 1,000,000 |

Worker1 stages only those two JSON files directly under each active
`configs/deployments`, with the four selected model/runtime files at their
unchanged relative paths. Do not recursively copy profile directories.
[`discovery._deployment_ids`](../scripts/control/discovery.py) enumerates every
top-level `.json` name; the snapshot supplies no roster filter. Both the data
release and fixed control copy must expose exactly these two choices. Keep
native Qwen 128K/256K, older GLM profiles and D1 runtime/image/recovery copies
outside active discovery in protected rollback storage; do not delete them.
No preemptive fallback256 selection: root assigns that adjustment if needed.

**Dependency finding at this base:** excluding native deployment JSONs does not
break the selected Qwen path. `scripts/lifecycle/qwen38.py::validate` calls
`declared_profile(d['id'])`, whose `_pinned_json` reads only that deployment,
its model/runtime and acquisition/research manifests. `evidence` validates the
native receipt first, then the separate extension receipt through
`_validate_auth_proof`. Native proof validation uses the fixed context pair and
fixture/support hashes; it does not open native deployment JSONs. Extension
validation calls `run_fixture.py::extension_identity`, which opens the selected
extension deployment, launcher and `qwen38_config.json`. Thus preserve all
listed fixture files, provenance, launcher, OCI support and manifests at their
original relative paths in both normal source trees. Hash constants for native
profiles alone do not require those files in the active catalog. No adapter,
receipt validator or source-closure bypass is added.

## Final source composition (Worker1, after live profile review)

Follow [B1S staging](lifecycle/b1s-current-vm-staging.md),
[`boot_unit.py`](../scripts/lifecycle/boot_unit.py),
[`llmctl.conf`](../scripts/lifecycle/llmctl.conf), [control API](control-api.md)
and [private network](private-network.md). Refresh the current root-reviewed
installed guard/source identities and registered mounts; run registered-storage
and root-disk guards before/after authorized writes, recording under protected
registered logs. Use the canonical lifecycle lease and coordinated idle slot.

| Destination | Composition contract |
| --- | --- |
| Protected release under the registered data services root | Final reviewed normal lifecycle/control source, six selected declarations and exact proof/adapter/receipt dependencies; freeze its actual path/commit with Worker1. Preserve the protected instance and saved intent. |
| `/usr/local/lib/llm-server/control-api` | Same reviewed Manager/profile/dependency bytes, including the existing `scripts/control/source-closure.json` recovery and normal files, plus the snapshot's GLM proof/recipe closure. Preserve relative paths; root copy remains independent of data mounts for recovery. |
| `/usr/local/lib/local-ai-server` | Exactly the 11 paths in `boot_unit.RECOVERY_FILES`, byte-equal to the data release. No profile, fixture or manifest additions to this boot-stop tree. |

Use protected nonsymlink, single-link files/ancestry, root-owned directories
without group/other write, and preserve Git executable modes. Verify both root
copies actually reside on the root filesystem. Follow B1S's isolated boot-stop
import, rendered unit/drop-in and control credential-binding checks; this task
runs none of those host checks. Existing imported `scripts/install` modules
remain runtime dependencies, not authorization for installer work.

Preserve `/etc/llm-server/control.json`, separate root control key and systemd
credential binding, registered inference key, acquisition receipts, actual GLM
patched-image evidence and Qwen native/extension proof receipts. Qwen requires
both `sglang-qwen38-0.5.19.auth.json` and
`sglang-qwen38-0.5.19.q38max.auth.json` under the existing evidence directory,
with `auth_gate_evidence` and `extension_auth_gate_evidence` instance bindings.
Do not regenerate evidence or credentials from this snapshot.

Retain NETPATCH's helper, six network units, protected ownership receipt and
reviewed firewall/TLS policy. Its helper SHA256 belongs to the canonical
inventory, not the selection snapshot. Worker1 must reconcile installed source
signatures/inventory and the existing
receipt migration with current reviewed evidence, never overwrite it using an
older signature or bypass its checks. Native listeners stay authenticated IPv4
loopback; direct private transport is subject to that existing policy. Enable
control/Qwen sockets only after native authentication acceptance. Publication
and all three destination updates remain separate APIDEPLOY work.

## Canonical registered storage input

The original L2 launch handoff reported `/etc/local-ai-server/storage.json`
absent; that is historical, not a current observation. APISELECT has not checked
the host. Worker1 must preserve and verify the current protected registration
and exact mounts against its latest reviewed handoff. The following schema and
historical supplied identities are contract references, not permission to
recreate registration. No installer workflow or mutation helper is added here.

Registration is a root-owned mode0600 single-link regular file, at most 16384
bytes, with protected nonsymlink parents. Its required stable schema1 fields
are `schema_version:1`, `data`, `models`, and `roots`; `storage_mode:"existing"`
records the current mounted-layout mode. Each role object contains literal
`path`, `mount`, `uuid`, `fstype`. For this supplied current-VM handoff only:

| Role | Path = exact mount | UUID | Filesystem |
| --- | --- | --- | --- |
| data | `/data` | `8daf56f1-5649-4163-9d87-919c2d271875` | `ext4` |
| models | `/data/models-large` | `a6d4ab58-84e1-4e48-9a67-13ad1c6f6e0a` | `ext4` |

These are supplied expected identities, not fresh evidence or defaults for
another host. L2VM must resolve their live devices, root/boot ancestry, mount
IDs, whole-volume aliases and writable filesystem state. Optional observed
`source`, `device`, `parents` fields are live observations, never guessed from
old device names. Stable identity excludes those observations.

`roots` must equal this complete derived mapping; it must not omit unused roots:

```json
{
  "hf_cache": "/data/hf-cache",
  "docker": "/data/docker",
  "containerd": "/data/containerd",
  "build": "/data/build",
  "logs": "/data/logs",
  "backups": "/data/backups",
  "services": "/data/services",
  "secrets": "/data/services/secrets",
  "state": "/data/services/installer",
  "models": "/data/models-large"
}
```

`state` is a required registration name, not authorization to run an installer.
Relevant registered roots must exist as protected nonsymlink directories before
their role verifies. In particular, `roots.secrets` and `roots.state` must be
root-owned mode0700; the actual verifier rejects any group/other permission bits.
Normal model readiness verifies both roles. Data-only
control persistence still compares the whole registered identity and cannot
write into a models-owned namespace or cross a nested mount. Recovery uses the
trusted `/run/llmctl/recovery.json` identity when normal storage is unavailable;
it does not depend on profiles, receipts, network policy or model data.

## Protected instance and completion receipts

Normal `load_manager` reads exactly
`/data/services/llm-manager/deployment-instance.json`. This and receipt files
must be root0600, regular, single-link, nonsymlink, at most 1 MiB, on verified
registered data storage with protected parents. Do not publish a source template
as completed evidence. Preserve the existing instance ID, immutable ownership
identity and real evidence when binding the current host.

Required instance inputs:

- `schema_version:1`, valid `id`, and `storage_identity` equal the complete stable
  registration `{schema_version, roots, data:{path,mount,uuid,fstype},
  models:{path,mount,uuid,fstype}}`.
- `paths.state` resolves to `/data/services/llm-manager/active`; fixed lock and
  recovery paths are `/run/llmctl/lifecycle.lock` and `/run/llmctl/recovery.json`.
  Role references remain `{role:"data",suffix:"services/llm-manager/active"}`;
  existing historical literal paths require the explicit reviewed historical
  binding contract. No implicit historical import or path relocation.
- Each selected installed model needs a `model_integrity` entry containing
  `verified:true`, their pinned `revision`, real nonempty `evidence` and literal
  `completion_manifest` path. Q38 additionally contains `manifest_sha256` equal
  to the actual pinned `reports/q38s-acquisition-manifest.json` SHA256. Preserve
  unrelated historical evidence: instance keys alone cannot publish a model
  whose deployment profile is excluded from this snapshot.
- `runtime_evidence` contains actual host evidence for each selected runtime.
  GLM requires its final measured patched `image_id`, `flags_verified:true`, `supported_flags`
  covering the runtime's required flags, supported `load_mode`, and evidence.
  Startup still independently checks local runtime/image and CLI contracts.
  The approved patched proof/recipe dependency closure accompanies the final
  runtime/deployment; old D1 source attestations cannot substitute for it.
- `obsolete_boot_owner_disabled:true` and real
  `obsolete_boot_owner_evidence` are start prerequisites, not values to infer
  from installing this source. Control and inference keys remain separate.

Receipt locations are `/data/services/llm-manager/acquisition/` followed by
`glm-5.3-ud-q4-k-xl.complete.json` or `qwen38-27b-fp8.complete.json`. Both generic
receipts contain `schema_version:1`, `complete:true`, exact model `repo_id`,
`revision`, `model_root` = `/data/models-large/{model-profile-id}`,
`artifact_count`, `total_bytes`, and `artifacts`. Each artifact is the exact
profile tuple `{path,size_bytes,sha256}` plus `verified:true`; no duplicates or
omissions. GLM has 11 artifacts totaling 467289116837 bytes. Q38 has 81 artifacts
totaling 30890049597 bytes; its strict receipt additionally contains the pinned
`manifest_sha256` and permits no other top-level/artifact fields. These receipts
must come from real acquired-byte verification, never synthetic source tests.

Actual catalog discovery requires a protected completion receipt even when a
historically imported instance could satisfy a narrower legacy attestation.
An absent/invalid receipt keeps the deployment known but excludes it from the
public installed list. `installed_verified_at` is this metadata observation
time, not a new hash of weights. Discovery does not traverse/hash model payloads
or read keys. Startup performs its separate artifact/path/runtime checks.

Q38 `runtime_evidence["sglang-qwen38-0.5.19"]` must link `auth_gate_evidence` to
`/data/services/llm-manager/evidence/sglang-qwen38-0.5.19.auth.json`, with exact
`image_id`, `image_reference`, `source_revision`, `launcher_sha256`,
`flags_verified:true`, `auth_gate_passed:true`, exact ordered `supported_flags`,
real `evidence`, and `docker_inspect` matching that protected actual-image
receipt. Consume Q38B's exact schema2 receipt via `qwen38.evidence`; do not
reconstruct it from these prose fields. Its outer image ID is the pinned OCI
config digest; nested inspected identity may use the approved config or exact
platform-manifest domain only with Q38B's validated relationship. Preserve
fixture/source/support hashes, actual native results and container lifetimes.
The separately installed root0644 launcher under
`/data/services/llm-manager/adapters/sglang38_file_auth.py` must match its source
hash. An actual-image authentication receipt is not model inference proof.

## Public endpoint and live acceptance

Protected control config may explicitly select
`"advertised_endpoint_policy":"private_network"`. N1S's no-argument
`load_policy()` supplies the protected exact `10.156.100.60` policy and fixed
ports. Catalog/status serialization maps GLM to `glm`/30002 and Q38 to
`qwen38`/30004 only when the actual deployed profile port matches. Served alias
comes from that profile. Internal endpoints and listeners stay loopback;
missing/invalid policy retains local tunnel DTO and cannot disable local
authenticated control or trusted recovery. Policy does not prove reachability.

Configured context is declared; `verified_occupied_tokens` remains null. New
live profile, allocation, occupied-context, speed, private authentication,
stream/tool, OpenCode, switch and reboot acceptance remain **PENDING/NOT_TESTED**
here. Historical readiness, fixture passes and short probes retain their own
boundaries and do not prove current serving or occupied capacity.

The planned order is current accepted **Qwen → GLM → Qwen**, then one reboot
with selected fast Qwen and **resume**. Worker1 uses existing
`scripts/llmctl select "$DEPLOYMENT" --boot-policy resume --yes` during a planned
stopped selection, avoiding a reload solely for policy. The current control
adapter preserves saved boot policy across switches (the older B1S manual-only
statement is historical). Release Worker1's lifecycle lease before Worker2 API
switching; keep one request owner, then explicitly return ownership for reboot.
Check exact two-choice catalog/status, wrong key, stale generation, idempotent
replay, both switch directions via returned operation polling, ordinary clients
once per selected model, and post-reboot LAN readiness. End on fast Qwen/resume.

Private client preparation uses only existing `scripts/client/bootstrap.py`
and pinned OpenCode 1.18.31 dependencies, with these anticipated settings:

| Alias | Direct endpoint | Context | Effort |
| --- | --- | --- | --- |
| `glm-5.3` | `http://10.156.100.60:30002/v1` | 1048576 | `low` |
| `qwen3.8-27b` | `http://10.156.100.60:30004/v1` | 1000000 | `none` |

Use existing protected key provisioning and new private prefixes when settings
change; no key disclosure/rotation. Dependency/key/prefix locations are not
established by this source handoff. Record the required settings for the next
owner rather than search broadly, replay bootstrap or download dependencies.
The 2048 output-token acceptance budget is separate from context capacity.
Later APIACCEPT uses existing `scripts/agent/acceptance.py` and
`scripts/client/verify.py`; neither runs here. Follow the supplied final
acceptance plan for bounded GLM 32K / Qwen 128K occupied cases with 8192 reserved,
actual rendered counts and real tool continuation. Allocation and declared
capacity remain separate from completed occupied-context evidence.

## Focused source verification

APISELECT performs one bounded local check: parse JSON; require the exact two
model/deployment mappings; verify selected declarations and dependency SHA256s;
and check actual discovery's directory enumeration against the two-file staged
catalog. Check proof pins by reading source only, without executing fixtures,
loading receipts or making host/model/control/network requests. Record results
outside Git in the task's `checks.txt`; no broad suite or historical bootstrap
replay. These checks establish source identity only.
