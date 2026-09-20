"""Candidate admission/native proof seams; all current-host/native I/O mocked."""
import copy
import importlib
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from tests.lifecycle.test_qwen38 import BindingFixture, container as qcontainer
from tests.lifecycle.test_sglang38_file_auth import args_fixture
from benchmark import concurrent_validate as candidate, profiles
from benchmark.host import LinuxHost

GIB = 1024**3
GLM, QWEN = 'a' * 64, 'b' * 64


class CandidateHost(unittest.TestCase):
    def setUp(self):
        self.cp, self.qwen = profiles.candidate_modules()
        self.runtime_io = importlib.import_module(self.cp.__package__ + '.runtime_io')
        self.manifests = dict(zip((GLM, QWEN), profiles.candidate_manifests()))

    def group(self, anon, shmem, file):
        return {'anon_bytes': anon * GIB, 'shmem_bytes': shmem * GIB,
                'file_bytes': file * GIB, 'swap_bytes': 0}

    def sample(self, available=688 * GIB, groups=None):
        return {'host': {'available_bytes': available}, 'cgroups': groups or {},
                'gpus': [{'uuid': uuid, 'total_bytes': 96 * GIB, 'free_bytes': 16 * GIB}
                         for uuid in self.cp.GPU_UUIDS]}

    def host(self, placements=('G1', 'Q1')):
        manifests = {cid: m for cid, m in self.manifests.items() if m['placement'] in placements}
        host = SimpleNamespace(scope=candidate.SCOPE, concurrent_resource_violations={},
            owner=SimpleNamespace(resources=[{'state': 'RUNNING', 'resource': {'id': cid}} for cid in manifests]),
            binding=BindingFixture(data='/data', models='/data/models-large'), load_manifests=manifests,
            budget=Mock(), identity=Mock())
        host.budget.checkpoint.return_value = 30
        host.identity.side_effect = lambda cid: ({'Id': cid}, Path('/synthetic/' + cid), [123])
        return host

    def inventory(self):
        return SimpleNamespace(stdout=('0, ' + self.cp.GPU_UUIDS[0] + '\n1, ' + self.cp.GPU_UUIDS[1] + '\n').encode())

    def test_preload_reserves_both_fixed_caps_and_os_reserve(self):
        result = candidate.memory_obligations(self.sample(), {})
        self.assertEqual(result['required_host_available_bytes'], 688 * GIB)
        self.assertEqual(result['resident_nonreclaimable_bytes'], {})
        with self.assertRaisesRegex(ValueError, 'candidate_remaining_caps_host_reserve_failed'):
            candidate.memory_obligations(self.sample(688 * GIB - 1), {})

    def test_resident_anon_shmem_credit_once_retains_peer_remaining_obligation(self):
        groups = {GLM: self.group(400, 20, 200)}
        result = candidate.memory_obligations(self.sample(268 * GIB, groups), self.manifests)
        self.assertEqual(result['required_host_available_bytes'], 268 * GIB)
        self.assertEqual(result['resident_nonreclaimable_bytes'], {'G1': 420 * GIB})
        groups[GLM].update(file_bytes=500 * GIB, current_bytes=900 * GIB,
                           peak_since_cgroup_creation_bytes=1000 * GIB)
        self.assertEqual(candidate.memory_obligations(self.sample(268 * GIB, groups), self.manifests), result)
        groups[QWEN] = self.group(12, 1, 8)
        result = candidate.memory_obligations(self.sample(255 * GIB, groups), self.manifests)
        self.assertEqual(result['required_host_available_bytes'], 255 * GIB)
        self.assertEqual(result['resident_nonreclaimable_bytes'], {'G1': 420 * GIB, 'Q1': 13 * GIB})
        with self.assertRaisesRegex(ValueError, 'candidate_remaining_caps_host_reserve_failed'):
            candidate.memory_obligations(self.sample(255 * GIB - 1, groups), self.manifests)

    def test_missing_swapped_inconsistent_duplicate_or_over_cap_credit_fails_closed(self):
        for key, value in [('anon_bytes', None), ('shmem_bytes', True), ('file_bytes', -1),
                           ('shmem_bytes', 201 * GIB), ('swap_bytes', 1)]:
            group = self.group(400, 20, 200); group[key] = value
            with self.subTest(key=key, value=value), self.assertRaisesRegex(
                    ValueError, 'candidate_resident_credit_unavailable'):
                candidate.memory_obligations(self.sample(groups={GLM: group}), self.manifests)
        with self.assertRaisesRegex(ValueError, 'candidate_resident_credit_exceeds_cap'):
            candidate.memory_obligations(self.sample(groups={GLM: self.group(640, 1, 1)}), self.manifests)
        groups = {GLM: self.group(1, 1, 1), QWEN: self.group(1, 1, 1)}
        with self.assertRaisesRegex(ValueError, 'candidate_duplicate_resident'):
            candidate.memory_obligations(self.sample(groups=groups), {GLM: self.manifests[GLM], QWEN: self.manifests[GLM]})

    def test_admission_fresh_inventory_and_both_identity_rechecks(self):
        host = self.host()
        sample = self.sample(groups={GLM: self.group(400, 20, 200), QWEN: self.group(12, 1, 8)})
        with patch('benchmark.host.command', return_value=self.inventory()) as command, \
                patch.object(candidate, 'identity_stamp', side_effect=lambda h, cid: {'id': cid, 'pid': 123}) as stamp:
            result = candidate.admission(host, sample=sample)
        self.assertEqual(stamp.call_count, 4)
        self.assertEqual(result['identities'], {cid: {'id': cid, 'pid': 123} for cid in self.manifests})
        command.assert_called_once_with(['nvidia-smi', '--query-gpu=index,uuid', '--format=csv,noheader,nounits'], 5)
        self.assertEqual(result['required_host_available_bytes'], 255 * GIB)

    def test_admission_rejects_identity_change_and_stale_or_missing_resident_sample(self):
        host = self.host(('G1',))
        sample = self.sample(groups={GLM: self.group(400, 20, 200)})
        with patch('benchmark.host.command', return_value=self.inventory()), \
                patch.object(candidate, 'identity_stamp', side_effect=[{'id': GLM, 'pid': 123}, {'id': GLM, 'pid': 124}]), \
                self.assertRaisesRegex(ValueError, 'candidate_sampling_identity_changed'):
            candidate.admission(host, sample=sample)
        for groups in ({}, {QWEN: self.group(12, 1, 8)}):
            with patch('benchmark.host.command', return_value=self.inventory()), \
                    patch.object(candidate, 'identity_stamp', return_value={'id': GLM}), \
                    self.assertRaisesRegex(ValueError, 'candidate_resident_inventory_mismatch'):
                candidate.admission(host, sample=self.sample(groups=groups))

    def test_admission_rejects_actual_uuid_free_reserve_and_qwen_ten_percent_failures(self):
        host = self.host(())
        cases = [('uuid', 'unknown'), ('free_bytes', 16 * GIB - 1), ('total_bytes', 200 * GIB)]
        for key, value in cases:
            sample = self.sample(); sample['gpus'][1][key] = value
            with self.subTest(key=key), patch('benchmark.host.command', return_value=self.inventory()), \
                    self.assertRaises(ValueError):
                candidate.admission(host, sample=sample)
        wrong = self.inventory(); wrong.stdout = wrong.stdout.replace(b'0,', b'1,', 1)
        with patch('benchmark.host.command', return_value=wrong), self.assertRaises(self.cp.LifecycleError):
            candidate.admission(host, sample=self.sample())

    def test_native_glm_uses_resolved_capacity_not_manifest_and_binds_current_identity(self):
        host = self.host(('G1',))
        info = {'default_generation_settings': {'n_ctx': 480000}, 'total_slots': 1,
                'is_sleeping': False, 'model_alias': 'glm-5.3'}
        with patch.object(self.runtime_io, 'native_capacity_metadata', return_value=info) as native, \
                patch.object(candidate, 'identity_stamp', return_value={'id': GLM, 'pid': 123}) as stamp, \
                patch.object(self.cp, 'check_acceptance', side_effect=AssertionError('candidate is not accepted')):
            result = candidate.native_proof(host, GLM)
        self.assertEqual(result['native_pool_tokens'], 480000)
        self.assertEqual(result['identity'], {'id': GLM, 'pid': 123})
        self.assertEqual(stamp.call_count, 2)
        native.assert_called_once_with('http://127.0.0.1:30002/v1', '/data/services/secrets/llm-api-key', timeout=5)
        info['default_generation_settings']['n_ctx'] = 65536
        with patch.object(self.runtime_io, 'native_capacity_metadata', return_value=info), \
                patch.object(candidate, 'identity_stamp', return_value={'id': GLM}), \
                self.assertRaisesRegex(self.cp.LifecycleError, 'concurrent_native_capacity_mismatch'):
            candidate.native_proof(host, GLM)

    def qwen_info(self):
        args = args_fixture(1000000, resolved=True)
        args.context_length = args.max_total_tokens = 700160
        args.tp_size = 1
        fields = json.loads(json.dumps(vars(args), default=vars))
        return {'server_args': fields, 'max_total_num_tokens': 700160,
                'max_req_len': 700159, 'max_req_input_len': 700154}

    def test_native_qwen_requires_actual_pool_and_input_limit_not_argv_only(self):
        host, info = self.host(('Q1',)), self.qwen_info()
        with patch.object(self.runtime_io, 'native_capacity_metadata', return_value=info), \
                patch.object(candidate, 'identity_stamp', return_value={'id': QWEN, 'pid': 123}):
            result = candidate.native_proof(host, QWEN, info)
        self.assertEqual(result['native_pool_tokens'], 700160)
        self.assertEqual(result['native_input_limit'], 700154)
        self.assertEqual(result['native_arguments_basis'], 'actual_native_resolving_view_validated_by_exact_pair_wrapper')
        self.assertEqual(len(result['resolved_fields_sha256']), 64)
        for bad in ({'server_args': info['server_args']}, {**info, 'max_total_num_tokens': 699904},
                    {**info, 'max_req_input_len': 700155}):
            with patch.object(self.runtime_io, 'native_capacity_metadata', return_value=bad), \
                    patch.object(candidate, 'identity_stamp', return_value={'id': QWEN}), \
                    self.assertRaises(self.cp.LifecycleError):
                candidate.native_proof(host, QWEN, bad)

    def test_native_qwen_actual_resolved_defaults_or_identity_drift_is_not_proof(self):
        host, info = self.host(('Q1',)), self.qwen_info()
        with patch.object(self.runtime_io, 'native_capacity_metadata', return_value=info), \
                patch.object(candidate, 'identity_stamp', side_effect=[{'id': QWEN, 'pid': 1}, {'id': QWEN, 'pid': 2}]), \
                self.assertRaisesRegex(ValueError, 'candidate_native_identity_changed'):
            candidate.native_proof(host, QWEN, info)
        bad = copy.deepcopy(info); bad['server_args']['mem_fraction_static'] = 0.81
        with patch.object(self.runtime_io, 'native_capacity_metadata', return_value=bad), \
                patch.object(candidate, 'identity_stamp', return_value={'id': QWEN}), self.assertRaises(Exception):
            candidate.native_proof(host, QWEN, bad)


