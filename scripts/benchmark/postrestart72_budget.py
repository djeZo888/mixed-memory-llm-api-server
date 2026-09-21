"""Closed actual72 campaign clocks; no lifecycle or transport operations.

The anchored host starts a separately bounded preparation ledger at maintenance.
Only explicit measured admission starts six hours. A successful admission grants
its requested HTTP duration; later campaign expiry never revokes that grant.
Historical CampaignBudget clocks are deliberately unchanged.
"""
from __future__ import annotations

import copy
import math
from pathlib import Path
import threading
import time

from .campaign import CampaignBudget, _budget_serialized
from .lifecycle import require


class PostrestartBudget(CampaignBudget):
    budget_seconds = 21600
    preparation_seconds = 7200

    def __init__(self, host, *, clock=time.time):
        self._mutex = threading.RLock()
        self.host, self.path, self.clock = host, Path(host.log_root) / 'budget.json', clock
        self._data = host.read_json('budget.json', missing=True)
        if self._data is not None:
            self._validate()

    def _validate(self, _depth=0):
        d = self._data
        number = lambda n: type(n) in (int, float) and math.isfinite(n) and n >= 0
        require(type(d) is dict and d.get('schema') == 2 and
                d.get('clock_policy') == 'postrestart72-measurement-admission-v1' and
                d.get('budget_seconds') == self.budget_seconds and
                d.get('preparation_seconds') == self.preparation_seconds and
                d.get('phase') in {'PREPARING', 'MEASURING', 'RESTORING', 'RESTORED', 'RESTORE_FAILED'} and
                number(d.get('preparation_started_at')) and number(d.get('last_seen_at')) and
                d['last_seen_at'] >= d['preparation_started_at'] and
                d.get('preparation_deadline_epoch') == d['preparation_started_at'] + self.preparation_seconds,
                'invalid_postrestart_budget_ledger')
        start = d.get('started_at')
        require((start is None and d.get('deadline_epoch') is None) or
                (number(start) and d['preparation_started_at'] <= start <= min(d['last_seen_at'], d['preparation_deadline_epoch']) and
                 d.get('deadline_epoch') == start + self.budget_seconds), 'invalid_postrestart_measurement_clock')
        require((d['phase'] != 'PREPARING' or start is None) and
                (d['phase'] != 'MEASURING' or start is not None), 'invalid_postrestart_budget_phase')
        restoring = d['phase'] in {'RESTORING', 'RESTORED', 'RESTORE_FAILED'}
        boundary = d.get('restoration_started_at')
        require((not restoring and boundary is None) or
                (restoring and number(boundary) and
                 (start if start is not None else d['preparation_started_at']) <= boundary <= d['last_seen_at']),
                'invalid_postrestart_restoration_boundary')

        if 'prior_segment' in d:
            prior, identity = d['prior_segment'], d.get('followup_identity')
            require(_depth < 2 and type(prior) is dict and prior.get('phase') in {'PREPARING', 'MEASURING'} and
                    type(identity) is dict and {'session_id', 'source_commit'} <= set(identity) and
                    all(isinstance(v, str) and bool(v) for v in identity.values()), 'invalid_postrestart_followup_ledger')
            try:
                self._data = prior
                self._validate(_depth + 1)
            finally:
                self._data = d
            require(d['preparation_started_at'] >= prior['last_seen_at'], 'invalid_postrestart_followup_boundary')

    def _save(self):
        self._validate()
        self.host.write_json('budget.json', self.data)

    @_budget_serialized
    def start(self, kind):
        require(self._data is None and kind == 'maintenance', 'budget_already_started')
        now = self.clock()
        require(type(now) in (int, float) and math.isfinite(now) and now >= 0, 'invalid_clock')
        self._data = {'schema': 2, 'clock_policy': 'postrestart72-measurement-admission-v1',
            'phase': 'PREPARING', 'budget_seconds': self.budget_seconds,
            'preparation_seconds': self.preparation_seconds, 'preparation_started_at': now,
            'preparation_deadline_epoch': now + self.preparation_seconds,
            'started_at': None, 'deadline_epoch': None, 'last_seen_at': now,
            'restoration_started_at': None}
        self._save()
        return self.data

    @_budget_serialized
    def checkpoint(self):
        require(self._data is not None, 'budget_not_started')
        now = self.clock()
        require(type(now) in (int, float) and math.isfinite(now) and now >= self._data['last_seen_at'],
                'wall_clock_regressed_stop_campaign')
        self._data['last_seen_at'] = now
        self._save()
        boundary = self._data['restoration_started_at']
        if boundary is None:
            boundary = now
        deadline = self._data['deadline_epoch']
        if deadline is None:
            deadline = self._data['preparation_deadline_epoch']
        return max(0, deadline - boundary)

    @_budget_serialized
    def request_timeout(self, requested_s=7200, *, measured=False):
        require(type(requested_s) in (int, float) and math.isfinite(requested_s) and
                0 < requested_s <= 7200 and type(measured) is bool, 'request_timeout_out_of_bounds')
        remaining = self.checkpoint()
        require(self._data['phase'] in {'PREPARING', 'MEASURING'} and remaining > 0, 'STOP_BUDGET')
        if measured and self._data['phase'] == 'PREPARING':
            now = self._data['last_seen_at']
            self._data.update(phase='MEASURING', started_at=now, deadline_epoch=now + self.budget_seconds)
            self._save()
        # A grant is independent from both preparation and admission deadlines.
        # http_transport starts the per-request duration at its actual dispatch.
        return requested_s

    @_budget_serialized
    def begin_followup(self, identity):
        """At most a reviewed remaining-pair and one bound extra-request segment."""
        self.checkpoint()
        previous_count, previous, sessions = 0, self._data, set()
        if 'followup_identity' in previous:
            sessions.add(previous['followup_identity']['session_id'])
        while 'prior_segment' in previous:
            previous_count += 1
            previous = previous['prior_segment']
            if 'followup_identity' in previous:
                sessions.add(previous['followup_identity']['session_id'])
        require(self._data['phase'] in {'PREPARING', 'MEASURING'} and previous_count < 2 and
                type(identity) is dict and {'session_id', 'source_commit'} <= set(identity) and
                identity['session_id'] not in sessions and
                all(isinstance(v, str) and bool(v) for v in identity.values()),
                'postrestart_followup_budget_forbidden')
        previous, now = self.data, self._data['last_seen_at']
        self._data = {'schema': 2, 'clock_policy': 'postrestart72-measurement-admission-v1',
            'phase': 'PREPARING', 'budget_seconds': self.budget_seconds,
            'preparation_seconds': self.preparation_seconds, 'preparation_started_at': now,
            'preparation_deadline_epoch': now + self.preparation_seconds,
            'started_at': None, 'deadline_epoch': None, 'last_seen_at': now,
            'restoration_started_at': None, 'prior_segment': previous,
            'followup_identity': copy.deepcopy(identity)}
        self._save()
        return self.data

    @_budget_serialized
    def begin_restoration(self):
        self.checkpoint()
        require(self._data['phase'] in {'PREPARING', 'MEASURING'}, 'restoration_already_started')
        self._data.update(phase='RESTORING', restoration_started_at=self._data['last_seen_at'])
        self._save()
