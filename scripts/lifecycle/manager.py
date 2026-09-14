"""Serialized, declarative lifecycle. Docker is the runtime; systemd only replays intent.

All live I/O is injectable for deterministic worker tests. Production has no
LLMCTL_SKIP_* bypass. Files in this package are D2 owned.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import copy
import fcntl
import json
import os
from pathlib import Path
import re
import signal
import stat
import tempfile
import time
from typing import Any

from .runtime_io import (Docker, LifecycleError, probe, run,
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


def atomic_json(path: Path, value: dict) -> None:
    """Unique temporary file, file fsync, atomic rename and directory fsync."""
    require(path.parent.resolve() == path.parent, "unsafe_state_parent_symlink")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    require(not path.is_symlink(), "unsafe_state_symlink")
    fd, tmp = tempfile.mkstemp(prefix=".llmctl-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            os.fchmod(stream.fileno(), 0o600)
            json.dump(value, stream, sort_keys=True, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


@contextmanager
def process_lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        require(stat.S_ISREG(os.fstat(fd).st_mode), "invalid_lock")
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


def transition_in_progress(path: Path) -> bool:
    """Cheap nonblocking observation; never infer startup from stale state alone."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError:
        return False
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return False
        except BlockingIOError:
            return True
    finally:
        os.close(fd)


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
                 monotonic_fn=time.monotonic, test_paths=False):
        self.config_root, self.instance = Path(config_root), copy.deepcopy(instance)
        self.docker = docker if docker is not None else Docker()
        self.probe, self.run, self.sleep, self.monotonic = probe_fn, run_fn, sleep_fn, monotonic_fn
        require(instance.get("schema_version") == 1, "invalid_instance_version")
        require(bool(ID_RE.fullmatch(str(instance.get("id", "")))), "invalid_instance_id")
        paths = instance.get("paths", {})
        self.state_file = Path(paths.get("state", "/data/services/llm-manager/active")) / "active.json"
        self.lock_file = Path(paths.get("lock", "/run/llmctl/lifecycle.lock"))
        self.recovery_file = Path(paths.get("recovery", "/run/llmctl/recovery.json"))
        if not test_paths:
            require(self.state_file.parent == Path("/data/services/llm-manager/active"), "unsafe_state_path")
            require(self.lock_file == Path("/run/llmctl/lifecycle.lock"), "unsafe_lock_path")
            require(self.recovery_file == Path("/run/llmctl/recovery.json"), "unsafe_recovery_path")
        self.test_paths = test_paths
        self.state = empty_state()

    def deployment(self, identifier: str) -> dict:
        require(isinstance(identifier, str) and bool(ID_RE.fullmatch(identifier)), "invalid_deployment_id")
        if identifier in LEGACY:
            return legacy_profile(identifier)
        d = read_json(self.config_root / "deployments" / (identifier + ".json"))
        require(d.get("id") == identifier and d.get("schema_version") == 1, "invalid_deployment")
        for kind, field in (("models", "model"), ("runtimes", "runtime")):
            name = d.get(field)
            require(isinstance(name, str) and bool(ID_RE.fullmatch(name)), "invalid_profile_id")
            value = read_json(self.config_root / kind / (name + ".json"))
            require(value.get("id") == name and value.get("schema_version") == 1, "invalid_profile")
            d["_" + field] = value
        self.validate_deployment(d)
        return d

    def validate_deployment(self, d: dict) -> None:
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
        require(auth.get("key_file", "").startswith("/data/services/secrets/"), "unsafe_key_path")
        mounts = d.get("mounts", [])
        require(len(mounts) == 5, "invalid_mount_contract")
        targets = set()
        for m in mounts:
            source, target = Path(m["source"]), Path(m["target"])
            require(source.is_absolute() and target.is_absolute() and ".." not in source.parts
                    and ".." not in target.parts and "," not in str(source), "unsafe_mount_path")
            require(m["required_mount"] in {"/data", "/data/models-large"}, "missing_required_mount")
            require(source.is_relative_to(Path(m["required_mount"])) and source != Path(m["required_mount"]), "mount_outside_data")
            require(str(target) not in targets and type(m["read_only"]) is bool, "duplicate_mount_target")
            targets.add(str(target))
        require(targets == {"/models", "/cache", "/logs", "/service", auth["container_key_file"]}, "invalid_mount_targets")
        by_target = {m["target"]: m for m in mounts}
        for role, target in (("model", "/models"), ("cache", "/cache"), ("logs", "/logs"), ("service", "/service")):
            require(d["paths"][role] == by_target[target]["source"], "path_mount_mismatch")
        require(by_target["/models"]["read_only"] and by_target[auth["container_key_file"]]["read_only"], "writable_model_or_key")
        require(by_target[auth["container_key_file"]]["source"] == auth["key_file"], "key_mount_mismatch")
        require(d["paths"]["model"] == d["_model"]["model_root"], "model_root_mismatch")
        for role, root in (("model", "/data/models-large"), ("cache", "/data/models-large/runtime-cache"),
                           ("logs", "/data/logs/llmctl"), ("service", "/data/services/llm-manager")):
            require(Path(d["paths"][role]).is_relative_to(root) and Path(d["paths"][role]) != Path(root), "unsafe_role_mount")
        require(auth["container_key_file"] == "/run/secrets/llm-api-key", "unsafe_container_key_path")
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

    def check_mounts(self, targets=None) -> None:
        """findmnt exact targets/UUIDs, never a parent fallback or same root device."""
        mounts = self.instance.get("required_mounts", [])
        require(isinstance(mounts, list) and {m.get("target") for m in mounts} == {"/data", "/data/models-large"}
                and len(mounts) == 2, "missing_mount_contract")
        root = json.loads(self.run(["findmnt", "--json", "--output", "TARGET,UUID,FSTYPE,MAJ:MIN", "--target", "/"]))["filesystems"][0]
        seen = {root["maj:min"]}
        for m in sorted(mounts, key=lambda x: len(x["target"])):
            if targets is not None and m["target"] not in targets:
                continue
            require(isinstance(m.get("uuid"), str) and bool(re.fullmatch(r"[a-fA-F0-9-]{36}", m["uuid"])), "missing_mount_uuid")
            raw = self.run(["findmnt", "--json", "--output", "TARGET,UUID,FSTYPE,MAJ:MIN", "--target", m["target"]])
            rows = json.loads(raw).get("filesystems", [])
            require(len(rows) == 1, "unmounted_required_disk")
            live = rows[0]
            require(live.get("target") == m["target"], "unmounted_required_disk")
            require(live.get("uuid", "").lower() == m["uuid"].lower(), "wrong_mount_uuid")
            require(live.get("fstype") == m.get("filesystem") and live.get("maj:min") not in seen, "unsafe_mount_device")
            seen.add(live["maj:min"])

    def host_guards(self) -> None:
        self.run([str(REPO / "scripts/common/require-data-mounted.sh")], timeout=120)
        self.run([str(REPO / "scripts/common/root-disk-guard.sh"), "--report",
                  "/data/logs/llmctl-root-disk-guard.md"], timeout=300)

    def check_artifacts(self, d: dict) -> None:
        if d.get("legacy"):
            root = Path(d["paths"]["model"])
            require(root.is_dir() and (root / "config.json").is_file()
                    and any(root.glob("*.safetensors")), "legacy_model_files_missing")
            return
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
            require(path.resolve() == path and path.is_file(), "artifact_missing_or_symlink")
            require(path.stat().st_size == a["size_bytes"], "artifact_size_mismatch")
        verified = self.instance.get("model_integrity", {}).get(d["model"], {})
        require(verified.get("verified") is True and verified.get("revision") == model["revision"]
                and bool(verified.get("evidence")), "d1_integrity_evidence_required")

    def image_evidence(self, d: dict) -> dict:
        e = self.instance.get("runtime_evidence", {}).get(d["runtime"], {})
        require(bool(DIGEST_RE.fullmatch(str(e.get("image_id", "")))), "d1_image_id_required")
        require(e.get("flags_verified") is True and bool(e.get("evidence")), "d1_flag_evidence_required")
        require(set(d["_runtime"]["required_cli_flags"]).issubset(set(e.get("supported_flags", []))), "d1_supported_flags_required")
        require(e.get("load_mode") in {"auto", "none", "mmap", "mlock", "mmap+mlock", "dio"}, "d1_load_mode_required")
        return e

    def read_state(self, recovery=False) -> dict:
        path = self.recovery_file if recovery else self.state_file
        if not path.exists():
            if not recovery and self.recovery_file.exists():
                return self.read_state(recovery=True)
            # One-time previous llmctl location; a v2 tombstone always wins.
            legacy = self.state_file.parent.parent / "state" / "active.json"
            if not recovery and legacy.exists():
                path = legacy
            else:
                return empty_state()
        s = read_json(path)
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
        require(s.get("desired") in {"running", "stopped"} and s.get("boot_policy") in {"manual", "resume"}
                and s.get("observed") in {"stopped", "starting", "ready", "unhealthy", "failed"}, "invalid_state")
        require(s.get("selected") is None or isinstance(s.get("selected"), str)
                and bool(ID_RE.fullmatch(s["selected"])), "invalid_state_selection")
        require(s.get("selected") is not None or s.get("desired") == "stopped", "invalid_empty_intent")
        if s.get("container"):
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
        if not recovery and self.recovery_file.exists():
            try:
                journal = self.read_state(recovery=True)
            except (LifecycleError, OSError):
                journal = {}
                s["failure"] = "recovery_journal_invalid_primary_used"
            if journal.get("updated_at", 0) > s.get("updated_at", 0) and journal.get("state_persisted") is False:
                return journal
        # Never relay arbitrary state-file strings/extra fields to stdout/reports.
        allowed = set(empty_state()) | {"updated_at", "migrated_from", "last_selected", "state_persisted"}
        return {k: v for k, v in s.items() if k in allowed}

    def save(self, *, emergency=False) -> None:
        self.state["updated_at"] = time.time_ns()
        # A best-effort /run journal enables stop even when /data is unavailable.
        # Shutdown proceeds even if both journal writes fail.
        try:
            atomic_json(self.recovery_file, self.state)
        except (OSError, LifecycleError):
            if not emergency:
                raise
        try:
            self.check_mounts({"/data"})
            self.state["state_persisted"] = True
            atomic_json(self.state_file, self.state)
        except (LifecycleError, OSError):
            self.state["state_persisted"] = False
            if not emergency:
                raise
        try:
            atomic_json(self.recovery_file, self.state)
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
            names.add(read_json(path).get("container_name"))
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
            code = self.probe(self.endpoint(d), d["endpoint"]["served_model"],
                              d.get("auth", {}).get("key_file"), require_auth=not d.get("legacy", False),
                              timeout=d["launch"]["request_timeout_seconds"])
            was_starting = s["observed"] == "starting"
            s["observed"] = "ready" if code == "ready" and health != "unhealthy" else "unhealthy"
            if code == "not_ready" and health != "unhealthy" and was_starting and transition_in_progress(self.lock_file):
                s["observed"] = "starting"
            if s["desired"] == "stopped":
                s["failure"] = "unexpected_running_container_stop_first"
        except (LifecycleError, OSError, ValueError, KeyError, TypeError):
            s["observed"] = "unhealthy"
            if "container_running" not in s:
                s["container_running"] = None
        return s

    def offline_status(self) -> dict:
        """Read saved intent only. Never inspect Docker, API, key or model files."""
        saved = self.read_state()
        return {"schema_version": 2, "configured": True,
                "selected": saved["selected"], "desired": saved["desired"],
                "boot_policy": saved["boot_policy"],
                "recorded_observed": saved["observed"], "observed": None,
                "container_running": None, "observation": "not_performed_offline"}

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
        self.check_mounts({"/data"} if d.get("legacy") else None)
        self.host_guards()
        require(self.instance.get("obsolete_boot_owner_disabled") is True
                and bool(self.instance.get("obsolete_boot_owner_evidence")), "obsolete_boot_owner_removal_required")
        self.check_artifacts(d)
        if not d.get("legacy"):
            self.image_evidence(d)
            validate_key_metadata(d["auth"]["key_file"])
            for m in d["mounts"]:
                source = Path(m["source"])
                require(source.resolve() == source and source.exists(), "mount_source_missing_or_symlink")
                if m["target"] != d["auth"]["container_key_file"]:
                    require(source.is_dir(), "mount_source_not_directory")
        require(self.docker.capture("info", "--format", "{{.DockerRootDir}}").strip() == "/data/docker", "docker_root_outside_data")

    def create_args(self, d: dict) -> list[str]:
        e = self.image_evidence(d)
        launch, rt = d["launch"], d["_runtime"]
        image = json.loads(self.docker.capture("image", "inspect", rt["image_tag"]))
        require(len(image) == 1 and image[0].get("Id") == e["image_id"], "runtime_image_id_mismatch")
        require(image[0].get("Config", {}).get("Entrypoint") == rt["entrypoint"], "runtime_entrypoint_mismatch")
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
        require(set(rt.get("environment", {})).issubset({"LD_LIBRARY_PATH", "LLAMA_ARG_HOST", "XDG_CACHE_HOME"}), "unsafe_runtime_environment")
        for key, value in rt.get("environment", {}).items():
            args += ["--env", key + "=" + value]
        args += [e["image_id"]] + self.launch_command(d, e)
        return args

    @staticmethod
    def launch_command(d: dict, e: dict) -> list[str]:
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
        """A valid model alias cannot distinguish 8K from 32K; verify launch too."""
        e = self.image_evidence(d)
        require(c.get("Image") == e["image_id"], "runtime_image_id_mismatch")
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
                    new_id = self.docker.create(self.create_args(d))
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
                self.docker.start(c["Id"])
            self.state["container_running"] = True
            self.save()
            deadline = self.monotonic() + d["launch"]["timeout_seconds"]
            last = "not_ready"
            while self.monotonic() < deadline:
                c = self.trusted_container(self.state["container"])
                require(self.running(c), "container_exited_during_start")
                self.network_check(c, d)
                last = self.probe(self.endpoint(d), d["endpoint"]["served_model"],
                                  d.get("auth", {}).get("key_file"), require_auth=not d.get("legacy", False),
                                  timeout=min(d["launch"]["request_timeout_seconds"], max(0.1, deadline - self.monotonic())))
                if last == "ready" and c.get("State", {}).get("Health", {}).get("Status") != "unhealthy":
                    self.host_guards()
                    self.check_mounts({"/data"} if d.get("legacy") else None)
                    self.state.update(observed="ready", container_running=True, failure=None)
                    self.save()
                    return
                if last in {"auth_error", "wrong_model"}:
                    raise LifecycleError(last)
                self.sleep(min(d["launch"]["poll_seconds"], max(0, deadline - self.monotonic())))
            raise LifecycleError("readiness_timeout")
        except BaseException:
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
        self.check_mounts({"/data"})
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

    def dispatch(self, action: str, deployment_id=None, boot_policy=None, dry_run=False) -> dict:
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
        with process_lock(self.lock_file):
            # Reading under lock is essential: another caller may have stopped/selected.
            if action == "recover-stop":
                self.state = self.read_state(recovery=True)
                require(self.state.get("container") is not None, "no_recovery_identity")
            else:
                self.check_mounts({"/data"}) if action not in {"stop", "deactivate", "boot-stop"} else None
                try:
                    self.state = self.read_state()
                except (LifecycleError, OSError):
                    if action not in {"stop", "boot-stop", "deactivate"}:
                        raise
                    self.state = self.read_state(recovery=True)
                    require(self.state.get("container") is not None, "no_recovery_identity")
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
            except LifecycleError as exc:
                if action in {"start", "restart", "boot-start"}:
                    self.state["observed"] = "failed"
                    self.state["failure"] = str(exc)
                    self.save(emergency=True)
                raise
            return copy.deepcopy(self.state)


