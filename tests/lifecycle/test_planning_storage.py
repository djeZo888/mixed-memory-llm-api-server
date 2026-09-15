"""Read-only planner boundary: explicit offline assumptions never authorize live I/O."""
from contextlib import redirect_stdout, redirect_stderr
import importlib.machinery
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
loader = importlib.machinery.SourceFileLoader('llmctl_planning_fixture', str(ROOT / 'scripts/llmctl'))
spec = importlib.util.spec_from_loader(loader.name, loader)
llmctl = importlib.util.module_from_spec(spec)
loader.exec_module(llmctl)


class PlanningStorageTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {
            'LLMCTL_CONFIG_ROOT': '/untrusted/configs',
            'LLMCTL_DATA_ROOT': '/untrusted/data',
            'LLMCTL_MODELS_ROOT': '/untrusted/models',
            'LLMCTL_STATE_DIR': '/untrusted/state',
            'LLMCTL_ACTIVE_DIR': '/untrusted/active',
            'LLMCTL_INSTANCE': '/untrusted/instance.json',
            'LLMCTL_SKIP_HOST_CHECKS': '1',
        })
        self.env.start()
        self.addCleanup(self.env.stop)
        llmctl.OFFLINE = False
        llmctl.CONFIG_ROOT = ROOT / 'configs'

    def invoke(self, *args):
        output, error = io.StringIO(), io.StringIO()
        with redirect_stdout(output), redirect_stderr(error):
            code = llmctl.main(list(args))
        return code, output.getvalue(), error.getvalue()

    def test_live_metadata_ignores_config_override(self):
        code, output, error = self.invoke('validate')
        self.assertEqual(code, 0, error)
        self.assertEqual(llmctl.CONFIG_ROOT, ROOT / 'configs')
        self.assertNotIn('/untrusted', output)

    def test_live_env_uses_validated_registry_not_environment(self):
        registered = {'data': {'path': '/srv/ai'}, 'models': {'path': '/mnt/weights'}}
        with patch.object(llmctl.subprocess, 'run', return_value=SimpleNamespace(
                returncode=0, stdout=json.dumps(registered))) as run:
            code, output, error = self.invoke('env')
        self.assertEqual(code, 0, error)
        self.assertIn('DATA_ROOT=/srv/ai\n', output)
        self.assertIn('MODELS_ROOT=/mnt/weights\n', output)
        self.assertIn('STATE_ROOT=/srv/ai/services/llm-manager/state\n', output)
        self.assertNotIn('/untrusted', output)
        args, kwargs = run.call_args
        self.assertEqual(args[0][:3], ['/usr/bin/python3', '-I', '-B'])
        self.assertEqual(args[0][-1], '--json')
        self.assertEqual(kwargs['env'], {'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LC_ALL': 'C'})

    def test_missing_registration_never_falls_back_to_default_or_environment(self):
        with patch.object(llmctl.subprocess, 'run', return_value=SimpleNamespace(
                returncode=1, stdout='host details that must not leak')):
            code, output, error = self.invoke('env')
        self.assertEqual(code, 1)
        self.assertEqual(output, '')
        self.assertNotIn('host details', error)
        self.assertNotIn('/untrusted', error)

    def test_legacy_skip_variable_cannot_skip_live_checks(self):
        with patch.object(llmctl, 'configure_live_paths') as binding, \
                patch.object(llmctl, 'run_check') as check:
            llmctl.host_checks('download')
        binding.assert_called_once_with()
        self.assertEqual([call.args[0] for call in check.call_args_list],
                         [llmctl.REQUIRE_DATA, llmctl.ROOT_GUARD])

    def test_offline_is_explicit_and_prints_unverified_assumptions(self):
        with patch.object(llmctl.subprocess, 'run', side_effect=AssertionError('offline host I/O')):
            code, output, error = self.invoke('env', '--offline')
        self.assertEqual(code, 0, error)
        self.assertIn('unverified planning assumptions; no live authorization', output)
        self.assertIn('DATA_ROOT=/untrusted/data\n', output)
        self.assertIn('MODELS_ROOT=/untrusted/models\n', output)
        self.assertIn('STATE_ROOT=/untrusted/state\n', output)

    def test_offline_cannot_enter_a_live_lifecycle_command(self):
        with patch.object(llmctl.subprocess, 'run', side_effect=AssertionError('unexpected host I/O')):
            for args in [('activate', 'qwen3-coder-next', '--offline'),
                         ('activate', 'qwen3-coder-next', '--offline', '--dry-run')]:
                code, output, error = self.invoke(*args)
                self.assertEqual(code, 1)
                self.assertEqual(output, '')
                self.assertIn('--runtime and --dry-run', error)


if __name__ == '__main__':
    unittest.main()
