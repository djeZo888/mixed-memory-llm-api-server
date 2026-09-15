# Q38VR — first actual diagnostic fixture FAIL; bounded task complete

## Result

One unchanged reviewed CLI invocation ran on Worker1 through SSH ai-vm at
2026-09-15T03:20:28.720472+00:00–2026-09-15T03:20:29.390420+00:00 (0.667665 seconds).
The **131072** context failed with `q38s_image_fixture_failed` / **ATTACH_FAILED**;
outer helper exit **1**. **262144 was not started. No auth receipt or READY state
was produced.** No retry, source correction, extra runtime invoker or model
activation followed. Installer remains STOPPED.

The first observable terminal result was written immediately to
`../phase-result.md`, its committed [copy](q38vr-evidence/phase-result.md), and
ai-vm `/data/logs/q38vr-20260915/phase-result.md` before postchecks or packaging.
The shipped CLI exposes no intermediate 128K PASS event. Its unchanged internal
loop gates 256K on all 128K native/result checks and verified owned cleanup.

## Newly retained safe diagnostic

| Field | Observed result |
| --- | --- |
| Host runtime inspection | PASS_HOST_INSPECT, context 131072 |
| Attach CLI return code | 2 |
| Container exit observed before cleanup stop | EXITED, exit 2 |
| CLI / native signal | null / null; no signal established |
| Failure kind / phase / operation | CLI_NONZERO_EXIT / ATTACH / START_ATTACH |
| Safe fixture callsite | run_pinned_image.py:580, FixtureFailure |
| Inner fixed failure code | actual_image_fixture_failed |
| Inner stdout capture | COMPLETE, 163 bytes, SHA256 de15e3556c43867d2ef3b95dd412f208684f10ddb95573c39b9d0577bbd8fcd2 |
| Inner stderr capture | COMPLETE, 0 bytes, SHA256 e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 |

Static source mapping places line 580 at `run_cache_probe`'s compound child
acceptance check: successful return, empty stderr, and stdout within 131072
bytes. The retained hint identifies that boundary only. **Which predicate
failed, the cache child's return code/output, and the underlying native cause
remain unknown.** `START_ATTACH` is an operation label, not a cause. This
allowlisted diagnostic hint is excluded from successful receipt acceptance;
it does not prove that installed native source, cache, library, auth, parser or
template gates passed. No raw child errors, messages, locals, traceback text,
headers, bodies, environment or key values were disclosed.

Full safe record: [fixture-execution.json](q38vr-evidence/fixture-execution.json).

## Exact owned cleanup

Owned container ID: `411f949b60cd102390123cd75eddc6f2ca0abe186e1c6225bbfaa4a56d048e9a`.
Name: `q38b-fixture-87b24617f0287ea276117a7ce380202a`.

Shipped cleanup reported **QUIESCENT_REMOVAL_VERIFIED**: exact name/label/image/ID
ownership, PID-zero quiescence, non-force removal, then absence verification.
Independent successful Docker listings filtered by the exact full ID and exact
name both returned empty stdout/stderr. **Created 1, removed 1, remaining 0.**
No unresolved owned identity, additional removal, unrelated container action,
force removal or global prune occurred. See [final-checks.json](q38vr-evidence/final-checks.json).

## Source and guard authority

- Executed task snapshot: commit `cb2e49c2bea670a3d72f9cce08f8c51c194b6c67`, tree `dae3d3cfc3acc9c35e81ee2d9d1918533f355114`;
  **764** exact committed files at `/data/build/q38vr-20260915/source`.
  Root-owned directory0555 / files0444 or executable0555; source root
  device2065/inode44307638. All file hashes, sizes, modes, single links and
  protected ancestry passed before/after; final exact directory set passed.
- Archive SHA256: `632d093f25e1c6fa1541e5169d3052cc231152bbaeeb3ffa7df9be6260d42b6f`.
  [Source manifest](q38vr-evidence/source-manifest.json) SHA256:
  `4a4dcd9bebb000f71fcd74143b9a433a4d49aa4c2451676ae1d2f3249a074b2d`.
- Outer fixture SHA256: `9757a9b097c601c2201c78052bd05e81c1db6c97d140befba26b4895b1496653`;
  inner: `185ac9c1faf663c619ef64da84f1ac7ff1bfc4530a50a2947909ade2b14a4118`;
  provenance: `407eae14b0433b5017ef0b66c772eb78f5d7b25ec951672d4d94e2ecfb823ee2`;
  adapter `scripts/lifecycle/qwen38.py`: `480011184c43e2bc425e32e78a7cd57c71ac7925829f49d6cfaaa868506df404`.
- Actual guard authority was exclusively the reviewed installed registered
  guard at `/usr/local/lib/llm-server/control-api/scripts/common/registered-storage.py`,
  SHA256 `21cf082a841aeab9470bd6704b77104961b9d4afcaec696d90aa22b65f5b6f3d`;
  adjacent `scripts/install/storage.py` SHA256
  `4f834e92d149ea1955e79d34c53c18bf8c5846a4121d779e135a50d31a615505`.
  Both exact hashes and all protected ancestors passed pre/post.
