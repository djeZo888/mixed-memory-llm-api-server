"""Serial native H016 acceptance, discarded representative warmup and first 4K."""
import hashlib
import http.client
import json
import pathlib
import random
import time
from candidate_owner import ADMIT_END, HARD_END, BASE, LOG, save
from telemetry import placement
MODEL = 'mimo-v2.6-pro-rl'


def body(text, thinking=False, output=256):
    return {'model': MODEL, 'messages': [{'role': 'user', 'content': text}], 'max_tokens': output, 'n': 1, 'stream': True, 'stream_options': {'include_usage': True}, 'tool_choice': 'auto', 'parallel_tool_calls': False, 'chat_template_kwargs': {'enable_thinking': thinking}, 'reasoning_format': 'deepseek', 'add_generation_prompt': True, 'temperature': 0}


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


def fixture(key, target, salt):
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
        text = ('Technical retrieval fixture ' + salt + '. Record the three labelled codes.\nEARLY_CODE=' + codes[0] + '\n' + ' '.join(words[:a]) + '\nMIDDLE_CODE=' + codes[1] + '\n' + ' '.join(words[a:a+b]) + '\nEND_CODE=' + codes[2] + '\nReturn only JSON with codes in early/middle/end order, product=17*19, and safe_adc=min(5000,4095).')
        return body(text)
    n = min(len(words), max(1, target // 2))
    prior = set()
    for _ in range(40):
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
                    got, raw = count(key, fixed)
                    if got == target:
                        return fixed, raw, codes
            n = max(1, n - max(1, abs(delta) // 2))
        else:
            prior.add(n)
            n = max(1, min(len(words), int(n * target / actual)))
    raise RuntimeError('exact_varied_fixture_count_not_converged')


def request(h, key, payload, label, failed):
    h.require(time.time() < ADMIT_END and not failed.is_set(), 'benchmark_admission_closed')
    expected, raw = count(key, payload)
    h.require(expected + payload['max_tokens'] <= 131071, 'context_admission')
    start = time.monotonic()
    deadline = min(time.time() + 7200, HARD_END)
    row = {'label': label, 'started_utc': h.now(), 'expected_input_tokens': expected, 'request_sha256': hashlib.sha256(raw).hexdigest(), 'thinking': payload['chat_template_kwargs']['enable_thinking'], 'output_budget': payload['max_tokens'], 'status': 'SUBMITTED'}
    save(h, label + '.json', row)
    c = http.client.HTTPConnection('127.0.0.1', 30012, timeout=max(.1, deadline - time.time()))
    response = None
    try:
        c.request('POST', '/v1/chat/completions', raw, {'Authorization': 'Bearer ' + key.decode(), 'Content-Type': 'application/json'})
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
            pending += chunk
            while b'\n' in pending:
                line, pending = pending.split(b'\n', 1)
                if not line.startswith(b'data: '):
                    continue
                data = line[6:].strip()
                if data == b'[DONE]':
                    done = True
                    continue
                event = json.loads(data)
                row['response_id'] = event.get('id', row.get('response_id'))
                if isinstance(event.get('usage'), dict):
                    usage = event['usage']
                if event.get('timings'):
                    row['native_timings'] = event['timings']
                for choice in event.get('choices', []):
                    delta = choice.get('delta', {})
                    if delta.get('content') or delta.get('reasoning_content') or delta.get('tool_calls'):
                        row.setdefault('ttft_seconds', time.monotonic() - start)
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
        row['correctness'] = 'UNSCORED'
        return row
    except BaseException as exc:
        row.update(status='FAILED_QUARANTINE_NO_RETRY', error_type=type(exc).__name__)
        raise
    finally:
        c.close()
        row['finished_utc'] = h.now()
        save(h, label + '.json', row)


def qualify(h, key, failed):
    # Private production roster: shape and canonical native count only, no 65536-token generation.
    from private_proxy import normalize
    raw_fixture = pathlib.Path(BASE, 'mimo-production-fixture-65536.json').read_bytes()
    h.require(hashlib.sha256(raw_fixture).hexdigest() == '2fb03cef2e700b304f8eea538a5ef8df300afc53bb0a94241bc754c17679ef78', 'production_fixture_file_identity')
    fixture_body = json.loads(raw_fixture)['canonicalBody']
    normalize(fixture_body)
    canonical = json.dumps(fixture_body, separators=(',', ':'), ensure_ascii=False).encode()
    tools = json.dumps(fixture_body['tools'], separators=(',', ':'), ensure_ascii=False).encode()
    h.require(hashlib.sha256(canonical).hexdigest() == 'c85d504741f038c1a0f150fdb59657a661ed38330958daab2b3f93f293e1e41b' and hashlib.sha256(tools).hexdigest() == '80e7a1e12e073ac57638e86638cf571158711ff821c96605135627777ce44e8c' and len(fixture_body['tools']) == 17, 'production_fixture_canonical_identity')
    tokens, _ = count(key, fixture_body)
    h.require(tokens + fixture_body['max_tokens'] <= 131071, 'production_fixture_count_capacity')
    save(h, 'PRODUCTION17-COUNT.json', {'status': 'SHAPE_AND_NATIVE_COUNT_ONLY', 'input_tokens': tokens, 'output_ceiling': 65536, 'tools': 17, 'generated_tokens': 0, 'body_sha256': hashlib.sha256(canonical).hexdigest(), 'native_tool_qualification': False})
    for thinking in [False, True]:
        row = request(h, key, body('Compute 17*19. Give only the integer.', thinking=thinking, output=2048 if thinking else 256), 'TEXT-' + str(thinking), failed)
        correct = row['finish_reason'] == 'stop' and row['content'].strip() == '323'
        row['correctness'] = 'PASS' if correct else 'FAIL_OR_TRUNCATED'
        save(h, 'TEXT-' + str(thinking) + '.json', row)
        h.require(correct, 'thinking_text_correctness_failed')
    tool = body('Call multiply with a=17,b=19, then report the tool result. Do not calculate without calling it.', output=2048)
    tool['tools'] = [{'type': 'function', 'function': {'name': 'multiply', 'description': 'Multiply two integers', 'strict': True, 'parameters': {'type': 'object', 'properties': {'a': {'type': 'integer'}, 'b': {'type': 'integer'}}, 'required': ['a', 'b'], 'additionalProperties': False}}}]
    row = request(h, key, tool, 'TOOL-CALL', failed)
    h.require(row['finish_reason'] == 'tool_calls' and len(row['tool_calls']) == 1, 'auto_tool_not_complete')
    call = row['tool_calls'][0]
    h.require(call['function']['name'] == 'multiply' and json.loads(call['function']['arguments']) == {'a': 17, 'b': 19}, 'tool_arguments_incorrect')
    tool['messages'] += [{'role': 'assistant', 'content': row['content'] or None, 'reasoning_content': row['reasoning_content'], 'tool_calls': row['tool_calls']}, {'role': 'tool', 'tool_call_id': call['id'], 'content': '323'}]
    row = request(h, key, tool, 'TOOL-CONTINUATION', failed)
    h.require(row['finish_reason'] == 'stop' and '323' in row['content'] and not row['tool_calls'], 'tool_continuation_incorrect')
    warm, _, _ = fixture(key, 4096, 'warm-' + h.now())
    request(h, key, warm, 'WARM4K-DISCARDED', failed)
    state = json.loads(pathlib.Path(LOG, 'OWNER.json').read_text())
    save(h, 'POST-WARM-PLACEMENT.json', placement(state['native_pid']))
    test, _, codes = fixture(key, 4096, 'measured-' + h.now())
    row = request(h, key, test, 'BENCH4096', failed)
    row['correctness'] = 'PASS' if row['finish_reason'] == 'stop' and all(code in row['content'] for code in codes + ['323', '4095']) else 'FAIL_OR_TRUNCATED'
    row['warmth_limit'] = 'One discarded varied technical4K; expert coverage and full537.997GiB residency/page warmth unproven. See faults/cache/NUMA telemetry.'
    row['later_duration_planning_only_seconds'] = {str(n): row['total_seconds'] * n / 4096 for n in [16384, 65536]}
    row['projection_limit'] = 'Linear planning estimate from one4K; not measured throughput or quality, may be optimistic with context-dependent attention.'
    save(h, 'BENCH4096.json', row)  # Immediate checkpoint before root decides later admission.
    h.require(row['correctness'] == 'PASS', 'first4k_correctness_failed')
