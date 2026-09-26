"""Bounded independent collectors; cached reads do no I/O or lifecycle work.

One daemon thread at most per registered collector. A timed-out/hung call keeps
its slot until it really returns; there is no replacement process/thread loop.
Late results are discarded. Callbacks must enforce their own external I/O budget
and output bound; a kernel hang cannot be cancelled by a Python deadline.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import math
import threading
import time

POLL_SECONDS = 5.0
DEADLINE_SECONDS = 2.0
STALE_SECONDS = 15.0
MAX_COLLECTORS = 17
MAX_SAMPLE_BYTES = 64 * 1024


def utc(epoch):
    return datetime.fromtimestamp(epoch, timezone.utc).isoformat()


@dataclass(frozen=True)
class Sample:
    value: dict | None = None
    observed_at: str | None = None
    observed_mono: float | None = None
    state: str = 'unknown'
    reason: str | None = 'not_observed'


class _Slot:
    def __init__(self, callback):
        self.callback = callback
        self.sample = Sample()
        self.thread = None
        self.started = None
        self.next_poll = 0.0
        self.lock = threading.Lock()


class BoundedObservers:
    def __init__(self, callbacks, *, clock=time.monotonic, wall=time.time,
                 poll_seconds=POLL_SECONDS, deadline_seconds=DEADLINE_SECONDS,
                 stale_seconds=STALE_SECONDS):
        if (not 1 <= len(callbacks) <= MAX_COLLECTORS or
                any(type(k) is not str or not k or len(k) > 96 for k in callbacks) or
                not all(callable(v) for v in callbacks.values()) or
                any(type(v) not in (int, float) or not math.isfinite(v) or v <= 0
                    for v in (poll_seconds, deadline_seconds, stale_seconds))):
            raise ValueError('invalid_observers')
        self.clock, self.wall = clock, wall
        self.poll_seconds, self.deadline_seconds, self.stale_seconds = poll_seconds, deadline_seconds, stale_seconds
        self._slots = {name: _Slot(callback) for name, callback in callbacks.items()}
        self._stop = threading.Event()
        self._poller = None
        self._lifetime = threading.Lock()

    def _collect(self, slot, started):
        try:
            value = slot.callback(self.deadline_seconds)
            if type(value) is not dict or len(json.dumps(value, allow_nan=False).encode()) > MAX_SAMPLE_BYTES:
                raise ValueError('invalid_sample')
            sample = Sample(copy.deepcopy(value), utc(self.wall()), self.clock(), 'ok', None)
        except Exception:
            sample = Sample(state='error', reason='collector_failed')
        ended = self.clock()
        with slot.lock:
            previous = slot.sample
            if ended - started >= self.deadline_seconds:
                slot.sample = Sample(previous.value, previous.observed_at, previous.observed_mono,
                                     'timeout', 'collector_timeout')
            elif sample.state == 'ok':
                slot.sample = sample
            else:
                slot.sample = Sample(previous.value, previous.observed_at, previous.observed_mono,
                                     sample.state, sample.reason)
            slot.started = None
            slot.next_poll = max(started + self.poll_seconds, ended)
            # Thread pointer stays until is_alive() becomes False. A new worker
            # cannot overlap this worker's completion or a hung child cleanup.

    def tick(self):
        """Nonblocking scheduling; tests may drive this with a fake clock."""
        if self._stop.is_set():
            return
        now = self.clock()
        for slot in self._slots.values():
            if not slot.lock.acquire(blocking=False):
                continue
            try:
                if slot.thread is not None and slot.thread.is_alive():
                    if slot.started is not None and now - slot.started >= self.deadline_seconds:
                        old = slot.sample
                        slot.sample = Sample(old.value, old.observed_at, old.observed_mono,
                                             'timeout', 'collector_timeout')
                    continue
                if now < slot.next_poll:
                    continue
                slot.started = now
                slot.thread = threading.Thread(target=self._collect, args=(slot, now),
                                               name='node-observer', daemon=True)
                slot.thread.start()
            finally:
                slot.lock.release()

    def read(self, name):
        """Pure cached projection; never starts or waits for a collector."""
        slot = self._slots[name]
        sample = slot.sample  # Immutable pointer publication, no external locks.
        age = None if sample.observed_mono is None else max(0, self.clock() - sample.observed_mono)
        freshness = 'unknown' if age is None else ('fresh' if age <= self.stale_seconds else 'stale')
        state, reason = sample.state, sample.reason
        if slot.started is not None and self.clock() - slot.started >= self.deadline_seconds:
            state, reason = 'timeout', 'collector_timeout'
        return {'value': copy.deepcopy(sample.value), 'state': state, 'reason': reason,
                'observed_at': sample.observed_at, 'age_ms': None if age is None else int(age * 1000),
                'freshness': freshness}

    def start(self):
        with self._lifetime:
            if self._stop.is_set() or self._poller is not None:
                return
            def poll():
                while not self._stop.is_set():
                    self.tick()
                    self._stop.wait(min(0.1, self.poll_seconds))
            self._poller = threading.Thread(target=poll, name='node-observer-poll', daemon=True)
            self._poller.start()

    def close(self):
        # No unbounded join: outstanding slots stay owned until completion.
        self._stop.set()

    def active_count(self):
        return sum(slot.thread is not None and slot.thread.is_alive() for slot in self._slots.values())
