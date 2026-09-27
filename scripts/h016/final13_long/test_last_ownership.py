"""LAST request ownership through the actual client, reader and ExecStopPost.

Offline fake network; HTTPResponse performs real response/header/framing parsing.
No remote, service, credential or native inference operation occurs.
"""
import contextlib
import copy
import http.client
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import socket
import sys
import tempfile
import time
import types
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
READER = HERE / 'reader.py'
spec = importlib.util.spec_from_file_location('last_ownership_client', HERE / 'client.py')
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)
MARKER = b'X-H016-Admission: rejected-local-busy-before-native-v1\r\n'


class Harness:
    s = types.SimpleNamespace(root_payload_guard=lambda: None)
    writes = None

    @staticmethod
    def require(ok, why):
        if not ok:
            raise RuntimeError(why)

    @staticmethod
    def now():
        return '2026-09-27T17:06:00Z'

    @staticmethod
    def MountedStorageGuard(_):
        return contextlib.nullcontext(None)

    class AnchoredRoot:
        def __init__(self, root, _):
            self.root = Path(root)

        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def open(self, name, flags=os.O_RDONLY):
            fd = os.open(self.root / name, flags, 0o600)
            return os.fdopen(fd, 'wb' if flags & os.O_WRONLY else 'rb', buffering=0)

        def atomic_json(self, name, value):
            snapshot = copy.deepcopy(value)
            Harness.writes.append((name, snapshot))
            (self.root / name).write_text(json.dumps(snapshot))


def reader_module():
    owner = types.ModuleType('candidate_owner')
    owner.ADMIT_END = time.time() + 40000
    owner.HARD_END = owner.ADMIT_END + 1500
    owner.BASE = '/unused'
    owner.LOG = '/unused'
    owner.get = owner.save = lambda *_: None
    telemetry = types.ModuleType('telemetry')
    telemetry.bounded_placement = lambda *_: None
    with mock.patch.dict(sys.modules, {'candidate_owner': owner, 'telemetry': telemetry}):
        spec = importlib.util.spec_from_file_location('last_actual_reader', READER)
        reader = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(reader)
    reader.fixture = lambda *args: (reader.body('Synthetic ownership fixture.'), b'', ['a', 'b', 'c'])
    reader.count = lambda key, payload: (65536, json.dumps(payload).encode())
    return reader


def response(wire, method='POST', response_class=None):
    class Socket:
        def makefile(self, *_):
            return io.BytesIO(wire)
    r = (response_class or http.client.HTTPResponse)(Socket(), method=method)
    r.begin()
    return r


def wire_json(value):
    body = json.dumps(value).encode()
    return b'HTTP/1.0 200 OK\r\nContent-Type: application/json\r\nContent-Length: ' + str(len(body)).encode() + b'\r\n\r\n' + body


def clean_stream(done=True):
    event = {'id': 'owned-synthetic-response',
             'choices': [{'index': 0, 'delta': {'content': json.dumps({'codes': ['a', 'b', 'c'], 'product': 323, 'safe_adc': 4095})},
                          'finish_reason': 'stop'}],
             'usage': {'prompt_tokens': 65536, 'completion_tokens': 8},
             'timings': {'prompt_n': 65536, 'prompt_ms': 1000, 'predicted_n': 8, 'predicted_ms': 1000}}
    body = b'data: ' + json.dumps(event).encode() + b'\n\n'
    if done:
        body += b'data: [DONE]\n\n'
    return b'HTTP/1.0 200 OK\r\nContent-Type: text/event-stream\r\n\r\n' + body


