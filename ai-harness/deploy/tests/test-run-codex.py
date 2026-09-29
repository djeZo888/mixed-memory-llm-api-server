#!/usr/bin/env python3
"""Reuse existing container ownership/security fixtures for Codex; fake Podman only."""
import importlib.util
import hashlib
import tomllib
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('minimax_launcher_fixture', Path(__file__).with_name('test-run-engine.py'))
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
base.LAUNCHER = Path(__file__).resolve().parents[1] / 'run-codex.sh'
base.REVISION = '064c6b8c737f5b41d171fdda80bd9ef10ad06eb3'
base.IMAGE_ID = 'sha256:d8841743002e16de1f9269a850a2f06a73055688befec4c309778ca8a4c11aad'
# Cached native image label is distinct from the updated host-mounted policy.
base.PATCHSET = 'dd0ff12a651db4cc8521cddb8e5094c5a197ca87cef6b7ec797343da67d9f1ec'

class CodexLauncherContract(base.LauncherContract):
    def assert_catalog_selected_by_container_config_is_mounted(self, run, config_name):
        # Inspect the real launcher's emitted Podman arguments, not a mocked catalog.
        mounts = [run[i+1] for i, value in enumerate(run) if value == '--volume']
        config = tomllib.loads((base.LAUNCHER.parent / 'codex' / config_name).read_text())
        target = config['model_catalog_json']
        self.assertEqual(target, '/opt/sova/codex/models.json')
        matching = [mount for mount in mounts if mount.split(':')[1] == target]
        self.assertEqual(matching, [f'{base.LAUNCHER.parent}/codex/models.json:{target}:ro,rprivate'])

    def test_acp_transport_mounts_and_environment_allowlist(self):
        self.env.update(OPENAI_API_KEY='fixture-never-export', SSH_AUTH_SOCK='/private/ssh', CODEX_HOME='/private/codex', NODE_OPTIONS='--inspect', CONTAINER_HOST='ssh://wrong', HTTP_PROXY='http://wrong')
        request='{"id":1,"method":"initialize"}\n'
        result=self.invoke(text=request)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(result.stdout,request)
        calls=self.calls();run=calls[-3]['argv'];name=run[run.index('--name')+1]
        for c in calls:
            self.assertFalse({'OPENAI_API_KEY','SSH_AUTH_SOCK','CODEX_HOME','NODE_OPTIONS','CONTAINER_HOST','HTTP_PROXY'} & c['env'].keys())
            self.assertNotIn(base.TOKEN,' '.join(c['argv']))
        mounts=[run[i+1] for i,v in enumerate(run) if v=='--volume']
        source = base.LAUNCHER.parent.parent
        self.assertEqual(mounts,[
            f'{self.profile}:{self.profile}:rw,rprivate',
            f'{self.workspace}:{self.workspace}:rw,rprivate',
            f'{source}/tools/image/image-mcp.mjs:/opt/ai-harness/tools/image/image-mcp.mjs:ro,rprivate',
            f'{source}/tools/image/image.mjs:/opt/ai-harness/tools/image/image.mjs:ro,rprivate',
            f'{base.LAUNCHER.parent}/codex/config.toml:{self.profile}/codex-home/config.toml:ro,rprivate',
            f'{base.LAUNCHER.parent}/codex/models.json:/opt/sova/codex/models.json:ro,rprivate',
            f'{base.LAUNCHER.parent}/codex/skills/sova-local-tools:{self.profile}/codex-home/skills/sova-local-tools:ro,rprivate',
        ])
        self.assert_catalog_selected_by_container_config_is_mounted(run, 'config.toml')
        env=[run[i+1] for i,v in enumerate(run) if v=='--env']
        self.assertIn(f'CODEX_HOME={self.profile}/codex-home',env)
        self.assertIn(f'HOME={self.profile}/codex-home/home',env)
        self.assertFalse(any('MINIMAX' in x or 'OPENAI' in x for x in env))
        for flag in ['--pull=never','--read-only','--init','--cgroup-parent=aiharnesstasks.slice','no-new-privileges']:self.assertIn(flag,run)
        self.assertEqual(calls[-2]['argv'],['--remote=false','rm','--force','--time','20','--ignore',name])
        self.assertEqual(calls[-1]['argv'],['--remote=false','container','exists',name])
    def test_image_catalog_requires_trusted_launcher_flag(self):
        result=self.invoke(['--profile-dir',str(self.profile),'--workspace',str(self.workspace),'--image-jobs-qualified'])
        self.assertEqual(result.returncode,0,result.stderr)
        run=self.calls()[-3]['argv']
        self.assertIn(f'{base.LAUNCHER.parent}/codex/config-image-jobs.toml:{self.profile}/codex-home/config.toml:ro,rprivate',run)
        self.assertNotIn('--image-jobs-qualified',run)
        self.assert_catalog_selected_by_container_config_is_mounted(run, 'config-image-jobs.toml')
    def test_symlinked_engine_state_rejected(self):
        (self.profile/'codex-home').symlink_to(self.home,target_is_directory=True)
        result=self.invoke();self.assertEqual(result.returncode,64)
        self.assertFalse(any('run' in c['argv'] for c in self.calls()))
    def test_symlinked_engine_home_rejected(self):
        (self.profile/'codex-home').mkdir()
        (self.profile/'codex-home'/'home').symlink_to(self.home,target_is_directory=True)
        self.assertEqual(self.invoke().returncode,64)
        self.assertFalse(any('run' in c['argv'] for c in self.calls()))
    def test_help_does_not_start_podman(self):
        result=self.invoke(['--help']);self.assertEqual(result.returncode,0)
        self.assertIn('private AppServer stdio',result.stdout);self.assertFalse(self.calls())

if __name__=='__main__': unittest.main()
