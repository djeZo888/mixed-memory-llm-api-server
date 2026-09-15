# L1 registered lifecycle handoff

L1 is source-only. The server role remains API-only. No host installation,
model acquisition, build, activation, key operation, disk mutation, GPU test or
boot occurred on the worker. See [source report](../../reports/l1-registered-lifecycle.md).
Full installer/production apply remains blocked on reviewed installer completion.

## Public imports and ownership

Add the reviewed checkout's `scripts` directory to `sys.path` once. Import the
canonical module by name in every in-process caller:

```python
from common.lifecycle_lease import acquire_lease, LifecycleLease, LeaseBusy
from lifecycle.storage_binding import RegisteredStorageBinding
from lifecycle.manager import Manager

binding = RegisteredStorageBinding.load(runner)
with acquire_lease() as lease:
    manager = Manager(protected_config_root, protected_instance, binding=binding)
    result = manager.dispatch('start', lease=lease)
```

`runner.run(argv, timeout=30)` is the existing shared storage runner contract.
Instance and transition state must be read under the acquired lease for mutation;
the CLI implements this ordering. Installer admission must reconcile I1R's
package transaction before calling lifecycle. Manager requires the authoritative
read-only `install.prerequisites.assert_package_admission(data_dir, storage_guard)`
under its already-held lease before every ordinary mutation. Any pending marker,
execution gate, orphan inhibitor, missing API or unknown state fails closed with
`package_transaction_recovery_required`. Manager never restores package policy.

`acquire_lease(*, blocking=True, system_root=Path('/'), trusted_uid=0)` yields an
active `LifecycleLease`. CLI/installer use blocking acquisition. Future U1 uses
`blocking=False`; the same atomic nonblocking flock raises `LeaseBusy` with safe
code `lifecycle_busy` for HTTP 409. U1 is a separate task.

Borrowing validates the same-process, active minted object and trusted canonical
inode/descriptor. It does not reopen/reacquire the lock or close the owner's FD.
The only lock is `/run/llmctl/lifecycle.lock`. No CLI/environment root override,
raw-FD Manager borrowing, already-locked flag or alternate installer lock exists.
Status uses nonblocking observation and does not wait for a lifecycle transition.

