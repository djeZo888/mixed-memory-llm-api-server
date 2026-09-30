# H013 image recovery lease admission — source candidate

Offline PASS: 67 image runtime tests, including 14 new recovery cases. Live
acceptance is NOT EXECUTED. Only `scripts/image_runtime/service.py`, its tests
and this report changed. No remote contact, deployment, inference, recovery,
Sova action, push or subagents. Installer work and H011/H012 evidence untouched.

Required base: `5d30814899dbe3ce4c0b9f320cc3a8804fd9ab66`; branch
`worker2/h013-image-recovery`. Base differs from root-requested `b5636dc` only in
`docs/h013-status-20260927.md` and the H013 production receipt (verified locally).
Native ID `01a0e16a-a7e3-7001-aa9d-404fc63a3c76`; wrapper start
`2026-09-27T05:50:58Z`, hard deadline `2026-09-27T06:05:58Z`, from
`../events-01.jsonl`, `../started-01-utc`, `../hard-deadline-utc` relative to repo.
The wrapper sends TERM after 885s; work closes before that threshold.

## Failure and fixed contract

Root/Worker1 supplied the original failure, not reproduced here: boot llmctl
finished and the API started at 05:37:45 UTC. Attempt
`3a83363f37a748d690b55b4411566a7b` began at 05:37:45.670 and failed
`recover_admission` / `lifecycle_busy` at 05:37:45.792; later storage status was
verified, no backend was created, API remained CLOSED. One ordinary API restart
was recovering when assigned; this worker does not infer its outcome. Original
remote evidence and existing receipts remain unchanged.

The existing ExitStack admission pattern now accepts an absolute deadline.
Preflight, mutation admission and post-warm verification use the same recovery
start +840s deadline. Failure cleanup uses the existing start +900s ceiling,
after exact-unit stop/kill has consumed its time. Acquisition polls the SAME
canonical nonblocking lease at at most 0.2s intervals. No new lock, lease deletion,
guard retry, body retry, restart loop, failure clearing or deadline extension.
A body never begins at/after its admission deadline. Start retains its 2s lease
allowance; stop remains nonblocking. Already acquired start admission now also
checks expiry before yielding, the minimal shared-helper deadline safeguard.

Verification and cleanup previously retained the expired mutation lease in
`runtime.lease`; both now assign their actual newly acquired capability. Current
verification/cleanup methods do not presently consume that field for hardware
checks, but retaining a stale capability was incorrect. Tests assert the current
capability at every mocked guarded operation.

Permanent admission denial before reset dispatch cannot stop, reset, save or
restart owned work. After mutation begins, existing exact-unit and validated
container cleanup remains permitted and bounded. Body LeaseBusy, hardware/storage
failures and ownership refusals propagate without replay. This fixes contention
handling; it does not serialize entire recovery attempts across the released
systemd boundary. Existing sole-owner coordination is still required. The
existing conservative `mutation_started` flag is set before `reset_owned()`:
a failure inside reset may therefore invoke settlement even if reset failed
before its first mutation. That pre-existing policy is not broadened or rewritten.

## Ordering and deployment effect — review only

API template already has `After=network.target llmctl-boot.service`; backend
already has `After=docker.service systemd-tmpfiles-setup.service llmctl-boot.service`
and mount dependencies. Neither unit is changed. Boot ordering orders systemd
jobs; it cannot exclude later independent canonical readiness/control/lifecycle
holders, and does not synchronize the separate recovery phase acquisitions.
Effective installed drop-ins were not queried in this source-only task.

Matched deployment must bind the following exact paths and fields after root
review and Worker1 settlement/current installed guards:

