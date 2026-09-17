"""Synthetic worker contracts against hash-verified pinned SGLang source.

Set Q38NEXT_UPSTREAM_ROOT to a separate checkout/download of the primary
files below (paths are relative to python/sglang), and Q38FIN_FLASHINFER_ROOT to
the pinned FlashInfer package directory. Existing files use the
committed provenance; the additional serving hook has an explicit source pin.
Only the selected Python definitions run, with explicit synthetic dependencies.
No installed SGLang, native library, listener, process, model or key is used.
These tests cannot establish actual-image fixture or model acceptance.
"""
import ast
from contextlib import contextmanager
import copy
import dataclasses
import hashlib
import importlib.util
import inspect
import json
import logging
import os
from pathlib import Path
import pickle
import re
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from tests.lifecycle.test_sglang38_file_auth import (
    App, args_fixture, cli, launcher, synthetic_dependencies,
)
from tests.lifecycle.test_qwen38_image_fixture import inner


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests/lifecycle/sglang38_fixture/run_pinned_image.py"
PROVENANCE = json.loads(FIXTURE.with_name("provenance.json").read_text())
REVISION = "0bcd822377da7b5718e674eaf9c870d349424dd1"
SOURCE_FILES = (
    "launch_server.py", "srt/entrypoints/engine.py",
    "srt/entrypoints/http_server.py", "srt/server_args.py",
    "srt/runtime_context.py", "srt/utils/auth.py",
    "srt/arg_groups/pipeline.py", "srt/arg_groups/serving_hook.py", "srt/environ.py",
)


def definition(tree, name):
    matches = [node for node in ast.walk(tree)
               if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name == name]
    if len(matches) != 1:
        raise AssertionError("pinned contract definition is missing or ambiguous")
    return copy.deepcopy(matches[0])


def execute_definitions(nodes, namespace, filename):
    """Execute exact definitions only; imports/default dependencies stay synthetic."""
    module = ast.Module(body=[ast.ImportFrom(module="__future__", names=[
        ast.alias(name="annotations")], level=0), *nodes], type_ignores=[])
    ast.fix_missing_locations(module)
    exec(compile(module, filename, "exec"), namespace)


class PinnedNativeLaunchContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = os.environ.get("Q38NEXT_UPSTREAM_ROOT")
        if root is None:
            raise AssertionError("source-worker contracts require Q38NEXT_UPSTREAM_ROOT")
        source_root = Path(root)
        if not source_root.is_dir():
            raise AssertionError("explicit pinned upstream source directory is unavailable")
        if PROVENANCE["source_revision"] != REVISION:
            raise AssertionError("unexpected installed source revision")
        cls.trees = {}
        for name in SOURCE_FILES:
            content = (source_root / name).read_bytes()
            expected_url = (
                f"https://raw.githubusercontent.com/sgl-project/sglang/{REVISION}"
                f"/python/sglang/{name}"
            )
            pin = (dict(bytes=36757, sha256="396ff8562ae865550cf3ebd9617f6ac7a31b4cc133d949cf2290119732570a93",
                        url=expected_url) if name == "srt/arg_groups/serving_hook.py"
                   else PROVENANCE["sources"][name])
            if (len(content) != pin["bytes"]
                    or hashlib.sha256(content).hexdigest() != pin["sha256"]
                    or pin["url"] != expected_url):
                raise AssertionError("pinned primary source identity mismatch: " + name)
            cls.trees[name] = ast.parse(content, filename=name)
        cls.fixture_tree = ast.parse(FIXTURE.read_text())
        flashinfer_root = os.environ.get("Q38FIN_FLASHINFER_ROOT")
        if flashinfer_root is None:
            raise AssertionError("source-worker contracts require Q38FIN_FLASHINFER_ROOT")
        content = (Path(flashinfer_root) / "triton/__init__.py").read_bytes()
        # FlashInfer 69ff11fc4954396d98326656dc85debd2223f637, version 0.6.18.
        if hashlib.sha256(content).hexdigest() != "ae0d97f7ca56c142787f0bfd127e2bdb45d21613c033beea2ab0c70dd14ed4b2":
            raise AssertionError("pinned FlashInfer import source identity mismatch")
        cls.flashinfer_tree = ast.parse(content, filename="flashinfer/triton/__init__.py")

    def flashinfer_import_hook(self, release=13):
        """Exact pinned function and import-time call; ptxas I/O is synthetic."""
        name = "_patch_triton_ptxas_blackwell"
        calls = [node for node in self.flashinfer_tree.body if isinstance(node, ast.Expr)
                 and isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name)
                 and node.value.func.id == name]
        self.assertEqual(len(calls), 1)
        namespace = {"os": os, "re": re,
            "shutil": SimpleNamespace(which=Mock(return_value="/synthetic/cuda/bin/ptxas")),
            "subprocess": SimpleNamespace(STDOUT=-2, CalledProcessError=RuntimeError,
                check_output=Mock(return_value=f"ptxas: release {release}.0".encode()))}
        def invoke():
            execute_definitions([definition(self.flashinfer_tree, name), copy.deepcopy(calls[0])],
                                namespace, "pinned/flashinfer/triton/__init__.py")
        return invoke

    def test_pinned_flashinfer_import_reproduces_cache_prefix_preflight_failure(self):
        for release in (12, 13):
            with self.subTest(synthetic_cuda_release=release), \
                    patch.dict(os.environ, launcher.CACHE_ENVIRONMENT, clear=True), \
                    patch.object(launcher.importlib.metadata, "version", return_value="0.5.19"), \
                    patch.object(launcher.importlib.metadata, "entry_points", return_value={}):
                launcher.validate_environment()
                before = dict(os.environ)
                self.flashinfer_import_hook(release)()
                self.assertEqual(set(os.environ) - set(before),
                    {"TRITON_PTXAS_BLACKWELL_PATH"} if release == 13 else set())
                if release == 13:
                    # This is exactly the refused-prefix branch, not SGLANG.
                    with self.assertRaisesRegex(launcher.LaunchError, "^launch_environment_invalid$"):
                        launcher.validate_environment()
                else:
                    launcher.validate_environment()

    def test_explicit_invalid_launch_snapshot_still_fails_with_independent_operands(self):
        for name in ("TRITON_PTXAS_BLACKWELL_PATH", "HF_TOKEN", "SGLANG_UNREVIEWED"):
            with self.subTest(name=name), \
                    patch.dict(os.environ, launcher.CACHE_ENVIRONMENT, clear=True), \
                    patch.object(launcher.importlib.metadata, "version", return_value="0.5.19"), \
                    patch.object(launcher.importlib.metadata, "entry_points", return_value={}), \
                    patch.object(inner.os, "write"), patch.object(launcher.LOGGER, "error"):
                invalid = {**os.environ, name: "synthetic-unreviewed"}
                with self.assertRaises(inner.FixtureFailure) as caught:
                    inner.checked_launch(launcher, cli(), [], [], "synthetic-contract-key", invalid)
                self.assertEqual(caught.exception.launch_failure, {
                    "result": 1, "captured": 0, "engine_calls": 0,
                    "first_exception_class": "LaunchError"})
                self.assertEqual(dict(os.environ), launcher.CACHE_ENVIRONMENT)

    def test_actual_scenario_validates_entry_before_first_native_import(self):
        real_import = __import__
        class NativeBoundary(Exception):
            pass
        for inherited_override in (False, True):
            env = dict(launcher.CACHE_ENVIRONMENT)
            if inherited_override:
                env["TRITON_PTXAS_BLACKWELL_PATH"] = "/synthetic/unreviewed/ptxas"
            reached = []
            def stop_at_native(name, *args, **kwargs):
                if name == "torch":
                    reached.append(name)
                    raise NativeBoundary("synthetic_stop_before_native_import")
                return real_import(name, *args, **kwargs)
            with self.subTest(inherited_override=inherited_override), \
                    patch.dict(os.environ, env, clear=True), \
                    patch.object(inner, "verify_sources", return_value=Path(launcher.__file__)), \
                    patch.object(inner, "run_cache_probe", return_value={}), \
                    patch.object(launcher.importlib.metadata, "version", return_value="0.5.19"), \
                    patch.object(launcher.importlib.metadata, "entry_points", return_value={}), \
                    patch("builtins.__import__", side_effect=stop_at_native):
                expected = "launch_environment_invalid" if inherited_override else "synthetic_stop_before_native_import"
                with self.assertRaisesRegex(Exception, "^" + expected + "$"):
                    inner.run_actual(ROOT, "all", None)
                self.assertEqual(reached, [] if inherited_override else ["torch"])

    def port_args_type(self):
        namespace = {"dataclasses": dataclasses, "__name__": __name__}
        execute_definitions([definition(self.trees["srt/server_args.py"], "PortArgs")],
                            namespace, "pinned/srt/server_args.py")
        # Dataclass pickles need the exact synthetic class identity to be visible.
        globals()["PortArgs"] = namespace["PortArgs"]
        return namespace["PortArgs"]

    def http_namespace(self, args, *, engine=None, uvicorn=None):
        app = App()
        app.routes.append(SimpleNamespace(path="/__synthetic/admin-force"))
        serving = SimpleNamespace(host=args.host, port=args.port, skip_server_warmup=False)
        namespace = {
            "__name__": __name__, "dataclasses": dataclasses,
            "Engine": SimpleNamespace(_launch_subprocesses=engine), "app": app,
            "envs": SimpleNamespace(SGLANG_RUST_SERVER=SimpleNamespace(get=lambda: False),
                                    SGLANG_TIMEOUT_KEEP_ALIVE=SimpleNamespace(get=lambda: 5)),
            "get_serving": lambda: serving,
            "get_observability": lambda: SimpleNamespace(
                enable_metrics=False, log_level_http=None, log_level="warning"),
            "get_model": lambda: SimpleNamespace(model_path="/models"),
            "init_tokenizer_manager": Mock(name="synthetic_init_tokenizer"),
            "run_scheduler_process": Mock(name="synthetic_scheduler"),
            "run_detokenizer_process": Mock(name="synthetic_detokenizer"),
            "_execute_server_warmup": Mock(name="synthetic_default_warmup"),
            "_freeze_gc_after_server_warmup": Mock(name="synthetic_freeze_gc"),
            "app_has_admin_force_endpoints": lambda app: True,
            "set_uvicorn_logging_configs": Mock(name="synthetic_logging_config"),
            "uvicorn": SimpleNamespace(run=uvicorn),
            "logger": logging.getLogger("q38next.synthetic.contract"),
            "ServerStatus": SimpleNamespace(Starting="starting", Up="up"),
        }
        tree = self.trees["srt/entrypoints/http_server.py"]
        execute_definitions([definition(tree, name) for name in (
            "_GlobalState", "set_global_state", "_wait_and_warmup",
            "_setup_and_run_http_server", "launch_server")],
            namespace, "pinned/srt/entrypoints/http_server.py")
        return namespace

    def test_engine_signature_and_six_value_return_match_fixture_call(self):
        node = definition(self.trees["srt/entrypoints/engine.py"], "_launch_subprocesses")
        self.assertEqual([arg.arg for arg in node.args.args], [
            "cls", "server_args", "init_tokenizer_manager_func", "run_scheduler_process_func",
            "run_detokenizer_process_func", "port_args", "placement_group"])
        self.assertEqual([ast.literal_eval(value) for value in node.args.defaults], [None, None])
        returns = [item for item in node.body if isinstance(item, ast.Return)]
        self.assertEqual(len(returns), 1)
        self.assertTrue(all(isinstance(item.value, ast.Tuple) and len(item.value.elts) == 6
                            for item in ast.walk(node) if isinstance(item, ast.Return)))
        self.assertEqual([ast.unparse(value) for value in returns[0].value.elts], [
            "tokenizer_manager", "template_manager", "port_args", "scheduler_init_result",
            "subprocess_watchdog", "weight_cache_daemon_procs"])
        # Signature-only binding never executes Engine or a scheduler process.
        node.body = [ast.Pass()]
        node.decorator_list = []
        namespace = {}
        execute_definitions([node], namespace, "pinned/engine-signature-only.py")
        signature = inspect.signature(namespace["_launch_subprocesses"])
        call = next(item for item in ast.walk(definition(
            self.trees["srt/entrypoints/http_server.py"], "launch_server"))
            if isinstance(item, ast.Call) and ast.unparse(item.func) == "Engine._launch_subprocesses")
        keywords = {item.arg: object() for item in call.keywords}
        signature.bind(object(), **keywords)
        with self.assertRaises(TypeError):
            signature.bind(object(), server_args=object())

    def test_exact_port_args_eight_required_fields_and_optional_defaults(self):
        ports = self.port_args_type()
        signature = inspect.signature(ports)
        self.assertEqual(list(signature.parameters), [
            "tokenizer_ipc_name", "scheduler_input_ipc_name", "detokenizer_ipc_name",
            "nccl_port", "rpc_ipc_name", "metrics_ipc_name", "tokenizer_worker_ipc_name",
            "decoupled_spec_ipc_config", "load_collector_ipc_name", "instance_id"])
        values = ("ipc:///cache/tokenizer", "ipc:///cache/scheduler",
                  "ipc:///cache/detokenizer", 29999, "ipc:///cache/rpc",
                  "ipc:///cache/metrics", None, None)
        instance = ports(*values)
        self.assertEqual(instance.load_collector_ipc_name, "")
        self.assertEqual(instance.instance_id, "")
        self.assertEqual(dataclasses.asdict(pickle.loads(pickle.dumps(instance))),
                         dataclasses.asdict(instance))
        with self.assertRaises(TypeError):
            ports(*values[:-1])

    def test_publish_resolves_before_installing_same_record_under_tokenizer_role(self):
        events = []
        args = SimpleNamespace(resolve_once=lambda: events.append("resolve"))
        context = SimpleNamespace(overrides_log=lambda: [],
            set_server_args=lambda value: events.append(("set", value)))
        namespace = {"_ROLE_NS_MODE": "enforce", "ROLE_NAMESPACE_SETS": {"tokenizer": None},
                     "_CONTEXT": context}
        execute_definitions([definition(self.trees["srt/runtime_context.py"], "publish")],
                            namespace, "pinned/srt/runtime_context.py")
        self.assertIs(namespace["publish"](args, role="tokenizer"), context)
        self.assertEqual(events, ["resolve", ("set", args)])
        self.assertEqual(context._publish_role, "tokenizer")
        with self.assertRaises(TypeError):
            namespace["publish"](args, "tokenizer")
        with self.assertRaises(ValueError):
            namespace["publish"](args, role="unreviewed")

    def test_pinned_launch_retains_app_engine_record_auth_and_custom_warmup(self):
        args = args_fixture()
        args.is_ep_scale_joiner = False
        tokenizer = SimpleNamespace(server_status="starting")
        template, ports, watchdog = object(), object(), object()
        scheduler_info = {"synthetic": True}
        engine = Mock(return_value=(tokenizer, template, ports,
            SimpleNamespace(scheduler_infos=[scheduler_info]), watchdog, []))
        warmup, callback, uvicorn = Mock(return_value=True), Mock(), Mock()
        namespace = self.http_namespace(args, engine=engine, uvicorn=uvicorn)
        app = namespace["app"]
        # The same pinned middleware helper used by production is source-only.
        from tests.lifecycle.test_sglang38_file_auth import native
        synthetic_key = launcher._PrivateKey("synthetic-contract-key")
        with synthetic_dependencies(), patch.dict(sys.modules, {"sglang.srt.utils.auth": native}):
            launcher.install_auth(SimpleNamespace(app=app), native.add_api_key_middleware,
                                  synthetic_key)
            before = list(app.user_middleware)
            namespace["launch_server"](args, execute_warmup_func=warmup, launch_callback=callback)
        self.assertEqual(engine.call_count, 1)
        self.assertEqual(set(engine.call_args.kwargs), {"server_args", "init_tokenizer_manager_func",
            "run_scheduler_process_func", "run_detokenizer_process_func"})
        self.assertIs(engine.call_args.kwargs["server_args"], args)
        self.assertEqual(uvicorn.call_count, 1)
        self.assertIs(uvicorn.call_args.args[0], app)
        self.assertIs(app.server_args, args)
        self.assertEqual(app.warmup_thread_kwargs, {"server_args": args,
            "launch_callback": callback, "execute_warmup_func": warmup})
        self.assertIs(namespace["_global_state"].tokenizer_manager, tokenizer)
        self.assertIs(namespace["_global_state"].template_manager, template)
        self.assertIs(namespace["_global_state"].scheduler_info, scheduler_info)
        self.assertIs(tokenizer._subprocess_watchdog, watchdog)
        self.assertEqual(app.user_middleware[1:], before)
        self.assertIsNone(app.user_middleware[0].kwargs["api_key"])
        self.assertIsNone(app.user_middleware[0].kwargs["admin_api_key"])
        self.assertEqual(uvicorn.call_args.kwargs, {
            "host": args.host, "port": 30004, "root_path": None,
            "log_level": "warning", "timeout_keep_alive": 5, "loop": "uvloop",
            "ssl_keyfile": None, "ssl_certfile": None,
            "ssl_ca_certs": None, "ssl_keyfile_password": None})
        self.assertFalse(warmup.called)
        namespace["_wait_and_warmup"](**app.warmup_thread_kwargs)
        warmup.assert_called_once_with(args)
        callback.assert_called_once_with()
        namespace["_freeze_gc_after_server_warmup"].assert_called_once_with(args)

    def test_pinned_warmup_false_never_freezes_or_calls_ready_callback(self):
        args = args_fixture()
        args.is_ep_scale_joiner = False
        namespace = self.http_namespace(args)
        manager = SimpleNamespace(server_status="starting")
        namespace["_global_state"] = SimpleNamespace(tokenizer_manager=manager)
        warmup, callback = Mock(return_value=False), Mock()
        namespace["_wait_and_warmup"](args, launch_callback=callback, execute_warmup_func=warmup)
        warmup.assert_called_once_with(args)
        self.assertEqual(manager.server_status, "starting")
        callback.assert_not_called()
        namespace["_freeze_gc_after_server_warmup"].assert_not_called()

    def test_pinned_launch_refuses_wrong_engine_tuple_before_http_setup(self):
        for values in ((object(),) * 5, (object(),) * 7):
            with self.subTest(return_count=len(values)):
                uvicorn = Mock()
                namespace = self.http_namespace(args_fixture(),
                    engine=Mock(return_value=values), uvicorn=uvicorn)
                with self.assertRaises(ValueError):
                    namespace["launch_server"](args_fixture())
                uvicorn.assert_not_called()

    def test_fixture_engine_hook_matches_pinned_publication_and_http_setup(self):
        """The shipped hook runs; every native dependency here is synthetic."""
        spec = importlib.util.spec_from_file_location("q38next_synthetic_fixture_contract", FIXTURE)
        fixture = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(fixture)
        args = args_fixture()
        args.__class__.__module__ = __name__
        globals()[args.__class__.__name__] = args.__class__
        args._raw_input = dataclasses.asdict(args)
        args.is_ep_scale_joiner = False
        published = []
        context = SimpleNamespace(overrides_log=lambda: [],
            set_server_args=lambda value: published.append(value))
        publish_namespace = {"_ROLE_NS_MODE": "enforce", "ROLE_NAMESPACE_SETS": {"tokenizer": None},
                             "_CONTEXT": context}
        execute_definitions([definition(self.trees["srt/runtime_context.py"], "publish")],
                            publish_namespace, "pinned/srt/runtime_context.py")
        captured = Mock()
        server = self.http_namespace(args, uvicorn=captured)
        calls = []
        namespace = {
            **vars(fixture), "launcher": launcher, "ServerArgs": type(args),
            "PortArgs": self.port_args_type(), "sentinel": "synthetic-contract-key",
            "server": SimpleNamespace(**server), "context": 131072, "engine_calls": calls,
        }
        execute_definitions([definition(self.fixture_tree, "engine_start")],
                            namespace, str(FIXTURE))
        server["Engine"]._launch_subprocesses = namespace["engine_start"]
        from tests.lifecycle.test_sglang38_file_auth import native
        with synthetic_dependencies(), patch.dict(sys.modules, {
            "sglang.srt.arg_groups.overrides": SimpleNamespace(resolving_view=lambda value: value),
            "sglang.srt.runtime_context": SimpleNamespace(publish=publish_namespace["publish"]),
            "sglang.srt.utils": SimpleNamespace(MultiprocessingSerializer=SimpleNamespace(
                serialize=pickle.dumps)),
            "sglang.srt.utils.auth": native,
        }), patch.object(logging.getLogger("sglang.srt.entrypoints.engine"), "warning"):
            server["launch_server"](args, execute_warmup_func=Mock(return_value=True))
        self.assertEqual(published, [args])
        self.assertEqual(context._publish_role, "tokenizer")
        self.assertEqual(len(calls), 1)
        self.assertIs(calls[0][0], args)
        self.assertEqual(captured.call_count, 1)
        self.assertIs(server["app"].server_args, args)
        self.assertIs(server["_global_state"].tokenizer_manager, calls[0][1])

    def native_environment_hook(self):
        """Exact native functions, isolated to ordinary synthetic env fields."""
        namespace = {"os": os, "contextmanager": contextmanager}
        execute_definitions([definition(self.trees["srt/environ.py"], name)
                             for name in ("EnvField", "EnvStr")],
                            namespace, "pinned/srt/environ.py")
        env_fields = {}
        for name in ("SGLANG_ENABLE_TORCH_COMPILE", "SGLANG_MAMBA_SSM_DTYPE",
                     "SGLANG_DISABLE_OUTLINES_DISK_CACHE", "SGLANG_ENABLE_DETERMINISTIC_INFERENCE"):
            value = namespace["EnvStr"](None)
            value.__set_name__(object, name)
            env_fields[name] = value
        namespace.update(
            envs=SimpleNamespace(**env_fields), resolving_view=lambda value: value,
            handle_multimodal_feature_transport=Mock(name="synthetic_feature_transport"),
            get_platform=lambda: SimpleNamespace(is_cuda=False, is_hip=False),
        )
        execute_definitions([definition(self.trees["srt/arg_groups/serving_hook.py"],
                                        "handle_environment_variables")],
                            namespace, "pinned/srt/arg_groups/serving_hook.py")
        args = SimpleNamespace(enable_torch_compile=False, mamba_ssm_dtype="float32",
            disable_outlines_disk_cache=False, enable_deterministic_inference=False,
            debug_cuda_graph=False, enable_deepseek_v4_fp4_indexer=False)
        return lambda: namespace["handle_environment_variables"](args)

    def test_exact_resolution_environment_hook_pollutes_next_launcher_preflight(self):
        pipeline = self.trees["srt/arg_groups/pipeline.py"]
        calls = [node for node in ast.walk(pipeline) if isinstance(node, ast.Call)
                 and isinstance(node.func, ast.Name)
                 and node.func.id == "handle_environment_variables"]
        self.assertEqual(len(calls), 1)
        self.assertEqual([ast.unparse(value) for value in calls[0].args], ["server_args"])
        hook = self.native_environment_hook()
        with patch.dict(os.environ, launcher.CACHE_ENVIRONMENT, clear=True), \
                patch.object(launcher.importlib.metadata, "version", return_value="0.5.19"), \
                patch.object(launcher.importlib.metadata, "entry_points", return_value={}):
            launcher.validate_environment()
            hook()
            self.assertEqual(os.environ["SGLANG_MAMBA_SSM_DTYPE"], "float32")
            # Production must continue refusing inherited native runtime switches.
            with self.assertRaisesRegex(launcher.LaunchError, "^launch_environment_invalid$"):
                launcher.validate_environment()

    def test_checked_launch_restores_native_environment_after_success_and_failure(self):
        spec = importlib.util.spec_from_file_location("q38next_synthetic_environment_fixture", FIXTURE)
        fixture = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(fixture)
        hook = self.native_environment_hook()
        for result in (0, 1):
            with self.subTest(result=result), \
                    patch.dict(os.environ, launcher.CACHE_ENVIRONMENT, clear=True), \
                    patch.object(launcher.importlib.metadata, "version", return_value="0.5.19"), \
                    patch.object(launcher.importlib.metadata, "entry_points", return_value={}), \
                    patch.object(fixture.os, "write"):
                before = dict(os.environ)
                self.flashinfer_import_hook()()
                imported_environment = dict(os.environ)
                observed = []

                def invoke(_argv):
                    launcher.validate_environment()
                    hook()
                    observed.append(os.environ["SGLANG_MAMBA_SSM_DTYPE"])
                    return result

                synthetic_launcher = SimpleNamespace(main=invoke, LOGGER=Mock(),
                                                      __file__=launcher.__file__)
                if result == 0:
                    self.assertEqual(fixture.checked_launch(synthetic_launcher, [], [object()],
                        [object()], "synthetic-contract-key", before), 0)
                else:
                    with self.assertRaises(fixture.FixtureFailure) as caught:
                        fixture.checked_launch(synthetic_launcher, [], [object()],
                            [object()], "synthetic-contract-key", before)
                    self.assertEqual(caught.exception.launch_failure["result"], 1)
                self.assertEqual(observed, ["float32"])
                self.assertEqual(dict(os.environ), imported_environment)

                # The next independent injection-negative case reaches cleanup;
                # native imports/key reading and process cleanup are synthetic.
                cleanup = Mock(name="synthetic_cleanup")
                server = SimpleNamespace(Engine=SimpleNamespace(_launch_subprocesses=Mock()),
                                         uvicorn=SimpleNamespace(run=Mock()))
                auth = SimpleNamespace(add_api_key_middleware=Mock())
                negative = next(node for node in ast.walk(definition(self.fixture_tree, "run_actual"))
                    if isinstance(node, ast.With)
                    and any(ast.unparse(item.context_expr).startswith("patch.dict(os.environ,")
                            for item in node.items)
                    and any(isinstance(item, ast.Constant)
                        and item.value == "no_op_injection_not_refused" for item in ast.walk(node)))
                with patch.dict(sys.modules, {
                    "sglang.srt.server_args": SimpleNamespace(prepare_server_args=lambda argv: args_fixture()),
                    "sglang.srt.entrypoints": SimpleNamespace(http_server=server),
                    "sglang.srt.arg_groups.overrides": SimpleNamespace(resolving_view=lambda value: value),
                    "sglang.srt.utils": SimpleNamespace(kill_process_tree=cleanup),
                    "sglang.srt.utils.auth": auth,
                }), patch.object(launcher, "read_key", return_value=launcher._PrivateKey("synthetic-contract-key")), \
                        patch.object(launcher, "install_auth", side_effect=launcher.LaunchError("auth_installation_invalid")), \
                        patch.object(launcher.LOGGER, "error"):
                    execute_definitions([copy.deepcopy(negative)], {
                        "patch": patch, "os": os, "launch_environment": before,
                        "auth": auth, "server": server, "launcher": launcher,
                        "argv": cli(), "require": fixture.require}, "fixture-auth-negative.py")
                cleanup.assert_called_once_with(os.getpid(), include_parent=False)
                self.assertEqual(dict(os.environ), imported_environment)


if __name__ == "__main__":
    unittest.main()
