"""Closed actual72 source/profile/proof tests. No live host or model requests."""
import ast
import copy
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from benchmark import cpu_budget_host as proof, cpu_budget_profiles as profile
from benchmark import cpu_budget_telemetry as telemetry, fixtures, profiles, qwen_launcher, runner
from tests.test_cpu_budget_profiles import flag
from tests import test_cpu_budget_telemetry as cpu_fixture


class PostrestartProfilesCPU(unittest.TestCase):
    def test_closed_shared_pair_pins_allmemory_and_stage_campaign(self):
        g, q = profile.postrestart_manifests()
        self.assertEqual([m['layout'] for m in (g, q)], ['P', 'P'])
        self.assertEqual([m['guest_cpuset'] for m in (g, q)], ['0-71', '0-7'])
        self.assertEqual([m['guest_cpu_count'] for m in (g, q)], [72, 8])
        for value in (g, q):
            old = profile.manifest('A', value['placement'])
            self.assertEqual(value['configured_capacity'], 480000)
            self.assertEqual(value['guest_total_vcpus'], 72)
            self.assertEqual(value['active_guest_vcpus'], 72)
            self.assertEqual(value['guest_mems_allowed'], '0-7')
            for field in ('gpu_uuids', 'image', 'model', 'ram_cap_bytes', 'resource_policy'):
                self.assertEqual(value[field], old[field])
            self.assertEqual(flag(value['create_argv'], '--memory-swap'), flag(value['create_argv'], '--memory'))
            self.assertNotIn('--cpuset-mems', value['create_argv'])
            self.assertNotIn('96-111', json.dumps(value))
        for key in ('--threads', '--threads-batch'):
            self.assertEqual(flag(g['native_argv'], key), '72')
        self.assertEqual(profiles.cpu_set(g['guest_cpuset']) | profiles.cpu_set(q['guest_cpuset']), set(range(72)))
        self.assertEqual(profiles.cpu_set(g['guest_cpuset']) & profiles.cpu_set(q['guest_cpuset']), set(range(8)))
        self.assertEqual(q['native_argv'], profile.manifest('A', 'Q1')['native_argv'])
        self.assertEqual(flag(q['create_argv'], '--scope'), profile.POSTRESTART_SCOPE)
        contract = [node for node in ast.walk(ast.parse(runner.STAGE)) if isinstance(node, ast.Assert)
                    and any(isinstance(part, ast.Name) and part.id == 'campaign' for part in ast.walk(node))]
        self.assertEqual(len(contract), 1)
        exec(compile(ast.Module(body=contract, type_ignores=[]), 'actual-STAGE', 'exec'),
             {'campaign': profile.POSTRESTART_CAMPAIGN})

    def test_exact_closed_plan_and_no_timing_or_mask_mutation(self):
        plan = profile.postrestart_trial_order()
        self.assertEqual([v['id'] for v in plan['trials']], ['P-G4K', 'P-G65008', 'P-Qnear480K'])
        self.assertEqual([v['saved_input_tokens'] for v in plan['trials']], [3546, 65008, 479487])
        self.assertEqual((plan['measurement_budget_seconds'], plan['maximum_request_seconds']), (21600, 7200))
        self.assertEqual(plan['budget_start'], 'first_measurement_admission')
        self.assertFalse(plan['clock_includes_preparation'])
        self.assertFalse(plan['warmup']['performance_gate'])
        self.assertEqual(plan['preliminary_gate']['decode_minimum_output_tokens'], 64)
        self.assertNotIn('common_input', plan)
        arm = {'scope': profile.POSTRESTART_SCOPE, 'campaign': profile.POSTRESTART_CAMPAIGN,
               'manifests': profile.postrestart_manifests(), 'trial_plan': plan}
        self.assertEqual(profile.validate_postrestart_arm_scope(arm), profile.POSTRESTART_SCOPE)
        for mutate in (lambda a: a['manifests'][1].update(guest_cpuset='72-79'),
                       lambda a: a['trial_plan'].update(maximum_request_seconds=3600),
                       lambda a: a['trial_plan']['trials'].append({'id': 'P-Q256K'})):
            bad = copy.deepcopy(arm); mutate(bad)
            with self.assertRaises(ValueError): profile.validate_postrestart_arm_scope(bad)

    def test_frozen_tuple_only_and_launcher_closed_480000_tp1(self):
        scope = profile.POSTRESTART_SCOPE
        base = qwen_launcher.pinned_base(profiles.ROOT / 'scripts/runtime/sglang38_file_auth.py')
        self.assertEqual(qwen_launcher.variant(base, 480000, 1, scope=scope),
                         profile.postrestart_manifest('Q1')['native_argv'])
        from tests.test_benchmark_qwen_adapter import fixture
        argv = qwen_launcher.bind_variant(base, 480000, 1, scope=scope)
        options, native = base.parse_options(argv)
        self.assertEqual(options.context_length, '480000')
        self.assertEqual(native, profile.postrestart_manifest('Q1')['native_argv'])
        args = fixture.args_fixture(base.EXTENSION_CONTEXT)
        args.context_length = args.max_total_tokens = 480000
        args.tp_size, args.port, args.served_model_name = 1, 31004, 'bench-qwen3.8-27b'
        base.validate_server_args(args)
        base.validate_server_args(fixture.resolved_args_fixture(args), resolved=True)
        for field, value in (('max_total_tokens', 479744), ('tp_size', 2), ('mem_fraction_static', .81)):
            bad = copy.deepcopy(args); setattr(bad, field, value)
            with self.assertRaises(base.LaunchError): base.validate_server_args(bad)
        for context, tp in ((700160, 1), (480000, 2), (262144, 1)):
            with self.assertRaises(ValueError): qwen_launcher.variant(base, context, tp, scope=scope)
        for model, target in (('bench-glm-5.3', 4096), ('bench-glm-5.3', 65536),
                              ('bench-qwen3.8-27b', 480000)):
            self.assertEqual(fixtures._fit_target(model, 480000, scope, target, 'retrieval', 256, False), target)
        for model, target in (('bench-glm-5.3', 480000), ('bench-qwen3.8-27b', 262144)):
            with self.assertRaises(fixtures.HarnessError):
                fixtures._fit_target(model, 480000, scope, target, 'retrieval', 256, False)
        counter = Mock(side_effect=AssertionError('no native fitting'))
        with self.assertRaisesRegex(fixtures.HarnessError, 'refit is forbidden'):
            fixtures.fit_sample('bench-qwen3.8-27b', 480000, 'fixture-seed', 'fresh-nonce', counter, scope=scope)
        counter.assert_not_called()
        frozen = fixtures.build_sample('bench-qwen3.8-27b', 80, 'frozen-q-fixture', 'old-prefix')
        def counted(raw):
            return {'source': 'synthetic_offline', 'body_sha256': fixtures.digest(raw),
                    'configured_context': 480000, 'input_tokens': 479487,
                    'template_sha256': 'a'*64, 'token_ids_sha256': 'b'*64}
        matched, count = fixtures.matched_sample(frozen, 'new-prefix', counted, 480000,
                    scope=scope, target_capacity=480000, synthetic=True)
        self.assertEqual(matched['fixture_sha256'], frozen['fixture_sha256'])
        self.assertEqual(count['input_tokens'], 479487)

    def test_native_resolving_view_conflicts_and_strict_scheduler_numbers(self):
        flat = {'context_length': 480000, 'tp_size': 1,
                'max_total_num_tokens': 480000, 'max_req_input_len': 479994, 'max_req_len': 479999}
        nested = {'server_args': {'context_length': 480000, 'tp_size': 1},
                  'internal_states': [{k: v for k, v in flat.items() if k not in ('context_length', 'tp_size')}]}
        for info in (flat, nested, {**flat, **nested}):
            self.assertEqual(proof.qwen_native_view(info)['context_length'], 480000)
            self.assertEqual(proof.qwen_native_proof(info, scope=profile.POSTRESTART_SCOPE)['native_input_limit'], 479994)
        for bad in ({**flat, 'server_args': {'context_length': 700160, 'tp_size': 1}},
                    {**flat, 'internal_states': [{'context_length': 480000.0}]},
                    {**flat, 'max_req_input_len': 479993}, {'server_args': flat}):
            with self.assertRaises(ValueError): proof.qwen_native_proof(bad, scope=profile.POSTRESTART_SCOPE)

    def test_actual72_counter_scope_and_old112_preserved(self):
        rows, summary = cpu_fixture.CpuBudgetTelemetryTests().full_measurement()
        self.assertEqual(telemetry.summarize_measurement(rows, summary)['counter_evidence']['status'], 'COMPLETE')
        for row in rows:
            for cpu in range(72, 112): del row['guest_cpus']['cpu' + str(cpu)]
        current = telemetry.summarize_measurement(rows, summary, scope=profile.POSTRESTART_SCOPE)
        self.assertEqual(current['counter_evidence']['status'], 'COMPLETE')
        self.assertEqual(current['counter_evidence']['required_guest_vcpus'], 72)
        self.assertEqual(telemetry.summarize_measurement(rows, summary)['counter_evidence']['status'], 'INCOMPLETE')
        gate = telemetry.warmup_gate(rows, 'glm', scope=profile.POSTRESTART_SCOPE)
        self.assertEqual(gate['status'], 'PASS')
        self.assertTrue(gate['intervals'][0]['all_72_guest_vcpu_deltas_available'])
        rows[-1]['guest_cpus']['cpu72'] = copy.deepcopy(rows[-1]['guest_cpus']['cpu71'])
        bad = telemetry.summarize_measurement(rows, summary, scope=profile.POSTRESTART_SCOPE)
        self.assertEqual(bad['counter_evidence']['status'], 'INCOMPLETE')

    def test_captured_stopped_manual_only_and_existing_fresh_ram_floor(self):
        host = SimpleNamespace(scope=profile.POSTRESTART_SCOPE)
        original = {'manager': {'selected': 'qwen38-27b-1000000-yarn4-tp2-bf16kv',
            'desired': 'stopped', 'observed': 'stopped', 'container_running': False, 'boot_policy': 'manual'}}
        sample = {'host': {'available_bytes': 688 * 1024**3}}
        with patch('benchmark.host.collect_sample', return_value=sample):
            receipt = proof.pre_retirement_admission(host, original)
            self.assertIn('STOPPED_manual', receipt['production'])
            for field, value in (('desired', 'running'), ('observed', 'ready'),
                                 ('container_running', True), ('boot_policy', 'resume')):
                bad = copy.deepcopy(original); bad['manager'][field] = value
                with self.assertRaisesRegex(ValueError, 'STOPPED_manual'):
                    proof.pre_retirement_admission(host, bad)
            sample['host']['available_bytes'] -= 1
            with self.assertRaisesRegex(ValueError, 'fresh_host_admission'):
                proof.pre_retirement_admission(host, original)

    def test_quiescent_guest_topology_allowed_masks_and_mems_are_real_reads(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            system, proc, group = root / 'sys', root / 'proc', root / 'group'
            (system / 'cpu').mkdir(parents=True); (system / 'node').mkdir()
            (system / 'cpu/online').write_text('0-71\n'); (system / 'node/online').write_text('0-7\n')
            for i in range(8):
                node = system / 'node' / ('node' + str(i)); node.mkdir()
                (node / 'cpulist').write_text(f'{9*i}-{9*i+8}\n')
                (node / 'meminfo').write_text(f'Node {i} MemTotal:       117440512 kB\n')
            (proc / '44').mkdir(parents=True); group.mkdir()
            (proc / '44/stat').write_text(cpu_fixture.stat())
            (proc / '44/numa_maps').write_text('1234 default file=/private/model N0=30 N7=10\n')
            for placement, cpus in (('G1', '0-71'), ('Q1', '0-7')):
                manifest = profile.postrestart_manifest(placement)
                container = {'HostConfig': {'CpusetCpus': cpus, 'CpusetMems': ''}}
                (group / 'cpuset.cpus.effective').write_text(cpus)
                (group / 'cpuset.mems.effective').write_text('0-7')
                (proc / '44/status').write_text(f'Cpus_allowed_list:\t{cpus}\nMems_allowed_list:\t0-7\n')
                def run():
                    return proof.postrestart_cpu_proof(manifest, container, group, [44], proc_root=proc, sys_root=system)
                receipt = run()
                self.assertEqual(receipt['status'], 'PASS')
                self.assertEqual(receipt['guest_node_memory_total_bytes'], 896 * 1024**3)
                self.assertEqual(receipt['processes'][0]['cpus_allowed_list'], cpus)
                self.assertNotIn('/private/model', json.dumps(receipt))
                for path, bad, good in ((system / 'cpu/online', '0-111', '0-71'),
                    (group / 'cpuset.mems.effective', '0-6', '0-7'),
                    (group / 'cpuset.cpus.effective', '72-79', cpus),
                    (proc / '44/status', f'Cpus_allowed_list:\t{cpus}\nMems_allowed_list:\t0-6\n',
                     f'Cpus_allowed_list:\t{cpus}\nMems_allowed_list:\t0-7\n')):
                    path.write_text(bad)
                    with self.assertRaises(ValueError): run()
                    path.write_text(good)


if __name__ == '__main__':
    unittest.main()
