"""Offline binding plus execution of the exact transformed scheduler loop.

Dependency fixtures replace CUDA/SGLang/ZMQ imports honestly; the loop and
sequential-output draining methods are compiled from the full hash-pinned source.
Set ADAPTIVE_IMAGE_SOURCE_ROOT to a retained raw-source tree for source tests.
No network retrieval occurs in tests and full upstream source is not vendored.
"""
import ast
from collections import deque
from contextlib import nullcontext
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
from types import SimpleNamespace as NS
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from runtime.adaptive_diffusion import DiffusionIdleBinding

SOURCE_REL = 'python/sglang/multimodal_gen/runtime/managers/scheduler.py'
SOURCE_SHA = '84302a63933a7bb4a869aaafd842d2bdb24157339a8123270eab65537ec82077'
ASYNC_FIELDS = ('_pool_work_pull', '_pool_result_push', '_transfer_manager',
                '_transfer_stream', '_rdma_push_queue', '_rdma_push_thread',
                '_rdma_push_zmq', '_compute_ready_queue', '_recv_prefetch_thread')


class Req:
    is_warmup = False


class Clock:
    now = 0.0
    def __call__(self):
        return self.now


def scheduler_fixture():
    s = NS(server_args=NS(num_gpus=1, dp_size=1, sp_degree=1, tp_size=1,
                         enable_cfg_parallel=False),
           _disagg_role=NS(value='monolithic'), _disagg_mode=False,
           receiver=object(), waiting_queue=deque(),
           _poller=NS(poll=lambda: None))
    for name in ASYNC_FIELDS:
        setattr(s, name, None)
    return s


class BindingTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.scheduler = scheduler_fixture()
        self.waits = []
        self.scheduler._poller.poll = lambda: self.waits.append(self.clock.now)
        self.binding = DiffusionIdleBinding(self.scheduler, Req, clock=self.clock)

    def test_boundary_passive_observations_and_no_cache_access(self):
        objects = {name: object() for name in ('weights', 'kv', 'allocator')}
        original = dict(objects)
        self.scheduler.worker = NS(empty_cache=lambda: objects.clear(), cache=objects)
        self.clock.now = 599.999
        self.assertFalse(self.binding.maybe_wait())
        self.clock.now = 600
        self.assertTrue(self.binding.maybe_wait())
        for _ in range(3):
            self.binding.begin([(b'client', object())])
            self.clock.now += 20
            self.assertFalse(self.binding.maybe_wait())  # Control still dispatching.
            self.binding.complete()
            self.assertTrue(self.binding.maybe_wait())
        self.assertEqual(self.binding.policy.snapshot()['last_real_work_monotonic'], 0)
        self.assertEqual(self.waits, [600, 620, 640, 660])
        self.assertEqual(objects, original)
        self.assertTrue(all(objects[name] is original[name] for name in objects))

    def test_long_generation_final_completion_and_warmup_get_full_grace(self):
        for grouped in (False, True):
            request = Req()
            request.is_warmup = grouped
            self.clock.now += 1000
            self.binding.begin([(b'client', [request] if grouped else request)])
            self.clock.now += 1500
            self.assertFalse(self.binding.maybe_wait())
            self.clock.now += 5
            self.binding.complete()
            completed = self.clock.now
            self.clock.now = completed + 599.999
            self.assertFalse(self.binding.maybe_wait())
            self.clock.now = completed + 600
            self.assertTrue(self.binding.maybe_wait())

    def test_real_queue_suppresses_wait_passive_queue_does_not_renew(self):
        self.clock.now = 800
        self.scheduler.waiting_queue.append((b'client', object(), 100))
        self.assertFalse(self.binding.maybe_wait())
        self.assertEqual(self.binding.policy.snapshot()['last_real_work_monotonic'], 0)
        self.scheduler.waiting_queue.append((b'client', Req(), 200))
        self.assertFalse(self.binding.maybe_wait())
        self.assertEqual(self.binding.policy.snapshot()['last_real_work_monotonic'], 800)

    def test_unsupported_async_and_multirank_fail_closed(self):
        for field in ASYNC_FIELDS:
            for value in (deque(), object()):
                s = scheduler_fixture()
                setattr(s, field, value)
                with self.subTest(field=field), self.assertRaisesRegex(
                        RuntimeError, 'async_state_not_supported'):
                    DiffusionIdleBinding(s, Req)
        s = scheduler_fixture()
        del s._compute_ready_queue
        with self.assertRaisesRegex(RuntimeError, 'async_state_not_supported'):
            DiffusionIdleBinding(s, Req)
        for name in ('num_gpus', 'dp_size', 'sp_degree', 'tp_size'):
            s = scheduler_fixture()
            setattr(s.server_args, name, 2)
            with self.subTest(name=name), self.assertRaisesRegex(
                    RuntimeError, 'unsupported_execution_mode'):
                DiffusionIdleBinding(s, Req)

    def test_level_triggered_wait_immediate_arrival_and_renewal(self):
        entered, arrival, completed = threading.Event(), threading.Event(), threading.Event()
        self.clock.now = 600
        def poll():
            entered.set()
            if not arrival.wait(1):
                raise AssertionError('lost wake')
        self.scheduler._poller.poll = poll
        def execute():
            self.binding.maybe_wait()
            self.binding.begin([(b'client', Req())])
            self.clock.now = 605
            self.binding.complete()
            completed.set()
        thread = threading.Thread(target=execute, daemon=True)
        thread.start()
        try:
            self.assertTrue(entered.wait(1))
            self.assertFalse(completed.is_set())
            self.clock.now = 601
            arrival.set()
            self.assertTrue(completed.wait(1))
        finally:
            arrival.set()
            thread.join(1)
        self.clock.now = 1204.999
        self.assertFalse(self.binding.maybe_wait())
        self.assertEqual(self.binding.policy.snapshot()['last_real_work_monotonic'], 605)

    def test_arrival_at_empty_check_to_poll_boundary_is_not_lost(self):
        self.clock.now = 600
        readable = threading.Event()
        def poll():
            # Arrival after the helper's queue check but before entering wait.
            readable.set()
            self.assertTrue(readable.wait(0))
        self.scheduler._poller.poll = poll
        self.assertTrue(self.binding.maybe_wait())


class ExactPatchedLoopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(os.environ.get('ADAPTIVE_IMAGE_SOURCE_ROOT',
                    ROOT.parent / 'scratch/installed/image'))
        source = root / SOURCE_REL
        if not source.is_file():
            raise unittest.SkipTest('Exact native source not supplied; set ADAPTIVE_IMAGE_SOURCE_ROOT')
        raw = source.read_bytes()
        if hashlib.sha256(raw).hexdigest() != SOURCE_SHA:
            raise AssertionError('Source differs from exact pinned scheduler')
        cls.before = raw.decode()
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / SOURCE_REL
            target.parent.mkdir(parents=True)
            target.write_bytes(raw)
            subprocess.run(['git', 'apply', str(ROOT / 'scripts/runtime/patches/diffusion-adaptive-idle.patch')],
                           cwd=tmp, capture_output=True, check=True)
            cls.after = target.read_text()
        cls.tree = ast.parse(cls.after)
        # Compile the full transformed file for syntax, then execute its exact
        # loop/drain methods with explicit dependency fixtures (no CUDA claims).
        compile(cls.tree, 'pinned_diffusion_scheduler.py', 'exec')

    def build(self, *, sequential=False, reply_error=False):
        clock, binding, polls, returns = Clock(), [], [], []
        role = NS(value='monolithic')
        class ZMQError(Exception):
            pass
        class OutputBatch:
            def __init__(self, error=None): self.error = error
        class Sequential:
            def __init__(self, outputs): self.outputs = outputs
        def make_binding(scheduler, req):
            result = DiffusionIdleBinding(scheduler, req, clock=clock)
            binding.append(result)
            return result
        namespace = dict(AdaptiveIdle=None, DiffusionIdleBinding=make_binding, Req=Req,
                         RoleType=NS(MONOLITHIC=role), time=NS(monotonic=clock),
                         maybe_record_function=lambda *a: nullcontext(),
                         logger=NS(debug=lambda *a: None, error=lambda *a, **k: None),
                         zmq=NS(ZMQError=ZMQError), OutputBatch=OutputBatch,
                         _SequentiallyReturnedOutputs=Sequential,
                         get_first_generation_req=lambda r: r if isinstance(r, Req) else None)
        cls_node = next(n for n in self.tree.body if isinstance(n, ast.ClassDef) and n.name == 'Scheduler')
        methods = [n for n in cls_node.body if isinstance(n, ast.FunctionDef) and n.name in
                   ('event_loop', '_return_results_sequentially', '_fetch_next_output')]
        # Postponed annotations keep dependency fixtures intentionally small.
        future = ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')], level=0)
        ast.fix_missing_locations(future)
        module = ast.Module(body=[future, *methods], type_ignores=[])
        exec(compile(module, 'exact_patched_scheduler_methods.py', 'exec'), namespace)
        s = scheduler_fixture()
        s._disagg_role = role
        s.dp_replica = 0
        s._running = True
        s.metrics = s._disagg_metrics = None
        s._max_consecutive_errors = 3
        s._consecutive_error_count = 0
        s._log_batch_metrics_summary = lambda: None
        s._cleanup_disagg = lambda: None
        s.context = NS(destroy=lambda **k: None)
        s.receiver = NS(close=lambda: None)
        s._req_label = lambda items: 'fixture'
        s._dynamic_batching_enabled = lambda: False
        s.process_received_reqs_with_req_based_warmup = lambda reqs: reqs
        s.get_next_batch_to_run = lambda: [(q[0], q[1]) for q in [s.waiting_queue.popleft()]] if s.waiting_queue else None
        s._return_results_sequentially = namespace['_return_results_sequentially'].__get__(s)
        s._fetch_next_output = namespace['_fetch_next_output'].__func__
        s._return_sequential_errors = lambda *args: None
        receives = 0
        def recv():
            nonlocal receives
            receives += 1
            if receives == 1:
                clock.now = 1
                return [(b'client', Req())]
            if receives == 2:
                self.assertEqual(binding[0].policy.snapshot()['last_real_work_monotonic'], 1005)
                clock.now = 1604.999
                return []
            if receives == 3:
                self.assertEqual(polls, [])
                clock.now = 1605
                return []
            if receives == 4:
                self.assertEqual(polls, [1605])
                return [(b'client', object())]  # Passive control.
            self.assertEqual(polls, [1605, 1605])
            s._running = False
            return []
        s.recv_reqs = recv
        s._poller.poll = lambda: polls.append(clock.now)
        def outputs():
            try:
                clock.now = 1001
                self.assertFalse(binding[0].maybe_wait())  # Generator still active.
                yield OutputBatch()
            finally:
                clock.now = 1005  # Final generator close work, after reply.
        def dispatch(items):
            if isinstance(items[0][1], Req):
                if sequential:
                    return Sequential(outputs())
                clock.now = 1001
                self.assertFalse(binding[0].maybe_wait())
            return OutputBatch()
        s._dispatch_items = dispatch
        def return_result(item, output):
            returns.append(type(item[1]))
            if isinstance(item[1], Req):
                clock.now = 1005
                if reply_error: raise ZMQError('fixture send failure')
        s._return_item_result = return_result
        namespace['event_loop'](s)
        return binding[0], polls, returns

    def test_long_request_final_reply_grace_and_passive_wake(self):
        binding, polls, returns = self.build()
        self.assertEqual(binding.policy.snapshot()['last_real_work_monotonic'], 1005)
        self.assertEqual(polls, [1605, 1605])
        self.assertEqual(returns, [Req, object])

    def test_streaming_iterator_finally_included_in_completion_grace(self):
        binding, polls, _ = self.build(sequential=True)
        self.assertEqual(binding.policy.snapshot()['last_real_work_monotonic'], 1005)
        self.assertEqual(polls, [1605, 1605])

    def test_reply_error_still_completes_real_work_before_grace(self):
        binding, _, _ = self.build(reply_error=True)
        self.assertEqual(binding.policy.snapshot()['last_real_work_monotonic'], 1005)

    def test_patch_changes_only_import_and_event_loop(self):
        before, after = ast.parse(self.before), ast.parse(self.after)
        for tree in (before, after):
            for item in tree.body:
                if isinstance(item, ast.ClassDef) and item.name == 'Scheduler':
                    item.body = [n for n in item.body if not (isinstance(n, ast.FunctionDef) and n.name == 'event_loop')]
            tree.body = [n for n in tree.body if not (isinstance(n, ast.ImportFrom) and
                         n.module == 'sglang.multimodal_gen.runtime.managers.adaptive_diffusion')]
        self.assertEqual(ast.dump(before), ast.dump(after))


