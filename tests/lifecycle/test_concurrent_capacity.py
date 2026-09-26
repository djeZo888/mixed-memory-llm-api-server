"""Current admission/native capacity contracts; synthetic I/O, never live proof."""
import copy
import io
import json
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from tests.lifecycle.test_concurrent_profiles import ADA_UUID, bound, receipt, pair, LifecycleError, Manager
from lifecycle import runtime_io

GIB = 1024**3
GPU_QUERY = ['nvidia-smi', '--query-gpu=index,uuid,memory.total,memory.free', '--format=csv,noheader,nounits']


def target_gpu_query(uuid):
    return [GPU_QUERY[0], '--id=' + uuid, *GPU_QUERY[1:]]


def resident(slot):
    return {'Id': ('a' if slot == 'glm' else 'b') * 64, 'State': {'Running': True, 'Pid': 101 if slot == 'glm' else 102},
            'Config': {'Labels': {'io.llmctl.owner': 'mixed-memory-llm-api-server',
                'io.llmctl.instance': 'synthetic-instance', 'io.llmctl.deployment': pair.SLOTS[slot]}}}


class MemoryFixture:
    def __init__(self, *, available=800, free=(95, 95), residents=None, resident_stats=None):
        self.available, self.free, self.residents = available, free, residents or {}
        self.resident_stats = resident_stats or {}
        self.calls, self.overrides = [], {}

    def run(self, argv, *, timeout):
        if not 0 < timeout <= 5:
            raise AssertionError('unbounded current sample')
        self.calls.append(argv)
        if tuple(argv) in self.overrides:
            return self.overrides[tuple(argv)]
        if argv == ['/usr/bin/cat', '/sys/devices/system/cpu/online']:
            return '0-71\n'
        if argv == ['/usr/bin/cat', '/proc/meminfo']:
            return f'MemTotal: {900 * GIB // 1024} kB\nMemAvailable: {self.available * GIB // 1024} kB\n'
        if argv in [target_gpu_query(uuid) for uuid in pair.GPU_UUIDS]:
            return '\n'.join(f'{index}, {uuid}, {96 * 1024}, {self.free[index] * 1024}'
                             for index, uuid in enumerate(pair.GPU_UUIDS) if argv[1] == '--id=' + uuid)
        for slot, anon in self.residents.items():
            item = resident(slot); cid, pid = item['Id'], item['State']['Pid']
            root = '/sys/fs/cgroup/system.slice/docker-' + cid + '.scope'
            stats = {'anon': anon * GIB, 'file': 300 * GIB, 'shmem': 0, 'kernel': GIB,
                     **self.resident_stats.get(slot, {})}
            values = {f'/proc/{pid}/cgroup': '0::/system.slice/docker-' + cid + '.scope\n',
                      root + '/cgroup.procs': str(pid) + '\n', root + '/memory.swap.current': '0\n',
                      root + '/memory.stat': ''.join(f'{name} {value}\n' for name, value in stats.items())}
            if argv[0] == '/usr/bin/cat' and argv[1] in values:
                return values[argv[1]]
        raise AssertionError('unexpected command')


