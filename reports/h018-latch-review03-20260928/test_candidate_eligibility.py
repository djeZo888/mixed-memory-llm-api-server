"""Independent narrow review fixture. Pass the frozen candidate owner path.

python3 -B reports/h018-latch-review03-20260928/test_candidate_eligibility.py \
    ../input/candidate/owner.py

Expected: forbidden initial unknowns cannot be rescued by a second fresh read.
The reviewed 5853614 candidate fails these checks; no production code is edited.
"""
import contextlib
import copy
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

import test_latch_contract as baseline

CANDIDATE_PATH = Path(sys.argv.pop(1)).resolve()
spec = importlib.util.spec_from_file_location('frozen_candidate', CANDIDATE_PATH)
candidate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(candidate)


class TransitionBinding(baseline.Binding):
    def __init__(self, first):
        self.first, self.calls = first, 0

    def read_json(self, *args, **kwargs):
        self.calls += 1
        if self.calls == 1:
            if isinstance(self.first, Exception):
                raise self.first
            return copy.deepcopy(self.first)
        return baseline.healthy()


class Eligibility(unittest.TestCase):
    def check_forbidden(self, first):
        binding = TransitionBinding(first)
        original = baseline.policy.read_latch_status

        @contextlib.contextmanager
        def lease(**kwargs):
            self.assertEqual(kwargs, {'blocking': False})
            yield types.SimpleNamespace(validate=lambda: None)

        with patch.object(baseline.RegisteredStorageBinding, 'read_registered', return_value=binding), \
             patch.object(baseline.policy, 'read_latch_status', side_effect=lambda *a, **k:
                 original(*a, **k, wall=lambda: baseline.EPOCH)):
            with self.assertRaises(Exception, msg='Forbidden initial evidence was accepted after readback'):
                candidate.latch(types.SimpleNamespace(acquire_lease=lease), baseline.BOOT)

    def test_initial_unreadable_then_fresh_must_refuse(self):
        self.check_forbidden(OSError('synthetic-unreadable'))

    def test_initial_corrupt_then_fresh_must_refuse(self):
        self.check_forbidden({'invalid': True})

    def test_initial_missing_proof_then_fresh_must_refuse(self):
        self.check_forbidden({'schema_version': 1, 'targets': {}})

    def test_initial_wrongboot_then_fresh_must_refuse(self):
        state = baseline.healthy()
        state['validated'][baseline.GPU]['boot_id'] = baseline.OTHER_BOOT
        self.check_forbidden(state)

    def test_initial_future_proof_then_fresh_must_refuse(self):
        state = baseline.healthy()
        state['validated'][baseline.GPU]['observed_at'] = baseline.stamp(30)
        self.check_forbidden(state)

    def test_initial_positive_then_fresh_must_refuse(self):
        self.check_forbidden(baseline.Contract().positive().export_state())


if __name__ == '__main__':
    unittest.main(verbosity=2)
