"""Source-only checks of the fixed, isolated H045 model endpoint graph."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import build_graph


class PrivateNetworkGraphTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = json.loads((build_graph.ROOT / 'configs/vision/h043-candidate.json').read_text())
        cls.tmp = tempfile.TemporaryDirectory()
        cls.out = Path(cls.tmp.name)
        with mock.patch.object(build_graph, 'OUT', cls.out):
            cls.graph = build_graph.build()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_exact_role_addresses_no_publication_or_dns(self):
        network = self.graph['runtime']['network']
        self.assertIs(network['internal'], True)
        self.assertEqual(network['subnet'], '172.31.243.0/28')
        self.assertIn('--internal', network['createArgv'])
        self.assertEqual(network['createArgv'][network['createArgv'].index('--subnet') + 1], network['subnet'])
        self.assertEqual(network['loopbackPorts'], [])
        for model in self.graph['runtime']['containers']:
            ip, port, key, _ = build_graph.MODEL_ENDPOINTS[model['role']]
            argv = model['createArgv']
            self.assertEqual(argv[argv.index('--ip') + 1], ip)
            self.assertEqual(argv[argv.index('--network') + 1], 'ACTUAL_NEW_NETWORK_ID')
            self.assertEqual(network['roleAddresses'][model['role']], ip)
            self.assertEqual(model['privateIp'], ip)
            self.assertEqual(model['origin'], f'http://{ip}:{port}')
            self.assertEqual(model['origin'], self.cfg['service'][key])
            self.assertNotIn('--publish', argv)
            self.assertNotIn('-p', argv)
            self.assertIn('--pull=never', argv)
            self.assertIn('HF_HUB_OFFLINE=1', argv)

    def test_service_frontend_and_private_ingress_unchanged(self):
        runtime = self.graph['runtime']
        self.assertEqual(runtime['service']['listenOrigin'], 'http://127.0.0.1:18193')
        self.assertEqual(runtime['service']['modelOrigins'], {
            'interpretation': 'http://172.31.243.2:18191',
            'ocr': 'http://172.31.243.3:18192'})
        self.assertEqual(runtime['ingress']['bind'], '10.156.100.60:18193')
        self.assertEqual(runtime['ingress']['forward'], '127.0.0.1:18193')
        self.assertEqual(runtime['ingress']['clientIp'], '10.156.100.61')
        self.assertIs(runtime['service']['enabled'], False)
        self.assertIs(runtime['ingress']['enabled'], False)
        self.assertIs(self.graph['execute'], False)

    def test_approved_fixed_kv_and_private_exec_tmpfs_reproduced(self):
        for model in self.graph['runtime']['containers']:
            argv, runtime = model['createArgv'], model['runtimeArgv']
            expected_kv = build_graph.MODEL_ENDPOINTS[model['role']][3]
            self.assertEqual(runtime[runtime.index('--kv-cache-memory-bytes') + 1], str(expected_kv))
            self.assertEqual(runtime.count('--kv-cache-memory-bytes'), 1)
            self.assertEqual([argv[i+1] for i, arg in enumerate(argv) if arg == '--tmpfs'], [
                '/tmp:rw,exec,nosuid,size=4g,mode=700,uid=1000,gid=1000',
                '/home/runtime:rw,exec,nosuid,size=64m,mode=700,uid=1000,gid=1000'])
            self.assertIn('--ipc=private', argv)
            self.assertIn('--read-only', argv)
            exported = self.out / ('runtime-argv-' + model['role'] + '.json')
            self.assertEqual(json.loads(exported.read_text()), runtime)
            manifest = json.loads((self.out / 'SOURCE-MANIFEST.json').read_text())
            self.assertEqual(manifest['inputs'][exported.name]['sha256'], hashlib.sha256(exported.read_bytes()).hexdigest())

    def test_roster_capacity_pins_preserved(self):
        runtime = self.graph['runtime']
        self.assertEqual(runtime['enabledServices'], {'general': ['qwen0', 'qwen1', 'mimo'], 'vision': ['interpretation', 'ocr'], 'generation': False})
        self.assertEqual(runtime['peakMeasurements']['otherInstanceCount'], 3)
        self.assertEqual(runtime['peakMeasurements']['minimumFreeFraction'], 0.07)
        self.assertEqual(self.graph['workload']['generalContext'], 480000)
        self.assertEqual(self.graph['workload']['generalOutput'], 65536)
        self.assertEqual(self.cfg['runtime03']['pins'], {'native': '0.158.0', 'upstream': '064c', 'context': 480000, 'auto': 400000, 'output': 65536})

    def test_config_role_mismatch_and_user_origins_rejected(self):
        cases = []
        for field, value in [('privateIp', '172.31.243.3'), ('candidatePort', 18192), ('kvCacheMemoryBytes', 1), ('role', 'untrusted')]:
            cfg = copy.deepcopy(self.cfg)
            cfg['models'][0][field] = value
            cases.append(cfg)
        for origin in ['http://localhost:18191', 'http://example.com:18191', 'http://127.0.0.1:18191', 'http://172.31.243.2:18191/path', 'http://172.31.243.3:18192']:
            cfg = copy.deepcopy(self.cfg)
            cfg['service']['qwenOrigin'] = origin
            cases.append(cfg)
        for cfg in cases:
            with self.subTest(cfg=cfg['service']['qwenOrigin'], model=cfg['models'][0]):
                with self.assertRaises(ValueError):
                    build_graph.validate_model_network(cfg)

    def test_internal_subnet_changes_rejected(self):
        for network in [{'internal': False, 'subnet': '172.31.243.0/28'}, {'internal': True, 'subnet': '172.31.244.0/28'}, {}]:
            cfg = copy.deepcopy(self.cfg)
            cfg['modelNetwork'] = network
            with self.subTest(network=network), self.assertRaises(ValueError):
                build_graph.validate_model_network(cfg)


if __name__ == '__main__':
    unittest.main()
