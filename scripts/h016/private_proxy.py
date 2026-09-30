#!/usr/bin/env python3
"""Fixed H016 private IPv4 authenticated route proxy. No request/body logging."""
import argparse
import hmac
import http.client
import http.server
import ipaddress
import json
import socket
import threading
import datetime
import time
from verify_retained import dependency

ROUTES = {('POST', '/v1/chat/completions/input_tokens'),
          ('POST', '/v1/chat/completions'), ('GET', '/props'),
          ('GET', '/slots'), ('GET', '/v1/readiness')}
MODEL = 'mimo-v2.6-pro-rl'
MAX_BODY = 16 * 1024 * 1024
FIELDS = {'model', 'messages', 'tools', 'tool_choice', 'parallel_tool_calls',
          'max_tokens', 'max_completion_tokens', 'temperature', 'top_p', 'seed',
          'stream', 'stream_options', 'chat_template_kwargs', 'stop', 'n', 'reasoning_format', 'add_generation_prompt'}


def normalize(body):
    if not isinstance(body, dict) or set(body) - FIELDS or body.get('model') != MODEL:
        raise ValueError('closed_model_request_required')
    messages = body.get('messages')
    if not isinstance(messages, list) or not messages:
        raise ValueError('messages_required')
    for m in messages:
        if not isinstance(m, dict) or set(m) - {'role', 'content', 'name', 'tool_calls', 'tool_call_id', 'reasoning_content'}:
            raise ValueError('closed_message_required')
        if m.get('role') not in {'system', 'developer', 'user', 'assistant', 'tool'}:
            raise ValueError('role_required')
        c = m.get('content')
        if isinstance(c, list):
            if any(type(x) is not dict or set(x) != {'type', 'text'} or x['type'] != 'text' or not isinstance(x['text'], str) for x in c):
                raise ValueError('text_only')
        elif not isinstance(c, str) and not (c is None and m['role'] == 'assistant' and m.get('tool_calls')):
            raise ValueError('text_only')
    if 'max_completion_tokens' in body:
        raise ValueError('canonical_max_tokens_required')
    outputs = [body[k] for k in ['max_tokens'] if k in body]
    if len(outputs) != 1 or type(outputs[0]) is not int or not 1 <= outputs[0] <= 65536:
        raise ValueError('output_budget_1_to_65536_required')
    if body.get('n', 1) != 1 or body.get('parallel_tool_calls', False) is not False:
        raise ValueError('serial_required')
    if body.get('tool_choice', 'auto') not in ['auto', 'none']:
        raise ValueError('tool_choice_unqualified')
    kwargs = body.get('chat_template_kwargs')
    if not isinstance(kwargs, dict) or set(kwargs) != {'enable_thinking'} or type(kwargs['enable_thinking']) is not bool:
        raise ValueError('thinking_boolean_required')
    if body.get('stream') is not True:
        raise ValueError('stream_required')
    if body.get('stream_options') != {'include_usage': True}:
        raise ValueError('usage_required')
    if body.get('reasoning_format') != 'deepseek' or body.get('add_generation_prompt') is not True:
        raise ValueError('canonical_template_required')
    return body


def read_key(h):
    with h.MountedStorageGuard(h.s) as g, h.AnchoredRoot('/data/services/secrets', g) as a, a.open('llm-api-key') as f:
        st = f.stat()
        raw = f.read(4097)
        h.require(len(raw) <= 4096, 'invalid_key_file')
        key = raw.rstrip()
        h.require(st.st_mode & 0o777 == 0o600 and 1 <= len(key) <= 4096 and all(33 <= x <= 126 for x in key), 'invalid_key_file')
        return key


