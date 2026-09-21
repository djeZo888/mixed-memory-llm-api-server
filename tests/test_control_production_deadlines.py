"""Synthetic production-budget regression; no host I/O or wall-clock sleeps."""

from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from control import adapter
from control.core import Application, _Ticket
from control.journal import Journal
from control.protocol import ControlError
from test_control_core_guards import ready_raw
from test_control_journal import MemoryStore
from test_control_receipts import fixture_lease


class ProductionDeadlineTests(unittest.TestCase):
    def setUp(self):
        self.now = 100.0
        self.backend = Mock()
        self.session = self.backend.open.return_value
        self.session.observe.return_value = ready_raw()
        self.session.catalog.return_value = []
        self.store = MemoryStore()
        self.clock = patch("control.protocol.time.monotonic", side_effect=lambda: self.now)
        self.clock.start()
        self.addCleanup(self.clock.stop)

    def advance(self, seconds, deadline):
        self.now += seconds
        deadline.remaining()

    def application(self, production=True):
        # Execute the real production factory/Application with inert backend,
        # memory journal and no worker; invoke synchronous paths deterministically.
        with patch("control.core.threading.Thread"), \
                patch.object(adapter, "ProductionBackend", return_value=self.backend), \
                patch.object(adapter, "ManagerJournalStore", return_value=self.store):
            if production:
                return adapter.production_application("unused-fixture-configs", b"inert-fixture-key")
            return Application(self.backend, Journal(self.store))

    def ticket(self, expires_in=60, expected_generation=1):
        ticket = _Ticket("stop", {"expected_active": None,
                                  "expected_generation": expected_generation}, "fixture-stop")
        ticket.expires_at = self.now + expires_in
        return ticket

    def prepare_admission(self, seconds=11):
        def check(lease, deadline):
            self.advance(seconds, deadline)
        def observe(deadline):
            self.advance(seconds, deadline)
            return {"selected": None, "desired": "stopped", "container": None,
                    "container_running": False, "observed": "stopped",
                    "observation_available": True, "storage_available": True,
                    "state_persisted": True}
        self.session.check_admission.side_effect = check
        self.session.observe.side_effect = observe

    def test_factory_explicitly_selects_sixty_seconds_and_keeps_transition_budget(self):
        production, generic = self.application(), self.application(production=False)
        self.assertEqual((production.read_seconds, production.admission_seconds), (60, 60))
        self.assertEqual((generic.read_seconds, generic.admission_seconds), (10, 10))
        self.assertEqual(production.transition_seconds, generic.transition_seconds)
        self.assertEqual(production.transition_seconds, 8000)
        with patch("control.core._Ticket") as ticket_type:
            production._submit("stop", {"expected_active": None, "expected_generation": 0}, "fixture")
        ticket_type.return_value.wait.assert_called_once_with(60)

    def test_observation_and_catalog_over_ten_seconds_share_production_read_budget(self):
        def observe(deadline):
            self.advance(11, deadline)
            return ready_raw()
        def catalog(deadline):
            self.advance(11, deadline)
            return []
        self.session.observe.side_effect = observe
        self.session.catalog.side_effect = catalog
        for production in (False, True):
            with self.subTest(production=production):
                app = self.application(production)
                with patch.object(app, "_try_refresh"):
                    status, result = app._read(catalog=True)
                self.assertEqual(status, 200)
                if production:
                    self.assertEqual(result["observed"], "ready")
                    self.assertTrue(result["observation_available"])
                    self.assertEqual(self.session.observe.call_args.args,
                                     self.session.catalog.call_args.args)
                else:
                    self.assertEqual(result["failure_code"], "deadline_exceeded")
                    self.assertFalse(result["observation_available"])

    def test_production_read_still_expires_at_sixty_seconds(self):
        self.session.observe.side_effect = lambda deadline: self.advance(60, deadline)
        app = self.application()
        with patch.object(app, "_try_refresh"):
            status, result = app._read()
        self.assertEqual(status, 200)
        self.assertEqual(result["failure_code"], "deadline_exceeded")
        self.assertFalse(result["observation_available"])

    def test_admission_over_ten_seconds_completes_with_production_budget(self):
        self.prepare_admission()
        app, ticket = self.application(), self.ticket()
        with fixture_lease(blocking=False) as lease:
            app._transition(ticket, lease)
        self.assertEqual(ticket.result[0], 202)
        self.assertTrue(ticket.result[1]["state_persisted"])
        self.session.check_admission.assert_called_once()
        self.assertIs(self.session.check_admission.call_args.args[0], lease)
        self.assertEqual(self.session.check_admission.call_args.args[1].end, 160)
        self.session.stop.assert_called_once()
        self.assertEqual(next(iter(self.store.value["entries"].values()))["status"], "succeeded")

    def test_admission_retains_ticket_expiry_and_finite_cap(self):
        for expires_in, seconds in ((10, 11), (60, 31)):
            with self.subTest(expires_in=expires_in):
                self.prepare_admission(seconds)
                app, ticket = self.application(), self.ticket(expires_in)
                with fixture_lease(blocking=False) as lease, \
                        self.assertRaisesRegex(ControlError, "^deadline_exceeded$"):
                    app._transition(ticket, lease)
                self.assertIsNone(ticket.result)
                self.session.stop.assert_not_called()

    def test_slow_receipt_past_production_expiry_never_mutates(self):
        self.prepare_admission()
        original_write = self.store.write
        def write(value):
            if any(entry["status"] == "pending" for entry in value["entries"].values()):
                self.now += 61
            original_write(value)
        self.store.write = write
        app, ticket = self.application(), self.ticket()
        with fixture_lease(blocking=False) as lease:
            app._transition(ticket, lease)
        self.assertTrue(ticket.cancelled)
        self.assertIsNone(ticket.result)
        self.session.stop.assert_not_called()
        operation = next(iter(self.store.value["entries"].values()))
        self.assertEqual((operation["status"], operation["failure_code"]),
                         ("interrupted", "admission_timeout"))

    def test_longer_admission_still_uses_fresh_generation_cas(self):
        self.prepare_admission()
        app, ticket = self.application(), self.ticket(expected_generation=0)
        with fixture_lease(blocking=False) as lease, \
                self.assertRaisesRegex(ControlError, "^stale_state$"):
            app._transition(ticket, lease)
        self.session.observe.assert_called_once()
        self.assertIsNone(ticket.result)
        self.session.stop.assert_not_called()


if __name__ == "__main__":
    unittest.main()
