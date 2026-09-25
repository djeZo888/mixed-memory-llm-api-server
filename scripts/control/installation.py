"""Fixed installer-owned files. No environment/path/configuration overrides."""
from __future__ import annotations

import hmac
import json
import os
from pathlib import Path
import stat

SOURCE_ROOT = Path('/usr/local/lib/llm-server/control-api')
CONFIG_FILE = Path('/etc/llm-server/control.json')
KEY_SOURCE = Path('/etc/llm-server/control-api-key')
CREDENTIAL_FILE = Path('/run/credentials/llm-control.service/control-api-key')
# Import closure only. Model data, private instance, profiles and inference keys
# are not startup dependencies. Normal-only files are listed in source-closure.json.
RECOVERY_FILES = (
    'scripts/control/__init__.py', 'scripts/control/serve.py',
    'scripts/control/installation.py', 'scripts/control/adapter.py',
    'scripts/control/core.py', 'scripts/control/protocol.py',
    'scripts/control/journal.py', 'scripts/control/catalog.py',
    'scripts/control/discovery.py', 'scripts/control/http.py',
    'scripts/control/private_network.py',
    'scripts/common/lifecycle_lease.py',
    'scripts/lifecycle/__init__.py', 'scripts/lifecycle/manager.py',
    'scripts/lifecycle/runtime_io.py', 'scripts/lifecycle/storage_binding.py',
    'scripts/lifecycle/qwen_next.py', 'scripts/lifecycle/slot_state.py',
    'scripts/install/__init__.py',
    'scripts/install/storage.py',
)

NORMAL_FILES = (
    'scripts/control/node.py', 'scripts/control/node_observation.py',
    'scripts/control/node_actions.py', 'scripts/control/node_action_owner.py',
    'scripts/control/node_collectors.py', 'scripts/control/node_resources.py',
    'scripts/control/node_installation.py', 'scripts/control/node_serve.py',
    'scripts/control/node-source-closure.json', 'scripts/control/passive.py',
    'scripts/control/llm-node.service.in',
    'scripts/control/hardware_latch.py', 'scripts/lifecycle/hardware_policy.py',
    'scripts/lifecycle/boot_unit.py', 'scripts/control/source-closure.json',
    'scripts/install/storage_io.py', 'scripts/install/prerequisites.py',
    'scripts/common/require-data-mounted.sh', 'scripts/common/registered-storage.py',
    'scripts/lifecycle/sglang_file_auth.py',
    'reports/f1s-contract-evidence/f1a-qwen-manifest.json',
    'scripts/lifecycle/qwen38.py', 'scripts/lifecycle/concurrent_profiles.py',
    'scripts/runtime/qwen38_oci.py',
    'scripts/runtime/sglang38_file_auth.py', 'scripts/runtime/sglang38_pair_file_auth.py',
    'scripts/runtime/verify_adaptive_idle_overlay.py',
    'scripts/runtime/h005_runtime_binding.py', 'configs/runtimes/h005-runtime-binding.json',
    'scripts/runtime/adaptive_idle_sources.json', 'scripts/runtime/adaptive_idle_source_gate.py',
    'scripts/runtime/build_adaptive_idle_overlay.py',
    'scripts/runtime/adaptive_idle.py', 'scripts/runtime/adaptive_text.py',
    'scripts/runtime/adaptive_text_drain.py', 'scripts/runtime/adaptive_diffusion.py',
    'scripts/runtime/adaptive_diffusion_drain.py',
    'scripts/runtime/patches/text-adaptive-idle.patch',
    'scripts/runtime/patches/text-adaptive-drain.patch',
    'scripts/runtime/patches/text-adaptive-grammar.patch',
    'scripts/runtime/patches/diffusion-adaptive-idle.patch',
    'scripts/runtime/patches/diffusion-adaptive-drain.patch',
    'reports/q38r-source-weight-manifest.json',
    'reports/q38s-acquisition-manifest.json',
    'tests/lifecycle/sglang38_fixture/provenance.json',
    'tests/lifecycle/sglang38_fixture/run_fixture.py',
    'tests/lifecycle/sglang38_fixture/run_pinned_image.py',
    'tests/lifecycle/sglang38_fixture/auth_native.py',
    'tests/lifecycle/sglang38_fixture/chat_template.jinja',
    'tests/lifecycle/sglang38_fixture/cache_probe.py',
    'tests/lifecycle/sglang38_fixture/qwen38_config.json',
    'tests/lifecycle/sglang38_fixture/pair_launcher.py',
    'tests/lifecycle/sglang38_fixture/run_pair_fixture.py',
    'tests/lifecycle/sglang38_fixture/run_pair_pinned_image.py',
)