class CandidateContainer(unittest.TestCase):
    """Exact production contract with only enumerated campaign path changes."""
    def fixture(self, placement):
        host = LinuxHost.__new__(LinuxHost)
        host.binding = BindingFixture(data='/data', models='/data/models-large')
        manifest = profiles.candidate_manifest(placement, host.binding)
        d = profiles.candidate_profile(placement, host.binding)
        q = profiles.candidate_profile('Q1', host.binding)
        container = qcontainer(q)
        resources = d['concurrent_pair']
        container['Image'] = manifest['expected_image_ids'][0]
        container['Config'].update(Image=manifest['image'], Entrypoint=d['_runtime']['entrypoint'],
            Cmd=manifest['native_argv'] if placement == 'G1' else ['/opt/llmctl/sglang38_pair_file_auth.py'])
        inherited = {'PATH': '/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin'}
        if placement == 'G1':
            env = {**inherited, **d['_runtime']['environment'], **d['launch_environment']}
            container['Config'].update(Env=[k + '=' + v for k, v in env.items()], WorkingDir='/', User='')
        container['HostConfig'].update(CpusetCpus=resources['guest_cpuset'], Memory=resources['memory_bytes'],
            MemorySwap=resources['memory_swap_bytes'], NanoCpus=0, CpuQuota=0, CpuPeriod=0,
            DeviceRequests=[{'Driver': 'nvidia', 'Count': 0, 'DeviceIDs': d['launch']['gpus'], 'Capabilities': [['gpu']]}])
        port = str(d['endpoint']['port'])
        container['HostConfig']['PortBindings'] = {port + '/tcp': [{'HostIp': '127.0.0.1', 'HostPort': port}]}
        container['Mounts'] = [{'Type': 'bind', 'Source': m['source'], 'Destination': m['target'],
                               'RW': not m['read_only'], 'Propagation': 'rprivate'} for m in manifest['mounts']]
        if placement == 'G1':
            container['HostConfig'].update(ReadonlyRootfs=False, Tmpfs={}, ShmSize=64 * 1024**2, Ulimits=None)
        image = {'Id': manifest['image'], 'Config': {'Entrypoint': d['_runtime']['entrypoint'],
                                                  'Env': [k + '=' + v for k, v in inherited.items()]}}
        return host, manifest, container, SimpleNamespace(stdout=json.dumps([image]).encode())

    def test_exact_production_launch_accepts_both_candidates_and_actual_image_defaults(self):
        for placement in ('G1', 'Q1'):
            host, manifest, container, image = self.fixture(placement)
            with patch('benchmark.host.command', return_value=image) as command:
                host.candidate_container(manifest, container)
                host.candidate_container(manifest, container)
            self.assertEqual(command.call_count, 1 if placement == 'G1' else 0)

    def test_launch_image_entrypoint_and_native_arguments_drift_rejected(self):
        for change in (lambda c: c.update(Image='sha256:' + '0' * 64),
                       lambda c: c['Config'].update(Image='unreviewed:latest'),
                       lambda c: c['Config'].update(Entrypoint=['sh']),
                       lambda c: c['Config']['Cmd'].append('--unreviewed')):
            host, manifest, container, image = self.fixture('Q1'); change(container)
            with self.assertRaisesRegex(ValueError, 'candidate_container_launch_changed'):
                host.candidate_container(manifest, container)

    def test_mount_duplicates_type_permissions_sources_and_extra_bind_rejected(self):
        changes = [lambda c: c['Mounts'].append(copy.deepcopy(c['Mounts'][0])),
            lambda c: c['Mounts'][0].update(Type='volume'),
            lambda c: c['Mounts'][0].update(RW=True),
            lambda c: c['Mounts'][0].update(RW=0),
            lambda c: c['Mounts'][0].update(Source='/unreviewed/model'),
            lambda c: c['Mounts'][0].update(Propagation='shared'),
            lambda c: c['Mounts'].append({'Type': 'bind', 'Source': '/unreviewed', 'Destination': '/tmp', 'RW': True})]
        for change in changes:
            host, manifest, container, _ = self.fixture('Q1'); change(container)
            with self.assertRaisesRegex(ValueError, 'candidate_container_mounts_changed'):
                host.candidate_container(manifest, container)

    def test_qwen_only_declared_tmpfs_is_accepted_with_exact_bind_inventory(self):
        host, manifest, container, _ = self.fixture('Q1')
        tmp = {'Type': 'tmpfs', 'Source': '', 'Destination': '/tmp', 'RW': True, 'Propagation': ''}
        container['Mounts'].append(tmp)
        host.candidate_container(manifest, container)
        for change in (lambda c: c['Mounts'][-1].update(Destination='/models'),
                       lambda c: c['Mounts'][-1].update(Source='/unreviewed'),
                       lambda c: c['Mounts'].append(copy.deepcopy(tmp))):
            bad = copy.deepcopy(container); change(bad)
            with self.assertRaisesRegex(ValueError, 'candidate_container_mounts_changed'):
                host.candidate_container(manifest, bad)

    def test_exact_environment_blocks_overrides_extras_and_duplicates(self):
        for placement in ('G1', 'Q1'):
            for change in (lambda c: c['Config']['Env'].append('LD_PRELOAD=/unreviewed.so'),
                           lambda c: c['Config']['Env'].append(c['Config']['Env'][0]),
                           lambda c: c['Config'].update(Env=[e for e in c['Config']['Env'] if not e.startswith('XDG_CACHE_HOME=')])):
                host, manifest, container, image = self.fixture(placement); change(container)
                with patch('benchmark.host.command', return_value=image), self.assertRaises(Exception):
                    host.candidate_container(manifest, container)

    def test_network_gpu_caps_no_swap_and_cpu_partition_drift_rejected(self):
        changes = [lambda c: c['HostConfig']['PortBindings']['30004/tcp'][0].update(HostIp='0.0.0.0'),
            lambda c: c['HostConfig'].update(NetworkMode='host'),
            lambda c: c['HostConfig'].update(MemorySwap=-1),
            lambda c: c['HostConfig'].update(CpusetCpus='0-111'),
            lambda c: c['HostConfig'].update(CpuQuota=1000),
            lambda c: c['HostConfig']['DeviceRequests'][0].update(DeviceIDs=['1']),
            lambda c: c['HostConfig']['RestartPolicy'].update(Name='always')]
        for change in changes:
            host, manifest, container, _ = self.fixture('Q1'); change(container)
            with self.assertRaises(Exception):
                host.candidate_container(manifest, container)

    def test_security_logging_and_namespace_policy_drift_rejected(self):
        changes = [lambda c: c['HostConfig'].update(CapDrop=[]),
            lambda c: c['HostConfig'].update(CapAdd=['SYS_ADMIN']),
            lambda c: c['HostConfig'].update(SecurityOpt=[]),
            lambda c: c['HostConfig'].update(LogConfig={'Type': 'none'}),
            lambda c: c['HostConfig'].update(VolumesFrom=['unrelated']),
            lambda c: c['HostConfig'].update(Binds=['/host:/container']),
            lambda c: c['HostConfig'].update(IpcMode='container:unrelated')]
        for change in changes:
            host, manifest, container, _ = self.fixture('Q1'); change(container)
            with self.assertRaisesRegex(ValueError, 'candidate_security_policy_changed'):
                host.candidate_container(manifest, container)

    def test_qwen_process_readonly_shm_tmpfs_and_core_policy_drift_rejected(self):
        changes = [lambda c: c['Config'].update(User='123'),
            lambda c: c['Config'].update(WorkingDir='/tmp'),
            lambda c: c['Config'].update(Healthcheck={'Test': ['CMD', 'true']}),
            lambda c: c['HostConfig'].update(ReadonlyRootfs=False),
            lambda c: c['HostConfig'].update(ShmSize=16 * GIB),
            lambda c: c['HostConfig'].update(Tmpfs={}),
            lambda c: c['HostConfig'].update(Ulimits=[]),
            lambda c: c['HostConfig']['Ulimits'][0].update(Soft=True)]
        for change in changes:
            host, manifest, container, _ = self.fixture('Q1'); change(container)
            with self.assertRaisesRegex(ValueError, 'candidate_qwen_'):
                host.candidate_container(manifest, container)

    def test_glm_inherited_environment_requires_exact_immutable_image_and_entrypoint(self):
        for field, value in (('Id', 'sha256:' + 'f' * 64), ('entrypoint', ['sh'])):
            host, manifest, container, image = self.fixture('G1')
            item = json.loads(image.stdout)[0]
            if field == 'Id': item[field] = value
            else: item['Config']['Entrypoint'] = value
            image.stdout = json.dumps([item]).encode()
            with patch('benchmark.host.command', return_value=image), self.assertRaisesRegex(
                    ValueError, 'candidate_image_environment_unavailable'):
                host.candidate_container(manifest, container)


