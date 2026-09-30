"""Actual Handler local BUSY provenance and lane ownership; fixture-only I/O."""
import importlib.util
import io
import json
from email.message import Message
from pathlib import Path
import sys
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

SOURCE = Path(__file__).resolve().parents[1] / 'scripts/runtime/mimo'


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


o = load('mimo_admission_owner', SOURCE / 'owner.py')
with patch.dict(sys.modules, {'owner': o}):
    p = load('mimo_admission_proxy', SOURCE / 'private_proxy.py')


class AdmissionTests(unittest.TestCase):
    def setUp(self):
        self.lock = threading.Lock()
        self.state = SimpleNamespace(quarantined=False, broken=Mock(is_set=lambda: False),
                                     begin=Mock(), finish=Mock())
        server = Mock()
        locks = iter([self.lock, threading.Lock()])
        with patch.object(p, 'setup', return_value=Mock()), \
                patch.object(p, 'read', return_value={'context': 131072}), \
                patch.object(p, 'validate_manifest'), patch.object(p, 'require_selected'), \
                patch.object(p, 'read_key', return_value=b'fixture-only'), \
                patch.object(p, 'native_ready', return_value=True), \
                patch.object(p, 'Disposition', return_value=self.state), \
                patch.object(p.threading, 'Lock', side_effect=lambda: next(locks)), \
                patch.object(p.http.server, 'ThreadingHTTPServer', return_value=server) as create:
            p.serve()
        self.handler = object.__new__(create.call_args.args[1])
        body = json.dumps({'model': p.MODEL, 'messages': [{'role': 'user', 'content': 'fixture'}],
                          'max_tokens': 128, 'stream': True, 'stream_options': {'include_usage': True},
                          'chat_template_kwargs': {'enable_thinking': False},
                          'reasoning_format': 'deepseek', 'add_generation_prompt': True}).encode()
        h = self.handler
        h.client_address = ('10.156.100.61', 1)
        h.command, h.path = 'POST', '/v1/chat/completions'
        h.headers = Message()
        h.headers['Authorization'] = 'Bearer fixture-only'
        h.headers['Content-Length'] = str(len(body))
        h.connection = Mock()
        h.rfile, h.wfile = io.BytesIO(body), io.BytesIO()
        h.send_response, h.send_header, h.end_headers = Mock(), Mock(), Mock()

    def test_local_busy_unique_marker_before_begin_or_native_and_keeps_existing_holder(self):
        self.lock.acquire()
        try:
            with patch.object(p.http.client, 'HTTPConnection') as native:
                self.handler.forward()
            self.handler.send_response.assert_called_once_with(429)
            self.assertEqual(self.handler.send_header.call_args_list[0].args, ('Content-Length', '0'))
            self.assertEqual(self.handler.send_header.call_args_list[1].args,
                             ('X-H016-Admission', 'rejected-local-busy-before-native-v1'))
            self.assertEqual(self.handler.send_header.call_count, 2)
            self.assertEqual(self.handler.wfile.getvalue(), b'')
            self.assertTrue(self.handler.close_connection)
            self.state.begin.assert_not_called()
            self.state.finish.assert_not_called()
            native.assert_not_called()
            self.assertTrue(self.lock.locked())
        finally:
            self.lock.release()

    def stream(self, status=200, detached=False):
        stream = (b'data: {"choices":[{"finish_reason":"length"}],"usage":{"completion_tokens":128}}\n\n'
                  b'data: [DONE]\n\n')
        response = Mock(status=status)
        response.getheader.side_effect = lambda key, default=None: {
            'Content-Type': 'text/event-stream',
            'X-H016-Admission': 'rejected-local-busy-before-native-v1',
            'Content-Length': '0'}.get(key, default)
        chunks = iter([stream[:31], stream[31:], b''])
        def read_chunk(_):
            self.assertTrue(self.lock.locked())
            self.state.finish.assert_not_called()
            return next(chunks)
        response.read1.side_effect = read_chunk
        count = Mock(status=200)
        count.read.return_value = b'{"input_tokens":83}'
        connection = Mock()
        connection.getresponse.side_effect = [count, response]
        connection.close.side_effect = lambda: self.assertTrue(self.lock.locked())
        self.state.begin.side_effect = lambda: self.assertTrue(self.lock.locked())
        self.state.finish.side_effect = lambda clean: self.assertTrue(self.lock.locked())
        if detached:
            self.handler.wfile = Mock()
            self.handler.wfile.write.side_effect = BrokenPipeError()
        with patch.object(p.http.client, 'HTTPConnection', return_value=connection):
            self.handler.forward()
        self.assertFalse(self.lock.locked())
        self.assertEqual(response.read1.call_count, 3)
        self.assertEqual(connection.request.call_count, 2)
        connection.close.assert_called_once()
        return response

    def test_upstream_429_cannot_forward_local_marker_or_length(self):
        response = self.stream(status=429)
        self.handler.send_response.assert_called_once_with(429)
        self.assertEqual([call.args[0] for call in self.handler.send_header.call_args_list],
                         ['Content-Type', 'Connection'])
        self.assertEqual([call.args[0] for call in response.getheader.call_args_list], ['Content-Type'])
        self.state.finish.assert_called_once_with(False)

    def test_clean_lane_lock_held_through_eof_close_and_disposition(self):
        self.stream()
        self.state.finish.assert_called_once_with(True)

    def test_detached_lane_keeps_lock_through_full_drain_and_quarantines(self):
        self.stream(detached=True)
        self.state.finish.assert_called_once_with(False)
        self.handler.wfile.write.assert_called_once()


if __name__ == '__main__': unittest.main()