class InstallationError(Exception):
    def __init__(self):
        super().__init__('unsafe_or_missing_control_installation')


def protected_file(path, *, modes=None, maximum=1024 * 1024, uid=0,
                   root_device=None, boundary=Path('/')):
    """Bounded no-follow read with stable inode/metadata and protected parents.

    uid/boundary are in-process fixture parameters, never CLI/config fields.
    """
    path, boundary = Path(path), Path(boundary)
    fd = None
    try:
        if not path.is_absolute() or '..' in path.parts or not path.is_relative_to(boundary):
            raise InstallationError()
        for parent in path.parents:
            meta = parent.lstat()
            if (not stat.S_ISDIR(meta.st_mode) or meta.st_uid != uid or meta.st_mode & 0o022):
                raise InstallationError()
            if parent == boundary:
                break
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        meta = os.fstat(fd)
        mode = stat.S_IMODE(meta.st_mode)
        if (not stat.S_ISREG(meta.st_mode) or meta.st_uid != uid or meta.st_nlink != 1
                or meta.st_size > maximum or mode & 0o022
                or modes is not None and mode not in modes
                or root_device is not None and meta.st_dev != root_device):
            raise InstallationError()
        data = os.read(fd, maximum + 1)
        signature = lambda value: (value.st_dev, value.st_ino, value.st_mode, value.st_uid,
                                   value.st_nlink, value.st_size, value.st_mtime_ns, value.st_ctime_ns)
        if (len(data) != meta.st_size or signature(meta) != signature(os.fstat(fd))
                or signature(meta) != signature(path.lstat())):
            raise InstallationError()
        return data
    except (OSError, ValueError):
        raise InstallationError() from None
    finally:
        if fd is not None:
            os.close(fd)


def _key(raw):
    value = raw[:-1] if raw.endswith(b'\n') else raw
    if not 32 <= len(value) <= 256 or any(byte < 33 or byte > 126 for byte in value):
        raise InstallationError()
    return value


def _control_config(device):
    raw = protected_file(CONFIG_FILE, modes={0o600}, maximum=256, root_device=device)
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise InstallationError()
            value[key] = item
        return value
    try:
        config = json.loads(raw, object_pairs_hook=unique)
        if (type(config) is not dict or 'schema_version' not in config
                or set(config) - {'schema_version', 'advertised_endpoint_policy'}
                or type(config['schema_version']) is not int or config['schema_version'] != 1
                or ('advertised_endpoint_policy' in config
                    and config['advertised_endpoint_policy'] != 'private_network')):
            raise InstallationError()
    except (ValueError, UnicodeError):
        raise InstallationError() from None
    return config


def read_advertised_policy():
    """Optional DTO setting; exposure policy failure cannot block local recovery.

    Call only after validate_installation() has protected the import closure.
    No network policy file is required for control startup or trusted stop.
    Unrelated config/code integrity failures remain fatal.
    """
    config = _control_config(Path('/').stat().st_dev)
    if 'advertised_endpoint_policy' not in config:
        return None
    from .private_network import load_policy, PrivateNetworkError
    try:
        return load_policy()
    except PrivateNetworkError:
        return None


def validate_installation():
    if os.geteuid() != 0 or Path(__file__).resolve() != SOURCE_ROOT / 'scripts/control/installation.py':
        raise InstallationError()
    device = Path('/').stat().st_dev
    for relative in RECOVERY_FILES:
        protected_file(SOURCE_ROOT / relative, root_device=device)
    # Optional for recovery, but any present normal code must remain protected
    # on root too; a symlink into data is not a trusted executable dependency.
    for relative in NORMAL_FILES:
        path = SOURCE_ROOT / relative
        if path.exists() or path.is_symlink():
            protected_file(path, root_device=device)
    _control_config(device)
    source = _key(protected_file(KEY_SOURCE, modes={0o600}, maximum=257, root_device=device))
    credential = _key(protected_file(CREDENTIAL_FILE, modes={0o400, 0o600}, maximum=257))
    if not hmac.compare_digest(source, credential):
        raise InstallationError()
    return credential
