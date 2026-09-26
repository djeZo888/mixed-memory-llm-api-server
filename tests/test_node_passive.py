"""Offline fake-clock and real loopback fixtures; no VM or native backend."""
import concurrent.futures
import http.client
import json
from pathlib import Path
import sys
import threading
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from control.passive import BoundedObservers
from control.node import NodeStatus, NodeApplication
from control.node_actions import NodeActions
from control.http import make_server
from control import node_collectors as collectors
from control import node_installation

BOOT = '37e425eb-3d3e-4070-80a0-5ecfb39604f1'
GPU = collectors.GPU_UUIDS[0]


def wait_for(predicate):
    limit = time.monotonic() + 2
    while not predicate() and time.monotonic() < limit:
        threading.Event().wait(.001)
    assert predicate()


class Clock:
    value = 0
    def __call__(self):
        return self.value


class PassiveTests(unittest.TestCase):
    def test_600_reads_do_not_start_collectors_or_refresh(self):
        calls = []
        obs = BoundedObservers({'boot': lambda _: calls.append(1)})
        status = NodeStatus(obs)
        for _ in range(600):
            self.assertEqual(status.snapshot()['freshness'], 'unknown')
        self.assertEqual(calls, [])

    def test_hung_capacity_independent_and_late_result_discarded(self):
        clock = Clock()
        release, entered = threading.Event(), threading.Event()
        calls = []
        def hang(_):
            calls.append(1); entered.set(); release.wait(); return {'secret': 'must_not_publish_late'}
        obs = BoundedObservers({'hung': hang, 'healthy': lambda _: {'ok': True}}, clock=clock)
        try:
            obs.tick(); self.assertTrue(entered.wait(1))
            wait_for(lambda: obs.read('healthy')['state'] == 'ok')
            clock.value = 30
            with concurrent.futures.ThreadPoolExecutor(8) as executor:
                list(executor.map(lambda _: obs.tick(), range(500)))
            self.assertEqual(len(calls), 1)
            self.assertEqual(obs.read('hung')['state'], 'timeout')
            self.assertIsNone(obs.read('hung')['value'])
            release.set(); wait_for(lambda: obs.active_count() == 0)
            self.assertIsNone(obs.read('hung')['value'])
        finally:
            release.set(); obs.close()

    def test_error_preserves_age_does_not_refresh_prior_success(self):
        clock = Clock()
        fail = []
        def callback(_):
            if fail: raise RuntimeError('private exception text')
            return {'value': 1}
        obs = BoundedObservers({'source': callback}, clock=clock, wall=lambda: 1700000000)
        obs.tick(); wait_for(lambda: obs.active_count() == 0)
        first = obs.read('source')['observed_at']
        fail.append(1); clock.value = 16; obs.tick(); wait_for(lambda: obs.active_count() == 0)
        result = obs.read('source')
        self.assertEqual((result['freshness'], result['age_ms'], result['state']), ('stale', 16000, 'error'))
        self.assertEqual(result['observed_at'], first)
        self.assertNotIn('private', json.dumps(result))
        obs.close()

    def test_independent_authenticated_http_status_survives_hung_observer(self):
        release = threading.Event()
        def hung(_): release.wait(); return {}
        obs = BoundedObservers({'inventory': hung})
        application = NodeApplication(NodeStatus(obs), NodeActions())
        key = b'fixture-node-credential-not-a-real-key'
        server = make_server(application, key, port=0)
        thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .01}, daemon=True)
        thread.start(); obs.tick()
        def request(auth):
            connection = http.client.HTTPConnection(*server.server_address, timeout=1)
            connection.request('GET', '/control/v1/node/status', headers={'Authorization': 'Bearer '+key.decode()} if auth else {})
            response = connection.getresponse(); result = response.status, json.loads(response.read());connection.close();return result
        try:
            self.assertEqual(request(False)[0], 401)
            started = time.monotonic()
            status, body = request(True)
            self.assertEqual((status, body['node_id']), (200, 'ai-vm'))
            self.assertLess(time.monotonic() - started, .5)
            self.assertEqual(body['inventory']['freshness'], 'unknown')
        finally:
            release.set(); obs.close(); server.shutdown(); server.server_close(); thread.join(1)

    def test_no_legacy_routes_and_strict_duplicate_action_body(self):
        app = NodeApplication(NodeStatus(BoundedObservers({'boot': lambda _: {}})), NodeActions())
        self.assertEqual(app.handle('GET', '/control/v1/status', {}, b'')[0], 404)
        self.assertEqual(app.handle('POST', '/control/v1/node/actions', {}, b'{"action":"a","action":"b"}')[0],400)
        self.assertEqual(app.handle('POST', '/control/v1/node/actions', {}, b'[]')[0],400)


