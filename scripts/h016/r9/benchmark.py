"""R9 final-setting serial qualification, owned by the durable Linux supervisor.

Private request/raw stream receipts stay under the registered task log root.
No CLI receiver, retries, optional profiler, or service/lifecycle mutation here.
"""
import base64
import copy
import contextlib
import datetime
import hashlib
import http.client
import io
import json
import os
import pathlib
import random
import time
from candidate_owner import ADMIT_END, HARD_END, BASE, LOG, get, save
from telemetry import bounded_placement
MODEL = 'mimo-v2.6-pro-rl'
SEED = 270927
CLIENT_END = min(HARD_END - 480, datetime.datetime(2026, 9, 27, 17, 17,
                 tzinfo=datetime.timezone.utc).timestamp())
TOOL_TURN_SECONDS = 450
PREFILL_PLANNING_TOKENS_PER_SECOND = 61.0
DECODE_PLANNING_TOKENS_PER_SECOND = 7.76
PLANNING_MARGIN = 1.20
PLANNING_OVERHEAD_SECONDS = 30
FIXTURE_SHA = '2fb03cef2e700b304f8eea538a5ef8df300afc53bb0a94241bc754c17679ef78'
TOOLS_SHA = '80e7a1e12e073ac57638e86638cf571158711ff821c96605135627777ce44e8c'
READ_NAME = 'FINAL17-READ.txt'
READ_TEXT = 'A=2\nB=3\nMARKER=H016_R9_REAL_READ_20260927\n'
READ_MARKER = 'H016_R9_REAL_READ_20260927'


def utc_now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='microseconds')


def body(text, thinking=False, output=256):
    return {'model': MODEL, 'messages': [{'role': 'user', 'content': text}], 'max_tokens': output, 'n': 1, 'stream': True, 'stream_options': {'include_usage': True}, 'tool_choice': 'auto', 'parallel_tool_calls': False, 'chat_template_kwargs': {'enable_thinking': thinking}, 'reasoning_format': 'deepseek', 'add_generation_prompt': True, 'temperature': 0, 'seed': SEED}


def count(key, payload):
    raw = json.dumps(payload, separators=(',', ':'), ensure_ascii=False).encode()
    c = http.client.HTTPConnection('127.0.0.1', 30012, timeout=30)
    try:
        c.request('POST', '/v1/chat/completions/input_tokens', raw, {'Authorization': 'Bearer ' + key.decode(), 'Content-Type': 'application/json'})
        r = c.getresponse()
        j = json.loads(r.read())
        if r.status != 200 or type(j.get('input_tokens')) is not int:
            raise RuntimeError('native_count_failed')
        return j['input_tokens'], raw
    finally:
        c.close()


