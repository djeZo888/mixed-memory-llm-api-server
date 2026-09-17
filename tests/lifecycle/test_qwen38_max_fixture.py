"""Q38MAX finite fixture controls and pinned context-resolution source tests.

All collaborators are synthetic. No Docker/native image/model/server runs and
no receipt is published. Source-method resolution is not installed-image proof.
Set Q38NEXT_UPSTREAM_ROOT to the existing hash-pinned SGLang source directory.
"""
import ast
import copy
import hashlib
import json
import logging
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tests.lifecycle.test_qwen38_image_fixture import ROOT, FIXTURE, host, inner, native_result


class ExtensionFixtureControls(unittest.TestCase):
    def test_explicit_extension_selection_and_native_default_pair(self):
        options = host.parse_options(['--repo', str(ROOT), '--output', '/private/proof.json'])
        self.assertEqual(options.profile, 'native-pair')
        self.assertEqual(host.NATIVE_CONTEXTS, (131072, 262144))
        options = host.parse_options(['--repo', str(ROOT), '--output', '/private/proof.json',
                                      '--profile', host.EXTENSION_PROFILE])
        self.assertEqual(options.profile, host.EXTENSION_PROFILE)
        for invalid in ('all', '1000000', 'qwen38-27b-1000000-yarn4-tp1-fp8kv'):
            with self.subTest(invalid=invalid), self.assertRaises(host.FixtureError):
                host.parse_options(['--repo', str(ROOT), '--output', '/private/proof.json',
                                    '--profile', invalid])
        self.assertEqual(inner.parse_options(['--actual-image', '--repo', '/fixture',
                                               '--context', '1000000']).context, 1000000)

    def test_extension_command_adds_only_reviewed_environment(self):
        cache = {'HF_HOME': '/cache/huggingface'}
        native = host.docker_command(ROOT, cache, 262144)
        extension = host.docker_command(ROOT, cache, 1000000)
        approved = 'SGLANG_ALLOW_OVERWRITE_LONGER_CONTEXT_LEN=1'
        self.assertNotIn(approved, native)
        self.assertEqual(extension.count(approved), 1)
        self.assertEqual(extension[-2:], ['--context', '1000000'])
        self.assertNotIn('--gpus', extension)  # Model execution remains synthetic.
        self.assertEqual(extension[extension.index('--ulimit') + 1], 'core=1:1')
        for bad in (True, 1048576, 999999):
            with self.subTest(context=bad), self.assertRaises(host.FixtureError):
                host.docker_command(ROOT, cache, bad)

    def test_extension_reuses_owned_lifetime_cleanup_on_success_timeout_and_environment_drift(self):
        from tests.lifecycle.test_qwen38_fixture_lifetime import DockerDaemon, OWN_ID, SENTINEL_ID
        for mode in ('success', 'timeout', 'missing_extension_environment'):
            mutate = None
            if mode == 'missing_extension_environment':
                def mutate(container):
                    container['Config']['Env'] = [value for value in container['Config']['Env']
                        if not value.startswith('SGLANG_ALLOW_OVERWRITE_LONGER_CONTEXT_LEN=')]
            daemon = DockerDaemon(mode if mutate is None else 'success', policy_mutator=mutate)
            with self.subTest(mode=mode):
                if mode == 'success':
                    _, evidence = host.run_disposable_fixture(Path('/reviewed'), {}, 1000000, docker=daemon)
                else:
                    with self.assertRaises(host.LifetimeFailure) as caught:
                        host.run_disposable_fixture(Path('/reviewed'), {}, 1000000, docker=daemon)
                    evidence = caught.exception.evidence
                self.assertEqual(evidence['cleanup'], 'QUIESCENT_REMOVAL_VERIFIED')
                self.assertNotIn(OWN_ID, daemon.objects)
                self.assertEqual(daemon.objects[SENTINEL_ID], daemon.sentinel)
                if mutate is not None:
                    self.assertFalse(daemon.attached)

    def test_extension_identity_drift_and_native_receipt_refused(self):
        provenance = json.loads((FIXTURE / 'provenance.json').read_text())
        result = native_result(provenance, 1000000)
        with self.assertRaisesRegex(host.FixtureError, 'extension_identity_mismatch'):
            host.check_native_result(result, provenance, 1000000, repo=ROOT)
        result['extension_identity'] = host.extension_identity(ROOT, provenance)
        result['model_config_resolution'] = host.expected_extension_resolution(provenance)
        host.check_native_result(result, provenance, 1000000, repo=ROOT)
        for path, wrong in (
                (('extension_identity', 'profile_id'), 'qwen38-27b-256k'),
                (('extension_identity', 'profile_sha256'), '0' * 64),
                (('extension_identity', 'config_sha256'), '0' * 64),
                (('extension_identity', 'backend_argv_sha256'), '0' * 64),
                (('extension_identity', 'extension_environment'), {}),
                (('model_config_resolution', 'context_len'), 262144),
                (('model_config_resolution', 'hf_context_len'), 262144),
                (('model_config_resolution', 'source_sha256'), '0' * 64),
                (('model_config_resolution', 'dtype'), 'torch.float8_e4m3fn'),
                (('model_config_resolution', 'status'), 'PASS_SYNTHETIC_SOURCE')):
            bad = copy.deepcopy(result)
            bad[path[0]][path[1]] = wrong
            with self.subTest(path=path), self.assertRaises(host.FixtureError):
                host.check_native_result(bad, provenance, 1000000, repo=ROOT)
        for wrong in (1, 'true'):
            bad = copy.deepcopy(result)
            bad['model_config_resolution']['rope_parameters']['mrope_interleaved'] = wrong
            with self.assertRaises(host.FixtureError):
                host.check_native_result(bad, provenance, 1000000, repo=ROOT)
        with self.assertRaisesRegex(host.FixtureError, 'extension_repository_required'):
            host.check_native_result(result, provenance, 1000000)

    def test_extension_environment_revalidated_before_cache_or_native_import(self):
        launcher = host.source_module('q38max_fixture_preflight_launcher',
                                      ROOT / 'scripts/runtime/sglang38_file_auth.py')
        for env in ({**launcher.CACHE_ENVIRONMENT},
                    {**launcher.CACHE_ENVIRONMENT, **launcher.EXTENSION_ENVIRONMENT,
                     'SGLANG_UNREVIEWED': '1'}):
            with patch.dict(os.environ, env, clear=True), \
                    patch.object(inner, 'verify_sources', return_value=Path(launcher.__file__)), \
                    patch.object(inner, 'run_cache_probe') as cache, \
                    patch.object(launcher.importlib.metadata, 'version', return_value='0.5.19'), \
                    patch.object(launcher.importlib.metadata, 'entry_points', return_value={}):
                with self.assertRaisesRegex(Exception, '^launch_environment_invalid$'):
                    inner.run_actual(ROOT, 'all', None, 1000000)
                cache.assert_not_called()

    def test_extension_cache_probe_has_native_environment_then_restores_extension(self):
        launcher = host.source_module('q38max_fixture_cache_launcher',
                                      ROOT / 'scripts/runtime/sglang38_file_auth.py')
        env = {**launcher.CACHE_ENVIRONMENT, **launcher.EXTENSION_ENVIRONMENT}
        cache_env = []
        original = __import__
        def stop_at_torch(name, *args, **kwargs):
            if name == 'torch':
                self.assertEqual(dict(os.environ), env)
                raise RuntimeError('synthetic_stop_before_native_import')
            return original(name, *args, **kwargs)
        def cache(_repo):
            cache_env.append(dict(os.environ))
            return {}
        with patch.dict(os.environ, env, clear=True), \
                patch.object(inner, 'verify_sources', return_value=Path(launcher.__file__)), \
                patch.object(inner, 'run_cache_probe', side_effect=cache), \
                patch.object(launcher.importlib.metadata, 'version', return_value='0.5.19'), \
                patch.object(launcher.importlib.metadata, 'entry_points', return_value={}), \
                patch('builtins.__import__', side_effect=stop_at_torch):
            with self.assertRaisesRegex(RuntimeError, '^synthetic_stop_before_native_import$'):
                inner.run_actual(ROOT, 'all', None, 1000000)
            self.assertEqual(dict(os.environ), env)
        self.assertEqual(cache_env, [launcher.CACHE_ENVIRONMENT])