if __name__ == '__main__':
    unittest.main()


class CandidateDemandIntegration(unittest.TestCase):
    def sample(self):
        from tests.test_concurrent_host import ConcurrentHostTests
        host, row = ConcurrentHostTests().pressure_sample()
        host.scope = candidate.SCOPE
        host.load_manifests = dict(zip(('a', 'b'), profiles.candidate_manifests()))
        for group in row['cgroups'].values():
            group.update(swap_bytes=0, events={'oom': 0, 'oom_kill': 0, 'oom_group_kill': 0})
        for gpu in row['gpus']:
            gpu['total_bytes'] = 96 * GIB
        return host, row

    def test_same_approved_estimate_raw_peak_separate_and_resident_obligations(self):
        host, row = self.sample()
        result = host.candidate_pressure(row)
        self.assertEqual(result['status'], 'PASS')
        g = result['charges']['a']
        self.assertEqual(g['evidence_status'], 'ESTIMATE')
        self.assertEqual(g['required_bytes'], max(222023680 + 2100539392 + 428890877952,
            429220401152 + 2100539392, g['native_floor_bytes']))
        self.assertEqual(g['lifetime_peak_bytes'], 549898883072)
        self.assertIsNone(g['reclaimable_file_bytes'])
        self.assertTrue(g['cap_headroom_25_percent'])
        self.assertGreater(result['remaining_cap_obligations']['required_host_available_bytes'], 16 * GIB)

    def test_missing_estimate_inputs_stay_unavailable_and_numeric_excess_latches(self):
        host, row = self.sample()
        row['processes']['a']['rss_bytes'] = None
        self.assertEqual(host.candidate_pressure(row)['status'], 'UNAVAILABLE')
        row['cgroups']['a']['anon_bytes'] = 200 * GIB
        result = host.candidate_pressure(row)
        self.assertEqual(result['status'], 'STOP_RESOURCE_GATE')
        row['cgroups']['a']['anon_bytes'] = 222023680
        self.assertEqual(host.candidate_pressure(row)['status'], 'STOP_RESOURCE_GATE')

    def test_qwen_margin_swap_oom_and_current_cap_failure_remain_stops(self):
        for variant in ('gpu', 'swap', 'oom', 'cap'):
            host, row = self.sample()
            if variant == 'gpu': row['gpus'][1].update(total_bytes=200 * GIB, free_bytes=16 * GIB)
            if variant == 'swap': row['cgroups']['b']['swap_bytes'] = 1
            if variant == 'oom': row['cgroups']['b']['events']['oom'] = 1
            if variant == 'cap': row['cgroups']['b']['current_bytes'] = 32 * GIB + 1
            self.assertEqual(host.candidate_pressure(row)['status'], 'STOP_RESOURCE_GATE')