class CurrentMemory(unittest.TestCase):
    def setUp(self):
        self.d = bound(pair.GLM_PROFILE)
        self.proof, self.instance = receipt(self.d)

    def asymmetric_case(self, identifier, resident_slots):
        """Deliberately distinct synthetic totals/peaks; never hardware evidence."""
        for review in self.proof['modes'].values():
            review['slots']['glm'].update(gpu_total_bytes=96 * GIB, minimum_free_gpu_bytes=24 * GIB)
            review['slots']['qwen'].update(gpu_total_bytes=80 * GIB, minimum_free_gpu_bytes=20 * GIB)
        self.instance['concurrent_pair_acceptance']['sha256'] = pair.receipt_sha256(self.proof)
        d = bound(identifier, self.d['_storage_binding'])
        mode = 'dual-qwen' if identifier == pair.QWEN0_PROFILE else 'glm-qwen'
        residents = {slot: resident(slot) for slot in resident_slots}
        for slot, container in residents.items():
            container['Config']['Labels']['io.llmctl.deployment'] = pair.MODES[mode][slot]
        fixture = MemoryFixture(residents={slot: 1 for slot in residents})
        target = pair.slot_for_deployment(identifier)
        needed = {slot: (16 if slot in residents else (88 if slot == 'glm' else 76)) * GIB
                  for slot in (target,)}
        # Ada is intentionally first and abundant, with remapped physical indices.
        rows = [[0, ADA_UUID, 256 * 1024, 255 * 1024],
                [7, pair.GPU_UUIDS[1], 80 * 1024, needed.get('qwen', 80 * GIB) // 1024**2],
                [3, pair.GPU_UUIDS[0], 96 * 1024, needed.get('glm', 96 * GIB) // 1024**2]]
        return d, residents, fixture, rows, needed

    @staticmethod
    def set_gpu_rows(fixture, rows):
        for uuid in pair.GPU_UUIDS:
            fixture.overrides[tuple(target_gpu_query(uuid))] = '\n'.join(', '.join(map(str, row)) for row in rows)

    def test_reordered_asymmetric_memory_follows_each_uuid_for_new_and_resident_slots(self):
        for identifier in pair.PROFILES:
            for resident_slots in ((), ('glm',), ('qwen',), ('glm', 'qwen')):
                d, residents, fixture, rows, needed = self.asymmetric_case(identifier, resident_slots)
                for inventory in (rows, list(reversed(rows)), rows[1:], list(reversed(rows[1:]))):
                    with self.subTest(identifier=identifier, residents=resident_slots, rows=inventory):
                        self.set_gpu_rows(fixture, inventory)
                        result = pair.preflight_current(d, self.instance, fixture.run, residents=residents)
                        self.assertEqual(result['gpu_required_free_bytes'], needed)

    def test_abundant_ada_and_peer_cannot_cover_low_free_exact_blackwell(self):
        for identifier in pair.PROFILES:
            for resident_slots in ((), ('glm',), ('qwen',), ('glm', 'qwen')):
                d, residents, fixture, rows, needed = self.asymmetric_case(identifier, resident_slots)
                for slot, required in needed.items():
                    bad = copy.deepcopy(rows)
                    for row in bad:
                        row[3] = row[2]  # Every other GPU has all its memory free.
                        if row[1] == pair.GPU_UUIDS[0 if slot == 'glm' else 1]:
                            row[3] = required // 1024**2 - 1
                    self.set_gpu_rows(fixture, bad)
                    with self.subTest(identifier=identifier, residents=resident_slots, low=slot), \
                            self.assertRaisesRegex(LifecycleError, 'concurrent_current_gpu_memory_insufficient'):
                        pair.preflight_current(d, self.instance, fixture.run, residents=residents)

    def test_wrong_total_for_target_uuid_refuses_even_with_matching_ada_total(self):
        for identifier in pair.PROFILES:
            for resident_slots in ((), ('glm', 'qwen')):
                d, residents, fixture, rows, needed = self.asymmetric_case(identifier, resident_slots)
                for slot in needed:
                    bad = copy.deepcopy(rows)
                    for row in bad:
                        if row[1] == pair.GPU_UUIDS[0 if slot == 'glm' else 1]:
                            # Ada has the exact expected total; the required UUID does not.
                            bad[0][2:] = [row[2], row[2]]
                            row[2] += 1024
                            row[3] = row[2]
                    self.set_gpu_rows(fixture, bad)
                    with self.subTest(identifier=identifier, residents=resident_slots, wrong=slot), \
                            self.assertRaisesRegex(LifecycleError, 'concurrent_current_gpu_memory_unavailable'):
                        pair.preflight_current(d, self.instance, fixture.run, residents=residents)

    def test_current_memory_rejects_missing_duplicate_and_malformed_gpu_rows(self):
        d, residents, fixture, rows, _ = self.asymmetric_case(pair.GLM_PROFILE, ())
        identity_cases = [rows[:2], rows + [[9, *rows[2][1:]]],
                          rows + [[3, ADA_UUID, 49140, 49140]]]
        malformed = [[], [*rows, [9, ADA_UUID]],
                     [*rows[:2], [3, pair.GPU_UUIDS[0], 'N/A', 'N/A']],
                     [*rows[:2], [3, pair.GPU_UUIDS[0], 0, 0]],
                     [*rows[:2], [3, pair.GPU_UUIDS[0], 49140, 49141]],
                     [*rows[:2], [3, pair.GPU_UUIDS[0], 49140, -1]]]
        for cases, code in ((identity_cases, 'concurrent_gpu_inventory_mismatch'),
                            (malformed, 'concurrent_current_gpu_memory_unavailable')):
            for inventory in cases:
                self.set_gpu_rows(fixture, inventory)
                with self.subTest(rows=inventory), self.assertRaisesRegex(LifecycleError, code):
                    pair.preflight_current(d, self.instance, fixture.run, residents=residents)

    def test_missing_peer_and_unavailable_peer_memory_do_not_gate_target_admission(self):
        for identifier in pair.PROFILES:
            for resident_slots in ((), ('glm', 'qwen')):
                d, residents, fixture, rows, needed = self.asymmetric_case(identifier, resident_slots)
                target_uuid = d['launch']['gpus'][0]
                target_row = next(row for row in rows if row[1] == target_uuid)
                # A stopped/missing peer, an unassigned card, and a retained
                # running-container host allocation never donate target VRAM.
                inventories = [[target_row], [rows[0], target_row]]
                for telemetry in (['N/A', 'N/A'], [0, 0], [1, 2], [1, -1]):
                    inventories.append([row if row[1] == target_uuid else [*row[:2], *telemetry]
                                        for row in rows])
                for inventory in inventories:
                    self.set_gpu_rows(fixture, inventory)
                    with self.subTest(identifier=identifier, residents=resident_slots, rows=inventory):
                        result = pair.preflight_current(d, self.instance, fixture.run, residents=residents)
                        self.assertEqual(result['gpu_required_free_bytes'], needed)
                        self.assertEqual(result['resident_slots'], sorted(residents))
                        expected_host = 16 * GIB + sum(self.proof['modes'][
                            'dual-qwen' if identifier == pair.QWEN0_PROFILE else 'glm-qwen']['slots'][slot][
                                'memory_bytes'] - (GIB if slot in residents else 0)
                            for slot in set(residents) | {pair.slot_for_deployment(identifier)})
                        self.assertEqual(result['required_host_available_bytes'], expected_host)

    def test_missing_target_and_ambiguous_target_refuse_with_abundant_peer_memory(self):
        for identifier in pair.PROFILES:
            d, residents, fixture, rows, _ = self.asymmetric_case(identifier, ())
            target_uuid = d['launch']['gpus'][0]
            target_row = next(row for row in rows if row[1] == target_uuid)
            missing = [row for row in rows if row[1] != target_uuid]
            ambiguous = [*rows, [11, *target_row[1:]]]
            for inventory in (missing, ambiguous):
                self.set_gpu_rows(fixture, inventory)
                with self.subTest(identifier=identifier, rows=inventory), self.assertRaisesRegex(
                        LifecycleError, 'concurrent_gpu_inventory_mismatch'):
                    pair.preflight_current(d, self.instance, fixture.run)

    def test_exact_target_query_succeeds_when_global_inventory_would_fail(self):
        for identifier in pair.PROFILES:
            d = bound(identifier, self.d['_storage_binding'])
            fixture = MemoryFixture()
            commands = []

            def read(argv, *, timeout):
                commands.append(argv)
                if argv[0] == 'nvidia-smi' and argv[1] != '--id=' + d['launch']['gpus'][0]:
                    raise LifecycleError('synthetic_unassigned_gpu_query_hang')
                return fixture.run(argv, timeout=timeout)

            result = pair.preflight_current(d, self.instance, read)
            self.assertEqual(set(result['gpu_required_free_bytes']), {pair.slot_for_deployment(identifier)})
            self.assertEqual([argv for argv in commands if argv[0] == 'nvidia-smi'],
                             [target_gpu_query(d['launch']['gpus'][0])])

    def test_fresh_load_requires_full_host_cap_headroom_and_measured_gpu_allocation(self):
        fixture = MemoryFixture(available=656)
        result = pair.preflight_current(self.d, self.instance, fixture.run)
        self.assertEqual(result['required_host_available_bytes'], 656 * GIB)
        self.assertEqual(result['gpu_required_free_bytes'], {'glm': 92 * GIB})
        self.assertEqual(result['resident_slots'], [])
        for available, free, code in [(655, (95, 95), 'host'), (800, (91, 95), 'gpu')]:
            fixture = MemoryFixture(available=available, free=free)
            with self.assertRaisesRegex(LifecycleError, 'concurrent_current_' + code + '_memory_insufficient'):
                pair.preflight_current(self.d, self.instance, fixture.run)

    def test_resident_peer_is_credited_once_without_file_cache_credit(self):
        d = bound(pair.QWEN_PROFILE, self.d['_storage_binding'])
        fixture = MemoryFixture(available=300, free=(20, 95), residents={'glm': 400})
        result = pair.preflight_current(d, self.instance, fixture.run, residents={'glm': resident('glm')})
        # GLM cap640 minus anon400 + Qwen cap32 + shared headroom16.
        self.assertEqual(result['required_host_available_bytes'], 288 * GIB)
        self.assertEqual(result['gpu_required_free_bytes'], {'qwen': 92 * GIB})
        fixture.available = 287
        with self.assertRaisesRegex(LifecycleError, 'concurrent_current_host_memory_insufficient'):
            pair.preflight_current(d, self.instance, fixture.run, residents={'glm': resident('glm')})

    def test_first_run_shmem_shape_admits_qwen_with_full_remaining_caps_and_os_reserve(self):
        # Root-supplied first RUN shape, rounded as provided; synthetic replay,
        # not a fresh VM observation or accepted capacity receipt.
        d = bound(pair.QWEN_PROFILE, self.d['_storage_binding'])
        anon, shmem = 9 * GIB // 10, 3996 * GIB // 10
        fixture = MemoryFixture(available=463, free=(20, 95), residents={'glm': 0},
            resident_stats={'glm': {'anon': anon, 'file': 500 * GIB, 'shmem': shmem,
                                   'anon_thp': anon, 'shmem_thp': shmem}})
        result = pair.preflight_current(d, self.instance, fixture.run, residents={'glm': resident('glm')})
        # Old anon-only accounting required ~687.1 GiB. The disjoint credit
        # leaves ~287.5 GiB required: GLM remainder + full Qwen cap + OS reserve.
        required = (640 + 32 + 16) * GIB - anon - shmem
        self.assertGreater((640 + 32 + 16) * GIB - anon, 463 * GIB)
        self.assertEqual(result['required_host_available_bytes'], required)
        fixture.overrides[('/usr/bin/cat', '/proc/meminfo')] = (
            f'MemTotal: {900 * GIB // 1024} kB\nMemAvailable: {required // 1024} kB\n')
        with self.assertRaisesRegex(LifecycleError, 'concurrent_current_host_memory_insufficient'):
            pair.preflight_current(d, self.instance, fixture.run, residents={'glm': resident('glm')})

    def test_shmem_is_not_added_again_as_file_thp_or_other_overlapping_charge(self):
        d = bound(pair.QWEN_PROFILE, self.d['_storage_binding'])
        fixture = MemoryFixture(available=288, free=(20, 95), residents={'glm': 1},
            resident_stats={'glm': {'shmem': 399 * GIB, 'file': 600 * GIB,
                'anon_thp': GIB, 'shmem_thp': 399 * GIB, 'file_mapped': 600 * GIB,
                'kernel': 30 * GIB}})
        result = pair.preflight_current(d, self.instance, fixture.run, residents={'glm': resident('glm')})
        self.assertEqual(result['required_host_available_bytes'], 288 * GIB)
        fixture.available = 287
        with self.assertRaisesRegex(LifecycleError, 'concurrent_current_host_memory_insufficient'):
            pair.preflight_current(d, self.instance, fixture.run, residents={'glm': resident('glm')})

    def test_both_resident_slots_keep_their_remaining_cap_and_os_reserve(self):
        d = bound(pair.QWEN_PROFILE, self.d['_storage_binding'])
        fixture = MemoryFixture(available=278, free=(20, 20), residents={'glm': 1, 'qwen': 2},
            resident_stats={'glm': {'shmem': 399 * GIB, 'file': 500 * GIB},
                            'qwen': {'shmem': 8 * GIB}})
        residents = {slot: resident(slot) for slot in ('glm', 'qwen')}
        result = pair.preflight_current(d, self.instance, fixture.run, residents=residents)
        self.assertEqual(result['required_host_available_bytes'], (640 - 400 + 32 - 10 + 16) * GIB)
        fixture.available = 277
        with self.assertRaisesRegex(LifecycleError, 'concurrent_current_host_memory_insufficient'):
            pair.preflight_current(d, self.instance, fixture.run, residents=residents)

    def test_running_target_reuse_needs_reserve_not_a_second_gpu_allocation(self):
        fixture = MemoryFixture(available=300, free=(20, 95), residents={'glm': 400})
        result = pair.preflight_current(self.d, self.instance, fixture.run, residents={'glm': resident('glm')})
        self.assertEqual(result['required_host_available_bytes'], 256 * GIB)
        self.assertEqual(result['gpu_required_free_bytes']['glm'], 16 * GIB)
        fixture.free = (15, 95)
        with self.assertRaisesRegex(LifecycleError, 'concurrent_current_gpu_memory_insufficient'):
            pair.preflight_current(self.d, self.instance, fixture.run, residents={'glm': resident('glm')})

    def test_saved_intent_unknown_identity_or_cgroup_cannot_receive_credit(self):
        fixture = MemoryFixture(residents={'glm': 400})
        for change in (lambda c: c['State'].update(Running=False), lambda c: c['State'].update(Pid=True),
                       lambda c: c['Config']['Labels'].update({'io.llmctl.deployment': 'other'})):
            bad = resident('glm'); change(bad)
            with self.assertRaisesRegex(LifecycleError, 'concurrent_resident_identity_invalid'):
                pair.preflight_current(self.d, self.instance, fixture.run, residents={'glm': bad})
        fixture.overrides[('/usr/bin/cat', '/proc/101/cgroup')] = '0::/unrelated\n'
        with self.assertRaisesRegex(LifecycleError, 'concurrent_resident_cgroup_unavailable'):
            pair.preflight_current(self.d, self.instance, fixture.run, residents={'glm': resident('glm')})

    def test_swap_missing_or_inconsistent_counters_and_malformed_observations_refuse(self):
        root = '/sys/fs/cgroup/system.slice/docker-' + 'a' * 64 + '.scope'
        cases = [(['/usr/bin/cat', root + '/memory.swap.current'], '1', 'concurrent_resident_swap_detected'),
                 (['/usr/bin/cat', root + '/memory.stat'], 'file 100\n', 'concurrent_resident_memory_unavailable'),
                 (['/usr/bin/cat', root + '/memory.stat'], 'anon 1\nfile 100\n', 'concurrent_resident_memory_unavailable'),
                 (['/usr/bin/cat', root + '/memory.stat'], 'anon 1\nshmem 100\n', 'concurrent_resident_memory_unavailable'),
                 (['/usr/bin/cat', root + '/memory.stat'], 'anon 1\nfile 100\nshmem 101\n', 'concurrent_resident_memory_unavailable'),
                 (['/usr/bin/cat', root + '/memory.stat'], 'anon 1\nfile 100\nshmem -1\n', 'concurrent_resident_memory_unavailable'),
                 (['/usr/bin/cat', '/proc/meminfo'], 'MemAvailable: 100 bytes\n', 'concurrent_current_host_memory_unavailable'),
                 (target_gpu_query(pair.GPU_UUIDS[0]), '0, unknown, 90000, 80000\n1, unknown, 90000, 80000', 'concurrent_gpu_inventory_mismatch'),
                 (target_gpu_query(pair.GPU_UUIDS[0]), '0, ' + pair.GPU_UUIDS[0] + ', N/A, N/A\n', 'concurrent_current_gpu_memory_unavailable')]
        for argv, output, code in cases:
            fixture = MemoryFixture(residents={'glm': 400}); fixture.overrides[tuple(argv)] = output
            with self.subTest(code=code), self.assertRaisesRegex(LifecycleError, code):
                pair.preflight_current(self.d, self.instance, fixture.run, residents={'glm': resident('glm')})

    def test_missing_reviewed_receipt_fails_before_current_process_reads(self):
        fixture = MemoryFixture()
        with self.assertRaisesRegex(LifecycleError, 'concurrent_reviewed_acceptance_required'):
            pair.preflight_current(self.d, {}, fixture.run)
        self.assertEqual(fixture.calls, [])


class NativeCapacity(unittest.TestCase):
    def test_glm_resolved_slot_context_is_required_not_model_training_context(self):
        d = bound(pair.GLM_PROFILE)
        props = {'model_alias': 'glm-5.3', 'is_sleeping': False, 'total_slots': 1,
                 'default_generation_settings': {'n_ctx': 480000}}
        with patch.object(runtime_io, 'native_capacity_metadata', return_value=props) as read:
            self.assertEqual(pair.native_capacity(d)['native_pool_tokens'], 480000)
            read.assert_called_once_with('http://127.0.0.1:30002/v1', d['auth']['key_file'], timeout=3, backend='glm')
        for change in (lambda p: p.update(is_sleeping=True), lambda p: p.update(total_slots=True),
                       lambda p: p['default_generation_settings'].update(n_ctx=32768),
                       lambda p: p.update(default_generation_settings={}, n_ctx_train=480000)):
            bad = copy.deepcopy(props); change(bad)
            with patch.object(runtime_io, 'native_capacity_metadata', return_value=bad), \
                    self.assertRaisesRegex(LifecycleError, 'concurrent_native_capacity_mismatch'):
                pair.native_capacity(d)

    def test_real_manager_ready_probe_requires_current_native_capacity(self):
        metadata = {
            pair.GLM_PROFILE: {'model_alias': 'glm-5.3', 'is_sleeping': False, 'total_slots': 1,
                              'default_generation_settings': {'n_ctx': 480000}},
            pair.QWEN_PROFILE: {'context_length': 480000, 'tp_size': 1,
                               'max_total_num_tokens': 480000, 'max_req_input_len': 479994}}
        for identifier, info in metadata.items():
            d = bound(identifier); binding = d['_storage_binding']
            normal_probe = Mock(return_value='ready')
            manager = Manager(pair.ROOT / 'configs', {'schema_version': 1, 'id': 'synthetic-instance',
                'storage_identity': binding.identity,
                'paths': {'state': {'role': 'data', 'suffix': 'services/llm-manager/active'}}},
                binding=binding, test_paths=True, probe_fn=normal_probe)
            with patch.object(runtime_io, 'native_capacity_metadata', return_value=info) as native:
                self.assertEqual(manager.probe_deployment(d, 5), 'ready')
                self.assertEqual(native.call_count, 1)
                self.assertTrue(0 < native.call_args.kwargs['timeout'] <= 5)
            wrong = copy.deepcopy(info)
            if identifier == pair.GLM_PROFILE:
                wrong['default_generation_settings']['n_ctx'] = 32768
            else:
                wrong['max_total_num_tokens'] = 262144
            with patch.object(runtime_io, 'native_capacity_metadata', return_value=wrong), \
                    self.assertRaisesRegex(LifecycleError, 'concurrent_native_capacity_mismatch'):
                manager.probe_deployment(d, 5)
            normal_probe.return_value = 'not_ready'
            with patch.object(runtime_io, 'native_capacity_metadata') as native:
                self.assertEqual(manager.probe_deployment(d, 5), 'not_ready')
                native.assert_not_called()

    def test_qwen_actual_pool_and_native_request_limit_top_or_internal(self):
        d = bound(pair.QWEN_PROFILE)
        actual = {'max_total_num_tokens': 480000, 'max_req_len': 479999, 'max_req_input_len': 479994}
        for info in ({'context_length': 480000, 'tp_size': 1, **actual},
                     {'server_args': {'context_length': 480000, 'tp_size': 1}, 'internal_states': [actual]}):
            with patch.object(runtime_io, 'native_capacity_metadata', return_value=info):
                result = pair.native_capacity(d)
                self.assertEqual((result['native_pool_tokens'], result['native_input_limit']), (480000, 479994))

    def test_qwen_argv_capacity_never_substitutes_for_allocated_pool(self):
        d = bound(pair.QWEN_PROFILE)
        args = {'context_length': 480000, 'tp_size': 1, 'max_total_tokens': 480000,
                'max_total_num_tokens': 480000, 'max_req_input_len': 479994}
        cases = [{'server_args': args},
            {'server_args': args, 'max_total_num_tokens': 262144, 'max_req_input_len': 262138},
            {'server_args': args, 'max_total_num_tokens': True, 'max_req_input_len': 479994},
            {'server_args': args, 'max_total_num_tokens': 480000, 'max_req_input_len': 700000},
            {'server_args': args, 'max_total_num_tokens': 480000, 'max_req_input_len': 479994,
             'internal_states': [{'max_total_num_tokens': 262144}]},
            {'server_args': args, 'internal_states': [{}, {}]}]
        for info in cases:
            with patch.object(runtime_io, 'native_capacity_metadata', return_value=info), self.assertRaises(LifecycleError):
                pair.native_capacity(d)


class NativeMetadataTransport(unittest.TestCase):
    def exchange(self, payload=b'{"native":1}', status=200):
        response = SimpleNamespace(status=status, read1=io.BytesIO(payload).read1)
        connection = Mock()
        connection.getresponse.return_value = response
        return connection

    def test_fixed_local_authenticated_get_and_cleanup(self):
        for endpoint, port, path in [('http://127.0.0.1:30002/v1', 30002, '/props'),
                                    ('http://127.0.0.1:30004/v1', 30004, '/get_server_info')]:
            connection = self.exchange()
            with patch.object(runtime_io, '_read_key', return_value='synthetic-secret'), \
                    patch.object(runtime_io.http.client, 'HTTPConnection', return_value=connection) as factory, \
                    patch.object(runtime_io.threading, 'Timer') as timer:
                self.assertEqual(runtime_io.native_capacity_metadata(endpoint, '/synthetic/key'), {'native': 1})
                factory.assert_called_once_with('127.0.0.1', port, timeout=3)
                self.assertEqual(connection.request.call_args.args, ('GET', path))
                self.assertEqual(connection.request.call_args.kwargs['headers']['Authorization'], 'Bearer synthetic-secret')
                connection.close.assert_called_once(); timer.return_value.cancel.assert_called_once()

    def test_redirect_auth_missing_or_malformed_metadata_is_safe_failure(self):
        cases = [(b'{}', 302), (b'{}', 401), (b'not-json synthetic-secret', 200),
                 (b'{"n":1,"n":2}', 200), (b'{"n":NaN}', 200), (b'[]', 200), (b'x' * 1048577, 200)]
        for payload, status in cases:
            connection = self.exchange(payload, status)
            with patch.object(runtime_io, '_read_key', return_value='synthetic-secret'), \
                    patch.object(runtime_io.http.client, 'HTTPConnection', return_value=connection), \
                    patch.object(runtime_io.threading, 'Timer'), self.assertRaises(LifecycleError) as error:
                runtime_io.native_capacity_metadata('http://127.0.0.1:30004/v1', '/synthetic/key')
            self.assertNotIn('synthetic-secret', str(error.exception))
            connection.close.assert_called_once()
        with patch.object(runtime_io.http.client, 'HTTPConnection') as connect:
            with self.assertRaises(LifecycleError):
                runtime_io.native_capacity_metadata('http://10.0.0.1:30004/v1', '/synthetic/key')
            connect.assert_not_called()


if __name__ == '__main__':
    unittest.main()
