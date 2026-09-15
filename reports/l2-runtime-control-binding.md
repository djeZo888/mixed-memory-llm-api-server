# L2 current-VM runtime/control binding

**PASS for bounded source handoff**, 2026-09-15. Installer work remains **STOPPED**.
Final source and publication gates are recorded below; actual ai-vm access,
Linux mount loss, service activation, model/runtime/inference and direct LAN
acceptance are **NOT_TESTED** and remain Worker1 L2VM requirements.

## Bounded source change

- Compose reviewed integration `6ffd620db7717eb81c615d77c76e9662dbe30027`
  with frozen Q38B `3a470d2b8c90398be0bffe78bccd13fe1c3a0f2e`, then final owner
  source `f17ec2c37d4c706752dd3fbe1978519983578b71`. The final Q38 composition
  preserves its frozen Manager/control bytes. No L2 Q38 adapter/profile edits.
- Consume only the exact N1S helper from owner source
  `05cb7ae253f6b93d5d3e0f55c168960c73075bea`, SHA256
  `ad0c48db68ce47213f292abb74aebc9b321b41baefc3385785bb7322e7e78ddc`.
  No helper edits, network units or firewall asset composition. The control
  path calls only its read-only public loader.
- Extract exactly the supplied Storage read/guard patch, SHA256
  `4a2ecd75e94d0724cd5428ed383ec2687a473f212f95192dd5be03f2de3e8148`.
  Storage had no role-aware verify API despite Manager/I1W requiring it.
  `verify`, `guard` and `root_payload_guard` now accept explicit roles and
  default to full verification. Reduced verification requires root-owned
  registration and retains the entire registered identity. Whole-volume alias
  validation rejects unregistered filesystem exposure, preserving subtree
  binds and path-aware same-device nested-mount refusal.
- Add the optional protected control setting
  `advertised_endpoint_policy: "private_network"`. Consume N1S's no-argument
  protected loader. Only public catalog/status DTOs receive its advertised
  origin, with actual deployed profile port and alias. Default/missing/invalid
  policy retains tunnel DTOs and local authenticated control/recovery. N1S
  code is root-resident; network policy is not a recovery dependency.
- Hand off an exact five-profile source selection for two offered model
  identities, GLM5.3 and Qwen3.8-27B FP8. GLM final runtime, deployment,
  measured patched image and proof/recipe/import closure remain explicit
  D3PD/D3T owner inputs. The old D1 runtime is baseline/rollback only.
  Historical profiles remain in source and are excluded from the installed
  snapshot. This is an operator manifest, not a provisioning framework.

[Snapshot and receipt contract](../docs/l2-live-snapshot.md),
[advertised DTO contract](../docs/control-api.md), and
[exact selection](../configs/control/ai-vm-live-snapshot.json).

## Preserved contracts and source review

The Storage AST audit against composition
`77fbe989e99698603766d11dd008e10d8f3f37ef` changes only existing read methods
`_registered_mount`, `_capacity`, `verify`, `root_payload_guard`; adds
`verified_roles`, `_role_snapshot`, `_whole_volume_aliases`. Every existing
mutation/dispatcher body, including `_uuid_mount_plan`, `_fstab_content`,
`_disk_plan`, `plan`, `_atomic_write`, `adopt`, remains identical. Stricter
shared read validation can reject unsafe aliases; no mutation operation or
installer workflow was introduced. No paused I1c merge was performed.

Independent control review found public serialization isolated from target
lookup, launch/network guards, fingerprint/generation, admission, CAS,
idempotency, interruption acknowledgement and trusted stop. Protected config
and unrelated source integrity errors remain fatal; only the reviewed
`PrivateNetworkError` becomes a tunnel fallback. The optional policy is a
startup snapshot refreshed by control restart. Header/request input never
supplies an origin. Backend readiness is not private-transport acceptance.

No L2 edits to Manager, D3T llama validation/argv, Q38 adapters/profile pins,
client/agent source, storage writer, acquisition, dispatcher, disk operations,
installer stages, units or firewall helpers. N1S helper composition is identical
owner source. Root closure adds only that helper; Q38B's existing list remains.

## Focused verification

**PASS: 255 tests in 16 focused suites**, no skips or expected failures.
[Exact commands, test-file and output hashes](l2-focused-tests.json),
[root closure byte hashes](l2-source-closure-sha256.json), and
[mutation/source scope evidence](l2-scope-evidence.json) are recorded.
All tests use temporary source/config/receipt files, synthetic mounted
identity/command fixtures or local ephemeral HTTP. No native inference runs.

The only preexisting U1B fixture repairs are in control tests: use the existing
actual `MountedStorageGuard`/`AnchoredRoot` writer seam (the old controlled
writer required a 0700 directory and rejected the correctly anchored 0755 logs
root with `fixture_storage_unprotected`), remove its stale expected failure,
and patch the newly explicit optional-policy reader in the existing mocked
entrypoint test. Initial production baseline had 15 fixture setup errors and
one unexpected success; the corrected focused production paths pass. No broad
installer suite or installer qualification was run.

## Outstanding live requirements / next action

Worker1 must compose final approved GLM runtime/deployment/image proof closure,
verify the supplied live UUIDs and exact protected registration, preserve real
model/auth receipts and existing instance ownership, copy the selected root
source/profile closure, and perform its separately authorized deployment.
Current source tests cannot produce installed receipts or prove host safety.

Required live acceptance: actual Linux mount loss and recovery stop, control
service authentication and restart, CAS/idempotency/interrupt/safe-stop,
exact two-model catalog, separate control/inference keys and unchanged loopback
listeners, direct private-network auth, stream/tool continuation, and measured
context/capacity. Q38 128K/256K remain declared; GLM32K/output test budgets are
not product limits. Configured context never becomes occupied-context proof.