I1R's detached package watcher inherits the same open-file description. Internal
`common.lifecycle_lease._export_package_watcher_fd(lease)` validates the minted
lease before duplicating a descriptor for `Runner(package_lease_fd=...)`/`pass_fds`.
The caller retains the duplicate for its entire Runner/package-use scope, then
closes it in finally before the outer lease exits, including failure. The watcher
closes its inherited copy independently at quiescence.
Lease cleanup is close-only so the watcher can retain exclusion after caller
exit/death. Manager never accepts that raw descriptor. The ownership semantics
follow the Linux [flock manual](https://man7.org/linux/man-pages/man2/flock.2.html).

L1 owns the new lease module, lifecycle binding/callers, templates, boot renderer,
tests and this report. I1b owns all `scripts/install` files, including the anchored
writer and installer dispatcher. F1S/F1E own auth launcher/runtime corrections;
L1 preserves their source pins and actual-image gate.

## Registered identity and paths

The fixed protected `/etc/local-ai-server/storage.json` schema1 is authoritative.
`RegisteredStorageBinding.load(runner)` builds configuration exclusively from
that registry and uses `install.storage.Storage` for current topology/UUID/
filesystem/ownership/capacity checks. `read_registered(runner)` reads only
protected metadata for explicitly offline status; mutation still calls verify.
`source`, `device` and `parents` are current observations, never durable identity.
`instance.storage_identity` equals `binding.identity`: schema version, complete
roots, and each data/models role's `path`, `mount`, `uuid`, `fstype`.

Data path equals its dedicated mount. Models path is a namespace, which may share
the data filesystem (including equal to the data path) or occupy a registered
nested/sibling second filesystem. Required mounts are deduplicated by actual
mount. A missing second filesystem must fail instead of resolving on its parent.
Root/boot device ancestry, hidden mounts, symlinks, wrong UUIDs and path traversal
are refused by the shared validator and source-path checks.

Host fields are `{role: 'data'|'models', suffix: 'normalized/relative/path'}`.
Only these declared fields are rendered; there is no global string replacement.
Model roots are `models/<model ID>`; container paths remain `/models`, `/cache`,
`/logs`, `/service`, `/run/secrets/llm-api-key` and the reviewed launcher target.
Fresh GLM cache/log/service suffixes use runtime/deployment IDs. An optional
`historical_suffix` preserves exact old GLM paths only for an explicitly imported
instance. F1S retains its reviewed `runtime-cache/sglang-qwen-next` suffix.

`binding.path(role, suffix)` constructs paths. `binding.validate_path(role,path)`
checks registered identity, protected ancestors and the actual filesystem for
that source, including missing descendants. Start checks before artifact access,
Docker create/start and readiness commit. Docker uses preexisting `--mount`
sources; no missing source is automatically created. These checks do not claim
protection against every arbitrary concurrent privileged mount operation.

## Persistent writes and emergency stop

Manager consumes I1b `install.storage_io.MountedStorageGuard(storage)` and
`AnchoredRoot(path, guard, uid=0)` through this exact binding adapter:

```python
with binding.mounted_guard(storage_io, roles=('data',)) as guard:
    with storage_io.AnchoredRoot(binding.path('data'), guard) as data:
        data.mkdir('services/llm-manager/active')
        data.atomic_json('services/llm-manager/active/active.json', stopped_state)
        data.check()
```

`binding.mounted_guard(storage_io, roles=('data','models'))` yields a callable
checked snapshot guard with `verify_full()`. It compares captured stable binding
identity on every returned snapshot, including any full-check result. It calls
the actual shared `verify_full()` before and after the operation and closes the
shared context on success/error, including entry failures after descriptor
construction. I1b retains registration descriptors, rereads mountinfo, and owns
anchored writes/commit checks. The current guard tracks named roots; a new
same-device mount below a deeper descendant remains a required failing shared
integration test. See the report; full mount-race acceptance is not claimed.
Relative `mkdir`, `stat`, `read_json`, `atomic_json` and `check` stay inside that
context. No duplicate writer, timed cache or preflight-only guard is substituted.
The actual reviewed I1b writer source `6e04a510` is merged. Tests distinguish its
real descriptor I/O with synthetic worker mount observations from injected API
contracts and actual Linux mounts. Injected contracts are not integrated evidence.

The initial I1 verifier and frozen mounted-guard constructor check both roles
even for a data-only request. The adapter forwards `roles` only if the actual
shared constructor explicitly supports it. Until I1c supplies that role-aware
guard, missing models can prevent durable stop state.
Emergency stop still uses the protected `/run/llmctl/recovery.json` container
ID/image/owner/instance identity. Missing data, registry, profile, key or model
cannot authorize a new container or stop an unrelated one. Stop does not read
keys or weights. A tiny protected volatile journal uses directory-relative I/O;
no persistent root fallback directory is created.

`state_persisted:false` means restore registered storage and repeat stop before
reboot. A failed commit's volatile record wins over a same-timestamp persistent
record. Failed journal/state writes do not prevent an already trusted stop.

## Fresh instance and explicit historical import

`lifecycle.instance_binding.render_fresh_instance(template,binding,instance_id)`
returns an unactivated bound template without writes. It refuses historical
mount contracts or completed model/auth evidence. Installer supplies its new ID,
reviewed evidence and protected installation after its own required gates.

`import_historical_instance(binding, *, lease, storage_io)` is the explicit
historical `/data` + `/data/models-large` operation. Under the canonical lease,
it requires matching existing UUIDs/paths and rereads the instance through the
anchored descriptor. It only adds `storage_identity` and `historical_import`.
Existing instance ID, paths, model/runtime/auth/acquisition evidence remain
unchanged; state schema2, intent, container, key and artifact files are untouched.
Start/status never call this helper implicitly. Moving an existing deployment
requires a separately reviewed stopped migration.

Immutable expected manifests and F1S launcher/image/parser identities stay fixed.
A fresh GLM or F1S acquisition completion must name the actual derived per-model root,
match every pinned artifact size/hash and explicitly attest completeness. An
explicit historical GLM import retains its prior D1 attestation when no receipt
was recorded; adding a receipt requires it to pass the same root checks. A
registration change does not make a historical completion receipt valid. The
F1S actual pinned-image auth gate remains mandatory; source fixtures cannot set it.

## Boot renderer contract

`lifecycle.boot_unit.render_boot_unit(binding,source_root,instance_path)` returns
text after validating the registered mounts, protected source snapshot and bound
instance. The old `.service` file is an inert contract pointer, not an installable
hard-coded unit. I1b/I1c installs/enables the rendered result.

The generated one-shot intent replayer uses unique exact mount dependencies,
correct systemd mount-unit escaping, `restart=no` containers, bounded start/stop,
private umask and null stdout/stderr. Persisted manual/stopped intent cannot start
a model at boot. A protected recovery-code snapshot at fixed
`/usr/local/lib/local-ai-server` keeps ExecStop independent of data mount loss;
WorkingDirectory is `/`. Installing that tiny code snapshot is an explicit
installer integration requirement, not a host action performed by L1.

## Worker verification

```sh
python3 -m unittest discover -s tests/lifecycle -v
python3 -m unittest discover -s tests/install -v
bash tests/shell/test-llmctl-fixtures.sh
bash tests/shell/test-llmctl-static.sh
git diff --check
```

Use the report for exact executed tests/counts and interface gaps. Worker fixtures
exercise genuine flock processes with synthetic Docker/mount discovery and tiny
files. Linux mount detach, installed systemd boot, real package cgroups, actual
pinned-image auth, GPU inference and fresh installation remain NOT_TESTED here.
