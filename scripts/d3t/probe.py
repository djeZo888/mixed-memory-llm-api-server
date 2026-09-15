#!/usr/bin/env python3
"""D3T worker-side phased probe. No deployment, reload, or server-side tools.

Live dispatch is only for the separate live owner after root review. See
README.md. This module is imported by CPU-only tests with an injected transport.
"""
from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import http.client
import json
import os
from pathlib import Path
import socket
import stat
import subprocess
import sys
import threading
import time
from urllib.parse import urlsplit

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE.parent))
from agent.protocol import AgentError, load_api_key, redact, strict_json_loads
from d3t.accounting import wire_body, parse_response, native_account, execute_tool
from d3t import guards
from agent.fixture import Fixture

STAGES = ('baseline', 'candidate', '64k', '128k', '256k', '512k', 'near1m')
TRIAL_MODES = ('comparison', 'native-capacity')
WINDOWS = dict(zip(STAGES, (32768, 32768, 65536, 131072, 262144, 524288, 1048576)))
CAPS = dict(zip(STAGES, (2400, 2400, 7200, 14400, 28800, 43200, 86400)))
MAX_BODY = 32 * 1024 * 1024
MAX_RAW = 2 * 1024 * 1024
STATE_LOCK_TIMEOUT = 5.0
STATE_LOCK_RETRY = 0.025
D1_IMAGE = 'sha256:6866856c573d69d504f82265321b182f631a7b3912a1ed1b4efbf893729d4e62'


def require(ok, code):
    if not ok:
        raise AgentError(code)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def private_read(path, limit=MAX_BODY):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        s = os.fstat(fd)
        require(stat.S_ISREG(s.st_mode) and s.st_uid == os.geteuid()
                and not s.st_mode & 0o077 and s.st_nlink == 1, 'private_file_required')
        require(s.st_size <= limit, 'file_limit')
        with os.fdopen(fd, 'rb', closefd=False) as f:
            data = f.read(limit + 1)
        require(len(data) <= limit, 'file_limit')
        return data
    finally:
        os.close(fd)


def read_json(path, limit=MAX_BODY):
    return strict_json_loads(private_read(path, limit))


def private_dir(path, create=False):
    path = Path(path).absolute()
    require('..' not in path.parts, 'parent_path_refused')
    require(not path.is_relative_to(REPO), 'run_directory_must_be_outside_repository')
    for ancestor in (path, *path.parents):
        require(not ancestor.is_symlink(), 'symlink_directory_refused')
    if create:
        path.mkdir(mode=0o700, parents=False, exist_ok=False)
    s = path.stat()
    require(stat.S_ISDIR(s.st_mode) and s.st_uid == os.geteuid()
            and not s.st_mode & 0o077, 'private_directory_required')
    return path


def write_bytes(path, data):
    """Private same-directory replacement plus fsync. Only owned run paths."""
    tmp = path.with_name('.' + path.name + '.new')
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, 'wb', closefd=False) as f:
            f.write(data)
            f.flush()
            os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(tmp, path)
    fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def write_json(path, obj):
    write_bytes(path, json.dumps(obj, ensure_ascii=False, allow_nan=False,
                               sort_keys=True, separators=(',', ':')).encode())


