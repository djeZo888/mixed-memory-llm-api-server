# L2 current ai-vm profile and evidence handoff

**Source selection only. Final GLM runtime, deployment and patched-image
proof/recipe closure are pending D3PD/D3T.** No installation,
host access, native execution, acquisition receipt or service activation is
performed or authorized by these files. Worker1 owns separately authorized L2VM
publication and live acceptance. Installer work remains stopped.

## Exact selected source

[The manifest](../configs/control/ai-vm-live-snapshot.json) pins five profile files
by SHA256 and names pending owner-approved GLM composition inputs. It is an operator
instruction, not an additional runtime loader. The installed source root is
`/usr/local/lib/llm-server/control-api`; relative paths remain unchanged.

| Offered model | Runtime | Selected deployments |
| --- | --- | --- |
| GLM5.3, `unsloth/GLM-5.3-GGUF`, UD-Q4_K_XL | Final measured patched runtime pending D3PD/D3T | One final practical-context profile from D3T; source path and SHA256 explicitly pending |
| `Qwen/Qwen3.8-27B-FP8` | `sglang-qwen38-0.5.19` | `qwen38-27b-128k`, `qwen38-27b-256k`; both declared only |

At final owner-approved composition, record exact source commits, runtime and
deployment paths, IDs and byte SHA256s; the measured patched image ID and actual
image proof; and every required proof/recipe/import dependency path and SHA256.
Bind the manifest's null GLM fields to those approved inputs together. Confirm
the final deployment uses the selected model and final runtime, with endpoint
port 30002. D3P's strict-alias patch requires a newly built and measured image;
the old D1 runtime/image remains baseline and rollback only. Include required
D3T-owned lifecycle source in the reviewed composition; a profile cannot bypass
its validation. No placeholder profile or fabricated image identity is enabled.
Any owner change to a fixed profile requires explicit reviewed repinning. Until
then this is an incomplete publication selection, not a deployable final
snapshot. Existing `glm-5.3-ud-q4-k-xl-32k.json` is only a source-test reference;
neither its context nor any test output budget is a product limit.

Worker1 copies exactly the five pinned profile files and final owner-approved
GLM profiles into their relative `configs/{models,runtimes,deployments}` locations.
GLM proof/recipe/import dependencies retain their separately reviewed relative
source-closure paths; they do not belong in profile directories. All installed profile
files and directories must be root-owned, nonsymlink, and not group/other
writable; use root0644 files and root0755 directories on the root filesystem.
Do not recursively copy those source directories. Actual discovery enumerates
every `*.json` directly under installed `configs/deployments`; there is no
runtime roster filter. Verify the destination directory contains only the two
Q38 deployment files and the one final GLM deployment. Historical Coder-Next,
GLM8K/32K test profiles, research profiles and instance templates remain in the
repository, excluded from this installed profile snapshot.

Copy the exact reviewed root source closure from
[`source-closure.json`](../scripts/control/source-closure.json) separately.
Normal Q38 closure includes its pinned manifests, fixture provenance and support
files: profile copying alone is insufficient. Preserve recovery code on root,
independent of data/models mounts. The two-model choice applies to this host's
snapshot; generic catalog discovery still supports future reviewed models.
One model/backend may run at a time; Q38 variants share port and served alias.

## Canonical registered storage input

The supplied launch handoff reports `/etc/local-ai-server/storage.json` absent;
this source task has not checked the host. L2VM must independently verify exact
mounts and publish the reviewed canonical registration through its own bounded
authorization. No installer workflow or mutation helper is added here.

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

Configured context is declared; `verified_occupied_tokens` remains null and
occupied provenance unknown. Q38 128K/256K source declarations, successful
short probes and GLM test budgets do not supply occupied-context evidence.
L2VM still owes actual Linux mount loss, local authenticated control service,
CAS/idempotency/interrupt/safe-stop, exact two-model catalog, direct LAN auth
through all applicable fixed ports, and real model stream/tool continuation
acceptance. These live requirements remain **NOT_TESTED** in L2.

## Focused source verification

Run `python3 -m unittest tests.test_l2_live_snapshot -v`. The suite copies only
the manifest selection into a temporary config root, binds actual Manager
profiles and exercises real discovery/protected synthetic receipt reads.
The GLM32K and old D1 runtime test sources are included only inside temporary fixtures. No model
payload, Docker, key, service or host is used; incomplete source publication and
missing evidence are tested as unavailable. This is not installer qualification.