def add_commands(subparsers) -> None:
    for name in ("select", "activate", "start", "stop", "restart", "deactivate", "status", "active",
                 "boot-start", "boot-stop", "recover-stop", "list-deployments", "logs"):
        p = subparsers.add_parser(name, help="D2 declarative lifecycle")
        p.add_argument("--instance", type=Path, default=Path(os.environ.get("LLMCTL_INSTANCE", "/data/services/llm-manager/deployment-instance.json")))
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


def cli(args: argparse.Namespace) -> int:
    def interrupted(_signum, _frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, interrupted)
    try:
        config = Path(os.environ.get("LLMCTL_CONFIG_ROOT", REPO / "configs"))
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
        if args.command == "status" and args.offline:
            if args.instance.exists():
                result = Manager(config, read_json(args.instance)).offline_status()
            else:
                result = {"schema_version": 2, "configured": False, "selected": None,
                          "desired": "stopped", "boot_policy": "manual", "recorded_observed": None,
                          "observed": None, "container_running": None,
                          "observation": "not_performed_offline"}
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0
        if not args.instance.exists() and args.command in {"status", "active"}:
            # Never infer an active model when the instance is absent.
            print(json.dumps({**empty_state(), "observed": "failed", "container_running": None, "failure": "instance_missing_observation_unavailable"}, indent=2))
            return 1
        manager = Manager(config, read_json(args.instance))
        if getattr(args, "runtime", None):
            require(args.runtime == manager.deployment(args.deployment_id)["runtime"], "runtime_profile_mismatch")
        result = manager.dispatch(args.command, getattr(args, "deployment_id", None),
                                  getattr(args, "boot_policy", None), getattr(args, "dry_run", False))
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except KeyboardInterrupt:
        print("FAIL: lifecycle_interrupted_use_status_then_stop", file=__import__("sys").stderr)
        return 130
    except (LifecycleError, OSError, ValueError, KeyError, TypeError, IndexError, AttributeError) as exc:
        message = str(exc) if isinstance(exc, LifecycleError) else "invalid_configuration_or_io_failure"
        message += "; use --yes or --dry-run" if message == "mutation_requires_confirmation" else ""
        message += "; stop the other managed deployment first; see D2 handoff conflict procedure" if message == "conflicting_backend_stop_first" else ""
        print("FAIL: " + message, file=__import__("sys").stderr)
        return 1
