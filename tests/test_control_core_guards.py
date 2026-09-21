"""Pure request/projection guards; no production adapter or inference execution."""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from control.adapter import production_application  # noqa: E402
from control.core import (  # noqa: E402
    Application, SAFE_CODES, digest, observation, public_operation,
    public_outcome, safe_error,
)
from control.protocol import ControlError, Deadline  # noqa: E402


def ready_raw(**changes):
    raw = {
        "selected": "alpha", "desired": "running", "observed": "ready",
        "container_running": True, "observation_available": True,
        "storage_available": True, "state_persisted": True,
        "container": {"instance": "ordinary-server", "deployment": "alpha",
                      "id": "immutable-container-1", "generation": "start-1"},
        "ready_proof": {name: True for name in (
            "trusted_identity", "safe_network", "authenticated_model", "runtime_health")},
    }
    raw.update(changes)
    return raw


def valid_request(kind="switch", **changes):
    value = {"expected_active": None, "expected_generation": 0}
    if kind == "switch":
        value.update(deployment_id="alpha", allow_interrupt=False)
    value.update(changes)
    return value


def operation():
    return {
        "id": "a" * 32, "kind": "switch", "target": "alpha", "status": "failed",
        "created_at": 1, "updated_at": 3, "deadline": 10, "completed_at": 3,
        "generation": 2, "active_identity": None, "failure_code": "start_failed",
        "state_persisted": True, "poll_url": "/control/v1/operations/" + "a" * 32,
        "request_digest": "b" * 64, "idempotency_digest": "c" * 64,
        "observed": {"selected": "alpha", "desired": "running", "observed": "failed",
                     "container_running": False, "active_identity": None,
                     "generation": 2, "state_persisted": True, "observed_at": 3},
    }


