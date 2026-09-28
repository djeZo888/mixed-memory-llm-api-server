"""Offline Ada observation proof composition; no native commands or lifecycle."""
import hashlib
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tests.test_node_projection import BOOT, Cached, sample
from control import node_observation as n
from control.node import NodeStatus, SERVICES


class AdaPassiveTests(unittest.TestCase):
    def setUp(self):
        self.cid = 'a' * 64
        self.source = b'def validate_container(c, config, state):\n assert c["Id"] == state["container"]["id"]\ndef operate(*a):\n raise AssertionError("mutation")\n'
        self.pins = {'ada_owner.py': hashlib.sha256(self.source).hexdigest()}
        self.files = {n.ADA_BASE + '/config.json': json.dumps({'source_sha256': self.pins}).encode(),
            n.ADA_AUTH_PATH: b'fixture-auth-source',
            n.ADA_BASE + '/state.json': json.dumps({'container': {'id': self.cid}}).encode(),
            n.ADA_BASE + '/source/ada_owner.py': self.source,
            '/data/services/secrets/llm-api-key': b'fixture-passive-secret-1234567890'}
        self.commands = []
        self.gets = []
        self.native = {'context_length': 200000, 'max_total_tokens': 200000,
            'internal_states': [{'max_total_num_tokens': 200000, 'max_req_input_len': 199994}]}
        def run(argv, seconds):
            self.commands.append(argv)
            self.assertEqual(argv, ['/usr/bin/docker', 'inspect', self.cid])
            return json.dumps([{'Id': self.cid, 'State': {'Running': True, 'StartedAt': 'unchanged'}}])
        self.reader = SimpleNamespace(boot=lambda: {'boot_id': BOOT}, run=run,
            binding=lambda _: SimpleNamespace(validate_path=lambda *_: None),
            read=lambda path, **_: self.files[str(path)])
        self.patch = patch.object(n, 'ADA_SOURCES', self.pins)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        auth_patch = patch.object(n, 'ADA_AUTH_SHA256', hashlib.sha256(b'fixture-auth-source').hexdigest())
        auth_patch.start()
        self.addCleanup(auth_patch.stop)

    def get(self, port, path, key, seconds):
        self.gets.append((port, path))
        self.assertEqual(port, 30014)
        self.assertGreater(seconds, 0)
        if path == '/get_server_info':
            return 200, self.native
        return 200, {'schema_version': 1, 'model_alias': n.ADA_ALIAS,
            'state': 'up', 'ready': True, 'admitting': None}

    def test_ready_requires_exact_source_identity_and_native_allocation(self):
        result = n.AdaPassiveCollector(self.reader, get=self.get)(2)
        self.assertTrue(result['ready'])
        self.assertEqual(result['configured_context_tokens'], 200000)
        self.assertIsNone(result['functional_qualified'])
        self.assertEqual(len(self.commands), 2)
        self.assertEqual(self.gets, [(30014, '/v1/readiness'), (30014, '/get_server_info')])

    def test_arbitrary_config_pins_cannot_bless_changed_source(self):
        self.files[n.ADA_BASE + '/source/ada_owner.py'] += b'\n# changed'
        with self.assertRaisesRegex(ValueError, 'source_identity'):
            n.AdaPassiveCollector(self.reader, get=self.get)(2)
        self.assertEqual(self.commands, [])

    def test_wrong_native_capacity_rejects_ready(self):
        self.native['max_total_tokens'] = 480000
        with self.assertRaisesRegex(ValueError, 'capacity_mismatch'):
            n.AdaPassiveCollector(self.reader, get=self.get)(2)

    def test_identity_change_during_readiness_is_rejected(self):
        def get(*args):
            response = self.get(*args)
            self.files[n.ADA_BASE + '/state.json'] += b' '
            return response
        with self.assertRaisesRegex(ValueError, 'identity_changed'):
            n.AdaPassiveCollector(self.reader, get=get)(2)

    def test_projection_is_observation_only_no_hardware_or_action_grant(self):
        result = n.AdaPassiveCollector(self.reader, get=self.get)(2)
        snapshot = NodeStatus(Cached({'boot': sample({'boot_id': BOOT}),
            n.ADA_SERVICE: sample(result)})).snapshot()
        row = next(row for row in snapshot['services'] if row['service_id'] == n.ADA_SERVICE)
        self.assertNotIn(n.ADA_SERVICE, SERVICES)
        self.assertNotIn(n.ADA_SERVICE, snapshot['affected_services'])
        self.assertEqual(row['affected_services'], [])
        self.assertIsNone(row['generation'])
        self.assertIsNone(row['admitting'])
        self.assertIsNone(row['hardware_latched'])
        self.assertIsNone(row['functional_qualified'])


if __name__ == '__main__':
    unittest.main()
