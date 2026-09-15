"""Real Manager profile/argv checks against the retained D3BR binding.

Docker observations are controlled copies of the actual retained identity.
No Docker daemon, key, model, state writer, host guard or API is invoked. These
checks exercise Manager's existing attestation/Id/entrypoint boundary; the
task-owned binder separately verifies source, recipe and raw CLI evidence.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests/lifecycle"))

from d3t import profiles
from fixture_storage import HistoricalBinding
from lifecycle.manager import Manager
from lifecycle.runtime_io import LifecycleError


RUNTIME = "llama-cpp-v0.4.1-d3br"
PROOF = "reports/d3rp-runtime-proof.json"
VARIANTS = {
    "glm-5.3-ud-q4-k-xl-n76-32k": 32768,
    "glm-5.3-ud-q4-k-xl-n76-native1m": 1048576,
}


def read(relative):
    return json.loads((ROOT / relative).read_text())


def different_image(identity):
    """A negative observation, never an image identity or runnable profile."""
    digit = "0" if identity[7] != "0" else "1"
    return identity[:7] + digit + identity[8:]


class ControlledDocker:
    """Only the requested image inspect is allowed; no mutation API exists."""

    def __init__(self, tag, image):
        self.tag = tag
        self.image = copy.deepcopy(image)
        self.calls = []

    def capture(self, *args, **kwargs):
        self.calls.append(args)
        if args[:2] != ("image", "inspect") or len(args) != 3:
            raise AssertionError("D3RD allows only controlled image inspection")
        # An unknown tag has no image in this controlled observation set.
        return json.dumps([self.image] if args[2] == self.tag else [])


class ActualBindingManagerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Required files fail if absent: evidence is never replaced by a made-up
        # happy-path image, and this suite does not skip a missing binding.
        cls.runtime = read(f"configs/runtimes/{RUNTIME}.json")
        cls.proof = read(PROOF)
        cls.retained_identity = read("reports/d3rp-contract-evidence/image-identity.json")
        # Worker1 retained selected identity fields, not unrestricted inspect.
        # Project those actual values into the documented Docker inspect shape
        # expected by Manager; this projection is only a controlled observation.
        os_name, architecture = cls.retained_identity["platform"].split("/")
        cls.identity = {
            "Id": cls.retained_identity["image_id"],
            "RepoTags": [cls.retained_identity["image_tag"]],
            "RepoDigests": copy.deepcopy(cls.retained_identity["repo_digests"]),
            "Os": os_name,
            "Architecture": architecture,
            "Config": {
                "Entrypoint": copy.deepcopy(cls.retained_identity["entrypoint"]),
                "Labels": copy.deepcopy(cls.retained_identity["oci_labels"]),
            },
        }
        cls.d1 = read("configs/runtimes/llama-cpp-v0.4.1-d1.json")

    def setUp(self):
        binding = HistoricalBinding()
        self.docker = ControlledDocker(self.runtime["image_tag"], self.identity)
        # The instance is an in-memory consumer of the chosen actual evidence,
        # not publication to an installed or checked-in protected instance.
        self.manager = Manager(ROOT / "configs", {
            "schema_version": 1,
            "id": "d3rd-source-check",
            "storage_identity": binding.identity,
            "paths": {"state": {"role": "data", "suffix": "services/llm-manager/active"}},
            "runtime_evidence": {RUNTIME: {
                "image_id": self.proof["image_id"],
                "flags_verified": True,
                "supported_flags": copy.deepcopy(self.proof["supported_flags"]),
                "load_mode": "none",
                "evidence": "/usr/local/lib/llm-server/control-api/" + PROOF,
            }},
        }, binding=binding, docker=self.docker, test_paths=True)

    def evidence(self):
        return self.manager.instance["runtime_evidence"][RUNTIME]

    def test_actual_identity_and_attestation_match_runtime_without_d1_substitution(self):
        self.assertEqual(self.identity["Id"], self.proof["image_id"])
        self.assertEqual(self.identity["Id"], self.runtime["validation"]["image_id"])
        self.assertNotEqual(self.identity["Id"], self.d1["validation"]["image_id"])
        self.assertEqual(self.identity["Config"]["Entrypoint"], self.runtime["entrypoint"])
        self.assertEqual(self.proof["image_tag"], self.runtime["image_tag"])
        self.assertIn(self.runtime["image_tag"], self.identity["RepoTags"])
        self.assertEqual(self.runtime["validation"]["supported_flags"], self.proof["supported_flags"])
        self.assertIn("--n-cpu-moe", self.runtime["required_cli_flags"])
        self.assertIn("--n-cpu-moe", self.evidence()["supported_flags"])

    def test_both_shipped_profiles_preserve_exact_d3t_shape_and_declared_status(self):
        proposals = {item["id"]: item for item in profiles.generate_plan()["proposals"]}
        for identifier, context in VARIANTS.items():
            with self.subTest(profile=identifier):
                source = read(f"configs/deployments/{identifier}.json")
                expected = copy.deepcopy(proposals[identifier])
                for field in ("runtime", "purpose", "notes"):
                    expected[field] = source[field]
                self.assertEqual(source, expected)
                self.assertEqual(source["runtime"], RUNTIME)
                self.assertEqual(source["capability_status"], "NOT_TESTED")
                d = self.manager.deployment(identifier)
                self.assertEqual(Manager.backend(d), "llama_cpp")
                self.assertEqual(d["launch"]["context_size"], context)
                self.assertEqual(d["launch"]["n_cpu_moe"], 76)
                self.assertEqual(d["launch"]["parallel"], 1)
                self.assertEqual(d["launch"]["tensor_split"], "1,1")
                self.assertEqual(d["launch"]["n_gpu_layers"], 999)
                self.assertEqual(d["launch"]["devices"], ["CUDA0", "CUDA1"])
                self.assertEqual(d["launch"]["chat_template_kwargs"], {"clear_thinking": True})

    def test_both_create_args_inspect_chosen_tag_and_launch_immutable_image(self):
        before = copy.deepcopy(self.manager.state)
        for identifier, context in VARIANTS.items():
            with self.subTest(profile=identifier):
                d = self.manager.deployment(identifier)
                argv = self.manager.create_args(d)
                self.assertEqual(self.docker.calls[-1], ("image", "inspect", self.proof["image_tag"]))
                image_index = argv.index(self.proof["image_id"])
                command = argv[image_index + 1:]
                self.assertNotIn(self.proof["image_tag"], argv)
                self.assertEqual(argv[argv.index("--entrypoint") + 1], self.runtime["entrypoint"][0])
                self.assertEqual(argv[argv.index("--restart") + 1], "no")
                self.assertEqual(argv[argv.index("--publish") + 1], "127.0.0.1:30002:30002/tcp")
                self.assertEqual(argv[argv.index("--gpus") + 1], '"device=0,1"')
                self.assertEqual(argv.count("--mount"), 5)
                for flag, value in {
                    "--ctx-size": str(context), "--n-cpu-moe": "76", "--parallel": "1",
                    "--tensor-split": "1,1", "--n-gpu-layers": "999", "--load-mode": "none",
                    "--device": "CUDA0,CUDA1", "--alias": "glm-5.3",
                    "--chat-template-kwargs": '{"clear_thinking":true}',
                    "--api-key-file": "/run/secrets/llm-api-key",
                }.items():
                    self.assertEqual(command[command.index(flag) + 1], value)
                self.assertNotIn("--cpu-moe", command)
                self.assertEqual(command, Manager.launch_command(d, self.evidence()))
        self.assertEqual(self.manager.state, before)

    def test_launch_delta_from_unchanged_d1_is_only_n76_and_context(self):
        baseline = self.manager.deployment(profiles.BASELINE_ID)
        original = Manager.launch_command(baseline, {
            "image_id": self.d1["validation"]["image_id"], "load_mode": "none"})
        self.assertIn("--cpu-moe", original)
        for identifier, context in VARIANTS.items():
            expected = original.copy()
            position = expected.index("--cpu-moe")
            expected[position:position + 1] = ["--n-cpu-moe", "76"]
            expected[expected.index("--ctx-size") + 1] = str(context)
            d = self.manager.deployment(identifier)
            self.assertEqual(Manager.launch_command(d, self.evidence()), expected)

    def test_missing_n_cpu_moe_attestation_refuses_before_inspection(self):
        self.evidence()["supported_flags"].remove("--n-cpu-moe")
        for identifier in VARIANTS:
            with self.subTest(profile=identifier), self.assertRaisesRegex(
                    LifecycleError, "d1_supported_flags_required"):
                self.manager.create_args(self.manager.deployment(identifier))
        self.assertEqual(self.docker.calls, [])

    def test_incomplete_attestation_refuses_before_inspection(self):
        valid = copy.deepcopy(self.evidence())
        for field, value, reason in (("flags_verified", False, "d1_flag_evidence_required"),
                ("evidence", "", "d1_flag_evidence_required"),
                ("load_mode", "unknown", "d1_load_mode_required"),
                ("image_id", None, "d1_image_id_required")):
            self.manager.instance["runtime_evidence"][RUNTIME] = copy.deepcopy(valid)
            self.evidence()[field] = value
            with self.subTest(field=field), self.assertRaisesRegex(LifecycleError, reason):
                self.manager.create_args(self.manager.deployment(next(iter(VARIANTS))))
        self.assertEqual(self.docker.calls, [])

    def test_wrong_observed_image_and_entrypoint_refuse_for_both_contexts(self):
        for identifier in VARIANTS:
            for field in ("image", "entrypoint"):
                self.docker.image = copy.deepcopy(self.identity)
                if field == "image":
                    self.docker.image["Id"] = different_image(self.identity["Id"])
                    reason = "runtime_image_id_mismatch"
                else:
                    self.docker.image["Config"]["Entrypoint"] = ["/unreviewed/llama-server"]
                    reason = "runtime_entrypoint_mismatch"
                with self.subTest(profile=identifier, field=field), self.assertRaisesRegex(
                        LifecycleError, reason):
                    self.manager.create_args(self.manager.deployment(identifier))

    def test_wrong_configured_tag_has_no_image_in_controlled_observation(self):
        d = self.manager.deployment(next(iter(VARIANTS)))
        d["_runtime"]["image_tag"] += "-unreviewed"
        with self.assertRaisesRegex(LifecycleError, "runtime_image_id_mismatch"):
            self.manager.create_args(d)
        self.assertEqual(self.docker.calls, [("image", "inspect", d["_runtime"]["image_tag"])])

    def test_d1_runtime_or_d1_attested_observed_image_cannot_launch_n76(self):
        for identifier in VARIANTS:
            d = self.manager.deployment(identifier)
            d["runtime"] = self.d1["id"]
            d["_runtime"] = copy.deepcopy(self.d1)
            with self.subTest(profile=identifier), self.assertRaisesRegex(
                    LifecycleError, "d3t_patched_runtime_required"):
                self.manager.validate_deployment(d)
            d = self.manager.deployment(identifier)
            self.evidence()["image_id"] = self.d1["validation"]["image_id"]
            self.docker.image["Id"] = self.evidence()["image_id"]
            with self.assertRaisesRegex(LifecycleError, "d3t_patched_image_required"):
                self.manager.create_args(d)

    def test_attested_observed_drift_still_must_match_measured_runtime_image(self):
        self.evidence()["image_id"] = different_image(self.identity["Id"])
        self.docker.image["Id"] = self.evidence()["image_id"]
        for identifier in VARIANTS:
            with self.subTest(profile=identifier), self.assertRaisesRegex(
                    LifecycleError, "d3t_patched_image_required"):
                self.manager.create_args(self.manager.deployment(identifier))

    def test_generic_manager_evidence_reference_is_an_attestation_not_proof_parser(self):
        # Deliberately demonstrate the narrower retained Manager contract. Only
        # the binder tests may claim raw proof/source/recipe/label verification.
        self.evidence()["evidence"] = "controlled nonempty operator attestation"
        self.docker.image["Config"]["Labels"] = {}
        self.docker.image["Architecture"] = "controlled-unchecked-value"
        d = self.manager.deployment(next(iter(VARIANTS)))
        # Manager asks for the configured tag. It does not own a second tag
        # whitelist when a controlled alternate tag resolves to the same Id.
        d["_runtime"]["image_tag"] += "-controlled-alias"
        self.docker.tag = d["_runtime"]["image_tag"]
        argv = self.manager.create_args(d)
        self.assertIn(self.proof["image_id"], argv)


if __name__ == "__main__":
    unittest.main()
