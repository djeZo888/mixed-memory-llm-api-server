"""Candidate scheduler-local idle policy; importing this file activates nothing.

Native bindings must supply ALL activity counters and a level-triggered wait
covering every ingress/completion source. This policy has no torch, cache,
model, GPU, lifecycle, status-HTTP or process-management dependencies.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import time
from typing import Callable, Optional


GRACE_SECONDS = 600.0


@dataclass(frozen=True)
class Activity:
    """Unknown counters forbid blocking; ready is not evidence of idle."""

    active: Optional[int] = None
    queued: Optional[int] = None
    streaming: Optional[int] = None
    pending_async: Optional[int] = None

    def __post_init__(self):
        for value in self.values:
            if value is not None and (type(value) is not int or value < 0):
                raise ValueError("invalid_activity_counter")

    @property
    def values(self):
        return (self.active, self.queued, self.streaming, self.pending_async)

    @property
    def has_work(self):
        return any(value is not None and value > 0 for value in self.values)

    @property
    def confirmed_idle(self):
        return all(value == 0 for value in self.values)


class AdaptiveIdle:
    """One instance per native scheduler, owned by its scheduler thread.

    Record real request admission AND final completion (including warmup).
    Positive live counters also renew grace, preventing an active/queued/streaming
    or asynchronous workload from sleeping. Request metadata/status/metrics and
    bare event wakeups never renew grace. All known-zero counters are necessary,
    but a correct native binding must also fence/check any asynchronous producer
    and register its notification source with the level-triggered waiter.
    """

    def __init__(self, *, clock: Callable[[], float] = time.monotonic):
        self._clock = clock
        self._last_work = self._now()  # Startup gets the full initial grace.

    def _now(self):
        value = self._clock()
        if type(value) not in (float, int) or not math.isfinite(value):
            raise ValueError("invalid_monotonic_clock")
        return float(value)

    def record_real_work(self):
        """Called for this scheduler's real work, especially final completion."""
        now = self._now()
        if now < self._last_work:
            raise ValueError("monotonic_clock_regressed")
        self._last_work = now

    def maybe_wait(self, activity: Activity, wait_readable: Callable[[], object]):
        """Return whether an indefinite event wait was entered.

        ``wait_readable`` MUST remain readable while an event/request is pending;
        it must not clear/drain an event between the idle check and wait. This
        avoids lost wakes when a request arrives at the check/wait boundary.
        The callback may return for management traffic or a spurious wake. Its
        return is not real work: classify and record real work in the scheduler.
        No timed polling, fixed busy sleeps or cache cleanup occurs here.
        """
        if not isinstance(activity, Activity):
            raise ValueError("invalid_activity_snapshot")
        now = self._now()
        if now < self._last_work:
            raise ValueError("monotonic_clock_regressed")
        if activity.has_work:
            self._last_work = now
            return False
        if not activity.confirmed_idle or now - self._last_work < GRACE_SECONDS:
            return False
        wait_readable()
        return True

    def snapshot(self):
        """Read-only policy state; observation cannot keep a scheduler busy."""
        return {"grace_seconds": GRACE_SECONDS,
                "last_real_work_monotonic": self._last_work}
