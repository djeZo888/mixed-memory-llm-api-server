"""Synthetic proc/cgroup snapshots through the real REAL72 proof and callsites.

No container, native HTTP request, model, or live host is used by these tests.
"""
import copy
from contextlib import ExitStack
import io
import json
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from benchmark import cpu_budget_host as proof, cpu_budget_profiles as profiles
from benchmark import cpu_budget_telemetry as telemetry, host as host_module
from benchmark.lifecycle import PlanError
from tests.test_cpu_budget_telemetry import stat


class CoherentProcSnapshotTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.proc, self.system, self.group = (self.root / name for name in ('proc', 'sys', 'group'))
        (self.system / 'cpu').mkdir(parents=True)
        (self.system / 'node').mkdir()
        (self.system / 'cpu/online').write_text('0-71\n')
        (self.system / 'node/online').write_text('0-7\n')
        for i in range(8):
            node = self.system / 'node' / ('node' + str(i))
            node.mkdir()
            (node / 'cpulist').write_text(f'{9*i}-{9*i+8}\n')
            (node / 'meminfo').write_text(f'Node {i} MemTotal: 117440512 kB\n')
        self.group.mkdir()
        (self.group / 'cpuset.cpus.effective').write_text('0-7')
        (self.group / 'cpuset.mems.effective').write_text('0-7')
        self.manifest = profiles.postrestart_manifest('Q1')
        self.cid = 'a' * 64
        model_path = next(arg.split('source=', 1)[1].split(',', 1)[0]
                          for arg in self.manifest['create_argv'] if 'target=/models' in arg)
        self.container = {'Id': self.cid,
            'State': {'Running': True, 'Pid': 44, 'StartedAt': '2026-09-20T12:00:00Z'},
            'HostConfig': {'CpusetCpus': '0-7', 'CpusetMems': '',
                           'DeviceRequests': [{'DeviceIDs': self.manifest['gpu_uuids']}]},
            'Config': {'Image': self.manifest['image'], 'Cmd': []},
            'Mounts': [{'Source': model_path, 'Destination': '/models', 'RW': False}]}
        self.set_members(44, 45)
        self.saved = []
        self.host = host_module.LinuxHost.__new__(host_module.LinuxHost)
        self.host.scope = profiles.POSTRESTART_SCOPE
        self.host.load_manifests = {self.cid: self.manifest}
        self.host.identity = Mock(side_effect=self.identity)
        self.host.budget = Mock()
        self.host.budget.data = {'phase': 'PREPARING'}
        self.host.budget.checkpoint.return_value = 100
        self.host.assert_idle = Mock()
        self.host.write_json = Mock(side_effect=lambda name, value: self.saved.append((name, copy.deepcopy(value))))
        self.host.write_bytes = Mock()
        self.host.allocation_proofs, self.host.requests = {}, {}
        self.host.owner = SimpleNamespace(phase='ACTIVE', warm_hold_resumed=False)
        self.host.concurrent_limits = Mock(return_value=({}, {}))
        self.host.cuda_mapping = Mock(return_value=self.manifest['gpu_uuids'])
        self.host.manager = Mock()
        self.host.log_root = '/synthetic-protected-logs'
        self.sample = {'gpus': [{'uuid': gpu, 'free_bytes': 32 * 1024**3}
                                for gpu in self.manifest['gpu_uuids']],
                       'concurrent_resource_gate': {'status': 'PASS', 'reasons': [], 'unavailable_reasons': []}}
        self.host.telemetry = Mock(return_value=self.sample)

    def set_members(self, *members):
        (self.group / 'cgroup.procs').write_text(''.join(f'{pid}\n' for pid in members))
        for pid in members:
            base = self.proc / str(pid)
            base.mkdir(parents=True, exist_ok=True)
            if not (base / 'stat').exists():
                (base / 'stat').write_text(stat(pid, generation=900 + pid))
            (base / 'status').write_text('Cpus_allowed_list:\t0-7\nMems_allowed_list:\t0-7\n')
            (base / 'numa_maps').write_text('1234 default file=/private/model N0=30 N7=10\n')
            (base / 'cgroup').write_text('0::/synthetic-group\n')

    def identity(self, cid):
        self.assertEqual(cid, self.cid)
        members = [int(value) for value in (self.group / 'cgroup.procs').read_text().split()]
        return copy.deepcopy(self.container), self.group, members

    def run_proof(self):
        return proof.coherent_postrestart_cpu_proof(self.host, self.cid, self.manifest,
                                                   proc_root=self.proc, sys_root=self.system)

    def receipt(self):
        return [row for name, row in self.saved if name == 'loads/' + self.cid + '-cpu-snapshot.json'][-1]

    def inject_open(self, callback):
        original = Path.open
        def opened(path, *args, **kwargs):
            callback(path, args, kwargs)
            return original(path, *args, **kwargs)
        return patch.object(Path, 'open', opened)

    def check_complete(self, result, members, attempts):
        self.assertEqual(result['status'], 'PASS')
        self.assertEqual(result['attempt_count'], attempts)
        self.assertEqual([row['pid'] for row in result['processes']], list(members))
        self.assertTrue(all(row['cpus_allowed_list'] == '0-7' and row['mems_allowed_list'] == '0-7'
                            for row in result['processes']))
        self.assertEqual([row['pid'] for row in result['numa_pages']['processes']['owned']], list(members))
        self.assertEqual([row['status'] for row in result['attempts']], ['UNAVAILABLE'] * (attempts - 1) + ['PASS'])
        self.assertNotIn('/private/model', json.dumps(result))
        self.assertNotIn(str(self.root), json.dumps(result))

    def test_stable_full_inventory_is_single_attempt(self):
        self.check_complete(self.run_proof(), (44, 45), 1)
        self.assertGreaterEqual(self.host.identity.call_count, 2)
        self.assertEqual(self.receipt()['attempts'][-1]['status'], 'PASS')

    def test_child_exit_then_fresh_stable_cohort_never_drops_pid(self):
        fired = []
        def exit_once(path, args, kwargs):
            if path == self.proc / '45/stat' and not fired:
                fired.append(True)
                path.unlink()
                self.set_members(44, 46)
        with self.inject_open(exit_once):
            result = self.run_proof()
        self.check_complete(result, (44, 46), 2)
        self.assertIn('45', json.dumps(result['attempts'][0]['cohort']))
        self.assertTrue(result['attempts'][0]['reason'])

    def test_child_generation_race_requires_new_complete_attempt(self):
        fired = []
        def reuse_once(path, args, kwargs):
            if path == self.proc / '45/status' and not fired:
                fired.append(True)
                (self.proc / '45/stat').write_text(stat(45, generation=1945))
        with self.inject_open(reuse_once):
            result = self.run_proof()
        self.check_complete(result, (44, 45), 2)
        self.assertEqual(result['processes'][1]['process_starttime_ticks'], 1945)

    def test_numa_lifetime_gap_requires_fresh_complete_cohort(self):
        fired = []
        def exit_in_numa(path, args, kwargs):
            if path == self.proc / '45/numa_maps' and not fired:
                fired.append(True)
                path.unlink()
                self.set_members(44, 46)
        with self.inject_open(exit_in_numa):
            result = self.run_proof()
        self.check_complete(result, (44, 46), 2)
        self.assertIn('45', json.dumps(result['attempts'][0]['cohort']))

    def test_invalid_numa_maps_with_final_lifetime_race_requires_complete_resample(self):
        cases = (('', 'generation', True), ('malformed', 'generation', True),
                 ('', 'missing', True), ('malformed', 'missing', True),
                 ('', 'missing', False), ('malformed', 'generation', False))
        for maps_text, race, recover in cases:
            with self.subTest(maps=maps_text, race=race, recover=recover):
                self.set_members(44, 45)
                self.saved.clear()
                maps_path, stat_path = self.proc / '45/numa_maps', self.proc / '45/stat'
                stat_path.write_text(stat(45, generation=945))
                maps_path.write_text(maps_text)
                races = []
                def fresh_identity(cid):
                    if races and recover:
                        self.set_members(44, 45)
                    return self.identity(cid)
                self.host.identity = Mock(side_effect=fresh_identity)
                def final_race(path, args, kwargs):
                    if path == maps_path and args and args[0] == 'rb' and (not races or not recover):
                        races.append(True)
                        if race == 'missing':
                            stat_path.unlink()
                        else:
                            stat_path.write_text(stat(45, generation=1945 + len(races)))
                with self.inject_open(final_race):
                    if recover:
                        result = self.run_proof()
                        self.check_complete(result, (44, 45), 2)
                        self.assertEqual(result['attempts'][0]['reason'],
                            'proc_observation_missing' if race == 'missing' else 'proc_generation_changed')
                    else:
                        with self.assertRaisesRegex(PlanError, '^postrestart_cpu_snapshot_unavailable$'):
                            self.run_proof()
                        receipt = self.receipt()
                        self.assertEqual(receipt['attempt_count'], 3)
                        self.assertEqual([row['status'] for row in receipt['attempts']], ['UNAVAILABLE'] * 3)
                        self.assertTrue(all(row['cohort']['pids'] == [44, 45] for row in receipt['attempts']))

    def test_membership_changed_after_complete_reads_requires_resample(self):
        original = self.identity
        calls = []
        def changed(cid):
            calls.append(True)
            if len(calls) == 2:
                self.set_members(44, 45, 46)
            return original(cid)
        self.host.identity.side_effect = changed
        result = self.run_proof()
        self.check_complete(result, (44, 45, 46), 2)

    def test_persistent_missing_child_is_three_attempts_and_safe_fixed_code(self):
        (self.proc / '45/stat').unlink()
        with self.assertRaisesRegex(PlanError, '^postrestart_cpu_snapshot_unavailable$'):
            self.run_proof()
        receipt = self.receipt()
        self.assertEqual(receipt['attempt_count'], 3)
        self.assertEqual([row['status'] for row in receipt['attempts']], ['UNAVAILABLE'] * 3)
        self.assertTrue(all('45' in json.dumps(row['cohort']) for row in receipt['attempts']))
        self.assertNotIn(str(self.root), json.dumps(receipt))

    def test_main_process_missing_is_immediate_identity_refusal(self):
        (self.proc / '44/stat').unlink()
        with self.assertRaisesRegex(PlanError, '^postrestart_cpu_snapshot_identity_changed$'):
            self.run_proof()
        self.assertEqual(self.host.identity.call_count, 1)

    def test_existing_preparation_and_command_deadlines_are_not_reset(self):
        self.host.budget.checkpoint.return_value = 0
        with self.assertRaisesRegex(PlanError, '^STOP_BUDGET$'):
            self.run_proof()
        self.host.identity.assert_not_called()
        self.host.budget.checkpoint.return_value = 100
        deadline = time.monotonic() - 1
        token = host_module._COMMAND_DEADLINE.set(deadline)
        try:
            with self.assertRaisesRegex(PlanError, '^host_operation_deadline$'):
                self.run_proof()
            self.assertEqual(host_module._COMMAND_DEADLINE.get(), deadline)
            self.host.identity.assert_not_called()
        finally:
            host_module._COMMAND_DEADLINE.reset(token)

    def test_preparation_expiry_after_race_blocks_next_attempt(self):
        (self.proc / '45/stat').unlink()
        with patch.object(proof.time, 'monotonic', return_value=1000) as clock:
            def expiry(path, args, kwargs):
                if path == self.proc / '45/stat': clock.return_value = 1101
            with self.inject_open(expiry), self.assertRaisesRegex(PlanError, '^host_operation_deadline$'):
                self.run_proof()
        self.assertEqual(self.host.identity.call_count, 1)
        self.host.budget.checkpoint.assert_called_once()
        self.assertEqual(self.receipt()['attempt_count'], 1)
        self.assertEqual(self.receipt()['attempts'][0]['status'], 'UNAVAILABLE')

    def test_permission_malformed_and_nonproc_missing_are_not_retried(self):
        for variant in ('permission', 'malformed', 'topology_missing', 'numa_permission', 'numa_malformed'):
            with self.subTest(variant=variant):
                self.host.identity.reset_mock()
                saved_stat = (self.proc / '45/stat').read_text()
                target = self.proc / '45/numa_maps' if variant.startswith('numa') else self.proc / '45/stat'
                saved_target = target.read_text()
                if variant == 'malformed':
                    target.write_text('not a Linux stat record')
                if variant == 'numa_malformed':
                    target.write_bytes(b'\xff')
                if variant == 'topology_missing':
                    (self.system / 'cpu/online').unlink()
                def denied(path, args, kwargs):
                    if variant in {'permission', 'numa_permission'} and path == target:
                        raise PermissionError('private path must not become public diagnostic')
                try:
                    expected = FileNotFoundError if variant == 'topology_missing' else PlanError
                    with self.inject_open(denied), self.assertRaises(expected):
                        self.run_proof()
                    self.assertEqual(self.host.identity.call_count, 1)
                finally:
                    target.write_text(saved_target)
                    (self.proc / '45/stat').write_text(saved_stat)
                    (self.system / 'cpu/online').write_text('0-71')

    def test_identity_and_mask_drift_are_immediate_refusals(self):
        for field in ('Id', 'Pid', 'StartedAt', 'cgroup', 'main_generation', 'cpu_mask', 'mems_mask'):
            with self.subTest(field=field):
                self.host.identity.reset_mock()
                old_container = copy.deepcopy(self.container)
                old_group = self.group
                count = []
                def drift(cid):
                    count.append(True)
                    if len(count) == 2:
                        if field == 'Id': self.container['Id'] = 'b' * 64
                        if field == 'Pid': self.container['State']['Pid'] = 45
                        if field == 'StartedAt': self.container['State']['StartedAt'] = '2026-09-20T12:00:01Z'
                        if field == 'cgroup':
                            self.group = self.root / 'replacement-group'
                            self.group.mkdir(exist_ok=True)
                            (self.group / 'cgroup.procs').write_text('44\n45\n')
                        if field == 'main_generation':
                            (self.proc / '44/stat').write_text(stat(44, generation=1944))
                    return self.identity(cid)
                self.host.identity.side_effect = drift
                if field == 'cpu_mask': (self.proc / '45/status').write_text('Cpus_allowed_list:\t0-6\nMems_allowed_list:\t0-7\n')
                if field == 'mems_mask': (self.proc / '45/status').write_text('Cpus_allowed_list:\t0-7\nMems_allowed_list:\t0-6\n')
                try:
                    with self.assertRaises(PlanError): self.run_proof()
                    self.assertLessEqual(self.host.identity.call_count, 2)
                finally:
                    self.container, self.group = old_container, old_group
                    (self.proc / '44/stat').write_text(stat(44, generation=944))
                    (self.proc / '45/status').write_text('Cpus_allowed_list:\t0-7\nMems_allowed_list:\t0-7\n')
        self.host.identity.side_effect = self.identity

    def allocation_io(self, *, logs=None):
        stack = ExitStack()
        stack.enter_context(patch('benchmark.host.command', side_effect=logs or
            (lambda *args, **kwargs: SimpleNamespace(stdout=b'', stderr=b''))))
        stack.enter_context(patch('benchmark.host.http_json', return_value={
            'context_length': 480000, 'tp_size': 1,
            'max_total_num_tokens': 480000, 'max_req_input_len': 479994}))
        stack.enter_context(patch('benchmark.host.parse_qwen_log', return_value={
            'ranks': {'0': {'k_gb_log_label': 1, 'v_gb_log_label': 1}}}))
        stack.enter_context(patch('benchmark.host.allocation_gate', return_value={
            'status': 'ALLOCATION_PROOF_ACCEPTED', 'reasons': []}))
        actual_anchor = proof.postrestart_cpu_anchor
        stack.enter_context(patch.object(proof, 'postrestart_cpu_anchor',
            side_effect=lambda container, group: actual_anchor(container, group, proc_root=self.proc)))
        actual = proof.coherent_postrestart_cpu_proof
        stack.enter_context(patch.object(proof, 'coherent_postrestart_cpu_proof',
            side_effect=lambda host, cid, manifest, **kwargs: actual(host, cid, manifest,
                proc_root=self.proc, sys_root=self.system, **kwargs)))
        return stack

    def test_allocation_refreshes_after_logs_native_http_and_telemetry(self):
        def logs(*args, **kwargs):
            self.set_members(44, 46)
            (self.proc / '45/stat').unlink()
            return SimpleNamespace(stdout=b'', stderr=b'')
        def sampled(cid):
            self.set_members(44, 47)
            (self.proc / '46/stat').unlink()
            return self.sample
        self.host.telemetry.side_effect = sampled
        with self.allocation_io(logs=logs):
            result = self.host.allocation(self.cid)
        self.check_complete(result['observed']['actual_cpu_scope'], (44, 47), 1)
        self.assertEqual(result['observed']['native_capacity']['native_input_limit'], 479994)
        self.assertIn(self.cid, self.host.allocation_proofs)

    def test_allocation_main_generation_drift_during_logs_is_immediate_refusal(self):
        def logs(*args, **kwargs):
            (self.proc / '44/stat').write_text(stat(44, generation=1944))
            return SimpleNamespace(stdout=b'', stderr=b'')
        with self.allocation_io(logs=logs), self.assertRaisesRegex(
                PlanError, '^postrestart_cpu_snapshot_identity_changed$'):
            self.host.allocation(self.cid)
        self.assertNotIn(self.cid, self.host.allocation_proofs)
        self.assertEqual(self.host.identity.call_count, 2)

    def test_numeric_allocation_refusal_does_not_resample_missing_process(self):
        (self.proc / '45/stat').unlink()
        self.sample['concurrent_resource_gate'].update(status='FAIL', reasons=['numeric_resource_failure'])
        with self.allocation_io(), patch.object(proof, 'coherent_postrestart_cpu_proof') as coherent:
            result = self.host.allocation(self.cid)
        coherent.assert_not_called()
        self.assertEqual(result['allocation']['status'], 'STOP_ALLOCATION_PROOF')
        self.assertNotIn(self.cid, self.host.allocation_proofs)

    def test_quiescent_resource_danger_refuses_before_cpu_resampling(self):
        self.sample['concurrent_resource_gate'].update(status='STOP_RESOURCE_GATE', reasons=['numeric_resource_failure'])
        actual_anchor = proof.postrestart_cpu_anchor
        with patch.object(proof, 'postrestart_cpu_anchor', side_effect=lambda container, group:
                actual_anchor(container, group, proc_root=self.proc)), \
             patch.object(proof, 'coherent_postrestart_cpu_proof') as coherent, \
             self.assertRaises(PlanError):
            self.host.quiescent(self.cid, 'readiness')
        coherent.assert_not_called()

    def test_allocation_persistent_gap_blocks_cache_and_new_inference(self):
        (self.proc / '45/stat').unlink()
        with self.allocation_io(), self.assertRaisesRegex(PlanError, '^postrestart_cpu_snapshot_unavailable$'):
            self.host.allocation(self.cid)
        self.assertNotIn(self.cid, self.host.allocation_proofs)
        with self.assertRaisesRegex(PlanError, '^concurrent_current_allocation_required$'):
            self.host.dispatch({'op': 'request_begin', 'id': self.cid, 'timeout_s': 7200})
        self.assertEqual(self.host.requests, {})
        self.host.budget.request_timeout.assert_not_called()

    def test_quiescent_refreshes_after_telemetry_and_reuses_coherent_numa(self):
        def sampled(cid):
            self.set_members(44, 46)
            (self.proc / '45/stat').unlink()
            return self.sample
        self.host.telemetry.side_effect = sampled
        actual_proof, actual_numa = proof.coherent_postrestart_cpu_proof, telemetry.numa_snapshot
        actual_anchor = proof.postrestart_cpu_anchor
        cohorts = []
        def snapshot(pids, **kwargs):
            cohorts.append(copy.deepcopy(pids))
            return actual_numa(pids, **kwargs)
        with patch.object(proof, 'postrestart_cpu_anchor', side_effect=lambda container, group:
                actual_anchor(container, group, proc_root=self.proc)), \
             patch.object(proof, 'coherent_postrestart_cpu_proof', side_effect=lambda host, cid, manifest, **kwargs:
                actual_proof(host, cid, manifest, proc_root=self.proc, sys_root=self.system, **kwargs)), \
             patch.object(telemetry, 'numa_snapshot', side_effect=snapshot):
            result = self.host.quiescent(self.cid, 'readiness')
        self.check_complete(result['actual_cpu_scope'], (44, 46), 1)
        coherent_numa = result['actual_cpu_scope']['numa_pages']
        self.assertEqual(result['numa_pages'], {**coherent_numa,
            'processes': {self.cid: coherent_numa['processes']['owned']}})
        self.assertEqual(cohorts, [{'owned': [44, 46]}])

    def test_rpc_receipt_preserves_fixed_code_class_frames_without_private_paths(self):
        (self.proc / '45/stat').unlink()
        source = io.StringIO(json.dumps({'op': 'allocation', 'id': self.cid}) + '\n')
        sink = io.StringIO()
        with self.allocation_io():
            host_module.serve(self.host, source, sink)
        self.assertFalse(json.loads(sink.getvalue())['ok'])
        receipts = [row for name, row in self.saved if name.startswith('rpc-errors/')]
        self.assertEqual(len(receipts), 1)
        receipt = receipts[0]
        self.assertEqual(receipt['operation'], 'allocation')
        self.assertEqual(receipt['exception_class'], 'PlanError')
        self.assertEqual(receipt['require_code'], 'postrestart_cpu_snapshot_unavailable')
        self.assertIn('coherent_postrestart_cpu_proof', [row['function'] for row in receipt['frames']])
        self.assertTrue(all(set(row) == {'source', 'function', 'line'} for row in receipt['frames']))
        self.assertNotIn(str(self.root), json.dumps(receipt))
        self.assertNotIn('/private/model', json.dumps(receipt))
        self.assertNotIn('synthetic-protected-logs', json.dumps(receipt))

    def test_historical_quiescent_scopes_do_not_use_real72_coherent_helper(self):
        for scope in (profiles.CPU_SCOPE, 'concurrent-g1q1'):
            with self.subTest(scope=scope):
                self.host.scope = scope
                with patch.object(proof, 'coherent_postrestart_cpu_proof') as coherent, \
                     patch.object(telemetry, 'numa_snapshot', return_value={'synthetic': True}) as numa:
                    result = self.host.quiescent(self.cid, 'readiness')
                coherent.assert_not_called()
                self.assertNotIn('actual_cpu_scope', result)
                self.assertEqual(numa.call_count, int(scope == profiles.CPU_SCOPE))


if __name__ == '__main__':
    unittest.main()
