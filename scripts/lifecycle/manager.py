"""Serialized, declarative lifecycle. Docker is the runtime; systemd only replays intent.

All live I/O is injectable for deterministic worker tests. Production has no
LLMCTL_SKIP_* bypass. Files in this package are D2 owned.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager, nullcontext
from functools import wraps
import copy
import json
import importlib
import os
from pathlib import Path
import re
import signal
import stat
import time
from typing import Any

from common.lifecycle_lease import (acquire_lease, LifecycleLease, LeaseError,
                                    _validate_borrowed_lease, transition_in_progress as lease_in_progress)
from .storage_binding import RegisteredStorageBinding, BindingError, _entered_storage_context
from . import qwen_next
from .runtime_io import (Docker, LifecycleError, probe, probe_sglang, run,
                         validate_container_network, validate_key_metadata,
                         validate_published)

OWNER = "mixed-memory-llm-api-server"
LABEL = "io.llmctl."
REPO = Path(__file__).resolve().parents[2]
ID_RE = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}\Z")
DIGEST_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
CONTAINER_RE = re.compile(r"[0-9a-f]{64}\Z")
LEGACY = {
    "qwen3-0.6b-smoke": {
        "container_name": "sglang-smoke-qwen3-0.6b", "port": 30000,
        "compose_file": "/data/services/llm-manager/compose/sglang-smoke.compose.yml",
        "compose_service": "sglang-smoke", "compose_profile": "sglang-smoke",
    },
    "qwen3-30b-a3b-instruct-2507": {
        "container_name": "sglang-qwen3-30b-a3b-instruct-2507", "port": 30001,
        "compose_file": "/data/services/llm-manager/compose/sglang-qwen3-30b.compose.yml",
        "compose_service": "sglang-qwen3-30b", "compose_profile": "sglang-real-fast",
    },
}
# R1 identified this stopped predecessor. Inventory it even though D2 cannot start it.
HISTORICAL_NAMES = {"minimax-m3-mxfp8-poc"}


def require(condition: bool, code: str) -> None:
    if not condition:
        raise LifecycleError(code)


def read_json(path: Path) -> dict:
    try:
        require(not path.is_symlink(), "unsafe_json_symlink")
        require(path.stat().st_size <= 1024 * 1024, "json_too_large")
        result = json.loads(path.read_text())
        require(isinstance(result, dict), "invalid_json_object")
        return result
    except (OSError, ValueError, TypeError):
        raise LifecycleError("invalid_or_missing_json") from None


def state_errors(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except (ValueError, TypeError, KeyError, AttributeError, IndexError):
            raise LifecycleError('invalid_state') from None
    return wrapped


def protected_json(path: Path, *, uid=0) -> dict:
    """Small nonsecret control file; credentials never pass through this opener."""
    path = Path(path)
    require(path.is_absolute() and path.resolve() == path, "untrusted_control_path")
    for parent in path.parents:
        info = parent.stat()
        require(info.st_uid == uid and not info.st_mode & 0o022, "untrusted_control_parent")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_uid == uid
                and stat.S_IMODE(info.st_mode) == 0o600 and info.st_size <= 1024 * 1024,
                "untrusted_control_file")
        raw = os.read(fd, 1024 * 1024 + 1)
        current = path.lstat()
        require((info.st_dev, info.st_ino) == (current.st_dev, current.st_ino)
                and len(raw) == info.st_size, "control_file_changed")
        value = json.loads(raw)
        require(isinstance(value, dict), "invalid_json_object")
        return value
    finally:
        os.close(fd)


def atomic_json(path: Path, value: dict, *, system_root=Path('/'), trusted_uid=0) -> None:
    """Only the tiny volatile journal. Persistent writes belong to I1b storage_io."""
    root = Path(system_root)
    require(path == root / 'run/llmctl/recovery.json', "volatile_journal_path_required")
    parent = path.parent
    require(parent.resolve() == parent, "unsafe_state_parent_symlink")
    # The canonical lease creates this private directory. Never create a fallback.
    for item in (parent, *parent.parents):
        if item == root.parent:
            break
        meta = item.lstat()
        require(stat.S_ISDIR(meta.st_mode) and meta.st_uid == trusted_uid
                and not meta.st_mode & 0o022, "untrusted_journal_parent")
        if item == root:
            break
    directory = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    tmp = '.recovery-' + os.urandom(16).hex()
    try:
        if path.exists() or path.is_symlink():
            old = path.lstat()
            require(stat.S_ISREG(old.st_mode) and old.st_nlink == 1 and old.st_uid == trusted_uid
                    and stat.S_IMODE(old.st_mode) == 0o600, "untrusted_journal_file")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
        with os.fdopen(fd, 'w') as stream:
            json.dump(value, stream, sort_keys=True, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        require(parent.stat().st_ino == os.fstat(directory).st_ino
                and parent.stat().st_dev == os.fstat(directory).st_dev, "journal_directory_changed")
        os.replace(tmp, path.name, src_dir_fd=directory, dst_dir_fd=directory)
        os.fsync(directory)
    finally:
        try:
            os.unlink(tmp, dir_fd=directory)
        except FileNotFoundError:
            pass
        os.close(directory)


@contextmanager
def process_lock(path: Path):
    """Compatibility for in-process fixtures; production has one canonical path."""
    path = Path(path)
    require(path.parts[-3:] == ('run', 'llmctl', 'lifecycle.lock'), "unsafe_lock_path")
    root = path.parents[2]
    with acquire_lease(system_root=root, trusted_uid=0 if root == Path('/') else os.geteuid()) as lease:
        yield lease


def transition_in_progress(path: Path) -> bool:
    path = Path(path)
    require(path.parts[-3:] == ('run', 'llmctl', 'lifecycle.lock'), "unsafe_lock_path")
    root = path.parents[2]
    return lease_in_progress(system_root=root, trusted_uid=0 if root == Path('/') else os.geteuid())


def empty_state() -> dict:
    return {"schema_version": 2, "selected": None, "desired": "stopped",
            "boot_policy": "manual", "observed": "stopped", "container": None,
            "container_running": False, "failure": None}


def legacy_profile(identifier: str) -> dict:
    spec = LEGACY[identifier]
    return {"id": identifier, "model": identifier, "runtime": "sglang", "legacy": True,
            **spec, "container_port": 30000,
            "endpoint": {"host": "127.0.0.1", "port": spec["port"],
                         "api_prefix": "/v1", "served_model": identifier},
            "paths": {"model": "/data/models/" + identifier},
            "launch": {"timeout_seconds": 1200, "poll_seconds": 5,
                       "request_timeout_seconds": 5, "stop_timeout_seconds": 60},
            "image_tag": "lmsysorg/sglang:v0.5.14-cu130"}


class Manager:
    def __init__(self, config_root: Path, instance: dict, *, docker=None,
                 probe_fn=probe, run_fn=run, sleep_fn=time.sleep,
                 monotonic_fn=time.monotonic, test_paths=False, binding=None,
                 storage_io=None, lease_system_root=Path('/'), recovery_only=False):
        require(isinstance(instance, dict), 'invalid_instance')
        self.config_root, self.instance = Path(config_root), copy.deepcopy(instance)
        self.docker = docker if docker is not None else Docker()
        self.probe, self.run, self.sleep, self.monotonic = probe_fn, run_fn, sleep_fn, monotonic_fn
        self.sglang_probe = probe_sglang if probe_fn is probe else probe_fn
        require(instance.get("schema_version") == 1, "invalid_instance_version")
        require(bool(ID_RE.fullmatch(str(instance.get("id", "")))), "invalid_instance_id")
        self.binding, self.storage_io = binding, storage_io
        self.recovery_only, self.test_paths = recovery_only, test_paths
        self.lease_system_root = Path(lease_system_root)
        require(test_paths or self.lease_system_root == Path('/'), "unsafe_lock_path")
        self.trusted_uid = os.geteuid() if test_paths else 0
        self.lock_file = self.lease_system_root / 'run/llmctl/lifecycle.lock'
        self.recovery_file = self.lease_system_root / 'run/llmctl/recovery.json'
        self.state_file = None
        paths = instance.get("paths", {})
        require(recovery_only or isinstance(paths, dict), 'invalid_instance_paths')
        if not recovery_only:
            require(binding is not None, "registered_storage_binding_required")
            require(instance.get('storage_identity') == binding.identity, "registry_instance_identity_mismatch")
            self.historical_imported()
            state_path = self.host_path(paths.get('state'), expected_role='data')
            require(test_paths or state_path == binding.path('data', 'services/llm-manager/active'), "unsafe_state_path")
            self.state_file = Path(state_path) / 'active.json'
            require(test_paths or paths.get('lock', str(self.lock_file)) == str(self.lock_file), "unsafe_lock_path")
            require(test_paths or paths.get('recovery', str(self.recovery_file)) == str(self.recovery_file), "unsafe_recovery_path")
        self.state = empty_state()

    def historical_imported(self):
        flag = self.instance.get('historical_import', False)
        require(type(flag) is bool, 'invalid_historical_import_marker')
        if flag:
            require(self.binding is not None, 'historical_storage_binding_required')
            registry = self.binding.registry
            require(registry['data']['path'] == registry['data']['mount'] == '/data'
                    and registry['models']['path'] == registry['models']['mount'] == '/data/models-large',
                    'historical_paths_must_be_preserved')
        return flag

    def host_path(self, value, *, expected_role=None) -> str:
        require(self.binding is not None, "registered_storage_binding_required")
        if isinstance(value, dict):
            require(set(value) in ({'role', 'suffix'}, {'role', 'suffix', 'historical_suffix'})
                    and value['role'] in {'data', 'models'}, "invalid_host_path_binding")
            require(expected_role is None or value['role'] == expected_role, "wrong_host_path_role")
            self.binding.path(value['role'], value['suffix'])
            if 'historical_suffix' in value:
                self.binding.path(value['role'], value['historical_suffix'])
            suffix = value.get('historical_suffix', value['suffix']) if self.historical_imported() else value['suffix']
            return self.binding.path(value['role'], suffix)
        # Concrete host evidence/explicitly imported instances retain exact paths.
        require(isinstance(value, str) and expected_role is not None, "role_relative_host_path_required")
        base = Path(self.binding.path(expected_role))
        p = Path(value)
        require(p.is_absolute() and p.is_relative_to(base) and str(p) == value, "host_path_outside_role")
        suffix = str(p.relative_to(base))
        require(suffix != '.', "host_path_suffix_required")
        require(self.binding.path(expected_role, suffix) == value, "invalid_host_path_binding")
        return value

    def persistent_writer(self):
        require(self.binding is not None and not self.recovery_only, "registered_storage_unavailable")
        if self.storage_io is None:
            try:
                self.storage_io = importlib.import_module('install.storage_io')
            except ImportError:
                raise LifecycleError('i1b_anchored_storage_io_required') from None
        return self.storage_io

    def persistent_json(self, path, value):
        """I1b owns directory anchoring; all paths below the anchor are relative."""
        data = Path(self.binding.path('data'))
        target = Path(path)
        require(str(target) == str(path), 'invalid_persistent_path')
        require(target != data and target.is_relative_to(data), 'persistent_path_outside_data')
        require(self.binding.path('data', str(target.relative_to(data))) == str(target),
                'invalid_persistent_path')
        # The coincident data/models root is models-owned. Durable lifecycle
        # state and reports belong below a more-specific registered service/log
        # root; let the actual writer retain final path-role authorization.
        candidates = [(Path(self.binding.path(role)), role) for role in ('services', 'state', 'logs')]
        candidates = [(root, role) for root, role in candidates
                      if root != data and root.is_relative_to(data)
                      and target != root and target.is_relative_to(root)]
        require(bool(candidates), 'persistent_path_outside_service_roots')
        root, role = max(candidates, key=lambda item: len(item[0].parts))
        relative = str(target.relative_to(root))
        require(self.binding.path(role, relative) == str(target), 'invalid_persistent_path')
        self.binding.validate_path(role, str(target))
        writer = self.persistent_writer()
        try:
            with self.binding.mounted_guard(writer, roles=('data',)) as guard:
                with _entered_storage_context(writer.AnchoredRoot(str(root), guard)) as anchored:
                    if Path(relative).parent != Path('.'):
                        anchored.mkdir(str(Path(relative).parent), mode=0o700, parents=True)
                    anchored.atomic_json(relative, value)
                    anchored.check()
        except Exception:
            raise LifecycleError('persistent_storage_io_failed') from None

    def check_package_admission(self):
        """Consume I1R's read-only marker/gate/orphan-inhibitor admission.

        Called under the canonical lease. Missing shared admission fails closed;
        lifecycle never restores package policy or guesses transaction completion.
        """
        try:
            self.check_mounts({'data'})
            admission = getattr(importlib.import_module('install.prerequisites'),
                                'assert_package_admission', None)
            require(callable(admission), 'package_transaction_recovery_required')
            writer = self.persistent_writer()
            with self.binding.mounted_guard(writer, roles=('data',)) as guard:
                admission(self.binding.path('data'), guard)
                guard()
        except Exception:
            raise LifecycleError('package_transaction_recovery_required') from None

    def bind_deployment(self, d):
        """Resolve only declared host roles; container paths and evidence are untouched."""
        d['_storage_binding'] = self.binding
        for name in ('model', 'cache', 'logs', 'service'):
            d['paths'][name] = self.host_path(d['paths'][name], expected_role='models' if name in {'model', 'cache'} else 'data')
        d['auth']['key_file'] = self.host_path(d['auth']['key_file'], expected_role='data')
        d['_model']['model_root'] = self.host_path(d['_model']['model_root'], expected_role='models')
        for mount in d['mounts']:
            require(mount.get('required_role') in {'data', 'models'} and 'required_mount' not in mount, "missing_required_role")
            mount['source'] = self.host_path(mount['source'], expected_role=mount['required_role'])
        return d

    def profile_json(self, path):
        if self.test_paths:
            return read_json(path)
        # Profiles are nonsecret reviewed source, protected just like the adapter.
        value = json.loads(qwen_next.protected_bytes(path))
        require(isinstance(value, dict), 'invalid_profile')
        return value

    def deployment(self, identifier: str) -> dict:
        require(isinstance(identifier, str) and bool(ID_RE.fullmatch(identifier)), "invalid_deployment_id")
        if identifier in LEGACY:
            require(self.binding is not None and self.binding.path('data') == '/data'
                    and self.historical_imported(), "legacy_requires_explicit_historical_import")
            return legacy_profile(identifier)
        d = self.profile_json(self.config_root / "deployments" / (identifier + ".json"))
        require(d.get("id") == identifier and d.get("schema_version") == 1, "invalid_deployment")
        for kind, field in (("models", "model"), ("runtimes", "runtime")):
            name = d.get(field)
            require(isinstance(name, str) and bool(ID_RE.fullmatch(name)), "invalid_profile_id")
            value = self.profile_json(self.config_root / kind / (name + ".json"))
            require(value.get("id") == name and value.get("schema_version") == 1, "invalid_profile")
            d["_" + field] = value
        self.bind_deployment(d)
        self.validate_deployment(d)
        return d

    @staticmethod
    def backend(d: dict) -> str:
        backend = d["_runtime"].get("backend")
        require(isinstance(backend, str) and backend in {"llama_cpp", "sglang", "sglang_qwen38"}, "unsupported_backend")
        return backend

    @staticmethod
    def sglang_adapter(d: dict):
        backend = Manager.backend(d)
        if backend == "sglang_qwen38":
            # Offline recovery snapshots intentionally contain a minimal import
            # closure. Load Q38's installed-source dependencies only for Q38.
            from . import qwen38
            return qwen38
        return qwen_next if backend == "sglang" else None

    def validate_deployment(self, d: dict) -> None:
        backend = self.backend(d)
        adapter = self.sglang_adapter(d)
        require(d["_runtime"].get("kind") == "docker", "unsupported_runtime_kind")
        require(d["_runtime"].get("network_mode") == "bridge", "unsafe_network_mode")
        require(d.get("docker_restart_policy") == "no", "multiple_supervisors_refused")
        require(bool(ID_RE.fullmatch(d.get("container_name", ""))), "invalid_container_name")
        ep = d.get("endpoint", {})
        require(ep.get("host") == "127.0.0.1" and ep.get("api_prefix") == "/v1", "unsafe_endpoint")
        require(bool(ID_RE.fullmatch(ep.get("served_model", ""))), "invalid_served_model")
        for port in (ep.get("port"), d.get("container_port")):
            require(type(port) is int and 1 <= port <= 65535, "invalid_port")
        require(d.get("container_host") == "0.0.0.0", "invalid_bridge_server_host")
        auth = d.get("auth", {})
        require(auth.get("mode") == "0600", "unsafe_key_mode")
        require(auth.get("key_file") == self.binding.path("data", "services/secrets/llm-api-key"), "unsafe_key_path")
        mounts = d.get("mounts", [])
        require(len(mounts) == (6 if adapter else 5), "invalid_mount_contract")
        targets = set()
        for m in mounts:
            source, target = Path(m["source"]), Path(m["target"])
            require(source.is_absolute() and target.is_absolute() and ".." not in source.parts
                    and ".." not in target.parts and "," not in str(source), "unsafe_mount_path")
            require(m.get("required_role") in {"data", "models"}, "missing_required_role")
            base = Path(self.binding.path(m['required_role']))
            require(source.is_relative_to(base) and source != base, "mount_outside_data")
            require(str(target) not in targets and type(m["read_only"]) is bool, "duplicate_mount_target")
            targets.add(str(target))
        require(targets == {"/models", "/cache", "/logs", "/service", auth["container_key_file"]}
                | ({adapter.LAUNCHER_TARGET} if adapter else set()), "invalid_mount_targets")
        by_target = {m["target"]: m for m in mounts}
        for role, target in (("model", "/models"), ("cache", "/cache"), ("logs", "/logs"), ("service", "/service")):
            require(d["paths"][role] == by_target[target]["source"], "path_mount_mismatch")
        require(by_target["/models"]["read_only"] and by_target[auth["container_key_file"]]["read_only"], "writable_model_or_key")
        require(by_target[auth["container_key_file"]]["source"] == auth["key_file"], "key_mount_mismatch")
        require(d["paths"]["model"] == d["_model"]["model_root"]
                == self.binding.path('models', d['model']), "model_root_mismatch")
        for role, root in (("model", self.binding.path('models')), ("cache", self.binding.path('models', 'runtime-cache')),
                           ("logs", self.binding.path('data', 'logs/llmctl')), ("service", self.binding.path('data', 'services/llm-manager'))):
            require(Path(d["paths"][role]).is_relative_to(root) and Path(d["paths"][role]) != Path(root), "unsafe_role_mount")
        require(auth["container_key_file"] == "/run/secrets/llm-api-key", "unsafe_container_key_path")
        require(d.get("logs", {}) == {"driver": "json-file", "max_size": "20m", "max_file": 3}, "unbounded_logs")
        for key, low, high in (("timeout_seconds", 1, 14400), ("poll_seconds", 1, 30),
                               ("request_timeout_seconds", 1, 30), ("stop_timeout_seconds", 1, 120)):
            value = d.get("launch", {}).get(key)
            require(type(value) is int and low <= value <= high, "invalid_launch_limit")
        if adapter:
            adapter.validate(d)
            return
        require(d["_runtime"].get("environment") == {"LD_LIBRARY_PATH": "/opt/llama", "LLAMA_ARG_HOST": "0.0.0.0", "XDG_CACHE_HOME": "/cache"}, "unsafe_runtime_environment")
        launch = d.get("launch", {})
        for key, low, high in (("context_size", 512, 131072), ("parallel", 1, 1),
                               ("timeout_seconds", 1, 14400), ("poll_seconds", 1, 30),
                               ("request_timeout_seconds", 1, 30), ("stop_timeout_seconds", 1, 120),
                               ("n_gpu_layers", 1, 999)):
            require(type(launch.get(key)) is int and low <= launch[key] <= high, "invalid_launch_limit")
        require(launch.get("cpu_moe") is True and launch.get("jinja") is True
                and launch.get("no_webui") is True, "invalid_launch_safety")
        require(launch.get("split_mode") == "layer" and re.fullmatch(r"[0-9]+(?:\.[0-9]+)?,[0-9]+(?:\.[0-9]+)?", launch.get("tensor_split", "")), "invalid_gpu_split")
        require(launch.get("devices") == ["CUDA0", "CUDA1"], "invalid_runtime_devices")
        require(launch.get("chat_template_kwargs") == {"clear_thinking": True}, "invalid_template_parameters")
        require(len(launch.get("gpus", [])) == 2 and len(set(launch["gpus"])) == 2
                and all(re.fullmatch(r"[0-9]+", g) for g in launch["gpus"]), "invalid_gpu_devices")
        require(d.get("logs", {}) == {"driver": "json-file", "max_size": "20m", "max_file": 3}, "unbounded_logs")

    def check_mounts(self, roles=None) -> None:
        require(self.binding is not None and not self.recovery_only, "registered_storage_unavailable")
        require(self.instance.get('storage_identity') == self.binding.identity, "registry_instance_identity_mismatch")
        try:
            return self.binding.verify(roles=('data', 'models') if roles is None else roles)
        except BindingError:
            raise LifecycleError('registered_storage_verification_failed') from None

    def check_sources(self, d) -> None:
        self.check_mounts({'data'} if d.get('legacy') else None)
        sources = ([('data', '/data/models'), ('data', d['paths']['model']), ('data', d['compose_file'])]
                   if d.get('legacy') else [(m['required_role'], m['source']) for m in d['mounts']])
        for role, source in sources:
            try:
                self.binding.validate_path(role, source)
            except BindingError:
                raise LifecycleError('unregistered_mount_source') from None

    def host_guards(self) -> None:
        self.check_mounts()
        # Guard commands are read-only here; reports use the shared anchored writer.
        self.run([str(REPO / "scripts/common/require-data-mounted.sh")], timeout=120)
        result = self.run(['/usr/bin/python3', '-I', '-B', str(REPO / 'scripts/common/registered-storage.py'),
                           '--json', '--root-guard'], timeout=300)
        value = json.loads(result)
        self.persistent_json(self.binding.path('data', 'logs/llmctl-root-disk-guard.json'), value)

    def check_completion(self, d):
        """Fresh GLM receipts bind verified artifact identities to the actual root."""
        model = d['_model']
        item = self.instance.get('model_integrity', {}).get(d['model'], {})
        require(item.get('verified') is True and item.get('revision') == model['revision']
                and bool(item.get('evidence')), 'd1_integrity_evidence_required')
        path = item.get('completion_manifest')
        if self.historical_imported() and path is None:
            return  # Preserve explicit historical D1 attestation unchanged.
        acquisition = Path(self.binding.path('data', 'services/llm-manager/acquisition'))
        require(isinstance(path, str) and Path(path).parent == acquisition, 'acquisition_completion_required')
        complete = self.binding.read_json('data', path)
        expected = {'schema_version': 1, 'complete': True, 'repo_id': model['repo_id'],
                    'revision': model['revision'], 'model_root': self.binding.path('models', d['model']),
                    'artifact_count': model['artifact_count'], 'total_bytes': model['total_bytes']}
        require(all(complete.get(k) == v and type(complete.get(k)) is type(v) for k, v in expected.items()),
                'acquisition_completion_identity_mismatch')
        files = complete.get('artifacts')
        require(isinstance(files, list) and len(files) == model['artifact_count']
                and all(isinstance(a, dict) and a.get('verified') is True for a in files),
                'acquisition_completion_incomplete')
        actual = {(a.get('path'), a.get('size_bytes'), a.get('sha256')) for a in files}
        expected_files = {(a['path'], a['size_bytes'], a['sha256']) for a in model['artifacts']}
        require(actual == expected_files and len(actual) == len(files), 'acquisition_completion_artifacts_mismatch')

    def check_artifacts(self, d: dict) -> None:
        self.check_sources(d)
        if d.get("legacy"):
            root = Path(d["paths"]["model"])
            self.binding.validate_path('data', str(root / 'config.json'))
            weights = list(root.glob('*.safetensors'))
            for path in weights:
                self.binding.validate_path('data', str(path))
            require(root.is_dir() and (root / "config.json").is_file()
                    and bool(weights), "legacy_model_files_missing")
            return
        adapter = self.sglang_adapter(d)
        if adapter:
            adapter.check_completion(d, self.instance)
        else:
            self.check_completion(d)
        model = d["_model"]
        entries = model.get("artifacts", [])
        require(len(entries) == model.get("artifact_count") and len(entries) > 0, "invalid_artifact_manifest")
        require(len({a["path"] for a in entries}) == len(entries) and
                sum(a["size_bytes"] for a in entries) == model.get("total_bytes"), "invalid_artifact_manifest")
        require(model["load_entry"] in {a["path"] for a in entries}, "missing_load_entry")
        root = Path(model["model_root"])
        require(root.resolve() == root, "model_symlink_refused")
        for a in entries:
            path = root / a["path"]
            require(not Path(a["path"]).is_absolute() and ".." not in Path(a["path"]).parts,
                    "unsafe_artifact_path")
            try:
                self.binding.validate_path('models', str(path))
            except BindingError:
                raise LifecycleError('unregistered_artifact_mount') from None
            require(path.resolve() == path and path.is_file(), "artifact_missing_or_symlink")
            require(path.stat().st_size == a["size_bytes"], "artifact_size_mismatch")
        verified = self.instance.get("model_integrity", {}).get(d["model"], {})
        require(verified.get("verified") is True and verified.get("revision") == model["revision"]
                and bool(verified.get("evidence")), "d1_integrity_evidence_required")

    def image_evidence(self, d: dict) -> dict:
        adapter = self.sglang_adapter(d)
        if adapter:
            return adapter.evidence(d, self.instance)
        e = self.instance.get("runtime_evidence", {}).get(d["runtime"], {})
        require(bool(DIGEST_RE.fullmatch(str(e.get("image_id", "")))), "d1_image_id_required")
        require(e.get("flags_verified") is True and bool(e.get("evidence")), "d1_flag_evidence_required")
        require(set(d["_runtime"]["required_cli_flags"]).issubset(set(e.get("supported_flags", []))), "d1_supported_flags_required")
        require(e.get("load_mode") in {"auto", "none", "mmap", "mlock", "mmap+mlock", "dio"}, "d1_load_mode_required")
        return e

    @state_errors
    def read_state(self, recovery=False, *, offline=False) -> dict:
        if not recovery:
            if self.recovery_only:
                return self.read_state(recovery=True)
            if not offline:
                self.check_mounts({'data'})
        path = self.recovery_file if recovery else self.state_file
        if not path.exists():
            if not recovery and self.recovery_file.exists():
                return self.read_state(recovery=True)
            # One-time previous llmctl location; a v2 tombstone always wins.
            legacy = self.state_file.parent.parent / "state" / "active.json" if not recovery else None
            if legacy is not None and legacy.exists():
                path = legacy
            else:
                return empty_state()
        s = (read_json(path) if self.test_paths else
             protected_json(path) if recovery or offline else self.binding.read_json('data', str(path)))
        if s.get("schema_version") != 2:
            require(not recovery and s.get("schema_version") is None, "invalid_state_version")
            ident = s.get("model_profile")
            require(ident in LEGACY, "unrecognized_legacy_state")
            d = legacy_profile(ident)
            expected = {"model_profile": ident, "runtime_profile": "sglang", "bind": "127.0.0.1",
                        "port": d["endpoint"]["port"], "endpoint": self.endpoint(d),
                        "image": d["image_tag"], "model_path": d["paths"]["model"],
                        "container_name": d["container_name"]}
            require(all(s.get(k) == v for k, v in expected.items()), "legacy_identity_mismatch")
            require(s.get("compose_file", d["compose_file"]) == d["compose_file"], "legacy_compose_mismatch")
            s = {**empty_state(), "selected": ident, "migrated_from": expected,
                 "failure": "legacy_state_requires_explicit_start"}
        require(set(empty_state()).issubset(s), 'invalid_state')
        require(s.get("desired") in {"running", "stopped"} and s.get("boot_policy") in {"manual", "resume"}
                and s.get("observed") in {"stopped", "starting", "ready", "unhealthy", "failed"}, "invalid_state")
        require(s.get("selected") is None or isinstance(s.get("selected"), str)
                and bool(ID_RE.fullmatch(s["selected"])), "invalid_state_selection")
        require(s.get("selected") is not None or s.get("desired") == "stopped", "invalid_empty_intent")
        if s.get("container") is not None:
            self.validate_identity(s["container"])
            require(s["container"]["deployment"] == s["selected"], "state_deployment_identity_mismatch")
            s["container"] = {k: s["container"][k] for k in ("id", "image_id", "name", "owner", "instance", "deployment", "legacy") if k in s["container"]}
        require(s.get("container_running") is None or type(s.get("container_running")) is bool, "invalid_running_state")
        failure = s.get("failure")
        require(failure is None or isinstance(failure, str) and str(LifecycleError(failure)) == failure, "invalid_failure_code")
        if s.get("last_selected") is not None:
            require(isinstance(s["last_selected"], str) and bool(ID_RE.fullmatch(s["last_selected"])), "invalid_previous_selection")
        if "migrated_from" in s:
            require(s["selected"] in LEGACY and isinstance(s["migrated_from"], dict), "invalid_migration_record")
            legacy = legacy_profile(s["selected"])
            s["migrated_from"] = {"model_profile": legacy["model"], "runtime_profile": legacy["runtime"], "endpoint": self.endpoint(legacy)}
        require(type(s.get("updated_at", 0)) is int, "invalid_state_timestamp")
        require('state_persisted' not in s or type(s['state_persisted']) is bool, 'invalid_persistence_state')
        if not recovery and self.recovery_file.exists():
            try:
                journal = self.read_state(recovery=True)
            except (LifecycleError, BindingError, OSError):
                journal = {}
                s["failure"] = "recovery_journal_invalid_primary_used"
            if journal.get("updated_at", 0) >= s.get("updated_at", 0) and journal.get("state_persisted") is False:
                return journal
        # Never relay arbitrary state-file strings/extra fields to stdout/reports.
        allowed = set(empty_state()) | {"updated_at", "migrated_from", "last_selected", "state_persisted"}
        return {k: v for k, v in s.items() if k in allowed}

    def save(self, *, emergency=False) -> None:
        self.state["updated_at"] = time.time_ns()
        self.state['state_persisted'] = False
        # A best-effort /run journal enables stop even when /data is unavailable.
        # Shutdown proceeds even if both journal writes fail.
        try:
            atomic_json(self.recovery_file, self.state, system_root=self.lease_system_root, trusted_uid=self.trusted_uid)
        except (OSError, LifecycleError):
            if not emergency:
                raise
        try:
            self.check_mounts({"data"})
            self.state["state_persisted"] = True
            self.persistent_json(str(self.state_file), self.state)
        except Exception:
            self.state["state_persisted"] = False
            try:
                atomic_json(self.recovery_file, self.state, system_root=self.lease_system_root, trusted_uid=self.trusted_uid)
            except (OSError, LifecycleError):
                pass
            if not emergency:
                raise LifecycleError('persistent_state_write_failed') from None
        try:
            atomic_json(self.recovery_file, self.state, system_root=self.lease_system_root, trusted_uid=self.trusted_uid)
        except (OSError, LifecycleError):
            if not emergency:
                raise

    def validate_identity(self, identity: dict) -> None:
        require(isinstance(identity, dict), "invalid_recorded_container")
        require(type(identity.get("legacy", False)) is bool, "invalid_legacy_identity")
        require(bool(CONTAINER_RE.fullmatch(str(identity.get("id", "")))), "invalid_recorded_container_id")
        require(bool(DIGEST_RE.fullmatch(str(identity.get("image_id", "")))), "invalid_recorded_image_id")
        require(bool(ID_RE.fullmatch(str(identity.get("name", "")))) and
                identity.get("owner") == OWNER and identity.get("instance") == self.instance["id"], "untrusted_container_identity")
        require(isinstance(identity.get("deployment"), str) and bool(ID_RE.fullmatch(identity["deployment"])), "invalid_recorded_deployment")

    def identity(self, c: dict, d: dict, legacy=False) -> dict:
        value = {"id": c["Id"], "name": c["Name"].lstrip("/"), "image_id": c["Image"],
                 "owner": OWNER, "instance": self.instance["id"], "deployment": d["id"], "legacy": legacy}
        self.validate_identity(value)
        return value

    def trusted_container(self, identity: dict) -> dict | None:
        self.validate_identity(identity)
        c = self.docker.inspect(identity["id"])
        if c is None:
            return None
        require(c.get("Id") == identity["id"] and c.get("Image") == identity["image_id"]
                and c.get("Name", "").lstrip("/") == identity["name"], "container_identity_changed")
        if identity.get("legacy"):
            require(identity["deployment"] in LEGACY, "invalid_legacy_identity")
            d = legacy_profile(identity["deployment"])
            self.validate_legacy_identity(c, d)
        else:
            labels = c.get("Config", {}).get("Labels") or {}
            require(all(labels.get(LABEL + k) == identity[k] for k in ("owner", "instance", "deployment")), "container_ownership_mismatch")
        return c

    def validate_legacy_identity(self, c: dict, d: dict) -> None:
        config = c.get("Config", {})
        labels = config.get("Labels") or {}
        command = config.get("Cmd") or []
        require(c.get("Name", "").lstrip("/") == d["container_name"]
                and config.get("Image") == d["image_tag"]
                and labels.get("com.docker.compose.service") == d["compose_service"], "legacy_container_ownership_mismatch")
        require(isinstance(command, list) and "--model-path" in command
                and command[command.index("--model-path") + 1] == d["paths"]["model"], "legacy_container_model_mismatch")
        require(any(m.get("Destination") == "/data/models" and m.get("Source") == "/data/models"
                    and not m.get("RW", True) for m in c.get("Mounts", [])), "legacy_model_mount_mismatch")

    def conflict_check(self, allowed_id=None) -> None:
        names = {x["container_name"] for x in LEGACY.values()} | HISTORICAL_NAMES
        for path in (self.config_root / "deployments").glob("*.json"):
            names.add(self.profile_json(path).get("container_name"))
        for c in self.docker.inventory():
            labels = c.get("Config", {}).get("Labels") or {}
            owned = labels.get(LABEL + "owner") == OWNER or c.get("Name", "").lstrip("/") in names
            if owned and c.get("Id") != allowed_id and self.running(c):
                raise LifecycleError("conflicting_backend_stop_first")

    @staticmethod
    def running(c: dict | None) -> bool:
        return bool(c and (c.get("State", {}).get("Running") or c.get("State", {}).get("Status") in {"running", "restarting", "paused"}))

    @staticmethod
    def endpoint(d: dict) -> str:
        ep = d["endpoint"]
        return f'http://{ep["host"]}:{ep["port"]}{ep["api_prefix"]}'

    def network_check(self, c: dict, d: dict) -> None:
        allowed = set()
        mode = c.get("HostConfig", {}).get("NetworkMode", "")
        if d.get("legacy") and mode not in {"host", "none", "bridge", "default", ""} and not mode.startswith(("container:", "service:")):
            info = json.loads(self.docker.capture("network", "inspect", mode))
            require(len(info) == 1 and info[0].get("Driver") == "bridge"
                    and not info[0].get("Internal") and not info[0].get("Options", {}).get("com.docker.network.bridge.trusted_host_interfaces"), "unsafe_legacy_network")
            allowed.add(mode)
        validate_container_network(c, d["endpoint"]["port"], d["container_port"], allowed_bridge_networks=allowed, allow_host_ipc=d.get("legacy", False))
        require(c.get("HostConfig", {}).get("RestartPolicy", {}).get("Name", "no") == "no", "multiple_supervisors_refused")

    def probe_deployment(self, d: dict, timeout: float) -> str:
        check = self.sglang_probe if not d.get("legacy") and self.sglang_adapter(d) else self.probe
        return check(self.endpoint(d), d["endpoint"]["served_model"],
                     d.get("auth", {}).get("key_file"), require_auth=not d.get("legacy", False),
                     timeout=timeout)

    def observe(self) -> dict:
        s = self.state
        if not s.get("container"):
            s["container_running"] = False
            s["observed"] = "stopped"
            return s
        s["container_running"] = None
        try:
            c = self.trusted_container(s["container"])
            s["container_running"] = self.running(c)
            if not self.running(c):
                s["observed"] = "failed" if s["desired"] == "running" else "stopped"
                return s
            d = self.deployment(s["container"]["deployment"])
            self.network_check(c, d)
            if not d.get("legacy"):
                self.validate_reused_contract(c, d)
            health = c.get("State", {}).get("Health", {}).get("Status")
            code = self.probe_deployment(d, d["launch"]["request_timeout_seconds"])
            was_starting = s["observed"] == "starting"
            s["observed"] = "ready" if code == "ready" and health != "unhealthy" else "unhealthy"
            if code == "not_ready" and health != "unhealthy" and was_starting and transition_in_progress(self.lock_file):
                s["observed"] = "starting"
            if s["desired"] == "stopped":
                s["failure"] = "unexpected_running_container_stop_first"
        except (LifecycleError, BindingError, LeaseError, OSError, ValueError, KeyError, TypeError):
            s["observed"] = "unhealthy"
            if "container_running" not in s:
                s["container_running"] = None
        return s

    def offline_status(self) -> dict:
        """Read saved intent only. Never inspect Docker, API, key or model files."""
        saved = self.read_state(offline=True)
        return {"schema_version": 2, "configured": True,
                "selected": saved["selected"], "desired": saved["desired"],
                "boot_policy": saved["boot_policy"],
                "recorded_observed": saved["observed"], "observed": None,
                "container_running": None, "observation": "not_performed_offline",
                "storage_observation": "not_performed_offline"}

    def status(self) -> dict:
        # Cheap status never reads/stat/hashes artifacts or invokes start guards.
        self.state = self.read_state()
        if self.state.get("migrated_from") and not self.state.get("container"):
            d = self.deployment(self.state["selected"])
            c = self.docker.inspect(d["container_name"])
            if c:
                self.validate_legacy_identity(c, d)
                self.state["container"] = self.identity(c, d, legacy=True)
        return copy.deepcopy(self.observe())

    def prepare_start(self, d: dict) -> None:
        self.check_sources(d)
        self.host_guards()
        require(self.instance.get("obsolete_boot_owner_disabled") is True
                and bool(self.instance.get("obsolete_boot_owner_evidence")), "obsolete_boot_owner_removal_required")
        self.check_artifacts(d)
        if not d.get("legacy"):
            e = self.image_evidence(d)
            adapter = self.sglang_adapter(d)
            if adapter:
                adapter.validate_launcher(d, e)
            validate_key_metadata(d["auth"]["key_file"])
            for m in d["mounts"]:
                source = Path(m["source"])
                require(source.resolve() == source and source.exists(), "mount_source_missing_or_symlink")
                file_targets = {d["auth"]["container_key_file"]} | ({adapter.LAUNCHER_TARGET} if adapter else set())
                if m["target"] not in file_targets:
                    require(source.is_dir(), "mount_source_not_directory")
        require(self.docker.capture("info", "--format", "{{.DockerRootDir}}").strip() == self.binding.path('data', 'docker'), "docker_root_outside_data")
        if not d.get('legacy'):
            # U1 preflights under its borrowed lease before stopping the old
            # backend. Reuse the exact read-only local image/argument checks;
            # _start still repeats create_args before container creation.
            self.create_args(d)

    def create_args(self, d: dict) -> list[str]:
        self.validate_deployment(d)
        backend = self.backend(d)
        adapter = self.sglang_adapter(d)
        e = self.image_evidence(d)
        launch, rt = d["launch"], d["_runtime"]
        reference = adapter.IMAGE_REFERENCE if backend == "sglang_qwen38" else rt["image_tag"]
        image = json.loads(self.docker.capture("image", "inspect", reference))
        require(isinstance(image, list) and len(image) == 1 and isinstance(image[0], dict),
                "runtime_image_id_mismatch")
        if backend == "sglang_qwen38":
            adapter.verify_runtime_image(image[0], d, e)
        else:
            require(image[0].get("Id") == e["image_id"], "runtime_image_id_mismatch")
        if backend == "llama_cpp":
            require(image[0].get("Config", {}).get("Entrypoint") == rt["entrypoint"], "runtime_entrypoint_mismatch")
        else:
            # The pinned SGLang image entrypoint is deliberately overridden.
            self.sglang_adapter(d).validate_launcher(d, e)
        require(len(rt["entrypoint"]) == 1, "unsupported_entrypoint")
        args = ["--name", d["container_name"], "--network", "bridge", "--restart", "no",
                "--publish", f'127.0.0.1:{d["endpoint"]["port"]}:{d["container_port"]}/tcp',
                "--gpus", '"device=' + ",".join(launch["gpus"]) + '"',
                "--log-driver", "json-file", "--log-opt", "max-size=20m", "--log-opt", "max-file=3",
                "--security-opt", "no-new-privileges:true", "--cap-drop", "ALL",
                "--entrypoint", rt["entrypoint"][0]]
        for k, v in {"owner": OWNER, "instance": self.instance["id"], "deployment": d["id"]}.items():
            args += ["--label", LABEL + k + "=" + v]
        for m in d["mounts"]:
            args += ["--mount", f'type=bind,source={m["source"]},target={m["target"]}' + (",readonly" if m["read_only"] else "")]
        if backend == "llama_cpp":
            require(set(rt.get("environment", {})).issubset({"LD_LIBRARY_PATH", "LLAMA_ARG_HOST", "XDG_CACHE_HOME"}), "unsafe_runtime_environment")
        else:
            args += ["--read-only", "--tmpfs", "/tmp:rw,nosuid,nodev,size=1g", "--shm-size", "8g",
                     "--workdir", "/service", "--no-healthcheck", "--user", "0"]
        for key, value in rt.get("environment", {}).items():
            args += ["--env", key + "=" + value]
        if backend == "sglang_qwen38":
            args += ["--pull=never", adapter.IMAGE_REFERENCE]
        else:
            args += [e["image_id"]]
        args += self.launch_command(d, e)
        return args

    @staticmethod
    def launch_command(d: dict, e: dict) -> list[str]:
        adapter = Manager.sglang_adapter(d)
        if adapter:
            adapter.validate(d)
            return adapter.command(d)
        launch = d["launch"]
        return ["--model", "/models/" + d["_model"]["load_entry"],
                 "--host", d["container_host"], "--port", str(d["container_port"]),
                 "--alias", d["endpoint"]["served_model"], "--api-key-file", d["auth"]["container_key_file"],
                 "--ctx-size", str(launch["context_size"]), "--parallel", str(launch["parallel"]),
                 "--cpu-moe", "--jinja", "--no-webui", "--n-gpu-layers", str(launch["n_gpu_layers"]),
                 "--split-mode", launch["split_mode"], "--tensor-split", launch["tensor_split"],
                 "--load-mode", e["load_mode"], "--device", ",".join(launch["devices"]),
                 "--chat-template-kwargs", json.dumps(launch["chat_template_kwargs"], sort_keys=True, separators=(",", ":"))]

    def validate_reused_contract(self, c: dict, d: dict) -> None:
        """A valid model alias cannot distinguish launch contracts; verify all."""
        self.validate_deployment(d)
        e = self.image_evidence(d)
        expected_image_id = e["docker_inspect"]["image_id"] if self.backend(d) == "sglang_qwen38" else e["image_id"]
        require(c.get("Image") == expected_image_id, "runtime_image_id_mismatch")
        config = c.get("Config", {})
        require(config.get("Entrypoint") == d["_runtime"]["entrypoint"]
                and config.get("Cmd") == self.launch_command(d, e), "container_launch_contract_mismatch")
        expected = {(m["source"], m["target"], not m["read_only"]) for m in d["mounts"]}
        actual = {(m.get("Source"), m.get("Destination"), m.get("RW")) for m in c.get("Mounts", [])}
        require(actual == expected and len(c.get("Mounts", [])) == len(expected), "container_mount_contract_mismatch")
        environment = dict(item.split("=", 1) for item in config.get("Env", []) if "=" in item)
        require(all(environment.get(k) == v for k, v in d["_runtime"]["environment"].items()), "container_environment_mismatch")
        host = c.get("HostConfig", {})
        require(host.get("LogConfig") == {"Type": "json-file", "Config": {"max-size": "20m", "max-file": "3"}}, "container_log_contract_mismatch")
        requests = host.get("DeviceRequests", [])
        require(len(requests) == 1 and requests[0].get("DeviceIDs") == d["launch"]["gpus"], "container_gpu_contract_mismatch")
        adapter = self.sglang_adapter(d)
        if adapter:
            reference = adapter.IMAGE_REFERENCE if self.backend(d) == "sglang_qwen38" else e["image_id"]
            image = json.loads(self.docker.capture("image", "inspect", reference))
            require(isinstance(image, list) and len(image) == 1 and isinstance(image[0], dict)
                    and image[0].get("Id") == expected_image_id, "runtime_image_id_mismatch")
            adapter.validate_reused(c, d, e, image[0])

    def _start(self) -> None:
        require(self.state.get("selected") is not None, "no_deployment_selected_use_select")
        d = self.deployment(self.state["selected"])
        self.state.update(desired="running", container_running=None if self.state.get("container") else False)
        self.prepare_start(d)  # ALL mount checks before artifact stat or Docker inventory.
        identity = self.state.get("container")
        c = self.trusted_container(identity) if identity else None
        if c and not d.get("legacy"):
            self.validate_reused_contract(c, d)
        self.conflict_check(c["Id"] if c else None)
        if c and self.running(c):
            self.network_check(c, d)
        self.state.update(desired="running", observed="starting", failure=None,
                          container_running=self.running(c))
        self.save()
        try:
            if not c:
                existing = self.docker.inspect(d["container_name"])
                if d.get("legacy"):
                    require(existing is not None, "legacy_container_missing_restore_reviewed_compose_first")
                    self.validate_legacy_identity(existing, d)
                    c = existing
                    self.state["container"] = self.identity(c, d, legacy=True)
                else:
                    require(existing is None, "container_name_in_use_select_or_recover_first")
                    args = self.create_args(d)
                    self.check_sources(d)
                    new_id = self.docker.create(args)
                    c = self.docker.inspect(new_id)
                    require(c is not None, "created_container_missing")
                    self.state["container"] = self.identity(c, d)
                    self.trusted_container(self.state["container"])
                self.state["container_running"] = self.running(c)
                self.save()  # immutable identity durable BEFORE Docker start.
            if d.get("legacy"):
                raw = self.docker.capture("compose", "-f", d["compose_file"], "--profile", d["compose_profile"], "config", "--format", "json")
                rendered = json.loads(raw)
                services = rendered.get("services", {})
                require(len(services) == 1 and d["compose_service"] in services, "legacy_compose_service_mismatch")
                service = services[d["compose_service"]]
                validate_published(service, d["container_port"], d["endpoint"]["port"], allow_host_ipc=True)
                require(service.get("container_name") == d["container_name"] and service.get("image") == d["image_tag"]
                        and str(service.get("restart", "no")) == "no", "legacy_compose_identity_mismatch")
            self.network_check(c, d)
            if not d.get("legacy"):
                self.validate_reused_contract(c, d)
            if not self.running(c):
                self.check_sources(d)
                self.docker.start(c["Id"])
            self.state["container_running"] = True
            self.save()
            deadline = self.monotonic() + d["launch"]["timeout_seconds"]
            last = "not_ready"
            while self.monotonic() < deadline:
                c = self.trusted_container(self.state["container"])
                require(self.running(c), "container_exited_during_start")
                self.network_check(c, d)
                minimum = 0 if not d.get("legacy") and self.sglang_adapter(d) else 0.1
                last = self.probe_deployment(
                    d, min(d["launch"]["request_timeout_seconds"], max(minimum, deadline - self.monotonic())))
                if last == "ready" and c.get("State", {}).get("Health", {}).get("Status") != "unhealthy":
                    self.host_guards()
                    self.check_mounts({"data"} if d.get("legacy") else None)
                    self.state.update(observed="ready", container_running=True, failure=None)
                    self.save()
                    return
                if last in {"auth_error", "wrong_model"}:
                    raise LifecycleError(last)
                self.sleep(min(d["launch"]["poll_seconds"], max(0, deadline - self.monotonic())))
            raise LifecycleError("readiness_timeout")
        except BaseException:
            if not d.get("legacy") and self.sglang_adapter(d) and self.state.get("container"):
                try:
                    failed = self.trusted_container(self.state["container"])
                    if self.running(failed):
                        self.docker.stop(failed["Id"], timeout=d["launch"]["stop_timeout_seconds"])
                except Exception:
                    pass  # State below truthfully records failed or unknown cleanup.
            # Retain identity for a deterministic stop; never hide a running failure.
            self.state["observed"] = "failed"
            self.state["failure"] = "start_failed_use_stop_before_retry"
            try:
                self.state["container_running"] = self.running(self.trusted_container(self.state["container"])) if self.state.get("container") else False
            except Exception:
                self.state["container_running"] = None
            self.save(emergency=True)
            raise

    def _stop(self, *, preserve_intent=False) -> None:
        if not preserve_intent:
            self.state["desired"] = "stopped"
        # Stop never requires model/key/config parsing, disk capacity or start guards.
        identity = self.state.get("container")
        if not identity and self.state.get("selected") in LEGACY:
            d = legacy_profile(self.state["selected"])
            c = self.docker.inspect(d["container_name"])
            if c:
                self.validate_legacy_identity(c, d)
                identity = self.identity(c, d, legacy=True)
                self.state["container"] = identity
        self.save(emergency=True)
        if identity:
            try:
                c = self.trusted_container(identity)
                if self.running(c):
                    self.docker.stop(identity["id"], timeout=120)
                    require(not self.running(self.trusted_container(identity)), "container_still_running")
            except BaseException:
                self.state.update(observed="failed", failure="stop_failed_container_may_be_running", container_running=None)
                try:
                    self.state["container_running"] = self.running(self.trusted_container(identity))
                except Exception:
                    pass
                self.save(emergency=True)
                raise
        self.state.update(observed="stopped", container_running=False, failure=None)
        self.save(emergency=True)

    def _select(self, identifier: str, boot_policy: str | None) -> None:
        d = self.deployment(identifier)
        self.check_mounts({"data"})
        self.host_guards()
        self.conflict_check()
        old = self.state.get("container")
        if old:
            require(not self.running(self.trusted_container(old)), "selected_container_running_stop_first")
        # Preserve stopped container identity for reselect, avoiding container name adoption.
        c = self.docker.inspect(d["container_name"])
        ident = None
        if c:
            if d.get("legacy"):
                self.validate_legacy_identity(c, d)
                ident = self.identity(c, d, legacy=True)
            else:
                ident = self.identity(c, d)
                self.trusted_container(ident)
        previous = self.state.get("selected") or self.state.get("last_selected")
        self.state = {**empty_state(), "selected": identifier, "last_selected": previous,
                      "container": ident, "boot_policy": boot_policy or "manual"}
        self.save()
        self.host_guards()

    def dispatch(self, action: str, deployment_id=None, boot_policy=None, dry_run=False, *, lease=None) -> dict:
        require(isinstance(action, str) and action in {
            'status', 'active', 'select', 'activate', 'start', 'restart',
            'stop', 'recover-stop', 'boot-stop', 'deactivate', 'boot-start'},
            'invalid_lifecycle_action')
        require(boot_policy is None or isinstance(boot_policy, str)
                and boot_policy in {'manual', 'resume'}, 'invalid_boot_policy')
        require(type(dry_run) is bool, 'invalid_dry_run')
        require(deployment_id is None or isinstance(deployment_id, str)
                and bool(ID_RE.fullmatch(deployment_id)), 'invalid_deployment_id')
        if action in {'select', 'activate'}:
            require(deployment_id is not None, 'invalid_deployment_id')
        if lease is not None:
            require(type(lease) is LifecycleLease, 'invalid_borrowed_lease')
            _validate_borrowed_lease(lease, system_root=self.lease_system_root, trusted_uid=self.trusted_uid)
        if self.recovery_only:
            require(action in {'stop', 'recover-stop', 'boot-stop', 'status', 'active'}, 'recovery_stop_only')
        if action in {"status", "active"}:
            return self.status()
        if dry_run:
            s = self.read_state()
            target = deployment_id or s.get("selected")
            if action in {"select", "activate", "start", "restart"}:
                require(target is not None, "no_deployment_selected_use_select")
                self.deployment(target)
            return {"dry_run": True, "action": action, "selected": target,
                    "model_file_deletion": "none", "image_deletion": "none",
                    "wait_for_readiness": True, "writes": False}
        with (nullcontext(lease) if lease is not None else acquire_lease(
                system_root=self.lease_system_root, trusted_uid=self.trusted_uid)) as active_lease:
            _validate_borrowed_lease(active_lease, system_root=self.lease_system_root, trusted_uid=self.trusted_uid)
            recovery_required = self.recovery_only
            if action in {'stop', 'recover-stop', 'boot-stop'}:
                try:
                    self.check_package_admission()
                except Exception:
                    # Root-approved narrow exception: only /run's already-owned
                    # immutable identity may be stopped if package state is unknown.
                    recovery_required = True
            else:
                self.check_package_admission()
            # Reading under lock is essential: another caller may have stopped/selected.
            if action == "recover-stop" or recovery_required:
                self.state = self.read_state(recovery=True)
                require(self.state.get("container") is not None, "no_recovery_identity")
            else:
                self.check_mounts({"data"}) if action not in {"stop", "deactivate", "boot-stop"} else None
                try:
                    self.state = self.read_state()
                except (LifecycleError, BindingError, OSError):
                    if action not in {"stop", "boot-stop", "deactivate"}:
                        raise
                    self.state = self.read_state(recovery=True)
                    require(self.state.get("container") is not None, "no_recovery_identity")
            if self.recovery_only:
                require(self.state.get('container') is not None, 'no_recovery_identity')
            try:
                if action in {"select", "activate"}:
                    self._select(deployment_id, boot_policy)
                elif action == "start":
                    self._start()
                elif action == "restart":
                    self._stop()
                    self._start()
                elif action in {"stop", "recover-stop", "boot-stop"}:
                    self._stop(preserve_intent=action == "boot-stop")
                elif action == "deactivate":
                    self._stop()
                    self.state["last_selected"] = self.state.get("selected")
                    self.state.update(selected=None, desired="stopped", boot_policy="manual", container=None)
                    self.save(emergency=True)
                elif action == "boot-start":
                    require(self.state.get("failure") != "recovery_journal_invalid_primary_used", "recovery_journal_invalid_no_boot_resume")
                    if self.state["selected"] and self.state["desired"] == "running" and self.state["boot_policy"] == "resume":
                        self._start()
                else:
                    raise LifecycleError("unsupported_lifecycle_action")
            except (LifecycleError, BindingError) as exc:
                if action in {"start", "restart", "boot-start"}:
                    self.state["observed"] = "failed"
                    self.state["failure"] = str(exc) if isinstance(exc, LifecycleError) else 'registered_storage_verification_failed'
                    self.save(emergency=True)
                raise
            result = copy.deepcopy(self.state)
            if result.get('state_persisted') is False:
                result['warning'] = 'restore_registered_storage_and_repeat_stop_before_reboot'
            return result


def add_commands(subparsers) -> None:
    for name in ("select", "activate", "start", "stop", "restart", "deactivate", "status", "active",
                 "boot-start", "boot-stop", "recover-stop", "list-deployments", "logs"):
        p = subparsers.add_parser(name, help="D2 declarative lifecycle")
        p.add_argument("--instance", type=Path, default=None)
        if name == "status":
            p.add_argument("--offline", action="store_true", help="inspect saved intent only; no Docker, API or host checks")
        if name in {"select", "activate"}:
            p.add_argument("deployment_id")
            p.add_argument("--boot-policy", choices=("manual", "resume"), default="manual")
            p.add_argument("--runtime", help="legacy plan compatibility; use deployment IDs for lifecycle")
        if name not in {"status", "active", "list-deployments"}:
            p.add_argument("--yes", action="store_true")
            p.add_argument("--dry-run", action="store_true")
        if name == "start":
            p.add_argument("--no-wait", action="store_true", help="deprecated; refused because readiness must be bounded and truthful")
        if name == "logs":
            p.add_argument("--tail", type=int, default=200)
        p.set_defaults(func=cli)


class StorageRunner:
    def run(self, argv, *, timeout=30):
        return run(argv, timeout=timeout)


def recovery_manager(config=REPO / 'configs'):
    """Bootstrap stop solely from the trusted volatile ownership record.

    No new owner is inferred from Docker names, env, profiles or missing disks.
    The canonical lease must already be held by a mutating caller.
    """
    journal = protected_json(Path('/run/llmctl/recovery.json'))
    identity = journal.get('container')
    require(isinstance(identity, dict), 'no_recovery_identity')
    manager = Manager(config, {'schema_version': 1, 'id': identity.get('instance')}, recovery_only=True)
    manager.validate_identity(identity)
    return manager


def load_manager(args, config, *, offline=False):
    binding = (RegisteredStorageBinding.read_registered(StorageRunner()) if offline else
               RegisteredStorageBinding.load(StorageRunner(), roles=('data',)))
    expected = Path(binding.path('data', 'services/llm-manager/deployment-instance.json'))
    require(args.instance is None or args.instance == expected, 'instance_path_must_match_registration')
    instance = protected_json(expected) if offline else binding.read_json('data', str(expected))
    return Manager(config, instance, binding=binding)


def cli(args: argparse.Namespace) -> int:
    def interrupted(_signum, _frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, interrupted)
    try:
        config = REPO / 'configs'
        if args.command == "list-deployments":
            print("\n".join(sorted(list(LEGACY) + [p.stem for p in (config / "deployments").glob("*.json")])))
            return 0
        if args.command not in {"status", "active"}:
            require(args.yes or args.dry_run, "mutation_requires_confirmation")
        if args.command == "logs":
            require(args.dry_run, "raw_logs_disabled_use_d3_reviewed_redaction")
            print("DRY-RUN: bounded Docker logs; raw log output disabled in manager")
            return 0
        require(not getattr(args, "no_wait", False), "no_wait_refused_use_bounded_start")
        if args.command in {'status', 'active'}:
            try:
                manager = load_manager(args, config, offline=getattr(args, 'offline', False))
            except (BindingError, LifecycleError, OSError):
                if getattr(args, 'offline', False):
                    result = {"schema_version": 2, "configured": False, "selected": None,
                              "desired": "stopped", "boot_policy": "manual", "recorded_observed": None,
                              "observed": None, "container_running": None,
                              "observation": "not_performed_offline"}
                    print(json.dumps(result, indent=2, sort_keys=True))
                    return 0
                print(json.dumps({**empty_state(), "observed": "failed", "container_running": None,
                                  "failure": "instance_missing_observation_unavailable"}, indent=2))
                return 1
            result = manager.offline_status() if getattr(args, 'offline', False) else manager.status()
        else:
            # The CLI owns exactly the same lease used by core.exclusive/Manager.
            # Read instance/transition state only after acquisition.
            with (nullcontext(None) if args.dry_run else acquire_lease()) as lease:
                try:
                    manager = load_manager(args, config)
                except (BindingError, LifecycleError, OSError):
                    if args.command not in {'stop', 'recover-stop', 'boot-stop'}:
                        raise
                    manager = recovery_manager(config)
                if getattr(args, 'runtime', None):
                    require(args.runtime == manager.deployment(args.deployment_id)['runtime'], 'runtime_profile_mismatch')
                result = manager.dispatch(args.command, getattr(args, 'deployment_id', None),
                                          getattr(args, 'boot_policy', None), args.dry_run, lease=lease)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except KeyboardInterrupt:
        print("FAIL: lifecycle_interrupted_use_status_then_stop", file=__import__("sys").stderr)
        return 130
    except (LifecycleError, BindingError, LeaseError, OSError, ValueError, KeyError, TypeError, IndexError, AttributeError) as exc:
        message = str(exc) if isinstance(exc, (LifecycleError, LeaseError)) else "invalid_configuration_or_io_failure"
        message += "; use --yes or --dry-run" if message == "mutation_requires_confirmation" else ""
        message += "; stop the other managed deployment first; see D2 handoff conflict procedure" if message == "conflicting_backend_stop_first" else ""
        print("FAIL: " + message, file=__import__("sys").stderr)
        return 1