@contextlib.contextmanager
def lock(run, name='state.lock'):
    """Reject a second request owner immediately; bound short state transactions."""
    fd = os.open(run / name, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        s = os.fstat(fd)
        require(stat.S_ISREG(s.st_mode) and s.st_uid == os.geteuid()
                and not s.st_mode & 0o077 and s.st_nlink == 1, 'unsafe_lock')
        deadline = time.monotonic() + STATE_LOCK_TIMEOUT
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if name != 'state.lock':
                    raise AgentError('owned_request_or_state_busy') from None
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise AgentError('state_lock_timeout') from None
                time.sleep(min(STATE_LOCK_RETRY, remaining))
        yield
    finally:
        os.close(fd)


class Transfer:
    """A single HTTP request in a daemon thread; main worker enforces elapsed cap."""
    def __init__(self, base_url, key, body, stream, timeout):
        self.done = threading.Event()
        self.connection = None
        self.network_socket = None
        self.response = None
        self.raw = None
        self.error = None
        self.status = None
        self.started = time.monotonic()
        self.thread = threading.Thread(target=self._run, args=(base_url, key, body, stream, timeout), daemon=True)
        self.thread.start()

    def _run(self, base_url, key, body, stream, timeout):
        try:
            u = urlsplit(base_url)
            self.connection = http.client.HTTPConnection(u.hostname, u.port, timeout=timeout)
            self.connection.connect()
            self.network_socket = self.connection.sock
            self.connection.request('POST', u.path + '/chat/completions', body=body,
                headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json',
                         'Accept': 'text/event-stream' if stream else 'application/json', 'Accept-Encoding': 'identity'})
            self.response = self.connection.getresponse()
            self.status = self.response.status
            require(self.status == 200, 'http_non_200')
            require(self.response.getheader('Content-Type', '').split(';')[0].strip() ==
                    ('text/event-stream' if stream else 'application/json'), 'response_content_type')
            require(self.response.getheader('Content-Encoding', 'identity') == 'identity', 'response_encoding')
            length = self.response.getheader('Content-Length')
            require(length is None or (length.isdecimal() and int(length) <= MAX_RAW), 'raw_response_limit')
            chunks, total = [], 0
            while True:
                part = self.response.read1(min(65536, MAX_RAW + 1 - total))
                if not part:
                    require(self.response.length in (None, 0), 'truncated_http_body')
                    break
                chunks.append(part)
                total += len(part)
                require(total <= MAX_RAW, 'raw_response_limit')
                # SSE protocol helper requires [DONE]; HTTP chunked streams normally close.
                # Recognize exact complete terminal event even if connection stays alive.
                if stream and b'data: [DONE]\n\n' in b''.join(chunks).replace(b'\r\n', b'\n'):
                    break
            self.raw = b''.join(chunks)
        except Exception:
            self.error = 'transport_failed'
        finally:
            self.cancel()
            self.done.set()

    def cancel(self):
        if self.connection is not None:
            sock = self.network_socket if self.network_socket is not None else self.connection.sock
            if sock is not None:
                try:
                    sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
            self.connection.close()
        if self.response is not None:
            self.response.close()


def phase_for(stage):
    return stage if stage in ('baseline', 'candidate') else 'native'


def steps(stage):
    return ('cold', 'warm', 'tool', 'continuation') if stage in ('baseline', 'candidate') else ('cold', 'tool', 'continuation')


def trial_mode(config):
    mode = config.get('trial_mode', 'comparison')
    require(mode in TRIAL_MODES, 'unknown_trial_mode')
    return mode


def eligible_stages(config):
    return STAGES[2:] if trial_mode(config) == 'native-capacity' else STAGES


def validate_prepare(s, c, stage):
    eligible = eligible_stages(c)
    require(stage in eligible, 'stage_not_in_trial')
    require(s['status'] in ('READY', 'STEP_PASS', 'STAGE_PASS', 'PREPARING'), 'previous_step_not_complete')
    require(s['status'] != 'PREPARING' or s.get('stage') == stage, 'different_stage_preparing')
    idx = eligible.index(stage)
    require(all(s['stages'].get(x, {}).get('status') == 'PASS' for x in eligible[:idx]), 'previous_stage_not_passed')
    require(not any(x in s['stages'] for x in eligible[idx + 1:]), 'cannot_revisit_stage')
    require(s['stages'].get(stage, {}).get('status') != 'PASS', 'stage_already_passed')
    require(phase_for(stage) in c['phases'], 'phase_not_bound')


def init_run(run, base_url, key_file, trial_mode='comparison'):
    require(trial_mode in TRIAL_MODES, 'unknown_trial_mode')
    u = urlsplit(base_url)
    require(u.scheme == 'http' and u.hostname == '127.0.0.1' and u.port is not None
            and u.path == '/v1' and not any((u.username, u.password, u.query, u.fragment)), 'loopback_v1_required')
    require(Path(key_file).is_absolute(), 'protected_key_file_path_required')
    run = private_dir(run, create=True)
    write_json(run / 'config.json', {'base_url': base_url, 'api_key_file': key_file,
                                   'trial_mode': trial_mode, 'phases': {}})
    write_json(run / 'state.json', {'schema_version': 1, 'status': 'READY', 'stages': {},
               'generation_seconds_32k': 0, 'highest_proven_window': None,
               'native_configured_capacity': None})


