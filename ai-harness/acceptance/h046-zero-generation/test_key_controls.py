#!/usr/bin/env python3
"""Focused SOURCE fixtures. They cannot qualify Linux key creation/native life."""
import copy
import datetime as dt
import hashlib
import hmac
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import key_inventory as inventory
import ordinary_key_create as creator

NOW = 1780401600.0
FIXTURE_KEY = b'SOURCE_ONLY_' + b'F' * 20


def timestamp(delta):
    return dt.datetime.fromtimestamp(NOW + delta, dt.timezone.utc).isoformat()


def body():
    result = {key: {} for key in creator.FIELDS}
    result.update(schema=creator.SCHEMA, status='APPROVED', approvedBy='root',
                  authority='H046', goId='a' * 64, issuedUtc=timestamp(-10),
                  notBeforeUtc=timestamp(-5), dispatchCutoffUtc=timestamp(120),
                  expiresUtc=timestamp(180), invocations=1, retries=0,
                  counts={'createOrdinaryKey': 1, 'overwrite': 0, 'rotate': 0},
                  sourceCommit='1' * 40,
                  helper={'path': '/protected/ordinary_key_create.py', 'sha256': '2' * 64, 'uid': 0},
                  generalOwners={'qwen1': {}, 'qwen2': {}, 'mimo': {}},
                  application={'unit': 'ai-harness.service',
                               'unitFile': '/home/user/.config/systemd/user/ai-harness.service',
                               'unitSha256': '4' * 64, 'owner': {'uid': 1000, 'gid': 1000}},
                  target={'path': '/protected/ordinary.key', 'parentIdentity': {}, 'uid': 1000, 'gid': 1000},
                  claim={'path': '/protected/' + 'a' * 64 + '.ordinary-key-create.claim.json', 'parentIdentity': {}},
                  ordinaryAbsenceReview={'reviewedBy': 'root', 'status': 'WHOLLY_ABSENT_AT_EXACT_PATHS',
                                         'recognizedPaths': ['/protected/ordinary.key']})
    return result


def envelope(value):
    return {'body': value, 'seal': hmac.new(FIXTURE_KEY, inventory.canonical(value), hashlib.sha256).hexdigest()}


