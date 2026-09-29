"""Finite refresh CAS/guard fixtures; no VM, model, sleep loop or fake lease."""
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event, Thread
from unittest.mock import patch
import os
import sys
import time
import unittest

sys.path.insert(0, str(Path(__file__).parent))
from test_control_fixtures import HTTPHarness, SyntheticSession
from control.core import _Ticket
from control.protocol import ControlError, Deadline
from common.lifecycle_lease import acquire_lease, LeaseBusy
from test_control_production import ActualManagerFixture
from control.adapter import ManagerSession


class RefreshTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.h = HTTPHarness(Path(self.tmp.name))
        self.addCleanup(self.h.close)
        self.b = self.h.backend
        self.b.external_restart('alpha')

    def ticket(self):
        return _Ticket('refresh', {'catalog': False})

    def test_blocked_collection_does_not_own_guard_lease_and_one_read_collects_once(self):
        entered, release = Event(), Event()
        original = SyntheticSession.observe
        count = []
        def blocked(session, deadline):
            count.append(1)
            entered.set()
            if not release.wait(1):
                raise AssertionError('fixture collector not released')
            return original(session, deadline)
        result = []
        with patch.object(SyntheticSession, 'observe', blocked):
            thread = Thread(target=lambda: result.append(self.h.app._read()))
            thread.start()
            try:
                self.assertTrue(entered.wait(1))
                with acquire_lease(system_root=self.h.root, trusted_uid=os.getuid(), blocking=False):
                    pass  # A legitimate hardware guard obtains canonical ownership.
            finally:
                release.set()
                thread.join(2)
        self.assertFalse(thread.is_alive())
        self.assertEqual(result[0][1]['observed'], 'ready')
        self.assertEqual(len(count), 1)
        before = deepcopy(self.h.app._state)
        self.h.app._read()
        self.assertEqual(self.h.app._state, before)

    def test_every_intervening_identity_change_rejects_without_journal_write(self):
        changes = {
            'boot': lambda: setattr(self.b, 'boot', 'new-boot'),
            'profile': lambda: self.b.state.update(selected='beta'),
            'source': lambda: self.b.records[0].update(revision='b' * 40),
            'runtime': lambda: self.b.state['container'].update(id='replaced'),
            'owner': lambda: self.b.state['container'].update(instance='new-owner'),
            'owner_generation': lambda: self.b.state['container'].update(generation='new-start'),
            'pending_create': lambda: self.b.state.update(pending_create={'dispatch': 'unknown'}),
            'current_operation': lambda: setattr(self.h.app, '_current', 'changed'),
            'control_generation': lambda: self.h.app._state.update(generation=100),
        }
        original = SyntheticSession.refresh_anchor
        saved_state, records = deepcopy(self.b.state), deepcopy(self.b.records)
        for name, mutate in changes.items():
            with self.subTest(name=name):
                self.b.state, self.b.records = deepcopy(saved_state), deepcopy(records)
                self.b.boot = 'fixture-boot'
                self.h.app._current = None
                self.h.app._state['generation'] = 0
                calls = []
                def anchor(session, deadline):
                    calls.append(1)
                    if len(calls) == 3: mutate()
                    return original(session, deadline)
                with patch.object(SyntheticSession, 'refresh_anchor', anchor), patch.object(self.h.journal, 'save', wraps=self.h.journal.save) as write:
                    with self.assertRaises(ControlError) as error:
                        self.h.app._refresh(self.ticket())
                    self.assertEqual(error.exception.code, 'stale_state')
                    write.assert_not_called()
        self.h.app._current = None

    def test_expired_candidate_never_publishes(self):
        original = SyntheticSession.refresh_anchor
        calls = []
        def expired(session, deadline):
            calls.append(1)
            if len(calls) == 3:
                raise ControlError('deadline_exceeded')
            return original(session, deadline)
        with patch.object(SyntheticSession, 'refresh_anchor', expired), patch.object(self.h.journal, 'save') as write:
            with self.assertRaises(ControlError) as error: self.h.app._refresh(self.ticket())
            self.assertEqual(error.exception.code, 'deadline_exceeded')
            write.assert_not_called()

    def test_busy_publication_is_nonblocking_and_writes_nothing(self):
        with acquire_lease(system_root=self.h.root, trusted_uid=os.getuid()):
            with patch.object(self.h.journal, 'save', wraps=self.h.journal.save) as write:
                with self.assertRaises(LeaseBusy): self.h.app._refresh(self.ticket())
                write.assert_not_called()

    def test_recovery_running_never_becomes_ready(self):
        self.b.storage_available = False
        ticket = self.ticket()
        self.h.app._refresh(ticket)
        snapshot = ticket.result[1][0]
        self.assertFalse(snapshot['storage_available'])
        self.assertFalse(snapshot['state_persisted'])
        self.assertEqual(snapshot['observed'], 'unavailable')
        self.assertTrue(all(value is False for value in snapshot['ready_proof'].values()))

    def test_unknown_anchor_and_failed_write_stay_fail_closed(self):
        with patch.object(SyntheticSession, 'refresh_anchor', side_effect=ControlError('observation_unavailable')), patch.object(self.h.journal, 'save') as write:
            with self.assertRaises(ControlError): self.h.app._refresh(self.ticket())
            write.assert_not_called()
        with patch.object(self.h.journal, 'save', return_value=False):
            with self.assertRaises(ControlError): self.h.app._refresh(self.ticket())
        self.assertFalse(self.h.app._persisted)


