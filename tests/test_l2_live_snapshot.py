"""L2 source selection through actual Manager/catalog and protected fixture I/O.

No model bytes, native runtime, Docker, VM, key, or installation is used. The
temporary completion metadata is explicitly synthetic and removed at cleanup.
GLM32K is a test reference only, never the unresolved product profile selection.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import shutil
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests/lifecycle"))

from control.discovery import discover_catalog
from lifecycle import qwen38
from test_real_storage_io import LocalStorageFixture


class LiveSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.manifest = json.loads((ROOT / "configs/control/ai-vm-live-snapshot.json").read_text())
        self.fixture = LocalStorageFixture()
        self.addCleanup(self.fixture.close)
        self.manager = self.fixture.manager
        self.config = self.fixture.base / "source/configs"
        for relative in self.manifest["fixed_profile_sha256"]:
            destination = self.config.parent / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, destination)
        # Explicit temporary fixture source; manifest intentionally selects none
        # until D3T supplies its final practical-context deployment.
        self.glm_id = "glm-5.3-ud-q4-k-xl-32k"
        shutil.copyfile(ROOT / f"configs/deployments/{self.glm_id}.json",
                        self.config / f"deployments/{self.glm_id}.json")
        shutil.copyfile(ROOT / "configs/runtimes/llama-cpp-v0.4.1-d1.json",
                        self.config / "runtimes/llama-cpp-v0.4.1-d1.json")
        self.manager.config_root = self.config
        self.manager.instance["model_integrity"] = {}
        self.manager.instance["runtime_evidence"] = {}
        self.receipts = {}

    def complete(self, model_id):
        model = json.loads((self.config / f"models/{model_id}.json").read_text())
        receipt = {"schema_version": 1, "complete": True,
                   "repo_id": model["repo_id"], "revision": model["revision"],
                   "model_root": self.fixture.binding.path("models", model_id),
                   "artifact_count": model["artifact_count"], "total_bytes": model["total_bytes"],
                   "artifacts": [{key: value[key] for key in ("path", "size_bytes", "sha256")}
                                 | {"verified": True} for value in model["artifacts"]]}
        path = self.fixture.binding.path("data", f"services/llm-manager/acquisition/{model_id}.complete.json")
        evidence = {"verified": True, "revision": model["revision"],
                    "evidence": "SYNTHETIC L2 source fixture; not acquisition evidence",
                    "completion_manifest": path}
        if "manifest_sha256" in model:
            evidence["manifest_sha256"] = receipt["manifest_sha256"] = model["manifest_sha256"]
        self.fixture.jsonfile(path, receipt)
        self.manager.instance["model_integrity"][model_id] = evidence
        self.receipts[model_id] = (path, receipt)

    def public(self):
        return discover_catalog(self.manager).public({
            "storage_available": True, "observation_available": True,
            "observed_at": 1789434000.0, "selected": None, "desired": "stopped",
            "observed": "stopped", "container_running": False, "active_identity": None,
        })

    def test_frozen_source_selection_hashes_and_explicit_glm_owner_gap(self):
        offered = self.manifest["offered_models"]
        self.assertEqual({row["id"] for row in offered},
                         {"glm-5.3-ud-q4-k-xl", "qwen38-27b-fp8"})
        self.assertEqual(self.manifest["status"],
                         "OWNER_FINAL_GLM_RUNTIME_DEPLOYMENT_AND_PROOF_CLOSURE_REQUIRED")
        glm = next(row for row in offered if row["network_role"] == "glm")
        self.assertEqual(glm["composition_owner"], "D3PD/D3T")
        for field in ("runtime", "runtime_source", "runtime_sha256", "measured_image_id",
                      "patched_image_proof", "recipe_dependency_closure", "deployment_source",
                      "deployment_sha256"):
            self.assertIsNone(glm[field])
        files = self.manifest["fixed_profile_sha256"]
        self.assertEqual(len(files), 5)
        self.assertNotIn("configs/runtimes/llama-cpp-v0.4.1-d1.json", files)
        for relative, digest in files.items():
            self.assertEqual(hashlib.sha256((ROOT / relative).read_bytes()).hexdigest(), digest)
        self.assertEqual({p.stem for p in (self.config / "models").glob("*.json")},
                         {row["id"] for row in offered})
        self.assertEqual({p.stem for p in (self.config / "runtimes").glob("*.json")},
                         {"llama-cpp-v0.4.1-d1", "sglang-qwen38-0.5.19"})
        for identifier in (self.glm_id, *qwen38.VARIANTS):
            deployment = self.manager.deployment(identifier)
            self.assertEqual(deployment["endpoint"]["host"], "127.0.0.1")
        self.assertTrue((ROOT / "configs/deployments/qwen3-coder-next.json").is_file())
        self.assertFalse((self.config / "deployments/qwen3-coder-next.json").exists())

    def test_profile_presence_does_not_publish_installed_models(self):
        catalog = discover_catalog(self.manager)
        self.assertEqual(self.public(), [])
        for identifier in (self.glm_id, *qwen38.VARIANTS):
            with self.assertRaisesRegex(ValueError, "^target_unavailable$"):
                catalog.target(identifier)
        with self.assertRaisesRegex(ValueError, "^unknown_deployment$"):
            catalog.target("qwen3-coder-next")

    def test_real_discovery_offers_only_two_models_with_declared_context_variants(self):
        for row in self.manifest["offered_models"]:
            self.complete(row["id"])
        with patch.object(self.manager, "check_artifacts", side_effect=AssertionError("payload read")), \
                patch.object(self.manager, "prepare_start", side_effect=AssertionError("start")), \
                patch.object(self.manager, "read_state", side_effect=AssertionError("state read")):
            entries = self.public()
        self.assertEqual({row["model_id"] for row in entries},
                         {row["model_id"] for row in self.manifest["offered_models"]})
        self.assertEqual({row["deployment_id"] for row in entries},
                         {self.glm_id, *qwen38.VARIANTS})
        for row in entries:
            self.assertEqual(row["state"], "unavailable")  # No native runtime evidence or payloads.
            self.assertFalse(row["endpoint"]["ready"])
            self.assertEqual(row["context"]["configured_provenance"], "declared")
            self.assertIsNone(row["context"]["verified_occupied_tokens"])
            self.assertEqual(row["context"]["verified_occupied_provenance"], "unknown")
            self.assertEqual(row["context"]["evidence"], [])
            if row["deployment_id"] in qwen38.VARIANTS:
                self.assertEqual(row["context"]["configured_tokens"], qwen38.VARIANTS[row["deployment_id"]])
                self.assertEqual(row["endpoint"]["served_model"], "qwen3.8-27b")
                self.assertEqual(row["endpoint"]["base_url"], "http://127.0.0.1:30004/v1")
        self.assertEqual(self.fixture.docker.calls, [])
        self.assertFalse(Path(self.fixture.binding.path("models", qwen38.MODEL)).exists())
        # The separate strict Q38 acquisition validator accepts these exact
        # fixture tuples; this still supplies no runtime or inference evidence.
        qwen38.check_completion(self.manager.deployment("qwen38-27b-128k"), self.manager.instance)

    def test_receipt_root_or_manifest_drift_removes_only_affected_model(self):
        for row in self.manifest["offered_models"]:
            self.complete(row["id"])
        qpath, qreceipt = self.receipts[qwen38.MODEL]
        for change in ({"model_root": "/unregistered/qwen38"}, {"manifest_sha256": "0" * 64}):
            self.fixture.jsonfile(qpath, qreceipt | change)
            self.assertEqual([row["deployment_id"] for row in self.public()], [self.glm_id])
        self.fixture.jsonfile(qpath, qreceipt)
        self.fixture.local(qpath).chmod(0o644)
        self.assertEqual([row["deployment_id"] for row in self.public()], [self.glm_id])

    def test_generic_catalog_has_no_permanent_two_model_limit(self):
        for row in self.manifest["offered_models"]:
            self.complete(row["id"])
        deployment = json.loads((self.config / f"deployments/{self.glm_id}.json").read_text())
        model = json.loads((self.config / "models/glm-5.3-ud-q4-k-xl.json").read_text())
        # Add one future reviewed profile only inside this temporary snapshot.
        # Generic discovery must follow its files instead of hardcoded roster IDs.
        text = json.dumps(deployment).replace(self.glm_id, "future-fixture-8k")
        text = text.replace("glm-5.3-ud-q4-k-xl", "future-fixture")
        future = json.loads(text)
        future["endpoint"]["served_model"] = "future-fixture"
        future["launch"]["context_size"] = 8192
        model = copy.deepcopy(model)
        model.update(id="future-fixture", repo_id="Fixture/Future",
                     model_root={"role": "models", "suffix": "future-fixture"})
        (self.config / "deployments/future-fixture-8k.json").write_text(json.dumps(future))
        (self.config / "models/future-fixture.json").write_text(json.dumps(model))
        self.complete("future-fixture")
        self.assertEqual({row["model_id"] for row in self.public()},
                         {"unsloth/GLM-5.3-GGUF", "Qwen/Qwen3.8-27B-FP8", "Fixture/Future"})


if __name__ == "__main__":
    unittest.main()
