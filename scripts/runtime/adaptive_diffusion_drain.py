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
_OWNED_TASKS = set()
_CURRENT_ITEM = ContextVar("adaptive_diffusion_current_item", default=None)
_SIGNAL_KEY = "__llmctl_adaptive_drain__"


def _signal(event, token, admitted=None):
    value = {_SIGNAL_KEY: 1, "event": event, "token": token}
    if event == "end":
        value["admitted"] = admitted
    return value


def mark_submitted(client, batch):
    """Called only after the exact native socket.send successfully completes."""
    tracked = _CURRENT_ITEM.get()
    if tracked is not None and tracked[0] is client and tracked[1] is batch:
        tracked[2]["admitted"] = True


async def _end(client, token, admitted):
    # An undelivered end leaves the scheduler conservatively busy. This is a
    # lifecycle failure, never a timeout-based licence to clear pending work.
    try:
        await client.forward(_signal("end", token, admitted))
    except Exception:
        pass


def _own(coroutine):
    task = asyncio.create_task(coroutine)
    _OWNED_TASKS.add(task)
    def settled(done):
        _OWNED_TASKS.discard(done)
        if not done.cancelled():
            done.exception()  # Retrieve failures even if its HTTP waiter was cancelled.
    task.add_done_callback(settled)
    return task


async def _finish(state, token):
    item = state["pending"].get(token)
    if (item is None or not item["begin_ack"] or not item["forward_closed"]
            or not state["response_closed"]):
        return
    del state["pending"][token]
    # Keep delivery owned if the request task is cancelled during cleanup.
    await asyncio.shield(_own(_end(item["client"], token, item["admitted"])))


async def _begin(forward, client, state, token, item):
    await forward(client, _signal("begin", token))
    item["begin_ack"] = True
    # Cancellation may have already closed the HTTP scope while ACK was in flight.
    await _finish(state, token)


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
            item = {"client": client, "forward_closed": False, "begin_ack": False, "admitted": False}
            state["pending"][token] = item
            begin_task = _own(_begin(forward, client, state, token, item))
            try:
                await asyncio.shield(begin_task)
                context = _CURRENT_ITEM.set((client, batch, item))
                try:
                    return await forward(client, batch, *args, **kwargs)
                finally:
                    _CURRENT_ITEM.reset(context)
            finally:
                item["forward_closed"] = True
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
        state = {"pending": {}, "response_closed": False}
        context = _SCOPE.set(state)
        try:
            return await self.app(scope, receive, send)
        finally:
            state["response_closed"] = True
            try:
                for token in list(state["pending"]):
                    await _finish(state, token)
            finally:
                _SCOPE.reset(context)
