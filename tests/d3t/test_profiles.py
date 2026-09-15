"""Exercise shipped D3T profile generation and source/output refusal boundaries."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from d3t import profiles
from lifecycle.manager import Manager
from lifecycle.runtime_io import LifecycleError
sys.path.insert(0, str(ROOT / "tests/lifecycle"))
from fixture_storage import HistoricalBinding


class ProfilePlanTests(unittest.TestCase):
    def setUp(self):
        self.plan = profiles.generate_plan()
        self.baseline_path = ROOT / f"configs/deployments/{profiles.BASELINE_ID}.json"
        self.baseline = json.loads(self.baseline_path.read_text())

    def test_exact_generation_preserves_baseline_and_limits_candidate_delta(self):
        before = self.baseline_path.read_bytes()
        self.assertEqual(profiles.canonical_bytes(self.plan),
                         profiles.canonical_bytes(profiles.generate_plan()))
        self.assertEqual(self.plan["status"], "NOT_TESTED")
        self.assertFalse(self.plan["deployable"])
        self.assertEqual(self.plan["rollback"]["image_id"], profiles.D1_IMAGE)
        self.assertEqual(self.plan["source_sha256"], profiles.SOURCE_PINS)
        for proposal in self.plan["proposals"]:
            expected = copy.deepcopy(self.baseline["launch"])
            expected["context_size"] = proposal["launch"]["context_size"]
            if "n76" in proposal["id"]:
                del expected["cpu_moe"]
                expected["n_cpu_moe"] = 76
            self.assertEqual(proposal["launch"], expected)
            for key in ("schema_version", "model", "endpoint", "container_port",
                        "container_host", "auth", "boot_policy", "docker_restart_policy", "logs"):
                self.assertEqual(proposal[key], self.baseline[key])
            self.assertIsNone(proposal["runtime"])
            self.assertEqual(proposal["capability_status"], "NOT_TESTED")
            for target, role in (("/cache", "cache"), ("/logs", "logs"), ("/service", "service")):
                mount = next(m for m in proposal["mounts"] if m["target"] == target)
                self.assertEqual(mount["source"], proposal["paths"][role])
                self.assertNotEqual(proposal["paths"][role], self.baseline["paths"][role])
                self.assertNotIn("historical_suffix", proposal["paths"][role])
        self.assertEqual(before, self.baseline_path.read_bytes())

    def test_current_manager_rejects_unbound_proposals_before_storage_or_image_work(self):
        # Use the shipped deployment reader; stop at its runtime reference gate.
        # This exercises the actual admission boundary, without Docker/host I/O.
        manager = object.__new__(Manager)
        manager.config_root = ROOT / "configs"
        for proposal in self.plan["proposals"]:
            def source(path):
                if path.parent.name == "deployments":
                    return copy.deepcopy(proposal)
                return json.loads(path.read_text())
            manager.profile_json = source
            with self.assertRaisesRegex(LifecycleError, "invalid_profile_id"):
                manager.deployment(proposal["id"])

    def test_two_capacity_sequence_and_only_explicit_all_cpu_fallback(self):
        self.assertEqual([(p["launch"]["context_size"], p["launch"].get("n_cpu_moe"),
                           p["launch"].get("cpu_moe")) for p in self.plan["proposals"]],
                         [(32768, 76, None), (1048576, 76, None), (1048576, None, True)])
        progression = self.plan["progression"]
        self.assertEqual(progression["configured_contexts"], [32768, 1048576])
        self.assertEqual(progression["native_capacity_loads_after_32k"], 1)
        self.assertFalse(progression["automatic_fallback_or_reload"])
        for window, ceiling in zip(progression["occupied_windows"], progression["initial_templated_input_ceilings"]):
            self.assertEqual(window - ceiling, 8192)
        self.assertIsNone(self.plan["runtime_dependency"]["measured_image_id"])
        self.assertIsNone(self.plan["runtime_dependency"]["runtime_id"])
        self.assertTrue(self.plan["manager_integration"]["changes_applied"])

    def test_baseline_or_runtime_or_model_drift_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            for relative in profiles.SOURCE_PINS:
                destination = root / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / relative, destination)
            self.assertEqual(profiles.generate_plan(root), self.plan)
            for relative in profiles.SOURCE_PINS:
                path = root / relative
                before = path.read_bytes()
                path.write_bytes(before + b" ")
                with self.assertRaisesRegex(profiles.ProfileError, "source hash changed"):
                    profiles.generate_plan(root)
                path.write_bytes(before)
                path.unlink()
                path.symlink_to(ROOT / relative)
                with self.assertRaisesRegex(profiles.ProfileError, "symlink"):
                    profiles.generate_plan(root)
                path.unlink()
                path.write_bytes(before)

    def test_source_output_is_exclusive_private_and_outside_configs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            target = root / "plan.json"
            profiles.write_plan(target, self.plan)
            self.assertEqual(target.read_bytes(), profiles.canonical_bytes(self.plan))
            self.assertEqual(target.stat().st_mode & 0o777, 0o600)
            with self.assertRaises(FileExistsError):
                profiles.write_plan(target, self.plan)
            configs = root / "configs"
            configs.mkdir()
            with self.assertRaisesRegex(profiles.ProfileError, "outside any configs"):
                profiles.write_plan(configs / "plan.json", self.plan)
            alias = root / "alias"
            alias.symlink_to(root, target_is_directory=True)
            with self.assertRaisesRegex(profiles.ProfileError, "symlink"):
                profiles.write_plan(alias / "unsafe.json", self.plan)
            self.assertEqual(sorted(p.name for p in root.iterdir()), ["alias", "configs", "plan.json"])

    def test_cli_help_and_output_are_cpu_source_only(self):
        command = [sys.executable, str(ROOT / "scripts/d3t/profiles.py")]
        help_result = subprocess.run(command + ["--help"], capture_output=True, timeout=10, check=True)
        self.assertIn(b"--output", help_result.stdout)
        result = subprocess.run(command, capture_output=True, timeout=10, check=True)
        self.assertEqual(result.stdout, profiles.canonical_bytes(self.plan))
        self.assertEqual(result.stderr, b"")


class ManagerD3TTests(unittest.TestCase):
    """Actual llama validator/argv, with no profile install or runtime I/O."""
    SYNTHETIC_IMAGE = "sha256:" + "a" * 64

    def setUp(self):
        self.manager = object.__new__(Manager)
        self.manager.binding = HistoricalBinding()
        self.manager.instance = {}
        self.baseline = json.loads((ROOT / f"configs/deployments/{profiles.BASELINE_ID}.json").read_text())
        self.runtime = json.loads((ROOT / f"configs/runtimes/{profiles.D1_RUNTIME}.json").read_text())
        self.model = json.loads((ROOT / f"configs/models/{profiles.MODEL}.json").read_text())

    def bound(self, source, *, patched=True, model=None):
        d = copy.deepcopy(source)
        d["_model"] = copy.deepcopy(self.model)
        d["_runtime"] = copy.deepcopy(self.runtime)
        if patched:
            # Fixture-only identity; never written as deployment/image evidence.
            d["runtime"] = "synthetic-d3p-fixture"
            d["_runtime"]["id"] = d["runtime"]
            d["_runtime"]["validation"]["image_id"] = self.SYNTHETIC_IMAGE
        if model:
            d["model"] = model
            d["_model"]["id"] = model
            d["_model"]["model_root"]["suffix"] = model
            d["paths"]["model"]["suffix"] = model
            next(m for m in d["mounts"] if m["target"] == "/models")["source"]["suffix"] = model
        return self.manager.bind_deployment(d)

    def test_actual_candidate_argv_changes_only_placement_and_selected_context(self):
        baseline = self.bound(self.baseline, patched=False)
        self.manager.validate_deployment(baseline)
        old = Manager.launch_command(baseline, {"load_mode": "none", "image_id": profiles.D1_IMAGE})
        for proposal in profiles.generate_plan()["proposals"]:
            d = self.bound(proposal)
            self.manager.validate_deployment(d)
            actual = Manager.launch_command(d, {"load_mode": "none", "image_id": self.SYNTHETIC_IMAGE})
            expected = old.copy()
            expected[expected.index("--ctx-size") + 1] = str(proposal["launch"]["context_size"])
            if "n_cpu_moe" in proposal["launch"]:
                position = expected.index("--cpu-moe")
                expected[position:position + 1] = ["--n-cpu-moe", "76"]
                self.assertNotIn("--cpu-moe", actual)
            else:
                self.assertNotIn("--n-cpu-moe", actual)
            self.assertEqual(actual, expected)

    def test_old_all_cpu_context_range_and_model_scope_are_preserved(self):
        for context in (512, 8192, 32768, 131072):
            d = self.bound(self.baseline, patched=False)
            d["launch"]["context_size"] = context
            self.manager.validate_deployment(d)
        d = self.bound(self.baseline, model="other-model")
        d["launch"]["context_size"] = 1048576
        with self.assertRaisesRegex(LifecycleError, "invalid_launch_limit"):
            self.manager.validate_deployment(d)
        for context in (511, 131073, 262144, 524288, 1048577, True, 32768.0):
            d = self.bound(self.baseline)
            d["launch"]["context_size"] = context
            with self.subTest(context=context), self.assertRaisesRegex(LifecycleError, "invalid_launch_limit"):
                self.manager.validate_deployment(d)

    def test_selected_n76_refuses_sweep_dual_overrides_wrong_models_and_flag_drift(self):
        proposal = profiles.generate_plan()["proposals"][0]
        cases = [{"n_cpu_moe": n} for n in (0, 75, 77, 78, True, 76.0, "76", None)]
        cases += [{"cpu_moe": x} for x in (True, False, None)]
        cases += [{"context_size": c} for c in (8192, 65536, 131072)]
        cases += [{"tensor_split": "2,1"}, {"n_gpu_layers": 998}]
        for change in cases:
            d = self.bound(proposal)
            d["launch"].update(change)
            with self.subTest(change=change), self.assertRaises(LifecycleError):
                self.manager.validate_deployment(d)
        d = self.bound(proposal, model="other-model")
        with self.assertRaisesRegex(LifecycleError, "invalid_launch_safety"):
            self.manager.validate_deployment(d)

    def test_d1_and_unmeasured_mismatched_image_cannot_render_new_profiles(self):
        for proposal in profiles.generate_plan()["proposals"]:
            d = self.bound(proposal)
            d["runtime"] = profiles.D1_RUNTIME
            with self.assertRaisesRegex(LifecycleError, "d3t_patched_runtime_required"):
                self.manager.validate_deployment(d)
            for measured, instance_image in ((None, self.SYNTHETIC_IMAGE),
                    (self.SYNTHETIC_IMAGE, profiles.D1_IMAGE),
                    (profiles.D1_IMAGE, profiles.D1_IMAGE),
                    ("sha256:short", "sha256:short")):
                d = self.bound(proposal)
                d["_runtime"]["validation"]["image_id"] = measured
                with self.subTest(measured=measured, instance=instance_image), self.assertRaisesRegex(
                        LifecycleError, "d3t_patched_image_required"):
                    Manager.launch_command(d, {"load_mode": "none", "image_id": instance_image})


if __name__ == "__main__":
    unittest.main()
