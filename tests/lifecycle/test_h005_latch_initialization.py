"""Once-only latch initialization with real local anchored writers and leases.

Linux mount discovery/UID use LocalStorageFixture seams. No VM, GPU, service,
installer execution, protected production path or live acceptance is involved.
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from tests.lifecycle.test_real_storage_io import LocalStorageFixture, real_io
from tests.test_hardware_latch import BOOT, inventory
from common.lifecycle_lease import LeaseError
from control.hardware_latch import HardwareLatch, empty_state
from lifecycle.hardware_policy import (GPU_UUIDS, INITIALIZATION_REVIEW_SUFFIX,
    INITIALIZATION_SUFFIX, RegisteredLatchStore, STATE_SUFFIX, read_latch_status)
from lifecycle.runtime_io import LifecycleError


class FirstInstall(unittest.TestCase):
    def setUp(self):
        self.fixture = LocalStorageFixture()
        self.addCleanup(self.fixture.close)
        original_verify = self.fixture.storage.verify
        verify = patch.object(self.fixture.storage, 'verify',
            side_effect=lambda registration=None, **kwargs: original_verify(registration))
        verify.start()
        self.addCleanup(verify.stop)
        self.review = {'schema_version': 1, 'kind': 'h005-latch-first-install',
                       'status': 'REVIEWED_NO_PRIOR_STATE', 'reviewed_source_commit': 'a' * 40,
                       'absence_evidence_sha256': 'b' * 64}
        self.review_path = self.path(INITIALIZATION_REVIEW_SUFFIX)
        self.state_path = self.path(STATE_SUFFIX)
        self.marker_path = self.path(INITIALIZATION_SUFFIX)
        self.fixture.jsonfile(self.review_path, self.review)
        self.owner = self.fixture.lease()
        self.lease = self.owner.__enter__()
        self.addCleanup(self.owner.__exit__, None, None, None)
        self.store = RegisteredLatchStore(self.fixture.binding, lease=self.lease,
            storage_io=self.fixture.api, system_root=self.fixture.base, trusted_uid=os.geteuid())

    def path(self, suffix):
        return Path(self.fixture.binding.path('services', suffix))

    def assert_uninitialized(self):
        self.assertFalse(self.state_path.exists())
        self.assertFalse(self.marker_path.exists())

    def test_review_missing_invalid_or_not_protected_refuses_before_write(self):
        self.review_path.unlink()
        with self.assertRaises(Exception):
            self.store.initialize()
        self.assert_uninitialized()
        for field, bad in (('schema_version', True), ('kind', 'other'), ('status', 'UNREVIEWED'),
                           ('reviewed_source_commit', 'main'), ('absence_evidence_sha256', 'not-a-hash'),
                           ('extra', True)):
            review = {**self.review, field: bad}
            self.fixture.jsonfile(self.review_path, review)
            with self.subTest(field=field), self.assertRaises(LifecycleError):
                self.store.initialize()
            self.assert_uninitialized()
        self.fixture.jsonfile(self.review_path, self.review)
        self.review_path.chmod(0o666)
        with self.assertRaises(Exception):
            self.store.initialize()
        self.assert_uninitialized()

    def test_once_only_success_is_empty_unknown_and_marker_binds_review(self):
        self.assertEqual(self.store.initialize(), empty_state())
        self.assertEqual(json.loads(self.state_path.read_text()), empty_state())
        marker = json.loads(self.marker_path.read_text())
        self.assertEqual(marker, {'schema_version': 1, 'kind': 'h005-latch-initialization',
            'review_sha256': hashlib.sha256(json.dumps(self.review, sort_keys=True,
                separators=(',', ':')).encode()).hexdigest()})
        for path in (self.state_path, self.marker_path):
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(path.stat().st_nlink, 1)
        status = read_latch_status(self.fixture.binding, [GPU_UUIDS[0]], current_boot_id=BOOT)
        self.assertIsNone(status['hardware_latched'])
        self.assertEqual(status['reason'], 'hardware_latch_unknown')
        before = self.state_path.read_bytes(), self.marker_path.read_bytes()
        with self.assertRaisesRegex(LifecycleError, 'already_initialized_or_present'):
            self.store.initialize()
        self.assertEqual((self.state_path.read_bytes(), self.marker_path.read_bytes()), before)

    def test_marker_survives_deleted_state_and_never_reinitializes(self):
        self.store.initialize()
        marker = self.marker_path.read_bytes()
        self.state_path.unlink()
        with self.assertRaisesRegex(LifecycleError, 'already_initialized_or_present'):
            self.store.initialize()
        self.assertEqual(self.marker_path.read_bytes(), marker)
        self.assertFalse(self.state_path.exists())

    def test_ordinary_write_cannot_bootstrap_missing_or_replace_corrupt_state(self):
        with self.assertRaises(Exception):
            self.store.write(empty_state())
        self.assert_uninitialized()
        self.store.initialize()
        self.state_path.write_text('{"schema_version":99}\n')
        before = self.state_path.read_bytes()
        with self.assertRaises(Exception):
            self.store.write(empty_state())
        self.assertEqual(self.state_path.read_bytes(), before)
        self.state_path.unlink()
        with self.assertRaises(Exception):
            self.store.write(empty_state())
        self.assertFalse(self.state_path.exists())

    def test_existing_positive_state_is_preserved_without_creating_marker(self):
        latch = HardwareLatch()
        for second in (0, 5):
            latch.observe(GPU_UUIDS[0], inventory(second, uuids=[]),
                          current_boot_id=BOOT, boot_age_seconds=150)
        state = latch.export_state()
        self.assertTrue(state['targets'][GPU_UUIDS[0]]['hardware_latched'])
        self.fixture.jsonfile(self.state_path, state)
        before = self.state_path.read_bytes()
        with self.assertRaisesRegex(LifecycleError, 'already_initialized_or_present'):
            self.store.initialize()
        self.assertEqual(self.state_path.read_bytes(), before)
        self.assertFalse(self.marker_path.exists())

    def test_lost_lease_mount_or_root_payload_refuses_without_first_write(self):
        self.store.lease = object()
        with self.assertRaises(LeaseError):
            self.store.initialize()
        self.assert_uninitialized()
        self.store.lease = self.lease
        self.fixture.lost = True
        with self.assertRaises(Exception):
            self.store.initialize()
        self.assert_uninitialized()
        self.fixture.lost = False
        payload = self.fixture.base / 'var/lib/docker/unreviewed-payload'
        payload.parent.mkdir(parents=True)
        payload.write_text('synthetic-root-payload')
        with self.assertRaisesRegex(Exception, 'existing container payload remains on root'):
            self.store.initialize()
        self.assert_uninitialized()

    def test_partial_marker_blocks_retry_without_silently_repairing(self):
        original = real_io.AnchoredRoot.open
        def fail_state_open(anchored, name, *args, **kwargs):
            if name == STATE_SUFFIX:
                raise OSError('synthetic-write-interruption-after-durable-marker')
            return original(anchored, name, *args, **kwargs)
        with patch.object(real_io.AnchoredRoot, 'open', fail_state_open), \
                self.assertRaises(OSError):
            self.store.initialize()
        self.assertFalse(self.state_path.exists())
        marker = self.marker_path.read_bytes()
        with self.assertRaisesRegex(LifecycleError, 'already_initialized_or_present'):
            self.store.initialize()
        self.assertEqual(self.marker_path.read_bytes(), marker)
        self.assertFalse(self.state_path.exists())


if __name__ == '__main__':
    unittest.main()
