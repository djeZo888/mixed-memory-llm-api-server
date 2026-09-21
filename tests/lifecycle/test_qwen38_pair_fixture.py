"""Closed pair fixture source controls; Docker/model/native image NOT_TESTED.

Synthetic collaborators test validation only. Every receipt writer is mocked;
no output here is actual-image evidence and no protected receipt is published.
"""
import ast
import copy
import importlib.util
import io
import json
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tests.lifecycle.test_qwen38_image_fixture import ROOT, FIXTURE, native_result, lifetime, inspected


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, FIXTURE / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


pair = load('q38pair_source_controls', 'run_pair_fixture.py')
child = load('q38pair_inner_controls', 'run_pair_pinned_image.py')


def observed():
    provenance, _ = pair.host.read_provenance(ROOT)
    result = native_result(provenance, pair.CONTEXT)
    result.update(extension_identity=pair.pair_identity(ROOT),
                  model_config_resolution=pair.expected_extension_resolution(provenance))
    return result


def synthetic_receipt():
    result = observed()
    with patch.object(pair.host, 'validate_output_path'), \
            patch.object(pair.host.subprocess, 'run', return_value=SimpleNamespace(
                returncode=0, stdout=json.dumps(inspected()).encode())), \
            patch.object(pair.host, 'run_disposable_fixture', return_value=(SimpleNamespace(
                returncode=0, stdout=json.dumps(result).encode(), stderr=b''), lifetime(pair.CONTEXT))), \
            patch.object(pair.host, 'write_receipt') as writer:
        receipt = pair.run(ROOT, Path('/synthetic/pair.json'))
    if writer.call_count != 1:
        raise AssertionError('synthetic writer not reached')
    return receipt


