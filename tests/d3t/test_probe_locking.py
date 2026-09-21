"""Real OS-lock contention; all transport/accounting/telemetry are CPU fixtures.

No HTTP listener, network request, native model or GPU execution is used here.
"""
from __future__ import annotations

import contextlib
import os
import threading
import time
import unittest
from unittest.mock import Mock, patch

import test_probe as fixtures

probe = fixtures.probe
AgentError = fixtures.AgentError


class LockingTests(unittest.TestCase):
    def setUp(self):
        # Composition avoids discovering/rerunning the unrelated loopback test.
        self.f = fixtures.DriverTests()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.run = self.f.run
        probe.prepare(self.run, 'baseline', accountant=self.f.accountant)
        with patch.object(probe.subprocess, 'Popen'):
            probe.launch(self.run)

    @contextlib.contextmanager
    def status_reader(self, *, release_after=2, on_release=None):
        """Hold a real status read until worker flock has actually collided.

        flock is observed, never simulated: the status thread owns a separately
        opened descriptor. Events bound test coordination to three seconds.
        """
        held, release = threading.Event(), threading.Event()
        attempts, errors, observed = [], [], []
        real_read, real_flock = probe.read_json, probe.fcntl.flock
        worker_thread = threading.current_thread()

        def read(path, *args, **kwargs):
            value = real_read(path, *args, **kwargs)
            if threading.current_thread() is reader and path == self.run / 'state.json':
                held.set()
                if not release.wait(3):
                    raise AssertionError('status reader release deadline')
                if on_release:
                    on_release()
            return value

        def flock(fd, operation):
            try:
                return real_flock(fd, operation)
            except BlockingIOError:
                if (threading.current_thread() is worker_thread and held.is_set()
                        and os.fstat(fd).st_ino == (self.run / 'state.lock').stat().st_ino):
                    attempts.append(time.monotonic())
                    if release_after is not None and len(attempts) >= release_after:
                        release.set()
                raise

        def poll():
            try:
                observed.append(probe.status(self.run))
            except BaseException as exc:
                errors.append(exc)

        reader = threading.Thread(target=poll)

        def start():
            reader.start()
            self.assertTrue(held.wait(3), 'status did not acquire state.lock')

        with patch.object(probe, 'read_json', side_effect=read), patch.object(probe.fcntl, 'flock', side_effect=flock):
            try:
                yield start, release, attempts
            finally:
                release.set()
                if reader.ident is not None:
                    reader.join(3)
                    self.assertFalse(reader.is_alive(), 'status thread did not exit')
                self.assertEqual(errors, [])
        self.assertEqual(len(observed), 1)

    def worker(self, transport=None, sampler=None):
        probe.worker(self.run, transport=transport or self.f.transport,
                     sampler_factory=sampler or fixtures.SyntheticSampler)

    def assert_one_success(self, cancellations):
        self.assertEqual(self.f.state()['status'], 'STEP_PASS')
        self.assertEqual(len(self.f.state()['stages']['baseline']['results']), 1)
        self.assertEqual(len(self.f.transfers), 1)
        # One normal finally cleanup after publication; no premature cancel.
        self.assertEqual(cancellations, [(True, 'STEP_PASS')])
        with self.assertRaises(AgentError):
            probe.launch(self.run)

    def observed_transport(self, cancellations):
        def transport(*args):
            transfer = self.f.transport(*args)
            transfer.cancel.side_effect = lambda: cancellations.append(
                (transfer.done.is_set(), self.f.state()['status']))
            return transfer
        return transport

    def test_initial_and_predispatch_state_reads_serialize_with_status(self):
        for phase in ('initial', 'predispatch'):
            with self.subTest(phase=phase):
                if phase == 'predispatch':
                    # A fresh prepared request, never retry the completed one.
                    probe.prepare(self.run, 'baseline', accountant=self.f.accountant)
                    with patch.object(probe.subprocess, 'Popen'):
                        probe.launch(self.run)
                with self.status_reader() as (start, _, attempts):
                    class Sampler(fixtures.SyntheticSampler):
                        def next(inner, timeout):
                            if phase == 'predispatch' and not attempts:
                                start()
                            return super().next(timeout)
                    if phase == 'initial':
                        start()
                    self.worker(sampler=Sampler)
                self.assertGreaterEqual(len(attempts), 2)
                self.assertEqual(self.f.state()['status'], 'STEP_PASS')
        self.assertEqual(len(self.f.transfers), 2)

    def test_active_status_contention_neither_cancels_nor_duplicates_dispatch(self):
        cancellations = []
        with self.status_reader() as (start, _, attempts):
            def transport(*args):
                transfer = self.observed_transport(cancellations)(*args)
                transfer.done.clear()  # Still active when status owns state.lock.
                start()
                duplicate = Mock()
                with self.assertRaisesRegex(AgentError, 'owned_request_or_state_busy'):
                    self.worker(transport=duplicate)
                duplicate.assert_not_called()
                return transfer

            owner = self
            class Sampler(fixtures.SyntheticSampler):
                def next(inner, timeout):
                    if owner.f.transfers:
                        owner.f.transfers[0].done.set()
                    return super().next(timeout)

            self.worker(transport=transport, sampler=Sampler)
        self.assertGreaterEqual(len(attempts), 2)
        self.assert_one_success(cancellations)

    def test_final_publication_waits_for_status_without_discarding_result(self):
        cancellations = []
        real_check = probe.check_cache
        with self.status_reader() as (start, _, attempts):
            def checked(*args):
                real_check(*args)
                start()  # The completed response has passed every result gate.
            with patch.object(probe, 'check_cache', side_effect=checked):
                self.worker(transport=self.observed_transport(cancellations))
        self.assertGreaterEqual(len(attempts), 2)
        self.assert_one_success(cancellations)

    def test_failure_publication_waits_for_status_and_preserves_reason(self):
        with self.status_reader() as (start, _, attempts):
            def fail(*args):
                start()
                raise AgentError('useful_prefix_reuse_NOT_TESTED')
            with patch.object(probe, 'check_cache', side_effect=fail):
                self.worker()
        self.assertGreaterEqual(len(attempts), 2)
        self.assertEqual(self.f.state()['failure_class'], 'useful_prefix_reuse_NOT_TESTED')
        self.assertEqual(self.f.state()['status'], 'PENDING_RECONCILIATION')
        self.assertEqual(self.f.state()['stages']['baseline']['results'], [])
        self.assertEqual(len(self.f.transfers), 1)

    def test_exhausted_active_lock_records_failure_when_failure_lock_recovers(self):
        with self.status_reader(release_after=None) as (start, release, attempts):
            def transport(*args):
                transfer = self.f.transport(*args)
                transfer.done.clear()
                transfer.cancel.side_effect = release.set
                start()
                return transfer
            with patch.object(probe, 'STATE_LOCK_TIMEOUT', .1):
                began = time.monotonic()
                self.worker(transport=transport)
                self.assertLess(time.monotonic() - began, 2)
        self.assertGreaterEqual(len(attempts), 2)
        self.assertEqual(self.f.state()['failure_class'], 'state_lock_timeout')
        self.assertEqual(self.f.state()['status'], 'PENDING_RECONCILIATION')
        self.assertEqual(self.f.state()['stages']['baseline']['results'], [])
        with self.assertRaises(AgentError):
            probe.launch(self.run)

    def test_exhausted_failure_publication_keeps_unknown_checkpoint_and_no_retry(self):
        with self.status_reader(release_after=None) as (start, _, attempts):
            def transport(*args):
                transfer = self.f.transport(*args)
                transfer.done.clear()
                start()
                return transfer
            with patch.object(probe, 'STATE_LOCK_TIMEOUT', .1):
                began = time.monotonic()
                with self.assertRaisesRegex(AgentError, '^state_lock_timeout$'):
                    self.worker(transport=transport)
                self.assertLess(time.monotonic() - began, 2)
        self.assertGreaterEqual(len(attempts), 4)
        self.assertEqual(self.f.state()['status'], 'IN_FLIGHT')
        self.assertEqual(probe.status(self.run)['status'], 'IN_FLIGHT_UNKNOWN')
        self.assertEqual(self.f.state()['stages']['baseline']['results'], [])
        self.f.transfers[0].cancel.assert_called()
        duplicate = Mock()
        self.worker(transport=duplicate)
        duplicate.assert_not_called()
        with self.assertRaises(AgentError):
            probe.launch(self.run)

    def test_owner_cancel_during_final_result_processing_is_not_overwritten(self):
        real_check = probe.check_cache
        with self.status_reader() as (start, _, attempts):
            def checked(*args):
                real_check(*args)
                probe.cancel(self.run)
                start()
            with patch.object(probe, 'check_cache', side_effect=checked):
                self.worker()
        self.assertGreaterEqual(len(attempts), 2)
        self.assertEqual(self.f.state()['failure_class'], 'owner_cancelled')
        self.assertEqual(self.f.state()['status'], 'PENDING_RECONCILIATION')
        self.assertEqual(self.f.state()['stages']['baseline']['results'], [])

    def test_active_and_final_state_waits_cannot_extend_request_deadline(self):
        # Fresh fixture per failure: neither request may be retried.
        for phase in ('active', 'final'):
            with self.subTest(phase=phase):
                if phase == 'final':
                    self.setUp()
                clock = [time.time()]
                state = self.f.state()
                state['request_deadline'] = clock[0] + .5
                probe.write_json(self.run / 'state.json', state)
                def expire():
                    clock[0] += 1
                with self.status_reader(on_release=expire) as (start, _, attempts):
                    def transport(*args):
                        transfer = self.f.transport(*args)
                        if phase == 'active':
                            transfer.done.clear()
                            start()
                        return transfer
                    real_check = probe.check_cache
                    def checked(*args):
                        real_check(*args)
                        if phase == 'final':
                            start()
                    class Sampler(fixtures.SyntheticSampler):
                        def next(inner, timeout):
                            clock[0] += .01  # Preserve strictly increasing sample timestamps.
                            return super().next(timeout)
                    with patch.object(probe.time, 'time', side_effect=lambda: clock[0]), \
                            patch.object(probe, 'check_cache', side_effect=checked):
                        self.worker(transport=transport, sampler=Sampler)
                self.assertGreaterEqual(len(attempts), 2)
                self.assertEqual(self.f.state()['failure_class'], 'stage_timeout')
                self.assertEqual(self.f.state()['status'], 'PENDING_RECONCILIATION')
                self.assertEqual(self.f.state()['stages']['baseline']['results'], [])


if __name__ == '__main__':
    unittest.main()
