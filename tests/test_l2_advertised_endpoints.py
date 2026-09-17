"""L2 public DTO/config checks; real local HTTP, no deployed service/inference."""
from copy import deepcopy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'tests'))
from control import installation
from control.catalog import Catalog
from test_control_catalog import record, observation
from test_control_fixtures import HTTPHarness

# Frozen N1S public contract; validation belongs to its actual protected loader.
POLICY = {
    'schema_version': 1, 'mode': 'socket_proxyd_private_ipv4',
    'interface': 'enp6s18', 'private_address': '10.156.100.60',
    'prefix_length': 24, 'allowed_client_ipv4': ['10.156.100.0/24'],
    'ports': {'control': 30000, 'glm': 30002, 'qwen38': 30004},
}


def model(identifier, model_id, port, alias, context):
    return record(identifier, model_id=model_id, context_limit=context,
                  endpoint={'host': '127.0.0.1', 'port': port, 'api_prefix': '/v1',
                            'served_model': alias, 'authentication_required': True})


class AdvertisedDTOTests(unittest.TestCase):
    def setUp(self):
        self.records = [
            model('glm-owner-context', 'unsloth/GLM-5.3-GGUF', 30002, 'glm-5.3', 1048576),
            model('qwen38-27b-128k', 'Qwen/Qwen3.8-27B-FP8', 30004, 'qwen38-27b', 131072),
            model('qwen38-27b-256k', 'Qwen/Qwen3.8-27B-FP8', 30004, 'qwen38-owner-alias', 262144),
        ]

    def test_two_model_context_variants_use_actual_alias_and_exact_role_port(self):
        catalog = Catalog(self.records)
        public = catalog.public(observation(), advertised_policy=POLICY)
        self.assertEqual(len({item['model_id'] for item in public}), 2)
        for item, raw in zip(public, self.records):
            self.assertEqual(item['endpoint'], {
                'base_url': f"http://10.156.100.60:{raw['endpoint']['port']}/v1",
                'served_model': raw['endpoint']['served_model'],
                'authentication_required': True, 'address_scope': 'private_network',
                'server_relative': False, 'ready': False,
            })
            self.assertEqual(item['context']['configured_provenance'], 'declared')
            self.assertIsNone(item['context']['verified_occupied_tokens'])
            self.assertTrue(catalog.target(item['deployment_id'])['endpoint']['server_relative'])
        self.assertEqual(self.records[0]['endpoint']['host'], '127.0.0.1')

    def test_absence_future_identity_wrong_role_port_and_control_port_keep_tunnel(self):
        variants = [self.records[0],
                    model('future', 'Future/Model', 30002, 'future', 8192),
                    model('wrong-port', 'unsloth/GLM-5.3-GGUF', 30004, 'glm-5.3', 8192),
                    model('control-port', 'Qwen/Qwen3.8-27B-FP8', 30000, 'qwen38', 8192)]
        for policy, records in ((None, self.records), (POLICY, variants[1:])):
            for item in Catalog(records).public(observation(), advertised_policy=policy):
                self.assertTrue(item['endpoint']['base_url'].startswith('http://127.0.0.1:'))
                self.assertEqual(item['endpoint']['address_scope'], 'server_loopback')
                self.assertTrue(item['endpoint']['server_relative'])

    def test_advertisement_cannot_accept_nonloopback_or_disabled_auth_profile(self):
        for change in ({'host': '10.156.100.60'}, {'host': '0.0.0.0'},
                       {'authentication_required': False}):
            value = deepcopy(self.records[0])
            value['endpoint'].update(change)
            with self.assertRaises(ValueError):
                Catalog([value]).public(observation(), advertised_policy=POLICY)

    def test_real_authenticated_http_status_catalog_and_header_spoofing(self):
        with tempfile.TemporaryDirectory(prefix='l2-advertised-') as directory:
            http = HTTPHarness(Path(directory))
            try:
                http.backend.records = deepcopy(self.records)
                http.backend.state.update(model_id=self.records[0]['model_id'],
                                          endpoint=deepcopy(self.records[0]['endpoint']))
                spoof = {'Host': 'evil.invalid:9999', 'Forwarded': 'host=evil.invalid;proto=https',
                         'X-Forwarded-Host': 'evil.invalid', 'X-Forwarded-Proto': 'https'}
                for policy, host in ((None, '127.0.0.1'), (deepcopy(POLICY), '10.156.100.60')):
                    http.app.advertised_policy = policy  # Explicit in-process test seam only.
                    for path in ('/control/v1/status', '/control/v1/catalog'):
                        status, dto = http.request(path=path, headers=spoof)
                        self.assertEqual(status, 200)
                        self.assertEqual(dto['endpoint']['base_url'], f'http://{host}:30002/v1')
                        self.assertNotIn('model_id', dto)  # Raw identity is not new status metadata.
                        self.assertNotIn('evil.invalid', json.dumps(dto))
                        for entry in dto.get('entries', []):
                            self.assertTrue(entry['endpoint']['base_url'].startswith(f'http://{host}:'))
                        self.assertFalse(dto['endpoint']['ready'])
                        self.assertEqual(http.request(path=path, auth=False, headers=spoof)[0], 401)
                self.assertEqual(http.address[0], '127.0.0.1')
                self.assertEqual(http.backend.calls, [])
                self.assertEqual(http.backend.state['endpoint']['host'], '127.0.0.1')
            finally:
                http.close()


class ControlSettingTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='l2-control-config-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.config = self.root / 'control.json'
        self.config.write_text('{"schema_version":1}')
        self.config.chmod(0o600)
        self.addCleanup(patch.stopall)
        patch.object(installation, 'CONFIG_FILE', self.config).start()
        original = installation.protected_file
        patch.object(installation, 'protected_file', side_effect=lambda path, **kw:
                     original(path, uid=os.geteuid(), boundary=self.root, **kw)).start()

    def write(self, raw):
        self.config.write_bytes(raw)

    def test_exact_optional_field_and_default(self):
        self.assertEqual(installation._control_config(self.root.stat().st_dev), {'schema_version': 1})
        self.assertIsNone(installation.read_advertised_policy())
        self.write(b'{"schema_version":1,"advertised_endpoint_policy":"private_network"}')
        self.assertEqual(installation._control_config(self.root.stat().st_dev)['advertised_endpoint_policy'],
                         'private_network')

    def test_invalid_fields_types_duplicates_and_arbitrary_origin_are_refused(self):
        for value in (None, False, 1, [], {}, '10.156.100.60', 'https://10.156.100.60', 'tunnel'):
            self.write(json.dumps({'schema_version': 1, 'advertised_endpoint_policy': value}).encode())
            with self.subTest(value=value), self.assertRaises(installation.InstallationError):
                installation.read_advertised_policy()
        for raw in (b'{"schema_version":true}',
                    b'{"schema_version":1,"advertised_endpoint_policy":"private_network","host":"10.156.100.60"}',
                    b'{"schema_version":1,"advertised_endpoint_policy":"private_network","advertised_endpoint_policy":"private_network"}'):
            self.write(raw)
            with self.subTest(raw=raw), self.assertRaises(installation.InstallationError):
                installation.read_advertised_policy()


if __name__ == '__main__':
    unittest.main()
