"""Offline Linux resource/real registered-storage guard wiring; no VM access."""
import copy
import json
from pathlib import Path
import sys
import threading
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent / 'lifecycle'))
from storage_fixtures import RegisteredFixture
from control.node_resources import DiskCollector, NetworkCollector, disk_counters
from control.passive import BoundedObservers
from control import node_collectors


class Clock:
    value = 100.
    def __call__(self):
        return self.value


def wait_for(predicate):
    limit = time.monotonic() + 2
    while not predicate() and time.monotonic() < limit:
        threading.Event().wait(.001)
    assert predicate()


def net(rx, tx, *, virtual=100000):
    return ('Inter-| Receive | Transmit\n face |bytes packets errs drop fifo frame compressed multicast|bytes packets errs drop fifo colls carrier compressed\n'
            f'ens18: {rx} 0 0 0 0 0 0 0 {tx} 0 0 0 0 0 0 0\n'
            f'veth0: {virtual} 0 0 0 0 0 0 0 {virtual} 0 0 0 0 0 0 0\n')


class DiskTests(unittest.TestCase):
    def setUp(self):
        self.fixture = RegisteredFixture('/data', '/data/models', split=True)
        self.addCleanup(self.fixture.close)
        self.clock = Clock()
        self.calls, self.stats = [], []
        self.counters = '8 1 sda1 0 0 10 0 0 0 20 0 0 0 0\n8 17 sdb1 0 0 30 0 0 0 40 0 0 0 0\n8 33 sdc1 0 0 50 0 0 0 60 0 0 0 0\n'
        def run(argv, seconds):
            self.calls.append((argv, seconds))
            return self.fixture.runner.run([Path(argv[0]).name, *argv[1:]])
        self.run = run
        def stat_volume(path, device):
            self.stats.append((path, device))
            cap = {'8:1': 32, '8:17': 1000, '8:33': 2000}[device] * 1024**3
            return {'total_bytes': cap, 'available_bytes': cap // 2}
        self.stat = stat_volume
        self.collector = DiskCollector(run=run, clock=self.clock, wall=lambda: 1700000000 + self.clock.value,
                                       stat_volume=stat_volume, read_diskstats=lambda: self.counters,
                                       system_root=self.fixture.root)

    def test_real_registered_roles_capacity_and_two_sample_rates(self):
        first = self.collector(2)
        volumes = first['volumes']
        self.assertEqual([v['volume_id'] for v in volumes], ['root', 'data', 'models'])
        self.assertEqual([v['state'] for v in volumes], ['ok'] * 3)
        self.assertEqual([v['total_bytes'] // 1024**3 for v in volumes], [32, 1000, 2000])
        self.assertEqual(first['total_bytes'], volumes[0]['total_bytes'])
        self.assertTrue(all(v['read_bytes_per_second'] is None for v in volumes))
        self.clock.value += 5
        self.counters = self.counters.replace(' 10 ', ' 20 ').replace(' 30 ', ' 60 ').replace(' 50 ', ' 100 ')
        second = self.collector(2)
        self.assertEqual([v['read_bytes_per_second'] for v in second['volumes']], [1024, 3072, 5120])
        self.assertEqual(second['read_bytes_per_second'], 1024)
        self.assertTrue(all(argv[0].startswith('/usr/bin/') and 0 < seconds <= 2 for argv, seconds in self.calls))

    def test_missing_model_mount_cannot_report_data_or_root_capacity(self):
        self.collector(2)
        for row in self.fixture.runner.blocks:
            if row.get('uuid') == 'models-uuid':
                row['mountpoints'] = [None]
        self.stats.clear()
        result = self.collector(2)
        self.assertEqual([v['state'] for v in result['volumes']], ['ok', 'ok', 'unknown'])
        models = result['volumes'][2]
        self.assertEqual(models['reason'], 'mount_identity_unavailable')
        self.assertEqual(models['mount_point'], '/data/models')
        self.assertIsNone(models['total_bytes'])
        self.assertIsNone(models['observed_at'])
        self.assertNotIn(str(self.fixture.local('/data/models')), [path for path, _ in self.stats])

    def test_uuid_or_filesystem_misbind_is_unknown_independent_of_data(self):
        row = next(r for r in self.fixture.runner.blocks if r.get('uuid') == 'models-uuid')
        original = copy.deepcopy(row)
        for key, value in [('uuid', 'unexpected-uuid'), ('fstype', 'xfs')]:
            row.update(original); row[key] = value
            result = self.collector(2)['volumes']
            self.assertEqual(result[1]['state'], 'ok')
            self.assertEqual(result[2]['state'], 'unknown')
            self.assertIsNone(result[2]['total_bytes'])

    def test_protected_registration_missing_or_unprotected_keeps_root(self):
        registry = self.fixture.local(self.fixture.registry_path)
        registry.chmod(0o644)
        result = self.collector(2)
        self.assertEqual(result['volumes'][0]['state'], 'ok')
        self.assertEqual(result['volumes'][1]['reason'], 'registration_unknown')
        self.assertIsNone(result['volumes'][1]['mount_point'])
        registry.unlink()
        self.assertEqual(self.collector(2)['volumes'][2]['state'], 'unknown')

    def test_capacity_exception_is_partial_and_does_not_fabricate_rates(self):
        def stat_volume(path, device):
            if device == '8:17':
                raise OSError('fixture volume offline')
            return self.stat(path, device)
        self.collector.stat_volume = stat_volume
        result = self.collector(2)['volumes']
        self.assertEqual([v['state'] for v in result], ['ok', 'unknown', 'ok'])
        self.assertEqual(result[1]['reason'], 'capacity_unavailable')
        self.assertIsNone(result[1]['read_bytes_per_second'])

    def test_mount_changed_during_capacity_never_publishes_result(self):
        def stat_volume(path, device):
            result = self.stat(path, device)
            if device == '8:33':
                next(r for r in self.fixture.runner.blocks if r.get('uuid') == 'models-uuid')['mountpoints'] = [None]
            return result
        self.collector.stat_volume = stat_volume
        result = self.collector(2)['volumes'][2]
        self.assertIsNone(result['total_bytes'])
        self.assertEqual(result['state'], 'unknown')

    def test_registration_change_during_sample_invalidates_registered_roles_only(self):
        def stat_volume(path, device):
            result = self.stat(path, device)
            if device == '8:33':
                registry = copy.deepcopy(self.fixture.registration)
                registry['models']['uuid'] = 'changed-uuid'
                self.fixture.jsonfile(self.fixture.registry_path, registry)
            return result
        self.collector.stat_volume = stat_volume
        result = self.collector(2)['volumes']
        self.assertEqual([v['state'] for v in result], ['ok', 'unknown', 'unknown'])
        self.assertIsNone(result[1]['total_bytes'])

    def test_disk_counter_failure_does_not_hide_current_capacity(self):
        self.counters = 'broken\n'
        result = self.collector(2)
        self.assertEqual(result['volumes'][2]['state'], 'ok')
        self.assertIsNone(result['volumes'][2]['read_bytes_per_second'])
        with self.assertRaises(ValueError):
            disk_counters('8 1 sda1 0 0 10 0 0 0 20 0 0 0 0\n' * 2)

    def test_shared_model_filesystem_is_explicit_not_summed(self):
        fixture = RegisteredFixture('/data', split=False)
        self.addCleanup(fixture.close)
        collector = DiskCollector(run=lambda argv, _: fixture.runner.run([Path(argv[0]).name, *argv[1:]]),
                                  stat_volume=self.stat, read_diskstats=lambda: self.counters,
                                  system_root=fixture.root)
        volumes = collector(2)['volumes']
        self.assertEqual(volumes[1]['mount_point'], volumes[2]['mount_point'])
        self.assertEqual(volumes[1]['filesystem_uuid'], volumes[2]['filesystem_uuid'])
        self.assertEqual(volumes[1]['total_bytes'], volumes[2]['total_bytes'])

    def test_disk_hang_keeps_one_slot_and_independent_network_fresh(self):
        entered, release = threading.Event(), threading.Event()
        calls = []
        def hang(path, device):
            calls.append(1); entered.set(); release.wait(); return self.stat(path, device)
        self.collector.stat_volume = hang
        network = NetworkCollector(read=lambda: net(100, 200), interface=lambda name: 2 if name == 'ens18' else None, clock=self.clock)
        observers = BoundedObservers({'disk': self.collector, 'network': network}, clock=self.clock)
        try:
            observers.tick(); self.assertTrue(entered.wait(1))
            wait_for(lambda: observers.read('network')['state'] == 'ok')
            observed = observers.read('network')['observed_at']
            self.clock.value += 30
            for _ in range(300):
                observers.tick()
                observers.read('disk')
            self.assertEqual(len(calls), 1)
            self.assertEqual(observers.read('disk')['state'], 'timeout')
            wait_for(lambda: observers.active_count() == 1)
            self.assertEqual(observers.read('network')['freshness'], 'fresh')
            release.set(); wait_for(lambda: observers.active_count() == 0)
            self.assertIsNone(observers.read('disk')['value'])
        finally:
            release.set(); observers.close()


class CpuMemoryTests(unittest.TestCase):
    def test_cpu_guest_counters_are_not_double_counted_and_full_node_percent(self):
        raw = ['cpu 100 0 0 100 0 0 0 0 80 0\n']
        collector = node_collectors.CpuCollector(read=lambda: raw[0], count=lambda: 72)
        self.assertIsNone(collector(2)['percent'])
        raw[0] = 'cpu 200 0 0 100 0 0 0 0 160 0\n'
        self.assertEqual(collector(2), {'percent': 100, 'logical_count': 72})

    def test_memory_kib_conversion_and_independent_nullable_pressure(self):
        mem = 'MemTotal: 1000 kB\nMemAvailable: 250 kB\nSwapTotal: 100 kB\nSwapFree: 80 kB\n'
        with patch.object(Path, 'read_text', side_effect=[mem, 'some avg10=1.25 avg60=0.5 avg300=0.1 total=100\nfull avg10=0.25 avg60=0.1 avg300=0.0 total=5\n']):
            result = node_collectors.collect_memory(2)
        self.assertEqual(result['total_bytes'], 1024000)
        self.assertEqual(result['swap_free_bytes'], 81920)
        self.assertEqual(result['pressure_some_avg10'], 1.25)
        self.assertEqual(result['pressure_full_avg10'], .25)
        with patch.object(Path, 'read_text', side_effect=[mem, FileNotFoundError()]):
            result = node_collectors.collect_memory(2)
        self.assertEqual(result['available_bytes'], 256000)
        self.assertIsNone(result['pressure_some_avg10'])


class NetworkTests(unittest.TestCase):
    def test_guest_nic_rates_exclude_virtual_double_count_and_reset(self):
        clock, raw = Clock(), [net(1000, 2000)]
        collector = NetworkCollector(read=lambda: raw[0], interface=lambda name: 2 if name == 'ens18' else None, clock=clock)
        self.assertEqual(collector(2), {'rx_bytes_per_second': None, 'tx_bytes_per_second': None})
        raw[0] = net(1100, 2500, virtual=9999999); clock.value += 5
        self.assertEqual(collector(2), {'rx_bytes_per_second': 20, 'tx_bytes_per_second': 100})
        raw[0] = net(1, 2600); clock.value += 5
        self.assertEqual(collector(2), {'rx_bytes_per_second': None, 'tx_bytes_per_second': 20})
        collector.interface = lambda name: 3 if name == 'ens18' else None
        clock.value += 5
        self.assertEqual(collector(2), {'rx_bytes_per_second': None, 'tx_bytes_per_second': None})

    def test_no_identified_nic_is_unknown_not_zero(self):
        collector = NetworkCollector(read=lambda: net(100, 200), interface=lambda _: None)
        self.assertIsNone(collector(2)['rx_bytes_per_second'])

    def test_failed_network_read_preserves_sample_age_and_disk_independence(self):
        clock, raw = Clock(), [net(100, 200)]
        network = NetworkCollector(read=lambda: raw[0], interface=lambda _: 2, clock=clock)
        observers = BoundedObservers({'network': network, 'disk': lambda _: {'total_bytes': 123}}, clock=clock)
        try:
            observers.tick(); wait_for(lambda: observers.active_count() == 0)
            observed = observers.read('network')['observed_at']
            raw[0] = 'malformed'; clock.value += 20
            observers.tick(); wait_for(lambda: observers.active_count() == 0)
            result = observers.read('network')
            self.assertEqual((result['state'], result['age_ms'], result['freshness']), ('error', 20000, 'stale'))
            self.assertEqual(result['observed_at'], observed)
            self.assertEqual(observers.read('disk')['freshness'], 'fresh')
        finally:
            observers.close()

    def test_fixture_volume_fields_are_exact_additive_contract(self):
        path = Path(__file__).resolve().parent / 'fixtures/service_resilience/disk-volumes-v1.json'
        fixture = json.loads(path.read_text())
        self.assertEqual([v['volume_id'] for v in fixture['volumes']], ['root', 'data', 'models'])
        expected = {'volume_id', 'mount_point', 'filesystem_uuid', 'filesystem_type', 'state', 'reason',
                    'observed_at', 'age_ms', 'freshness', 'total_bytes', 'available_bytes',
                    'read_bytes_per_second', 'write_bytes_per_second'}
        self.assertTrue(all(set(v) == expected for v in fixture['volumes']))


if __name__ == '__main__':
    unittest.main()
