"""Idle binding for the pinned single-GPU, monolithic diffusion scheduler.

All accepted generation, generator draining and reply work is synchronous in
this scheduler. The only asynchronous ingress is its level-triggered ROUTER
socket, including acknowledged native HTTP drain signals. Those retain pending
work through postprocessing and final ASGI delivery. Disaggregated/multi-rank
paths have other queues and are refused here.
This module never touches model residency, torch or the allocator cache.
"""
from __future__ import annotations

import re

from .adaptive_idle import Activity, AdaptiveIdle


class DiffusionIdleBinding:
    def __init__(self, scheduler, generation_type, *, clock=None):
        args = scheduler.server_args
        if (args.num_gpus != 1 or args.dp_size != 1 or args.sp_degree != 1
                or args.tp_size != 1 or args.enable_cfg_parallel
                or scheduler._disagg_role.value != "monolithic"
                or scheduler._disagg_mode or scheduler.receiver is None):
            raise RuntimeError("adaptive_diffusion_unsupported_execution_mode")
        # These exact pinned fields own background producers in disaggregation.
        # Unknown/missing state is not evidence of an idle scheduler.
        for field in ("_pool_work_pull", "_pool_result_push", "_transfer_manager",
                      "_transfer_stream", "_rdma_push_queue", "_rdma_push_thread",
                      "_rdma_push_zmq", "_compute_ready_queue", "_recv_prefetch_thread"):
            if not hasattr(scheduler, field) or getattr(scheduler, field) is not None:
                raise RuntimeError("adaptive_diffusion_async_state_not_supported")
        self.scheduler = scheduler
        self.generation_type = generation_type
        self.policy = AdaptiveIdle() if clock is None else AdaptiveIdle(clock=clock)
        self._dispatching = False
        self._real_dispatch = False
        self._pending_drains = set()

    def process_signals(self, requests, acknowledge):
        remaining = []
        for identity, req in requests:
            if type(req) is not dict or "__llmctl_adaptive_drain__" not in req:
                remaining.append((identity, req))
                continue
            expected = {"__llmctl_adaptive_drain__", "event", "token"}
            if req.get("event") == "end":
                expected.add("admitted")
            valid = (set(req) == expected
                     and (req.get("event") != "end" or type(req.get("admitted")) is bool)
                     and type(req["__llmctl_adaptive_drain__"]) is int
                     and req["__llmctl_adaptive_drain__"] == 1
                     and req["event"] in ("begin", "end")
                     and isinstance(req["token"], str)
                     and re.fullmatch("[0-9a-f]{32}", req["token"]) is not None)
            if not valid:
                raise RuntimeError("adaptive_diffusion_invalid_drain_signal")
            if req["event"] == "begin":
                self._pending_drains.add(req["token"])
            elif req["token"] in self._pending_drains:
                self._pending_drains.remove(req["token"])
                if req["admitted"]:
                    self.policy.record_real_work()
            acknowledge(identity)
        return remaining

    def _is_generation(self, req):
        return isinstance(req, self.generation_type) or (
            isinstance(req, list) and bool(req)
            and all(isinstance(item, self.generation_type) for item in req)
        )

    def maybe_wait(self):
        """Only called at the top of the event loop, outside any dispatch.

        A passive queued request forbids waiting but does not renew grace.
        No queue or socket is drained between the empty check and poll(): a
        request arriving at that boundary stays readable, so no wake is lost.
        """
        queue = self.scheduler.waiting_queue
        real_queued = sum(self._is_generation(item[1]) for item in queue)
        if self._dispatching and not self._real_dispatch:
            return False
        # Reservation/drain ownership inhibits waiting, but is not itself work.
        if self._pending_drains and not self._real_dispatch and not real_queued:
            return False
        activity = Activity(active=int(self._real_dispatch), queued=real_queued,
                            streaming=int(self._real_dispatch),
                            pending_async=0)
        if queue and not real_queued:
            return False
        return self.policy.maybe_wait(activity, self.scheduler._poller.poll)

    def begin(self, items):
        if self._dispatching:
            raise RuntimeError("adaptive_diffusion_nested_dispatch")
        self._dispatching = True
        self._real_dispatch = any(self._is_generation(item[1]) for item in items)
        if self._real_dispatch:
            self.policy.record_real_work()

    def complete(self):
        """After final generator close/reply/error drain, not forward admission."""
        if not self._dispatching:
            raise RuntimeError("adaptive_diffusion_completion_without_dispatch")
        if self._real_dispatch:
            self.policy.record_real_work()
        self._real_dispatch = False
        self._dispatching = False
