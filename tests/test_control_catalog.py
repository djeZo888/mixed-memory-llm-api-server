"""Catalog serialization tests: explicit protocol records, no live inference."""

import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from control.catalog import CAPABILITIES, Catalog, MAX_ENTRIES


def record(identifier="model-a", **changes):
    value = {
        "deployment_id": identifier, "model_id": "Example/Model",
        "display_name": "Example model", "revision": "a" * 40,
        "backend": "fixture-backend", "runtime": "fixture-runtime-v1",
        "installed": True, "installed_verified_at": "2026-09-15T01:00:00Z",
        "small_checks_passed": True, "context_limit": 32768,
        "quantization": "FP8", "installed_bytes": 1000,
        "endpoint": {"port": 30001, "served_model": identifier,
                     "authentication_required": True},
    }
    value.update(changes)
    return value


def observation(**changes):
    value = {
        "observed_at": 1789434000.0, "selected": None, "desired": "stopped",
        "observed": "stopped", "container_running": False,
        "active_identity": None, "storage_available": True,
    }
    value.update(changes)
    return value


def ready(**changes):
    value = observation(selected="model-a", desired="running", observed="ready",
                        container_running=True, active_identity="opaque-instance-1",
                        observed_deployment="model-a", ready_proof={
                            "trusted_identity": True, "safe_network": True,
                            "authenticated_model": True, "runtime_health": True})
    value.update(changes)
    return value


