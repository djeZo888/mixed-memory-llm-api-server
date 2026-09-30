"""Execute the transformed pinned normal loop; CUDA/ZMQ dependency fixtures.

Set H005_PINNED_TEXT_ROOT to the extracted source root to run exact native
method fixtures. Socket tests use real socketpair/select behind a ZMQ-shaped
fixture; they are not acceptance of the native binary or GPU scheduler.
"""
import ast
from collections import deque
from concurrent.futures import Future
import hashlib
import importlib
import os
from pathlib import Path
import select
import socket
import subprocess
import sys
import tempfile
import threading
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from runtime.adaptive_idle import AdaptiveIdle


class Poller:
    def __init__(self):
        self.sockets = []
        self.wait = lambda: None

    def register(self, sock, events):
        self.sockets.append(sock)

    def poll(self):
        return self.wait()


with patch.dict(sys.modules, {'zmq': NS(Poller=Poller, POLLIN=1)}):
    TextAdaptiveIdle = importlib.import_module('runtime.adaptive_text').TextAdaptiveIdle


class Clock:
    value = 0.0

    def __call__(self):
        return self.value


class EndLoop(Exception):
    pass


class Generate:
    health = False


class Drain:
    def __init__(self, event, token, admitted=False):
        self.event, self.token, self.admitted = event, token, admitted


class BatchGenerate:
    def __init__(self, items):
        self.items = items

    def __iter__(self):
        return iter(self.items)


class Batch:
    def __init__(self, reqs=()):
        self.reqs = list(reqs)
        self.done = not self.reqs

    def is_empty(self):
        return self.done


def state():
    return NS(server_args=NS(tp_size=1, pp_size=1, dp_size=1,
                            disable_overlap_schedule=True, disaggregation_mode='null'),
              enable_overlap=False, enable_pdmux=False, enable_hisparse=False,
              enable_hierarchical_cache=False, enable_unified_memory=False,
              rust_server=None, input_blocker=None, recv_skipper=None,
              mm_receiver=None, external_corpus_manager=None, lora_drainer=None,
              dllm_config=None, ipc_channels=NS(recv_from_tokenizer=object(), recv_from_rpc=object()),
              flush_wrapper=NS(_pending=None), _engine_paused=False, gracefully_exit=False,
              is_fully_idle=lambda: True, running_batch=Batch(), last_batch=None,
              waiting_queue=[], chunked_req=None, grammar_manager=NS(grammar_queue=[], _adaptive_pending_futures=set()))


