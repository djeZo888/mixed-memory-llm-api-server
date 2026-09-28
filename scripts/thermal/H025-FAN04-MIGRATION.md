# FAN04 version 2 migration procedure

Requires exact root reviewGO for this source and this procedure. Keep the unit
stopped and failed; do not start/reset it before successful migration. No unit,
credential, source-mask, mode, or curve write is part of migration. Preserve the
historical lifecycle PASS and all failures. This is a one-time state migration,
not automatic recovery. An absent baseline still permits first installation;
an existing unversioned/v1 baseline always raises baseline_migration_required.

The following executable Python procedure runs ONLY on ai-harness as the state
owner after root review. Run from the reviewed scripts/thermal directory. Supply
a private root-reviewed manifest at REVIEW_MANIFEST with canonical digest()
values for each current state file listed below (digest(null) for absent files), plus
prior_status_sha256 for the exact historical healthy own-40 status JSON placed
at PRIOR_STATUS. Both inputs are host-local, not credentials. Root must compare
the original baseline raw SHA256 against
b9ceeb03ad04763df9fb1d0b02fd11051b60f3b603c246f8d7093fccc47205ff before approval.
The exact prior healthy status is preserved in FAN02 results under
final_fresh_status.status; source9293a17d and canonical invariant45069284.
Unknown/missing approval values are a refusal, never auto-filled from live state.

```python
import copy, hashlib, os
from pathlib import Path
import cha_fan3 as f
names = ('baseline.json', 'blocked.json', 'status.json',
         'invariant-mismatch.json', 'pending-write.json', 'uncertain-write.json')
manifest = f.decode(f.protected(Path(os.environ['REVIEW_MANIFEST']), 65536))
prior = f.decode(f.protected(Path(os.environ['PRIOR_STATUS']), 65536))
assert f.digest(prior) == manifest['prior_status_sha256']
assert prior['state'] == 'healthy' and prior['errors'] == []
assert type(prior['desired_duty']) is int and prior['desired_duty'] == 40
assert type(prior['readback_duty']) is int and prior['readback_duty'] == 40
assert prior['source_sha256'] == '9293a17dcdfbda23015142d9fd57099e133fda48e251f488484550b1b8df3d0c'
store = f.Store()  # Existing singleton flock, held through final latch clear.
bmc = f.BMC(f.BMC_FILE)  # Host-local original credential; read-only BMC calls.
try:
    old = {name: store.read(name) for name in names}
    assert all(f.digest(old[n]) == manifest[n] for n in names)
    raw = f.protected(f.STATE / 'baseline.json', 65536)
    assert hashlib.sha256(raw).hexdigest() == 'b9ceeb03ad04763df9fb1d0b02fd11051b60f3b603c246f8d7093fccc47205ff'
    assert 'schema_version' not in old['baseline.json']
    assert f.digest(f.configuration_only(old['baseline.json'])) == prior['invariant_sha256']
    pending = old['pending-write.json']
    assert not pending or pending.get('state') == 'verified'
    original = copy.deepcopy(old['baseline.json'])
    for point in original[f.PATHS[1]][3]['CurrentPWMdata'][:4]:
        assert point['Duty'] is None
        point['Duty'] = 40
    target = f.invariant(original)
    # Do not derive accepted target settings from current hardware.
    bmc.login()
    fresh = bmc.snapshot()
    assert f.shape(fresh) == 40 and f.invariant(fresh) == target
    # Fixed names, no append history, refuse rerun/overwriting archives.
    for name in names:
        assert store.read('migration-v1-' + name) is None
    for name in names:
        store.write('migration-v1-' + name, {'present': old[name] is not None,
                    'value': old[name], 'sha256': f.digest(old[name])})
    store.write('migration-v1-prior-status.json', prior)
    store.write('migration-v1-fresh-snapshot.json', fresh)
    store.assert_held()
    assert all(store.read(n) == old[n] for n in names)  # CAS under held lock.
    # Revalidate target/own duty immediately before atomic baseline replace.
    fresh = bmc.snapshot()
    assert f.shape(fresh) == 40 and f.invariant(fresh) == target
    store.write('migration-v1-final-snapshot.json', fresh)
    store.assert_held()
    assert all(store.read(n) == old[n] for n in names)
    store.write('baseline.json', target)
    # A failure after baseline replacement leaves the original latch in place.
    # Preserve the archived proof, publish a nonhealthy migration status.
    store.write('status.json', dict(prior, state='migration_pending_restart',
                updated_at=f.utc(), invariant_sha256=f.digest(target)))
    store.write('migration-v2-receipt.json', {'at': f.utc(), 'own_duty': 40,
                'baseline_sha256': f.digest(target), 'bmc_puts': bmc.puts})
    assert bmc.puts == 0 and store.read('blocked.json') == old['blocked.json']
    store.write('blocked.json', None)  # Last atomic change; original archived.
finally:
    bmc.logout()
    store.close()
```

The original mismatch and verified pending/uncertain receipts remain in place
and are archived. A new controller run may replace current receipts, while
migration-v1-* preserves the originals. Interrupted migration is an explicit
review hold; never rerun blindly or clear a latch to work around assertions.
After successful migration only, root may authorize installation/restart and
focused live verification of the exact reviewed source. FAN04 executed this procedure after root exact GO; see
reports/h025-fan04-20260928/results.json for the executed receipt. Cooperative CAS is protected by the existing flock; it
cannot fence an unrelated process that disregards that lock.
