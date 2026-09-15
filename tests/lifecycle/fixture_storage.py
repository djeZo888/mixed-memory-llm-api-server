"""Explicit host-I/O substitutes for retained D2/F1S tests, never live guards.

This writer intentionally does NOT establish the I1b anchored-write race gate.
"""
from contextlib import contextmanager
import copy
import json
import os
from pathlib import Path
import re

from lifecycle.storage_binding import BindingError


class HistoricalBinding:
    def __init__(self):
        self.registry = {
            'schema_version': 1,
            'data': {'path': '/data', 'mount': '/data', 'uuid': 'synthetic-data', 'fstype': 'ext4'},
            'models': {'path': '/data/models-large', 'mount': '/data/models-large', 'uuid': 'synthetic-models', 'fstype': 'ext4'},
            'roots': {name: '/data/' + suffix for name, suffix in {
                'services': 'services', 'logs': 'logs', 'docker': 'docker', 'containerd': 'containerd',
                'hf_cache': 'hf-cache', 'build': 'build', 'backups': 'backups',
                'secrets': 'services/secrets', 'state': 'services/installer'}.items()},
        }
        self.registry['roots']['models'] = '/data/models-large'
        self.identity = copy.deepcopy(self.registry)

    def path(self, role, suffix=''):
        if role not in {'data', 'models', *self.registry['roots']} or not isinstance(suffix, str) or (suffix and
                (not re.fullmatch(r'[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*', suffix)
                 or any(p in {'.', '..'} for p in suffix.split('/')))):
            raise BindingError('invalid_storage_suffix')
        root = (self.registry[role]['path'] if role in {'data', 'models'}
                else self.registry['roots'][role])
        return root + ('/' + suffix if suffix else '')

    def verify(self, roles=('data', 'models')):
        return copy.deepcopy(self.registry)

    @contextmanager
    def mounted_guard(self, storage_io, roles=('data', 'models')):
        # Explicit synthetic guard only. Real guard integration has a separate gate.
        yield lambda: self.verify(roles=roles)

    def validate_path(self, role, path):
        return Path(path)


class FixtureWriter:
    """Tiny worker files only; not an anchored storage implementation."""
    class AnchoredRoot:
        def __init__(self, path, guard, *, uid=0):
            self.path, self.guard = Path(path), guard

        def __enter__(self):
            self.check()
            return self

        def __exit__(self, *args):
            return False

        def check(self):
            return self.guard()

        def mkdir(self, relative, mode=0o700, parents=True):
            (self.path / relative).mkdir(parents=parents, exist_ok=True, mode=mode)

        def atomic_json(self, relative, value):
            self.check()
            p = self.path / relative
            p.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            p.write_text(json.dumps(value))
            p.chmod(0o600)
            self.check()