class OwnershipTests(unittest.TestCase):
    def exercise(self, generation_wire, *, slots_busy_after=False, identity_busy_after=False):
        """Execute real run and settle with actual reader and synthetic transport."""
        with tempfile.TemporaryDirectory() as td:
            log = Path(td)
            Harness.writes = []
            reader = reader_module()
            h = Harness()
            identity = {'supervisor': {'pid': 123, 'invocation_id': 'owned-invocation'},
                        'native': {'pid': 456, 'container_id': 'owned-container'}}
            raw_source = b'offline source pin fixture'
            go = {'authorized': True, 'purpose': 'H016_LAST_NEAR1M',
                  'hard_end_epoch': time.time() + 40000,
                  'production_identity': identity,
                  'source_sha256': {str(c.OWNER): c.sha(raw_source), str(Path(c.__file__).resolve()): c.sha(raw_source)}}
            state = {**copy.deepcopy(identity), 'status': 'RUNNING'}
            commands, requests, availability_flags = [], [], []
            slots_reads = 0

            def owner_read(path):
                if Path(path).name == 'CLIENT.json':
                    return json.loads((log / 'CLIENT.json').read_text())
                if Path(path).name == 'state.json':
                    return copy.deepcopy(state)
                if Path(path).name == 'proxy-state.json':
                    return {'active_requests': 1 if identity_busy_after else 0}
                raise AssertionError('unanticipated owner read: ' + str(path))

            def owner_run(argv, timeout):
                commands.append(argv)
                if argv[:2] == ['systemctl', 'show']:
                    return 'MainPID=123\nInvocationID=owned-invocation\n'
                if argv[:2] == ['systemctl', 'stop']:
                    state.update(status='SETTLED', settlement={'pid_released': True, 'cgroup_empty': True, 'gpu_compute_empty': True})
                    return ''
                raise AssertionError('unanticipated command: ' + str(argv))

            o = types.SimpleNamespace(BASE=Path('/production'), UNIT='production-fixture.service',
                read=owner_read, run=owner_run, HEX=re.compile(r'[0-9a-f]{64}'),
                protected=lambda _: raw_source, read_key=lambda _: b'offline-synthetic-key',
                native_ready=lambda *_: True)

            class FakeConnection:
                def __init__(self, host, port=None, *args, **kwargs):
                    self.host, self.port, self.timeout = host, port, kwargs.get('timeout')
                    self.sock = None
                    self.method = self.path = None

                def request(self, method, path, body=None, headers=None, **kwargs):
                    self.method, self.path = method, path
                    requests.append((self.host, self.port, method, path))

                def getresponse(self):
                    nonlocal slots_reads
                    if self.path == '/slots':
                        slots_reads += 1
                        if slots_reads > 1:
                            availability_flags.append(owner_read(log / 'CLIENT.json')['request_may_be_active'])
                        return response(wire_json([{'id': 0, 'n_ctx': 1000000,
                              'is_processing': slots_busy_after and slots_reads > 1}]), 'GET')
                    if self.path == '/v1/chat/completions':
                        if isinstance(generation_wire, BaseException):
                            raise generation_wire
                        return response(generation_wire, response_class=getattr(self, 'response_class', None))
                    raise AssertionError('unexpected HTTP route: ' + str(self.path))

                def close(self):
                    pass

            identity_calls = 0
            def checked(*args, **kwargs):
                nonlocal identity_calls
                identity_calls += 1
                if identity_busy_after and identity_calls > 1:
                    availability_flags.append(owner_read(log / 'CLIENT.json')['request_may_be_active'])
                    raise RuntimeError('production_lane_not_clean')
                return {'context': 1000000}, state, {'status': 'ok'}

            with mock.patch.object(c, 'LOG', td), \
                 mock.patch.object(c, 'owner', return_value=o), \
                 mock.patch.object(c, 'read_go', return_value=(go, 'go-fixture-sha')), \
                 mock.patch.object(c, 'preflight', return_value=(h, {'context': 1000000}, state, {'status': 'ok'}, READER.parent)), \
                 mock.patch.object(c, 'load_module', return_value=reader), \
                 mock.patch.object(c, 'check_identity', side_effect=checked), \
                 mock.patch.object(c.http.client, 'HTTPConnection', FakeConnection), \
                 mock.patch.object(c.signal, 'signal'), \
                 mock.patch.object(c.signal, 'setitimer'), \
                 mock.patch.object(c.time, 'sleep'):
                error = None
                try:
                    c.run()
                except BaseException as exc:
                    error = exc
                result = owner_read(log / 'CLIENT.json')
                c.settle()
                if not (log / 'LAST-64K.json').exists():
                    raise AssertionError('reader did not execute: ' + repr(error))
                reader_row = json.loads((log / 'LAST-64K.json').read_text())
                return {'result': result, 'error': error, 'commands': commands,
                        'requests': requests, 'reader_row': reader_row,
                        'writes': copy.deepcopy(Harness.writes),
                        'availability_flags': availability_flags}

    def test_validated_local_busy_survives_actual_reader_and_exec_stop_post(self):
        got = self.exercise(b'HTTP/1.0 429 Too Many Requests\r\n' + MARKER + b'Content-Length: 0\r\n\r\n')
        self.assertEqual(got['result']['status'], 'BUSY_NOT_SUBMITTED')
        self.assertIs(got['result']['request_may_be_active'], False)
        self.assertEqual(got['reader_row']['status'], 'BUSY_NOT_SUBMITTED')
        self.assertEqual(got['reader_row']['owned_stream_disposition']['admission_marker'], c.LOCAL_BUSY_MARKER)
        self.assertEqual(got['result']['owned_disposition']['native_settlement'],
                         'NOT_APPLICABLE_TO_THIS_UNSUBMITTED_REQUEST')
        self.assertFalse(any(cmd[:2] == ['systemctl', 'stop'] for cmd in got['commands']))
        generations = [r for r in got['requests'] if r[3] == '/v1/chat/completions']
        self.assertEqual(len(generations), 1)
        self.assertEqual(got['result']['completed_rungs'], [])
        self.assertFalse(any(r[0] != c.HOST or r[1] != c.PORT for r in got['requests']))
        clears = [row for name, row in got['writes'] if name == 'CLIENT.json' and row.get('status') == 'BUSY_NOT_SUBMITTED']
        self.assertTrue(clears)
        self.assertTrue(all(row['request_may_be_active'] is False for row in clears))

    def test_ambiguous_replies_keep_ownership_and_exact_settlement(self):
        cases = {
            'http09_normalized_to_10': b'HTTP/0.9 429 Too Many Requests\r\n' + MARKER + b'Content-Length: 0\r\n\r\n',
            'upstream_429': b'HTTP/1.0 429 Too Many Requests\r\nContent-Type: application/json\r\nConnection: close\r\n\r\n{}',
            'duplicate_marker': b'HTTP/1.0 429 Too Many Requests\r\n' + MARKER + MARKER + b'Content-Length: 0\r\n\r\n',
            'duplicate_length': b'HTTP/1.0 429 Too Many Requests\r\n' + MARKER + b'Content-Length: 0\r\nContent-Length: 0\r\n\r\n',
            'wrong_length': b'HTTP/1.0 429 Too Many Requests\r\n' + MARKER + b'Content-Length: 1\r\n\r\nx',
            'transfer_encoding': b'HTTP/1.0 429 Too Many Requests\r\n' + MARKER + b'Content-Length: 0\r\nTransfer-Encoding: chunked\r\n\r\n0\r\n\r\n',
            'wrong_content_type': b'HTTP/1.0 429 Too Many Requests\r\n' + MARKER + b'Content-Length: 0\r\nContent-Type: application/json\r\n\r\n',
            'keep_alive': b'HTTP/1.0 429 Too Many Requests\r\n' + MARKER + b'Content-Length: 0\r\nConnection: keep-alive\r\n\r\n',
            'different_status': b'HTTP/1.0 500 Error\r\n' + MARKER + b'Content-Length: 0\r\n\r\n',
            'reset': ConnectionResetError('synthetic reset'),
            'empty_eof': b'',
            'unterminated_headers': b'HTTP/1.0 429 Too Many Requests\r\n' + MARKER + b'Content-Length: 0\r\n',
            'extra_bytes_after_zero_length': b'HTTP/1.0 429 Too Many Requests\r\n' + MARKER + b'Content-Length: 0\r\n\r\nnot-empty',
            'header_parser_defect': b'HTTP/1.0 429 Too Many Requests\r\n' + MARKER + b'Content-Length: 0\r\nBrokenHeaderWithoutColon\r\n\r\n',
            'missing_done': clean_stream(done=False),
        }
        for label, wire in cases.items():
            with self.subTest(label=label):
                got = self.exercise(wire)
                self.assertIsNotNone(got['error'])
                self.assertNotEqual(got['result']['status'], 'BUSY_NOT_SUBMITTED')
                self.assertIs(got['result']['request_may_be_active'], True)
                stops = [cmd for cmd in got['commands'] if cmd[:2] == ['systemctl', 'stop']]
                self.assertEqual(stops, [['systemctl', 'stop', 'production-fixture.service']])
                self.assertEqual(len([r for r in got['requests'] if r[3] == '/v1/chat/completions']), 1)

    def test_own_terminal_drain_clears_before_another_slot_request(self):
        got = self.exercise(clean_stream(), slots_busy_after=True)
        self.assertIsNotNone(got['error'])
        self.assertIs(got['result']['request_may_be_active'], False)
        self.assertEqual(got['availability_flags'], [False])
        self.assertFalse(any(cmd[:2] == ['systemctl', 'stop'] for cmd in got['commands']))
        self.assertEqual(got['reader_row']['owned_stream_disposition']['status'], 'OWN_STREAM_TERMINAL_FULL_DRAIN')

    def test_own_terminal_drain_clears_before_later_global_busy(self):
        got = self.exercise(clean_stream(), identity_busy_after=True)
        self.assertIsNotNone(got['error'])
        self.assertIs(got['result']['request_may_be_active'], False)
        self.assertEqual(got['availability_flags'], [False, False])
        self.assertFalse(any(cmd[:2] == ['systemctl', 'stop'] for cmd in got['commands']))
        self.assertEqual(len([r for r in got['requests'] if r[3] == '/v1/chat/completions']), 1)


