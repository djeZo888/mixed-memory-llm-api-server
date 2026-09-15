# L1B bounded lifecycle consumers

Source base: reviewed `4ab862f`, including L1 `bed7532` and I1W `bb007686`.
Only lifecycle consumers, focused fixtures/tests and lifecycle documentation
change. See [checks and pending dependencies](../../reports/l1b-lifecycle-consumers.md).

## U1B pre-stop contract

While holding the same canonical lifecycle lease used for the subsequent
`Manager.dispatch(..., lease=lease)` calls, load the target deployment and call
`Manager.prepare_start(target)`. Complete this before stopping the old backend.
`prepare_start` returns `None`; its existing host guard can persist an anchored
report. It validates source/artifact/storage/evidence/auth/DockerRootDir as before
and, for non-legacy deployments, now invokes the existing read-only
`create_args(target)` validation. This inspects the actual configured image tag,
compares its immutable ID, and applies the existing entrypoint/launcher checks.
Failure must leave the old backend running. Legacy compose retains its contract.

This creates no preflight token/cache/framework and performs no trial switch.
`_start()` still calls preflight and repeats `create_args()` before creating a
container; source checks before mutation remain. A successful earlier preflight
cannot authorize a later image change. Canonical borrowing and close-only OFD
export ownership are unchanged. U1B must integrate this call under its own owner;
L1B's synthetic switch sequence is consumer-contract evidence only.

## Path-aware writer and persistent roots

`_BoundMountedGuard.check_path(path)` forwards the actual absolute path unchanged
to reviewed I1W, validates the snapshot's stable identity, and sanitizes errors.
Missing capability fails closed. Historical tests translate fixture coordinates
with an object that retains this public method; a lambda is insufficient.

`Manager.persistent_json` accepts a normalized descendant of the registered data
root, selects the most-specific containing `services`, `state` or `logs` root,
and passes a normalized suffix relative to that anchor. A report immediately
under logs needs no `mkdir('.')`. The coincident data/models root remains
models-owned; choosing a services/logs anchor does not change that role or permit
data-only traversal into a distinct models subtree. The real I1W writer retains
final role/path authorization. Registry and descriptor checks are unchanged.

## I1c / I1O dependency boundary

I1c must publish frozen source for `Storage.verify/guard(registration=None, *,
roles=('data','models'))`. The default verifies both; data-only explicitly
attests `verified_roles`, preserves both complete immutable registrations and
all roots, and omits unverified model device/capacity. Missing separate models
must permit data service/report writes while full verification and model access
still fail. Equal roots require normal save/report/stop persistence to succeed
before faults are introduced. Unregistered mount aliases remain refused.

The current base does not implement that Storage API. The dependency tests fail
explicitly there. The supplied frozen I1c patch, SHA256
`4a2ecd75e94d0724cd5428ed383ec2687a473f212f95192dd5be03f2de3e8148`,
passes all four actual-source role/writer tests in an isolated verification copy.
It is uncommitted provisional test input, excluded from this source bundle;
committed I1c source must replace it before final integration acceptance.
No synthetic role attestation or unowned Storage implementation is substituted.
I1O separately owns installer caller/completion integration: canonical package
lease export, package admission/recovery, protected source/instance/recovery/boot
installation and acceptance. L1B does not enable installer stages or alter
runtime/environment/profile sources.

Trusted recovery stop remains available from its exact protected volatile
container identity. Failed durable writes report `state_persisted:false`; restore
registered storage and repeat stop before relying on reboot persistence. Real
Linux mount insertion/loss, boot/reboot, package ownership, actual image auth,
GPU inference and fresh installation remain runtime gates, untested here.
