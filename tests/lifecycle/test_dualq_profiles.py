"""Offline dual-Qwen tuple checks; no native image, model or VM execution."""
import contextlib
import copy
import hashlib
import io
import json
import unittest
from unittest.mock import patch

from tests.lifecycle.test_qwen38 import ROOT, bound, q
from tests.lifecycle.test_sglang38_file_auth import args_fixture
from tests.lifecycle.test_qwen38_pair_fixture import pair, child, load
from lifecycle import concurrent_profiles
from runtime import sglang38_pair_file_auth as wrapper


class DualQwenProfiles(unittest.TestCase):
    def test_distinct_480k_instances_share_cpu_budget_and_pin_physical_gpus(self):
        declarations = [bound(name) for name in concurrent_profiles.QWEN_PROFILES]
        self.assertEqual(q.PAIR_PROFILES, frozenset(concurrent_profiles.QWEN_PROFILES))
        for index, d in enumerate(declarations):
            with self.subTest(index=index):
                q.validate(d)
                self.assertEqual(d['launch']['context_size'], 480000)
                self.assertEqual(d['launch']['max_total_tokens'], 480000)
                self.assertEqual(d['launch']['gpus'], [concurrent_profiles.GPU_UUIDS[index]])
                self.assertEqual(d['endpoint']['port'], (30002, 30004)[index])
                self.assertEqual(d['endpoint']['served_model'], ('qwen3.8-27b-gpu0', 'qwen3.8-27b')[index])
                self.assertEqual(q.command(d), [q.PAIR_LAUNCHER_TARGET, '--slot', 'gpu' + str(index)])
                self.assertEqual(d['concurrent_pair']['guest_cpuset'], '0-7')
                self.assertEqual(d['concurrent_pair']['guest_cpu_count'], 8)
                self.assertEqual(d['concurrent_pair']['guest_cpu_sharing'], 'shared')
                self.assertEqual(d['concurrent_pair']['memory_bytes'], 32 * 1024**3)
                self.assertEqual(d['concurrent_pair']['memory_swap_bytes'], 32 * 1024**3)
        self.assertNotEqual(declarations[0]['container_name'], declarations[1]['container_name'])
        for name in ('cache', 'logs', 'service'):
            self.assertNotEqual(declarations[0]['paths'][name], declarations[1]['paths'][name])

    def test_glm72_shared_mask_retains_cap_and_allocation(self):
        d = concurrent_profiles.declared_profile(concurrent_profiles.GLM_PROFILE)
        self.assertEqual((d['launch']['threads'], d['launch']['threads_batch']), (72, 72))
        self.assertEqual(d['concurrent_pair']['guest_cpuset'], '0-71')
        self.assertEqual(d['concurrent_pair']['guest_cpu_sharing'], 'shared')
        self.assertEqual(d['concurrent_pair']['memory_bytes'], 640 * 1024**3)
        self.assertEqual(d['concurrent_pair']['host_demand_reserve_percent'], 15)

    def test_historical_700k_profile_bytes_retained_but_not_admitted(self):
        name = 'qwen38-27b-q1-700160-yarn4-bf16kv'
        raw = (ROOT / 'configs/deployments' / (name + '.json')).read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), '7650e6ba3cc089ce3955c465a76bd0d97b832c5e1ef1d1ee37dfc56f13a1d401')
        self.assertNotIn(name, q.VARIANTS)
        self.assertFalse(concurrent_profiles.is_pair({'id': name}))

    def test_probe_rejects_cross_slot_alias_and_port(self):
        for port, alias in ((30002, 'qwen3.8-27b-gpu0'), (30004, 'qwen3.8-27b')):
            with patch.object(q, 'probe_sglang', return_value='synthetic') as probe:
                self.assertEqual(q.probe(f'http://127.0.0.1:{port}/v1', alias, '/synthetic/key'), 'synthetic')
                probe.assert_called_once()
            wrong_port = 30004 if port == 30002 else 30002
            with self.assertRaises(q.LifecycleError):
                q.probe(f'http://127.0.0.1:{wrong_port}/v1', alias, '/synthetic/key')


