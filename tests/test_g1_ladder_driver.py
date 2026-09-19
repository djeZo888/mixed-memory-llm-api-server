"""Focused ladder checks with synthetic counters and no host or VM access."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from benchmark import accounting, fixtures, g1_ladder as ladder, glmrepair, runner


class LadderFixtureTests(unittest.TestCase):
    def counter(self, capacity, calls, output_cap=256):
        def count(raw):
            calls.append(raw)
            body = json.loads(raw)
            self.assertEqual(body['max_tokens'], output_cap)
            self.assertEqual(body['temperature'], 1.0)
            self.assertEqual(body['seed'], 1729)
            self.assertEqual(body['reasoning_effort'], 'low')
            self.assertIs(body['stream'], True)
            schema = body['response_format']['json_schema']
            self.assertEqual(schema, {
                'name': 'retrieval', 'strict': True,
                'schema': {'type': 'object', 'required': ['START', 'MIDDLE', 'END'],
                           'additionalProperties': False,
                           'properties': {key: {'type': 'string'}
                                          for key in ('START', 'MIDDLE', 'END')}}})
            # Deliberately depends on the final body: untransformed probes fail
            # the schema/cap assertions above before their count can be used.
            tokens = body['messages'][0]['content'].count('record=') * 40 + 120
            return {'source': 'synthetic_offline', 'input_tokens': tokens,
                    'configured_context': capacity, 'body_sha256': fixtures.digest(raw),
                    'template_sha256': 'a' * 64, 'token_ids_sha256': 'b' * 64}
        return count

    def test_final_body_has_only_authorized_changes_and_no_answer_schema(self):
        sample = fixtures.build_sample(glmrepair.MODEL, 40, 'ladder-seed01', 'ladder-nonce01')
        original = copy.deepcopy(sample)
        for cap in (32, 256):
            with self.subTest(output_cap=cap):
                body = json.loads(ladder.body_bytes(sample, output_cap=cap))
                expected = copy.deepcopy(sample['body'])
                expected.update(temperature=1.0, seed=1729, max_tokens=cap)
                expected['response_format'] = body['response_format']
                self.assertEqual(body, expected)
                self.counter(16384, [], cap)(fixtures.canonical(body))
                for value in sample['scorer']['retrieval'].values():
                    self.assertNotIn(value, json.dumps(body['response_format']))
                    self.assertEqual(fixtures.canonical(body).count(value.encode()), 1)
        self.assertEqual(sample, original)
        contaminated = copy.deepcopy(sample)
        contaminated['body']['messages'][0]['content'] += sample['scorer']['retrieval']['START']
        with self.assertRaises(fixtures.HarnessError):
            ladder.body_bytes(contaminated)

    def test_bounded_counted_fit_final_bytes_and_full_batch_warmup(self):
        for capacity in (16384, 65536):
            for warmup in (False, True):
                with self.subTest(capacity=capacity, warmup=warmup):
                    calls = []
                    counter = self.counter(capacity, calls, 32 if warmup else 256)
                    nonce = 'warmup-ladder001' if warmup else 'primary-ladder001'
                    sample, raw, counted = ladder.fit(capacity, nonce, counter,
                                                     warmup=warmup, synthetic=True)
                    self.assertLessEqual(len(calls), 32)
                    self.assertEqual(json.loads(calls[0])['messages'][0]['content'].count('record='), 12)
                    self.assertIn(raw, calls)
                    self.assertEqual(raw, ladder.body_bytes(sample, output_cap=32 if warmup else 256))
                    self.assertEqual(counted['body_sha256'], fixtures.digest(raw))
                    fixtures.validate_count(counted, raw, capacity, synthetic=True)
                    lower, upper = (2304, 2432) if warmup else (capacity - 640, capacity - 512)
                    self.assertTrue(lower <= counted['input_tokens'] <= upper)
                    self.assertLessEqual(counted['input_tokens'] + (32 if warmup else 256) + 256,
                                         capacity)

    def test_invalid_capacity_and_stale_count_fail_before_inference(self):
        for capacity in (4096, 131072, 262144, 1048576):
            counter = Mock()
            with self.subTest(capacity=capacity), self.assertRaises((ValueError, RuntimeError)):
                ladder.fit(capacity, 'primary-ladder001', counter)
            counter.assert_not_called()
        calls = []
        valid = self.counter(16384, calls)
        def stale(raw):
            return {**valid(raw), 'body_sha256': 'c' * 64}
        with self.assertRaises(fixtures.HarnessError):
            ladder.fit(16384, 'primary-ladder001', stale, synthetic=True)
        self.assertEqual(len(calls), 1)

    def test_native_count_preserves_schema_sampling_and_binds_normalized_transport(self):
        sample = fixtures.build_sample(glmrepair.MODEL, 40, 'ladder-seed01', 'ladder-nonce01')
        raw = ladder.body_bytes(sample)
        original = json.loads(raw)
        normalized = {k: v for k, v in original.items() if k not in ('stream', 'stream_options')}
        calls = []
        def call(route, payload):
            calls.append((route, copy.deepcopy(payload)))
            return {'/props': {'model_alias': glmrepair.MODEL, 'is_sleeping': False,
                              'total_slots': 1, 'default_generation_settings': {'n_ctx': 16384},
                              'chat_template': 'offline native template'},
                    '/apply-template': {'prompt': 'offline exact rendered template'},
                    '/tokenize': {'tokens': [9, 8, 7]}}[route]
        counted = accounting.native_counter(glmrepair.MODEL, 16384, call)(raw)
        self.assertEqual(calls[1], ('/apply-template', normalized))
        self.assertEqual(calls[2], ('/tokenize', {'content': 'offline exact rendered template',
                                               'add_special': True, 'parse_special': True,
                                               'with_pieces': False}))
        self.assertEqual(json.loads(raw), original)
        self.assertEqual(counted['body_sha256'], fixtures.digest(raw))
        self.assertEqual(counted['count_body_sha256'], fixtures.digest(fixtures.canonical(normalized)))
        self.assertNotEqual(counted['body_sha256'], counted['count_body_sha256'])
        self.assertEqual(counted['count_transport_normalization'],
                         {'removed_fields': ['stream', 'stream_options']})
        fixtures.validate_count(counted, raw, 16384)

    def test_matched_repeat_one_recount_keeps_logical_fixture_and_expected_values(self):
        first, raw, _ = ladder.fit(16384, 'primary-ladder001', self.counter(16384, []), synthetic=True)
        original = copy.deepcopy(first)
        calls = []
        second, repeated_raw, counted = ladder.fit(16384, 'repeat--ladder001',
            self.counter(16384, calls), matched=first, synthetic=True)
        self.assertEqual(calls, [repeated_raw])
        self.assertEqual(first, original)
        for field in ('records', 'seed', 'kind', 'fixture_sha256', 'scorer'):
            self.assertEqual(first[field], second[field])
        self.assertNotEqual(first['nonce'], second['nonce'])
        self.assertEqual(repeated_raw, raw.replace(first['nonce'].encode(), second['nonce'].encode(), 1))
        self.assertNotEqual(fixtures.digest(raw), counted['body_sha256'])
        self.assertEqual(fixtures.digest(repeated_raw), counted['body_sha256'])

    def test_matched_repeat_refuses_stale_prefix_and_bad_recount_without_refit(self):
        first, _, _ = ladder.fit(16384, 'primary-ladder001', self.counter(16384, []), synthetic=True)
        original = copy.deepcopy(first)
        unused = Mock()
        with self.assertRaises((ValueError, RuntimeError)):
            ladder.fit(16384, first['nonce'], unused, matched=first, synthetic=True)
        unused.assert_not_called()
        for tokens in (1, 16384):
            calls = []
            valid = self.counter(16384, calls)
            def outside(raw):
                return {**valid(raw), 'input_tokens': tokens}
            with self.subTest(tokens=tokens), self.assertRaises((ValueError, RuntimeError)):
                ladder.fit(16384, 'repeat--ladder001', outside, matched=first, synthetic=True)
            self.assertEqual(len(calls), 1)
            self.assertEqual(first, original)

    def test_strict_scoring_keeps_fences_duplicates_and_wrong_values_failed(self):
        sample = fixtures.build_sample(glmrepair.MODEL, 40, 'ladder-seed01', 'ladder-nonce01')
        good = fixtures.canonical(sample['scorer']['retrieval']).decode()
        cases = [(good, 'PASS'), ('```json\n' + good + '\n```', 'HARNESS_FAILURE'),
                 (good + good, 'HARNESS_FAILURE'), (good + '</think>' + good, 'HARNESS_FAILURE'),
                 (json.dumps({**sample['scorer']['retrieval'], 'END': 'wrong'}), 'MODEL_INCORRECT'),
                 (json.dumps({**sample['scorer']['retrieval'], 'extra': 'value'}), 'MODEL_INCORRECT')]
        for content, expected in cases:
            response = {'parsed': {'message': {'role': 'assistant', 'content': content},
                                   'finish_reason': 'stop'}}
            with self.subTest(content=content):
                outcome = glmrepair.format_outcome(response, sample)
                self.assertEqual(outcome['status'], expected)
                self.assertFalse(outcome['output_modified'])
                self.assertEqual(outcome['content_sha256'], fixtures.digest(content.encode()))


class LadderSequenceTests(unittest.TestCase):
    def create(self, directory, failure=None):
        task = Path(directory)
        runner.save(task / 'progress.json', {'phase': 'CODE_READY', 'completed': {},
                                            'inflight': {}, 'errors': []})
        host = Mock()
        host.call.return_value = {'phase': 'ACTIVE'}
        manifests = [{'placement': 'G1', 'configured_capacity': n} for n in (16384, 65536)]
        armed = {'scope': 'g1-ladder', 'campaign': 'offline-ladder', 'session_id': 'offline',
                 'source_commit': 'offline', 'manifests': manifests}
        job = ladder.Ladder(task, armed, host, 'synthetic-offline-key')
        events = []
        job.collect = Mock()
        job.monitor = Mock()
        job.restore = Mock(side_effect=lambda: events.append('restore'))
        job.telemetry_window = Mock(return_value={'status': 'SAMPLED', 'scope': 'offline'})
        real_boundary = job.boundary
        def boundary(cid, point):
            if failure == 'memory_before_repeat' and point == 'BEFORE_G1-16384-repeat':
                job.safety[cid] = 'STOP_OOM'
            return real_boundary(cid, point)
        job.boundary = boundary

        def counter(cid):
            capacity = job.active[cid]['manifest']['configured_capacity']
            def count(raw):
                tokens = json.loads(raw)['messages'][0]['content'].count('record=') * 40 + 120
                # An offline injected native-response seam; no tokenizer or VM.
                return {'source': 'native_apply_template_tokenize', 'input_tokens': tokens,
                        'body_sha256': fixtures.digest(raw), 'configured_context': capacity,
                        'template_sha256': 'a' * 64, 'token_ids_sha256': 'b' * 64}
            return count
        job.counter = counter

        def request(cid, raw, identifier, *, timed=True):
            events.append(identifier)
            sample = json.loads((job.private / (identifier + '-fixture.json')).read_bytes())
            counted = json.loads((job.private / (identifier + '-count.json')).read_bytes())
            cap = 256 if timed else 32
            self.assertEqual(raw, ladder.body_bytes(sample, output_cap=cap))
            self.assertEqual(counted['body_sha256'], fixtures.digest(raw))
            content = fixtures.canonical(sample['scorer']['retrieval']).decode()
            cached, evaluated = 0, counted['input_tokens']
            if identifier.endswith('-repeat'):
                if failure == 'cached_repeat':
                    cached = 1
                elif failure == 'native_mismatch_repeat':
                    evaluated -= 1
                elif failure == 'fenced_repeat':
                    content = '```json\n' + content + '\n```'
                elif failure == 'duplicate_repeat':
                    content += content
                elif failure == 'wrong_repeat':
                    content = json.dumps({**sample['scorer']['retrieval'], 'MIDDLE': 'wrong'})
            if failure == 'cached_warmup' and not timed:
                cached = 1
            counters = {'prompt_tokens': counted['input_tokens'], 'cached_tokens': cached,
                        'evaluated_prompt_tokens': evaluated, 'completion_tokens': 17,
                        'decode_tokens': 17, 'prompt_ms': 500, 'decode_ms': 100}
            return {'summary': {'status': 'COMPLETE', 'counters': counters,
                                'response_retained_complete': True},
                    'parsed': {'finish_reason': 'stop', 'counters': counters,
                               'message': {'role': 'assistant', 'content': content}}}
        job.request = request

        def loaded(manifest):
            capacity = manifest['configured_capacity']
            events.append('load-' + str(capacity))
            cid = 'cid-' + str(capacity)
            job.active[cid] = {'manifest': manifest}
            job.warm(cid, manifest, {})
            return cid
        job.loaded = loaded
        def retire():
            events.append('retire')
            job.active.clear()
        job.retire_all = retire
        return job, events

    def test_exact_two_loads_three_measurements_and_matched_anchor(self):
        with tempfile.TemporaryDirectory() as directory:
            job, events = self.create(directory)
            with patch.object(ladder, 'checkpoint'):
                job.execute()
            self.assertEqual(events, ['load-16384', 'G1-16384-warmup', 'G1-16384-primary',
                'G1-16384-repeat', 'retire', 'load-65536', 'G1-65536-warmup',
                'G1-65536-primary', 'retire', 'restore'])
            self.assertEqual(list(job.progress['completed']),
                             ['G1-16384-primary', 'G1-16384-repeat', 'G1-65536-primary'])
            primary, repeat, large = job.progress['completed'].values()
            self.assertEqual(primary['fixture_sha256'], repeat['fixture_sha256'])
            self.assertEqual(primary['records'], repeat['records'])
            self.assertNotEqual(primary['count']['body_sha256'], repeat['count']['body_sha256'])
            self.assertEqual(repeat['count']['fit_calls'], 1)
            for row in (primary, repeat, large):
                self.assertEqual(row['status'], 'PASS')
                self.assertEqual(row['native_n_minus_1_decode_tokens_per_second'], 160)
                self.assertEqual(row['occupied_window_tokens'], row['count']['input_tokens'] + 17)
                self.assertFalse(row['output_modified'])
            self.assertEqual(job.progress['inflight'], {})
            job.restore.assert_called_once()

    def test_correctness_uncached_and_memory_failures_stop_without_retry_and_restore(self):
        failures = ('cached_repeat', 'native_mismatch_repeat', 'fenced_repeat',
                    'duplicate_repeat', 'wrong_repeat', 'memory_before_repeat', 'cached_warmup')
        for failure in failures:
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as directory:
                job, events = self.create(directory, failure)
                with patch.object(ladder, 'checkpoint'), self.assertRaisesRegex(RuntimeError, 'STOP_'):
                    job.execute()
                self.assertEqual(events.count('load-16384'), 1)
                self.assertNotIn('load-65536', events)
                self.assertLessEqual(events.count('G1-16384-repeat'), 1)
                self.assertEqual(events[-1], 'restore')
                job.restore.assert_called_once()
                if failure in ('memory_before_repeat', 'cached_warmup'):
                    self.assertNotIn('G1-16384-repeat', events)
                else:
                    row = json.loads(Path(directory, 'G1-16384-repeat-result.json').read_bytes())
                    self.assertEqual(row['status'], 'STOP_REQUEST_GATE')
                    self.assertFalse(row['output_modified'])
                    if failure in ('fenced_repeat', 'duplicate_repeat'):
                        self.assertEqual(row['score']['status'], 'HARNESS_FAILURE')
                    elif failure == 'wrong_repeat':
                        self.assertEqual(row['score']['status'], 'MODEL_INCORRECT')

    def test_warmup32_schema_uses_shared_capture_retains_raw_and_always_ends_owner(self):
        for interrupted in (False, True):
            with self.subTest(interrupted=interrupted), tempfile.TemporaryDirectory() as directory:
                job, _ = self.create(directory)
                job.active['cid'] = {'cancel_event': threading.Event()}
                job.admission = Mock(return_value=1)
                sample = fixtures.build_sample(glmrepair.MODEL, 40, 'ladder-seed01', 'ladder-nonce01')
                raw = ladder.body_bytes(sample, output_cap=32)
                response = fixtures.canonical({'model': glmrepair.MODEL,
                    'choices': [{'index': 0, 'delta': {'role': 'assistant', 'content': '{}'},
                                 'finish_reason': 'length'}],
                    'usage': {'prompt_tokens': 2391, 'completion_tokens': 32},
                    'timings': {'prompt_n': 2391, 'cache_n': 0, 'predicted_n': 32,
                                'prompt_ms': 30, 'predicted_ms': 62}})
                wire = b'data: ' + response + b'\n\n' + b'data: [DONE]\n\n'
                def transport(sent, timeout):
                    self.assertEqual(sent, raw)
                    self.assertEqual(timeout, 1)
                    yield wire
                    if interrupted:
                        raise KeyboardInterrupt()
                job.transport_factory = Mock(return_value=transport)
                if interrupted:
                    with self.assertRaises(KeyboardInterrupt):
                        ladder.Ladder.request(job, 'cid', raw, 'capture-warmup', timed=False)
                else:
                    result = ladder.Ladder.request(job, 'cid', raw, 'capture-warmup', timed=False)
                    self.assertEqual(result['summary']['status'], 'OUTPUT_LIMIT')
                    self.assertTrue(result['summary']['response_retained_complete'])
                self.assertEqual((job.private / 'capture-warmup.request.json').read_bytes(), raw)
                self.assertEqual((job.private / 'capture-warmup.response.sse').read_bytes(), wire)
                self.assertEqual(job.host.call.call_args.args, ('request_end',))


if __name__ == '__main__':
    unittest.main()
