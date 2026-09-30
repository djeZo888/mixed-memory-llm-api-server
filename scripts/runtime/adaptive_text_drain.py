"""Track native generation through ASGI response draining on the existing IPC.

No model request fields or outputs change. A reservation protects asynchronous
preprocessing without renewing grace. Only an actual tokenized model dispatch
marks work admitted; end follows BOTH generator closure and ASGI app completion
(including final send/background cleanup). Outside HTTP, generator closure is
the completion boundary. Failed/cancelled notifications leave the scheduler's
pending state conservative; generation is never replayed.
"""
from __future__ import annotations

import asyncio
from contextvars import ContextVar
from functools import wraps
import uuid


_CONTEXT = ContextVar("llmctl_native_generation_drain", default=None)
_CURRENT_GENERATION = ContextVar("llmctl_dispatched_generation", default=None)
_NOTIFICATIONS = set()  # Keep cancellation-shielded, finite-lived sends alive.
PASSIVE_PREFIXES = ("/health", "/metrics")


def _task(coroutine):
    task = asyncio.create_task(coroutine)
    _NOTIFICATIONS.add(task)

    def finished(done):
        _NOTIFICATIONS.discard(done)
        # Delivery failure must not rewrite an already-sent model response.
        # An unmatched begin remains pending in the scheduler (fail closed).
        if not done.cancelled():
            done.exception()

    task.add_done_callback(finished)
    return task


class _Generation:
    def __init__(self, manager, context):
        self.manager = manager
        self.context = context
        self.token = uuid.uuid4().hex
        self.generator_done = False
        self.end_task = None
        self.admitted = False
        self.begin_task = _task(self._send("begin"))
        if context is not None:
            context.generations.add(self)

    async def _send(self, event):
        # A tagged native IPC type participates in the pinned typed msgspec
        # union; arbitrary dicts are intentionally rejected by that transport.
        from sglang.srt.managers.io_struct import AdaptiveIdleDrainReq
        await self.manager._async_dispatch_to_scheduler(
            AdaptiveIdleDrainReq(event=event, token=self.token, admitted=self.admitted))

    def maybe_end(self):
        if (self.generator_done and (self.context is None or self.context.closed)
                and self.end_task is None):
            self.end_task = _task(self._end())
        return self.end_task

    async def _end(self):
        try:
            # A cancelled caller may finish before the begin transport send.
            await self.begin_task
            await self._send("end")
        finally:
            if self.context is not None:
                self.context.generations.discard(self)


class _Request:
    def __init__(self, passive):
        self.passive = passive
        self.closed = False
        self.generations = set()

    def close(self):
        self.closed = True
        return [task for generation in tuple(self.generations)
                if (task := generation.maybe_end()) is not None]


def tracked_dispatch(original):
    """Mark admission only at the existing synchronous typed model send.

    Preserve the native call/return/send semantics without async conversion.
    Control requests and validation failures cannot turn reservations into work.
    """
    @wraps(original)
    def dispatch(self, obj):
        from sglang.srt.managers.io_struct import (
            TokenizedGenerateReqInput, TokenizedEmbeddingReqInput, BatchTokenizedGenerateReqInput,
            BatchTokenizedEmbeddingReqInput,
        )
        result = original(self, obj)
        generation = _CURRENT_GENERATION.get()
        if (generation is not None and generation.manager is self
                and type(obj) in (TokenizedGenerateReqInput, TokenizedEmbeddingReqInput,
                                 BatchTokenizedGenerateReqInput, BatchTokenizedEmbeddingReqInput)):
            generation.admitted = True
        return result
    return dispatch


def tracked_generation(original):
    """Wrap the pinned TokenizerManager.generate_request async generator only."""
    @wraps(original)
    async def generate(self, obj, request=None):
        context = _CONTEXT.get()
        path = getattr(getattr(request, "url", None), "path", "")
        passive = ((context is not None and context.passive)
                   or isinstance(path, str) and path.startswith(PASSIVE_PREFIXES))
        native = original(self, obj, request)
        generation = None if passive else _Generation(self, context)
        try:
            if generation is not None:
                await asyncio.shield(generation.begin_task)
            while True:
                # Never leak this invocation's dispatch identity across yield
                # into a caller consuming another generator in the same task.
                reset = _CURRENT_GENERATION.set(generation)
                try:
                    try:
                        response = await native.__anext__()
                    except StopAsyncIteration:
                        break
                finally:
                    _CURRENT_GENERATION.reset(reset)
                yield response
        finally:
            try:
                reset = _CURRENT_GENERATION.set(generation)
                try:
                    await native.aclose()
                finally:
                    _CURRENT_GENERATION.reset(reset)
            finally:
                if generation is not None:
                    generation.generator_done = True
                    task = generation.maybe_end()
                    if task is not None:
                        # Keep delivery alive if the request task is cancelled.
                        await asyncio.gather(asyncio.shield(task), return_exceptions=True)
    return generate


class GenerationDrainMiddleware:
    """Pure ASGI: untouched scope/events/body, and no work on request arrival."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        context = _Request(scope.get("path", "").startswith(PASSIVE_PREFIXES))
        reset = _CONTEXT.set(context)
        try:
            await self.app(scope, receive, send)
        finally:
            tasks = context.close()
            _CONTEXT.reset(reset)
            if tasks:
                # Shield independently: repeated request cancellation cannot
                # cancel an enqueued completion or change model reply content.
                await asyncio.gather(*(asyncio.shield(task) for task in tasks),
                                     return_exceptions=True)
