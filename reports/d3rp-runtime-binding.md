# D3RD — measured D3BR source binding and declared N76 contexts

**PASS_SOURCE_BINDING_ONLY. Live acceptance remains NOT_TESTED.**

Source-only Mac-Worker2 task on `milestone/d3rd-runtime-binding`, exact reviewed
base `1e65e17534ae6be3a23ec54bda800ad64fcee7d8`. Installer work remains STOPPED.
Root review is required before Worker1 performs any later live apply. This task
has no ai-vm access, build, image/model download, inference request, host/service
change, instance publication or live test.

## Exact measured identity

The new runtime is `llama-cpp-v0.4.1-d3br`, backend `llama_cpp`, tag
`local/llama-cpp:v0.4.1-b29c606-cu132-sm120-d3p-43e4aeb5b63d`.

| Identity domain | Measured value |
| --- | --- |
| Docker image ID / image index | `sha256:86feba4c82a8ec083d8da31fb8d1648f7b221b724a48eca571f5dd277a0caab9` |
| Platform manifest SHA256 | `384a22a0b15b9668b89e4ec46ed7363f2bb02e91d3344db102411288551ef62b` |
| Image config SHA256 | `89a1ea2575d8a5ea2c2debd618d420ac03194b1c2d54b85972a8ebff850f3938` |
| Measured binary SHA256 | `c81262fd063e9d2fc098d9e116d0ae742ca7ea37344ee3f4b56eb5d088206e0a` |
| Build repository commit | `c7155099e4d8d096b0e946352fbf01e3a9072ab9` |
| Upstream source commit | `b29c606e28a01b1bc8c1351026a0fa6e616bf6c4` |
| Upstream Git tree | `950999fe62b7fe55f44ab5b7394e3c8542f37f12` |
| Combined patch SHA256 | `43e4aeb5b63dbb82d7457526000391ba52d49a408040ec736fb302092e734f3b` |
| Derived Git tree | `0075e6f2ca5b8a3f13c0725e35f60a0ceb2b2b5e` |
| Derived commit | `null` |

The Docker ID differs from preserved D1. The index, platform and config domains
remain separate. Source release remains upstream `v0.4.1`; `source_revision`
and proof `source_commit` remain upstream. The measured version is preserved
verbatim:

```text
version: 0.4.1-dev (build 62, commit b29c606)
built with GNU 13.3.0 for Linux x86_64
```

This version text is not proof of an unpatched tree. Explicit metadata records
`upstream_source_clean:true`, `source_state:verified-patched`, a separate derived
tree and `derived_commit:null`. No patched `source_clean:true` is asserted.

The actual help confirms **17 flags: all 16 inherited D1 flags plus
`--n-cpu-moe`**. Earlier shorthand “16 flags” referred to the baseline subset.
Measured load modes are `auto`, `none`, `mmap`, `mlock`, `mmap+mlock`, `dio`;
the protected instance addition selects exactly `none`. CUDA0 and CUDA1 were
enumerated. D3B2 build/version/help/enumeration PASS does not establish model
kernels, successful load, occupied context, protocol, agents, fusion or workspace.

## Selected source and publication boundary

The exact two new deployments are:

- `configs/deployments/glm-5.3-ud-q4-k-xl-n76-32k.json`: declared 32,768 tokens;
  initial test selection in the operator manifest.
- `configs/deployments/glm-5.3-ud-q4-k-xl-n76-native1m.json`: declared 1,048,576
  tokens; later capacity test candidate.

They are the first two unchanged D3T `_proposal` results with only `runtime`,
`purpose` and `notes` replaced. Both retain `capability_status:NOT_TESTED`, one
slot, loopback30002, alias `glm-5.3`, N76, split1,1, ngl999,
`clear_thinking:true`, restart `no`, and unchanged model/key/storage/budgets.
Unique per-deployment scratch paths are inherited from D3T. F16 KV,
batch2048/ubatch512, threads112 and fusion are effective settings to observe
later; this task invents no launch fields or acceptance evidence for them.
The all-CPU native proposal remains unbound. D1 remains the original rollback.

`configs/control/ai-vm-live-snapshot.json` is an operator manifest, not a loader.
It binds the initial 32K source and an explicit two-file `deployment_sources`
hash mapping, runtime, measured image, proof and six recipe dependencies.
The existing five fixed profile pins and Q38 row are preserved. Context evidence
is `declared_only`; live acceptance remains `NOT_TESTED`.

`scripts/control/source-closure.json`, including its stop-only recovery list,
stays byte-identical. The existing `reports/l2-source-closure-sha256.json` normal
publication inventory refreshes only its original filenames to current reviewed
hashes and adds explicit new GLM runtime/deployment/proof/evidence/recipe
dependencies. Six original entries were stale: Manager and five Q38VC-owned
source/provenance files. Those hashes now refer to base-reviewed bytes, including
Q38VC `77e232d8`; no executable control/Q38/D1 source was changed. Copy only the
explicit fixed profiles and new GLM dependencies, preserving relative paths.
Do not recursively copy configs directories.