class ClosedPairFixtureTests(unittest.TestCase):
    def test_only_exact_pair_mode_and_context(self):
        options = pair.parse_options(['--repo', str(ROOT), '--output', '/synthetic/pair.json', '--slot', 'gpu1'])
        self.assertEqual(options.slot, 'gpu1')
        for bad in ('native-pair', '700161', pair.host.EXTENSION_PROFILE):
            with self.subTest(bad=bad), self.assertRaises(pair.host.FixtureError):
                pair.parse_options(['--repo', str(ROOT), '--output', '/synthetic/pair.json', '--slot', bad])
        for bad in ('131072', '262144', '1000000', '700161'):
            with self.subTest(bad=bad), redirect_stdout(io.StringIO()), patch.object(child.inner, 'run_actual') as native:
                self.assertEqual(child.main(['--actual-image', '--repo', '/fixture', '--context', bad, '--slot', 'gpu1']), 2)
                native.assert_not_called()

    def test_pair_mode_uses_exact_wrapper_argv_and_restores_legacy_defaults(self):
        before = pair.host.EXTENSION_CONTEXT, pair.host.EXTENSION_PROFILE, pair.host.docker_command
        with pair.fixture_mode():
            cmd = pair.host.docker_command(ROOT, {}, pair.CONTEXT)
            self.assertIn(pair.INNER, cmd)
            self.assertNotIn(pair.OLD_INNER, cmd)
            self.assertEqual(cmd[-4:], ['--context', '480000', '--slot', 'gpu1'])
            self.assertIn('SGLANG_ALLOW_OVERWRITE_LONGER_CONTEXT_LEN=1', cmd)
            self.assertIn('NVIDIA_VISIBLE_DEVICES=none', cmd)
            self.assertNotIn('--gpus', cmd)
            with self.assertRaises(pair.host.FixtureError):
                pair.host.docker_command(ROOT, {}, 1000000)
        self.assertEqual(before, (pair.host.EXTENSION_CONTEXT, pair.host.EXTENSION_PROFILE, pair.host.docker_command))
        self.assertEqual(pair.host.NATIVE_CONTEXTS, (131072, 262144))

    def test_production_pinned_base_and_bind_variant_reused_without_launch(self):
        launcher = load('q38pair_facade_controls', 'pair_launcher.py')
        argv = launcher.backend_argv(pair.CONTEXT)
        self.assertEqual(argv, launcher.pair.backend_argv(launcher.base, "gpu1"))
        self.assertEqual(argv[argv.index('--context-length') + 1], '480000')
        self.assertEqual(argv[argv.index('--max-total-tokens') + 1], '480000')
        for invalid in (True, 1000000, 700161):
            with self.subTest(invalid=invalid), self.assertRaises(launcher.base.LaunchError):
                launcher.backend_argv(invalid)
        for invalid in ([], launcher.EXPECTED + ['--tp', '2']):
            with self.assertRaises(launcher.base.LaunchError):
                launcher.base.parse_options(invalid)
        with patch.object(launcher.base, 'main', return_value=0) as main:
            self.assertEqual(launcher.main(launcher.EXPECTED), 0)
            main.assert_called_once_with(launcher.EXPECTED)

    def test_pair_native_checks_cover_every_production_auth_check(self):
        tree = ast.parse((ROOT / 'scripts/lifecycle/qwen38.py').read_text())
        production = next(ast.literal_eval(node.value) for node in tree.body if isinstance(node, ast.Assign)
                          and any(isinstance(target, ast.Name) and target.id == 'AUTH_CHECKS' for target in node.targets))
        self.assertEqual(pair.host.CHECKS, production)
        self.assertTrue(all(name in pair.pair_identity(ROOT)['source_sha256'] for name in pair.PAIR_FILES))
        pair.host.read_provenance(ROOT)  # Legacy fixture bytes/pins unchanged.

    def test_source_only_or_old_native_pair_cannot_supply_receipt(self):
        receipt = synthetic_receipt()
        pair.check_pair_receipt(receipt, ROOT)
        self.assertEqual(receipt['kind'], pair.KIND)
        self.assertEqual(receipt['model_execution'], 'NOT_TESTED')
        for key, value in (('status', 'SOURCE_ONLY'), ('status', 'ACCEPTED_FOR_ACTIVATION'),
                           ('kind', 'q38b_actual_image_auth'), ('contexts', [131072, 262144]),
                           ('native_results', []), ('container_lifetimes', []),
                           ('image_identity_verification', 'SELF_REPORTED'),
                           ('model_execution', 'PASS')):
            with self.subTest(key=key, value=value), self.assertRaises(Exception):
                pair.check_pair_receipt({**receipt, key: value}, ROOT)

    def test_all_native_checks_and_exact_source_capacity_are_required(self):
        receipt = synthetic_receipt()
        mutations = [('native_results', 0, check) for check in pair.host.CHECKS]
        mutations += [('extension_identity', 'source_sha256', name) for name in pair.PAIR_FILES]
        mutations += [('model_config_resolution', 'context_len'),
                      ('native_results', 0, 'model_config_resolution', 'hf_context_len'),
                      ('container_lifetimes', 0, 'cleanup')]
        for keys in mutations:
            bad = copy.deepcopy(receipt)
            target = bad
            for key in keys[:-1]:
                target = target[key]
            target[keys[-1]] = 'UNAVAILABLE'
            with self.subTest(keys=keys), self.assertRaises(Exception):
                pair.check_pair_receipt(bad, ROOT)

    def test_failed_native_fixture_never_writes_receipt(self):
        with patch.object(pair.host, 'validate_output_path'), \
                patch.object(pair.host.subprocess, 'run', return_value=SimpleNamespace(
                    returncode=0, stdout=json.dumps(inspected()).encode())), \
                patch.object(pair.host, 'run_disposable_fixture', return_value=(SimpleNamespace(
                    returncode=1, stdout=b'{}', stderr=b''), lifetime(pair.CONTEXT))), \
                patch.object(pair.host, 'write_receipt') as writer:
            with self.assertRaises(pair.host.FixtureError):
                pair.run(ROOT, Path('/synthetic/pair.json'))
            writer.assert_not_called()

    def test_pair_reuses_existing_lifetime_and_exact_child_process_gate(self):
        from tests.lifecycle.test_qwen38_fixture_lifetime import DockerDaemon, OWN_ID, SENTINEL_ID
        class SlotDaemon(DockerDaemon):
            def __call__(self, command, *, timeout):
                # The legacy synthetic daemon parses context from its final
                # token. Production inspect still checks the full slot argv.
                if command[1] == 'create':
                    self_slot = command[-2:]
                    if self_slot != ['--slot', 'gpu1']:
                        raise AssertionError('closed fixture slot not passed')
                    command = command[:-2]
                return super().__call__(command, timeout=timeout)
        for mode in ('success', 'timeout'):
            def mode_process(container):
                container['Config']['Cmd'][3] = pair.INNER
                container['Config']['Cmd'] += ['--slot', 'gpu1']
            daemon = SlotDaemon(mode, policy_mutator=mode_process)
            with self.subTest(mode=mode), pair.fixture_mode():
                if mode == 'success':
                    _, evidence = pair.host.run_disposable_fixture(Path('/reviewed'), {}, pair.CONTEXT, docker=daemon)
                else:
                    with self.assertRaises(pair.host.LifetimeFailure) as caught:
                        pair.host.run_disposable_fixture(Path('/reviewed'), {}, pair.CONTEXT, docker=daemon)
                    evidence = caught.exception.evidence
                self.assertEqual(evidence['cleanup'], 'QUIESCENT_REMOVAL_VERIFIED')
                self.assertNotIn(OWN_ID, daemon.objects)
                self.assertEqual(daemon.objects[SENTINEL_ID], daemon.sentinel)
