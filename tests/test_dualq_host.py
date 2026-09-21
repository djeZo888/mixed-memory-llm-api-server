"""Offline tests of the actual closed two-Qwen host admission and cleanup seam."""
import copy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock, patch

from benchmark import cpu_budget_host as proofs, dualq_480k as dualq
from benchmark.host import LinuxHost, concurrent_capacity_policy
from benchmark.lifecycle import digest
from benchmark.postrestart72_budget import PostrestartBudget

GIB = 1024**3
NATIVE = {'context_length': 480000, 'tp_size': 1, 'max_total_num_tokens': 480000,
          'max_req_input_len': 479994, 'max_req_len': 479999}
# Actual extracted numeric fields, replayed offline from the corrected RUN's
# corrected-saved-diagnostics.json, native-numeric-diagnostic receipt SHA256
# c063b9618a9fb8920d1725f5944ced3465bb3e3f3019eaf6c52bf0fc9f9a6246.
# max_req_len was absent; no raw server_args, keys or synthetic target values.
EXTRACTED_NATIVE = {'context_length': 480000, 'tp_size': 1,
                    'max_total_num_tokens': 480000, 'max_req_input_len': 479994,
                    'internal_states': [{'context_length': 480000, 'tp_size': 1}]}


class DualQHostTests(unittest.TestCase):
    def setUp(self):
        self.h = h = LinuxHost.__new__(LinuxHost)
        h.scope, h.campaign, h.mode = dualq.SCOPE, dualq.CAMPAIGN, None
        h.config = {'gpu_uuids': [dualq.manifest(slot)['gpu_uuids'][0] for slot in dualq.SLOTS]}
        h.load_manifests = {slot: dualq.manifest(slot) for slot in dualq.SLOTS}
        h.allocation_proofs = {slot: {} for slot in dualq.SLOTS}
        h.manifests = {digest(m): m for m in h.load_manifests.values()}
        h.requests, h.concurrent_resource_violations = {}, {}
        h.dualq_state = {'binding': None, 'counts': {}, 'warmups': {}, 'admitted': [], 'ended': []}
        h.owner = SimpleNamespace(phase='ACTIVE', lease=Mock(), resources=[], launch=Mock())
        h.identity = Mock(return_value=({}, None, [])); h.concurrent_limits = Mock()
        h.telemetry = Mock(return_value={'concurrent_resource_gate': {'status': 'PASS'}})
        h.cuda_mapping = lambda cid, manifest, container: manifest['gpu_uuids']
        h.auth_probe = Mock(); h.batch_owned_idle = Mock(return_value=True)
        h.guards, h.assert_idle = Mock(), Mock()
        h.campaign_containers = Mock(return_value=[])
        self.saved = {}
        h.write_json = lambda name, value: self.saved.update({name: copy.deepcopy(value)})
        h.read_json = lambda name, **kwargs: None
        h.log_root = '/synthetic-offline-only'; self.now = [100.0]
        h.budget = PostrestartBudget(h, clock=lambda: self.now[0]); h.budget.start('maintenance')
        h.concurrent_round, h.concurrent_admitted = None, set()
        for name, value in [('benchmark.host.http_json', NATIVE),
                            ('benchmark.cpu_budget_host.resident_obligations', {})]:
            p = patch(name, return_value=value); p.start(); self.addCleanup(p.stop)

    def identity(self, slot, purpose, kind='measured'):
        suffix = '-count-' + kind if purpose == 'count' else '-warmup' if purpose == 'warmup' else '-near480K'
        return {'request_id': slot + suffix, 'purpose': purpose,
                'request_sha256': digest(slot + ('warmup' if purpose == 'warmup' else kind)),
                'manifest_sha256': digest(self.h.load_manifests[slot])}

    def begin(self, slot, purpose, kind='measured'):
        return self.h.dispatch({'op': 'request_begin', 'id': slot,
            'request_identity': self.identity(slot, purpose, kind), 'measured': purpose == 'measured',
            'timeout_s': 120 if purpose == 'count' else 7200})

    def end(self, slot, purpose, kind='measured', terminal=None):
        return self.h.dispatch({'op': 'request_end', 'id': slot,
            'request_identity': self.identity(slot, purpose, kind),
            'terminal_reason': terminal or ('COUNT_DRAINED' if purpose == 'count' else 'DRAINED')})

    def seal(self):
        for slot in dualq.SLOTS:
            self.begin(slot, 'count', 'warmup'); self.end(slot, 'count', 'warmup')
            self.begin(slot, 'warmup'); self.end(slot, 'warmup')
            self.begin(slot, 'count'); self.end(slot, 'count')
        binding = {slot: {k: v for k, v in self.identity(slot, 'measured').items() if k != 'purpose'}
                   for slot in dualq.SLOTS}
        return self.h.dispatch({'op': 'seal_dualq', 'binding': binding})

    def test_two_actual_family_profiles_exact_count_warm_and_pair_only(self):
        self.assertTrue(self.seal()['sealed'])
        self.assertIsNone(self.h.budget.data['started_at'])
        for slot in reversed(dualq.SLOTS):
            self.assertEqual(self.begin(slot, 'measured')['timeout_s'], 7200)
        self.assertEqual(set(self.h.requests), {'Q0', 'Q1'})
        for slot in dualq.SLOTS:
            self.assertTrue(self.end(slot, 'measured')['drained'])
            with self.assertRaises(ValueError): self.begin(slot, 'measured')
            with self.assertRaises(ValueError): self.begin(slot, 'warmup')
            with self.assertRaises(ValueError): self.begin(slot, 'count')
        self.assertEqual(set(self.h.dualq_state['admitted']), {'Q0', 'Q1'})
        self.assertEqual(len(self.h.dualq_state['counts']), 4)
        self.assertEqual(self.h.auth_probe.call_count, 8)
        self.assertFalse(self.h.requests)

    def test_body_and_manifest_binding_fail_closed(self):
        self.seal()
        for field in ('request_sha256', 'manifest_sha256', 'request_id', 'purpose'):
            value = self.identity('Q0', 'measured'); value[field] = 'x'
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.h.dispatch({'op': 'request_begin', 'id': 'Q0', 'measured': True,
                                 'timeout_s': 7200, 'request_identity': value})
        self.assertFalse(self.h.requests)
        self.assertNotIn('G1', concurrent_capacity_policy(dualq.SCOPE)['caps_bytes'])
        self.assertNotIn('G1_native_floor', concurrent_capacity_policy(dualq.SCOPE))

    def test_full_request_deadline_not_clipped_by_campaign(self):
        self.seal(); self.begin('Q0', 'measured')
        self.now[0] += 21600 - 1
        self.assertEqual(self.begin('Q1', 'measured')['timeout_s'], 7200)
        self.now[0] += 7201
        for slot in dualq.SLOTS: self.end(slot, 'measured')
        self.assertFalse(self.h.requests)

    def test_extracted_native_shape_allows_absent_optional_request_limit(self):
        proof = proofs.qwen_native_proof(EXTRACTED_NATIVE, scope=dualq.SCOPE)
        self.assertEqual((proof['configured_context'], proof['native_pool_tokens'],
                          proof['native_input_limit'], proof['native_request_limit']),
                         (480000, 480000, 479994, None))
        with patch('benchmark.host.http_json', return_value=EXTRACTED_NATIVE):
            for slot in dualq.SLOTS:
                self.begin(slot, 'count', 'warmup')
                self.assertEqual(self.saved['admission-' + slot + '-count-warmup-count.json']['native_capacity'], proof)
                self.end(slot, 'count', 'warmup')

    def test_current_native_numeric_fields_required_for_both_Q_roles(self):
        for slot in dualq.SLOTS:
            for key in ('context_length', 'tp_size', 'max_total_num_tokens', 'max_req_input_len'):
                bad = dict(NATIVE); del bad[key]
                with patch('benchmark.host.http_json', return_value=bad), self.subTest(slot=slot, missing=key), self.assertRaises(ValueError):
                    self.begin(slot, 'count', 'warmup')
        self.assertFalse(self.h.requests)
        self.assertFalse(self.h.dualq_state['counts'])

    def test_present_native_fields_remain_strict_and_conflicts_fail(self):
        # Malformed variants are synthetic; only EXTRACTED_NATIVE is observed.
        for key, expected in NATIVE.items():
            for value in (expected + 1, expected - 1, float(expected), str(expected), True, None, 0):
                bad = copy.deepcopy(EXTRACTED_NATIVE); bad[key] = value
                with self.subTest(field=key, value=value), self.assertRaises(ValueError):
                    proofs.qwen_native_proof(bad, scope=dualq.SCOPE)
        for location in ('top', 'state'):
            good = copy.deepcopy(EXTRACTED_NATIVE)
            row = good if location == 'top' else good['internal_states'][0]
            row['max_req_len'] = 479999
            self.assertEqual(proofs.qwen_native_proof(good, scope=dualq.SCOPE)['native_request_limit'], 479999)
            for value in (None, True, '479999', 479999.0, 0, 479998, 480000):
                row['max_req_len'] = value
                with self.subTest(location=location, value=value), self.assertRaises(ValueError):
                    proofs.qwen_native_proof(good, scope=dualq.SCOPE)
        for key, value in NATIVE.items():
            bad = copy.deepcopy(EXTRACTED_NATIVE); bad[key] = value
            bad['internal_states'][0][key] = value + 1
            with self.subTest(conflict=key), self.assertRaises(ValueError):
                proofs.qwen_native_proof(bad, scope=dualq.SCOPE)

    def test_original_stopped_manual_and_no_running_adoption(self):
        good = {'manager': {'desired': 'stopped', 'observed': 'stopped', 'container_running': False, 'boot_policy': 'manual'}}
        with patch('benchmark.host.collect_sample', return_value={'host': {'available_bytes': 80 * GIB}}):
            self.assertIn('STOPPED', proofs.pre_retirement_admission(self.h, good)['production'])
            for key, value in [('desired', 'running'), ('container_running', True), ('boot_policy', 'resume')]:
                bad = copy.deepcopy(good); bad['manager'][key] = value
                with self.assertRaises(ValueError): proofs.pre_retirement_admission(self.h, bad)

    def test_one_closed_QQ_admission_and_no_legacy_GQ(self):
        sample = {'host': {'available_bytes': 80 * GIB},
                  'gpus': [{'uuid': uuid, 'free_bytes': 90 * GIB} for uuid in self.h.config['gpu_uuids']]}
        with patch('benchmark.host.collect_sample', return_value=sample):
            with self.assertRaises(ValueError): self.h.admit_concurrent('P')
            result = self.h.admit_concurrent('QQ')
            self.assertEqual([m['placement'] for m in result['manifests']], ['Q0', 'Q1'])
            with self.assertRaises(ValueError): self.h.admit_concurrent('QQ')

    def resource_sample(self):
        group = {'current_bytes': 14 * GIB, 'peak_since_cgroup_creation_bytes': 14 * GIB,
                 'anon_bytes': 12 * GIB, 'kernel_bytes': GIB, 'file_bytes': GIB,
                 'file_mapped_bytes': GIB, 'shmem_bytes': 0, 'swap_bytes': 0,
                 'events': dict.fromkeys(('oom', 'oom_kill', 'oom_group_kill'), 0)}
        return {'host': {'available_bytes': 100 * GIB}, 'cgroups': {slot: copy.deepcopy(group) for slot in dualq.SLOTS},
                'processes': {slot: {'rss_bytes': 13 * GIB, 'swap_bytes': 0, 'known_process_count': 2} for slot in dualq.SLOTS},
                'gpus': [{'uuid': uuid, 'total_bytes': 96 * GIB, 'free_bytes': 30 * GIB} for uuid in self.h.config['gpu_uuids']],
                'vmstat': dict.fromkeys(('pgfault', 'pgmajfault', 'pswpin', 'pswpout', 'oom_kill'), 0), 'errors': []}

    def test_missing_resources_do_not_cancel_but_numeric_fault_latches(self):
        good = self.resource_sample()
        self.assertEqual(self.h.concurrent_pressure(good)['status'], 'PASS')
        missing = copy.deepcopy(good); missing['cgroups']['Q0']['file_mapped_bytes'] = None
        self.assertEqual(self.h.concurrent_pressure(missing)['status'], 'UNAVAILABLE')
        self.assertEqual(self.h.concurrent_resource_violations, {})
        bad = copy.deepcopy(missing); bad['processes']['Q0']['rss_bytes'] = 28 * GIB
        proof = self.h.concurrent_pressure(bad)
        self.assertEqual(proof['status'], 'STOP_RESOURCE_GATE')
        self.assertIn('concurrent_cap_15_percent_headroom_failed', proof['reasons'])
        self.assertEqual(self.h.concurrent_pressure(good)['status'], 'STOP_RESOURCE_GATE')

    def test_both_Qwen_GPU_ten_percent_reserves(self):
        for index in range(2):
            h = self.h; h.concurrent_resource_violations = {}
            sample = self.resource_sample(); sample['gpus'][index].update(free_bytes=16 * GIB, total_bytes=200 * GIB)
            self.assertIn('cpu_qwen_ten_percent_failed', h.concurrent_pressure(sample)['reasons'])

    def test_two_Q_cap_resident_obligations_no_GLM_floor(self):
        row = self.resource_sample(); proof = proofs.dualq_memory_obligations(row, self.h.load_manifests)
        self.assertEqual(proof['required_host_available_bytes'], 56 * GIB)
        self.assertEqual(set(proof['resident_nonreclaimable_bytes']), {'Q0', 'Q1'})
        row['host']['available_bytes'] = None
        with self.assertRaisesRegex(ValueError, 'unavailable'): proofs.dualq_memory_obligations(row, self.h.load_manifests)

    def test_timeout_and_cancel_keep_registry_until_canonical_stop_after_peer(self):
        for terminal in ('REQUEST_DEADLINE', 'CANCELLED'):
            self.setUp(); self.seal()
            for slot in dualq.SLOTS: self.begin(slot, 'measured')
            result = self.end('Q0', 'measured', terminal=terminal)
            self.assertEqual(result['status'], 'CANONICAL_STOP_REQUIRED')
            self.assertIn('Q0', self.h.requests)
            with patch('benchmark.host.command', return_value=SimpleNamespace(stdout=b'')):
                with self.assertRaisesRegex(ValueError, 'healthy_request'): LinuxHost.assert_idle(self.h)
                self.end('Q1', 'measured')
                LinuxHost.assert_idle(self.h)
                with tempfile.TemporaryDirectory() as directory:
                    self.h.identity = Mock(return_value=({}, Path(directory) / 'gone', []))
                    self.h._exact = Mock(return_value={'State': {'Running': False}})
                    LinuxHost.stop(self.h, {'id': 'Q0'})
            self.assertFalse(self.h.requests)
            self.assertTrue(self.saved['loads/Q0-failed-request-stop.json']['owned_processes_gone'])
            self.assertEqual(self.saved['loads/Q0-failed-request-stop.json']['native_request_completion'], 'UNKNOWN')

    def test_failed_exact_container_stop_cannot_clear_registration(self):
        self.begin('Q0', 'count', 'warmup')
        self.end('Q0', 'count', 'warmup', terminal='COUNT_FAILED')
        with tempfile.TemporaryDirectory() as directory:
            self.h.identity = Mock(return_value=({}, Path(directory) / 'gone', []))
            self.h._exact = Mock(return_value={'State': {'Running': True}})
            with patch('benchmark.host.command', return_value=SimpleNamespace(stdout=b'')), \
                    self.assertRaisesRegex(ValueError, 'still_running'):
                LinuxHost.stop(self.h, {'id': 'Q0'})
        self.assertIn('Q0', self.h.requests)

    def test_failed_count_no_retry_and_closed_scope_no_hold(self):
        self.begin('Q0', 'count', 'warmup'); self.end('Q0', 'count', 'warmup', terminal='COUNT_FAILED')
        with self.assertRaises(ValueError): self.begin('Q0', 'count', 'warmup')
        for operation in ('warm_hold', 'resume_measurements', 'admit_followup', 'decode_progress'):
            with self.assertRaises(ValueError): self.h.dispatch({'op': operation})

    def test_missing_current_resource_returns_pending_without_registration(self):
        self.h.telemetry.return_value = {'concurrent_resource_gate': {'status': 'UNAVAILABLE'}}
        self.assertTrue(self.begin('Q0', 'count', 'warmup')['proof_pending'])
        self.assertFalse(self.h.requests)
        self.assertFalse(self.h.dualq_state['counts'])
        self.assertFalse(self.h.concurrent_resource_violations)

    def test_protected_auth_receipts_bind_both_actual_slots_and_base(self):
        self.h.binding = Mock()
        qwen = SimpleNamespace(IMAGE_ID='image', IMAGE_REFERENCE='reference', SOURCE_REVISION='revision',
                               launcher_hash=lambda: 'launcher', _validate_auth_proof=Mock())
        fixture = SimpleNamespace(check_pair_receipt=Mock())
        raw = {role: json.dumps({'container_lifetimes': [{'container_id': role}]}).encode()
               for role in ('base', 'Q0', 'Q1')}
        refs = {role: {'registered_path': '/data/logs/llmctl/dualq-auth-20260921/' + role + '.json',
                       'sha256': hashlib.sha256(value).hexdigest()} for role, value in raw.items()}
        def read(path, **kwargs):
            self.assertTrue(kwargs['private'])
            return raw[Path(path).stem], {}
        with patch('benchmark.host.protected', side_effect=read), \
                patch('benchmark.host.candidate_modules', return_value=(None, qwen)), \
                patch('benchmark.concurrent_validate.auth_fixture_module', return_value=fixture):
            self.h.dualq_auth_receipts(refs)
            self.assertEqual([call.kwargs['slot'] for call in fixture.check_pair_receipt.call_args_list], ['gpu0', 'gpu1'])
            qwen._validate_auth_proof.assert_called_once()
            bad = copy.deepcopy(refs); bad['Q0']['sha256'] = '0' * 64
            with self.assertRaisesRegex(ValueError, 'hash_changed'): self.h.dualq_auth_receipts(bad)
            bad = copy.deepcopy(refs); bad['Q0']['registered_path'] = '/tmp/auth.json'
            with self.assertRaisesRegex(ValueError, 'reference_changed'): self.h.dualq_auth_receipts(bad)
            with self.assertRaisesRegex(ValueError, 'receipts_required'): self.h.dualq_auth_receipts({'Q1': refs['Q1']})

    def test_actual_host_constructor_keeps_installed_owner_and_dual_arm(self):
        from benchmark import host as module, profiles
        root = profiles.ROOT
        relative = 'scripts/benchmark/host.py'; source = (root / relative).read_bytes()
        arm = {'scope': dualq.SCOPE, 'campaign': dualq.CAMPAIGN,
               'manifests': [dualq.manifest(slot) for slot in dualq.SLOTS],
               'trial_plan': dualq.trial_plan(), 'runtime_policy': dualq.POLICY, 'runtime': dualq.POLICY,
               'concurrent_capacity_policy': concurrent_capacity_policy(dualq.SCOPE),
               'source_files': {relative: hashlib.sha256(source).hexdigest()},
               'source_commit': 'a' * 40, 'session_id': 'offline-run',
               'base_commit': 'f130ec46ebd9a27319d84e0d372746e0489a9972',
               'production_acceptance': 'NOT_GRANTED',
               'actual_image_auth_status': 'PENDING_ACTUAL_IMAGE_TESTS'}
        binding = Mock(); binding.path.side_effect = lambda role, suffix='': '/data/' + role + '/' + suffix
        manager = SimpleNamespace(binding=binding)
        manifest_path = '/data/services/synthetic/manifests.json'
        def protected(path, **kwargs):
            if str(path) == manifest_path: return json.dumps(arm).encode(), {}
            if Path(path) == root / relative: return source, {}
            raise AssertionError('unexpected protected read')
        with patch.object(module, 'INSTALL', root), patch.object(module.os, 'geteuid', return_value=0), \
                patch.object(LinuxHost, 'pin_sources'), patch.object(LinuxHost, 'read_json', return_value=None), \
                patch.object(LinuxHost, 'dualq_auth_receipts') as auth, \
                patch.object(module, 'protected', side_effect=protected), \
                patch('lifecycle.manager.load_manager', return_value=manager), \
                patch.object(module, 'command', side_effect=AssertionError('no host command')) as command:
            host = LinuxHost(dualq.CAMPAIGN, manifest_path)
        self.assertEqual(host.scope, dualq.SCOPE)
        self.assertEqual(len(host.manifests), 2)
        self.assertIsInstance(host.budget, PostrestartBudget)
        self.assertEqual(host.owner.scope, dualq.SCOPE)
        self.assertEqual(host.owner.phase, 'NEW')
        self.assertIsNone(host.owner.lease)
        auth.assert_called_once(); command.assert_not_called()

    def test_actual_shared_Q8_cgroup_memory_limits(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, value in {'memory.max': str(32 * GIB), 'memory.swap.max': '0',
                                'cpuset.cpus.effective': '0-7', 'cpuset.mems.effective': '0-7',
                                'cpu.max': 'max 100000'}.items(): (root / name).write_text(value)
            container = {'HostConfig': {'Memory': 32 * GIB, 'MemorySwap': 32 * GIB, 'CpusetCpus': '0-7',
                         'NanoCpus': 0, 'CpuQuota': 0, 'CpuPeriod': 0, 'CpusetMems': ''}}
            for slot in dualq.SLOTS:
                memory, cpus = LinuxHost.concurrent_limits(dualq.manifest(slot), container, root)
                self.assertEqual(memory['docker_memory_bytes'], 32 * GIB)
                self.assertEqual(cpus['cgroup_cpuset_cpus_effective'], '0-7')
            (root / 'cpuset.cpus.effective').write_text('8-15')
            with self.assertRaises(ValueError): LinuxHost.concurrent_limits(dualq.manifest('Q0'), container, root)


if __name__ == '__main__': unittest.main()
