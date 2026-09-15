"""Synthetic F1S source/lifecycle contracts; no Docker daemon, model, or real key.

These tests retain production validation and state transitions. Only host file
and process I/O is substituted. PASS is not the F1D pinned-image auth gate.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import sys
import tempfile
import unittest
from contextlib import ExitStack, contextmanager
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from lifecycle.manager import Manager
from lifecycle.runtime_io import LifecycleError
from lifecycle.storage_binding import BindingError
from lifecycle import qwen_next
import test_manager as retained

DEPLOYMENT = "qwen3-coder-next"
MODEL = "qwen3-coder-next-fp8"
RUNTIME = "sglang-qwen-next-0.5.14"
IMAGE = "sha256:5027e95bf6ec536856b1b52a91d1f35ff5c564ab83e8a94758a169ff09bb8df3"
TAG = "lmsysorg/sglang:v0.5.14-cu130"
REVISION = "da6e2ed27304dd39abadd9c82ef50e8de67bdd4c"
MANIFEST_SHA256 = "022674d4daf63fa57c2798a30fea80c6dde7b1b2e73630ae3c3aa94e45debb9e"
MANIFEST = ROOT / "reports/f1s-contract-evidence/f1a-qwen-manifest.json"
LAUNCHER = ROOT / "scripts/lifecycle/sglang_file_auth.py"
INSTALLED_LAUNCHER = "/data/services/llm-manager/adapters/sglang_file_auth.py"
COMPLETION = "/data/services/llm-manager/acquisition/qwen3-coder-next-fp8.complete.json"


def read_profile(kind, name):
    return json.loads((ROOT / "configs" / kind / (name + ".json")).read_text())


class QwenSourceContractTests(unittest.TestCase):
    def test_exact_authoritative_manifest_is_not_completion_evidence(self):
        raw = MANIFEST.read_bytes()
        expected = json.loads(raw)
        self.assertEqual(hashlib.sha256(raw).hexdigest(), MANIFEST_SHA256)
        model = read_profile("models", MODEL)
        for field in ("repo_id", "revision", "artifacts", "artifact_count", "total_bytes"):
            self.assertEqual(model[field], expected[field])
        self.assertEqual(model["repo_id"], "Qwen/Qwen3-Coder-Next-FP8")
        self.assertEqual(model["revision"], REVISION)
        self.assertEqual(model["artifact_count"], 48)
        self.assertEqual(model["total_bytes"], 80407722953)
        weights = [item for item in model["artifacts"] if item["role"] == "weight"]
        self.assertEqual(len(weights), 40)
        self.assertEqual(sum(item["size_bytes"] for item in weights), 80381394600)
        self.assertEqual(model["model_root"], {"role": "models", "suffix": MODEL})
        self.assertNotEqual(expected.get("complete"), True)

    def test_instance_template_cannot_activate_source_only_auth_or_partial_weights(self):
        template = read_profile("deployments/instances", "f1s.template")
        runtime = template["runtime_evidence"][RUNTIME]
        model = template["model_integrity"][MODEL]
        self.assertFalse(runtime["auth_gate_passed"])
        self.assertFalse(model["verified"])
        self.assertEqual(model["revision"], REVISION)
        self.assertEqual(model["manifest_sha256"], MANIFEST_SHA256)
        self.assertIsNone(template["storage_identity"])
        self.assertNotIn("required_mounts", template)

    def test_explicit_sglang_profile_uses_protected_file_adapter_and_exact_bounds(self):
        runtime = read_profile("runtimes", RUNTIME)
        deployment = read_profile("deployments", DEPLOYMENT)
        self.assertEqual(runtime["backend"], "sglang")
        self.assertEqual(runtime["image_tag"], TAG)
        self.assertEqual(runtime["network_mode"], "bridge")
        self.assertEqual(runtime["environment"]["DISABLE_OPENAPI_DOC"], "1")
        self.assertEqual(deployment["model"], MODEL)
        self.assertEqual(deployment["runtime"], RUNTIME)
        self.assertEqual(deployment["endpoint"], {
            "host": "127.0.0.1", "port": 30003,
            "api_prefix": "/v1", "served_model": DEPLOYMENT,
        })
        self.assertEqual(deployment["container_host"], "0.0.0.0")
        self.assertEqual(deployment["container_port"], 30003)
        self.assertEqual(deployment["docker_restart_policy"], "no")
        self.assertEqual(deployment["boot_policy"], "manual")
        self.assertEqual(deployment["launch"]["context_size"], 32768)
        self.assertEqual(deployment["launch"]["gpus"], ["0", "1"])
        self.assertEqual(deployment["launch"]["timeout_seconds"], 7200)
        by_target = {mount["target"]: mount for mount in deployment["mounts"]}
        self.assertEqual(len(by_target), 6)
        for target in ("/models", "/run/secrets/llm-api-key", "/opt/llmctl/sglang_file_auth.py"):
            self.assertTrue(by_target[target]["read_only"])
        self.assertEqual(by_target["/opt/llmctl/sglang_file_auth.py"]["source"],
                         {"role": "data", "suffix": qwen_next.LAUNCHER_SUFFIX})
        self.assertEqual(by_target["/opt/llmctl/sglang_file_auth.py"]["required_role"], "data")


class QwenBoundPathContractTests(unittest.TestCase):
    """Pure adapter checks; registered mount validation is exercised separately."""

    def deployment(self, data, models):
        roots = {'data': Path(data), 'models': Path(models)}
        binding = SimpleNamespace(path=lambda role, suffix: roots[role] / suffix,
                                  validate_path=lambda role, path: Path(path))
        d = read_profile('deployments', DEPLOYMENT)
        d['_runtime'] = read_profile('runtimes', RUNTIME)
        d['_model'] = read_profile('models', MODEL)
        d['_storage_binding'] = binding
        resolve = lambda value: str(binding.path(value['role'], value['suffix']))
        d['paths'] = {key: resolve(value) for key, value in d['paths'].items()}
        d['auth']['key_file'] = resolve(d['auth']['key_file'])
        d['_model']['model_root'] = resolve(d['_model']['model_root'])
        for mount in d['mounts']:
            mount['source'] = resolve(mount['source'])
        return d

    def test_nondefault_single_nested_sibling_and_historical_paths(self):
        for data, models in [('/srv/ai', '/srv/ai/models'), ('/srv/ai', '/srv/ai'),
                             ('/srv/ai', '/srv/ai/models-large'), ('/srv/ai', '/mnt/weights'),
                             ('/data', '/data/models-large')]:
            with self.subTest(data=data, models=models):
                d = self.deployment(data, models)
                qwen_next.validate(d)
                self.assertEqual(d['_model']['model_root'], models + '/' + MODEL)
                self.assertEqual(d['mounts'][-1]['source'], data + '/' + qwen_next.LAUNCHER_SUFFIX)
                self.assertEqual(qwen_next.command(d)[qwen_next.command(d).index('--model-path') + 1], '/models')
                self.assertEqual(len(d['mounts']), 6)

    def test_completion_root_is_concrete_bound_evidence_and_cannot_be_relocated(self):
        d = self.deployment('/srv/ai', '/mnt/weights')
        completion = {
            'schema_version': 1, 'complete': True, 'repo_id': d['_model']['repo_id'],
            'revision': REVISION, 'model_root': '/mnt/weights/' + MODEL,
            'manifest_sha256': MANIFEST_SHA256, 'artifact_count': 48, 'total_bytes': 80407722953,
            'artifacts': [{**a, 'verified': True} for a in d['_model']['artifacts']],
        }
        item = {'verified': True, 'revision': REVISION, 'manifest_sha256': MANIFEST_SHA256,
                'evidence': 'synthetic fixture',
                'completion_manifest': '/srv/ai/services/llm-manager/acquisition/' + MODEL + '.complete.json'}
        instance = {'model_integrity': {MODEL: item}}
        with patch.object(qwen_next, 'protected_bytes', side_effect=lambda path: json.dumps(completion).encode()) as read:
            qwen_next.check_completion(d, instance)
            self.assertEqual(str(read.call_args.args[0]), item['completion_manifest'])
            completion['model_root'] = '/data/models-large/' + MODEL
            with self.assertRaises(LifecycleError):
                qwen_next.check_completion(d, instance)
        for path in ['/data/services/llm-manager/acquisition/' + MODEL + '.complete.json',
                     '/srv/ai/services/llm-manager/acquisition/../acquisition/' + MODEL + '.complete.json',
                     {'role': 'data', 'suffix': 'services/llm-manager/acquisition/' + MODEL + '.complete.json'}]:
            with self.subTest(path=path), patch.object(qwen_next, 'protected_bytes') as read:
                item['completion_manifest'] = path
                with self.assertRaises(LifecycleError):
                    qwen_next.check_completion(d, instance)
                read.assert_not_called()


class QwenDocker(retained.FakeDocker):
    """Reuse the retained inspect-schema fake with backend-specific image IDs."""
    def __init__(self):
        super().__init__()
        self.sglang_image = IMAGE
        self.sglang_entrypoint = ["/opt/nvidia/nvidia_entrypoint.sh"]
        self.sglang_image_environment = ["PATH=/usr/local/bin:/usr/bin", "LANG=C.UTF-8"]

    def run(self, args, timeout=30):
        if args[:2] == ["image", "inspect"] and (TAG in args or IMAGE in args):
            self._event(("run", tuple(args)))
            return json.dumps([{"Id": self.sglang_image, "Config": {
                "Entrypoint": self.sglang_entrypoint,
                "Env": self.sglang_image_environment,
            }}])
        return super().run(args, timeout=timeout)

    def create(self, argv):
        image = next(item for item in argv if item.startswith("sha256:"))
        with patch.object(retained, "IMAGE", image):
            identity = super().create(argv)
        if image == IMAGE:
            records = self._read()
            record = next(item for item in records if item["Id"] == identity)
            environment = dict(entry.split("=", 1) for entry in self.sglang_image_environment)
            environment.update(entry.split("=", 1) for entry in record["Config"]["Env"])
            record["Config"].update(
                Env=[key + "=" + value for key, value in environment.items()],
                WorkingDir=argv[argv.index("--workdir") + 1], User=argv[argv.index("--user") + 1],
                Healthcheck={"Test": ["NONE"]} if "--no-healthcheck" in argv else {},
            )
            record["HostConfig"].update(
                ReadonlyRootfs="--read-only" in argv,
                ShmSize=8 * 1024**3 if argv[argv.index("--shm-size") + 1] == "8g" else 0,
                Tmpfs=dict([argv[argv.index("--tmpfs") + 1].split(":", 1)]),
                CapDrop=[argv[argv.index("--cap-drop") + 1]],
                SecurityOpt=[argv[argv.index("--security-opt") + 1]],
                Devices=[], DeviceCgroupRules=None, VolumesFrom=None, Binds=None,
                PidMode="", IpcMode="private", UTSMode="",
            )
            record["HostConfig"]["DeviceRequests"][0].update(
                Driver="", Count=0, Capabilities=[["gpu"]], Options={})
            self._write(records)
        return identity


class ProtectedSourceTests(unittest.TestCase):
    """Real local O_NOFOLLOW/open/read; mock root ownership of worker files only."""
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.path = self.root / "reviewed-source.py"
        self.payload = b"# nonsecret reviewed source fixture\n"
        self.path.write_bytes(self.payload)
        self.path.chmod(0o644)
        self.file_uid = 0
        self.parent_uid = 0
        self.parent_mode = 0o755
        real_fstat, real_stat = os.fstat, Path.stat

        def file_meta(fd):
            value = real_fstat(fd)
            return SimpleNamespace(st_mode=value.st_mode, st_size=value.st_size,
                                   st_uid=self.file_uid)

        def parent_meta(path, *args, **kwargs):
            value = real_stat(path, *args, **kwargs)
            if stat.S_ISDIR(value.st_mode):
                return SimpleNamespace(st_mode=stat.S_IFDIR | self.parent_mode,
                                       st_size=value.st_size, st_uid=self.parent_uid)
            return value

        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(os, "fstat", side_effect=file_meta))
        self.stack.enter_context(patch.object(Path, "stat", parent_meta))

    def test_protected_source_reads_exactbytes_and_closes_descriptor(self):
        with patch.object(os, "close", wraps=os.close) as close:
            self.assertEqual(qwen_next.protected_bytes(self.path), self.payload)
        close.assert_called_once()

    def test_nonroot_file_or_parent_and_writable_or_sticky_parent_are_refused(self):
        for uid, parent_uid, mode in ((1000, 0, 0o755), (0, 1000, 0o755),
                                      (0, 0, 0o775), (0, 0, 0o1777)):
            self.file_uid, self.parent_uid, self.parent_mode = uid, parent_uid, mode
            with self.subTest(file_uid=uid, parent_uid=parent_uid, mode=mode), \
                    self.assertRaises(LifecycleError):
                qwen_next.protected_bytes(self.path)

    def test_writable_empty_or_oversized_source_is_refused(self):
        self.path.chmod(0o666)
        with self.assertRaises(LifecycleError):
            qwen_next.protected_bytes(self.path)
        self.path.chmod(0o644)
        self.path.write_bytes(b"")
        with self.assertRaises(LifecycleError):
            qwen_next.protected_bytes(self.path)
        self.path.write_bytes(self.payload)
        with self.assertRaises(LifecycleError):
            qwen_next.protected_bytes(self.path, limit=1)

    def test_symlink_file_or_parent_and_nonregular_source_are_refused(self):
        alias = self.root / "alias.py"
        alias.symlink_to(self.path)
        parent = self.root / "alias-dir"
        parent.symlink_to(self.root, target_is_directory=True)
        for path in (alias, parent / self.path.name, self.root):
            with self.subTest(kind="symlink-or-directory"), self.assertRaises(LifecycleError):
                qwen_next.protected_bytes(path)

    def test_short_read_race_raises_generic_error_and_closes_descriptor(self):
        with patch.object(os, "read", return_value=b""), \
                patch.object(os, "close", wraps=os.close) as close:
            with self.assertRaises(LifecycleError) as raised:
                qwen_next.protected_bytes(self.path)
        self.assertRegex(str(raised.exception), r"^[a-z_]+$")
        close.assert_called_once()


class BoundQwenManager(retained.FixtureManager):
    """Inject storage identity/writer/lease; retain all production F1S checks."""
    host_guards = Manager.host_guards
    check_mounts = Manager.check_mounts
    check_artifacts = Manager.check_artifacts
    image_evidence = Manager.image_evidence
    prepare_start = Manager.prepare_start


class QwenContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.configs = self.root / "configs"
        shutil.copytree(ROOT / "configs", self.configs)
        self.instance = retained.make_instance(self.root)
        runtime = read_profile("runtimes", RUNTIME)
        self.instance["runtime_evidence"][RUNTIME] = {
            "image_id": IMAGE, "flags_verified": True,
            "supported_flags": runtime["required_cli_flags"],
            "evidence": "SYNTHETIC source fixture; no pinned-image execution",
            "launcher_sha256": hashlib.sha256(LAUNCHER.read_bytes()).hexdigest(),
            "auth_gate_passed": True,
            "auth_gate_evidence": "SYNTHETIC assertion for negative gate tests; NOT F1D proof",
        }
        self.instance["runtime_evidence"]["llama-cpp-v0.4.1-d1"].update(
            image_id=retained.IMAGE, load_mode="none")
        self.instance["model_integrity"][MODEL] = {
            "verified": True, "revision": REVISION,
            "evidence": "SYNTHETIC expected metadata; no acquired model payloads",
            "manifest_sha256": MANIFEST_SHA256, "completion_manifest": COMPLETION,
        }
        self.docker = QwenDocker()
        self.clock = retained.FakeClock()
        self.probe_result = "ready"
        self.probe_calls = []
        self.manager = BoundQwenManager(
            self.configs, self.instance, docker=self.docker, test_paths=True,
            run_fn=lambda *a, **kw: self.fail("unexpected worker subprocess"),
            probe_fn=self.probe, monotonic_fn=self.clock.monotonic, sleep_fn=self.clock.sleep,
        )
        self.original = self.manager.deployment(DEPLOYMENT)
        self.completion = {
            "schema_version": 1, "complete": True,
            "repo_id": self.original["_model"]["repo_id"], "revision": REVISION,
            "model_root": self.original["_model"]["model_root"],
            "manifest_sha256": MANIFEST_SHA256, "artifact_count": 48,
            "total_bytes": 80407722953,
            "artifacts": [{**{k: item[k] for k in ("path", "size_bytes", "sha256")}, "verified": True}
                          for item in self.original["_model"]["artifacts"]],
        }
        self.installed_launcher = LAUNCHER.read_bytes()
        self.missing_files = set()
        self.wrong_sizes = {}
        self.file_modes = {}
        self.symlink_paths = set()
        self.artifact_stats = []
        self.io_stack = ExitStack()
        self.addCleanup(self.io_stack.close)
        self.io_stack.enter_context(patch.object(self.manager, "check_mounts"))
        self.io_stack.enter_context(patch.object(self.manager, "host_guards"))
        self.io_stack.enter_context(patch("lifecycle.manager.validate_key_metadata"))
        self.io_stack.enter_context(patch.object(qwen_next, "protected_bytes", side_effect=self.protected_read))
        self.io_stack.enter_context(self.host_files())

    def probe(self, *args, **kwargs):
        self.probe_calls.append((args, kwargs))
        return self.probe_result

    def protected_read(self, path, *args, **kwargs):
        if str(path) == INSTALLED_LAUNCHER:
            return self.installed_launcher
        if str(path) == COMPLETION:
            return json.dumps(self.completion).encode()
        self.fail("unexpected protected file read")

    def test_completion_and_launcher_reject_hidden_mount_before_read_and_recheck_after(self):
        evidence = self.instance['runtime_evidence'][RUNTIME]
        for call, path in [(lambda: qwen_next.check_completion(self.original, self.instance), COMPLETION),
                           (lambda: qwen_next.validate_launcher(self.original, evidence), INSTALLED_LAUNCHER)]:
            with self.subTest(path=path, phase='before'), \
                    patch.object(self.manager.binding, 'validate_path', side_effect=BindingError('hidden_mount')), \
                    patch.object(qwen_next, 'protected_bytes') as read:
                with self.assertRaisesRegex(LifecycleError, '^sglang_storage_path_invalid$'):
                    call()
                read.assert_not_called()
            with self.subTest(path=path, phase='after'), \
                    patch.object(self.manager.binding, 'validate_path', side_effect=[None, BindingError('mount_lost')]) as verify, \
                    patch.object(qwen_next, 'protected_bytes', side_effect=self.protected_read) as read:
                with self.assertRaisesRegex(LifecycleError, '^sglang_storage_path_invalid$'):
                    call()
                self.assertEqual([item.args for item in verify.call_args_list], [('data', path), ('data', path)])
                read.assert_called_once()

    @contextmanager
    def host_files(self):
        """Model exact /data metadata only; real configs/state/locks use disk."""
        originals = {name: getattr(Path, name) for name in ("resolve", "exists", "is_file", "is_dir", "stat")}
        sizes = {self.original["_model"]["model_root"] + "/" + item["path"]: item["size_bytes"]
                 for item in self.original["_model"]["artifacts"]}
        file_paths = set(sizes) | {INSTALLED_LAUNCHER, COMPLETION, self.original["auth"]["key_file"]}

        def resolve(path, *args, **kwargs):
            if str(path).startswith("/data/"):
                return Path("/fixture-symlink-target") if str(path) in self.symlink_paths else path
            return originals["resolve"](path, *args, **kwargs)

        def metadata(name):
            def call(path, *args, **kwargs):
                value = str(path)
                if not value.startswith("/data/"):
                    return originals[name](path, *args, **kwargs)
                if name == "exists":
                    return value not in self.missing_files
                if name == "is_file":
                    return value in file_paths and value not in self.missing_files
                if name == "is_dir":
                    return value not in file_paths and value not in self.missing_files
                if value in sizes:
                    self.artifact_stats.append(value)
                return SimpleNamespace(st_size=self.wrong_sizes.get(value, sizes.get(value, 1)),
                                       st_mode=stat.S_IFREG | self.file_modes.get(value, 0o644), st_uid=0)
            return call

        with ExitStack() as stack:
            stack.enter_context(patch.object(Path, "resolve", resolve))
            for name in ("exists", "is_file", "is_dir", "stat"):
                stack.enter_context(patch.object(Path, name, metadata(name)))
            yield

    def assert_rejected(self, bad):
        with self.assertRaises(LifecycleError):
            self.manager.validate_deployment(bad)
            self.manager.create_args(bad)

    def render(self):
        return self.manager.create_args(self.original)

    def state(self):
        return json.loads((self.root / "state/active.json").read_text())

    def start(self):
        self.manager.dispatch("select", deployment_id=DEPLOYMENT)
        return self.manager.dispatch("start")

    def mutations(self):
        return [call for call in self.docker.calls if call[0] in
                {"create", "start_enter", "start_exit", "stop", "remove"}]

    def test_render_exact_image_command_auth_mount_and_container_restrictions(self):
        args = self.render()
        expected_command = [
            "/opt/llmctl/sglang_file_auth.py", "--key-file", "/run/secrets/llm-api-key",
            "--warmup-timeout", "600", "--model-path", "/models", "--served-model-name", DEPLOYMENT,
            "--host", "0.0.0.0", "--port", "30003", "--context-length", "32768",
            "--tp-size", "2", "--tokenizer-worker-num", "1", "--tool-call-parser", "qwen3_coder",
            "--mem-fraction-static", "0.75", "--max-running-requests", "1", "--load-format", "safetensors",
        ]
        self.assertEqual(args[args.index(IMAGE) + 1:], expected_command)
        for option, expected in {
            "--publish": "127.0.0.1:30003:30003/tcp", "--restart": "no", "--network": "bridge",
            "--entrypoint": "python3", "--gpus": '"device=0,1"', "--workdir": "/service",
            "--tmpfs": "/tmp:rw,nosuid,nodev,size=1g", "--shm-size": "8g",
            "--cap-drop": "ALL", "--security-opt": "no-new-privileges:true", "--user": "0",
        }.items():
            self.assertEqual(args[args.index(option) + 1], expected)
        self.assertIn("--read-only", args)
        self.assertIn("--no-healthcheck", args)
        self.assertIn("DISABLE_OPENAPI_DOC=1", args)
        self.assertEqual(args.count("--mount"), 6)
        self.assertIn("type=bind,source=" + INSTALLED_LAUNCHER +
                      ",target=/opt/llmctl/sglang_file_auth.py,readonly", args)
        self.assertIn("type=bind,source=/data/services/secrets/llm-api-key," +
                      "target=/run/secrets/llm-api-key,readonly", args)
        for unsafe in ("--api-key", "--admin-api-key", "--config", "--api-key-file", "--trust-remote-code",
                       "--enable-ray", "--enable-grpc", "--tool-server", "--skip-server-warmup"):
            self.assertNotIn(unsafe, args)

    def test_backend_dispatch_rejects_arbitrary_missing_or_disguised_backend(self):
        for backend in ("arbitrary", "llama_cpp", "legacy", None, ["sglang"]):
            bad = copy.deepcopy(self.original)
            if backend is None:
                bad["_runtime"].pop("backend")
            else:
                bad["_runtime"]["backend"] = backend
            with self.subTest(backend=backend):
                self.assert_rejected(bad)
        bad = copy.deepcopy(self.original)
        bad["legacy"] = True
        self.assert_rejected(bad)

    def test_profile_rejects_extra_flags_options_and_alternative_launch_paths(self):
        for field in ("args", "command", "extra_args", "config", "plugins", "tool_server", "env"):
            for target in ("deployment", "runtime"):
                bad = copy.deepcopy(self.original)
                (bad if target == "deployment" else bad["_runtime"])[field] = ["--api-key", "fixture-only"]
                with self.subTest(field=field, target=target):
                    self.assert_rejected(bad)
        for field in ("enable_ray", "enable_grpc", "enable_http2", "reload", "encoder_only", "extra_args"):
            bad = copy.deepcopy(self.original)
            bad["launch"][field] = True
            with self.subTest(field=field):
                self.assert_rejected(bad)

    def test_exact_parser_context_gpu_tokenizer_and_warmup_limits_are_enforced(self):
        changes = {
            "context_size": 8192, "gpus": ["1", "0"], "tp_size": 1, "tokenizer_worker_num": 2,
            "tool_call_parser": "qwen25", "max_running_requests": 2, "mem_fraction_static": 0.95,
            "load_format": "auto", "warmup_timeout_seconds": 0, "timeout_seconds": 7201,
            "poll_seconds": 0, "request_timeout_seconds": 0, "stop_timeout_seconds": 121,
        }
        for field, value in changes.items():
            bad = copy.deepcopy(self.original)
            bad["launch"][field] = value
            with self.subTest(field=field):
                self.assert_rejected(bad)
        for field in ("tp_size", "tokenizer_worker_num", "max_running_requests"):
            bad = copy.deepcopy(self.original)
            bad["launch"][field] = True
            self.assert_rejected(bad)

    def test_endpoint_restart_and_mount_tampering_is_rejected(self):
        cases = []
        for host in ("0.0.0.0", "::1", "localhost", "10.0.0.2"):
            bad = copy.deepcopy(self.original)
            bad["endpoint"]["host"] = host
            cases.append(bad)
        for mode in ("host", "macvlan", "container:other"):
            bad = copy.deepcopy(self.original)
            bad["_runtime"]["network_mode"] = mode
            cases.append(bad)
        bad = copy.deepcopy(self.original)
        bad["docker_restart_policy"] = "always"
        cases.append(bad)
        for target in ("/models", "/run/secrets/llm-api-key", "/opt/llmctl/sglang_file_auth.py"):
            for field, value in (("read_only", False), ("source", "/etc"), ("target", "/service")):
                bad = copy.deepcopy(self.original)
                next(m for m in bad["mounts"] if m["target"] == target)[field] = value
                cases.append(bad)
        bad = copy.deepcopy(self.original)
        bad["mounts"].append(copy.deepcopy(bad["mounts"][0]))
        cases.append(bad)
        bad = copy.deepcopy(self.original)
        bad["mounts"].pop()
        cases.append(bad)
        for index, bad in enumerate(cases):
            with self.subTest(case=index):
                self.assert_rejected(bad)

    def test_image_tag_digest_entrypoint_and_flag_metadata_cannot_drift(self):
        for field, value in (("image_id", retained.IMAGE), ("image_tag", "sglang:latest"),
                             ("entrypoint", ["python3", "-m", "sglang.launch_server"]),
                             ("required_cli_flags", ["--api-key"])):
            bad = copy.deepcopy(self.original)
            bad["_runtime"][field] = value
            with self.subTest(field=field):
                self.assert_rejected(bad)
        self.docker.sglang_image = retained.IMAGE
        with self.assertRaises(LifecycleError):
            self.render()

    def test_environment_profile_injection_rejected_without_echo(self):
        sentinel = os.urandom(24).hex()
        for key, value in (("API_KEY", sentinel), ("PYTHONPATH", "/service"),
                           ("HF_HOME", "/data/services/secrets"), ("HF_HUB_OFFLINE", "0"),
                           ("DISABLE_OPENAPI_DOC", "0")):
            bad = copy.deepcopy(self.original)
            bad["_runtime"]["environment"][key] = value
            with self.assertRaises(LifecycleError) as raised:
                self.manager.validate_deployment(bad)
            self.assertTrue(sentinel not in str(raised.exception), "generic exception leak detected")

    def test_each_production_auth_and_image_evidence_gate_is_required(self):
        evidence = self.manager.instance["runtime_evidence"][RUNTIME]
        original = copy.deepcopy(evidence)
        changes = {"image_id": retained.IMAGE, "flags_verified": False, "supported_flags": [],
                   "evidence": None, "launcher_sha256": "0" * 64,
                   "auth_gate_passed": False, "auth_gate_evidence": None}
        for field, value in changes.items():
            evidence.clear()
            evidence.update(original)
            evidence[field] = value
            with self.subTest(field=field), self.assertRaises(LifecycleError):
                self.render()
        evidence.clear()
        evidence.update(original)

    def test_malformed_evidence_fails_with_sanitized_lifecycle_error(self):
        for supported in (None, {"--model-path": True}, "--model-path", [None]):
            self.manager.instance["runtime_evidence"][RUNTIME]["supported_flags"] = supported
            with self.subTest(kind=type(supported).__name__), self.assertRaises(LifecycleError):
                self.manager.image_evidence(self.original)
        for path in (None, [], {}):
            self.manager.instance["model_integrity"][MODEL]["completion_manifest"] = path
            with self.subTest(kind=type(path).__name__), self.assertRaises(LifecycleError):
                self.manager.check_artifacts(self.original)
        self.manager.instance["model_integrity"][MODEL] = None
        with self.assertRaises(LifecycleError):
            self.manager.check_artifacts(self.original)

    def test_installed_launcher_hash_mismatch_refuses_start_before_docker_creation(self):
        self.installed_launcher += b"\n# local unauthorized edit\n"
        with self.assertRaises(LifecycleError):
            self.start()
        self.assertEqual(self.mutations(), [])

    def test_installed_launcher_requires_exact_readonly_source_mode(self):
        for mode in (0o600, 0o666, 0o755):
            self.file_modes[INSTALLED_LAUNCHER] = mode
            with self.subTest(mode=mode), self.assertRaises(LifecycleError):
                self.render()

    def test_model_profile_pin_architecture_quantization_and_inventory_tamper_rejected(self):
        changes = [lambda m: m.update(revision="0" * 40),
                   lambda m: m.update(repo_id="other/model"),
                   lambda m: m.update(architecture="Qwen3ForCausalLM"),
                   lambda m: m.update(quantization="gguf"),
                   lambda m: m.update(total_bytes=1),
                   lambda m: m["artifacts"][0].update(sha256="0" * 64),
                   lambda m: m["artifacts"].pop()]
        for index, mutate in enumerate(changes):
            bad = copy.deepcopy(self.original)
            mutate(bad["_model"])
            with self.subTest(case=index):
                self.assert_rejected(bad)

    def test_complete_acquisition_checks_all_48_sizes_without_reading_weight_payloads(self):
        with patch.object(Path, "read_bytes", side_effect=AssertionError("unexpected payload read")):
            self.manager.check_artifacts(self.original)
        self.assertEqual(set(self.artifact_stats), {
            self.original["_model"]["model_root"] + "/" + item["path"]
            for item in self.original["_model"]["artifacts"]})

    def test_incomplete_acquisition_and_missing_auth_gate_fail_before_docker_start(self):
        self.completion["complete"] = False
        with self.assertRaises(LifecycleError):
            self.start()
        self.assertEqual(self.mutations(), [])
        self.completion["complete"] = True
        self.manager.instance["runtime_evidence"][RUNTIME]["auth_gate_passed"] = False
        with self.assertRaises(LifecycleError):
            self.manager.dispatch("start")
        self.assertEqual(self.mutations(), [])

    def test_completion_rejects_partial_duplicate_wrong_hash_size_revision_and_schema(self):
        original = copy.deepcopy(self.completion)
        mutations = [
            lambda c: c.update(schema_version=2), lambda c: c.update(complete=1),
            lambda c: c.update(artifact_count=47), lambda c: c.update(total_bytes=80407722952),
            lambda c: c.update(revision="0" * 40), lambda c: c.update(manifest_sha256="0" * 64),
            lambda c: c.update(repo_id="somewhere/else"), lambda c: c.update(model_root="/models"),
            lambda c: c["artifacts"].pop(),
            lambda c: c["artifacts"].__setitem__(1, copy.deepcopy(c["artifacts"][0])),
            lambda c: c["artifacts"][0].update(verified=False),
            lambda c: c["artifacts"][0].update(sha256="0" * 64),
            lambda c: c["artifacts"][0].update(size_bytes=0),
            lambda c: c["artifacts"][0].update(path="../outside"),
        ]
        for index, mutate in enumerate(mutations):
            self.completion = copy.deepcopy(original)
            mutate(self.completion)
            with self.subTest(case=index), self.assertRaises(LifecycleError):
                self.manager.check_artifacts(self.original)
        self.completion = original

    def test_completion_order_is_immaterial_and_expected_inventory_is_not_completion(self):
        self.completion["artifacts"].reverse()
        self.manager.check_artifacts(self.original)
        self.completion = json.loads(MANIFEST.read_bytes())
        with self.assertRaises(LifecycleError):
            self.manager.check_artifacts(self.original)

    def test_model_evidence_missing_wrong_pin_or_unsafe_completion_path_is_rejected(self):
        evidence = self.manager.instance["model_integrity"][MODEL]
        original = copy.deepcopy(evidence)
        for field, value in (("verified", False), ("revision", "0" * 40),
                             ("manifest_sha256", "0" * 64), ("evidence", None),
                             ("completion_manifest", "/tmp/complete.json"),
                             ("completion_manifest", "/data/services/llm-manager/acquisition/../complete.json")):
            evidence.clear()
            evidence.update(original)
            evidence[field] = value
            with self.subTest(field=field), self.assertRaises(LifecycleError):
                self.manager.check_artifacts(self.original)
        evidence.clear()
        evidence.update(original)

    def test_last_weight_missing_wrong_size_or_symlink_is_rejected(self):
        weight = next(item for item in reversed(self.original["_model"]["artifacts"])
                      if item["role"] == "weight")
        path = self.original["_model"]["model_root"] + "/" + weight["path"]
        for kind in ("missing", "size", "symlink"):
            self.missing_files.clear()
            self.wrong_sizes.clear()
            self.symlink_paths.clear()
            if kind == "missing":
                self.missing_files.add(path)
            elif kind == "size":
                self.wrong_sizes[path] = weight["size_bytes"] - 1
            else:
                self.symlink_paths.add(path)
            with self.subTest(kind=kind), self.assertRaises(LifecycleError):
                self.manager.check_artifacts(self.original)

    def test_start_stop_restart_keep_exact_identity_and_authenticated_model_probe(self):
        self.start()
        identity = self.state()["container"]["id"]
        self.assertEqual(self.state()["observed"], "ready")
        args, kwargs = self.probe_calls[-1]
        self.assertEqual(args[:2], ("http://127.0.0.1:30003/v1", DEPLOYMENT))
        self.assertEqual(args[2], "/data/services/secrets/llm-api-key")
        self.assertTrue(kwargs["require_auth"])
        self.manager.dispatch("stop")
        self.assertEqual(self.state()["observed"], "stopped")
        self.manager.dispatch("start")
        self.assertEqual(self.state()["container"]["id"], identity)
        self.docker.calls.clear()
        self.manager.dispatch("restart")
        operations = [call[0] for call in self.mutations()]
        self.assertLess(operations.index("stop"), operations.index("start_enter"))
        self.assertEqual(self.state()["container"]["id"], identity)

    def test_backend_readiness_dispatch_uses_sglang_probe_and_retains_glm_probe(self):
        glm = self.manager.deployment(retained.PROOF)
        with patch.object(self.manager, "sglang_probe", return_value="sglang-fixture-result") as sglang, \
                patch.object(self.manager, "probe", return_value="glm-fixture-result") as generic:
            self.assertEqual(self.manager.probe_deployment(self.original, 2.5), "sglang-fixture-result")
            generic.assert_not_called()
            sglang.assert_called_once_with(
                "http://127.0.0.1:30003/v1", DEPLOYMENT, "/data/services/secrets/llm-api-key",
                require_auth=True, timeout=2.5)
            self.assertEqual(self.manager.probe_deployment(glm, 1.5), "glm-fixture-result")
            generic.assert_called_once_with(
                "http://127.0.0.1:30002/v1", "glm-5.3", "/data/services/secrets/llm-api-key",
                require_auth=True, timeout=1.5)
            self.assertEqual(sglang.call_count, 1)

    def test_reused_container_rejects_command_mount_image_environment_or_security_tamper(self):
        self.start()
        self.manager.dispatch("stop")
        original = self.docker._read()
        changes = [
            lambda c: c["Config"]["Cmd"].extend(["--api-key", "fixture-only"]),
            lambda c: c["Config"].update(Entrypoint=["python3", "-m", "sglang.launch_server"]),
            lambda c: c.update(Image=retained.IMAGE),
            lambda c: c["Mounts"][-1].update(RW=True),
            lambda c: c["Mounts"][-1].update(Type="volume"),
            lambda c: c["Mounts"].append(copy.deepcopy(c["Mounts"][0])),
            lambda c: c["Config"]["Env"].append("API_KEY=fixture-only"),
            lambda c: c["Config"]["Env"].append("PYTHONPATH=/service"),
            lambda c: c["Config"]["Env"].append(c["Config"]["Env"][0]),
            lambda c: c["Config"].update(WorkingDir="/"),
            lambda c: c["Config"].update(User="1000"),
            lambda c: c["HostConfig"].update(ReadonlyRootfs=False),
            lambda c: c["HostConfig"].update(ShmSize=64 * 1024**2),
            lambda c: c["HostConfig"].update(Tmpfs={}),
            lambda c: c["HostConfig"].update(CapAdd=["SYS_ADMIN"]),
            lambda c: c["HostConfig"].update(SecurityOpt=[]),
            lambda c: c["Config"].update(Healthcheck={"Test": ["CMD", "custom-probe"]}),
            lambda c: c["HostConfig"]["DeviceRequests"][0].update(DeviceIDs=["0"]),
            lambda c: c["HostConfig"]["DeviceRequests"][0].update(Driver="unreviewed-runtime"),
            lambda c: c["HostConfig"]["DeviceRequests"][0].update(Count=-1),
            lambda c: c["HostConfig"]["DeviceRequests"][0].update(Capabilities=[["gpu", "other"]]),
            lambda c: c["HostConfig"]["DeviceRequests"][0].update(Options={"custom": "value"}),
            lambda c: c["HostConfig"].update(Devices=[{"PathOnHost": "/dev/sdb", "PathInContainer": "/dev/sdb"}]),
            lambda c: c["HostConfig"].update(DeviceCgroupRules=["a *:* rwm"]),
            lambda c: c["HostConfig"].update(VolumesFrom=["unrelated-worker-service"]),
            lambda c: c["HostConfig"].update(Binds=["/etc:/mnt/host"]),
            lambda c: c["HostConfig"].update(PidMode="container:other"),
            lambda c: c["HostConfig"].update(IpcMode="shareable"),
            lambda c: c["HostConfig"].update(UTSMode="host"),
            lambda c: c["HostConfig"].update(NetworkMode="host"),
            lambda c: c["HostConfig"].update(Privileged=True),
            lambda c: c["HostConfig"].update(IpcMode="host"),
            lambda c: c["HostConfig"]["RestartPolicy"].update(Name="always"),
            lambda c: c["HostConfig"]["PortBindings"]["30003/tcp"][0].update(HostIp="0.0.0.0"),
            lambda c: c["HostConfig"]["PortBindings"].update({
                "39999/tcp": [{"HostIp": "127.0.0.1", "HostPort": "39999"}]}),
        ]
        for index, mutate in enumerate(changes):
            records = copy.deepcopy(original)
            mutate(records[0])
            self.docker._write(records)
            self.docker.calls.clear()
            with self.subTest(case=index), self.assertRaises(LifecycleError):
                self.manager.dispatch("start")
            self.assertEqual(self.mutations(), [])
        self.docker._write(original)

    def test_reviewed_nvidia_device_driver_reuses_same_identity(self):
        self.start()
        self.manager.dispatch("stop")
        identity = self.state()["container"]["id"]
        records = self.docker._read()
        records[0]["HostConfig"]["DeviceRequests"][0]["Driver"] = "nvidia"
        self.docker._write(records)
        self.manager.dispatch("start")
        self.assertEqual(self.state()["observed"], "ready")
        self.assertEqual(self.state()["container"]["id"], identity)

    def test_glm_on_other_port_blocks_qwen_start_and_is_never_stopped(self):
        glm = self.manager.deployment(retained.PROOF)
        identity = self.docker.create(self.manager.create_args(glm))
        self.docker.start(identity)
        self.docker.calls.clear()
        with self.assertRaises(LifecycleError):
            self.start()
        self.assertEqual(self.mutations(), [])
        self.assertTrue(self.docker.inspect(identity)["State"]["Running"])

    def test_qwen_running_blocks_glm_selection_and_preserves_active_identity(self):
        self.start()
        before = self.state()
        self.docker.calls.clear()
        with self.assertRaises(LifecycleError):
            self.manager.dispatch("select", deployment_id=retained.PROOF)
        self.assertEqual(self.state(), before)
        self.assertEqual(self.mutations(), [])

    def test_failed_start_keeps_exact_stoppable_identity_without_ready_claim(self):
        self.docker.fail_start = True
        with self.assertRaises(LifecycleError):
            self.start()
        identity = self.state()["container"]["id"]
        self.assertEqual(self.state()["observed"], "failed")
        self.assertFalse(self.state()["container_running"])
        self.manager.dispatch("stop")
        self.assertFalse(self.state()["container_running"])
        self.assertEqual(self.state()["container"]["id"], identity)

    def test_timeout_is_bounded_and_automatically_stops_failed_start(self):
        self.probe_result = "not_ready"
        with self.assertRaises(LifecycleError):
            self.start()
        self.assertEqual(self.clock.now, 7200)
        self.assertEqual(self.state()["observed"], "failed")
        self.assertFalse(self.state()["container_running"])
        self.assertIn(("stop", self.state()["container"]["id"]), self.docker.calls)
        self.manager.dispatch("stop")
        self.assertFalse(self.state()["container_running"])

    def test_auth_or_model_mismatch_cleans_up_and_never_claims_ready(self):
        for result in ("auth_error", "wrong_model"):
            self.probe_result = result
            with self.subTest(result=result), self.assertRaises(LifecycleError):
                self.start()
            self.assertEqual(self.state()["observed"], "failed")
            self.assertFalse(self.state()["container_running"])

    def test_cleanup_failure_keeps_running_failure_truthful_and_retry_stop_recovers(self):
        self.probe_result = "auth_error"
        self.docker.fail_stop = True
        with self.assertRaises(LifecycleError):
            self.start()
        self.assertEqual(self.state()["observed"], "failed")
        self.assertTrue(self.state()["container_running"])
        self.docker.fail_stop = False
        self.manager.dispatch("stop")
        self.assertFalse(self.state()["container_running"])

    def test_stop_does_not_require_auth_gate_model_or_launcher_to_remain_available(self):
        self.start()
        self.manager.instance["runtime_evidence"][RUNTIME]["auth_gate_passed"] = False
        self.completion["complete"] = False
        self.installed_launcher = b"changed"
        with patch.object(self.manager, "check_artifacts", side_effect=AssertionError("stop touched model")), \
                patch.object(qwen_next, "validate_launcher", side_effect=AssertionError("stop touched launcher")):
            self.manager.dispatch("stop")
        self.assertEqual(self.state()["observed"], "stopped")
        self.assertFalse(self.state()["container_running"])

    def test_stop_refuses_replaced_id_or_changed_ownership_without_stopping_other_container(self):
        self.start()
        records = self.docker._read()
        records[0]["Id"] = "f" * 64
        records[0]["Config"]["Labels"] = {}
        self.docker._write(records)
        self.docker.calls.clear()
        try:
            self.manager.dispatch("stop")
        except LifecycleError:
            pass
        self.assertNotIn(("stop", "f" * 64), self.docker.calls)
        self.assertTrue(self.docker._read()[0]["State"]["Running"])

    def test_status_does_not_rehash_or_require_acquisition_to_report_live_observation(self):
        self.start()
        with patch.object(self.manager, "check_artifacts", side_effect=AssertionError("status touched model")):
            self.assertEqual(self.manager.status()["observed"], "ready")


if __name__ == "__main__":
    unittest.main()