class CollectorsTests(unittest.TestCase):
    def test_successful_empty_inventory_vs_failed_initialization(self):
        identity = lambda: {'boot_id': BOOT, 'boot_age_seconds': 130}
        result = collectors.collect_inventory(2, run=lambda *_: '', boot=identity)
        self.assertEqual((result['complete'], result['gpu_uuids']), (True, []))
        def fail(*_): raise ValueError('NVML init failed')
        with self.assertRaises(ValueError):
            collectors.collect_inventory(2, run=fail, boot=identity)
        with self.assertRaises(ValueError):
            collectors.collect_inventory(2, run=lambda *_: GPU+'\n'+GPU, boot=identity)

    def test_gpu_uuid_scoped_nullable_sensors_and_observed_extrema(self):
        calls=[]
        xml = ['<nvidia_smi_log><gpu><uuid>'+GPU+'</uuid><product_name>Fixture GPU</product_name><temperature><gpu_temp>34 C</gpu_temp></temperature><ecc_mode><current_ecc>Enabled</current_ecc></ecc_mode></gpu></nvidia_smi_log>']
        def run(argv, seconds): calls.append(argv);return xml[0]
        collector = collectors.GpuCollector(GPU, run=run, boot=lambda: {'boot_id': BOOT})
        first = collector(2)['gpus'][0]
        xml[0] = xml[0].replace('34 C', '39 C')
        second = collector(2)['gpus'][0]
        self.assertIn('--id='+GPU,calls[0]);self.assertEqual(len(calls),2)
        self.assertEqual((second['temperature_min_c'], second['temperature_max_c']),(34,39))
        self.assertEqual(first['ecc_mode'],'enabled')
        self.assertIsNone(first['memory_total_mib']);self.assertIsNone(first['power_draw_w'])
        self.assertIsNone(first['index'])

    def test_cpu_node_fraction_and_first_sample_unknown(self):
        lines=['cpu  10 0 10 80 0 0 0 0\n']
        collector=collectors.CpuCollector(read=lambda:lines[0],count=lambda:72)
        self.assertIsNone(collector(2)['percent'])
        lines[0]='cpu  20 0 20 160 0 0 0 0\n'
        self.assertEqual(collector(2),{'percent':20,'logical_count':72})

    def test_service_running_does_not_mean_ready_or_idle(self):
        collector=collectors.service_collector('control',run=lambda *_:'active',boot=lambda:{'boot_id':BOOT})
        self.assertEqual(collector(2)['activity'],'unknown')
        self.assertIsNone(collector(2)['ready'])
        collector=collectors.service_collector('control',run=lambda *_:'failed',boot=lambda:{'boot_id':BOOT})
        self.assertFalse(collector(2)['ready'])

    def test_command_deadline_output_limit_and_no_shell(self):
        self.assertEqual(collectors.command([sys.executable,'-c','print("ok")'],2),'ok\n')
        started=time.monotonic()
        with self.assertRaises(TimeoutError):
            collectors.command([sys.executable,'-c','import time;time.sleep(3)'],.05)
        self.assertLess(time.monotonic()-started,1)
        with self.assertRaises(ValueError):
            collectors.command([sys.executable,'-c','print("x"*300000)'],2)

    def test_production_observers_are_bounded_and_individual(self):
        callbacks=collectors.production_callbacks()
        self.assertLessEqual(len(callbacks),17)
        from control.passive import BoundedObservers
        BoundedObservers(callbacks).close()
        self.assertEqual(len([name for name in callbacks if name.startswith('gpu:')]),4)
        self.assertNotIn('gpu_metrics',callbacks)

    def test_node_source_closure_and_credentials_protected_before_start(self):
        root=Path(__file__).resolve().parents[1]
        manifest=json.loads((root/'scripts/control/node-source-closure.json').read_text())
        self.assertEqual(manifest['files'],list(node_installation.SOURCE_FILES))
        key=b'fixture-node-protected-secret-material-only'
        calls=[]
        def read(path, **kwargs):
            calls.append(path)
            return json.dumps(manifest).encode() if path.name=='node-source-closure.json' else key
        with patch.object(node_installation.os,'geteuid',return_value=0),patch.object(node_installation,'protected_file',side_effect=read):
            self.assertEqual(node_installation.validate_installation(),key)
        self.assertIn(node_installation.CREDENTIAL_FILE,calls)
        self.assertIn(node_installation.KEY_SOURCE,calls)


if __name__=='__main__': unittest.main()
