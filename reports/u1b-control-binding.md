# U1B actual lifecycle control binding

Status: **source complete; combined production review required**. Source-only
worker work on `milestone/u1b-control-binding`, starting at `504e3ec0bc00517598b5de377929f748be8314a3`
(reviewed root `4ab862f` plus supplied U1 core `60eaca1a9f7628073677bb90700941633f0612a2`).
No ai-vm access, host install, service activation, disk mutation, model download,
real key handling or inference was performed.

## Result

- Actual L1 `load_manager`/`recovery_manager`, canonical nonblocking borrowed
  lease, authoritative package admission, `prepare_start` plus `create_args`,
  exact immutable stop and select/start calls replace the unavailable adapter.
- The one executor holds the canonical lease throughout CAS, durable receipt,
  target preflight, old stop, selection/start and outcome. No fixture fallback,
  HTTP-supplied config, commands, paths, image references or environment.
- Fixed root source/config/control credential and unit contract are published
  in [u1b-installer-contract.md](u1b-installer-contract.md). Entrypoint binds
  exactly IPv4 `127.0.0.1:30000` after protected installation checks. All routes
  authenticate. WorkingDirectory is `/`; data loss does not remove required
  Python imports, control key or canonical `/run` recovery identity.
- Journal uses actual registered L1 read and anchored write APIs. The reviewed
  P2 fix retains an acknowledged durable receipt/idempotency digest when a
  later write forces volatile stop recovery, including subsequent save/restart.
- Recovery observes exact protected `/run` state with actual `read_state`,
  `trusted_container` and `running`; no recovery profile/key read or inference
  probe. Identity includes immutable container/image and observed StartedAt.
  Recovery outcomes remain `state_persisted:false`; restored normal state retains
  stopped intent. No arbitrary container/name adoption.
- Generic installed catalog uses actual protected completion receipts and small
  profile/runtime/source checks. It neither scans weights nor treats saved Ready
  as observation. Configured context is declared; occupied-context verification
  and unsupported capability/resource proofs stay explicitly unknown. Control
  port30000 is reserved. Catalog/status endpoints are server-relative loopback.

## Validation

| Check | Result | Boundary |
| --- | --- | --- |
| Original worker control aggregate | **179 PASS, 1 expected failure**, 180 run | Base L1 lacks required I1W check_path forwarding; this is not an integration PASS. HTTP behavior uses an explicitly controlled writer. |
| Isolated committed-L1B + frozen-I1c control aggregate | **180 PASS**, no failures/skips/expected failures | Actual role verifier and anchored writer; raw Linux discovery, Docker objects and inference probe results are synthetic. |
| Strict production-adapter HTTP subset (included above) | **16 PASS** | Actual Manager, package admission, OS flock and localhost TCP, with actual candidate guarded writes. |
| Actual role/storage-owner integration | **4 PASS** | Equal-root state/report/stop persistence; split missing-model data persistence and denied model writes; synthetic raw discovery. |
| Root-source closure/entrypoint subset (included above) | **15 PASS** | Real protected-file descriptors; copied 18-file import closure in separate `-I -B` process from `/`; fixed CLI refusal on worker. |
| Worker `serve.py --help`; `--check-binding` | **PASS**; **expected exit 3** | No installed root closure/control credential exists here; no listener opened. |
| Ownership/whitespace/secret/metadata/publication checks | Recorded in taskroot publication evidence | Filename-only secret scans; exact author and committer; feature branch only. |

The HTTP tests reach actual local image inspection under the canonical lease:
missing image, mismatched image ID and invalid entrypoint each cause **zero old
container stops**. They exercise current/stale CAS, explicit interruption consent,
external process lease contention, actual pending-package marker rejection,
durable admission before stop, responsive reads during loading, idempotency and
restart replay, equal/missing inference key behavior, and single active backend.

A separate fresh subprocess, running from `/`, serves real TCP after synthetic
data/config directories and the inference key are physically removed. It returns
trusted recovery CAS, rejects stale CAS and start, stops only the recorded
container, preserves an unrelated container, and writes stopped volatile intent.
Its root control credential and Docker inventory are disposable test resources;
it is **not** the installed systemd entrypoint or a Linux mount-detach test.