class NativeDrainTests(unittest.IsolatedAsyncioTestCase):
    async def test_native_postprocessing_and_asgi_backpressure_get_final_grace(self):
        from runtime.adaptive_diffusion_drain import DiffusionDrainMiddleware, track_generation
        clock, scheduler = Clock(), scheduler_fixture()
        waits, signals = [], []
        scheduler._poller.poll = lambda: waits.append(clock.now)
        binding = DiffusionIdleBinding(scheduler, Req, clock=clock)

        class Client:
            @track_generation(Req)
            async def forward(self, batch):
                if isinstance(batch, dict):
                    signals.append(batch['event'])
                    binding.process_signals([(b'client', batch)], lambda identity: None)
                    return NS()
                binding.begin([(b'client', batch)])
                clock.now = 1000
                binding.complete()  # Scheduler reply available; native HTTP not done.
                return NS()
        client = Client()
        async def app(scope, receive, send):
            await client.forward([Req()])
            clock.now = 1700  # Slow native encode/store/serialize after scheduler reply.
            self.assertFalse(binding.maybe_wait())
            await send({'type': 'http.response.body', 'body': b'image'})
        async def send(message):
            clock.now = 2500  # ASGI output backpressure still owns work.
            self.assertFalse(binding.maybe_wait())
            self.assertEqual(signals, ['begin'])
        middleware = DiffusionDrainMiddleware(app)
        await middleware({'type': 'http', 'method': 'POST', 'path': '/v1/images/generations'}, None, send)
        self.assertEqual(signals, ['begin', 'end'])
        self.assertEqual(binding.policy.snapshot()['last_real_work_monotonic'], 2500)
        clock.now = 3099.999
        self.assertFalse(binding.maybe_wait())
        clock.now = 3100
        self.assertTrue(binding.maybe_wait())
        self.assertEqual(waits, [3100])

    async def test_passive_route_and_validation_failure_never_send_signals(self):
        from runtime.adaptive_diffusion_drain import DiffusionDrainMiddleware, track_generation
        sent = []
        class Client:
            @track_generation(Req)
            async def forward(self, batch):
                sent.append(batch)
        client = Client()
        async def passive(scope, receive, send):
            await client.forward({'status': True})
        for path in ('/health', '/metrics', '/v1/images/generations', '/v1/images/edits'):
            await DiffusionDrainMiddleware(passive)(
                {'type': 'http', 'method': 'POST', 'path': path}, None, None)
        self.assertEqual(sent, [{'status': True}] * 4)
        # Warmup/non-HTTP native request is covered by scheduler completion only.
        request = Req()
        await client.forward(request)
        self.assertIs(sent[-1], request)

    async def test_failed_end_delivery_keeps_scheduler_busy_conservatively(self):
        from runtime.adaptive_diffusion_drain import DiffusionDrainMiddleware, track_generation
        clock, scheduler = Clock(), scheduler_fixture()
        binding = DiffusionIdleBinding(scheduler, Req, clock=clock)
        class Client:
            @track_generation(Req)
            async def forward(self, batch):
                if isinstance(batch, dict):
                    if batch['event'] == 'end':
                        raise OSError('fixture IPC loss')
                    binding.process_signals([(b'client', batch)], lambda identity: None)
        client = Client()
        async def app(scope, receive, send):
            await client.forward(Req())
        await DiffusionDrainMiddleware(app)(
            {'type': 'http', 'method': 'POST', 'path': '/v1/images/edits'}, None, None)
        clock.now = 5000
        self.assertFalse(binding.maybe_wait())
        self.assertEqual(len(binding._pending_drains), 1)

    async def test_cancelled_begin_ack_never_dispatches_or_clears_uncertain_token(self):
        import asyncio
        from runtime.adaptive_diffusion_drain import DiffusionDrainMiddleware, track_generation
        clock, scheduler = Clock(), scheduler_fixture()
        binding = DiffusionIdleBinding(scheduler, Req, clock=clock)
        accepted, blocked_ack = asyncio.Event(), asyncio.Event()
        signals, dispatched = [], []
        class Client:
            @track_generation(Req)
            async def forward(self, batch):
                if isinstance(batch, dict):
                    signals.append(batch['event'])
                    # Native scheduler accepted begin, but its ACK has not
                    # reached the HTTP task when cancellation arrives.
                    binding.process_signals([(b'client', batch)], lambda identity: None)
                    accepted.set()
                    await blocked_ack.wait()
                else:
                    dispatched.append(batch)
        client = Client()
        async def app(scope, receive, send):
            await client.forward(Req())
        task = asyncio.create_task(DiffusionDrainMiddleware(app)(
            {'type': 'http', 'method': 'POST', 'path': '/v1/images/generations'}, None, None))
        await asyncio.wait_for(accepted.wait(), 1)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(dispatched, [])  # No generation or replay after uncertain ACK.
        self.assertEqual(signals, ['begin'])
        self.assertEqual(len(binding._pending_drains), 1)
        clock.now = 5000
        self.assertFalse(binding.maybe_wait())  # No timer expires uncertain state.
        clock.now = 10000
        self.assertFalse(binding.maybe_wait())

    async def test_unhandled_outer_error_retains_pending_until_owner_recovery(self):
        from runtime.adaptive_diffusion_drain import DiffusionDrainMiddleware, track_generation
        clock, scheduler = Clock(), scheduler_fixture()
        binding = DiffusionIdleBinding(scheduler, Req, clock=clock)
        signals = []
        class Client:
            @track_generation(Req)
            async def forward(self, batch):
                if isinstance(batch, dict):
                    signals.append(batch['event'])
                    binding.process_signals([(b'client', batch)], lambda identity: None)
        client = Client()
        async def app(scope, receive, send):
            await client.forward(Req())
            raise RuntimeError('fixture outer500 has not drained')
        with self.assertRaisesRegex(RuntimeError, 'outer500'):
            await DiffusionDrainMiddleware(app)(
                {'type': 'http', 'method': 'POST', 'path': '/v1/images/edits'}, None, None)
        clock.now = 9000
        self.assertFalse(binding.maybe_wait())
        self.assertEqual(signals, ['begin'])

    async def test_response_cancellation_finalizes_end_and_preserves_cancel(self):
        import asyncio
        from runtime.adaptive_diffusion_drain import DiffusionDrainMiddleware, track_generation
        signals = []
        class Client:
            @track_generation(Req)
            async def forward(self, batch):
                if isinstance(batch, dict): signals.append(batch['event'])
        client = Client()
        async def app(scope, receive, send):
            await client.forward(Req())
            raise asyncio.CancelledError()
        with self.assertRaises(asyncio.CancelledError):
            await DiffusionDrainMiddleware(app)(
                {'type': 'http', 'method': 'POST', 'path': '/v1/images/edits'}, None, None)
        self.assertEqual(signals, ['begin', 'end'])

    async def test_late_forward_completion_after_response_never_loses_end(self):
        import asyncio
        from runtime.adaptive_diffusion_drain import DiffusionDrainMiddleware, track_generation
        entered, release = asyncio.Event(), asyncio.Event()
        signals, children = [], []
        class Client:
            @track_generation(Req)
            async def forward(self, batch):
                if isinstance(batch, dict):
                    signals.append(batch['event'])
                else:
                    entered.set()
                    await release.wait()
        client = Client()
        async def app(scope, receive, send):
            children.append(asyncio.create_task(client.forward(Req())))
            await entered.wait()
        await DiffusionDrainMiddleware(app)(
            {'type': 'http', 'method': 'POST', 'path': '/v1/images/edits'}, None, None)
        self.assertEqual(signals, ['begin'])
        release.set()
        await children[0]
        self.assertEqual(signals, ['begin', 'end'])

    async def test_exact_source_drain_patch_full_compile_and_hook_positions(self):
        root = Path(os.environ.get('ADAPTIVE_IMAGE_SOURCE_ROOT', ROOT.parent / 'scratch/native/image'))
        files = {'python/sglang/multimodal_gen/runtime/scheduler_client.py': '9f2e9aaf88d8227d78b80a063c10e9c1bf8674f485cf145a09eb8c94c52fc22e', 'python/sglang/multimodal_gen/runtime/entrypoints/http_server.py': 'e4d11f5a5d43ab12d0ac6631524bb0b0b4aeee736e7f9cf3091eeb034cac2e41'}
        if not all((root / name).is_file() for name in files):
            self.skipTest('Complete pinned diffusion client+HTTP source not supplied')
        with tempfile.TemporaryDirectory() as directory:
            for name in files:
                target = Path(directory) / name
                target.parent.mkdir(parents=True, exist_ok=True)
                raw = (root / name).read_bytes()
                self.assertEqual(hashlib.sha256(raw).hexdigest(), files[name])
                target.write_bytes(raw)
            subprocess.run(['git', 'apply', str(ROOT / 'scripts/runtime/patches/diffusion-adaptive-drain.patch')],
                           cwd=directory, check=True, capture_output=True)
            for name in files:
                tree = ast.parse((Path(directory) / name).read_text())
                compile(tree, name, 'exec')
                if name.endswith('scheduler_client.py'):
                    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'AsyncSchedulerClient')
                    forward = next(n for n in cls.body if isinstance(n, ast.AsyncFunctionDef) and n.name == 'forward')
                    self.assertEqual(ast.unparse(forward.decorator_list[0]), 'track_generation(Req)')
                else:
                    create = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'create_app')
                    self.assertEqual(ast.unparse(create.body[-2]), 'app.add_middleware(DiffusionDrainMiddleware)')


if __name__ == '__main__':
    unittest.main()
