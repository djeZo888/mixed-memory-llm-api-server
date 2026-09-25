"""Native image request-drain tracking, carried over its existing scheduler IPC.

Only actual Req submissions inside the two accepted native image POST routes
start tracking. The matching end is sent after forward and ASGI response cleanup
both finish; passive traffic and failed validation do not count as model work.
The boundary is application ASGI send completion, not remote TCP receipt.
"""
from __future__ import annotations

import asyncio
from contextvars import ContextVar
from functools import wraps
import uuid

_SCOPE = ContextVar("adaptive_diffusion_request_drain", default=None)
_END_TASKS = set()
_SIGNAL_KEY = "__llmctl_adaptive_drain__"


def _signal(event, token):
    return {_SIGNAL_KEY: 1, "event": event, "token": token}


async def _end(client, token):
    # An undelivered end leaves the scheduler conservatively busy. This is a
    # lifecycle failure, never a timeout-based licence to clear pending work.
    try:
        await client.forward(_signal("end", token))
    except Exception:
        pass


async def _finish(state, token):
    item = state["pending"].get(token)
    if (item is None or not item["forward_closed"] or not state["response_closed"]
            or state["failed"]):
        return
    del state["pending"][token]
    task = asyncio.create_task(_end(item["client"], token))
    _END_TASKS.add(task)
    task.add_done_callback(_END_TASKS.discard)
    # Keep delivery owned if the request task is cancelled during cleanup.
    await asyncio.shield(task)


def track_generation(generation_type):
    """Decorate the exact native AsyncSchedulerClient.forward coroutine."""
    def decorate(forward):
        @wraps(forward)
        async def wrapped(client, batch, *args, **kwargs):
            state = _SCOPE.get()
            generation = isinstance(batch, generation_type) or (
                isinstance(batch, list) and bool(batch)
                and all(isinstance(req, generation_type) for req in batch)
            )
            if state is None or not generation:
                return await forward(client, batch, *args, **kwargs)
            token = uuid.uuid4().hex
            # Separate REQ sockets require this ACK to order begin before work.
            # Use the existing native client/timeout/error contract, no new IPC.
            await forward(client, _signal("begin", token))
            state["pending"][token] = {"client": client, "forward_closed": False}
            try:
                return await forward(client, batch, *args, **kwargs)
            finally:
                state["pending"][token]["forward_closed"] = True
                await _finish(state, token)
        return wrapped
    return decorate


class DiffusionDrainMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if (scope.get("type") != "http" or scope.get("method") != "POST"
                or scope.get("path") not in
                ("/v1/images/generations", "/v1/images/edits")):
            return await self.app(scope, receive, send)
        state = {"pending": {}, "response_closed": False, "failed": False}
        context = _SCOPE.set(state)
        try:
            return await self.app(scope, receive, send)
        except Exception:
            # The framework may send an outer unhandled-error response after
            # this middleware unwinds. Retain pending work until owner recovery,
            # rather than claiming the response has drained early.
            state["failed"] = True
            raise
        finally:
            state["response_closed"] = True
            try:
                for token in list(state["pending"]):
                    await _finish(state, token)
            finally:
                _SCOPE.reset(context)