class ClosedDualQwenLauncher(unittest.TestCase):
    def test_raw_and_resolved_slot_tuples_reject_cross_routing(self):
        for slot, expected in wrapper.SLOTS.items():
            base = wrapper.pinned_base(ROOT / 'scripts/runtime/sglang38_file_auth.py')
            argv = wrapper.bind_variant(base, slot)
            self.assertEqual(argv[argv.index('--context-length') + 1], '480000')
            self.assertEqual(argv[argv.index('--port') + 1], str(expected['port']))
            for resolved in (False, True):
                args = args_fixture(1000000, resolved=resolved)
                args.context_length = args.max_total_tokens = 480000
                args.tp_size = 1
                args.port = expected['port']
                args.served_model_name = expected['served_model_name']
                base.validate_server_args(args, resolved=resolved)
                for field, value in (('port', 30004 if slot == 'gpu0' else 30002),
                        ('served_model_name', 'qwen3.8-27b' if slot == 'gpu0' else 'qwen3.8-27b-gpu0'),
                        ('context_length', 700160), ('max_total_tokens', True),
                        ('tp_size', 2), ('api_key', 'synthetic-prohibited')):
                    bad = copy.deepcopy(args)
                    setattr(bad, field, value)
                    with self.subTest(slot=slot, field=field, resolved=resolved), self.assertRaises(base.LaunchError):
                        base.validate_server_args(bad, resolved=resolved)

    def test_cli_only_accepts_one_closed_slot_without_reading_key(self):
        with patch.object(wrapper, 'pinned_base') as source:
            for arguments in ([], ['--slot', 'gpu2'], ['--slot=gpu0'],
                              ['--slot', 'gpu0', '--slot', 'gpu1'],
                              ['--slot', 'gpu0', '--port', '30004']):
                with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                    wrapper.main(arguments)
            source.assert_not_called()
        for slot in wrapper.SLOTS:
            base = wrapper.pinned_base(ROOT / 'scripts/runtime/sglang38_file_auth.py')
            with patch.object(wrapper, 'pinned_base', return_value=base), \
                    patch.object(wrapper, 'verify_adaptive_overlay') as overlay_guard, \
                    patch.object(base, 'main', return_value=0) as launch:
                self.assertEqual(wrapper.main(['--slot', slot]), 0)
                overlay_guard.assert_called_once_with()
                self.assertEqual(launch.call_args.args[0][-3:], ['480000', '--disable-radix-cache', '--disable-overlap-schedule'])

    def test_fixture_slot_binds_native_alias_port_identity_and_child_arguments(self):
        for slot, expected in wrapper.SLOTS.items():
            identity = pair.pair_identity(ROOT, slot=slot)
            self.assertEqual(identity['slot'], slot)
            self.assertEqual(identity['native_endpoint'], expected)
            self.assertEqual(identity['profile_id'], pair.PROFILES[slot])
            with pair.fixture_mode(slot):
                command = pair.host.docker_command(ROOT, {}, 480000)
                self.assertEqual(command[-2:], ['--slot', slot])
            with patch.object(child.inner, 'main', return_value=0) as execute:
                def check(arguments):
                    self.assertEqual(child.inner.ALIAS, expected['served_model_name'])
                    self.assertEqual(child.inner.PORT, expected['port'])
                    self.assertEqual(child.inner.CHILD_ARGUMENTS, ('--slot', slot))
                    self.assertEqual(child.inner.FIXTURE_SLOT, slot)
                    self.assertEqual(child.inner.fixture_contract(ROOT).extension_identity(ROOT)['slot'], slot)
                    return 0
                execute.side_effect = check
                self.assertEqual(child.main(['--actual-image', '--repo', str(ROOT), '--context', '480000', '--slot', slot]), 0)
        self.assertEqual(child.inner.ALIAS, 'qwen3.8-27b')
        self.assertEqual(child.inner.PORT, 30004)
        self.assertEqual(child.inner.CHILD_ARGUMENTS, ())


if __name__ == '__main__':
    unittest.main()