class RequestGuards(unittest.TestCase):
    def parse(self, value, kind="switch", key="opaque-request"):
        return Application._request(kind, json.dumps(value).encode(), {
            "content-type": "application/json", "idempotency-key": key,
        })

    def assert_invalid(self, value, kind="switch", key="opaque-request"):
        with self.assertRaises(ControlError) as rejected:
            self.parse(value, kind, key)
        self.assertEqual(rejected.exception.code, "invalid_request")
        self.assertEqual(rejected.exception.status, 400)

    def test_valid_switch_and_stop_exact_schemas(self):
        for kind in ("switch", "stop"):
            with self.subTest(kind=kind):
                value = valid_request(kind)
                self.assertEqual(self.parse(value, kind), (value, "opaque-request"))

    def test_paths_commands_flags_images_and_profiles_rejected(self):
        for identifier in ("/data/models/private", "../../etc/passwd", "alpha/beta",
                           "alpha\\beta", "file:///private", "alpha;id", "$(id)",
                           "--runtime=other", "alpha\ncommand", "alpha%2fprivate", "alpha?port=1"):
            with self.subTest(identifier=identifier):
                self.assert_invalid(valid_request(deployment_id=identifier))

    def test_arbitrary_configuration_fields_rejected(self):
        for name in ("path", "command", "args", "flags", "environment", "env", "image",
                     "config", "profile", "runtime", "port", "host", "bootstrap", "force"):
            with self.subTest(name=name):
                self.assert_invalid(valid_request(**{name: "private-input"}))
        self.assert_invalid(valid_request("stop", deployment_id="alpha"), "stop")
        self.assert_invalid(valid_request("stop", allow_interrupt=True), "stop")

    def test_missing_required_fields_rejected(self):
        for kind in ("switch", "stop"):
            for name in valid_request(kind):
                with self.subTest(kind=kind, name=name):
                    value = valid_request(kind)
                    del value[name]
                    self.assert_invalid(value, kind)

    def test_identifier_bounds_and_types(self):
        self.assertEqual(self.parse(valid_request(deployment_id="a" * 96))[0]["deployment_id"], "a" * 96)
        for identifier in ("", "a" * 97, 1, True, None, [], {}, "αlpha"):
            with self.subTest(identifier=identifier):
                self.assert_invalid(valid_request(deployment_id=identifier))

    def test_expected_generation_is_bounded_integer_not_bool(self):
        for generation in (True, False, -1, 2**63, 1.5, "0", None, [], {}):
            with self.subTest(generation=generation):
                self.assert_invalid(valid_request(expected_generation=generation))
        self.assertEqual(self.parse(valid_request(expected_generation=2**63 - 1))[0]["expected_generation"], 2**63 - 1)

    def test_expected_active_is_opaque_identity_or_null(self):
        self.assertEqual(self.parse(valid_request(expected_active="f" * 64))[0]["expected_active"], "f" * 64)
        for active in ("alpha", "a" * 63, "a" * 65, "A" * 64, 0, False, [], {}):
            with self.subTest(active=active):
                self.assert_invalid(valid_request(expected_active=active))

    def test_interruption_acknowledgment_is_exact_boolean(self):
        for acknowledgment in (None, 0, 1, "true", "false", [], {}):
            with self.subTest(acknowledgment=acknowledgment):
                self.assert_invalid(valid_request(allow_interrupt=acknowledgment))

    def test_idempotency_is_bounded_opaque_header(self):
        self.assertEqual(self.parse(valid_request(), key="k" * 128)[1], "k" * 128)
        for key in ("", "k" * 129, "a/b", "../private", "a b", "a\tb", "a\nb", "κ"):
            with self.subTest(key=key):
                self.assert_invalid(valid_request(), key=key)

    def test_invalid_json_never_becomes_request(self):
        headers = {"content-type": "application/json", "idempotency-key": "opaque"}
        for body in (b"{", b"{} trailing", b"null", b"[]", b"\xff",
                     b'{"expected_active":null,"expected_active":null}',
                     b'{"expected_generation":NaN}', b" " * 4097,
                     b"[" * 1500 + b"0" + b"]" * 1500):
            with self.subTest(body=body[:30]):
                with self.assertRaises(ControlError) as rejected:
                    Application._request("switch", body, headers)
                self.assertEqual(rejected.exception.code, "invalid_request")

    def test_json_content_type_required(self):
        for content_type in ("", "text/plain", "application/octet-stream"):
            with self.subTest(content_type=content_type), self.assertRaises(ControlError):
                Application._request("switch", json.dumps(valid_request()).encode(), {
                    "content-type": content_type, "idempotency-key": "opaque",
                })

    def test_canonical_request_digest_ignores_field_order(self):
        value = valid_request()
        reversed_value = dict(reversed(tuple(value.items())))
        parsed, _ = self.parse(value)
        reversed_parsed, _ = self.parse(reversed_value)
        self.assertEqual(digest(["switch", parsed]), digest(["switch", reversed_parsed]))
        self.assertNotEqual(digest(["switch", parsed]), digest(["stop", parsed]))
        self.assertNotEqual(digest(["switch", parsed]), digest(["switch", {**parsed, "allow_interrupt": True}]))