def fixture(key, target, salt, before_count=lambda: None):
    rng = random.Random(hashlib.sha256(salt.encode()).digest())
    codes = [''.join(rng.choice('ABCDEFGHJKLMNPQRSTUVWXYZ23456789') for _ in range(8)) for _ in range(3)]
    paragraphs = []
    for i in range(target // 12 + 128):
        port, tick, value = rng.randrange(1, 32), rng.randrange(1000, 99999), rng.randrange(1, 65535)
        style = i % 4
        paragraphs.append([
            f'Log{tick}: channel{port} sample={value}; CRC checked; queue drained after acknowledgement.\n',
            f'uint32_t sample_{i} = {value}u; if (sample_{i} > 4095u) sample_{i} = 4095u; // saturate ADC\n',
            f'| sensor{port} | period {tick} us | reading {value} | calibration pending |\n',
            f'Review note{i}: a pull-up resistor establishes the idle logic level; open-drain outputs must not drive high. Buffer{port} stores {value} events.\n'
        ][style])
    words = ''.join(paragraphs).split(' ')
    def make(n):
        a, b = n // 2, n - n // 2
        text = ('Technical retrieval fixture ' + salt + '. Record the three labelled codes.\nEARLY_CODE=' + codes[0] + '\n' + ' '.join(words[:a]) + '\nMIDDLE_CODE=' + codes[1] + '\n' + ' '.join(words[a:a+b]) + '\nEND_CODE=' + codes[2] + '\nReturn only a JSON object with exactly these keys: codes (array in early/middle/end order), product (integer 17*19), and safe_adc (integer min(5000,4095)).')
        return body(text)
    n = min(len(words), max(1, target // 2))
    prior = set()
    for _ in range(40):
        before_count()
        payload = make(n)
        actual, raw = count(key, payload)
        if actual == target:
            return payload, raw, codes
        # First fit varied material, then add a bounded one-token pad only for exact alignment.
        delta = target - actual
        if n in prior or abs(delta) < 32:
            if delta >= 0:
                for pad in [' x', ' 0', '\n']:
                    fixed = make(n)
                    fixed['messages'][0]['content'] += pad * delta
                    before_count()
                    got, raw = count(key, fixed)
                    if got == target:
                        return fixed, raw, codes
            n = max(1, n - max(1, abs(delta) // 2))
        else:
            prior.add(n)
            n = max(1, min(len(words), int(n * target / actual)))
    raise RuntimeError('exact_varied_fixture_count_not_converged')


def admit(h, failed, planning_seconds=0):
    """Every count and generation has an absolute gate; estimates are not results."""
    now = time.time()
    h.require(now < ADMIT_END and not failed.is_set(), 'benchmark_admission_closed')
    h.require(planning_seconds >= 0 and now + planning_seconds < CLIENT_END,
              'conservative_client_completion_budget_unavailable')


def request(h, key, payload, label, failed, capacity, planning_seconds=0):
    h.require(not pathlib.Path(LOG, label + '.json').exists(), 'existing_receipt_no_replay')
    admit(h, failed, planning_seconds)
    expected, raw = count(key, payload)
    h.require(expected + payload['max_tokens'] <= capacity - 1, 'context_admission')
    admit(h, failed, planning_seconds)
    start = time.monotonic()
    deadline = CLIENT_END
    row = {'label': label, 'started_utc': h.now(), 'started_monotonic_seconds': start, 'raw_chunks': [], 'terminal_sse_events': [], 'expected_input_tokens': expected, 'request_sha256': hashlib.sha256(raw).hexdigest(), 'thinking': payload['chat_template_kwargs']['enable_thinking'], 'output_budget': payload['max_tokens'], 'status': 'SUBMITTED'}
    row['client_deadline_utc'] = datetime.datetime.fromtimestamp(deadline, datetime.timezone.utc).isoformat()
    row['client_bound_seconds'] = deadline - time.time()
    row['admission_planning_seconds'] = planning_seconds
    save(h, label + '.json', row)
    c = http.client.HTTPConnection('127.0.0.1', 30012, timeout=max(.1, deadline - time.time()))
    response = None
    progress_stack = contextlib.ExitStack()
    try:
        # Open once before transmission; no lifecycle lease spans this request.
        # FIRST_OUTPUT is a single unbuffered write, without hot-path guards/fsync.
        progress_guard = progress_stack.enter_context(h.MountedStorageGuard(h.s))
        progress_root = progress_stack.enter_context(h.AnchoredRoot(LOG, progress_guard))
        progress_file = progress_stack.enter_context(progress_root.open(label + '-PROGRESS.jsonl', os.O_WRONLY | os.O_CREAT | os.O_EXCL))
        progress_fd = progress_file.fileno()
        # Exact request bytes counted above are persisted and sent unchanged.
        request_file = progress_stack.enter_context(progress_root.open(label + '-REQUEST.json', os.O_WRONLY | os.O_CREAT | os.O_EXCL))
        request_writer = progress_stack.enter_context(io.BufferedWriter(io.FileIO(os.dup(request_file.fileno()), 'wb'), buffer_size=65536))
        request_writer.write(raw)
        request_writer.flush()
        capture_file = progress_stack.enter_context(progress_root.open(label + '-RAW.jsonl', os.O_WRONLY | os.O_CREAT | os.O_EXCL))
        capture_writer = progress_stack.enter_context(io.BufferedWriter(io.FileIO(os.dup(capture_file.fileno()), 'wb'), buffer_size=65536))
        row['private_raw_trace'] = label + '-RAW.jsonl'
        capture_flush = time.monotonic()
        capture_bytes = 0
        admit(h, failed, planning_seconds)
        c.request('POST', '/v1/chat/completions', raw, {'Authorization': 'Bearer ' + key.decode(), 'Content-Type': 'application/json'})
        row['request_sent_monotonic_seconds'] = time.monotonic()
        row['request_sent_utc'] = utc_now()
        sent = {'event': 'BODY_SENT', 'label': label, 'utc': row['request_sent_utc'],
                'monotonic_seconds': row['request_sent_monotonic_seconds'],
                'request_sha256': row['request_sha256'], 'expected_input_tokens': expected,
                'client_deadline_utc': row['client_deadline_utc']}
        sent_line = (json.dumps(sent, separators=(',', ':')) + '\n').encode()
        h.require(os.write(progress_fd, sent_line) == len(sent_line), 'body_sent_progress_short_write')
        response = c.getresponse()
        h.require(response.status == 200, 'native_http_failure')
        done, usage, finish = False, None, None
        content, reasoning, calls = '', '', {}
        pending = b''
        while True:
            h.require(time.time() < deadline and not failed.is_set(), 'request_guard_or_deadline')
            if c.sock:
                c.sock.settimeout(max(.1, deadline - time.time()))
            chunk = response.read1(65536)
            if not chunk:
                break
            received = time.monotonic()
            received_utc = utc_now()
            row['raw_chunks'].append({'utc': received_utc, 'monotonic_seconds': received, 'elapsed_seconds': received - start, 'bytes': len(chunk), 'base64': base64.b64encode(chunk).decode('ascii')})
            capture_bytes += len(chunk)
            h.require(capture_bytes <= 64 * 1024 * 1024, 'raw_stream_bound')
            capture_writer.write((json.dumps(row['raw_chunks'][-1], separators=(',', ':')) + '\n').encode())
            # Bounded buffered checkpoints only. No per-delta fsync, guard or lease.
            if received - capture_flush >= 5:
                capture_writer.flush()
                capture_flush = received
            pending += chunk
            while b'\n' in pending:
                line, pending = pending.split(b'\n', 1)
                if not line.startswith(b'data: '):
                    continue
                data = line[6:].strip()
                if data == b'[DONE]':
                    done = True
                    row.update(done_utc=received_utc, done_monotonic_seconds=received)
                    row['terminal_sse_events'].append({'utc': received_utc, 'monotonic_seconds': received, 'data': '[DONE]'})
                    continue
                event = json.loads(data)
                if event.get('usage') or event.get('timings') or any(x.get('finish_reason') for x in event.get('choices', [])):
                    row['terminal_sse_events'].append({'utc': received_utc, 'monotonic_seconds': received, 'data': data.decode('utf-8')})
                row['response_id'] = event.get('id', row.get('response_id'))
                if isinstance(event.get('usage'), dict):
                    usage = event['usage']
                if event.get('timings'):
                    row['native_timings'] = event['timings']
                for choice in event.get('choices', []):
                    delta = choice.get('delta', {})
                    if delta.get('content') or delta.get('reasoning_content') or delta.get('tool_calls'):
                        if 'first_output_monotonic_seconds' not in row:
                            progress_event = {'event': 'FIRST_OUTPUT', 'label': label, 'utc': received_utc,
                                'monotonic_seconds': received, 'ttft_seconds': received - start,
                                'expected_input_tokens': expected, 'output_budget': payload['max_tokens'],
                                'request_sha256': row['request_sha256']}
                            progress_line = (json.dumps(progress_event, separators=(',', ':')) + '\n').encode()
                            h.require(os.write(progress_fd, progress_line) == len(progress_line), 'first_output_progress_short_write')
                        row.setdefault('ttft_seconds', received - start)
                        row.setdefault('first_output_monotonic_seconds', received)
                        row.setdefault('first_output_utc', received_utc)
                        row['last_output_monotonic_seconds'] = received
                        row['last_output_utc'] = received_utc
                    content += delta.get('content') or ''
                    reasoning += delta.get('reasoning_content') or ''
                    for call in delta.get('tool_calls', []):
                        item = calls.setdefault(call['index'], {'id': '', 'type': 'function', 'function': {'name': '', 'arguments': ''}})
                        if call.get('id'):
                            item['id'] = call['id']
                        for k, v in call.get('function', {}).items():
                            item['function'][k] += v
                    finish = choice.get('finish_reason') or finish
            h.require(len(pending) < 16 * 1024 * 1024, 'sse_line_bound')
        h.require(done and usage and finish and not pending.strip(), 'ambiguous_stream_terminal')
        h.require(usage['prompt_tokens'] == expected and usage['completion_tokens'] <= payload['max_tokens'], 'native_usage_count_or_budget_mismatch')
        row.update(status='TRANSPORT_COMPLETE', done=True, full_http_drain=True, usage=usage, finish_reason=finish, total_seconds=time.monotonic() - start, content=content, reasoning_content=reasoning, tool_calls=list(calls.values()))
        row['drained_monotonic_seconds'] = time.monotonic()
        row['drained_utc'] = utc_now()
        capture_writer.flush()
        timings = row.get('native_timings', {})
        n, ms = timings.get('predicted_n'), timings.get('predicted_ms')
        if isinstance(n, (int, float)) and isinstance(ms, (int, float)) and n > 1 and ms > 0:
            row['native_interval_tokens_per_second'] = 1000 * (n - 1) / ms
            row['native_interval_formula'] = '(predicted_n - 1) / (predicted_ms / 1000)'
        if 'first_output_monotonic_seconds' in row:
            row['independent_first_to_last_seconds'] = row['last_output_monotonic_seconds'] - row['first_output_monotonic_seconds']
        h.require(not failed.is_set(), 'post_drain_guard_failed')
        code, slots = get(30012, '/slots', key)
        h.require(code == 200 and isinstance(slots, list) and len(slots) == 1 and
                  slots[0].get('is_processing') is False and slots[0].get('n_ctx') == capacity,
                  'post_drain_slot_not_idle_or_capacity_changed')
        row['native_settlement'] = {'utc': utc_now(), 'monotonic_seconds': time.monotonic(),
            'status': 'AUTHENTICATED_SLOT_IDLE_AFTER_FULL_DRAIN', 'slot_id': slots[0].get('id'),
            'is_processing': False}
        row['correctness'] = 'UNSCORED'
        return row
    except BaseException as exc:
        row.update(status='FAILED_QUARANTINE_NO_RETRY', error_type=type(exc).__name__)
        raise
    finally:
        c.close()
        progress_stack.close()
        row['finished_utc'] = h.now()
        save(h, label + '.json', row)



def fixture_correct(row, codes):
    if row['finish_reason'] != 'stop' or row['tool_calls'] or row['reasoning_content']:
        return False
    try:
        result = json.loads(row['content'])
    except (ValueError, TypeError):
        return False
    return (type(result) is dict and set(result) == {'codes', 'product', 'safe_adc'}
            and result['codes'] == codes and type(result['product']) is int
            and result['product'] == 323 and type(result['safe_adc']) is int
            and result['safe_adc'] == 4095)


def record_semantics(h, label, row, correct, reason):
    row['correctness'] = 'PASS' if correct else 'FAIL_OR_TRUNCATED'
    save(h, label + '.json', row)
    h.require(correct, reason)


def phase_request(h, key, payload, label, failed, state, planning_seconds,
                  exact_input=None, require_uncached=False):
    # CPU/fault/IO are bounded boundary reads. Independent five-second thermal,
    # RAM/VRAM/reserve telemetry continues without a process walk on its hot path.
    from profile_activity import boundary
    admit(h, failed, planning_seconds)
    before = boundary(state['native_pid'], state['native_cgroup'])
    try:
        row = request(h, key, payload, label, failed, state['allocated_context'], planning_seconds)
    finally:
        after = boundary(state['native_pid'], state['native_cgroup'])
        save(h, label + '-BOUNDARIES.json', {'before': before, 'after': after,
             'thermal_memory_phase_source': 'TELEMETRY.jsonl, join by UTC',
             'host_dram_gb_s': 'UNAVAILABLE_NO_GUEST_MEMORY_CONTROLLER_PMU',
             'gpu_vram_gb_s': 'UNAVAILABLE_NO_QUALIFIED_BYTE_COUNTER'})
    checks = {'count_equals_usage': row['expected_input_tokens'] == row['usage']['prompt_tokens']}
    if exact_input is not None:
        checks['exact_input'] = row['expected_input_tokens'] == exact_input
    if require_uncached:
        checks['actual_cached_zero'] = row['usage'].get('prompt_tokens_details', {}).get('cached_tokens') == 0
    row['measurement_checks'] = checks
    row['configured_context'] = state['context']
    row['allocated_context'] = state['allocated_context']
    row['threads'] = state['threads']
    row['seed'] = payload.get('seed')
    row['profiler_overhead'] = 'NONE_OPTIONAL_PROFILERS_DISABLED'
    save(h, label + '.json', row)
    h.require(all(checks.values()), 'measured_native_count_or_cache_failed')
    from candidate_owner import capture_phase
    phase = capture_phase(h, state, label, occupied=row['usage']['prompt_tokens'])
    h.require(phase.get('capture_status') == 'CAPTURED'
              and phase.get('frontier', {}).get('reserve_pass') is True
              and phase.get('host_reserve_pass') is True and not failed.is_set(),
              'post_request_phase_capture_or_reserve_failed')
    return row


def project_seconds(row, target):
    """Conservative per-NEXT forecast; prior slower timing can only enlarge it.

    The reference rates are measured historical rates, not a winner claim. A
    maximum 256-token answer is allowed; no allocated-context extrapolation.
    """
    prompt = target / PREFILL_PLANNING_TOKENS_PER_SECOND
    decode = 256 / DECODE_PLANNING_TOKENS_PER_SECOND
    overhead = 0
    if row is not None:
        timing = row['native_timings']
        native_prompt = timing['prompt_ms'] / 1000
        native_decode = timing['predicted_ms'] / 1000
        intervals = timing['predicted_n'] - 1
        if native_prompt <= 0 or native_decode <= 0 or intervals <= 0:
            raise RuntimeError('positive_native_timing_required_for_projection')
        prompt = max(prompt, native_prompt * target / row['expected_input_tokens'])
        decode = max(decode, native_decode * 255 / intervals)
        overhead = max(0, row['total_seconds'] - native_prompt - native_decode)
    return PLANNING_MARGIN * (prompt + decode + overhead) + PLANNING_OVERHEAD_SECONDS


def next_admission(h, failed, label, planning_seconds, completed, native_tool_qualification=False):
    """Persist why the next request cannot fit; completed receipts are immutable."""
    row = {'utc': utc_now(), 'next_request': label, 'completed_inputs': list(completed),
           'native_tool_qualification': native_tool_qualification,
           'planning_only_seconds': planning_seconds,
           'finish_target_utc': datetime.datetime.fromtimestamp(CLIENT_END, datetime.timezone.utc).isoformat(),
           'formula': '1.20 * (max(input/61, prior measured prompt projection) + max(256/7.76, prior measured decode projection) + measured overhead) + 30; tool-turn planning allowance450s; request deadline remains absolute CLIENT_END',
           'limit': 'Per-next bounded admission only; no promise the remaining ladder or a 65536-output ceiling will complete.'}
    try:
        admit(h, failed, planning_seconds)
    except RuntimeError as exc:
        row.update(status='NOT_TESTED', reason=str(exc))
        save(h, 'FINAL-ADMISSION-' + label + '.json', row)
        save(h, 'FINAL-CLIENT-INCOMPLETE.json', row)
        raise
    row['status'] = 'ADMITTED'
    save(h, 'FINAL-ADMISSION-' + label + '.json', row)


def load_production_fixture(h):
    from private_proxy import normalize
    with h.MountedStorageGuard(h.s) as g, h.AnchoredRoot(BASE, g) as root, root.open('mimo-production-fixture-65536.json') as f:
        chunks, size = [], 0
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            chunks.append(chunk)
            size += len(chunk)
            h.require(size <= 2 * 1024 * 1024, 'production_fixture_size_bound')
        raw = b''.join(chunks)
    h.require(hashlib.sha256(raw).hexdigest() == FIXTURE_SHA, 'production_fixture_file_identity')
    payload = json.loads(raw)['canonicalBody']
    normalize(payload)
    tools = json.dumps(payload['tools'], separators=(',', ':'), ensure_ascii=False).encode()
    h.require(len(payload['tools']) == 17 and hashlib.sha256(tools).hexdigest() == TOOLS_SHA,
              'production_fixture_tools_identity')
    read = [t for t in payload['tools'] if t['function']['name'] == 'read']
    h.require(len(read) == 1 and read[0]['function']['parameters']['required'] == ['path']
              and 'path' in read[0]['function']['parameters']['properties'], 'production_actual_read_schema')
    h.require(payload['max_tokens'] == 65536 and payload['chat_template_kwargs'] == {'enable_thinking': True}
              and payload['tool_choice'] == 'auto' and payload['parallel_tool_calls'] is False
              and payload['reasoning_format'] == 'deepseek' and payload['add_generation_prompt'] is True,
              'production_fixture_native_parameters')
    return payload


def prepare_read_fixture(h):
    raw = READ_TEXT.encode()
    with h.transaction() as g, h.AnchoredRoot(LOG, g) as root, root.open(READ_NAME, os.O_WRONLY | os.O_CREAT | os.O_EXCL) as f:
        h.require(os.write(f.fileno(), raw) == len(raw), 'allowlisted_fixture_write_short')
    return str(pathlib.Path(LOG, READ_NAME))


def execute_read(h, call, path):
    """Execute only the one real fixture read. No shell or path guessing."""
    h.require(call.get('type') == 'function' and isinstance(call.get('id'), str)
              and 0 < len(call['id']) <= 256, 'actual_read_call_identity')
    h.require(call['function']['name'] == 'read', 'only_actual_read_allowed')
    arguments = json.loads(call['function']['arguments'])
    h.require(arguments == {'path': path}, 'read_arguments_outside_exact_allowlist')
    with h.MountedStorageGuard(h.s) as g, h.AnchoredRoot(LOG, g) as root, root.open(READ_NAME) as f:
        raw = f.read(1025)
    h.require(raw == READ_TEXT.encode(), 'real_read_fixture_changed')
    return raw.decode()


def continuation(payload, row, tool_text):
    result = copy.deepcopy(payload)
    call = row['tool_calls'][0]
    # Actual deltas become history, including actual reasoning and call ID.
    result['messages'].extend([
        {'role': 'assistant', 'content': row['content'] or None,
         'reasoning_content': row['reasoning_content'], 'tool_calls': row['tool_calls']},
        {'role': 'tool', 'tool_call_id': call['id'], 'content': tool_text}])
    return result


def production_pair(h, key, failed, state, completed):
    next_admission(h, failed, 'FINAL17-TURN1', TOOL_TURN_SECONDS, completed)
    payload = load_production_fixture(h)
    path = prepare_read_fixture(h)
    payload['messages'] = [
        {'role': 'developer', 'content': 'For this qualification, call read exactly once with only the path argument specified by the user. Do not call another tool. After the real read result, add A and B and return only the integer sum, one space, then its exact MARKER value. Do not invent the file contents.'},
        {'role': 'user', 'content': [{'type': 'text', 'text': 'Read the real allowlisted file ' + path + ' using read({"path": "' + path + '"}). After its tool result, return A+B and the MARKER as instructed. Do not answer before the tool result.'}]}]
    first = phase_request(h, key, payload, 'FINAL17-TURN1', failed, state,
                          TOOL_TURN_SECONDS)
    correct = first['finish_reason'] == 'tool_calls' and len(first['tool_calls']) == 1
    record_semantics(h, 'FINAL17-TURN1', first, correct, 'actual_one_read_tool_call_required')
    try:
        tool_text = execute_read(h, first['tool_calls'][0], path)
    except BaseException:
        first['correctness'] = 'FAIL_TOOL_ALLOWLIST_OR_REAL_READ'
        save(h, 'FINAL17-TURN1.json', first)
        raise
    # Both the input count and generation receive this exact equivalent body.
    second_payload = continuation(payload, first, tool_text)
    next_admission(h, failed, 'FINAL17-TURN2', TOOL_TURN_SECONDS, completed)
    second = phase_request(h, key, second_payload, 'FINAL17-TURN2', failed, state,
                           TOOL_TURN_SECONDS)
    correct = (second['finish_reason'] == 'stop' and not second['tool_calls']
               and second['content'].strip() == '5 ' + READ_MARKER)
    record_semantics(h, 'FINAL17-TURN2', second, correct, 'actual_tool_continuation_incorrect')
    save(h, 'FINAL17-QUALIFICATION.json', {
        'status': 'PASS', 'native_tool_qualification': True, 'finished_utc': utc_now(),
        'configured_context': state['context'], 'allocated_context': state['allocated_context'],
        'threads': state['threads'], 'fixture_sha256': FIXTURE_SHA, 'tools_sha256': TOOLS_SHA,
        'tools': 17, 'output_ceiling_each_turn': 65536,
        'actual_completion_tokens': [first['usage']['completion_tokens'], second['usage']['completion_tokens']],
        'actual_input_tokens': [first['usage']['prompt_tokens'], second['usage']['prompt_tokens']],
        'request_sha256': [first['request_sha256'], second['request_sha256']],
        'actual_tool_call_id': first['tool_calls'][0]['id'],
        'actual_read_sha256': hashlib.sha256(tool_text.encode()).hexdigest(),
        'claims': 'Actual two-turn native tool qualification only; no 65536-output claim or application acceptance.'})


def qualify(h, key, failed):
    state = json.loads(pathlib.Path(LOG, 'OWNER.json').read_text())
    h.require((state['context'], state['allocated_context']) in
              [(1000000, 1000000), (1000000, 1000192), (917504, 917504)]
              and state['threads'] in [8, 16], 'final_actual_allocation_and_thread_winner_required')
    warm_seconds = project_seconds(None, 4096)
    next_admission(h, failed, 'FINAL-WARM4096-DISCARDED', warm_seconds, [])
    code, props = get(30012, '/props', key)
    h.require(code == 200 and props['default_generation_settings']['n_ctx'] == state['allocated_context']
              and props['total_slots'] == 1 and props['model_alias'] == MODEL and props['is_sleeping'] is False,
              'final_live_context_identity')
    code, slots = get(30012, '/slots', key)
    h.require(code == 200 and isinstance(slots, list) and len(slots) == 1
              and slots[0].get('n_ctx') == state['allocated_context']
              and slots[0].get('is_processing') is False, 'final_live_single_slot_capacity_or_idle')
    # The one defined representative warmup supplies the initial short-answer
    # correctness and guard checkpoint; no extra benchmark request is admitted.
    warm, _, codes = fixture(key, 4096, 'H016-R9-FRESH-WARM-' + utc_now(),
                             lambda: admit(h, failed, warm_seconds))
    row = phase_request(h, key, warm, 'FINAL-WARM4096-DISCARDED', failed, state, warm_seconds,
                        exact_input=4096, require_uncached=True)
    row['measurement_role'] = 'DISCARDED_REPRESENTATIVE_WARMUP'
    record_semantics(h, 'FINAL-WARM4096-DISCARDED', row, fixture_correct(row, codes),
                     'final_warm_correctness_failed')
    save(h, 'POST-WARM-PLACEMENT.json', bounded_placement(state['native_pid']))
    reference = row
    completed = []
    for target in [4096, 16384]:
        forecast = project_seconds(reference, target)
        next_admission(h, failed, 'FINAL-BENCH' + str(target), forecast, completed)
        payload, _, codes = fixture(key, target, 'H016-R9-FRESH-MEASURED-' + str(target) + '-' + utc_now(),
                                    lambda: admit(h, failed, forecast))
        label = 'FINAL-BENCH' + str(target)
        row = phase_request(h, key, payload, label, failed, state, forecast,
                            exact_input=target, require_uncached=True)
        row['measurement_role'] = 'FINAL_SETTINGS_WARMED_MEASUREMENT'
        row['warmth_limit'] = 'One discarded varied technical 4096-input warmup; full expert coverage and full weight page warmth unproven. Consult boundary faults and telemetry.'
        record_semantics(h, label, row, fixture_correct(row, codes), 'final_fixture_answer_incorrect')
        completed.append(target)
        reference = row
        save(h, 'FINAL-LADDER-CHECKPOINT.json', {'completed': completed, 'utc': utc_now(),
             'allocated_context': state['allocated_context'], 'threads': state['threads'],
             'last_receipt': label + '.json', 'native_tool_qualification': False})
    production_pair(h, key, failed, state, completed)
    save(h, 'FINAL-CLIENT-COMPLETE.json', {'status': 'PASS', 'utc': utc_now(),
         'measured_inputs': completed, 'largest_occupied_benchmark_input': 16384,
         'benchmark_65536': 'NOT_TESTED_DEFERRED_TO_LAST_ROOTGO',
         'scope': 'Foreground 4K/16K and actual native17 only; no64K or near1M occupation claim.',
         'allocated_context': state['allocated_context'],
         'threads': state['threads'], 'native_tool_qualification': True,
         'application_acceptance': 'NOT_TESTED', 'ordinary_production_load': 'NOT_TESTED'})