class CatalogTests(unittest.TestCase):
    def test_third_future_model_is_generic_and_multiple_deployments_allowed(self):
        catalog = Catalog([record("model-a"), record("model-b"),
                           record("third-future-8k", model_id="Future/Model", context_limit=8192)])
        entries = catalog.public(observation())
        self.assertEqual([e["deployment_id"] for e in entries],
                         ["model-a", "model-b", "third-future-8k"])
        self.assertEqual(entries[2]["model_id"], "Future/Model")
        self.assertTrue(all(e["start_revalidation_required"] for e in entries))

    def test_uninstalled_historical_and_research_entries_excluded(self):
        catalog = Catalog([record(), {"deployment_id": "historical", "installed": False},
                           {"deployment_id": "q38-research", "installed": False}])
        self.assertEqual(len(catalog.public(observation())), 1)
        for identifier in ("historical", "q38-research"):
            with self.assertRaisesRegex(ValueError, "^target_unavailable$"):
                catalog.target(identifier)
        with self.assertRaisesRegex(ValueError, "^unknown_deployment$"):
            catalog.target("never-registered")

    def test_missing_acquisition_evidence_does_not_advertise_installed(self):
        for absent in ("installed", "installed_verified_at"):
            item = record()
            item.pop(absent)
            catalog = Catalog([item])
            self.assertEqual(catalog.public(observation()), [])
            with self.assertRaisesRegex(ValueError, "^target_unavailable$"):
                catalog.target("model-a")

    def test_installed_evidence_with_failed_small_checks_is_unavailable(self):
        catalog = Catalog([record(small_checks_passed=False)])
        self.assertEqual(catalog.public(observation())[0]["state"], "unavailable")
        with self.assertRaisesRegex(ValueError, "^target_unavailable$"):
            catalog.target("model-a")

    def test_true_ready_requires_all_proofs_and_matching_observation(self):
        catalog = Catalog([record()])
        self.assertEqual(catalog.public(ready())[0]["state"], "ready")
        for key in ready()["ready_proof"]:
            for false_value in (False, None, "true", 1):
                snapshot = ready()
                snapshot["ready_proof"][key] = false_value
                self.assertNotEqual(catalog.public(snapshot)[0]["state"], "ready")
        for changes in ({"observed_deployment": "model-b"}, {"active_identity": None},
                        {"container_running": False}, {"selected": "model-b"},
                        {"desired": "stopped"}, {"observed_at": None},
                        {"observation_available": False}, {"storage_available": False}):
            self.assertNotEqual(catalog.public(ready(**changes))[0]["state"], "ready")

    def test_model_list_and_saved_ready_during_warmup_never_ready(self):
        catalog = Catalog([record()])
        for snapshot in (observation(selected="model-a", desired="running", observed="ready"),
                         ready(observed="warming"), ready(ready_proof={"authenticated_model": True}),
                         ready(observed_at=None)):
            self.assertNotEqual(catalog.public(snapshot)[0]["state"], "ready")

    def test_loading_requires_owned_running_operation(self):
        catalog = Catalog([record()])
        loading = catalog.public(observation(current_operation={"target": "model-a", "status": "running"}))
        self.assertEqual(loading[0]["state"], "loading")
        self.assertFalse(loading[0]["endpoint"]["ready"])
        for operation in ({"target": "model-a", "status": "pending"},
                          {"target": "model-b", "status": "running"}):
            self.assertNotEqual(catalog.public(observation(current_operation=operation))[0]["state"], "loading")

    def test_failed_operation_and_unhealthy_desired_backend(self):
        catalog = Catalog([record()])
        self.assertEqual(catalog.public(observation(current_operation={
            "target": "model-a", "status": "failed"}))[0]["state"], "failed")
        self.assertEqual(catalog.public(ready(observed="unhealthy"))[0]["state"], "failed")

    def test_unknown_storage_and_observations_never_ready(self):
        catalog = Catalog([record()])
        self.assertEqual(catalog.public(ready(storage_available=False))[0]["state"], "unavailable")
        self.assertEqual(catalog.public(ready(storage_available=None))[0]["state"], "unknown")
        self.assertEqual(catalog.public(ready(observation_available=False))[0]["state"], "unknown")
        self.assertEqual(catalog.public({})[0]["state"], "unknown")

    def test_unknown_capabilities_and_resources_not_guessed(self):
        entry = Catalog([record()]).public(observation())[0]
        self.assertEqual(set(entry["capabilities"]), set(CAPABILITIES))
        self.assertTrue(all(c == {"status": "unknown", "evidence": []}
                            for c in entry["capabilities"].values()))
        self.assertTrue(all(r["bytes"] is None and r["provenance"] == "unknown"
                            for r in entry["requirements"].values()))

    def test_verified_tools_require_end_to_end_evidence(self):
        for kind in (None, "parser_flag", "source_inspection"):
            entry = Catalog([record(capabilities={"tool_calling": {
                "status": "verified", "evidence": ["tool-parser-present"],
                "verification_kind": kind}})]).public(observation())[0]
            self.assertEqual(entry["capabilities"]["tool_calling"]["status"], "unknown")
        capabilities = {"tool_calling": {"status": "verified", "evidence": ["acceptance-001"],
                                         "verification_kind": "end_to_end"}}
        entry = Catalog([record(capabilities=capabilities)]).public(observation())[0]
        self.assertEqual(entry["capabilities"]["tool_calling"],
                         {"status": "verified", "evidence": ["acceptance-001"]})

    def test_declared_capabilities_and_resource_provenance(self):
        entry = Catalog([record(capabilities={"vision": {
            "status": "declared", "evidence": ["model-card-1"], "verification_kind": "declaration"}},
            requirements={"ram_bytes": {"bytes": 500, "provenance": "estimate", "evidence": ["estimate-1"]},
                          "gpu_bytes": {"bytes": 300, "provenance": "measurement", "evidence": ["measurement-1"]}})
        ]).public(observation())[0]
        self.assertEqual(entry["capabilities"]["vision"]["status"], "declared")
        self.assertEqual(entry["requirements"]["ram_bytes"]["provenance"], "estimate")
        self.assertEqual(entry["requirements"]["gpu_bytes"]["provenance"], "measurement")

    def test_discovery_tracks_each_port_and_alias_as_server_relative(self):
        entries = Catalog([record(), record("model-b", endpoint={"port": 31009, "served_model": "new-alias",
                                                            "authentication_required": True})]).public(ready())
        self.assertEqual(entries[0]["endpoint"]["base_url"], "http://127.0.0.1:30001/v1")
        self.assertTrue(entries[0]["endpoint"]["ready"])
        self.assertEqual(entries[1]["endpoint"]["served_model"], "new-alias")
        self.assertEqual(entries[1]["endpoint"]["base_url"], "http://127.0.0.1:31009/v1")
        self.assertFalse(entries[1]["endpoint"]["ready"])
        self.assertTrue(all(e["endpoint"]["server_relative"] and e["endpoint"]["authentication_required"] for e in entries))

    def test_unsafe_endpoint_contracts_rejected_without_values_in_error(self):
        for endpoint in ({"port": 0}, {"port": 65536}, {"port": True},
                         {"host": "0.0.0.0"}, {"api_prefix": "/secret"},
                         {"authentication_required": False}, {"served_model": "../private"}):
            original = record()["endpoint"]
            original.update(endpoint)
            with self.assertRaisesRegex(ValueError, "^invalid_catalog$"):
                Catalog([record(endpoint=original)])

    def test_response_allowlist_excludes_paths_commands_secrets_raw_objects(self):
        item = record(auth={"token": "private-sentinel"}, paths={"model": "/large/weights"},
                      environment={"SENTINEL": "private-sentinel"}, command="untrusted-command",
                      raw_inspection={"data": "private-sentinel"})
        item["endpoint"]["key_file"] = "/data/services/secrets/control-key"
        snapshot = ready(auth={"token": "private-sentinel"}, failure="private-sentinel")
        encoded = json.dumps(Catalog([item]).public(snapshot))
        for forbidden in ("private-sentinel", "/large/weights", "/data/services/secrets", "untrusted-command"):
            self.assertNotIn(forbidden, encoded)

    def test_bounded_records_scalars_and_evidence(self):
        Catalog([record(str(i)) for i in range(MAX_ENTRIES)])
        invalid = ([record(str(i)) for i in range(MAX_ENTRIES + 1)], [record(), record()],
                   [record(deployment_id="a" * 129)], [record(display_name="x" * 161)],
                   [record(revision="main")], [record(context_limit=True)],
                   [record(installed_bytes=-1)], [record(context_limit=0)],
                   [record(installed_verified_at="2026-99-99T00:00:00Z")],
                   [record(capabilities={"vision": {"evidence": ["x"] * 9}})],
                   [record(capabilities={"vision": {"status": {}}})],
                   [record(requirements={"ram_bytes": {"provenance": []}})],
                   [record(capabilities={"vision": {"evidence": ["/private/evidence"]}})])
        for values in invalid:
            with self.subTest(values=values[:1]):
                with self.assertRaisesRegex(ValueError, "^invalid_catalog$"):
                    Catalog(values)

    def test_numeric_and_iso_observation_times_and_invalid_numbers(self):
        catalog = Catalog([record()])
        for value in (1789434000.0, 1789434000, "2026-09-15T01:00:00Z"):
            self.assertEqual(catalog.public(observation(observed_at=value))[0]["observed_at"], value)
        for value in (True, float("nan"), float("inf"), -1, 2**63, 10**1000):
            with self.assertRaisesRegex(ValueError, "^invalid_catalog$"):
                catalog.public(observation(observed_at=value))

    def test_inputs_and_returned_records_cannot_mutate_catalog(self):
        item = record()
        catalog = Catalog([item])
        item["endpoint"]["port"] = 32000
        catalog.target("model-a")["endpoint"]["served_model"] = "changed"
        output = catalog.public(observation())
        output[0]["capabilities"].clear()
        self.assertEqual(catalog.public(observation())[0]["endpoint"]["base_url"], "http://127.0.0.1:30001/v1")
        self.assertEqual(len(catalog.public(observation())[0]["capabilities"]), len(CAPABILITIES))

    def test_catalog_never_reads_or_stats_model_weights(self):
        with patch("builtins.open", side_effect=AssertionError("filesystem access")), \
             patch("os.stat", side_effect=AssertionError("filesystem access")):
            catalog = Catalog([record()])
            self.assertEqual(catalog.target("model-a")["deployment_id"], "model-a")
            self.assertEqual(catalog.public(ready())[0]["state"], "ready")

    def test_last_failed_transition_remains_visible_without_owned_loading(self):
        catalog = Catalog([record()])
        snapshot = observation(last_operation={"status": "failed", "target": "model-a"})
        self.assertEqual(catalog.public(snapshot)[0]["state"], "failed")
        snapshot = ready(last_operation={"status": "failed", "target": "model-a"})
        self.assertEqual(catalog.public(snapshot)[0]["state"], "ready")


if __name__ == "__main__":
    unittest.main()