class BindingTests(unittest.TestCase):
    def setUp(self):
        self.clock, self.scheduler = Clock(), state()
        self.idle = TextAdaptiveIdle(self.scheduler, lambda req: getattr(req, "health", False), Drain, clock=self.clock)
        self.waits = []
        self.idle.poller.wait = lambda: self.waits.append(self.clock.value)

    def test_startup_boundary_and_passive_wake(self):
        self.clock.value = 599.999
        self.assertFalse(self.idle.maybe_wait())
        self.clock.value = 600
        self.assertTrue(self.idle.maybe_wait())
        self.clock.value = 999
        self.assertTrue(self.idle.maybe_wait())
        self.assertEqual(self.idle.policy.snapshot()['last_real_work_monotonic'], 0)

    def test_queued_async_completion_receives_full_grace(self):
        self.scheduler.is_fully_idle = lambda: False
        self.scheduler.grammar_manager.grammar_queue = [object()]
        self.clock.value = 1800
        self.assertFalse(self.idle.maybe_wait())
        self.scheduler.is_fully_idle = lambda: True
        self.scheduler.grammar_manager.grammar_queue = []
        self.clock.value = 1900
        self.assertFalse(self.idle.maybe_wait())
        self.clock.value = 2499.999
        self.assertFalse(self.idle.maybe_wait())
        self.clock.value = 2500
        self.assertTrue(self.idle.maybe_wait())

    def test_paused_empty_engine_waits_but_paused_work_does_not(self):
        self.clock.value = 600
        self.scheduler._engine_paused = True
        self.assertTrue(self.idle.maybe_wait())
        self.scheduler.waiting_queue.append(Generate())
        self.scheduler.is_fully_idle = lambda: False
        self.assertFalse(self.idle.maybe_wait())

    def test_unknown_and_control_pending_suppress_without_renewal(self):
        self.clock.value = 1000
        self.scheduler.is_fully_idle = lambda: None
        self.assertFalse(self.idle.maybe_wait())
        self.scheduler.is_fully_idle = lambda: True
        self.scheduler.flush_wrapper._pending = object()
        self.assertFalse(self.idle.maybe_wait())
        self.scheduler.flush_wrapper._pending = None
        self.assertTrue(self.idle.maybe_wait())
        self.assertEqual(self.idle.policy.snapshot()['last_real_work_monotonic'], 0)

    def test_unsupported_producer_or_topology_fails_closed(self):
        for field in ('rust_server', 'input_blocker', 'recv_skipper', 'mm_receiver',
                      'external_corpus_manager', 'lora_drainer', 'dllm_config'):
            candidate = state()
            setattr(candidate, field, object())
            with self.subTest(field=field), self.assertRaises(RuntimeError):
                TextAdaptiveIdle(candidate, lambda req: False, Drain)
        for field in ('tp_size', 'pp_size', 'dp_size'):
            candidate = state()
            setattr(candidate.server_args, field, 2)
            with self.subTest(field=field), self.assertRaises(RuntimeError):
                TextAdaptiveIdle(candidate, lambda req: False, Drain)
        del self.scheduler.enable_overlap
        with self.assertRaises(RuntimeError):
            TextAdaptiveIdle(self.scheduler, lambda req: False, Drain)

    def test_aborted_running_grammar_future_survives_empty_queue(self):
        future = Future()
        self.assertTrue(future.set_running_or_notify_cancel())
        self.assertFalse(future.cancel())
        self.scheduler.grammar_manager._adaptive_pending_futures.add(future)
        self.clock.value = 1700
        self.assertFalse(self.idle.maybe_wait())
        self.assertFalse(self.scheduler.grammar_manager.grammar_queue)
        future.set_result(object())
        self.clock.value = 1800
        self.assertFalse(self.idle.maybe_wait())
        self.clock.value = 2399.999
        self.assertFalse(self.idle.maybe_wait())
        self.clock.value = 2400
        self.assertTrue(self.idle.maybe_wait())

    def test_rejected_preadmission_reservation_cannot_renew_grace(self):
        token = 'b' * 32
        self.clock.value = 900
        self.idle.consume_notifications([Drain('begin', token)])
        self.assertFalse(self.idle.maybe_wait())
        self.clock.value = 2100
        self.idle.consume_notifications([Drain('end', token, admitted=False)])
        self.assertTrue(self.idle.maybe_wait())
        self.assertEqual(self.idle.policy.snapshot()['last_real_work_monotonic'], 0)

    def test_pending_response_drain_beyond_600_then_full_grace(self):
        token = 'a' * 32
        marker = object()
        self.assertEqual(self.idle.consume_notifications([Drain('begin', token), marker]), [marker])
        self.clock.value = 3000
        self.assertFalse(self.idle.maybe_wait())
        self.assertEqual(self.idle.policy.snapshot()['last_real_work_monotonic'], 0)
        self.idle.consume_notifications([Drain('end', token, admitted=True)])
        self.clock.value = 3599.999
        self.assertFalse(self.idle.maybe_wait())
        self.clock.value = 3600
        self.assertTrue(self.idle.maybe_wait())

    def test_health_only_native_buffers_never_renew(self):
        health = Generate()
        health.health = True
        self.scheduler.running_batch = Batch([health])
        self.scheduler.is_fully_idle = lambda: False
        self.clock.value = 5000
        self.assertFalse(self.idle.maybe_wait())
        self.scheduler.running_batch = Batch()
        self.scheduler.is_fully_idle = lambda: True
        self.assertTrue(self.idle.maybe_wait())
        self.assertEqual(self.idle.policy.snapshot()['last_real_work_monotonic'], 0)

    def test_both_channels_no_lost_wake_at_check_wait_boundary(self):
        pairs = [socket.socketpair(), socket.socketpair()]
        try:
            self.scheduler.ipc_channels = NS(recv_from_tokenizer=pairs[0][0], recv_from_rpc=pairs[1][0])
            idle = TextAdaptiveIdle(self.scheduler, lambda req: getattr(req, "health", False), Drain, clock=self.clock)
            self.clock.value = 600
            for receiver, sender in pairs:
                def arrival_between_check_and_poll():
                    sender.send(b'x')
                    ready, _, _ = select.select(idle.poller.sockets, [], [], 1)
                    self.assertIn(receiver, ready)
                    self.assertEqual(receiver.recv(1), b'x')
                idle.poller.wait = arrival_between_check_and_poll
                self.assertTrue(idle.maybe_wait())
                self.assertEqual(idle.policy.snapshot()['last_real_work_monotonic'], 0)
        finally:
            for pair in pairs:
                for sock in pair:
                    sock.close()

    def test_blocked_channel_wakes_immediately_then_real_work_renews(self):
        receiver, sender = socket.socketpair()
        entered, done = threading.Event(), threading.Event()
        try:
            self.clock.value = 600
            def wait():
                entered.set()
                ready, _, _ = select.select([receiver], [], [], 2)
                if ready:
                    receiver.recv(1)
            self.idle.poller.wait = wait
            def worker():
                self.idle.maybe_wait()
                self.idle.record_real_work()
                done.set()
            thread = threading.Thread(target=worker, daemon=True)
            thread.start()
            self.assertTrue(entered.wait(1))
            self.assertFalse(done.is_set())
            self.clock.value = 611
            sender.send(b'x')
            self.assertTrue(done.wait(1))
            thread.join(1)
            self.clock.value = 1210.999
            self.assertFalse(self.idle.maybe_wait())
            self.assertEqual(self.idle.policy.snapshot()['last_real_work_monotonic'], 611)
        finally:
            receiver.close()
            sender.close()


class NativeLoopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source_root = os.environ.get('H005_PINNED_TEXT_ROOT')
        if not source_root:
            raise unittest.SkipTest('exact-source fixtures require H005_PINNED_TEXT_ROOT')
        original = Path(source_root) / 'python/sglang/srt/managers/scheduler.py'
        raw = original.read_bytes()
        if hashlib.sha256(raw).hexdigest() != '3a12fdfb9c21571d8007ba60aedd7e84b67636583bac8243373c75d6a2ab324e':
            raise AssertionError('pinned text source drift')
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'python/sglang/srt/managers/scheduler.py'
            target.parent.mkdir(parents=True)
            target.write_bytes(raw)
            subprocess.run(['git', 'apply', str(ROOT / 'scripts/runtime/patches/text-adaptive-idle.patch')],
                           cwd=directory, check=True, capture_output=True)
            cls.source = target.read_text()
        tree = ast.parse(cls.source)
        native = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'Scheduler')
        names = {'event_loop_normal', 'is_fully_idle', '_pp_microbatches_drained', '_tokenized_requests'}
        methods = [n for n in native.body if isinstance(n, ast.FunctionDef) and n.name in names]
        for node in methods:
            if node.name == 'event_loop_normal':
                node.decorator_list = []
        native.body = methods
        native.bases = []
        namespace = {'DisaggregationMode': NS(DECODE='decode', PREFILL='prefill'),
                     'TokenizedGenerateReqInput': Generate, 'TokenizedEmbeddingReqInput': Generate,
                     'BatchTokenizedGenerateReqInput': BatchGenerate,
                     'BatchTokenizedEmbeddingReqInput': BatchGenerate,
                     'is_health_check_generate_req': lambda req: req.health,
                     'envs': NS(SGLANG_ENABLE_STRICT_MEM_CHECK_DURING_BUSY=NS(get=lambda: False))}
        module = ast.Module(body=[ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')], level=0), native], type_ignores=[])
        exec(compile(ast.fix_missing_locations(module), 'exact_patched_scheduler.py', 'exec'), namespace)
        cls.scheduler_type = namespace['Scheduler']

    def setUp(self):
        self.clock = Clock()
        self.scheduler = self.scheduler_type()
        self.scheduler.__dict__.update(vars(state()))
        del self.scheduler.is_fully_idle
        self.scheduler.running_batch = Batch()
        self.scheduler.last_batch = None
        self.scheduler.chunked_req = None
        self.scheduler.dllm_manager = NS(any_staging_reqs=lambda: False)
        self.scheduler.ps = NS(pp_size=1)
        self.scheduler.waiting_queue = []
        self.scheduler.grammar_manager = NS(grammar_queue=[], _adaptive_pending_futures=set())
        self.scheduler.disaggregation_mode = 'null'
        self.scheduler.adaptive_idle = TextAdaptiveIdle(self.scheduler, lambda req: getattr(req, "health", False), Drain, clock=self.clock)
        self.scheduler.process_input_requests = lambda reqs: None
        self.scheduler.on_idle = lambda: None

    def test_native_long_request_and_final_stream_completion_get_600_seconds(self):
        s = self.scheduler
        req, batch = Generate(), Batch([Generate()])
        receive_count, waits, timeline = [0], [], []
        def recv():
            receive_count[0] += 1
            if receive_count[0] == 1:
                return [req]
            self.clock.value = 1999.999 if receive_count[0] == 2 else 2000
            return []
        def plan(**kwargs):
            current = batch if receive_count[0] == 1 else None
            return NS(running_batch=Batch(), batch_to_run=current)
        def run(current):
            self.clock.value = 1300
            timeline.append('forward-complete')
            return object()
        def process(current, result):
            # Model output/stream handoff itself remains pending another100s.
            self.clock.value = 1400
            timeline.append('final-stream-handoff')
            current.done = True
        def wait():
            waits.append(self.clock.value)
            raise EndLoop()
        s.request_receiver = NS(recv_requests=recv)
        s.get_next_batch_to_run, s.run_batch, s.process_batch_result = plan, run, process
        s.adaptive_idle.poller.wait = wait
        caches = {'weights': object(), 'kv': object(), 'allocator': object()}
        retained = dict(caches)
        with self.assertRaises(EndLoop):
            s.event_loop_normal()
        self.assertEqual(timeline, ['forward-complete', 'final-stream-handoff'])
        self.assertEqual(waits, [2000])
        self.assertEqual(caches, retained)
        self.assertEqual(s.adaptive_idle.policy.snapshot()['last_real_work_monotonic'], 1400)

    def test_native_is_fully_idle_suppresses_all_supported_queue_states(self):
        s = self.scheduler
        fields = [('running_batch', Batch([Generate()])), ('last_batch', Batch([Generate()])),
                  ('chunked_req', object()), ('waiting_queue', [Generate()]),
                  ('grammar_manager', NS(grammar_queue=[object()], _adaptive_pending_futures=set())),
                  ('dllm_manager', NS(any_staging_reqs=lambda: True))]
        self.clock.value = 1800
        s.adaptive_idle.poller.wait = lambda: self.fail('blocked active native work')
        for field, value in fields:
            old = getattr(s, field)
            setattr(s, field, value)
            with self.subTest(field=field):
                self.assertFalse(s.adaptive_idle.maybe_wait())
            setattr(s, field, old)

    def test_native_passive_inputs_do_not_renew(self):
        s = self.scheduler
        self.clock.value = 600
        calls = []
        def wait():
            calls.append(self.clock.value)
            if len(calls) == 3:
                raise EndLoop()
        s.adaptive_idle.poller.wait = wait
        s.request_receiver = NS(recv_requests=lambda: [object()])
        s.get_next_batch_to_run = lambda **kw: NS(running_batch=Batch(), batch_to_run=None)
        with self.assertRaises(EndLoop):
            s.event_loop_normal()
        self.assertEqual(calls, [600, 600, 600])
        self.assertEqual(s.adaptive_idle.policy.snapshot()['last_real_work_monotonic'], 0)

    def test_overlay_removes_legacy_idle_cache_path_and_keeps_request_code(self):
        self.assertNotIn('from sglang.srt.managers.scheduler_components.idle_sleeper import', self.source)
        self.assertNotIn('IdleSleeper(', self.source)
        self.assertIn('self.idle_sleeper = None', self.source)
        self.assertNotIn('--sleep-on-idle', self.source)


class NativeGrammarTests(unittest.TestCase):
    def test_actual_manager_retains_running_future_after_abort_and_queue_removal(self):
        import concurrent.futures
        import logging
        import time
        source_root = os.environ.get('H005_PINNED_TEXT_ROOT')
        if not source_root:
            self.skipTest('requires exact full grammar source')
        rel = 'python/sglang/srt/constrained/grammar_manager.py'
        raw = (Path(source_root) / rel).read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), 'dc4c94674191877a689c671713c739ab4693675f4fd26f68331a4751ecbc1903')
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / rel
            target.parent.mkdir(parents=True)
            target.write_bytes(raw)
            subprocess.run(['git', 'apply', str(ROOT / 'scripts/runtime/patches/text-adaptive-grammar.patch')],
                           cwd=directory, check=True, capture_output=True)
            tree = ast.parse(target.read_text())
        native = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'GrammarManager')
        future = concurrent.futures.Future()
        future.set_running_or_notify_cancel()
        backend = NS(enable_strict_thinking=False,
                     get_cached_or_future_value=lambda *args: (future, False))
        namespace = {'futures': concurrent.futures, 'time': time,
                     'logger': logging.getLogger('native-grammar-fixture'),
                     'create_grammar_backend': lambda *args, **kwargs: backend,
                     'envs': NS(SGLANG_GRAMMAR_POLL_INTERVAL=NS(get=lambda: 0.01),
                                SGLANG_GRAMMAR_MAX_POLL_ITERATIONS=NS(get=lambda: 100))}
        module = ast.Module(body=[ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')], level=0), native], type_ignores=[])
        exec(compile(ast.fix_missing_locations(module), '<exact patched grammar manager>', 'exec'), namespace)
        scheduler = state()
        scheduler.server_args.skip_tokenizer_init = False
        scheduler.tokenizer = object()
        scheduler.model_config = NS(vocab_size=100, hf_eos_token_id=2, think_end_ids=[])
        scheduler.dp_tp_cpu_group = object()
        scheduler.dp_tp_group = NS(world_size=1, first_rank=0, is_first_rank=True)
        scheduler.ps = NS(pp_rank=0, pp_size=1)
        scheduler.pp_group = None
        manager = namespace['GrammarManager'](scheduler)
        scheduler.grammar_manager = manager
        done = [False]
        req = NS(rid='real-grammar-request', require_reasoning=False,
                 sampling_params=NS(json_schema='{}', regex=None, ebnf=None, structural_tag=None),
                 finished=lambda: done[0], set_finish_with_abort=lambda message: done.__setitem__(0, True))
        self.assertTrue(manager.process_req_with_grammar(req))
        self.assertIn(future, manager._adaptive_pending_futures)
        manager.abort_requests(NS(abort_all=True, rid=''))
        self.assertFalse(future.cancelled())
        self.assertEqual(manager.get_ready_grammar_requests(), [req])
        self.assertEqual(manager.grammar_queue, [])
        self.assertIn(future, manager._adaptive_pending_futures)
        clock = Clock()
        binding = TextAdaptiveIdle(scheduler, lambda req: False, Drain, clock=clock)
        waits = []
        binding.poller.wait = lambda: waits.append(clock.value)
        clock.value = 2000
        self.assertFalse(binding.maybe_wait())
        future.set_result(object())
        clock.value = 2100
        self.assertFalse(binding.maybe_wait())
        clock.value = 2699.999
        self.assertFalse(binding.maybe_wait())
        clock.value = 2700
        self.assertTrue(binding.maybe_wait())
        self.assertEqual(waits, [2700])


if __name__ == '__main__':
    unittest.main()
