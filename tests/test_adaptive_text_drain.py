"""Real async-generator/ASGI lifetimes with an explicit in-memory IPC fixture."""
import asyncio
import ast
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from runtime import adaptive_text_drain as drain


class TokenizedGenerateReqInput:
    pass


class TokenizedEmbeddingReqInput:
    pass


class BatchTokenizedGenerateReqInput:
    pass


class BatchTokenizedEmbeddingReqInput:
    pass


class Manager:
    def __init__(self):
        self.messages = []
        self.events = []
        self.begin_gate = None
        self.end_fail = False
        self.end_received = asyncio.Event()
        self.wire = []
        self.preprocess_gate = None

    async def _async_dispatch_to_scheduler(self, message):
        if message.event == 'begin' and self.begin_gate is not None:
            await self.begin_gate.wait()
        if message.event == 'end' and self.end_fail:
            raise RuntimeError('synthetic IPC failure')
        self.messages.append(message)
        self.wire.append(message)
        if message.event == 'end':
            self.end_received.set()

    @drain.tracked_dispatch
    def _dispatch_to_scheduler(self, obj):
        self.wire.append(obj)
        return None

    @drain.tracked_generation
    async def generate_request(self, obj, request=None):
        self.events.append('native-start')
        try:
            if obj == 'raise':
                raise ValueError('original-validation-error')
            if self.preprocess_gate is not None:
                await self.preprocess_gate.wait()
            self._dispatch_to_scheduler(TokenizedGenerateReqInput())
            yield {'text': 'first'}
            if obj == 'wait':
                await asyncio.Event().wait()
            yield {'text': 'last'}
        finally:
            self.events.append('native-closed')


class DrainTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        # Exact native serialization is a separate installed-dependency test.
        dependency = types.SimpleNamespace(
            AdaptiveIdleDrainReq=types.SimpleNamespace,
            TokenizedGenerateReqInput=TokenizedGenerateReqInput,
            TokenizedEmbeddingReqInput=TokenizedEmbeddingReqInput,
            BatchTokenizedGenerateReqInput=BatchTokenizedGenerateReqInput,
            BatchTokenizedEmbeddingReqInput=BatchTokenizedEmbeddingReqInput)
        patcher = mock.patch.dict(sys.modules, {"sglang.srt.managers.io_struct": dependency})
        patcher.start()
        self.addCleanup(patcher.stop)

    async def asyncTearDown(self):
        pending = list(drain._NOTIFICATIONS)
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)

    async def test_direct_generator_preserves_outputs_order_and_one_completion(self):
        manager = Manager()
        self.assertEqual([r async for r in manager.generate_request('normal')],
                         [{'text': 'first'}, {'text': 'last'}])
        self.assertEqual([m.event for m in manager.messages], ['begin', 'end'])
        self.assertEqual(manager.messages[0].token, manager.messages[1].token)
        self.assertRegex(manager.messages[0].token, r'^[0-9a-f]{32}$')
        self.assertEqual(vars(manager.messages[0]).keys(), {'event', 'token', 'admitted'})
        self.assertEqual(manager.events, ['native-start', 'native-closed'])
        self.assertFalse(manager.messages[0].admitted)
        self.assertTrue(manager.messages[-1].admitted)
        self.assertIsInstance(manager.wire[1], TokenizedGenerateReqInput)

    async def test_final_asgi_send_and_cleanup_hold_completion_beyond_generation(self):
        manager, body_gate, cleanup_gate = Manager(), asyncio.Event(), asyncio.Event()
        final_send_started = asyncio.Event()
        async def app(scope, receive, send):
            result = [r async for r in manager.generate_request('normal')]
            self.assertEqual(result[-1], {'text': 'last'})
            await send({'type': 'http.response.body', 'body': b'last', 'more_body': False})
            await cleanup_gate.wait()
        async def send(event):
            final_send_started.set()
            await body_gate.wait()
        task = asyncio.create_task(drain.GenerationDrainMiddleware(app)(
            {'type':'http','path':'/v1/chat/completions'}, None, send))
        await final_send_started.wait()
        # Arbitrarily slow downstream transport does not emit end on native completion.
        self.assertEqual(manager.events, ['native-start', 'native-closed'])
        self.assertEqual([m.event for m in manager.messages], ['begin'])
        body_gate.set()
        await asyncio.sleep(0)
        self.assertEqual([m.event for m in manager.messages], ['begin'])
        cleanup_gate.set()
        await task
        self.assertEqual([m.event for m in manager.messages], ['begin','end'])

    async def test_native_nonstream_single_anext_finalizes_and_does_not_leak_pending(self):
        manager = Manager()
        async def app(scope, receive, send):
            # Exact native /generate and chat nonstream consumption pattern:
            # no retained iterator reference and only one __anext__ call.
            reply = await manager.generate_request('normal').__anext__()
            self.assertEqual(reply, {'text':'first'})
        await drain.GenerationDrainMiddleware(app)({'type':'http','path':'/generate'},None,None)
        await asyncio.wait_for(manager.end_received.wait(), timeout=1)
        self.assertEqual(manager.events, ['native-start', 'native-closed'])
        self.assertEqual([m.event for m in manager.messages], ['begin','end'])

    async def test_cancelled_stream_closes_native_and_sends_one_end(self):
        manager, started = Manager(), asyncio.Event()
        async def app(scope, receive, send):
            async for response in manager.generate_request('wait'):
                started.set()
        task = asyncio.create_task(drain.GenerationDrainMiddleware(app)(
            {'type':'http','path':'/generate'}, None, None))
        await started.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(manager.events, ['native-start','native-closed'])
        self.assertEqual([m.event for m in manager.messages], ['begin','end'])

    async def test_cancel_during_begin_retains_order_and_never_starts_native(self):
        manager = Manager()
        manager.begin_gate = asyncio.Event()
        iterator = manager.generate_request('normal')
        task = asyncio.create_task(anext(iterator))
        await asyncio.sleep(0)
        task.cancel()
        await asyncio.sleep(0)
        self.assertEqual(manager.events, [])
        manager.begin_gate.set()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual([m.event for m in manager.messages], ['begin','end'])

    async def test_passive_or_rejected_http_requests_do_not_submit_idle_controls(self):
        for path in ('/v1/readiness','/metrics','/health','/health_generate','/model_info'):
            manager = Manager()
            async def app(scope, receive, send):
                # Native health does invoke generation; it remains explicitly excluded.
                if path.startswith('/health'):
                    _ = [r async for r in manager.generate_request('normal')]
            await drain.GenerationDrainMiddleware(app)({'type':'http','path':path},None,None)
            self.assertEqual(manager.messages, [])

    async def test_original_validation_exception_survives_failed_end_notification(self):
        manager = Manager()
        manager.end_fail = True
        with self.assertRaisesRegex(ValueError, 'original-validation-error'):
            _ = [r async for r in manager.generate_request('raise')]
        self.assertEqual([m.event for m in manager.messages], ['begin'])

    async def test_validation_rejection_reservation_does_not_claim_admitted_work(self):
        manager = Manager()
        with self.assertRaisesRegex(ValueError, 'original-validation-error'):
            _ = [r async for r in manager.generate_request('raise')]
        self.assertEqual([m.event for m in manager.messages], ['begin', 'end'])
        self.assertEqual([m.admitted for m in manager.messages], [False, False])
        self.assertEqual(manager.wire, manager.messages)  # No model dispatch.
        from tests.test_adaptive_text import Clock, TextAdaptiveIdle, state
        clock = Clock()
        idle = TextAdaptiveIdle(state(), lambda req: False, types.SimpleNamespace, clock=clock)
        clock.value = 900
        initial_grace = idle.policy.snapshot()['last_real_work_monotonic']
        idle.consume_notifications(manager.messages[:1])
        self.assertFalse(idle.maybe_wait())  # Preprocessing reservation inhibits sleep.
        idle.consume_notifications(manager.messages[1:])
        self.assertEqual(idle.policy.snapshot()['last_real_work_monotonic'], initial_grace)
        self.assertTrue(idle.maybe_wait())  # Rejection cannot buy another 600 seconds.

    async def test_pending_preprocessing_reserves_sleep_without_claiming_work(self):
        manager = Manager()
        manager.preprocess_gate = asyncio.Event()
        task = asyncio.create_task(anext(manager.generate_request('normal')))
        for _ in range(4):
            await asyncio.sleep(0)
        self.assertEqual([m.event for m in manager.messages], ['begin'])
        self.assertFalse(manager.messages[0].admitted)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual([m.event for m in manager.messages], ['begin', 'end'])
        self.assertFalse(manager.messages[-1].admitted)

    async def test_generator_dispatch_context_does_not_leak_across_yields(self):
        manager = Manager()
        iterator = manager.generate_request('normal')
        await anext(iterator)
        self.assertIsNone(drain._CURRENT_GENERATION.get())
        # A second rejected invocation in the same task must stay unadmitted.
        with self.assertRaises(ValueError):
            _ = [r async for r in manager.generate_request('raise')]
        self.assertFalse(manager.messages[-1].admitted)
        await iterator.aclose()
        self.assertTrue(manager.messages[-1].admitted)

    @unittest.skipUnless(os.environ.get('H005_PINNED_TEXT_ROOT'), 'exact native source root not supplied')
    async def test_full_pinned_patch_and_actual_native_sync_dispatch_hook(self):
        root = Path(os.environ['H005_PINNED_TEXT_ROOT'])
        pins = {
            'python/sglang/srt/managers/tokenizer_manager.py': 'bdfaa4f4f214515f2138a3a82e8215882735490dfa85c271d2c41830b682ad33',
            'python/sglang/srt/entrypoints/http_server.py': 'd8cc81f8d9866957dd4c0aa59917afa3d4d7d0e28eefaff0a9800157ed068a43',
            'python/sglang/srt/managers/io_struct.py': 'ebe1d216c98d0918c39089832f872a225977ce53c244680c9bcee51dee70e9e6',
        }
        patch = (Path(__file__).resolve().parents[1] /
                 'scripts/runtime/patches/text-adaptive-drain.patch').read_bytes()
        with tempfile.TemporaryDirectory() as temporary:
            for relative, sha in pins.items():
                raw = (root / relative).read_bytes()
                self.assertEqual(hashlib.sha256(raw).hexdigest(), sha)
                path = Path(temporary) / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(raw)
            subprocess.run(['git', 'apply', '--check', '-'], input=patch, cwd=temporary, check=True)
            subprocess.run(['git', 'apply', '-'], input=patch, cwd=temporary, check=True)
            trees = {name: ast.parse((Path(temporary) / name).read_bytes()) for name in pins}
            for name, tree in trees.items():
                compile(tree, name, 'exec')
            tree = trees['python/sglang/srt/managers/tokenizer_manager.py']
            cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'TokenizerManager')
            method = next(n for n in cls.body if isinstance(n, ast.FunctionDef)
                          and n.name == '_dispatch_to_scheduler')
            self.assertEqual([ast.unparse(n) for n in method.decorator_list], ['tracked_dispatch'])
            namespace = {'tracked_dispatch': drain.tracked_dispatch, 'Any': object,
                         'sock_send': lambda socket, obj: socket.append(obj)}
            exec(compile(ast.Module(body=[method], type_ignores=[]), 'actual-native-dispatch', 'exec'), namespace)
            manager = Manager()
            manager.tokenizer_ipc_name = None
            manager.send_to_scheduler = manager.wire
            manager._dispatch_to_scheduler = types.MethodType(namespace['_dispatch_to_scheduler'], manager)
            self.assertEqual([r async for r in manager.generate_request('normal')],
                             [{'text': 'first'}, {'text': 'last'}])
            self.assertTrue(manager.messages[-1].admitted)
            self.assertIsInstance(manager.wire[1], TokenizedGenerateReqInput)

    async def test_completed_asgi_waits_for_still_running_generator_task(self):
        manager, yielded, finish = Manager(), asyncio.Event(), asyncio.Event()
        async def background():
            iterator = manager.generate_request('normal')
            self.assertEqual(await anext(iterator), {'text':'first'})
            yielded.set()
            await finish.wait()
            await iterator.aclose()
        tasks=[]
        async def app(scope, receive, send):
            tasks.append(asyncio.create_task(background()))
            await yielded.wait()
        await drain.GenerationDrainMiddleware(app)({'type':'http','path':'/generate'},None,None)
        self.assertEqual([m.event for m in manager.messages], ['begin'])
        finish.set()
        await tasks[0]
        self.assertEqual([m.event for m in manager.messages], ['begin','end'])

    async def test_concurrent_requests_do_not_end_each_others_generation(self):
        manager, gates = Manager(), [asyncio.Event(), asyncio.Event()]
        started = [asyncio.Event(), asyncio.Event()]
        async def app(scope, receive, send):
            _ = [r async for r in manager.generate_request('normal')]
            index=scope['index']; started[index].set(); await gates[index].wait()
        middleware=drain.GenerationDrainMiddleware(app)
        tasks=[asyncio.create_task(middleware({'type':'http','path':'/generate','index':i},None,None))
               for i in range(2)]
        await asyncio.gather(*(event.wait() for event in started))
        self.assertEqual([m.event for m in manager.messages], ['begin','begin'])
        gates[0].set(); await tasks[0]
        self.assertEqual([m.event for m in manager.messages], ['begin','begin','end'])
        gates[1].set(); await tasks[1]
        begins={m.token for m in manager.messages if m.event=='begin'}
        ends={m.token for m in manager.messages if m.event=='end'}
        self.assertEqual(len(begins),2)
        self.assertEqual(begins,ends)


if __name__ == '__main__':
    unittest.main()
