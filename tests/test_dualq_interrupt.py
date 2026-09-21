"""Actual DiagnosticSSHHost RPC signal-drain path; synthetic pipes, no network."""
import io
import json
import signal
import threading
from types import SimpleNamespace
import unittest

from benchmark import glmrepair, profiles


class DualQInterruptTests(unittest.TestCase):
    def test_deferred_signal_preserves_exact_identity_for_canonical_cleanup(self):
        for signum in (signal.SIGINT, signal.SIGTERM):
            for purpose in ('count', 'warmup', 'measured'):
                with self.subTest(signal=signum, purpose=purpose):
                    host = glmrepair.DiagnosticSSHHost.__new__(glmrepair.DiagnosticSSHHost)
                    host.armed = {'scope': profiles.DUALQ_SCOPE}
                    host.lock, host.rpc_unavailable = threading.RLock(), False
                    identity = {'request_id': 'Q0-count-warmup' if purpose == 'count' else 'Q0-' + purpose,
                                'request_sha256': 'a' * 64, 'manifest_sha256': 'b' * 64, 'purpose': purpose}
                    replies = []
                    def readline():
                        replies.append(True)
                        if len(replies) == 1:
                            signal.getsignal(signum)(signum, None)
                            return json.dumps({'result': {'timeout_s': 120 if purpose == 'count' else 7200}}) + '\n'
                        return json.dumps({'result': {'status': 'CANONICAL_STOP_REQUIRED'}}) + '\n'
                    host.process = SimpleNamespace(stdin=io.StringIO(), stdout=SimpleNamespace(readline=readline))
                    before = {sig: signal.getsignal(sig) for sig in (signal.SIGINT, signal.SIGTERM)}
                    with self.assertRaises(KeyboardInterrupt):
                        host.call('request_begin', id='c' * 64, measured=purpose == 'measured',
                                  timeout_s=120 if purpose == 'count' else 7200, request_identity=identity)
                    sent = [json.loads(line) for line in host.process.stdin.getvalue().splitlines()]
                    self.assertEqual([row['op'] for row in sent], ['request_begin', 'request_end'])
                    self.assertEqual(sent[1], {'op': 'request_end', 'id': 'c' * 64,
                                     'request_identity': identity, 'terminal_reason': 'NOT_DISPATCHED'})
                    self.assertFalse(host.rpc_unavailable)
                    self.assertEqual({sig: signal.getsignal(sig) for sig in before}, before)

    def test_missing_resource_proof_interrupt_has_no_registration_to_end(self):
        host = glmrepair.DiagnosticSSHHost.__new__(glmrepair.DiagnosticSSHHost)
        host.armed = {'scope': profiles.DUALQ_SCOPE}
        host.lock, host.rpc_unavailable = threading.RLock(), False
        def readline():
            signal.getsignal(signal.SIGINT)(signal.SIGINT, None)
            return json.dumps({'result': {'proof_pending': True, 'admitted': False}}) + '\n'
        host.process = SimpleNamespace(stdin=io.StringIO(), stdout=SimpleNamespace(readline=readline))
        with self.assertRaises(KeyboardInterrupt):
            host.call('request_begin', id='c' * 64, request_identity={'purpose': 'count'})
        sent = [json.loads(line)['op'] for line in host.process.stdin.getvalue().splitlines()]
        self.assertEqual(sent, ['request_begin'])


if __name__ == '__main__': unittest.main()
