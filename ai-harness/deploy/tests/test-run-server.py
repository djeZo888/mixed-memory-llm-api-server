#!/usr/bin/env python3
"""Host launcher fixture: no server, real credential or network is used."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

LAUNCHER = Path(__file__).resolve().parents[1] / 'run-server.sh'


@unittest.skipIf(os.geteuid() == 0, 'server launcher refuses root')
class ServerContract(unittest.TestCase):
    def test_explicit_worker_gateway_origin_web_path_and_clean_environment(self):
        with tempfile.TemporaryDirectory(prefix='h001-server-launch-') as temp:
            root = Path(temp).resolve()
            prefix = root / 'node'
            (prefix / 'bin').mkdir(parents=True)
            node = prefix / 'bin/node'
            node.write_text(f'#!{sys.executable}\nimport json,os,sys\n'
                            'print("v24.21.0" if sys.argv[1:] == ["--version"] else json.dumps(dict(os.environ)))\n')
            node.chmod(0o700)
            app = root / 'app'
            (app / 'server/dist').mkdir(parents=True)
            (app / 'server/dist/main.js').touch()
            (app / 'web/dist').mkdir(parents=True)
            engine = root / 'engine'
            engine.write_text('#!/bin/sh\nexit 0\n')
            engine.chmod(0o700)
            key = root / 'synthetic-key'
            key.write_text('synthetic-test-value-never-exported')
            key.chmod(0o600)
            data = root / 'data'
            args = ['/bin/bash', str(LAUNCHER), '--node-prefix', str(prefix),
                    '--app-dir', str(app), '--data-dir', str(data),
                    '--inference-key-file', str(key), '--engine-launcher', str(engine)]
            env = dict(os.environ, OPENAI_API_KEY='ambient-must-not-pass',
                       AI_HARNESS_GATEWAY_TOKEN='ambient-runner-must-not-pass',
                       AI_HARNESS_GATEWAY_URL='http://unreviewed.invalid/v1')
            result = subprocess.run(args, env=env, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            observed = json.loads(result.stdout)
            self.assertEqual(observed['AI_HARNESS_GATEWAY_URL'], 'http://10.0.2.2:8081/v1')
            self.assertEqual(observed['AI_HARNESS_ALLOWED_ORIGINS'], 'http://10.156.100.61')
            self.assertEqual(observed['AI_HARNESS_WEB_DIST'], str(app / 'web/dist'))
            self.assertEqual(observed['AI_HARNESS_INFERENCE_KEY_FILE'], str(key))
            self.assertTrue(observed['PATH'].startswith(str(prefix / 'bin') + ':'))
            for name in ('OPENAI_API_KEY', 'AI_HARNESS_GATEWAY_TOKEN', 'NODE_OPTIONS', 'SSH_AUTH_SOCK'):
                self.assertNotIn(name, observed)
            self.assertNotIn(key.read_text(), result.stdout + result.stderr)
            self.assertEqual(data.stat().st_mode & 0o777, 0o700)
            key.chmod(0o644)
            rejected = subprocess.run(args, env=env, text=True, capture_output=True)
            self.assertNotEqual(rejected.returncode, 0)
            self.assertNotIn(key.read_text(), rejected.stdout + rejected.stderr)


if __name__ == '__main__':
    unittest.main(verbosity=2)