class ProductionAnchorTests(unittest.TestCase):
    def setUp(self):
        self.fixture = ActualManagerFixture()
        self.addCleanup(self.fixture.close)
        self.session = ManagerSession(self.fixture.load(), lambda *_: [])

    def anchor(self):
        return self.session.refresh_anchor(Deadline.after(1))

    def test_unrelated_parent_directory_churn_does_not_invalidate_anchor(self):
        before = self.anchor()
        temporary = self.fixture.base / 'unrelated-file'
        temporary.write_text('inert')
        self.assertEqual(self.anchor(), before)
        temporary.unlink()
        self.assertEqual(self.anchor(), before)

    def test_source_profile_edit_and_aba_are_detected(self):
        before = self.anchor()
        profile = self.fixture.configs / 'deployments' / 'fixture-old.json'
        content = profile.read_bytes()
        profile.write_bytes(content + b'\n')
        self.assertNotEqual(self.anchor(), before)
        profile.write_bytes(content)
        self.assertNotEqual(self.anchor(), before)

    def test_native_mount_order_is_irrelevant_but_mount_contents_are_not(self):
        mounts = [{'Source': '/one', 'Destination': '/a', 'RW': False},
                  {'Source': '/two', 'Destination': '/b', 'RW': False}]
        item = {'Id': 'stable', 'Mounts': mounts, 'State': {'Running': True, 'StartedAt': 'same'}}
        with patch.object(self.session.manager.docker, 'inventory', return_value=[item]):
            before = self.anchor()
            mounts.reverse()
            self.assertEqual(self.anchor(), before)
            for key, changed in [('Source', '/changed'), ('Destination', '/changed'), ('RW', True)]:
                saved = mounts[0][key]
                mounts[0][key] = changed
                self.assertNotEqual(self.anchor(), before)
                mounts[0][key] = saved
            mounts.append(deepcopy(mounts[0]))
            self.assertNotEqual(self.anchor(), before)
            for invalid in (None, {}, 'private', [None], ['private']):
                item['Mounts'] = invalid
                with self.assertRaises(ControlError): self.anchor()
            del item['Mounts']
            with self.assertRaises(ControlError): self.anchor()

    def test_native_runtime_changes_and_unknown_inventory_are_rejected(self):
        before = self.anchor()
        with patch.object(self.session.manager.docker, 'inventory', return_value=[{'Id': 'new', 'Mounts': [], 'State': {'Running': True, 'StartedAt': 'new'}}]):
            self.assertNotEqual(self.anchor(), before)
        with patch.object(self.session.manager.docker, 'inventory', side_effect=OSError('private error')):
            with self.assertRaises(ControlError) as error: self.anchor()
            self.assertEqual(str(error.exception), 'observation_unavailable')

if __name__ == '__main__': unittest.main()