class DeadlineBudgetGuards(unittest.TestCase):
    def application(self):
        backend, journal = Mock(), Mock()
        journal.read.return_value = {"schema": 1, "generation": 0,
                                     "fingerprint": None, "entries": {}}
        backend.open.return_value.observe.return_value = ready_raw()
        backend.open.return_value.catalog.return_value = []
        with patch("control.core.threading.Thread"):
            return Application(backend, journal)

    def test_default_read_and_catalog_share_one_ten_second_deadline(self):
        app = self.application()
        session = app.backend.open.return_value
        with patch.object(app, "_try_refresh"), \
                patch("control.protocol.time.monotonic", return_value=100):
            status, snapshot = app._read(catalog=True)
        self.assertEqual(status, 200)
        self.assertEqual(snapshot["observed"], "ready")
        deadline = session.observe.call_args.args[0]
        self.assertEqual(deadline.end, 110)
        session.catalog.assert_called_once_with(deadline)

    def test_default_admission_wait_is_ten_seconds(self):
        app = self.application()
        with patch.object(app, "_replay", return_value=None), \
                patch("control.core._Ticket") as ticket_type:
            app._submit("stop", valid_request("stop"), "opaque-request")
        ticket_type.return_value.wait.assert_called_once_with(10)
        self.assertEqual(app.transition_seconds, 8000)

    def test_admission_check_keeps_ticket_remaining_deadline(self):
        app = self.application()
        session = app.backend.open.return_value
        session.check_admission.side_effect = ControlError("deadline_exceeded")
        lease = object()
        for expires_at, expected_end in ((None, 110), (103, 103)):
            with self.subTest(expires_at=expires_at), \
                    patch.object(app, "_get_session", return_value=(session, False)), \
                    patch("control.protocol.time.monotonic", return_value=100):
                with self.assertRaises(ControlError):
                    app._transition(Mock(kind="switch", expires_at=expires_at), lease)
                checked_lease, deadline = session.check_admission.call_args.args
                self.assertIs(checked_lease, lease)
                self.assertEqual(deadline.end, expected_end)
        session.observe.assert_not_called()
        session.preflight.assert_not_called()
        session.stop.assert_not_called()
        session.select.assert_not_called()
        session.start.assert_not_called()

    def test_read_and_admission_caps_reject_invalid_before_backend_or_journal(self):
        backend, journal = Mock(), Mock()
        for field in ("read_seconds", "admission_seconds"):
            for value in (0, -1, 60.001, float("nan"), float("inf"), -float("inf"),
                          True, False, None, "60", [], {}):
                with self.subTest(field=field, value=value):
                    with self.assertRaisesRegex(ValueError, "^invalid_deadlines$"):
                        Application(backend, journal, **{field: value})
        self.assertEqual(backend.mock_calls, [])
        self.assertEqual(journal.mock_calls, [])


class ObservationGuards(unittest.TestCase):
    def test_saved_ready_and_model_list_alone_are_not_ready(self):
        for raw in (ready_raw(observation_available=False), ready_raw(ready_proof={}),
                    ready_raw(ready_proof={"authenticated_model": True}),
                    ready_raw(observed="warming"), ready_raw(container=None)):
            with self.subTest(raw=raw):
                self.assertNotEqual(observation(raw)[0]["observed"], "ready")

    def test_every_ready_proof_requires_exact_true(self):
        self.assertEqual(observation(ready_raw())[0]["observed"], "ready")
        for name in ready_raw()["ready_proof"]:
            for value in (None, False, 1, "true"):
                with self.subTest(name=name, value=value):
                    raw = ready_raw()
                    raw["ready_proof"][name] = value
                    self.assertNotEqual(observation(raw)[0]["observed"], "ready")

    def test_storage_loss_or_unknown_storage_never_ready(self):
        for storage in (False, None):
            with self.subTest(storage=storage):
                snapshot, _ = observation(ready_raw(storage_available=storage))
                self.assertNotEqual(snapshot["observed"], "ready")

    def test_matching_selection_container_and_running_intent_required(self):
        for changes in ({"selected": "beta"}, {"desired": "stopped"},
                        {"container_running": False}, {"container_running": "true"},
                        {"observation_available": 1}):
            with self.subTest(changes=changes):
                self.assertNotEqual(observation(ready_raw(**changes))[0]["observed"], "ready")

    def test_immutable_identity_fields_all_required(self):
        for name in ("instance", "deployment", "id", "generation"):
            for value in (None, "", 1, "private\nvalue", "x" * 257):
                with self.subTest(name=name, value=value):
                    raw = ready_raw()
                    raw["container"][name] = value
                    snapshot, _ = observation(raw)
                    self.assertIsNone(snapshot["active_identity"])
                    self.assertNotEqual(snapshot["observed"], "ready")

    def test_polling_timestamps_and_health_do_not_change_fingerprint(self):
        raw = ready_raw(observed_at=1, last_probe_at=2)
        with patch("control.core.time.time", return_value=10):
            before, fingerprint = observation(raw)
        raw.update(observed_at=30, last_probe_at=40, observed="warming")
        with patch("control.core.time.time", return_value=50):
            after, new_fingerprint = observation(raw)
        self.assertNotEqual(before["observed_at"], after["observed_at"])
        self.assertEqual(fingerprint, new_fingerprint)
        self.assertEqual(before["active_identity"], after["active_identity"])

    def test_same_profile_new_container_or_start_changes_identity(self):
        before, fingerprint = observation(ready_raw())
        for name in ("id", "generation"):
            with self.subTest(name=name):
                raw = ready_raw()
                raw["container"][name] += "-new"
                after, changed = observation(raw)
                self.assertNotEqual(before["active_identity"], after["active_identity"])
                self.assertNotEqual(fingerprint, changed)

    def test_observation_projects_no_private_objects(self):
        raw = ready_raw(environment={"PRIVATE": "secret-value"}, path="/private/path",
                        authorization="secret-key", logs="private-logs", failure="secret_failure_value")
        raw["container"]["docker_inspection"] = {"secret": "secret-value"}
        snapshot, _ = observation(raw)
        encoded = json.dumps(snapshot)
        for private in ("secret-value", "private/path", "secret-key", "private-logs", "secret_failure_value", "immutable-container-1"):
            self.assertNotIn(private, encoded)
        self.assertIsNone(snapshot["failure_code"])

    def test_unavailable_observation_has_no_stale_active_identity(self):
        snapshot, fingerprint = observation(ready_raw(observation_available=False))
        self.assertIsNone(snapshot["active_identity"])
        self.assertIsNone(snapshot["container_running"])
        self.assertIsNone(fingerprint)


