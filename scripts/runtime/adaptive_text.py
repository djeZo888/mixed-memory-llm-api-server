"""Binding for the pinned, non-overlap, single-rank Qwen scheduler only.

Native is_fully_idle owns batch, chunk, grammar and async queue accounting.
The source overlay records admission and final result/stream handoff, not just
socket arrival. Both ingress sockets remain level-triggered across idle checks.
"""
from __future__ import annotations

import re

import zmq

from .adaptive_idle import Activity, AdaptiveIdle


class TextAdaptiveIdle:
    def __init__(self, scheduler, is_health_check, drain_type, *, clock=None):
        args = scheduler.server_args
        expected = {"tp_size": 1, "pp_size": 1, "dp_size": 1,
                    "disable_overlap_schedule": True, "disaggregation_mode": "null"}
        if any(type(getattr(args, k, None)) is not type(v) or getattr(args, k) != v
               for k, v in expected.items()):
            raise RuntimeError("adaptive_text_unsupported_mode")
        # These producers require independent completion/event contracts. They
        # are all disabled in the closed pair launcher; never silently enable.
        if any(getattr(scheduler, name, True) for name in (
                "enable_overlap", "enable_pdmux", "enable_hisparse",
                "enable_hierarchical_cache", "enable_unified_memory")):
            raise RuntimeError("adaptive_text_unsupported_async_mode")
        if any(getattr(scheduler, name, True) is not None for name in (
                "rust_server", "input_blocker", "recv_skipper", "mm_receiver",
                "external_corpus_manager", "lora_drainer", "dllm_config")):
            raise RuntimeError("adaptive_text_uncovered_producer")
        self.scheduler = scheduler
        self.is_health_check = is_health_check
        self.drain_type = drain_type
        self.pending_drains = set()
        self.policy = AdaptiveIdle(**({"clock": clock} if clock is not None else {}))
        self.poller = zmq.Poller()
        for socket in (scheduler.ipc_channels.recv_from_tokenizer,
                       scheduler.ipc_channels.recv_from_rpc):
            if socket is None:
                raise RuntimeError("adaptive_text_missing_ingress")
            self.poller.register(socket, zmq.POLLIN)
        self._was_busy = False

    def record_real_work(self):
        self.policy.record_real_work()

    def consume_notifications(self, requests):
        """Private typed IPC; preserve ordering and every original request."""
        native = []
        for request in requests:
            if not isinstance(request, self.drain_type):
                native.append(request)
                continue
            if (type(request.admitted) is not bool
                    or (request.event == "begin" and request.admitted)
                    or request.event not in ("begin", "end")
                    or not isinstance(request.token, str)
                    or not re.fullmatch("[0-9a-f]{32}", request.token)):
                raise RuntimeError("adaptive_text_invalid_drain_notification")
            if request.event == "begin":
                if request.token in self.pending_drains:
                    raise RuntimeError("adaptive_text_duplicate_drain_begin")
                self.pending_drains.add(request.token)
            else:
                if request.token not in self.pending_drains:
                    raise RuntimeError("adaptive_text_unmatched_drain_end")
                self.pending_drains.remove(request.token)
                if request.admitted:
                    self.record_real_work()
        return native

    def _real_work_pending(self):
        s = self.scheduler
        requests = list(s.waiting_queue)
        for batch in (s.running_batch, s.last_batch):
            if batch is not None and not batch.is_empty():
                requests.extend(batch.reqs)
        if s.chunked_req is not None:
            requests.append(s.chunked_req)
        # Grammar futures retain their real generation Req in this queue;
        # native health requests have no grammar or asynchronous compilation.
        return bool(s.grammar_manager.grammar_queue) or any(
            not self.is_health_check(req) for req in requests
        )

    def maybe_wait(self):
        # Keep the full native idle predicate as the safety authority. Its
        # scheduler-local queues alone cannot prove downstream stream drain.
        futures = self.scheduler.grammar_manager._adaptive_pending_futures
        completed = {future for future in futures if future.done()}
        if completed:
            futures.difference_update(completed)
            self.record_real_work()
        if futures:
            return False  # Includes compiler jobs surviving abort/timeout.
        idle = self.scheduler.is_fully_idle()
        if type(idle) is not bool:
            return False
        real_pending = self._real_work_pending()
        if real_pending:
            self._was_busy = True
            return self.policy.maybe_wait(Activity(1, 0, 0, 0), self.poller.poll)
        if self._was_busy:
            self.record_real_work()  # Final async grammar rejection/abort.
            self._was_busy = False
        if not idle or self.pending_drains:
            # Health-only native work and pending transport acknowledgments
            # prevent sleep without fabricating another real-work completion.
            return False
        if self.scheduler.flush_wrapper._pending is not None:
            return False
        if self.scheduler.gracefully_exit:
            return False
        return self.policy.maybe_wait(Activity(0, 0, 0, 0), self.poller.poll)
