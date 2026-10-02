"""Source-only fixed model health routing; no live model or network contact."""
import copy
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest import mock

import build_graph
import control
import workload


class PrivateNetworkHealthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with tempfile.TemporaryDirectory() as directory:
            with mock.patch.object(build_graph, 'OUT', Path(directory)):
                cls.graph = build_graph.build()
        cls.service = json.loads((build_graph.ROOT / 'configs/vision/h043-candidate.json').read_text())['service']
        cls.proof = {'component': 'health', 'actualUid': 1000, 'proofSHA256': 'SOURCE_ONLY'}

    def test_authenticated_health_uses_each_fixed_private_role_and_preserves_ingress(self):
        calls = []
        identity = {key: self.service[key] for key in ('serviceId', 'generation', 'mode', 'interpreter', 'parser')}
        replies = {
            '172.31.243.2': {'data': [{'id': 'Qwen/Qwen3.5-9B'}]},
            '172.31.243.3': {'data': [{'id': 'PaddlePaddle/PaddleOCR-VL-1.6'}]},
            '127.0.0.1': {'service': identity, 'ready': True, 'admitting': True},
            '10.156.100.60': {'service': identity, 'ready': True, 'admitting': True},
        }

        class Response:
            status = 200
            def __init__(self, value):
                self.raw = json.dumps(value).encode()
            def read(self, _limit):
                raw, self.raw = self.raw, b''
                return raw
            def isclosed(self):
                return True

        class Connection:
            def __init__(self, host, port, timeout):
                self.host, self.port, self.sock = host, port, None
            def connect(self):
                pass
            def request(self, method, path, payload, headers):
                calls.append((self.host, self.port, method, path, payload, headers))
            def getresponse(self):
                return Response(replies[self.host])
            def close(self):
                pass

        with mock.patch.object(workload.http.client, 'HTTPConnection', Connection), \
             mock.patch.object(workload, 'graph_service', return_value=self.service):
            result = workload.health(copy.deepcopy(self.graph), self.proof, time.monotonic() + 2,
                                     lambda role: 'SOURCE_ONLY_FAKE_' + role)
        self.assertEqual(result['status'], 'HEALTHY')
        self.assertEqual([(host, port, method, path) for host, port, method, path, _, _ in calls], [
            ('172.31.243.2', 18191, 'GET', '/v1/models'),
            ('172.31.243.3', 18192, 'GET', '/v1/models'),
            ('127.0.0.1', 18193, 'GET', '/v1/technical-vision/capabilities'),
            ('10.156.100.60', 18193, 'GET', '/v1/technical-vision/capabilities'),
        ])
        for call, role in zip(calls, ('interpretation', 'ocr', 'service', 'service')):
            self.assertEqual(call[4], b'')
            self.assertEqual(call[5]['Authorization'], 'Bearer SOURCE_ONLY_FAKE_' + role)
        self.assertEqual([row['origin'] for row in result['observations'][:2]], [
            'http://172.31.243.2:18191', 'http://172.31.243.3:18192'])

    def test_mismatched_dynamic_or_egress_targets_fail_before_credentials_or_network(self):
        mutations = {
            'swapped_origins': lambda g: g['runtime']['service']['modelOrigins'].update(
                interpretation='http://172.31.243.3:18192', ocr='http://172.31.243.2:18191'),
            'dns': lambda g: g['runtime']['service']['modelOrigins'].update(interpretation='http://model.invalid:18191'),
            'wrong_ip': lambda g: g['runtime']['service']['modelOrigins'].update(interpretation='http://172.31.243.4:18191'),
            'userinfo': lambda g: g['runtime']['service']['modelOrigins'].update(interpretation='http://172.31.243.2:18191@model.invalid'),
            'url_path': lambda g: g['runtime']['service']['modelOrigins'].update(ocr='http://172.31.243.3:18192/other'),
            'egress': lambda g: g['runtime']['network'].update(internal=False),
            'wrong_subnet': lambda g: g['runtime']['network'].update(subnet='172.31.244.0/28'),
            'wrong_role_ip': lambda g: g['runtime']['network']['roleAddresses'].update(ocr='172.31.243.2'),
            'wrong_container_ip': lambda g: g['runtime']['containers'][0].update(privateIp='172.31.243.3'),
            'missing_origins': lambda g: g['runtime']['service'].pop('modelOrigins'),
            'dynamic_address': lambda g: g['runtime']['containers'][0]['createArgv'].__setitem__(
                g['runtime']['containers'][0]['createArgv'].index('--ip') + 1, '172.31.243.4'),
            'wrong_network': lambda g: g['runtime']['containers'][0]['createArgv'].__setitem__(
                g['runtime']['containers'][0]['createArgv'].index('--network') + 1, 'bridge'),
        }
        for name, mutate in mutations.items():
            graph = copy.deepcopy(self.graph)
            mutate(graph)
            with self.subTest(case=name), mock.patch.object(workload, 'bounded_call') as network, \
                 mock.patch.object(workload, 'graph_service') as service:
                credential = mock.Mock()
                with self.assertRaises(control.Refused):
                    workload.health(graph, self.proof, time.monotonic() + 1, credential)
                credential.assert_not_called()
                network.assert_not_called()
                service.assert_not_called()


if __name__ == '__main__':
    unittest.main()