def bind(run, phase, container_id, image_id):
    """Pin the container separately loaded by live owner; never load/reload here."""
    with lock(run):
        s, c = read_json(run / 'state.json'), read_json(run / 'config.json')
        mode = trial_mode(c)
        require(s['status'] in ('READY', 'STAGE_PASS'), 'bind_only_between_successful_stages')
        require(phase not in c['phases'], 'phase_already_bound_no_reloads')
        if mode == 'native-capacity':
            require(phase == 'native', 'native_capacity_binding_only')
            require(s['status'] == 'READY' and not c['phases'] and not s['stages']
                    and s['highest_proven_window'] is None and s['native_configured_capacity'] is None,
                    'native_capacity_fresh_binding_required')
            # One reviewed source file, not an operator-supplied proof/import path.
            runtime = strict_json_loads((REPO / 'configs/runtimes/llama-cpp-v0.4.1-d3br.json').read_bytes())
            require(runtime['validation']['status'] == 'PASS_BUILD_CLI_ENUMERATION_ONLY'
                    and image_id == runtime['validation']['image_id'] and image_id != D1_IMAGE,
                    'measured_d3rd_image_required')
        else:
            order = ('baseline', 'candidate', 'native')
            require(len(c['phases']) < len(order) and phase == order[len(c['phases'])], 'phase_order')
            if phase != 'baseline':
                prev = 'baseline' if phase == 'candidate' else 'candidate'
                require(s['stages'].get(prev, {}).get('status') == 'PASS', 'comparison_must_pass_before_next_load')
        require((image_id == D1_IMAGE) == (phase == 'baseline'), 'd1_baseline_only')
        if phase == 'native' and mode == 'comparison':
            require(image_id == c['phases']['candidate']['image_id']
                    and container_id != c['phases']['candidate']['container_id'], 'one_native_patched_image_load')
        context = 1048576 if phase == 'native' else 32768
        observed = guards.collect(container_id, image_id, context)
        guards.check_snapshot(observed, native=phase == 'native')
        c['phases'][phase] = {'container_id': container_id, 'image_id': image_id, 'context': context}
        write_json(run / (phase + '.admission.json'), observed)
        write_json(run / 'config.json', c)
        if phase == 'native':
            s['native_configured_capacity'] = context
            write_json(run / 'state.json', s)


