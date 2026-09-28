"""Passive discovered GPU fixtures. No live commands, hardware or owner writes."""
import unittest

from tests.test_node_projection import BOOT, NEXT_BOOT, Cached, sample
from control import node_collectors as collectors
from control.node import NodeStatus, SERVICES
from control.passive import BoundedObservers, MAX_COLLECTORS

EXTRA = 'GPU-aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'
SECOND = 'GPU-aaaaaaaa-bbbb-cccc-dddd-ffffffffffff'
ASSIGNED = SERVICES['qwen-gpu0'][0]


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.now = 100.0
        self.boot_id = BOOT
        self.inventory = collectors.InventoryCollector()
        self.inventory.last_proof = ({'boot_id': BOOT, 'complete': True,
            'gpu_uuids': [ASSIGNED, EXTRA]}, self.now)
        self.calls = []
        self.failed_gpus = set()
        self.pci = {EXTRA: '00000000:01:00.0', SECOND: '00000000:02:00.0'}

    def command(self, argv, seconds):
        self.calls.append((argv, seconds))
        gpu = argv[1].removeprefix('--id=')
        if gpu in self.failed_gpus:
            raise ValueError('private error must not escape')
        return ('<nvidia_smi_log><gpu><uuid>' + gpu + '</uuid>'
            '<product_name>Fixture Ada</product_name><pci><pci_bus_id>' + self.pci[gpu] +
            '</pci_bus_id></pci><temperature><gpu_temp>33 C</gpu_temp>'
            '</temperature></gpu></nvidia_smi_log>')

    def collector(self):
        return collectors.DiscoveredGpuCollector(self.inventory, run=self.command,
            boot=lambda: {'boot_id': self.boot_id}, clock=lambda: self.now,
            wall=lambda: 1790637300 + self.now)

    def project(self, raw, **changes):
        return NodeStatus(Cached({'boot': sample({'boot_id': self.boot_id}),
            'inventory': sample(self.inventory.last_proof[0]),
            'gpu_metrics': sample(raw, **changes),
            'gpu:' + ASSIGNED: sample({'boot_id': self.boot_id,
                'gpus': [{'uuid': ASSIGNED, 'temperature_c': 27}]})})).snapshot()

    def test_added_and_reordered_gpu_uses_uuid_and_current_pci(self):
        collector = self.collector()
        for ordering, pci in (([ASSIGNED, EXTRA], '00000000:01:00.0'),
                              ([EXTRA, ASSIGNED], '00000000:06:00.0')):
            self.inventory.last_proof[0]['gpu_uuids'] = ordering
            self.pci[EXTRA] = pci
            rows = {r['uuid']: r for r in self.project(collector(2))['gpus']}
            self.assertEqual(rows[EXTRA]['pci_bus_id'], pci)
            self.assertEqual(rows[EXTRA]['temperature_c'], 33)
            self.assertEqual(rows[EXTRA]['affected_services'], [])
            self.assertIsNone(rows[EXTRA]['generation'])
            self.assertEqual(rows[EXTRA]['state'], 'ok')
        self.assertTrue(all(args[1] == '--id=' + EXTRA for args, _ in self.calls))

    def test_one_unassigned_failure_does_not_erase_peers(self):
        self.inventory.last_proof[0]['gpu_uuids'] += [SECOND]
        self.failed_gpus.add(EXTRA)
        raw = self.collector()(2)
        snapshot = self.project(raw)
        rows = {r['uuid']: r for r in snapshot['gpus']}
        self.assertEqual(rows[EXTRA]['state'], 'error')
        self.assertEqual(rows[EXTRA]['reason'], 'collector_failed')
        self.assertIsNone(rows[EXTRA]['temperature_c'])
        self.assertEqual(rows[SECOND]['temperature_c'], 33)
        self.assertEqual(rows[ASSIGNED]['temperature_c'], 27)
        self.assertNotIn('private error', str(snapshot))

    def test_missing_assigned_identity_is_preserved_without_metrics(self):
        for complete in (True, False):
            snapshot = NodeStatus(Cached({'boot': sample({'boot_id': BOOT}),
                'inventory': sample({'boot_id': BOOT, 'complete': complete, 'gpu_uuids': [EXTRA]})})).snapshot()
            rows = {r['uuid']: r for r in snapshot['gpus']}
            self.assertIn(ASSIGNED, rows)
            self.assertEqual(rows[ASSIGNED]['affected_services'], ['qwen-gpu0'])
            self.assertIsNone(rows[ASSIGNED]['temperature_c'])
            self.assertEqual(rows[ASSIGNED]['freshness'], 'unknown')

    def test_unknown_stale_or_changed_boot_inventory_does_not_probe(self):
        collector = self.collector()
        for proof in (None, ({'boot_id': BOOT, 'complete': True, 'gpu_uuids': [EXTRA]}, 80),
                      ({'boot_id': NEXT_BOOT, 'complete': True, 'gpu_uuids': [EXTRA]}, 100)):
            self.inventory.last_proof = proof
            with self.assertRaises(ValueError):
                collector(2)
        self.assertEqual(self.calls, [])

    def test_outer_age_and_failure_never_refresh_child(self):
        raw = self.collector()(2)
        row = next(r for r in self.project(raw, age_ms=16000)['gpus'] if r['uuid'] == EXTRA)
        self.assertEqual(row['age_ms'], 16000)
        self.assertEqual(row['freshness'], 'stale')
        row = next(r for r in self.project(raw, state='timeout', reason='collector_timeout')['gpus'] if r['uuid'] == EXTRA)
        self.assertEqual(row['state'], 'timeout')
        row = next(r for r in self.project(raw, freshness='stale')['gpus'] if r['uuid'] == EXTRA)
        self.assertEqual(row['freshness'], 'stale')

    def test_one_extra_slot_bounded_production_capacity(self):
        callbacks = collectors.production_callbacks()
        self.assertEqual(len(callbacks), 19)
        self.assertEqual(MAX_COLLECTORS, 19)
        self.assertIn('gpu_metrics', callbacks)
        self.assertEqual(len([key for key in callbacks if key.startswith('gpu:')]), 4)
        BoundedObservers(callbacks).close()
        with self.assertRaises(ValueError):
            BoundedObservers({str(i): lambda _: {} for i in range(20)})

    def test_unassigned_timeout_has_fair_budget_and_healthy_peer_keeps_capture_age(self):
        self.inventory.last_proof[0]['gpu_uuids'] += [SECOND]
        calls = []
        def command(argv, seconds):
            calls.append(seconds)
            if argv[1] == '--id=' + EXTRA:
                self.now += seconds
                raise TimeoutError('private timeout')
            return self.command(argv, seconds)
        collector = collectors.DiscoveredGpuCollector(self.inventory, run=command,
            boot=lambda: {'boot_id': self.boot_id}, clock=lambda: self.now,
            wall=lambda: 1790637300 + self.now)
        rows = {r['uuid']: r for r in self.project(collector(2))['gpus']}
        self.assertEqual(len(calls), 2)
        self.assertTrue(all(0 < budget < 1 for budget in calls))
        self.assertLess(self.now - 100, 2)
        self.assertEqual(rows[EXTRA]['state'], 'timeout')
        self.assertEqual(rows[SECOND]['state'], 'ok')
        self.assertEqual(rows[ASSIGNED]['temperature_c'], 27)

    def test_removed_unassigned_gpu_does_not_accumulate_collectors(self):
        collector = self.collector()
        collector(2)
        self.inventory.last_proof[0]['gpu_uuids'] = [ASSIGNED]
        self.assertEqual(collector(2)['gpus'], [])
        self.assertEqual(collector.collectors, {})


if __name__ == '__main__':
    unittest.main()
