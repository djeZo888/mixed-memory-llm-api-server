"""Offline review fixtures for frozen source; proposed marker is NOT deployed.
Usage: python3 test_busy_contract.py [--input-dir PATH]
No proxy serve(), sockets, owner imports, or host commands are executed.
"""
import argparse
import ast
import hashlib
import hmac
import http.server
import io
import ipaddress
import json
from pathlib import Path
import socket
import threading
import time
import types
import unittest

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--input-dir', type=Path, default=Path(__file__).resolve().parents[3] / 'input')
args, unittest_args = parser.parse_known_args()
SOURCE = args.input_dir / 'production-private_proxy.py'
assert hashlib.sha256(SOURCE.read_bytes()).hexdigest() == 'ad7fea4cbf9fd2b6583c87530325136c858d94c1e28318b71bed682965972a56'
assert hashlib.sha256((args.input_dir / 'client.py').read_bytes()).hexdigest() == '73869aaa2e737c44e3381e35f94f13463b15e828ef32fc2255a69b9d165d17c5'
TREE = ast.parse(SOURCE.read_text())
HANDLER = next(n for n in ast.walk(TREE) if isinstance(n, ast.ClassDef) and n.name == 'Handler')
MARKER = ('X-H016-Admission', 'rejected-local-busy-before-native-v1')


def proposed_local_busy(status, headers, body, *, endpoint=('10.156.100.60', 30012),
                        method='POST', route='/v1/chat/completions', authenticated_pinned_route=True):
    """Review-only candidate predicate; never asserts existing deployed support."""
    values = {}
    for k, v in headers:
        values.setdefault(k.lower(), []).append(v)
    return (authenticated_pinned_route and endpoint == ('10.156.100.60', 30012)
            and method == 'POST' and route == '/v1/chat/completions'
            and type(status) is int and status == 429 and body == b''
            and values.get('x-h016-admission') == [MARKER[1]]
            and values.get('content-length') == ['0']
            and not any(k in values for k in ('transfer-encoding', 'content-type', 'connection')))


def proposed_classify(read_response, **route):
    """A complete parsed reply is prerequisite; transport/parser failures stay unknown."""
    try:
        status, headers, body = read_response()
        return proposed_local_busy(status, headers, body, **route)
    except (OSError, http.client.HTTPException, EOFError, ValueError):
        return False


class Lock:
    def __init__(self, events):
        self.real, self.events = threading.Lock(), events
    def acquire(self, blocking=False):
        self.events.append('acquire')
        return self.real.acquire(blocking=blocking)
    def release(self):
        self.events.append('release')
        self.real.release()
    def locked(self):
        return self.real.locked()


def frozen_exchange(*, busy=False, upstream_status=200, detached=False, malformed=False):
    events, wire = [], io.BytesIO()
    lock, quarantine = Lock(events), threading.Event()
    disposition = types.SimpleNamespace(quarantined=False, broken=threading.Event())
    def begin():
        assert lock.locked()
        events.append('begin')
    def finish(clean):
        assert lock.locked()
        events.append(('finish', clean))
    disposition.begin, disposition.finish = begin, finish
    if busy:
        lock.real.acquire()
    chunk = (b'data: {"usage":{},"choices":[{"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n'
             if not malformed else b'data: invalid-json\n')
    class Response:
        status = upstream_status
        def getheader(self, name, default=None):
            # Fake malicious upstream marker is never requested/forwarded.
            return MARKER[1] if name == MARKER[0] else default
        def read1(self, size):
            assert lock.locked()
            events.append('drain')
            if 'chunk' not in events:
                events.append('chunk')
                return chunk
            return b''
    class Connection:
        sock = None
        def __init__(self, *a, **kw):
            events.append('connection')
        def request(self, method, path, *a, **kw):
            assert lock.locked()
            events.append(path)
        def getresponse(self):
            if events[-1] == '/v1/chat/completions/input_tokens':
                return types.SimpleNamespace(status=200, read=lambda: b'{"input_tokens":10}')
            return Response()
        def close(self):
            assert lock.locked()
            events.append('close')
    ns = dict(http=types.SimpleNamespace(server=http.server, client=types.SimpleNamespace(HTTPConnection=Connection)),
              ipaddress=ipaddress, hmac=hmac, key=b'mock-key', time=time, json=json, socket=socket,
              owner=lock, quarantine=quarantine, disposition=disposition, capacity=1000192,
              MAX_BODY=16*1024*1024, ROUTES={('POST','/v1/chat/completions')}, normalize=lambda x:x)
    exec(compile(ast.Module(body=[HANDLER], type_ignores=[]), str(SOURCE), 'exec'), ns)
    h = ns['Handler'].__new__(ns['Handler'])
    h.client_address, h.command, h.path = ('10.156.100.61', 1234), 'POST', '/v1/chat/completions'
    h.request_version, h.requestline = 'HTTP/1.0', 'POST /v1/chat/completions HTTP/1.0'
    body = b'{"max_tokens":10}'
    from email.message import Message
    h.headers = Message()
    h.headers['Authorization'], h.headers['Content-Length'] = 'Bearer mock-key', str(len(body))
    h.rfile, h.connection = io.BytesIO(body), types.SimpleNamespace(settimeout=lambda _:None)
    class Sink:
        def write(self, b):
            if detached and b.startswith(b'data:'):
                events.append('downstream-broken')
                raise BrokenPipeError()
            return wire.write(b)
        def flush(self):
            pass
    h.wfile = Sink()
    h.forward()
    return wire.getvalue(), events, lock, quarantine


