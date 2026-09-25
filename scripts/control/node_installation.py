"""Protected standalone node source/credential validation; no host mutation."""
from __future__ import annotations

import hmac
import json
import os
from pathlib import Path

from .installation import InstallationError, protected_file, _key

SOURCE_ROOT = Path('/usr/local/lib/llm-server/node-api')
CREDENTIAL_FILE = Path('/run/credentials/llm-node.service/control-api-key')
KEY_SOURCE = Path('/etc/llm-server/control-api-key')
SOURCE_FILES = (
    'scripts/control/__init__.py', 'scripts/control/installation.py',
    'scripts/control/http.py', 'scripts/control/node_serve.py',
    'scripts/control/node_installation.py', 'scripts/control/node.py',
    'scripts/control/node_collectors.py', 'scripts/control/passive.py',
    'scripts/control/node_actions.py',
)


def validate_installation():
    if os.geteuid() != 0:
        raise InstallationError()
    for relative in SOURCE_FILES:
        protected_file(SOURCE_ROOT / relative, root_device=Path('/').stat().st_dev)
    closure = json.loads(protected_file(SOURCE_ROOT / 'scripts/control/node-source-closure.json'))
    if closure != {'schema_version': 1, 'source_root': str(SOURCE_ROOT), 'files': list(SOURCE_FILES)}:
        raise InstallationError()
    credential = _key(protected_file(CREDENTIAL_FILE, modes={0o400, 0o600}, maximum=4096))
    source = _key(protected_file(KEY_SOURCE, modes={0o600}, maximum=4096))
    if not hmac.compare_digest(credential, source):
        raise InstallationError()
    return credential
