"""Cached node projection fixtures; no collectors, lifecycle calls or live I/O."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from control.node import NodeStatus, SERVICES, unknown  # noqa: E402

BOOT = '00000000-0000-0000-0000-000000000001'
NEXT_BOOT = '00000000-0000-0000-0000-000000000002'
GPU = SERVICES['qwen-gpu0'][0]
OTHER_GPU = SERVICES['qwen-gpu1'][0]
SECRET = 'private-value-that-must-never-appear'


def sample(value, **changes):
    result = dict(value=value, state='ok', observed_at='2026-09-25T12:00:00Z',
                  age_ms=0, freshness='fresh', reason=None)
    result.update(changes)
    return result


class Cached:
    def __init__(self, samples):
        self.samples = samples

    def read(self, name):
        if name not in self.samples:
            raise KeyError(name)
        return copy.deepcopy(self.samples[name])


def status(**samples):
    return NodeStatus(Cached(dict(boot=sample({'boot_id': BOOT, 'generation': 4}), **samples)))


def service(snapshot, name='qwen-gpu0'):
    return next(row for row in snapshot['services'] if row['service_id'] == name)


class NodeProjectionTests(unittest.TestCase):
    def test_inventory_only_fifth_gpu_is_visible_unassigned_without_collectors(self):
        fifth='GPU-aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'
        snapshot=status(inventory=sample(dict(boot_id=BOOT,complete=True,gpu_uuids=[fifth]))).snapshot()
        row=next(r for r in snapshot['gpus'] if r['uuid']==fifth)
        self.assertEqual(row['affected_services'],[])
        self.assertEqual(row['freshness'],'unknown');self.assertIsNone(row['memory_total_mib'])

    def test_nested_volume_age_is_not_refreshed_by_parent_and_missing_has_no_capacity(self):
        fixture=json.loads((Path(__file__).parent/'fixtures/service_resilience/disk-volumes-v1.json').read_text())
        raw=fixture.get('resources',{}).get('disk',fixture)
        raw=copy.deepcopy(raw)
        raw['volumes'][0]['age_ms']=10000
        raw['volumes'][2].update(state='unavailable',total_bytes=999,available_bytes=999,age_ms=None,observed_at=None)
        disk=status(disk=sample(raw,age_ms=7000)).snapshot()['resources']['disk']
        self.assertEqual(disk['volumes'][0]['age_ms'],17000)
        self.assertEqual(disk['volumes'][0]['freshness'],'stale')
        self.assertIsNone(disk['volumes'][2]['total_bytes'])
        self.assertIsNone(disk['volumes'][2]['available_bytes'])

    def test_negative_requires_exact_current_boot_fresh_validation_not_missing_record(self):
        raw=dict(boot_id=BOOT,hardware_latched=False,ready=True)
        def row():return service(status(**{'qwen-gpu0':sample(raw)}).snapshot())
        self.assertIsNone(row()['hardware_latched'])
        raw.update(hardware_validation_age_ms=0,hardware_validated_boot_id=BOOT,
                   hardware_validated_gpu_uuids=[GPU])
        self.assertFalse(row()['hardware_latched'])
        for key,bad in (('hardware_validated_boot_id',NEXT_BOOT),
                        ('hardware_validated_gpu_uuids',[OTHER_GPU]),('hardware_validation_age_ms',15001)):
            good=raw[key];raw[key]=bad
            self.assertIsNone(row()['hardware_latched']);raw[key]=good
        raw['hardware_validation_age_ms']=14000
        snapshot=status(**{'qwen-gpu0':sample(raw,age_ms=2000)}).snapshot()
        self.assertIsNone(service(snapshot)['hardware_latched'])

    def test_malformed_gpu_metric_row_cannot_collapse_partial_status(self):
        for bad in ([], {}, None, 1):
            snapshot = status(gpu_metrics=sample({'boot_id': BOOT, 'gpus': [{'uuid': bad}]})).snapshot()
            self.assertEqual(snapshot['gpus'], [])
            self.assertEqual(snapshot['node_id'], 'ai-vm')

    def test_independent_gpu_timeout_does_not_erase_healthy_peer(self):
        data = {'gpu:' + GPU: sample({'boot_id': BOOT, 'gpus': [{'uuid': GPU, 'temperature_c': 32}]}),
                'gpu:' + OTHER_GPU: sample(None, state='timeout', reason='collector_timeout')}
        snapshot = status(**data).snapshot()
        rows = {row['uuid']: row for row in snapshot['gpus']}
        self.assertEqual(rows[GPU]['state'], 'ok')
        self.assertEqual(rows[GPU]['temperature_c'], 32)
        self.assertEqual(rows[OTHER_GPU]['state'], 'timeout')
        self.assertIsNone(rows[OTHER_GPU]['temperature_c'])
        data['gpu:' + GPU]['value']['boot_id'] = NEXT_BOOT
        self.assertEqual(next(row for row in status(**data).snapshot()['gpus'] if row['uuid'] == GPU)['state'], 'unknown')

    def test_empty_complete_inventory_is_valid(self):
        node = status(inventory=sample({'boot_id': BOOT, 'complete': True, 'gpu_uuids': []}))
        inv = node.snapshot()['inventory']
        self.assertTrue(inv['complete'])
        self.assertEqual(inv['gpu_uuids'], [])
        self.assertEqual(inv['state'], 'ok')

    def test_failed_init_empty_inventory_cannot_become_complete(self):
        node = status(inventory=sample({'boot_id': BOOT, 'complete': True, 'gpu_uuids': []},
                                      state='error', reason='collector_failed'))
        inv = node.snapshot()['inventory']
        self.assertFalse(inv['complete'])
        self.assertEqual(inv['state'], 'error')
        self.assertEqual(inv['reason'], 'collector_failed')

    def test_ambiguous_partial_and_other_boot_inventory_are_explicit_unknown(self):
        for boot, complete, uuids in ((BOOT, True, [GPU, GPU]),
                                     (BOOT, False, [GPU]), (NEXT_BOOT, True, [GPU]),
                                     (BOOT, True, ['0']), (BOOT, True, None)):
            with self.subTest(boot=boot, complete=complete, uuids=uuids):
                node = status(inventory=sample({'boot_id': boot, 'complete': complete,
                                               'gpu_uuids': uuids}))
                inv = node.snapshot()['inventory']
                self.assertFalse(inv['complete'])
                self.assertEqual(inv['state'], 'unknown')
                self.assertEqual(inv['reason'], 'inventory_unknown')
                self.assertEqual(inv['gpu_uuids'], [])

    def test_stale_and_timeout_inventory_preserve_failed_envelope(self):
        for changes in ({'freshness': 'stale', 'age_ms': 20000},
                        {'state': 'timeout', 'reason': 'collector_timeout'}):
            with self.subTest(changes=changes):
                inv = status(inventory=sample({'boot_id': BOOT, 'complete': True,
                                               'gpu_uuids': []}, **changes)).snapshot()['inventory']
                self.assertFalse(inv['complete'])
                for key, value in changes.items():
                    self.assertEqual(inv[key], value)

    def test_positive_latch_survives_stale_failed_and_changed_boot_observation(self):
        for changes in ({'freshness': 'stale', 'age_ms': 20000},
                        {'state': 'timeout', 'reason': 'collector_timeout'}, {}):
            raw = {'boot_id': BOOT, 'ready': True, 'admitting': True,
                   'hardware_latched': True, 'reason': 'hardware_fault'}
            observer = Cached({'boot': sample({'boot_id': NEXT_BOOT}),
                               'qwen-gpu0': sample(raw, **changes)})
            row = service(NodeStatus(observer).snapshot())
            self.assertEqual(row['availability'], 'unavailable')
            self.assertEqual(row['reason'], 'hardware_fault')
            self.assertTrue(row['hardware_latched'])
            self.assertIs(row['ready'], False)
            self.assertIs(row['admitting'], False)

    def test_positive_latch_never_fabricates_missing_from_unrelated_reason(self):
        for why in (None, 'service_stopped', SECRET):
            row = service(status(**{'qwen-gpu0': sample({
                'boot_id': BOOT, 'hardware_latched': True, 'reason': why})}).snapshot())
            self.assertEqual(row['reason'], 'hardware_latch_unknown')
            self.assertEqual(row['availability'], 'unavailable')

    def test_stale_negative_latch_and_ready_do_not_claim_available(self):
        raw = {'boot_id': BOOT, 'hardware_latched': False, 'ready': True,
               'admitting': True, 'activity': 'idle', 'active_requests': 0, 'queue_depth': 0}
        row = service(status(**{'qwen-gpu0': sample(raw, freshness='stale', age_ms=20000)}).snapshot())
        self.assertEqual(row['availability'], 'unknown')
        self.assertIsNone(row['hardware_latched'])
        self.assertIsNone(row['ready'])
        self.assertIsNone(row['admitting'])
        self.assertIsNone(row['queue_depth'])
        self.assertIsNone(row['active_requests'])
        self.assertEqual(row['activity'], 'unknown')

    def test_healthy_independent_service_need_not_wait_for_inventory_collector(self):
        raw = {'boot_id': BOOT, 'hardware_latched': False, 'ready': True,
               'admitting': True, 'hardware_validation_age_ms':0,
               'hardware_validated_boot_id':BOOT,'hardware_validated_gpu_uuids':[GPU]}
        row = service(status(**{'qwen-gpu0': sample(raw)}).snapshot())
        self.assertEqual(row['availability'], 'available')
        self.assertEqual(row['activity'], 'unknown')  # Ready never means idle.
        self.assertIsNone(row['queue_depth'])
        self.assertIsNone(row['active_requests'])

    def test_boot_mismatch_never_claims_current_readiness(self):
        row = service(status(**{'qwen-gpu0': sample({'boot_id': NEXT_BOOT,
            'hardware_latched': False, 'ready': True, 'admitting': True})}).snapshot())
        self.assertEqual(row['availability'], 'unknown')
        self.assertIsNone(row['ready'])
        self.assertIsNone(row['admitting'])

    def test_unavailable_observers_leave_every_field_unknown_not_zero(self):
        snapshot = NodeStatus(Cached({})).snapshot()
        self.assertIsNone(snapshot['boot_id'])
        self.assertEqual(snapshot['freshness'], 'unknown')
        for row in snapshot['services']:
            self.assertEqual(row['availability'], 'unknown')
            self.assertIsNone(row['active_requests'])
            self.assertIsNone(row['queue_depth'])
        self.assertIsNone(snapshot['resources']['cpu']['percent'])

    def test_projection_excludes_raw_secrets_and_unqualified_capabilities(self):
        raw = {'boot_id': BOOT, 'hardware_latched': False, 'ready': True,
               'reason': SECRET, 'secret': SECRET, 'password': SECRET,
               'activity': SECRET, 'installed_capabilities': ['chat.completions', SECRET, 'responses'],
               'deployment_id': '../../' + SECRET, 'model_alias': '../../' + SECRET,
               'operation_profiles': [{'operation': 'edit', 'size': '1920x1080', 'secret': SECRET},
                                      {'operation': SECRET, 'size': '1920x1080'}]}
        snapshot = status(**{'qwen-gpu0': sample(raw), 'gpu_metrics': sample({'secret': SECRET,
            'gpus': [{'uuid': GPU, 'name': '\n' + SECRET, 'pci_bus_id': SECRET,
                      'ecc_mode': SECRET, 'sampling_since': SECRET, 'secret': SECRET}]}),
            'memory': sample({'total_bytes': 100, 'available_bytes': SECRET, 'secret': SECRET})}).snapshot()
        self.assertNotIn(SECRET, json.dumps(snapshot))
        self.assertEqual(service(snapshot)['installed_capabilities'], ['chat.completions'])
        self.assertIsNone(snapshot['resources']['memory']['available_bytes'])

    def test_duplicate_gpu_metrics_are_not_projected_under_an_ordinal(self):
        rows = [{'uuid': GPU, 'index': 0}, {'uuid': GPU, 'index': 1},
                {'uuid': OTHER_GPU, 'index': 99}, {'index': 0}]
        gpus = status(gpu_metrics=sample({'gpus': rows})).snapshot()['gpus']
        self.assertEqual([row['uuid'] for row in gpus], [OTHER_GPU])
        self.assertEqual(gpus[0]['affected_services'], ['qwen-gpu1'])


if __name__ == '__main__':
    unittest.main()
