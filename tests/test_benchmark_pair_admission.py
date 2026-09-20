"""Future benchmark refusal for fixed-slot production; synthetic/local only."""
from __future__ import annotations

import copy
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from tests.test_benchmark_lifecycle import snapshot
from tests.test_benchmark_owner import Fixture
from benchmark.lifecycle import (PlanError, plan_campaign,
                                 require_singleton_manager_state, validate_snapshot)
from benchmark.owner import OwnerError


class PairAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="benchmark-pair-refusal-")
        self.addCleanup(self.temp.cleanup)
        self.fixture = Fixture(Path(self.temp.name).resolve())
        self.owner = self.fixture.build()
        self.addCleanup(self.release_fixture_lease)

    def release_fixture_lease(self):
        # Local fixture cleanup only; production recovery retains its owner.
        if self.owner.lease_context is not None:
            self.owner.lease_context.__exit__(None, None, None)
            self.owner.lease_context = self.owner.lease = None

    def test_raw_pair_rejected_before_lossy_capture_or_maintenance(self):
        for slots in ({}, {"glm": {"desired": "stopped"}, "qwen": {"desired": "stopped"}},
                      {"glm": {"desired": "running"}, "qwen": {"desired": "running"}}):
            with self.subTest(slots=slots):
                self.fixture = Fixture(Path(self.temp.name).resolve())
                self.owner = self.fixture.build()
                # The callback would otherwise return a valid singleton snapshot,
                # matching the host's intentionally lossy status projection.
                raw = {**snapshot()["manager"], "schema_version": 3, "slots": slots}
                capture = Mock(side_effect=AssertionError("pair reached singleton capture"))
                self.owner.host = replace(self.owner.host, capture=capture)
                with patch.object(self.fixture, "read_state", return_value=raw):
                    with self.assertRaisesRegex(OwnerError, "^benchmark_pair_state_unsupported$"):
                        self.owner.begin()
                capture.assert_not_called()
                self.assertEqual(self.owner.phase, "FAILED_BEFORE_MUTATION")
                self.assertIsNone(self.owner.lease)
                self.assertIsNone(self.owner.original)
                self.assertFalse(self.owner.budget_started)
                self.assertFalse(any(e[0] in {"manager", "control", "create", "start", "stop", "remove"}
                                     for e in self.fixture.events))
                self.assertIn("benchmark_pair_state_unsupported", self.owner.errors)
                self.assertEqual(raw["slots"], slots)

    def test_disguised_pair_unknown_schema_and_malformed_state_fail_closed(self):
        for state in ({"schema_version": 2, "slots": {}}, {"schema_version": 3},
                      {"slots": None}, {"schema_version": 4}, {"schema_version": True},
                      {"schema_version": 2.0}, {}, [], None):
            with self.subTest(state=state), self.assertRaises(PlanError):
                require_singleton_manager_state(state)
        require_singleton_manager_state({"schema_version": 2})

    def test_pair_snapshot_and_dry_run_refused_even_with_legacy_fields(self):
        for pair_fields in ({"schema_version": 3}, {"slots": {}},
                            {"schema_version": 2, "slots": {"glm": {}, "qwen": {}}}):
            candidate = snapshot()
            candidate["manager"].update(pair_fields)
            original = copy.deepcopy(candidate)
            for action in (validate_snapshot, lambda value: plan_campaign(value, "pair-refusal")):
                with self.subTest(fields=pair_fields), self.assertRaisesRegex(
                        PlanError, "benchmark_pair_state_unsupported"):
                    action(candidate)
            self.assertEqual(candidate, original)

    def test_recovery_never_restores_singleton_over_pair_state(self):
        self.owner.begin()
        previous = len(self.fixture.events)
        pair = {"schema_version": 3, "slots": {"glm": {}, "qwen": {}}}
        with patch.object(self.fixture, "read_state", return_value=pair):
            with self.assertRaisesRegex(OwnerError, "restoration_failed_preserve_owner_and_ledger"):
                self.owner.restore()
        self.assertEqual(self.owner.phase, "RECOVERY_REQUIRED")
        self.assertIn("benchmark_pair_state_unsupported", self.owner.errors)
        self.owner.lease.validate()
        self.assertFalse(any(e[0] in {"manager", "control", "create", "start", "stop", "remove"}
                             for e in self.fixture.events[previous:]))


if __name__ == "__main__":
    unittest.main()
