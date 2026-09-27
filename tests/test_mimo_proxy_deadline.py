"""Ordinary production proxy deadline/closure fixtures; no network or host I/O."""
import contextlib
import hashlib
import importlib.util
import io
import json
from email.message import Message
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'scripts/runtime/mimo'


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


o = load('mimo_deadline_owner', SOURCE / 'owner.py')
with patch.dict(sys.modules, {'owner': o}):
    p = load('mimo_deadline_proxy', SOURCE / 'private_proxy.py')


class DeadlineTests(unittest.TestCase):
    def run_request(self, elapsed):
        now = [100000.0]
        state = SimpleNamespace(quarantined=False, broken=Mock(is_set=lambda: False),
                                begin=Mock(), finish=Mock())
        server = Mock()
        with patch.object(p, 'setup', return_value=Mock()), \
                patch.object(p, 'read', return_value={'context': 1000000}), \
                patch.object(p, 'validate_manifest'), patch.object(p, 'require_selected'), \
                patch.object(p, 'read_key', return_value=b'fixture-only'), \
                patch.object(p, 'native_ready', return_value=True), \
                patch.object(p, 'Disposition', return_value=state), \
                patch.object(p.http.server, 'ThreadingHTTPServer', return_value=server) as create:
            p.serve()
        handler = object.__new__(create.call_args.args[1])
        body = json.dumps({'model': p.MODEL, 'messages': [{'role': 'user', 'content': 'fixture'}],
                          'max_tokens': 128, 'stream': True, 'stream_options': {'include_usage': True},
                          'chat_template_kwargs': {'enable_thinking': False},
                          'reasoning_format': 'deepseek', 'add_generation_prompt': True}).encode()
        handler.client_address = ('10.156.100.61', 1)
        handler.command, handler.path = 'POST', '/v1/chat/completions'
        handler.headers = Message()
        handler.headers['Authorization'] = 'Bearer fixture-only'
        handler.headers['Content-Length'] = str(len(body))
        handler.connection = Mock()
        handler.rfile, handler.wfile = io.BytesIO(body), io.BytesIO()
        handler.send_response = Mock()
        handler.send_header = Mock()
        handler.end_headers = Mock()
        stream = (b'data: {"choices":[{"finish_reason":"length"}],"usage":{"completion_tokens":128}}\n\n'
                  b'data: [DONE]\n\n')
        response = Mock(status=200)
        response.getheader.return_value = 'text/event-stream'
        response.read1.side_effect = [stream, b'']
        count = Mock(status=200)
        count.read.return_value = b'{"input_tokens":83}'
        connection = Mock()
        def getresponse():
            if connection.getresponse.call_count == 1:
                return count
            now[0] += elapsed
            return response
        connection.getresponse.side_effect = getresponse
        with patch.object(p.time, 'time', side_effect=lambda: now[0]), \
                patch.object(p.http.client, 'HTTPConnection', return_value=connection) as native:
            handler.forward()
        return handler, state, connection, response, native, stream

    def test_stream_after_two_hours_drains_within_fixed_eight_hour_budget(self):
        handler, state, connection, response, native, stream = self.run_request(28799)
        self.assertEqual(native.call_args.kwargs['timeout'], 28800)
        self.assertEqual(connection.sock.settimeout.call_args_list[-1].args, (1.0,))
        self.assertEqual(handler.wfile.getvalue(), stream)
        self.assertEqual(response.read1.call_count, 2)  # Terminal stream and full HTTP drain.
        state.finish.assert_called_once_with(True)
        self.assertEqual(connection.request.call_count, 2)  # Count then one generation.
        connection.close.assert_called_once()

    def test_absolute_eight_hour_boundary_holds_ambiguous_request_without_replay(self):
        handler, state, connection, response, native, _ = self.run_request(28800)
        self.assertEqual(native.call_args.kwargs['timeout'], 28800)
        response.read1.assert_not_called()
        state.finish.assert_called_once_with(False)
        self.assertEqual(connection.request.call_count, 2)
        connection.close.assert_called_once()
        self.assertEqual(handler.wfile.getvalue(), b'')


class SourceClosureTests(unittest.TestCase):
    def manifest(self):
        paths = [str(o.BASE / 'source' / name) for name in ('owner.py', 'private_proxy.py', 'launch.json')]
        paths += ['/usr/local/lib/llm-server/node-api/scripts/control/' + name
                  for name in ('node.py', 'node_observation.py', 'node_collectors.py', 'passive.py')]
        return {'source_sha256': {name: '0' * 64 for name in paths}, 'qualification_sha256': {}}

    def test_proxy_pin_cannot_be_omitted_from_protected_closure(self):
        manifest = self.manifest()
        del manifest['source_sha256'][str(o.BASE / 'source/private_proxy.py')]
        with patch.object(o, 'validate_manifest'), \
                self.assertRaisesRegex(RuntimeError, 'deployed_source_closure_required'):
            o.source_preflight(None, manifest)

    def test_old_two_hour_proxy_pin_rejects_updated_protected_bytes(self):
        current = (SOURCE / 'private_proxy.py').read_bytes()
        old = current.replace(b'deadline = now + 8 * 60 * 60', b'deadline = now + 7200')
        self.assertNotEqual(current, old)
        manifest = self.manifest()
        proxy = str(o.BASE / 'source/private_proxy.py')
        # Check the changed file first, before any unrelated deployment fixtures.
        manifest['source_sha256'] = {proxy: hashlib.sha256(old).hexdigest(), **manifest['source_sha256']}
        manifest['source_sha256'][proxy] = hashlib.sha256(old).hexdigest()
        h = SimpleNamespace(MountedStorageGuard=lambda _: contextlib.nullcontext(None),
                            s=SimpleNamespace(root_payload_guard=lambda: None))
        with patch.object(o, 'validate_manifest'), patch.object(o, 'storage_paths'), \
                patch.object(o, 'protected', return_value=current) as protected, \
                self.assertRaisesRegex(RuntimeError, 'reviewed_file_changed'):
            o.source_preflight(h, manifest)
        protected.assert_called_once_with(proxy)


if __name__ == '__main__':
    unittest.main()