## Exact later protected instance addition

This is a delta for the later canonical lease/anchored writer, **not a complete
instance or an instruction to replace the file**:

```json
{
  "runtime_evidence": {
    "llama-cpp-v0.4.1-d3br": {
      "image_id": "sha256:86feba4c82a8ec083d8da31fb8d1648f7b221b724a48eca571f5dd277a0caab9",
      "flags_verified": true,
      "supported_flags": [
        "--model",
        "--host",
        "--port",
        "--alias",
        "--api-key-file",
        "--ctx-size",
        "--parallel",
        "--cpu-moe",
        "--jinja",
        "--no-webui",
        "--n-gpu-layers",
        "--split-mode",
        "--tensor-split",
        "--load-mode",
        "--device",
        "--chat-template-kwargs",
        "--n-cpu-moe"
      ],
      "load_mode": "none",
      "evidence": "/usr/local/lib/llm-server/control-api/reports/d3rp-runtime-proof.json"
    }
  }
}
```

Add only the new runtime key, after reviewing current protected instance bytes.
Preserve D1 runtime evidence, instance identity/storage binding, model receipts,
key, current selected deployment, desired/manual/boot policy, active state and
recovery state. Attesting a runtime does not select or start a deployment.
No instance was published by D3RD.

## Evidence and checks

The actual input proof was delivered from
`/data/build/d3p-d3b2-20260915/evidence/runtime-proof.json`, SHA256
`1d500eae56d6e777b944b2492071c8b3dd28ea350b04f5c72da5b7bd70d052c9`.
The retained build-observation JSON is an explicitly selected projection of that
input; transient process identifiers and device UUID samples are omitted.
Raw selected source/CLI/build artifacts retain their delivered bytes. The new
proof enumerates retained file hashes and original verified paths. All six
recipe hashes must agree with current source, host evidence, image evidence and
`reports/d3br-evidence/provenance.json`; historical D3PD helper/runner hashes
cannot substitute.

`python3 -B scripts/d3rd/verify_binding.py` checks retained-file digests and
cross-evidence consistency for actual image/tag/entrypoint/platform/labels,
source derivation, recipe, measured binary reference, CLI and device output,
profiles and final inventory. This is an offline check over reviewed delivered
measurements; it does not authenticate the operator or remeasure the image.

Generic Manager evidence is a protected operator attestation/reference. Existing
Manager checks the attested flags/load mode, inspects the configured tag,
requires observed immutable ID and exact entrypoint, and requires new N76/native
image equality with runtime validation while refusing D1. It does not parse
patch/tree/recipe evidence or independently verify image labels/architecture.
The source checker and Manager tests deliberately keep those boundaries distinct.

Focused verification passed: **50 tests**, zero skips/failures, covering the
actual-input binder and real Manager paths, unchanged D3T proposals/D1 rollback,
Q38 Manager dispatch and exact Q38VC source/provenance drift checks:

```sh
python3 -B scripts/d3rd/verify_binding.py
python3 -B -m unittest tests.d3rd.test_binding tests.d3rd.test_manager_binding \
  tests.d3t.test_profiles tests.lifecycle.test_qwen38_manager \
  tests.lifecycle.test_qwen38_final_source -v
```

The 13 binder tests use the delivered chosen data and alter image/D1 identity,
flags/help, tag, entrypoint, each of six recipe files, patch/tree provenance,
verbatim version and profile fields. Rehashed altered evidence is refused by
cross-checking the other measured inputs. The 11 Manager tests use controlled
Docker observations to render both real contexts and demonstrate the narrower
existing Manager checks. No test runs Docker or reads model/key bytes.

All 32 delivered file hashes passed; 19 raw files were retained byte-for-byte,
plus one sanitized selected observation. The final inventory contains 36
original filenames and 31 explicit GLM additions. Supplied build/final guards
passed with the recorded warning that root free space was below 6 GiB (still
above the supplied 4 GiB stop boundary); this task makes no current host claim.
Raw help/CMake output keeps its measured whitespace, including trailing spaces;
strict source whitespace checks exclude those retained measurement files.
The early in-progress inventory test saw a stale proof hash while the origin
metadata was being finalized; refreshing the inventory resolved it before the
50-test passing run.
No installer suite, all-repository rerun, occupancy or boot/reboot matrix is part
of this task. The old L2 test named `explicit_glm_owner_gap` documents historical
null slots; the task-owned D3RD inventory test validates the completed selection.

## Handoff

The final source commit, full `D3RD.bundle`, author/committer, feature publication,
committed-tree and imported-bundle check results are recorded outside the repo
in `../final.md`, `../session.md` and adjacent check artifacts, avoiding circular
commit/evidence pins. Root reviews the concrete source/proof/instance delta.
Worker1 owns any separately coordinated later apply and live acceptance. Stop
at this source handoff; no automatic VM retry follows.
