"""Task-only H016 affinity14 short decode baseline; existing streaming capturer retained."""
import base64
import contextlib
import datetime
import hashlib
import http.client
import json
import os
import pathlib
import random
import time
from candidate_owner import ADMIT_END, CLIENT_END, HARD_END, BASE, LOG, get, save
from telemetry import bounded_placement
MODEL = 'mimo-v2.6-pro-rl'


def utc_now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='microseconds')


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


def request(h, key, payload, label, failed, sampler=None):
    h.require(time.time() < ADMIT_END and not failed.is_set(), 'benchmark_admission_closed')
    expected, raw = count(key, payload)
    if label == 'BASELINE128':
        h.require(expected == 83, 'unchanged_baseline_must_count_83_tokens')
    h.require(expected + payload['max_tokens'] <= 131071, 'context_admission')
    start = time.monotonic()
    deadline = min(time.time() + 7200, CLIENT_END)
    row = {'label': label, 'started_utc': h.now(), 'started_monotonic_seconds': start, 'raw_chunks': [], 'terminal_sse_events': [], 'expected_input_tokens': expected, 'request_sha256': hashlib.sha256(raw).hexdigest(), 'thinking': payload['chat_template_kwargs']['enable_thinking'], 'output_budget': payload['max_tokens'], 'status': 'SUBMITTED'}
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
        c.request('POST', '/v1/chat/completions', raw, {'Authorization': 'Bearer ' + key.decode(), 'Content-Type': 'application/json'})
        row['request_sent_monotonic_seconds'] = time.monotonic()
        row['request_sent_utc'] = utc_now()
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
                            if sampler is not None:
                                sampler.start(received_utc, received)
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
        timings = row.get('native_timings', {})
        n, ms = timings.get('predicted_n'), timings.get('predicted_ms')
        h.require(isinstance(n, (int, float)) and isinstance(ms, (int, float)) and n > 1 and ms > 0,
                  'native_decode_timing_missing')
        row['native_interval_tokens_per_second'] = 1000 * (n - 1) / ms
        row['native_interval_formula'] = '(predicted_n - 1) / (predicted_ms / 1000)'
        row['native_reported_tokens_per_second'] = timings.get('predicted_per_second')
        h.require(isinstance(timings.get('prompt_ms'), (int, float)) and timings['prompt_ms'] >= 0, 'native_prefill_timing_missing')
        row['prefill_seconds'] = timings['prompt_ms'] / 1000
        row['actual_cached_tokens'] = usage.get('prompt_tokens_details', {}).get('cached_tokens')
        h.require(row['actual_cached_tokens'] == 0, 'actual_cached_tokens_not_zero')
        if label == 'BASELINE128':
            h.require(usage['completion_tokens'] == 128 and n == 128 and timings.get('prompt_n') == 83, 'baseline_native_counts_not_83_in_128_out')
        if 'first_output_monotonic_seconds' in row:
            row['independent_first_to_last_seconds'] = row['last_output_monotonic_seconds'] - row['first_output_monotonic_seconds']
        h.require(not failed.is_set(), 'post_drain_guard_failed')
        code, slots = get(30012, '/slots', key)
        h.require(code == 200 and isinstance(slots, list) and len(slots) == 1 and
                  slots[0].get('is_processing') is False and slots[0].get('n_ctx') == 131072, 'post_drain_slot_not_idle_or_capacity_changed')
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
        if sampler is not None:
            save(h, label + '-DECODE-AFFINITY.json', sampler.finish(row.get('last_output_monotonic_seconds')))
        row['finished_utc'] = h.now()
        save(h, label + '.json', row)


def qualify(h, key, failed):
    # Exactly one tiny discarded warmup and the unchanged R10 unprofiled fixture.
    from profile_activity import boundary
    warm = body('In one sentence, state the purpose of a pull-up resistor on an open-drain digital signal.',
                thinking=False, output=8)
    warm['seed'] = 270927
    row = request(h, key, warm, 'WARM-TINY-DISCARDED', failed)
    row.update(measurement_role='DISCARDED_TINY_WARMUP', correctness='UNSCORED')
    save(h, 'WARM-TINY-DISCARDED.json', row)
    state = json.loads(pathlib.Path(LOG, 'OWNER.json').read_text())
    # Bounded diagnostic at a safe boundary, never in the five-second guard.
    # TID affinities are observations; source worker indices are not TID labels.
    placement = bounded_placement(state['native_pid'])
    placement['source_expectation'] = {'decode_worker_count': 4, 'guest_decode_cpus': [0, 24, 40, 56],
        'qualification': 'Review actual TID masks; do not infer active decode workers from all thread count.'}
    save(h, 'POST-WARM-PLACEMENT.json', placement)
    label = 'BASELINE128'
    payload = body('Scientific technical fixture A. Explain how a successive-approximation ADC samples a sensor signal. '
                   'Write at least 800 words covering sample-and-hold, binary search, quantization error, reference voltage, '
                   'source impedance, settling time, aliasing, and anti-alias filtering. Continue in detailed numbered paragraphs '
                   'without an introduction or early conclusion until the response limit.', thinking=False, output=128)
    payload['seed'] = 270927
    from decode_affinity import DecodeAffinity
    sampler = DecodeAffinity(state['native_pid'], expected_cpus=[0, 24, 40, 56], configured_batch_cpus=list(range(8)) + list(range(16,72)))
    before = boundary(state['native_pid'], state['native_cgroup'])
    try:
        row = request(h, key, payload, label, failed, sampler=sampler)
    finally:
        after = boundary(state['native_pid'], state['native_cgroup'])
        save(h, label + '-BOUNDARIES.json', {'before': before, 'after': after})
    row.update(measurement_role='UNPROFILED_BASELINE',
               profiler_overhead='NONE_OPTIONAL_PROFILERS_DISABLED',
               correctness='UNSCORED_NOT_A_QUALITY_TEST', seed=270927,
               output_ceiling_reached=row['usage']['completion_tokens'] == 128,
               sample_status='CEILING_SAMPLE' if row['usage']['completion_tokens'] == 128 else 'EARLY_STOP_SAMPLE_NO_RETRY',
               warmth_limit='Same tiny representative discarded warmup as R10 before one unprofiled baseline. No profiler or second request.',
               host_dram_gb_s={'status': 'UNAVAILABLE', 'reason': 'Guest exposes no AMD UMC/uncore memory-controller PMU.'},
               gpu_vram_gb_s={'status': 'UNAVAILABLE', 'reason': 'No qualified byte counter collector; activity percent and PCIe throughput are not VRAM bandwidth.'})
    save(h, label + '.json', row)
