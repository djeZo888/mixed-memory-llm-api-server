# U1B frozen installer contract v1 — 2026-09-15

Source-only worker, root base 4ab862f + U1 core 60eaca1. Combined review required.
I1c owns provisioning, install, generation/reuse, activation and acceptance.

* Unit filename: llm-control.service; template scripts/control/llm-control.service.in.
* Fixed root-owned source closure: /usr/local/lib/llm-server/control-api.
  ExecStart=/usr/bin/python3 -I -B /usr/local/lib/llm-server/control-api/scripts/control/serve.py
  WorkingDirectory=/; one process and one mutation executor. No data BindsTo,
  RequiresMountsFor, mount condition or data-dependent process startup.
* Fixed root-owned mode0600 config: /etc/llm-server/control.json. Exact JSON:
  {"schema_version":1}. No source/path/backend/host/port/deadline overrides.
  Normal profile root is SOURCE_ROOT/configs, installer protected reviewed snapshot.
* Dedicated fixed CONTROL source: /etc/llm-server/control-api-key root:root 0600.
  32..256 printable nonspace ASCII bytes with optional final newline. Generate
  once/reuse safely on resume. Inference key remains its registered data path.
  LoadCredential=control-api-key:/etc/llm-server/control-api-key; adapter reads
  /run/credentials/llm-control.service/control-api-key (root 0400 or 0600).
  No secret argv/env/unit/log values; installer validates distinct key bytes and
  rejects inode/path alias when inference provisioning evidence is available.
  U1B creates/copies NO real keys. Production also compares when normal evidence
  is available; inability to read inference storage does not block recovery.
* Strict IPv4 127.0.0.1:30000 only; all routes authenticated. Existing U1
  /control/v1 catalog/status/switch/stop/operations schema_version=1 unchanged.
  CLI only --help and --check-binding. Check validates root source/config/key,
  no listener; absent/unsafe installation exits 3 with bounded safe code.
* Journal: registered DATA/services/llm-control/operations.json root0600;
  actual Manager binding.read_json and persistent_json anchored writer. Existing
  U1 schema=1, <=1MiB, 128 durable entries, 24h terminal retention, 16 volatile
  recovery receipts. No root-disk persistent operation/log fallback.
* Canonical common.lifecycle_lease.acquire_lease(blocking=False) held across
  actual package admission, CAS identity+semantic generation, durable admission,
  prepare_start(target) AND create_args(target) image validation, old stop,
  selection/start/observation/outcome. Borrow exact lease in Manager.dispatch.
  No guessed L1 APIs. L1B reviewed candidate final preflight tests still required.
* Fresh process recovery: actual recovery_manager + read_state(recovery=True) +
  trusted_container(immutable identity) + running; never status/deployment/key.
  Identity binds instance/deployment/container/image and Docker StartedAt; U1
  semantic generation is opaque CAS counter, refreshed after process restart.
  Exact /run/llmctl/recovery.json only; stopped tombstone preserved on restore.
* Root closure includes ONLY required control/lifecycle/common/install Python
  dependencies plus reviewed normal configs and pinned small evidence needed by
  selected lifecycle paths. Exact file manifest to accompany source publication;
  separate directory avoids L1 boot closure's strict file-set contract.
* Unit ReadWritePaths=-@REGISTERED_DATA_ROOT@ /run/llmctl, RuntimeDirectory=llmctl
  is NOT used (L1 owns shared directory; must not erase recovery on control stop).
  Preserve existing hardening; install validates missing-data mount namespace,
  Docker and lifecycle guards rather than assuming template proves it.

Unimplemented external dependencies: reviewed L1B image seam/descendant anchor;
I1W role-capable anchored storage; I1c exact snapshot/config/key/journal directory/
unit provisioning and credential separation evidence; Linux installed unit,
real mount-loss/reboot and two-model HTTP/inference acceptance. Worker fixtures
prove local HTTP with controlled resources only, never full installation.

## Frozen additions after actual source inspection

Exact closure manifest: scripts/control/source-closure.json (recovery_files are
mandatory root imports; normal_files/config snapshots never gate recovery boot).
Control port30000 is reserved: installed inference deployments on it remain
unavailable until their owning profile is changed. Status now includes the same
server-relative endpoint schema as catalog (null during recovery). Context adds
{configured_tokens, configured_provenance, verified_occupied_tokens:null,
verified_occupied_provenance:"unknown", evidence:[]} while retaining context_limit.
No configured cap establishes measured occupied-context proof; D3M remains owner.
Actual source pre-admission checks use ticket deadline; L1 loader finite external
limits can outlive that deadline, without allowing canceled destructive work.
L1B/I1c provisional supplied patches may be composed only in isolated TEST COPY;
they are not included as U1B owned source and do not imply combined review.

## Final user roster — publication requirement

The current approved offered roster is exactly TWO TOTAL models: GLM5.3 and
Qwen3.8-27B FP8. Coder-Next implementation/live work is deferred; historical
source/tests/evidence do not authorize publication. I1c owns the approved
protected configs/deployments snapshot and default selection; it MUST exclude
Coder-Next and every other deferred deployment from that installed snapshot,
even if their acquisition evidence remains on data storage. U1B enumerates only
that protected published deployment directory, not model-integrity or saved-state
keys. Do not hardcode a permanent maximum of two or add a model-specific router.

The source/import closure is exact for the L1B modules tested here. Q38-owned
Manager/runtime changes must be combined-reviewed and their required import
closure refreshed/verified by the source/installer owners before Q38 activation;
this handoff makes no Q38 runtime or new-closure acceptance claim. No additional
0.5.14 fixes, model acquisition, VM access or inference were performed by U1B.
