# I1W writer API

Status: frozen API revision 2, including the wrapper-forwarding contract found
by the actual L1 fixture. The first API was published before source edits;
coordination Revision2 contains I1c's ACK and frozen role draft, and Revision3
requires exact model containment. I1W owns only `storage_io.py` and focused QA.
Base: `c0e1a1dff0ac1647ed5207f05247ff63f72f7cc7`.

## Owned change and public signatures

```python
MountedStorageGuard(storage, *, roles=("data", "models"), mountinfo_reader=None)
MountedStorageGuard.__call__() -> dict
MountedStorageGuard.guard() -> dict  # existing alias
MountedStorageGuard.check_path(path) -> dict
MountedStorageGuard.verify_full() -> dict
AnchoredRoot(path, guard, *, uid=0)
AnchoredRoot.check(relative="") -> dict
AnchoredRoot.guard(relative="") -> dict  # existing alias
```

`check_path` accepts a normalized absolute string or Path for the actual
operation, including its final component even if it does not exist yet. It
checks the protected fixed registry bytes/inode/ancestry and current mountinfo
in one guarded observation, then checks every component from the registered
mount through that path. Each component must still resolve to the captured
registered role's exact mount entry (including mount ID), device and filesystem.
An unregistered descendant bind is refused even when its device is unchanged.
Unrelated descendant mounts outside the operation and existing managed-root
checks do not invalidate an operation. A registered model mount remains valid
for a models-authorized operation. Every intermediate component is checked,
including before a transition into a registered nested model mount.

`AnchoredRoot.check(relative)` retains all held descriptor and parent-name
identity checks and additionally uses `guard.check_path(absolute_operation)`
when supplied the mounted guard. Every writer operation checks its own path:
directory creation/traversal, file creation/open/read/write/truncate/fsync,
stat, unlink, and both ends of replace. The final component is included.
`proc_path(relative)` validates the suffix at issuance; a subprocess using a
path suffix still requires caller monitoring of that relative path and is not
made an atomic mount-namespace transaction by this API.

Existing no-argument trusted verifier callbacks remain compatible. They do
not acquire a mountinfo capability by wrapping a guard in a lambda. Mounted
guard snapshots carry `path_validation_required: True` (ephemeral observation
metadata, not registered identity). An `AnchoredRoot` given such a snapshot
requires a callable `check_path` on the guard object or bound method owner;
otherwise it raises `StorageIOError("storage_path_verifier_required")` before
opening an anchor. It also checks this requirement on subsequent checks.
Wrappers must retain the marker and forward the method. Explicit unmarked
fixture/verifier callbacks retain their existing responsibility for verification;
their results are not continuous mounted-guard or actual Linux evidence.

The supplied L1 `_BoundMountedGuard` does not forward this method. L1 must add
the following adapter contract in its owned source (not changed by I1W):

```python
def check_path(self, path):
    return self._snapshot(_mounted_call(self._mounted.check_path, path))
```

It must require a callable underlying `check_path`, preserve its own captured
identity checks and sanitize errors consistently. Historical fixture path
projection must explicitly translate physical paths back to logical paths for
`check_path`, then project the returned snapshot. A lambda that drops the method
is refused. I1W must not discover/unwrap private `_mounted` members or bypass
the binding's checks. The original supplied snapshot remains test-only and
unmodified except for the candidate writer overlay; forwarding is an L1 gate.

No lease, package, lifecycle, Storage implementation, or installer stage claim
changes belong to this patch. Source review and actual Linux tests remain gates.

## Required I1c Storage callable contract

```python
Storage.verify(registration=None, *, roles=("data", "models")) -> dict
Storage.guard(registration=None, *, roles=("data", "models")) -> dict
```

The default verifies both roles. The primary reduced scope needed here is
`roles=("data",)`. Canonical nonempty subsets are accepted. Invalid/empty/unknown
selections must fail closed. A reduced
scope must retain **both** immutable role registrations and the full roots map
in the snapshot, but explicitly identify which roles were actually verified
(`verified_roles`). A model device/capacity must not be invented
when it was not verified. Full registry identity checking must remain intact.
Data-only verification can tolerate an unavailable separate model mount while
refusing anchoring or operating in unverified model paths. A distinct registered
model subtree has containment precedence over nested service roots. Otherwise
role selection uses the longest declared root prefix, with `roots.models`
assigned to models and other named roots assigned to data. Ties select models.
More-specific service roots can therefore be used in a data-only guard when
data/model roots coincide; the ambiguous coincident root itself remains
models-owned. A models-only operation through a distinct unverified data-mount
ancestor fails closed; a sibling model mount or verified shared mount does not
require that missing ancestry. Default both-role verification remains compatible.
No environment identity override is accepted.

The mounted guard propagates the same roles to initial and full checks; each
snapshot must cover the requested roles. For old both-role Storage fixtures,
the no-argument default call and absent `verified_roles` retain the previous
both-role meaning. A data-only selection must be explicit and attested; it
must never fall back to a no-argument call following TypeError.

`Storage.guard` remains I1c's alias of `verify`; I1W only calls the keyword
roles contract. I1c also retains `root_payload_guard(registration=None, *,
roles=("data", "models"))` and `verified_roles(roles)` (canonical nonempty
subset). The writer keeps its small equivalent normalization local so the
reviewed base and isolated older L1 snapshot need no unowned source overlay.
Partial snapshots retain only stable unverified-role fields; unverified live
capacity is `None`. No stage or State integration is included here.

## Verification boundary

The supplied L1 snapshot is an uncommitted review/test dependency, not mergeable
source. Its SHA256 is
`a7d6963d5a414a833d9a80b894d860ddfe64246a39fbeba79ada40ebf373cd2a`.
Extract it into task-private temporary storage and overlay only the candidate
`scripts/install/storage_io.py` for actual guard/writer integration tests.
Local tests inject mountinfo and use local descriptor operations; only delegated
I2S Linux tests can establish real bind insertion and lazy-unmount evidence.