class BusyContract(unittest.TestCase):
    def test_frozen_local_busy_exact_shape_and_no_native_dispatch(self):
        wire, events, lock, quarantine = frozen_exchange(busy=True)
        header, body = wire.split(b'\r\n\r\n', 1)
        self.assertTrue(header.startswith(b'HTTP/1.0 429 Too Many Requests\r\n'))
        self.assertIn(b'Content-Length: 0', header)
        self.assertIn(b'Server: ', header); self.assertIn(b'Date: ', header)
        self.assertNotIn(b'Content-Type:', header); self.assertNotIn(b'Connection:', header)
        self.assertNotIn(MARKER[0].encode(), header)
        self.assertEqual(body, b''); self.assertEqual(events, ['acquire'])
        self.assertTrue(lock.locked()); self.assertFalse(quarantine.is_set())
        # Frozen source lacks the proposed explicit contract. Never fake support.
        self.assertFalse(proposed_local_busy(429, [('Content-Length','0')], body))

    def test_upstream429_cannot_spoof_local_marker(self):
        wire, events, lock, quarantine = frozen_exchange(upstream_status=429)
        self.assertIn(b'HTTP/1.0 429', wire)
        self.assertIn(b'Content-Type: application/json', wire)
        self.assertIn(b'Connection: close', wire)
        self.assertNotIn(b'Content-Length:', wire); self.assertNotIn(MARKER[0].encode(), wire)
        self.assertIn('/v1/chat/completions', events)
        self.assertEqual(events[-3:], ['close', ('finish', False), 'release'])
        self.assertTrue(quarantine.is_set()); self.assertFalse(lock.locked())

    def test_lock_held_through_clean_and_detached_drain(self):
        for detached in (False, True):
            with self.subTest(detached=detached):
                _, events, lock, quarantine = frozen_exchange(detached=detached)
                self.assertLess(events.index('begin'), events.index('/v1/chat/completions/input_tokens'))
                self.assertLess(events.index('/v1/chat/completions/input_tokens'), events.index('/v1/chat/completions'))
                self.assertEqual(events.count('drain'), 2)
                self.assertEqual(events[-3:], ['close', ('finish', not detached), 'release'])
                self.assertEqual(quarantine.is_set(), detached); self.assertFalse(lock.locked())
                if detached:
                    self.assertLess(events.index('downstream-broken'), len(events)-4)

    def test_malformed_upstream_is_quarantined_not_proved_settled(self):
        _, events, lock, quarantine = frozen_exchange(malformed=True)
        self.assertEqual(events[-3:], ['close', ('finish', False), 'release'])
        self.assertTrue(quarantine.is_set()); self.assertFalse(lock.locked())

    def test_proposed_exact_predicate_and_ambiguous_negative_cases(self):
        headers = [MARKER, ('Content-Length','0')]
        self.assertTrue(proposed_local_busy(429, headers, b''))
        for status in (200,400,401,403,404,500,503,None,'429',True):
            self.assertFalse(proposed_local_busy(status, headers, b''))
        for bad in ([('Content-Length','0')], [MARKER], headers+[MARKER], headers+[('Content-Length','0')],
                    [MARKER,('Content-Length','1')], [('X-H016-Admission','wrong'),('Content-Length','0')],
                    headers+[('Transfer-Encoding','chunked')], headers+[('Content-Type','application/json')],
                    headers+[('Connection','close')]):
            self.assertFalse(proposed_local_busy(429,bad,b''))
        self.assertFalse(proposed_local_busy(429,headers,b'nonempty'))
        for kwargs in ({'endpoint':('127.0.0.1',30012)}, {'route':'/v1/chat/completions/input_tokens'},
                       {'method':'GET'}, {'authenticated_pinned_route':False}):
            self.assertFalse(proposed_local_busy(429,headers,b'',**kwargs))
        self.assertFalse(proposed_local_busy(429,headers,None))
        self.assertTrue(proposed_classify(lambda:(429,headers,b'')))
        # No response status/header tuple is manufactured from a transport/parser error.
        for error in (ConnectionResetError(), TimeoutError(), http.client.BadStatusLine('bad'),
                      http.client.IncompleteRead(b''), EOFError(), ValueError('malformed headers')):
            with self.subTest(error=type(error).__name__):
                def incomplete():
                    raise error
                self.assertFalse(proposed_classify(incomplete))

if __name__ == '__main__':
    unittest.main(argv=[__file__, *unittest_args])