| Installed item | Required disposition |
| --- | --- |
| `/data/services/image21-runtime-20260923/source/service.py` | New candidate raw SHA256 `748b94a5b17e6c2cb4229d69f4dd142dc9cf099b05206f0f97e6c04173cab052`; preserve protected root:ai 0644 metadata |
| `/data/services/image21-runtime-20260923/config.json` | Update only `source_sha256["service.py"]` to that hash; preserve protected root:ai 0600 and the exact other three runtime entries |
| Same config `release_source_sha256` | Preserve the complete exact map of `RELEASE_SOURCE_FILES`; release root `/data/services/releases/h005-qwen0-mount-order-fix-20260925` is unchanged |
| `scripts/image_runtime/source-closure.json` in that release | Declaration unchanged: same runtime/release/API/helper/unit file sets, no new import dependency or self hash |
| `/etc/llm-server/image-api.json` | Preserve qualification manifest bytes: runtime/model revisions, runtime image digest, profiles and evidence hashes do not change; this schema has no host `service.py` source hash |
| `/usr/local/lib/llm-server/image-api/scripts/image_api/{__init__.py,serve.py,protection.py,protocol.py,uploads.py,backend.py,app.py}` | Source and any external hashes remain unchanged |
| `/usr/local/libexec/llm-image-backend-recover`, both installed systemd units | Unchanged fixed invocation and ordering; no daemon-reload required by this source-only delta |
| Root's current external source/delivery manifest and installed-byte receipt | Append a new reviewed transition binding candidate commit, service raw hash and changed config raw hash; preserve predecessor manifests, API qualification/source hashes, units, helper and native image/overlay pins |

The exact *current external manifest filename* and current installed config raw
hash are not supplied in this checkout and were not queried remotely. Worker1
must identify them from the current protected deployment handoff, not rewrite
historical H005 proposals or assume old H003/H006 receipt hashes are current.
Source contract: `verify_source_closure()` and `RUNTIME_SOURCE_FILES` /
`RELEASE_SOURCE_FILES`; deployment precedent:
`docs/h006-maintenance-robustness.md` matched source/config table. No API schema,
`SOURCE_SHA` (upstream runtime revision), checkpoint, immutable native image,
`configs/runtimes/h005-runtime-binding.json` or overlay pin changes are needed.

Publishing matched bytes alone changes future helper invocations and does not
restart a running backend. To exercise the fix or reopen a CLOSED API, an ordinary
API restart invokes its existing recovery helper once, which resets the backend,
runs `systemctl restart llm-image-backend.service`, cold loads and performs the
existing warm generation. Thus an API restart is NOT a backend-preserving action;
no separate backend restart command or image rebuild is required. A currently
running old helper will not acquire these Python changes. Coordinate Worker1's
current recovery/load before any later deployment. No activation is authorized
or executed by this report.

## Checks and handoff

- `python3 -B -m unittest discover -s tests/image_runtime -p 'test_*.py' -v`:
  **67 PASS**; full output in `test-output.txt`. Includes source closure, real
  fixture-root canonical lock, foreign-owner refusals, start admission and
  settlement regressions. New recovery cases use fake clocks and commands,
  including real context-manager entry contention; no real sleeps. Existing
  canonical-lock regression retains its pre-existing local 0.01s wait.
- Focused command: `python3 -B -m unittest discover -s tests/image_runtime -p 'test_recovery_admission.py' -v`;
  14 cases included in the final 67-test run (initial focused run: 13 PASS before
  adding the cleanup-body no-replay case).
- Python `compile(Path(file).read_bytes(), file, 'exec')` for all three changed
  Python files: PASS, no bytecode writes. `git diff --check`: PASS.
- Original supplied failure, configured ordering and offline contract are
  distinct from unexecuted deployed startup/permission/guard/warm/API acceptance.
  No cold-load timing, contention fairness or current image health claim.

Bundle target: `../H013-IMAGE-RECOVERY.bundle`, against the exact required base.
Root reviews/publishes; Worker1 owns any subsequent matched deployment and live
acceptance. Accepted Sova 1M artifacts remain a separate unchanged delivery.