class PinnedExtensionModelConfig(unittest.TestCase):
    """Run unchanged upstream construction/context methods with explicit fakes.

    The HF parser only reads pinned JSON into synthetic config containers; model
    shape/quantization classifications are synthetic. Actual override application,
    ServerArgs routing, constructor and context derivation are source-executed.
    """
    @classmethod
    def setUpClass(cls):
        root = os.environ.get('Q38NEXT_UPSTREAM_ROOT')
        if root is None:
            raise AssertionError('Q38NEXT_UPSTREAM_ROOT is required for pinned source tests')
        provenance = json.loads((FIXTURE / 'provenance.json').read_text())
        cls.trees = {}
        for name in ('srt/configs/model_config.py', 'srt/utils/hf_transformers/config.py',
                     'srt/utils/hf_transformers/common.py'):
            raw = (Path(root) / name).read_bytes()
            pin = provenance['sources'][name]
            if len(raw) != pin['bytes'] or hashlib.sha256(raw).hexdigest() != pin['sha256']:
                raise AssertionError('pinned source identity mismatch: ' + name)
            cls.trees[name] = ast.parse(raw, filename=name)
        cls.metadata = json.loads((FIXTURE / 'qwen38_config.json').read_text())
        cls.launcher = host.source_module('q38max_source_launcher',
                                         ROOT / 'scripts/runtime/sglang38_file_auth.py')

    @staticmethod
    def execute(nodes, namespace):
        module = ast.Module(body=[ast.ImportFrom(module='__future__',
            names=[ast.alias(name='annotations')], level=0), *copy.deepcopy(nodes)], type_ignores=[])
        ast.fix_missing_locations(module)
        exec(compile(module, 'hash-verified-upstream-source', 'exec'), namespace)

    def model_class(self):
        class SyntheticConfig(SimpleNamespace):
            def update(self, values):
                self.__dict__.update(copy.deepcopy(values))
        def parse(_model, **_kwargs):
            data = copy.deepcopy(self.metadata)
            data['text_config'] = SyntheticConfig(**data['text_config'])
            return SyntheticConfig(**data)
        false = lambda *_args, **_kwargs: False
        namespace = {'copy': copy, 'json': json, 'logger': logging.getLogger('q38max.synthetic'),
            'ModelImpl': SimpleNamespace(AUTO='auto', TRANSFORMERS='transformers'),
            'PretrainedConfig': SyntheticConfig, 'check_gguf_file': false,
            'resolve_runai_obj_uri': lambda value: value, 'is_remote_url': false,
            'is_mistral_model': false, 'get_model_config_parser': lambda _name: SimpleNamespace(parse=parse),
            'get_hf_text_config': lambda config: config.text_config,
            'get_generation_config': lambda *_args, **_kwargs: None,
            'resolve_embedding_model_spec': lambda *_args, **_kwargs: None,
            '_quant_config_to_dict': lambda value: value,
            '_get_and_verify_dtype': lambda _config, dtype: 'torch.' + dtype,
            'resolving_view': lambda value: value,
            'is_in_ci': false,
            'envs': SimpleNamespace(SGLANG_ALLOW_OVERWRITE_LONGER_CONTEXT_LEN=SimpleNamespace(
                get=lambda: os.environ.get('SGLANG_ALLOW_OVERWRITE_LONGER_CONTEXT_LEN') == '1'))}
        for name in ('is_embedding_gemma', 'is_deepseek_v4', 'is_multimodal_model', 'is_audio_model',
                     'is_multimodal_chunked_prefill_supported', 'is_encoder_decoder_model',
                     'is_local_attention_model', 'is_piecewise_cuda_graph_disabled_model',
                     'is_multimodal_piecewise_cuda_graph_supported',
                     'is_multimodal_breakable_cuda_graph_supported'):
            namespace[name] = false
        namespace['is_generation_model'] = lambda *_args: True
        common = self.trees['srt/utils/hf_transformers/common.py']
        keys = next(node for node in common.body if isinstance(node, ast.Assign)
                    and any(isinstance(target, ast.Name) and target.id == 'CONTEXT_LENGTH_KEYS'
                            for target in node.targets))
        context = next(node for node in common.body if isinstance(node, ast.FunctionDef)
                       and node.name == 'get_context_length')
        get_config = copy.deepcopy(next(node for node in self.trees[
            'srt/utils/hf_transformers/config.py'].body if isinstance(node, ast.FunctionDef)
                                        and node.name == 'get_config'))
        get_config.decorator_list = []  # Synthetic cache collaborator; function body is unchanged.
        model = copy.deepcopy(next(node for node in self.trees['srt/configs/model_config.py'].body
                                   if isinstance(node, ast.ClassDef) and node.name == 'ModelConfig'))
        model.body = [node for node in model.body if isinstance(node, ast.FunctionDef)
                      and node.name in ('__init__', 'from_server_args', '_derive_context_length')]
        self.execute([keys, context, get_config, model], namespace)
        cls = namespace['ModelConfig']
        for name in ('_validate_quantize_and_serve_config', '_maybe_pull_model_for_runai',
                     '_maybe_pull_model_tokenizer_from_remote', '_config_draft_model',
                     '_get_sliding_window_size', '_derive_model_shapes', '_derive_hybrid_model',
                     '_verify_quantization', '_verify_dual_chunk_attention_config', '_get_hf_eos_token_id'):
            setattr(cls, name, lambda *_args: None)
        return cls

    def args(self, context=1000000, override=None):
        return SimpleNamespace(model_path='/synthetic-pinned-metadata', trust_remote_code=False,
            revision=None, context_length=context, json_model_override_args=(
                self.launcher.EXTENSION_OVERRIDE_JSON if override is None else override),
            is_embedding=False, enable_multimodal=False, dtype='bfloat16', quantization='fp8',
            model_impl='auto', sampling_defaults='openai', quantize_and_serve=False,
            decrypted_config_file=None, enable_multi_layer_eagle=False, language_only=False,
            language_model_only=False, encoder_only=False, disable_hybrid_swa_memory=False,
            model_config_parser='auto', speculative_algorithm=None)

    def test_genuine_modelconfig_resolves_context_and_nested_yarn_under_synthetic_collaborators(self):
        cls = self.model_class()
        with patch.dict(os.environ, self.launcher.EXTENSION_ENVIRONMENT, clear=True):
            resolved = cls.from_server_args(self.args())
        self.assertEqual(resolved.context_len, 1000000)
        self.assertEqual(resolved.hf_config.context_len, 1000000)
        self.assertEqual(resolved.hf_text_config.max_position_embeddings, 262144)
        self.assertEqual(resolved.hf_text_config.rope_parameters, host.EXTENSION_ROPE_PARAMETERS)
        self.assertEqual(resolved.hf_text_config.hidden_size, 5120)
        self.assertEqual(resolved.dtype, 'torch.bfloat16')

    def test_genuine_context_derivation_refuses_missing_extension_environment(self):
        cls = self.model_class()
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, 'SGLANG_ALLOW_OVERWRITE_LONGER_CONTEXT_LEN=1'):
                cls.from_server_args(self.args())
            native = cls.from_server_args(self.args(context=262144, override='{}'))
        self.assertEqual(native.context_len, 262144)
        self.assertEqual(native.hf_text_config.rope_parameters['rope_type'], 'default')


if __name__ == '__main__':
    unittest.main()