def corpus(records):
    """Append-only deterministic reference; three selected records vary by stage."""
    require(type(records) is int and 32 <= records <= 131072, 'corpus_bound')
    rows = [f'item_{i:06d}={digest(f"D3T record {i}".encode())[:16]}\n' for i in range(records)]
    selected = (1, records // 2, records - 2)
    marks = {k: f'item_{i:06d}' for k, i in zip(('early', 'middle', 'late'), selected)}
    expected = {k: digest(f'D3T record {i}'.encode())[:16] for k, i in zip(marks, selected)}
    return ''.join(rows), marks, expected


def cold_body(records, cap):
    text, marks, expected = corpus(records)
    messages = [{'role': 'system', 'content': 'Read the reference carefully. Return only requested facts. Use tools only when requested.'},
                {'role': 'user', 'content': text + '\nReturn only a JSON object with early, middle, late values for these markers: ' + json.dumps(marks, sort_keys=True)}]
    return make_body(messages, cap, False), expected


def make_body(messages, cap, stream):
    b = {'model': 'glm-5.3', 'messages': messages, 'tools': [Fixture.schemas[0]],
         'temperature': 0, 'reasoning_effort': 'low', 'max_tokens': cap, 'stream': stream}
    if stream:
        b['stream_options'] = {'include_usage': True}
    return b


def prefix_count(left, right):
    count = 0
    for a, b in zip(left, right):
        if a != b:
            break
        count += 1
    return count


def compact_accounting(a):
    return {key: a[key] for key in ('input_tokens', 'tokens_sha256', 'rendered_prompt_sha256', 'body_sha256')}


def checked_account(body, phase, stage, initial, accountant=native_account):
    a = accountant(body, phase['container_id'], phase['image_id'])
    require(a['body_sha256'] == wire_body(body)[1] and a['input_tokens'] == len(a['token_ids'])
            and a['tokens_sha256'] == digest(json.dumps(a['token_ids'], separators=(',', ':')).encode()), 'native_body_token_mismatch')
    require(a['configured_context'] == phase['context'], 'actual_native_context_changed')
    window = WINDOWS[stage]
    ceiling = window - (8192 if initial else body['max_tokens'])
    require(a['input_tokens'] <= ceiling, 'native_input_reserve_exceeded')
    if initial and phase_for(stage) == 'native':
        require(a['input_tokens'] >= ceiling - 256, 'native_occupied_target_not_reached')
    return a


def prepare(run, stage, accountant=native_account):
    """Freeze body, actual native template/token accounting, and prefix state."""
    with lock(run, 'request.lock'):
        s, c = read_json(run / 'state.json'), read_json(run / 'config.json')
        validate_prepare(s, c, stage)
        idx = STAGES.index(stage)
        phase = c['phases'][phase_for(stage)]
        rec = s['stages'].setdefault(stage, {'status': 'PENDING', 'results': [], 'started_at': None})
        if rec['started_at'] is None:
            rec['started_at'] = time.time()
        deadline = rec['started_at'] + CAPS[stage]
        require(time.time() < deadline, 'stage_elapsed_cap')
        step = steps(stage)[len(rec['results'])]
        comparison = stage in ('baseline', 'candidate')
        cap = (256 if step in ('cold', 'warm') else 512) if comparison else (128 if step == 'cold' else 256)
        name = stage + '.' + step
        # Commit elapsed cap before accounting: a new session cannot reset time budget.
        s.update(status='PREPARING', stage=stage, step=step, request_name=name, deadline=deadline)
        write_json(run / 'state.json', s)
        if step == 'cold':
            if comparison:
                body, expected = cold_body(64, cap)
                records = 64
            else:
                # Bounded deterministic token fit, never runtime tuning or generation.
                low = 32 if idx == 2 else s['stages'][STAGES[idx - 1]]['records'] + 1
                high, best = 131072, None
                for _ in range(18):
                    if low > high:
                        break
                    require(time.time() < deadline, 'stage_elapsed_cap')
                    n = (low + high) // 2
                    b, e = cold_body(n, cap)
                    candidate = accountant(b, phase['container_id'], phase['image_id'])
                    if candidate['input_tokens'] <= WINDOWS[stage] - 8192:
                        best = (n, b, e, candidate)
                        low = n + 1
                    else:
                        high = n - 1
                require(best is not None, 'native_corpus_fit_failed')
                records, body, expected, a = best
            rec['records'], rec['expected'] = records, expected
        elif step == 'warm':
            body = read_json(run / (stage + '.cold.body.json'))
        elif step == 'tool' and comparison:
            # Independent frozen tool fixture: exactly equal baseline/candidate body.
            body = make_body([{'role': 'user', 'content': 'Call read_file exactly once for calc.py on the worker. After the result, reply exactly LOCAL_READ_OK: return a - b'}], cap, True)
        else:
            previous_name = rec['results'][-1]['name']
            previous_body = read_json(run / (previous_name + '.body.json'))
            previous_response = read_json(run / (previous_name + '.response.json'))
            messages = previous_body['messages'] + [previous_response['message']]
            if step == 'tool':
                messages += [{'role': 'user', 'content': 'Call read_file exactly once for calc.py on the worker. After the result, reply exactly LOCAL_READ_OK: return a - b'}]
            else:
                messages += [read_json(run / (stage + '.tool.result.json'))['message']]
            body = make_body(messages, cap, step == 'tool' or (not comparison and step == 'continuation'))
        # Every frozen outgoing request has real accounting, including continuations.
        a = checked_account(body, phase, stage, step == 'cold', accountant)
        require(time.time() < deadline, 'stage_elapsed_cap')
        raw, sha = wire_body(body)
        require(len(raw) <= MAX_BODY, 'body_limit')
        if 'template_sha256' in c:
            require(a['template_sha256'] == c['template_sha256'], 'actual_loaded_template_changed')
        else:
            c['template_sha256'] = a['template_sha256']
            write_json(run / 'config.json', c)
        if stage == 'candidate' and step != 'continuation':
            require(raw == private_read(run / ('baseline.' + step + '.body.json')), 'comparison_body_mismatch')
        if stage == 'candidate' and step == 'continuation':
            def normalized(value):
                value = json.loads(json.dumps(value))
                for message in value['messages']:
                    if message['role'] == 'tool':
                        message['tool_call_id'] = 'MATCHED_TOOL_ID'
                    for call in message.get('tool_calls', []):
                        call['id'] = 'MATCHED_TOOL_ID'
                return value
            require(normalized(body) == normalized(read_json(run / 'baseline.continuation.body.json')),
                    'continuation_comparison_differs_beyond_native_tool_id')
        previous_a = None
        if rec['results']:
            previous_a = read_json(run / (rec['results'][-1]['name'] + '.tokens.json'))
        elif idx > 2:
            previous_a = read_json(run / (STAGES[idx - 1] + '.cold.tokens.json'))
        common = prefix_count(previous_a['token_ids'], a['token_ids']) if previous_a else None
        write_bytes(run / (name + '.body.json'), raw)
        write_json(run / (name + '.tokens.json'), a)
        summary = compact_accounting(a)
        summary['common_prefix_tokens'] = common
        s.update(status='PREPARED', body_sha256=sha, accounting=summary)
        write_json(run / 'state.json', s)


def launch_prepare(run, stage):
    # Native token fitting may take minutes; coordinator only observes this child.
    with lock(run):
        s, c = read_json(run / 'state.json'), read_json(run / 'config.json')
        validate_prepare(s, c, stage)
        require(s['status'] in ('READY', 'STEP_PASS', 'STAGE_PASS'), 'previous_step_not_complete')
        s.update(status='PREPARING', stage=stage)
        write_json(run / 'state.json', s)
        with open(os.devnull, 'wb') as sink:
            subprocess.Popen([sys.executable, '-B', str(Path(__file__).resolve()), '_prepare',
                              '--run', str(run), '--stage', stage],
                stdin=subprocess.DEVNULL, stdout=sink, stderr=sink, cwd=run,
                env={'PATH': os.defpath, 'PYTHONDONTWRITEBYTECODE': '1'},
                start_new_session=True, close_fds=True)


def launch(run):
    with lock(run):
        s, c = read_json(run / 'state.json'), read_json(run / 'config.json')
        require(s.get('stage') in eligible_stages(c), 'stage_not_in_trial')
        require(s['status'] == 'PREPARED', 'dispatch_already_attempted_or_not_prepared')
        now = time.time()
        deadline = s['deadline']
        if s['stage'] in ('baseline', 'candidate'):
            deadline = min(deadline, now + 600, now + 2400 - s['generation_seconds_32k'])
        require(deadline > now, 'approved_elapsed_budget_exhausted')
        s.update(status='STARTING', request_deadline=deadline, dispatched_at=None, cancel_requested=False)
        write_json(run / 'state.json', s)  # Durable before spawn: never automatically retry.
    env = {'PATH': os.defpath, 'PYTHONDONTWRITEBYTECODE': '1'}
    with open(os.devnull, 'wb') as sink:
        subprocess.Popen([sys.executable, '-B', str(Path(__file__).resolve()), '_worker', '--run', str(run)],
                    stdin=subprocess.DEVNULL, stdout=sink, stderr=sink, cwd=run,
                    env=env, start_new_session=True, close_fds=True)


def check_correctness(run, s, parsed):
    message, step, stage = parsed['message'], s['step'], s['stage']
    if step in ('cold', 'warm'):
        require(not message.get('tool_calls') and strict_json_loads(message.get('content', '')) == s['stages'][stage]['expected'], 'retrieval_sentinel_mismatch')
        return {'early': True, 'middle': True, 'late': True}
    if step == 'tool':
        message, evidence = execute_tool(message, workspace_parent=str(run))
        write_json(run / (stage + '.tool.result.json'), {'message': message, 'evidence': evidence})
        return evidence
    require(not message.get('tool_calls') and message.get('content', '').strip() == 'LOCAL_READ_OK: return a - b', 'tool_continuation_mismatch')
    return {'tool_continuation': True}


def check_cache(s, parsed):
    counts = parsed['counters']
    actual = counts['prompt_tokens']
    require(actual is not None and actual == s['accounting']['input_tokens'], 'actual_usage_vs_native_accounting_NOT_TESTED')
    cached = counts['cached_tokens']
    common = s['accounting']['common_prefix_tokens']
    step, stage = s['step'], s['stage']
    if stage in ('baseline', 'candidate') and step == 'cold':
        require(cached == 0, 'cold_cache_NOT_TESTED')
    reuse = step in ('warm', 'continuation') or (phase_for(stage) == 'native' and (step == 'tool' or STAGES.index(stage) > 2))
    if reuse:
        require(type(cached) is int and type(common) is int and common > 0
                and max(1, common - 256) <= cached <= actual, 'useful_prefix_reuse_NOT_TESTED')


def worker(run, transport=Transfer, sampler_factory=None):
    """One durable worker process, one request, cooperative socket-only cancel."""
    with lock(run, 'request.lock'):
        transfer, sampler = None, None
        started = time.monotonic()
        try:
            with lock(run):
                s, c = read_json(run / 'state.json'), read_json(run / 'config.json')
                require(s.get('stage') in eligible_stages(c), 'stage_not_in_trial')
                require(s['status'] == 'STARTING' and not s['cancel_requested'], 'worker_start_state')
                phase = c['phases'][phase_for(s['stage'])]
                key = load_api_key(path=c['api_key_file'])
                raw = private_read(run / (s['request_name'] + '.body.json'))
                require(digest(raw) == s['body_sha256'] and key.encode() not in raw, 'body_changed_or_contains_key')
                require(time.time() < s['request_deadline'], 'deadline_before_dispatch')
            body = strict_json_loads(raw)
            sampler = (sampler_factory or guards.Sampler)(phase['container_id'], phase['image_id'], phase['context'],
                         min(86400, max(1, int(s['request_deadline'] - time.time()) + 1)))
            first = sampler.next(timeout=15)
            guards.check_snapshot(first, native=phase_for(s['stage']) == 'native')
            admission = read_json(run / (phase_for(s['stage']) + '.admission.json'))
            require(guards.stable_identity(first) == guards.stable_identity(admission), 'bound_runtime_restarted_or_changed')
            require(first['vmstat'] == admission['vmstat'], 'swap_or_oom_since_admission')
            with lock(run):
                latest = read_json(run / 'state.json')
                require(not latest['cancel_requested'], 'cancel_before_dispatch')
                require(time.time() < s['request_deadline'], 'deadline_before_dispatch')
                s.update(status='IN_FLIGHT', dispatched_at=time.time())
                write_json(run / 'state.json', s)
            transfer = transport(c['base_url'], key, raw, body['stream'], max(.001, s['request_deadline'] - time.time()))
            count, previous = 0, None
            extrema = {'gpu_min_free_bytes': {}, 'rss_max_kib': None, 'pss_max_kib': None, 'mem_available_min_kib': None}
            sample = first
            completion_seen = False
            with open(run / (s['request_name'] + '.samples.jsonl'), 'xb', opener=lambda p, flags: os.open(p, flags | os.O_NOFOLLOW, 0o600)) as log:
                while True:
                    guards.check_snapshot(sample, native=phase_for(s['stage']) == 'native', previous=previous)
                    log.write(json.dumps(sample, separators=(',', ':')).encode() + b'\n')
                    log.flush()
                    count += 1
                    for gpu in sample['gpus']:
                        old = extrema['gpu_min_free_bytes'].get(gpu['uuid'], gpu['free_bytes'])
                        extrema['gpu_min_free_bytes'][gpu['uuid']] = min(old, gpu['free_bytes'])
                    for dest, value in (('rss_max_kib', sample['process_kib']['Rss']), ('pss_max_kib', sample['process_kib']['Pss'])):
                        extrema[dest] = value if extrema[dest] is None else max(extrema[dest], value)
                    available = sample['host_kib']['MemAvailable']
                    extrema['mem_available_min_kib'] = available if extrema['mem_available_min_kib'] is None else min(extrema['mem_available_min_kib'], available)
                    previous = sample
                    require(time.time() <= s['request_deadline'], 'stage_timeout')
                    with lock(run):
                        latest = read_json(run / 'state.json')
                    require(not latest['cancel_requested'], 'owner_cancelled')
                    require(time.time() <= s['request_deadline'], 'stage_timeout')
                    if transfer.done.is_set():
                        if completion_seen:
                            break
                        completion_seen = True
                    sample = sampler.next(timeout=min(3, max(.001, s['request_deadline'] - time.time())))
            require(transfer.error is None and transfer.raw is not None, 'transport_failed')
            parsed = parse_response(transfer.raw, body['stream'], 'glm-5.3')
            safe_parsed = redact(parsed, key)
            if safe_parsed != parsed:
                write_json(run / (s['request_name'] + '.redacted-response.json'),
                           {'original_sha256': digest(transfer.raw), 'redacted': True, 'response': safe_parsed})
                raise AgentError('credential_echo_response_refused')
            safe_raw = redact(transfer.raw.decode('utf-8'), key).encode()
            write_bytes(run / (s['request_name'] + '.raw'), safe_raw)
            require(safe_raw == transfer.raw, 'credential_echo_response_refused')
            parsed['counters']['elapsed_seconds'] = time.monotonic() - started
            checks = check_correctness(run, s, parsed)
            write_json(run / (s['request_name'] + '.response.json'), parsed)
            check_cache(s, parsed)
            elapsed = time.monotonic() - started
            result = {'name': s['request_name'], 'status': 'PASS', 'body_sha256': digest(raw),
                      'raw_sha256': digest(transfer.raw), 'elapsed_seconds': elapsed,
                      'accounting': s['accounting'], 'counters': parsed['counters'],
                      'checks': checks, 'sample_count': count, 'sampled_extrema': extrema,
                      'resource_evidence': 'bounded_1Hz_samples_not_instantaneous_peaks'}
            with lock(run):
                s = read_json(run / 'state.json')
                require(not s['cancel_requested'], 'owner_cancelled')
                require(time.time() <= s['request_deadline'], 'stage_timeout')
                rec = s['stages'][s['stage']]
                rec['results'].append(result)
                if s['stage'] in ('baseline', 'candidate'):
                    s['generation_seconds_32k'] += elapsed
                done = len(rec['results']) == len(steps(s['stage']))
                rec['status'] = 'PASS' if done else 'PENDING'
                s['status'] = 'STAGE_PASS' if done else 'STEP_PASS'
                if done and phase_for(s['stage']) == 'native':
                    s['highest_proven_window'] = WINDOWS[s['stage']]
                write_json(run / 'state.json', s)
        except Exception as exc:
            if transfer:
                transfer.cancel()
            with lock(run):
                s = read_json(run / 'state.json')
                s['status'] = 'PENDING_RECONCILIATION' if s.get('dispatched_at') else 'NOT_TESTED'
                # Only constant task codes, never raw backend/socket exception text.
                safe = str(exc) if isinstance(exc, AgentError) else ''
                s['failure_class'] = safe if safe.replace('_', '').isalnum() and len(safe) <= 96 else 'bounded_stage_stopped'
                s['elapsed_seconds'] = time.monotonic() - started
                s['later_stages'] = 'PENDING_NOT_TESTED'
                write_json(run / 'state.json', s)
        finally:
            if transfer:
                transfer.cancel()
            if sampler:
                sampler.close()


def status(run):
    with lock(run):
        s, c = read_json(run / 'state.json'), read_json(run / 'config.json')
        mode = trial_mode(c)
        eligible = eligible_stages(c)
    apparent = s['status']
    if apparent in ('STARTING', 'IN_FLIGHT', 'PREPARING'):
        try:
            with lock(run, 'request.lock'):
                apparent = 'PREPARATION_UNKNOWN' if apparent == 'PREPARING' else 'IN_FLIGHT_UNKNOWN'
        except AgentError:
            pass
    return {'schema_version': 1, 'trial_mode': mode,
            'comparison_status': 'NOT_RUN_IN_THIS_TRIAL' if mode == 'native-capacity' else
                {stage: s['stages'].get(stage, {}).get('status', 'PENDING_NOT_TESTED') for stage in STAGES[:2]},
            'status': apparent, 'stage': s.get('stage'), 'step': s.get('step'),
            'body_sha256': s.get('body_sha256'), 'deadline': s.get('request_deadline', s.get('deadline')),
            'highest_proven_window': s['highest_proven_window'], 'native_configured_capacity': s['native_configured_capacity'],
            'stage_status': {stage: s['stages'].get(stage, {}).get('status', 'PENDING_NOT_TESTED') for stage in eligible},
            'accounting': s.get('accounting'), 'failure_class': s.get('failure_class'),
            'monitor_again_within_seconds': 60}


def cancel(run):
    with lock(run):
        s = read_json(run / 'state.json')
        require(s['status'] in ('STARTING', 'IN_FLIGHT'), 'no_owned_active_request')
        s['cancel_requested'] = True
        write_json(run / 'state.json', s)


def main(argv=None):
    os.umask(0o077)
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='command', required=True)
    for name in ('init', 'bind', 'prepare', 'start', 'status', 'cancel', '_worker', '_prepare'):
        a = sub.add_parser(name)
        a.add_argument('--run', required=True)
        if name == 'init':
            a.add_argument('--base-url', required=True)
            a.add_argument('--key-file', required=True)
            a.add_argument('--trial-mode', choices=TRIAL_MODES, default='comparison')
        if name == 'bind':
            a.add_argument('--phase', choices=('baseline', 'candidate', 'native'), required=True)
            a.add_argument('--container-id', required=True)
            a.add_argument('--image-id', required=True)
        if name in ('prepare', '_prepare'):
            a.add_argument('--stage', choices=STAGES, required=True)
    a = p.parse_args(argv)
    try:
        if a.command == 'init':
            init_run(a.run, a.base_url, a.key_file, a.trial_mode)
        else:
            run = private_dir(a.run)
            if a.command == 'bind':
                bind(run, a.phase, a.container_id, a.image_id)
            elif a.command == 'prepare':
                launch_prepare(run, a.stage)
            elif a.command == '_prepare':
                prepare(run, a.stage)
            elif a.command == 'start':
                launch(run)
            elif a.command == '_worker':
                worker(run)
            elif a.command == 'cancel':
                cancel(run)
        if a.command not in ('_worker', '_prepare'):
            print(json.dumps(status(private_dir(a.run)), sort_keys=True))
        return 0
    except Exception:
        if a.command == '_prepare':
            # Failure publication cannot steal an active preparation's lock.
            # If either bounded lock refuses, retain the durable unknown state.
            with contextlib.suppress(Exception):
                run = private_dir(a.run)
                with lock(run, 'request.lock'), lock(run):
                    state = read_json(run / 'state.json')
                    # Refused invocations cannot overwrite dispatched/failed
                    # checkpoints or another stage's durable preparation.
                    if state['status'] == 'PREPARING' and state.get('stage') == a.stage:
                        config = read_json(run / 'config.json')
                        if config.get('trial_mode', 'comparison') in TRIAL_MODES and a.stage in eligible_stages(config):
                            state.update(status='NOT_TESTED', failure_class='native_preparation_stopped', later_stages='PENDING_NOT_TESTED')
                            write_json(run / 'state.json', state)
        print(json.dumps({'status': 'REFUSED', 'reason': 'inspect_phase_contract_and_private_checkpoint'}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
