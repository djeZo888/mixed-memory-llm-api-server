"""Source-only launcher argv/environment regressions; no native qualification."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

LAUNCHER = Path(__file__).resolve().parents[2] / 'deploy/run-server.sh'
FLAGS = {'--codex-generation-acceptance': 'AI_HARNESS_CODEX_GENERATION_ACCEPTANCE_FILE',
         '--codex-global-generation-proof': 'AI_HARNESS_CODEX_GENERATION_ONLY_FILE',
         '--codex-current-frontier-proof': 'AI_HARNESS_CODEX_CURRENT_FRONTIER_FILE'}

@unittest.skipIf(os.getuid() == 0, 'launcher requires ordinary service user')
class LauncherTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.node = self.root / 'node'
        (self.node / 'bin').mkdir(parents=True)
        self.capture = self.root / 'capture.json'
        fake = self.node / 'bin/node'
        fake.write_text('#!/usr/bin/python3\nimport json,os,sys\nif sys.argv[1:]==["--version"]: print("v24.21.0")\nelse: open('+repr(str(self.capture))+',"w").write(json.dumps({"argv":sys.argv[1:],"env":dict(os.environ)}))\n')
        fake.chmod(0o700)
        self.app = self.root / 'app'
        (self.app / 'server/dist').mkdir(parents=True)
        (self.app / 'web/dist').mkdir(parents=True)
        for name in ['main.js','codex-preview-main.js']:
            (self.app / 'server/dist' / name).write_text('// fixture only\n')
        self.key = self.root / 'key'; self.key.write_bytes(b'x'*32); self.key.chmod(0o600)
        self.approval = self.root / 'ordinary.json'; self.approval.write_text('{}'); self.approval.chmod(0o600)
        self.engine = self.root / 'engine'; self.engine.write_text('#!/bin/sh\nexit 0\n'); self.engine.chmod(0o700)
        self.args = ['bash', str(LAUNCHER), '--node-prefix',str(self.node),'--app-dir',str(self.app),'--data-dir',str(self.root/'data'), '--inference-key-file',str(self.key),'--engine-launcher',str(self.engine)]
        self.ordinary = ['--codex-preview-receipt',str(self.root/'receipt.json'),'--codex-ordinary-entry',str(self.approval),'--codex-ordinary-entry-key',str(self.key)]
    def run_launcher(self, extra, env=None):
        return subprocess.run(self.args+extra,capture_output=True,text=True,env=env,timeout=10)
    def test_only_explicit_paths_and_absent_ticket_forwarded(self):
        paths = {flag:str(self.root/(str(i)+'.absent.json')) for i,flag in enumerate(FLAGS)}
        ambient = dict(os.environ,UNTRUSTED_API_KEY='fixture-secret',AI_HARNESS_CODEX_GENERATION_ONLY_FILE='/ambient',AI_HARNESS_CODEX_CURRENT_FRONTIER_FILE='/ambient',AI_HARNESS_CODEX_GENERATION_ACCEPTANCE_FILE='/ambient',AI_HARNESS_CODEX_IMAGE_GENERATION_QUALIFIED='true')
        extra = self.ordinary + [v for pair in paths.items() for v in pair] + ['--codex-owned-acceptance-policy',str(self.root/'frontier-policy.json')]
        result=self.run_launcher(extra,ambient)
        self.assertEqual(result.returncode,0,result.stderr)
        captured=json.loads(self.capture.read_text())
        for flag,name in FLAGS.items(): self.assertEqual(captured['env'][name],paths[flag])
        self.assertNotIn('UNTRUSTED_API_KEY',captured['env'])
        self.assertNotIn('AI_HARNESS_CODEX_IMAGE_GENERATION_QUALIFIED',captured['env'])
        self.assertEqual(captured['argv'],[str(self.app/'server/dist/codex-preview-main.js'),str(self.root/'receipt.json'),'65536','image-jobs-unqualified',str(self.root/'frontier-policy.json')])
    def test_ambient_paths_never_forwarded(self):
        result=self.run_launcher([],dict(os.environ,**{name:'/ambient' for name in FLAGS.values()}))
        self.assertEqual(result.returncode,0,result.stderr)
        captured=json.loads(self.capture.read_text())
        for name in FLAGS.values(): self.assertEqual(captured['env'][name],'')
        self.assertEqual(captured['argv'],[str(self.app/'server/dist/main.js')])
    def test_preview_and_ordinary_prerequisite(self):
        for flag in FLAGS:
            with self.subTest(flag=flag):
                result=self.run_launcher([flag,str(self.root/'absent')])
                self.assertNotEqual(result.returncode,0)
                self.assertIn('require reviewed Codex preview and ordinary approval/key',result.stderr)
                self.assertFalse(self.capture.exists())
    def test_invalid_duplicate_missing_paths_fail(self):
        for flag in FLAGS:
            for tail in [[flag],[flag,'relative'],[flag,'/a\nb'],[flag,'/a\rb'],[flag,'/a',flag,'/b']]:
                with self.subTest(tail=tail):
                    result=self.run_launcher(self.ordinary+tail)
                    self.assertNotEqual(result.returncode,0)
                    self.assertFalse(self.capture.exists())
    def test_raw_boolean_is_not_an_option(self):
        result=self.run_launcher(self.ordinary+['--codex-generation-enabled'])
        self.assertNotEqual(result.returncode,0)
        self.assertIn('unknown argument',result.stderr)

if __name__ == '__main__': unittest.main()
