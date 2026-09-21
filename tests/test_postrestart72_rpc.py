"""Offline deterministic SSH RPC failure/timeout tests; no subprocess or network."""
import io
import json
from pathlib import Path
import sys
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from benchmark import runner

SCOPE = 'postrestart72-480k'


class InlineThread:
    def __init__(self, *, target, daemon):
        self.target = target
        self.daemon = daemon
    def start(self):
        self.target()


class ImmediateEvent:
    def __init__(self):
        self.set_called = False
        self.waits = []
    def set(self):
        self.set_called = True
    def wait(self, timeout):
        self.waits.append(timeout)
        return self.set_called


class RpcTests(unittest.TestCase):
    def host(self, output, *, scope=SCOPE):
        process = SimpleNamespace(stdin=io.StringIO(), stdout=io.StringIO(output), wait=Mock())
        popen = Mock(return_value=process)
        host = runner.SSHHost({'scope': scope, 'campaign': 'benchrun-p72-offline'}, popen=popen)
        return host, process, popen

    def inline(self, event):
        return patch.object(runner, 'threading', SimpleNamespace(
            RLock=threading.RLock, Thread=InlineThread, Event=lambda: event))

    def test_keepalive_is_new_scope_only_and_existing_hostkey_policy_is_preserved(self):
        for scope in (SCOPE, 'concurrent-480k-cpu'):
            host, process, popen = self.host('', scope=scope)
            argv = popen.call_args.args[0]
            self.assertEqual(argv[0], 'ssh'); self.assertIn('BatchMode=yes', argv)
            self.assertIn('ExitOnForwardFailure=yes', argv)
            self.assertIn('127.0.0.1:31002:127.0.0.1:31002', argv)
            self.assertIn('127.0.0.1:31004:127.0.0.1:31004', argv)
            self.assertEqual('ServerAliveInterval=15' in argv, scope == SCOPE)
            self.assertEqual('ServerAliveCountMax=3' in argv, scope == SCOPE)
            self.assertFalse(any('StrictHostKeyChecking' in value or 'KnownHostsFile' in value for value in argv))
            self.assertEqual(popen.call_args.kwargs['stderr'], runner.subprocess.DEVNULL)

    def test_scoped_operation_bounds_and_successful_single_line_alignment(self):
        for op, kwargs, bound in (('status', {}, 90), ('hold_checkpoint', {}, 90),
            ('begin', {}, 180), ('load', {}, 180), ('restore', {}, 7300),
            ('recover', {}, 7300), ('readiness', {'timeout_s': 120}, 150),
            ('readiness', {'timeout_s': 9000}, 7230)):
            with self.subTest(op=op, kwargs=kwargs):
                host, process, _ = self.host('{"result":{"phase":"WARM_HOLD"}}\n')
                event = ImmediateEvent()
                with self.inline(event):
                    self.assertEqual(host.call(op, **kwargs), {'phase': 'WARM_HOLD'})
                self.assertEqual(event.waits, [bound]); self.assertFalse(host.rpc_unavailable)
                self.assertEqual(json.loads(process.stdin.getvalue()), {'op': op, **kwargs})

    def test_silent_or_partial_reply_timeout_poisons_without_second_rpc(self):
        for partial in ('', '{"result":'):
            with self.subTest(partial=partial):
                host, process, _ = self.host('')
                read_started, release_reader = threading.Event(), threading.Event()
                threads, waits = [], []
                class Reader:
                    def readline(self):
                        # Models a pipe that has no newline: readline keeps waiting
                        # even if partial bytes are already available.
                        read_started.set(); release_reader.wait(2)
                        return partial
                class DeadlineEvent:
                    def set(self): pass
                    def wait(self, timeout):
                        waits.append(timeout)
                        if not read_started.wait(1):
                            raise AssertionError('exchange never reached readline')
                        return False
                def thread_factory(**kwargs):
                    thread = threading.Thread(**kwargs); threads.append(thread); return thread
                process.stdout = Reader()
                shim = SimpleNamespace(RLock=threading.RLock, Thread=thread_factory, Event=DeadlineEvent)
                try:
                    with patch.object(runner, 'threading', shim):
                        with self.assertRaisesRegex(RuntimeError, 'explicit_recovery_required'):
                            host.call('hold_checkpoint')
                        self.assertTrue(host.rpc_unavailable)
                        first = process.stdin.getvalue()
                        with self.assertRaisesRegex(RuntimeError, 'explicit_recovery_required'):
                            host.call('restore')
                        self.assertEqual(process.stdin.getvalue(), first)
                        self.assertEqual(len(threads), 1); self.assertTrue(threads[0].daemon)
                        self.assertEqual(waits, [90])
                finally:
                    release_reader.set()
                    for thread in threads:
                        thread.join(1); self.assertFalse(thread.is_alive())

    def test_write_failure_poisons_and_does_not_attempt_second_rpc(self):
        host, process, _ = self.host('')
        process.stdin = Mock(); process.stdin.write.side_effect = BrokenPipeError('synthetic')
        with self.inline(ImmediateEvent()):
            for op in ('status', 'restore'):
                with self.assertRaisesRegex(RuntimeError, 'explicit_recovery_required'):
                    host.call(op)
        self.assertEqual(process.stdin.write.call_count, 1)
        process.stdin.flush.assert_not_called(); self.assertTrue(host.rpc_unavailable)

    def test_eof_malformed_and_partial_protocol_reply_poison_new_scope(self):
        for output in ('', '{broken}\n', '{"result":{}}', '[]\n'):
            with self.subTest(output=output):
                host, process, _ = self.host(output)
                with self.inline(ImmediateEvent()):
                    with self.assertRaisesRegex(RuntimeError, 'explicit_recovery_required'):
                        host.call('status')
                    first = process.stdin.getvalue()
                    with self.assertRaisesRegex(RuntimeError, 'explicit_recovery_required'):
                        host.call('recover')
                    self.assertEqual(process.stdin.getvalue(), first)
                self.assertTrue(host.rpc_unavailable)

    def test_complete_host_refusal_is_aligned_and_historical_sync_path_unchanged(self):
        for scope in (SCOPE, 'concurrent-480k-cpu'):
            host, process, _ = self.host('{"error":"owned_operation_refused"}\n{"result":{"phase":"SAFE"}}\n', scope=scope)
            with self.inline(ImmediateEvent()):
                with self.assertRaisesRegex(RuntimeError, 'host_operation_refused:owned_operation_refused'):
                    host.call('load')
                self.assertEqual(host.call('status'), {'phase': 'SAFE'})
            self.assertEqual(len(process.stdin.getvalue().splitlines()), 2)
            self.assertFalse(host.rpc_unavailable)
        # Historical scopes retain their existing synchronous EOF exception,
        # without a new protocol timer/poison contract.
        host, process, _ = self.host('', scope='concurrent-480k-cpu')
        with patch.object(runner, 'threading', SimpleNamespace(Thread=Mock(side_effect=AssertionError('old scope started RPC thread')))):
            with self.assertRaisesRegex(RuntimeError, 'host_session_lost'):
                host.call('status')
        self.assertFalse(host.rpc_unavailable)


if __name__ == '__main__':
    unittest.main()