class ResponseAndBindingGuards(unittest.TestCase):
    def test_unknown_exception_codes_are_never_echoed(self):
        for exc in (RuntimeError("private-path-token"), ControlError("private_token_value"),
                    ControlError("/private/path")):
            self.assertEqual(safe_error(exc), "transition_failed")
        self.assertEqual(safe_error(ControlError("preflight_failed")), "preflight_failed")

    def test_operation_projection_excludes_private_receipts(self):
        value = operation()
        value.update(authorization="secret-key", raw_error="private-error", request={"private": "input"})
        result = public_operation(value)
        for private in ("authorization", "raw_error", "request", "request_digest", "idempotency_digest"):
            self.assertNotIn(private, result)
        result["observed"]["selected"] = "beta"
        self.assertEqual(value["observed"]["selected"], "alpha")

    def test_operation_projection_filters_unknown_failure_codes(self):
        value = operation()
        value["failure_code"] = "secret_token_value"
        result = public_operation(value)
        self.assertNotIn("secret_token_value", json.dumps(result))
        self.assertIn(result["failure_code"], SAFE_CODES | {None})

    def test_operation_projection_filters_nested_outcome_fields(self):
        value = operation()
        value["observed"]["raw_error"] = "private-observation-error"
        self.assertNotIn("private-observation-error", json.dumps(public_operation(value)))

    def test_outcome_projection_excludes_private_observation(self):
        snapshot, _ = observation(ready_raw())
        snapshot.update(generation=1, authorization="secret-key", raw_inspect={"private": "value"})
        result = public_outcome(snapshot)
        self.assertNotIn("authorization", result)
        self.assertNotIn("raw_inspect", result)
        self.assertNotIn("ready_proof", result)

    def test_production_binding_refuses_without_any_fixture_fallback(self):
        from control import installation
        with patch.dict(os.environ, {"CONTROL_BACKEND": "fixture", "LLMCTL_TEST_ROOT": "/not-an-installed-owner"}), \
                patch("subprocess.run", side_effect=AssertionError("must not spawn a fallback")), \
                patch("os.system", side_effect=AssertionError("must not spawn a fallback")):
            with self.assertRaises(installation.InstallationError) as rejected:
                installation.validate_installation()
        self.assertEqual(str(rejected.exception), "unsafe_or_missing_control_installation")

    def test_deadline_is_monotonic_and_fails_at_expiry(self):
        with patch("control.protocol.time.monotonic", return_value=10):
            deadline = Deadline.after(2)
        with patch("control.protocol.time.monotonic", return_value=11):
            self.assertEqual(deadline.remaining(), 1)
        for now in (12, 13):
            with patch("control.protocol.time.monotonic", return_value=now):
                with self.assertRaises(ControlError) as rejected:
                    deadline.remaining()
                self.assertEqual(rejected.exception.code, "deadline_exceeded")


if __name__ == "__main__":
    unittest.main()