class CandidateEvidence(unittest.TestCase):
    def bare(self):
        from benchmark.host import LinuxHost
        host = LinuxHost.__new__(LinuxHost)
        host.scope, host.requests = candidate.SCOPE, {}
        host.load_manifests = dict(zip(('a', 'b'), profiles.candidate_manifests()))
        host.manifests = {str(i): m for i, m in enumerate(host.load_manifests.values())}
        host.candidate_auth = {'evidence': 'synthetic_offline'}
        host.measured = {'G1': {'evidence_status': 'ESTIMATE', 'required_bytes': 401 * GIB},
                         'Q1': {'evidence_status': 'UNAVAILABLE', 'required_bytes': None}}
        host.log_root = '/data/logs/synthetic'
        host.write_json, host.read_json = Mock(), Mock(return_value={'evidence': 'synthetic_offline'})
        host.samples = {cid: [{'gpus': [{'uuid': m['gpu_uuids'][0], 'free_bytes': 20 * GIB}]}]
                        for cid, m in host.load_manifests.items()}
        checks = {}
        for placement in ('G1', 'Q1'):
            for kind in ('smoke', 'tool'):
                row = {'status': 'PASS', 'placement': placement,
                       'sample': {'counters': {'prompt_tokens': 300, 'completion_tokens': 32}}}
                if kind == 'tool':
                    row['continuation'] = {'counters': {'prompt_tokens': 400, 'completion_tokens': 48}}
                checks[placement + '-' + kind] = row
        return host, checks

    def test_configured_occupied_and_estimated_raw_evidence_remain_distinct(self):
        host, checks = self.bare()
        result = host.dispatch({'op': 'candidate_evidence', 'checks': checks})
        self.assertEqual(result['production_acceptance'], 'NOT_GRANTED')
        receipt = host.write_json.call_args.args[1]
        self.assertEqual(receipt['slots']['G1']['configured_context'], 480000)
        self.assertEqual(receipt['slots']['Q1']['configured_context'], 700160)
        self.assertEqual(receipt['slots']['G1']['largest_occupied_context_in_checks'], 448)
        self.assertEqual(receipt['slots']['G1']['host_demand']['evidence_status'], 'ESTIMATE')
        self.assertEqual(receipt['slots']['Q1']['host_demand']['evidence_status'], 'UNAVAILABLE')
        self.assertEqual(len(receipt['slots']['G1']['samples_sha256']), 64)
        self.assertTrue(receipt['slots']['G1']['sampled_not_absolute'])

    def test_incomplete_or_missing_native_counts_cannot_emit_candidate_pass(self):
        host, checks = self.bare();del checks['Q1-tool']
        with self.assertRaises(ValueError): host.dispatch({'op': 'candidate_evidence', 'checks': checks})
        host.write_json.assert_not_called()
        host, checks = self.bare();checks['G1-smoke']['sample']['counters'] = {}
        with self.assertRaises(ValueError): host.dispatch({'op': 'candidate_evidence', 'checks': checks})
        host.write_json.assert_not_called()

    def test_candidate_scope_excludes_profiler_and_arbitrary_benchmark_rounds(self):
        host, _ = self.bare()
        for op in ('admit_mixed', 'admit_concurrent', 'diagnostic_snapshot', 'decode_cpu_capture_start'):
            with self.assertRaisesRegex(ValueError, 'candidate_operation_outside_scope'):
                host.dispatch({'op': op})