class KeyControls(unittest.TestCase):
    def validate(self, value, key=FIXTURE_KEY):
        return creator.validate_go(envelope(value), key, NOW,
            '/protected/ordinary_key_create.py', '2' * 64)

    def test_fresh_exact_hmac_control(self):
        self.assertEqual(len(FIXTURE_KEY), 32)
        self.assertEqual(self.validate(body())['counts']['createOrdinaryKey'], 1)

    def test_unsupported_generic_or_tampered_key_denied(self):
        for key in (b'x' * 31, b'x' * 33, b'x' * 32):
            with self.subTest(length=len(key)), self.assertRaises(inventory.InventoryError):
                self.validate(body(), key)
        packet = envelope(body()); packet['body']['sourceCommit'] = '3' * 40
        with self.assertRaises(inventory.InventoryError):
            creator.validate_go(packet, FIXTURE_KEY, NOW, '/protected/ordinary_key_create.py', '2' * 64)

    def test_stale_expired_bool_count_source_and_reserve_denied(self):
        for key, value in [('issuedUtc', timestamp(1)), ('expiresUtc', timestamp(-1)),
                           ('expiresUtc', timestamp(130)), ('invocations', True),
                           ('retries', 1), ('sourceCommit', 'NOT_SEALED')]:
            changed = body(); changed[key] = value
            with self.subTest(field=key), self.assertRaises(inventory.InventoryError):
                self.validate(changed)
        changed = body(); changed['helper']['sha256'] = '3' * 64
        with self.assertRaises(inventory.InventoryError): self.validate(changed)

    def test_duplicate_nonfinite_and_foreign_schema_denied(self):
        for raw in (b'{"body":1,"body":2}', b'{"value":NaN}'):
            with self.assertRaises(inventory.InventoryError): creator.strict_json(raw)
        changed = body(); changed['schema'] = 'historical-go-v1'
        with self.assertRaises(inventory.InventoryError): self.validate(changed)

    def test_root_private_body_is_same_finite_source_bound_go_without_generated_auth_key(self):
        value = body()
        self.assertEqual(creator.validate_body(value, NOW,
            '/protected/ordinary_key_create.py', '2' * 64), value)
        unapproved = copy.deepcopy(value); unapproved['status'] = 'UNAPPROVED'
        with self.assertRaises(inventory.InventoryError):
            creator.validate_body(unapproved, NOW, '/protected/ordinary_key_create.py', '2' * 64)
        future = copy.deepcopy(value); future['expiresUtc'] = '2026-10-02T17:00:00+00:00'
        with self.assertRaises(inventory.InventoryError):
            creator.validate_body(future, NOW, '/protected/ordinary_key_create.py', '2' * 64)

    def test_metadata_never_reads_keybytes_and_distinguishes_absence(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as name:
            directory = Path(name); directory.chmod(0o700)
            key = directory / 'native.key'; key.write_bytes(b'fixture-not-an-operational-secret')
            key.chmod(0o600)
            with patch.object(Path, 'read_bytes', side_effect=AssertionError('key bytes must not be read')):
                value = inventory.file_metadata(key, os.getuid())
                absent = inventory.file_metadata(directory / 'ordinary.key', os.getuid())
            self.assertEqual(value['state'], 'PRESENT')
            self.assertFalse(value['keyBytesRead'])
            self.assertEqual(absent['state'], 'ABSENT')
            self.assertNotIn('sha256', value)
            key.chmod(0o644)
            self.assertFalse(inventory.file_metadata(key, os.getuid())['protected32B'])

    def test_private_fixture_write_is_exclusive_and_preserves_original(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as name:
            directory = Path(name); directory.chmod(0o700)
            target = directory / 'ordinary.key'
            parent = inventory.identity(directory)
            creator.write_exclusive(target, parent, b'SOURCE_ONLY_' + b'X' * 20, os.getuid(), os.getgid())
            original = inventory.identity(target); raw = target.read_bytes()
            with self.assertRaises(FileExistsError):
                creator.write_exclusive(target, inventory.identity(directory), b'replacement', os.getuid(), os.getgid())
            self.assertEqual(inventory.identity(target), original)
            self.assertEqual(target.read_bytes(), raw)
            self.assertEqual(original['mode'], 0o600)
            self.assertEqual(original['size'], 32)

    def test_symlink_and_parent_inode_changed_denied(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as name:
            directory = Path(name); directory.chmod(0o700)
            existing = directory / 'native.key'; existing.write_bytes(b'x' * 32)
            existing.chmod(0o600); alias = directory / 'ordinary.key'; alias.symlink_to(existing)
            with self.assertRaises(inventory.InventoryError): inventory.file_metadata(alias, os.getuid())
            altered = inventory.identity(directory); altered['ino'] += 1
            with self.assertRaises(inventory.InventoryError):
                creator.write_exclusive(directory / 'other.key', altered, b'x', os.getuid(), os.getgid())
            self.assertFalse((directory / 'other.key').exists())

    def test_unit_paths_bounded_and_not_credentials(self):
        root = str(Path(__file__).parent.resolve())
        raw = ('ExecStart=' + root + '/deploy/run-server.sh --app-dir ' + root +
               ' --data-dir ' + root + '/private --codex-ordinary-entry-key ' + root +
               '/private/ordinary.key\n').encode()
        options = inventory.unit_options(raw)
        self.assertEqual(options['--codex-ordinary-entry-key'], root + '/private/ordinary.key')
        with self.assertRaises(inventory.InventoryError): inventory.unit_options(raw + raw)


    def test_exact_uid1000_private_key_and_root_go_roles(self):
        for uid, gid in [(1001, 1001), (0, 0), (1000, 1001)]:
            value = body(); value['application']['owner'].update(uid=uid, gid=gid)
            value['target'].update(uid=uid, gid=gid)
            with self.subTest(uid=uid, gid=gid), self.assertRaises(inventory.InventoryError):
                self.validate(value)
        with patch.object(creator, 'identity', return_value={'uid': 1000, 'mode': 0o600, 'nlink': 1}), \
             patch.object(creator, 'absolute', return_value=Path('/fixture/GO')), \
             patch.object(creator, 'ancestry'):
            with self.assertRaises(inventory.InventoryError): creator.private('/fixture/GO', 0)
        with patch.object(creator, 'identity', return_value={'uid': 0, 'mode': 0o755}), \
             patch.object(creator, 'absolute', return_value=Path('/fixture/key')), \
             patch.object(creator, 'ancestry'):
            with self.assertRaises(inventory.InventoryError): creator.check_parent('/fixture/key', {'uid': 0, 'mode': 0o755}, 0)

    def test_actual_cli_integer_exit_without_live_mutation(self):
        command = [sys.executable, str(Path(creator.__file__).resolve()), '--help']
        result = subprocess.run(command, capture_output=True, text=True, timeout=5)
        self.assertIs(type(result.returncode), int)
        self.assertEqual(result.returncode, 0)
        denied = subprocess.run(command[:-1] + ['--go', '/absent', '--go-key', '/absent'],
                                capture_output=True, text=True, timeout=5)
        self.assertIs(type(denied.returncode), int)
        self.assertEqual(denied.returncode, 1)
        self.assertNotIn(FIXTURE_KEY.decode(), denied.stdout + denied.stderr)


if __name__ == '__main__': unittest.main(verbosity=2)
