"""Exercise the actual reader request body with offline HTTPResponse streams."""
import ast
import base64
import contextlib
import copy
import datetime
import hashlib
import http.client
import io
import json
import os
import pathlib
import tempfile
import threading
import time
import types
import unittest


SOURCE = pathlib.Path(__file__).with_name('reader.py')


def terminal_stream(usage=None, finish='stop', done=True):
    event = {'id': 'owned-response', 'choices': [
        {'delta': {'content': 'test'}, 'finish_reason': finish}],
        'usage': usage if usage is not None else {'prompt_tokens': 8, 'completion_tokens': 1}}
    return (b'data: ' + json.dumps(event).encode() + b'\n\n' +
            (b'data: [DONE]\n\n' if done else b''))


def response_bytes(body, content_length=None, header=None):
    framing = header if header is not None else (
        'Content-Length: ' + str(len(body) if content_length is None else content_length))
    return b'HTTP/1.1 200 OK\r\n' + framing.encode() + b'\r\n\r\n' + body


class WireSocket:
    def __init__(self, wire):
        self.wire = wire

    def makefile(self, *args):
        return io.BufferedReader(io.BytesIO(self.wire))


class ReaderCompletionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.events, self.receipts, self.callback_rows = [], [], []
        self.failed = threading.Event()
        self.wire = response_bytes(terminal_stream())
        self.response_error = None
        self.slots = [{'id': 0, 'is_processing': False, 'n_ctx': 128}]
        test = self

        class Connection:
            sock = None

            def __init__(self, *args, **kwargs):
                pass

            def request(self, *args, **kwargs):
                test.events.append('post')

            def getresponse(self):
                if test.response_error is not None:
                    raise test.response_error
                response = http.client.HTTPResponse(WireSocket(test.wire))
                response.begin()
                return response

            def close(self):
                pass

        class Root:
            def open(self, name, flags):
                return os.fdopen(os.open(pathlib.Path(test.tmp.name, name), flags, 0o600), 'wb')

        def require(value, reason):
            if not value:
                raise RuntimeError(reason)

        def get(*args):
            self.events.append('global_slots')
            return 200, self.slots

        self.h = types.SimpleNamespace(
            require=require, now=lambda: 'test-utc', s=None,
            MountedStorageGuard=lambda _: contextlib.nullcontext(),
            AnchoredRoot=lambda *args: contextlib.nullcontext(Root()))
        self.ns = dict(base64=base64, contextlib=contextlib, datetime=datetime,
                       hashlib=hashlib, io=io, json=json, os=os, pathlib=pathlib, time=time,
                       http=types.SimpleNamespace(client=types.SimpleNamespace(HTTPConnection=Connection)),
                       LOG=self.tmp.name, ADMIT_END=time.time() + 300, CLIENT_END=time.time() + 300,
                       count=lambda *_: (8, b'{"fixture":"offline"}'), get=get,
                       save=lambda h, name, row: self.receipts.append(copy.deepcopy(row)))
        tree = ast.parse(SOURCE.read_text())
        functions = [node for node in tree.body if isinstance(node, ast.FunctionDef)
                     and node.name in ('request', 'admit', 'utc_now')]
        exec(compile(ast.Module(body=functions, type_ignores=[]), str(SOURCE), 'exec'), self.ns)

    def callback(self, row):
        self.events.append('owned_drained')
        self.callback_rows.append(copy.deepcopy(row))

    def run_request(self, callback=None):
        return self.ns['request'](
            self.h, b'offline', {'max_tokens': 16, 'chat_template_kwargs': {'enable_thinking': False}},
            'TEST', self.failed, 128, on_owned_stream_drained=callback or self.callback)

    def assert_no_completion(self):
        with self.assertRaises(Exception):
            self.run_request()
        self.assertEqual(self.callback_rows, [])
        self.assertNotIn('global_slots', self.events)
        self.assertNotIn('owned_stream_disposition', self.receipts[-1])

    def test_callback_precedes_global_idle_probe(self):
        row = self.run_request()
        self.assertEqual(self.events, ['post', 'owned_drained', 'global_slots'])
        disposition = self.callback_rows[0]['owned_stream_disposition']
        self.assertEqual(disposition['status'], 'OWN_STREAM_TERMINAL_FULL_DRAIN')
        self.assertEqual(disposition['response_id'], 'owned-response')
        self.assertEqual(disposition['request_sha256'], row['request_sha256'])
        self.assertEqual(disposition['drained_utc'], row['drained_utc'])
        self.assertNotIn('native_settlement', self.callback_rows[0])

    def test_ordinary_proxy_http10_close_delimited_response(self):
        self.wire = b'HTTP/1.0 200 OK\r\nConnection: close\r\n\r\n' + terminal_stream()
        row = self.run_request()
        self.assertEqual(row['owned_stream_disposition']['status'],
                         'OWN_STREAM_TERMINAL_FULL_DRAIN')
        self.assertEqual(self.events, ['post', 'owned_drained', 'global_slots'])

    def test_original_call_without_optional_callback_still_works(self):
        row = self.ns['request'](
            self.h, b'offline', {'max_tokens': 16, 'chat_template_kwargs': {'enable_thinking': False}},
            'TEST', self.failed, 128)
        self.assertEqual(row['status'], 'TRANSPORT_COMPLETE')
        self.assertEqual(self.events, ['post', 'global_slots'])

    def test_new_global_busy_still_raises_after_owned_completion(self):
        self.slots[0]['is_processing'] = True
        with self.assertRaisesRegex(RuntimeError, 'post_drain_slot_not_idle'):
            self.run_request()
        self.assertEqual(self.events, ['post', 'owned_drained', 'global_slots'])
        self.assertEqual(self.receipts[-1]['status'], 'FAILED_QUARANTINE_NO_RETRY')
        self.assertEqual(self.receipts[-1]['owned_stream_disposition']['status'],
                         'OWN_STREAM_TERMINAL_FULL_DRAIN')
        self.assertNotIn('native_settlement', self.receipts[-1])

    def test_post_drain_guard_still_raises_after_callback(self):
        def callback(row):
            self.callback(row)
            self.failed.set()
        with self.assertRaisesRegex(RuntimeError, 'post_drain_guard_failed'):
            self.run_request(callback)
        self.assertEqual(self.events, ['post', 'owned_drained'])

    def test_usage_measurement_mismatch_still_raises_after_callback(self):
        self.wire = response_bytes(terminal_stream({'prompt_tokens': 9, 'completion_tokens': 1}))
        with self.assertRaisesRegex(RuntimeError, 'native_usage_count_or_budget_mismatch'):
            self.run_request()
        self.assertEqual(self.events, ['post', 'owned_drained'])

    def test_missing_done_has_no_callback(self):
        self.wire = response_bytes(terminal_stream(done=False))
        self.assert_no_completion()

    def test_truncated_content_length_after_done_has_no_callback(self):
        body = terminal_stream()
        self.wire = response_bytes(body, content_length=len(body) + 10)
        self.assert_no_completion()

    def test_missing_chunked_terminal_has_no_callback(self):
        body = terminal_stream()
        encoded = format(len(body), 'x').encode() + b'\r\n' + body + b'\r\n'
        self.wire = response_bytes(encoded, header='Transfer-Encoding: chunked')
        self.assert_no_completion()

    def test_malformed_sse_has_no_callback(self):
        self.wire = response_bytes(b'data: {broken json}\n\n' + terminal_stream())
        self.assert_no_completion()

    def test_malformed_content_length_has_no_callback(self):
        self.wire = response_bytes(terminal_stream(), header='Content-Length: invalid')
        self.assert_no_completion()

    def test_malformed_usage_has_no_callback(self):
        self.wire = response_bytes(terminal_stream({'prompt_tokens': True, 'completion_tokens': 1}))
        self.assert_no_completion()

    def test_invalid_finish_has_no_callback(self):
        self.wire = response_bytes(terminal_stream(finish='unknown'))
        self.assert_no_completion()

    def test_local_busy_exception_is_preserved_without_quarantine_or_settlement(self):
        class LocalBusyNotSubmitted(RuntimeError):
            evidence = {'status': 'PROXY_LOCAL_BUSY_PRE_DISPATCH'}
        exc = LocalBusyNotSubmitted('busy')
        self.ns['LOCAL_BUSY_EXCEPTION'] = LocalBusyNotSubmitted
        self.response_error = exc
        with self.assertRaises(LocalBusyNotSubmitted) as caught:
            self.run_request()
        self.assertIs(caught.exception, exc)
        self.assertEqual(self.receipts[-1]['status'], 'BUSY_NOT_SUBMITTED')
        self.assertEqual(self.receipts[-1]['owned_stream_disposition'], exc.evidence)
        self.assertEqual(self.callback_rows, [])
        self.assertNotIn('native_settlement', self.receipts[-1])

    def test_ambiguous_429_exception_keeps_original_quarantine(self):
        self.response_error = RuntimeError('ambiguous_429')
        self.assert_no_completion()
        self.assertEqual(self.receipts[-1]['status'], 'FAILED_QUARANTINE_NO_RETRY')


if __name__ == '__main__':
    unittest.main()