Initial strict runs failed before fault injection due to the old L1 guard and
then the legacy fixture's missing raw role discovery. These failures were not
counted as safety evidence. Only received source and controlled raw discovery
were used for the final strict passing candidate run; no guard forwarding,
role verifier or anchored writer was replaced to obtain that result.

## Exact dependency composition

L1B committed source: `9cb93959105468ea0e140598b51493ee0d13ce9e`, fetched from the
supplied full bundle; independent/combined review remains pending. Both tested
production modules and its role test are byte-identical to that commit.

| Input | SHA256 |
| --- | --- |
| L1B supplied candidate patch | `937e90a9ecf4c2f41cbe47d06d828cb67393c882abcdcf2a470dc6921b1ab647` |
| I1c frozen **uncommitted, test-only** Storage patch | `4a2ecd75e94d0724cd5428ed383ec2687a473f212f95192dd5be03f2de3e8148` |
| L1B actual Manager module | `39c3956404f3ef95925faf64dc00dbac0e804dbefba272f378b0a1c21817d652` |
| L1B storage-binding module | `69e61ce6685c310ce83449de75d45b209e63c6454c175f03d42bdad3daea7fbf` |
| Copy-only verification fixture patch | `7976d69373800daf998cd33bf0f3c831c1bf3cd2a00d91b7efe90e2430ca57b9` |

Only `scripts/control/*`, `tests/test_control*`, `docs/control-api.md` and
`reports/u1b-*` are U1B changes. Other owners' production files were composed
only in the isolated verification copy. The U1B branch retains its reviewed base;
installer/root must integrate the matching owner commits for production use.
The taskroot and `reports/u1b-*` contain complete passing logs, source hashes
and the copy-only fixture patch. No supplied uncommitted production dependency is committed here.

## Reproduction

Run the original control suite using the preloaded package command in
[control-api.md](../docs/control-api.md); normal `unittest discover -s tests`
otherwise lets `tests/lifecycle` shadow the production `lifecycle` package.

For the passing candidate check, create an isolated copy of this branch, apply
the supplied L1B two-production-module patch (or extract those exact modules from
`9cb9395`), the SHA-verified frozen I1c patch, then taskroot
`verification-fixtures.patch`. That fixture patch includes the exact L1B role
test plus only the two control test adaptations; it uses actual role verification
and actual I1W writes with controlled raw discovery. Run:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 tests/test_control_production.py -v
PYTHONDONTWRITEBYTECODE=1 python3 tests/lifecycle/test_real_storage_roles.py -v
# Then the preloaded-package full control command documented in control-api.md.
```

Do not apply these test overlays to a live host or publish the uncommitted
Storage patch as reviewed source.

## Remaining dependencies and next action

1. Root must complete L1B/U1B combined review and integrate the final I1c
   role-capable Storage commit matching or superseding the tested frozen patch.
2. I1c must implement/prove exact root source snapshot, config, separate control
   key generation/reuse and comparison, credential/unit/tmpfiles/journal path
   installation, resume and actual hardening/access checks. U1B supplies source
   and contract only; no key is copied here.
3. Installed Linux systemd, source/credential survival across actual mount loss,
   mount namespace behavior after restore, daemon shutdown/restart/boot and real
   package ownership remain **NOT_TESTED**.
4. Actual installed two-model switching, authenticated discovered-endpoint
   inference/OpenCode, interrupted inference stream behavior, GPU performance,
   highest practical occupied context and full/fresh installation remain
   **NOT_TESTED**. Configured context never proves long-context execution.
5. Session external calls use remaining deadline caps. L1 loader construction
   retains finite L1 per-command budgets and can outlive an HTTP deadline;
   cancellation prevents later destructive work and ownership remains held.
   Filesystem/kernel calls and weight hashing cannot be forcibly cancelled in a
   Python thread. Validate host timings before production service acceptance.

Next action: review this source and the exact dependency composition, then let
installer/live owners run their separately authorized acceptance. No production
activation or whole-install completion is claimed by this report.
