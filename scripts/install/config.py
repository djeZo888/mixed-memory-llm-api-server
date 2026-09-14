"""Strict public configuration. No command strings, secrets or execution hooks."""
from __future__ import annotations
import json
from pathlib import Path
import re
from urllib.parse import urlsplit
from .core import InstallError

DEFAULTS = {"schema_version": 1, "role": "server", "profile": None, "model_set": None,
    "data_dir": "/data", "data_uuid": None, "model_dir": None, "model_uuid": None,
    "storage_mode": "existing", "initialize_empty_disk": None, "confirm_disk_id": None,
    "disk_plan": None, "expected_gpu_count": 2, "root_min_free_bytes": 4294967296,
    "root_package_budget_bytes": 2147483648, "client_user": None, "client_workspace": None,
    "client_prefix": None, "client_base_url": None, "client_model": None, "client_key_file": None,
    "context_tokens": 8192, "output_tokens": 2048, "ssh_host": None}
PROFILES = {"flagship-hybrid": "glm", "fast-gpu": "qwen"}
MODELS = {"glm": "reports/r2-flagship-artifact.json", "qwen": "reports/f1a-qwen-manifest.json"}


def absolute(value):
    return isinstance(value, str) and bool(re.fullmatch(r"/[A-Za-z0-9_./-]+", value)) and ".." not in Path(value).parts and str(Path(value)) == value and value != "/" and not value.startswith("//")


def validate(value):
    if not isinstance(value, dict) or set(value) - set(DEFAULTS):
        raise InstallError("unknown_config_fields")
    c = {**DEFAULTS, **value}
    if type(c["schema_version"]) is not int or c["schema_version"] != 1:
        raise InstallError("unsupported_config_schema")
    for key, default in DEFAULTS.items():
        if key not in {"schema_version", "expected_gpu_count", "root_min_free_bytes", "root_package_budget_bytes", "context_tokens", "output_tokens"}:
            if c[key] is not None and not isinstance(c[key], str):
                raise InstallError("invalid_config_field_type")
    if c["data_dir"] is None:
        raise InstallError("invalid_absolute_path")
    if c["role"] not in {"server", "client", "combined"}:
        raise InstallError("invalid_role")
    if c["role"] != "client":
        if c["profile"] not in PROFILES or c["model_set"] not in ("glm", "qwen", "glm,qwen"):
            raise InstallError("explicit_profile_and_model_set_required")
        if PROFILES[c["profile"]] not in c["model_set"].split(","):
            raise InstallError("profile_not_in_selected_model_set")
    if c["storage_mode"] not in {"existing", "mount", "initialize"}:
        raise InstallError("invalid_storage_mode")
    for key in ("data_dir", "model_dir", "disk_plan", "client_workspace", "client_prefix", "client_key_file"):
        if c[key] is not None and not absolute(c[key]):
            raise InstallError("invalid_absolute_path")
    c["model_dir"] = c["model_dir"] or c["data_dir"] + "/models"
    if any(c["data_dir"] == x or c["data_dir"].startswith(x + "/") for x in ("/etc", "/usr", "/boot", "/dev", "/proc", "/sys", "/run", "/tmp", "/var", "/root", "/home")):
        raise InstallError("unsafe_data_location")
    for key in ("data_uuid", "model_uuid"):
        if c[key] is not None and not (isinstance(c[key], str) and re.fullmatch(r"[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12}", c[key])):
            raise InstallError("invalid_filesystem_uuid")
    if c["storage_mode"] == "mount" and not c["data_uuid"]:
        raise InstallError("mount_requires_explicit_uuid")
    if c["storage_mode"] == "initialize":
        disk = c["initialize_empty_disk"]
        if not isinstance(disk, str) or not re.fullmatch(r"/dev/disk/by-id/[A-Za-z0-9_.:-]+", disk) or Path(disk).name != c["confirm_disk_id"]:
            raise InstallError("stable_disk_identity_confirmation_required")
    elif any(c[k] is not None for k in ("initialize_empty_disk", "confirm_disk_id", "disk_plan")):
        raise InstallError("disk_flags_require_initialize_mode")
    for key, low, high in (("expected_gpu_count", 1, 16), ("root_min_free_bytes", 4294967296, 1099511627776),
                          ("root_package_budget_bytes", 0, 4294967296), ("context_tokens", 1024, 131072), ("output_tokens", 1, 32768)):
        if type(c[key]) is not int or not low <= c[key] <= high:
            raise InstallError("invalid_numeric_config")
    if c["output_tokens"] >= c["context_tokens"]:
        raise InstallError("output_exceeds_context")
    if c["role"] in {"client", "combined"}:
        if not isinstance(c["client_user"], str) or not re.fullmatch(r"[a-z_][a-z0-9_-]{0,31}", c["client_user"]) or c["client_user"] == "root":
            raise InstallError("ordinary_client_user_required")
        if any(not c[k] for k in ("client_workspace", "client_prefix", "client_base_url", "client_model", "client_key_file")):
            raise InstallError("explicit_client_settings_required")
        try:
            url = urlsplit(c["client_base_url"])
            if url.scheme != "http" or url.hostname not in {"127.0.0.1", "localhost", "::1"} or not url.port or url.path != "/v1" or url.username or url.password or url.query or url.fragment:
                raise ValueError()
        except (ValueError, TypeError):
            raise InstallError("client_requires_literal_loopback_url") from None
        if not re.fullmatch(r"[A-Za-z0-9_.:/-]{1,128}", c["client_model"]):
            raise InstallError("invalid_client_model")
    if c["ssh_host"] is not None and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.@-]{0,250}", c["ssh_host"]):
        raise InstallError("invalid_ssh_host")
    return c


def load(path):
    try:
        text = Path(path).read_text()
        if len(text) > 65536:
            raise ValueError()
        def unique(pairs):
            obj = {}
            for k, v in pairs:
                if k in obj:
                    raise ValueError()
                obj[k] = v
            return obj
        return json.loads(text, object_pairs_hook=unique)
    except (OSError, ValueError):
        raise InstallError("invalid_config_file") from None