class RealSocketFramingTests(unittest.TestCase):
    def test_raw_http09_remains_ambiguous_despite_normalized_version_10(self):
        # Real socket framing reproduces the stdlib normalization that must
        # never turn a non-reviewed wire status line into local BUSY proof.
        left, right = socket.socketpair()
        reader = types.SimpleNamespace(utc_now=lambda: 'fixture', count=lambda *_: (1, b'{}'))
        evidence = []
        c.adapter(reader, object(), object(), time.time() + 30,
                  on_local_busy=evidence.append)
        connection = reader.http.client.HTTPConnection('127.0.0.1', 30012, timeout=1)
        connection.sock = left
        response = None
        try:
            right.sendall(b'HTTP/0.9 429 Too Many Requests\r\n' + MARKER + b'Content-Length: 0\r\n\r\n')
            right.shutdown(socket.SHUT_WR)
            with mock.patch.object(c, 'write'):
                connection.request('POST', '/v1/chat/completions', b'{}',
                                   {'Authorization': 'Bearer offline-fixture'})
                response = connection.getresponse()
            self.assertEqual(response.status, 429)
            self.assertEqual(response.version, 10)
            self.assertEqual(response._h016_status_line, b'HTTP/0.9 429 Too Many Requests\r\n')
            self.assertTrue(response._h016_headers_complete)
            self.assertFalse(c.local_busy_response(response))
            self.assertEqual(evidence, [])
        finally:
            if response is not None:
                response.close()
            connection.close()
            left.close()
            right.close()

    def test_http10_logical_close_keeps_socket_timeout_usable_for_busy_eof(self):
        # UNIX socketpair only: actual HTTPConnection/HTTPResponse behavior,
        # including getresponse() closing its logical socket on HTTP/1.0.
        left, right = socket.socketpair()
        reader = types.SimpleNamespace(utc_now=lambda: 'fixture', count=lambda *_: (1, b'{}'))
        evidence = []
        c.adapter(reader, object(), object(), time.time() + 30,
                  on_local_busy=evidence.append)
        connection = reader.http.client.HTTPConnection('127.0.0.1', 30012, timeout=1)
        connection.sock = left
        try:
            right.sendall(b'HTTP/1.0 429 Too Many Requests\r\n' + MARKER + b'Content-Length: 0\r\n\r\n')
            right.shutdown(socket.SHUT_WR)
            with mock.patch.object(c, 'write'):
                connection.request('POST', '/v1/chat/completions', b'{}',
                                   {'Authorization': 'Bearer offline-fixture'})
                with self.assertRaises(c.LocalBusyNotSubmitted):
                    connection.getresponse()
            self.assertIsNone(connection.sock)
            self.assertEqual(len(evidence), 1)
            self.assertIs(evidence[0]['empty_body_fully_drained'], True)
        finally:
            connection.close()
            left.close()
            right.close()


if __name__ == '__main__':
    unittest.main()
