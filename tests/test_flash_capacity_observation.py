"""H013 capacity advertisement: pure/local fixtures, no VM or native requests."""
import copy
import hashlib
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from control import node_observation as n

BOOT = '37e425eb-3d3e-4070-80a0-5ecfb39604f1'


def native(context):
    return {'context_length': context, 'max_total_tokens': context,
            'internal_states': [{'max_total_num_tokens': context,
                                 'max_req_input_len': context - 6}]}


class CapacityObservation(unittest.TestCase):
    def test_historical_and_candidate_actual_pools(self):
        for context in (480000, 1048576):
            self.assertEqual(n.flash_native_context(200, native(context), context), {
                'configured_context_tokens': context,
                'deployment_id': f'glm-5.3-flash-{context}-fp8-kt'})

    def test_invalid_partial_conflicting_and_wrong_pool_refused(self):
        for context in (True, 1048576.0, '1048576', 1000000, 0, None):
            with self.assertRaises(ValueError):
                n.flash_native_context(200, native(1048576), context)
        for value in ({}, native(480000), {**native(1048576), 'context_length': True},
                      {**native(1048576), 'internal_states': None},
                      {**native(1048576), 'max_req_input_len': 1048571}):
            with self.assertRaises(ValueError):
                n.flash_native_context(200, value, 1048576)
        with self.assertRaises(ValueError):
            n.flash_native_context(503, native(1048576), 1048576)

    def test_real_local_candidate_sources_bound_to_manifest(self):
        names = {'file_auth.py', 'tokenize_adapter.py', 'idle.py', 'owner.py',
                 'tool_runtime.py', 'native-source-pins.json', 'numa-seccomp.json'}
        sources = {name: (ROOT / 'scripts/runtime/flash' / name).read_bytes() for name in names}
        config = {'source_sha256': {name: hashlib.sha256(raw).hexdigest()
                                    for name, raw in sources.items()}}
        read = lambda path, **kwargs: sources[path.name]
        self.assertEqual(n.flash_source_context(config, read), 1048576)
        common_changed = copy.deepcopy(config)
        common_changed['source_sha256']['owner.py'] = 'f' * 64
        with self.assertRaisesRegex(ValueError, 'common_source_unknown'):
            n.flash_source_context(common_changed, read)
        sources['idle.py'] += b'\n# unreviewed source\n'
        with self.assertRaisesRegex(ValueError, 'identity_changed'):
            n.flash_source_context(config, read)
        config['source_sha256']['idle.py'] = hashlib.sha256(sources['idle.py']).hexdigest()
        with self.assertRaisesRegex(ValueError, 'source_unknown'):
            n.flash_source_context(config, read)
        del config['source_sha256']['owner.py']
        with self.assertRaisesRegex(ValueError, 'manifest_unknown'):
            n.flash_source_context(config, read)

    def collect(self, context=1048576, *, actual=None, identity_changes=False, ready=True, generation=123):
        calls = []
        row = {'running': True, 'ownership_valid': True, 'hardware_latched': None,
               'boot_id': BOOT, 'generation': generation, 'source_context_tokens': context,
               'configured_context_tokens': None, 'deployment_id': None, 'ready': None}
        service_calls = []
        def service(*args):
            service_calls.append(args)
            value = copy.deepcopy(row)
            if identity_changes and len(service_calls) > 1:
                value['generation'] += 1
            return value
        binding = SimpleNamespace(path=lambda *args: '/fixture/key', validate_path=lambda *args: None)
        reader = SimpleNamespace(service=service, binding=lambda _: binding,
            read=lambda *args, **kwargs: b'fixture-only-key-12345678901234567890', boot=lambda: {'boot_id': BOOT})
        def get(port, path, key, seconds):
            calls.append((port, path))
            if path == '/v1/readiness':
                return (200 if ready else 503), {'schema_version': 1, 'model_alias': 'glm-5.3-flash',
                    'ready': ready, 'state': 'up' if ready else 'starting', 'admitting': None}
            self.assertEqual((port, path), (30010, '/get_server_info'))
            return 200, native(context if actual is None else actual)
        return n.PassiveServiceCollector('glm-5.3-flash', reader, get=get)(2), calls

    def test_collector_requires_native_pool_and_stable_source_owner(self):
        for context in (480000, 1048576):
            row, calls = self.collect(context)
            self.assertTrue(row['ready'])
            self.assertEqual(row['configured_context_tokens'], context)
            self.assertEqual(calls, [(30010, '/v1/readiness'), (30010, '/get_server_info')])
        for kwargs in ({'actual': 480000}, {'identity_changes': True}, {'ready': False},
                       {'generation': None}, {'generation': True}):
            row, _ = self.collect(**kwargs)
            self.assertIsNone(row['configured_context_tokens'])
            self.assertIsNone(row['deployment_id'])
            self.assertIsNot(row['ready'], True)


if __name__ == '__main__':
    unittest.main()