- Registered fixed `/etc/local-ai-server/storage.json`: root:root0600,
  parent0700, SHA256 `626db7130b644199f5f632b2ac3c04f86cdd382121573aa6f3825bbca8de9c27`.
  Installed protected 46-file closure manifest SHA256
  `bb0176749bd35deace1643d1a70c42be92a9f0b7bc629d41663c594678365f55`;
  every declared file's hash/size/mode/owner/single-link protection passed pre/post.
  This installed closure remains base `5e713441d9ea164b81860ee795c5ef35972ee8e3`
  with historical Q38B fixture pins, explicitly awaiting L2 Q38VD refresh. It is
  distinct from the executed task snapshot; Q38VR did not change it.
- [VM-GUARDS.json](q38vr-evidence/VM-GUARDS.json) preserves the supplied corrected
  D3 source baseline exactly. Its protected deployed files also hash-verified;
  legacy guards were not used as an execution fallback.

Registration-ready release and numeric evidence were checked before work, and
[coordination-input.md](q38vr-evidence/coordination-input.md) was checked each
phase, including root's first-failure bounded-finish instruction.
The supplied ready prose's `/data/logs` root:root claim is an acknowledged typo:
actual **uid0/gid1000/mode2755/inode47972353**, protected and non-group-writable.
`/data/build` is uid0/gid1001/mode2755/inode21757953. Q38VR changed no existing
parent owner/group/mode. New task parents are root:root0700; evidence files0600.
`task_paths: true` in preflight/stage means *absent before creation*.

## Verification and preserved boundaries

| Check | Result |
| --- | --- |
| Registered data and root guards before stage, before fixture, after fixture | PASS |
| /data UUID | 8daf56f1-5649-4163-9d87-919c2d271875 |
| /data/models-large UUID | a6d4ab58-84e1-4e48-9a67-13ad1c6f6e0a |
| Both exact mountpoints / ext4 / fsroot `/` | PASS pre/post |
| Root available bytes preflight / postfixture | 5209284608 / 5209182208 |
| Root STOP below 4 GiB | Not triggered; below-6-GiB warning retained |
| Shipped provenance and qwen38_oci validators | PASS before/after |
| Exact image unchanged; no pull | PASS |
| Historical Q38V snapshot / historical evidence | All 535 source files and 28 evidence files unchanged |
| GLM selected metadata | ID/image/status/PID/start time/restart-count digest unchanged |
| llm-control.service final | inactive/dead, disabled, MainPID0 |
| Actual native fixture | FAIL at 131072; 262144 NOT_RUN |
| Live model/native serving lifespan/agent acceptance | NOT_TESTED |

Actual image `.Id` is the platform-manifest domain
`sha256:37bbbd3444732a464bbc68dee4fb0164e0ce9e18e2f027f3fc967f1152d3c262`;
config remains `sha256:e6238090791a938ab86dd21a9a6394192dad15237e815df557cf83524d54b813`.
The reviewed `qwen38_oci` reconciliation passed unchanged for linux/amd64 and
source revision `0bcd822377da7b5718e674eaf9c870d349424dd1`.

The [exact launch plan](q38vr-evidence/fixture-plan.md) preserves NVIDIA runtime
with NVIDIA_VISIBLE_DEVICES=none, no GPU/device maps/network, private tmpfs
cache/model/secrets, readonly root/source, and unique owned container lifetime.
The shipped 30s create / 600s attach / 30s cleanup / 2s CLI drain bounds and
signal handling were unchanged. No source correction or new test framework was
added. No installer, build, package, service/network mutation, model/key access,
live inference/API/client request or restart was performed. Model artifacts were never mounted/read/loaded or changed; their
contents were deliberately not rehashed. No old `/tmp` checkout was used.
The initial optional control-status query named the wrong unit and is
non-authoritative; the exact final `llm-control.service` observation above
supersedes it. No service action occurred.

Reproducible guard command (no overrides):

```text
sudo -n /usr/bin/python3 -I -B /usr/local/lib/llm-server/control-api/scripts/common/registered-storage.py --root-guard --json
```

Direct `--json` without `--root-guard` also verified both registered volumes.
Optional guard reports used only existing protected task paths below registered
`/data/logs`; no report-root override or guard framework was added.

## Artifacts and next action

Private VM report/evidence/temp root: `/data/logs/q38vr-20260915`.
Raw outer stdout/stderr remain private there; only safe structured metadata and
hashes are committed. Source archive and exact readonly snapshot are retained.
Final report-only commit/bundle/identity/secret-scan verification are recorded
in `../Q38VR-handoff.md` after packaging. No push.

**Root reviews the retained child acceptance boundary and assigns any fresh
bounded source diagnostic correction. No further fixture retry, 256K run or
model activation is authorized by this result.** Even a future full 128K/256K
PASS would establish synthetic native fixture proof only, not live model proof.