def serve():
    h = dependency()
    key = read_key(h)
    probe = http.client.HTTPConnection('127.0.0.1', 30012, timeout=10)
    probe.request('GET', '/props', headers={'Authorization': 'Bearer ' + key.decode()})
    response = probe.getresponse()
    props = json.loads(response.read())
    probe.close()
    capacity = props.get('default_generation_settings', {}).get('n_ctx')
    h.require(response.status == 200 and capacity == 131072 and props.get('total_slots') == 1 and props.get('model_alias') == MODEL and props.get('is_sleeping') is False, 'loaded_capacity_identity_required')
    owner = threading.Lock()
    quarantine = threading.Event()

    class Handler(http.server.BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.0'

        def log_message(self, *_):
            pass

        def error(self, status):
            self.send_response(status)
            self.send_header('Content-Length', '0')
            self.end_headers()
            self.close_connection = True

        def do_GET(self):
            self.forward()

        def do_POST(self):
            self.forward()

        def forward(self):
            if ipaddress.ip_address(self.client_address[0]) not in ipaddress.ip_network('10.156.100.0/24'):
                return self.error(403)
            values = self.headers.get_all('Authorization') or []
            if len(values) != 1 or not hmac.compare_digest(values[0].encode(), b'Bearer ' + key):
                return self.error(401)
            if (self.command, self.path) not in ROUTES:
                return self.error(404)
            chat = self.path == '/v1/chat/completions'
            now = time.time()
            if chat and now >= datetime.datetime(2026, 9, 27, 13, 25, tzinfo=datetime.timezone.utc).timestamp():
                return self.error(503)
            deadline = min(now + 7200, datetime.datetime(2026, 9, 27, 13, 40, tzinfo=datetime.timezone.utc).timestamp())
            if now >= deadline:
                return self.error(503)
            owned = False
            conn = None
            terminal = False
            try:
                raw = None
                if self.command == 'POST':
                    lengths = self.headers.get_all('Content-Length') or []
                    if self.headers.get('Transfer-Encoding') or len(lengths) != 1:
                        return self.error(400)
                    size = int(lengths[0])
                    if not 0 < size <= MAX_BODY:
                        return self.error(413)
                    self.connection.settimeout(15)
                    data = self.rfile.read(size)
                    if len(data) != size:
                        return self.error(400)
                    body = normalize(json.loads(data))
                    raw = json.dumps(body).encode()
                if chat:
                    if quarantine.is_set():
                        return self.error(503)
                    owned = owner.acquire(blocking=False)
                    if not owned:
                        return self.error(429)
                path = '/health' if self.path == '/v1/readiness' else self.path
                conn = http.client.HTTPConnection('127.0.0.1', 30012, timeout=max(.1, deadline - time.time()))
                if chat:
                    conn.request('POST', '/v1/chat/completions/input_tokens', raw, {'Authorization': 'Bearer ' + key.decode(), 'Content-Type': 'application/json'})
                    counted = conn.getresponse()
                    count_body = json.loads(counted.read())
                    budget = body.get('max_tokens', body.get('max_completion_tokens'))
                    if counted.status != 200 or type(count_body.get('input_tokens')) is not int or count_body['input_tokens'] + budget > capacity - 1:
                        terminal = True  # Rejected before native generation.
                        return self.error(400)
                conn.request(self.command, path, raw, {'Authorization': 'Bearer ' + key.decode(), 'Content-Type': 'application/json'})
                response = conn.getresponse()
                self.send_response(response.status)
                self.send_header('Content-Type', response.getheader('Content-Type', 'application/json'))
                self.send_header('Connection', 'close')
                self.end_headers()
                self.connection.settimeout(5)
                detached = False
                pending = b''
                done = finish = usage = False
                while True:
                    if time.time() >= deadline:
                        raise TimeoutError('owned_absolute_deadline')
                    if conn.sock:
                        conn.sock.settimeout(max(.1, deadline - time.time()))
                    chunk = response.read1(65536)
                    if not chunk:
                        break
                    if chat:
                        pending += chunk
                        while b'\n' in pending:
                            line, pending = pending.split(b'\n', 1)
                            if line.startswith(b'data: '):
                                item = line[6:].strip()
                                if item == b'[DONE]':
                                    done = True
                                else:
                                    event = json.loads(item)
                                    usage |= isinstance(event.get('usage'), dict)
                                    finish |= any(x.get('finish_reason') in ['stop', 'length', 'tool_calls'] for x in event.get('choices', []))
                        if len(pending) > MAX_BODY:
                            raise ValueError('sse_bound')
                    if not detached:
                        try:
                            self.wfile.write(chunk)
                            self.wfile.flush()
                        except (BrokenPipeError, ConnectionResetError, socket.timeout):
                            detached = True  # Keep draining exact upstream; never retry.
                terminal = response.status == 200 and (not chat or (done and finish and usage and not pending.strip()))
            except (ValueError, TypeError, json.JSONDecodeError):
                if conn is None:
                    self.error(400)
            except Exception:
                pass  # Never include headers/body/credential in traceback or logs.
            finally:
                if conn:
                    conn.close()
                if owned:
                    if not terminal:
                        quarantine.set()
                    owner.release()
                self.close_connection = True

    server = http.server.ThreadingHTTPServer(('10.156.100.60', 30012), Handler, bind_and_activate=False)
    server.socket.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, b'enp6s18\0')
    server.server_bind()
    server.server_activate()
    server.daemon_threads = True
    server.serve_forever()


if __name__ == '__main__':
    argparse.ArgumentParser(description=__doc__).parse_args()
    serve()
