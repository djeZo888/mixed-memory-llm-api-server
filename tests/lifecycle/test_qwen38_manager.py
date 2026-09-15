"""Q38 dispatch against real Manager methods with synthetic evidence/inspect.

No Docker daemon, key, model or VM is used. Existing lease/storage/start suites
exercise retained transaction behavior; these checks cover the new dispatch.
"""
import copy
from contextlib import contextmanager
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from lifecycle.manager import Manager
from lifecycle import qwen38 as q
from lifecycle import runtime_io
from lifecycle.runtime_io import LifecycleError
from runtime import qwen38_oci as oci
from tests.lifecycle.test_qwen38 import BindingFixture, auth_receipt, container
from tests.lifecycle.test_qwen38_oci import inspected


class InspectFixture:
    def __init__(self, image):
        self.image = image
        self.calls = []

    def capture(self, *args, **kwargs):
        self.calls.append(args)
        if args == ("image", "inspect", q.IMAGE_REFERENCE):
            return json.dumps([self.image])
        if args == ("info", "--format", "{{.DockerRootDir}}"):
            return "/srv/ai/docker"
        raise AssertionError("only pinned image inspection is allowed in this fixture")


class ManagerDispatch(unittest.TestCase):
    def setUp(self):
        self.binding = BindingFixture()
        self.binding.identity = {"fixture": "Q38 dispatch only"}
        self.manager = Manager(ROOT / "configs", {"schema_version": 1,
            "id": "q38-worker-fixture", "storage_identity": self.binding.identity,
            "paths": {"state": {"role": "data", "suffix": "services/llm-manager/active"}}},
            binding=self.binding, test_paths=True)
        self.d = self.manager.deployment("qwen38-27b-128k")
        self.proof, instance = auth_receipt(self.d)
        self.manager.instance.update(instance)
        self.inspected = inspected()
        self.inspected["Config"]["Env"] = [k + "=" + v
            for k, v in self.d["_runtime"]["image_environment"].items()]
        self.docker = InspectFixture(self.inspected)
        self.manager.docker = self.docker
        self.launcher = patch.object(q, "_protected_bytes",
                                     return_value=(ROOT / "scripts/runtime/sglang38_file_auth.py").read_bytes())
        self.launcher.start()
        self.addCleanup(self.launcher.stop)

    def evidence(self):
        return self.manager.instance["runtime_evidence"][q.RUNTIME]

    def use_domain(self, domain):
        image = inspected(domain)
        image["Config"]["Env"] = self.inspected["Config"]["Env"]
        self.docker.image = image
        block = oci.verify_image(image)
        self.proof["docker_inspect"] = block
        self.evidence()["docker_inspect"] = block
        # BindingFixture retains the synthetic proof object in its document map.
        self.binding.documents[self.binding.path("data", q.PROOF_SUFFIX)] = self.proof

    @contextmanager
    def preflight_host_metadata(self):
        """Bound host mount metadata only; repo reads retain real worker I/O."""
        paths = {m["source"]: m["target"] not in
                 {q.LAUNCHER_TARGET, self.d["auth"]["container_key_file"]}
                 for m in self.d["mounts"]}
        real_resolve, real_exists, real_is_dir = Path.resolve, Path.exists, Path.is_dir
        with patch.object(Path, "resolve", lambda p, *a, **kw: p if str(p) in paths else real_resolve(p, *a, **kw)), \
                patch.object(Path, "exists", lambda p: True if str(p) in paths else real_exists(p)), \
                patch.object(Path, "is_dir", lambda p: paths[str(p)] if str(p) in paths else real_is_dir(p)):
            yield

    def test_both_exact_profile_variants_bind_through_manager(self):
        for identifier, context in q.VARIANTS.items():
            d = self.manager.deployment(identifier)
            self.assertEqual(Manager.backend(d), "sglang_qwen38")
            self.assertIs(Manager.sglang_adapter(d), q)
            self.assertEqual(d["launch"]["context_size"], context)
            self.assertEqual(d["paths"]["model"], "/mnt/models/" + q.MODEL)
            self.assertEqual(d["launch"]["gpus"], ["0"])

    def test_unknown_backend_disguised_shared_backend_and_third_variant_refuse(self):
        for backend in ("unknown", "sglang", "llama_cpp"):
            bad = copy.deepcopy(self.d); bad["_runtime"]["backend"] = backend
            with self.subTest(backend=backend), self.assertRaises(LifecycleError):
                self.manager.validate_deployment(bad)
        bad = copy.deepcopy(self.d); bad["id"] = "qwen38-27b-1m"
        with self.assertRaises(LifecycleError):
            self.manager.validate_deployment(bad)

    def test_create_pinned_reference_never_pulls_for_both_accepted_domains(self):
        for domain in ("oci_config", "oci_platform_manifest"):
            self.use_domain(domain)
            argv = self.manager.create_args(self.d)
            self.assertEqual(self.docker.calls[-1], ("image", "inspect", q.IMAGE_REFERENCE))
            self.assertEqual(argv[argv.index(q.IMAGE_REFERENCE) - 1], "--pull=never")
            self.assertEqual(argv[argv.index(q.IMAGE_REFERENCE) + 1:], q.command(self.d))
            self.assertNotIn(q.IMAGE_ID, argv)
            self.assertNotIn(self.d["_runtime"]["image_tag"], argv)
            self.assertEqual(argv[argv.index("--gpus") + 1], '"device=0"')
            self.assertEqual(argv[argv.index("--publish") + 1], "127.0.0.1:30004:30004/tcp")
            self.assertEqual(argv.count("--mount"), 6)
            self.assertIn("--read-only", argv)

    def test_missing_actual_auth_receipt_refuses_before_image_inspection(self):
        self.binding.documents.clear()
        with self.assertRaises(LifecycleError):
            self.manager.create_args(self.d)
        self.assertEqual(self.docker.calls, [])

    def test_256k_creation_keeps_native_context_and_exact_gpu0_contract(self):
        self.use_domain("oci_platform_manifest")
        d = self.manager.deployment("qwen38-27b-256k")
        argv = self.manager.create_args(d)
        command = argv[argv.index(q.IMAGE_REFERENCE) + 1:]
        self.assertEqual(command[command.index("--context-length") + 1], "262144")
        self.assertEqual(command[command.index("--max-total-tokens") + 1], "262144")
        self.assertEqual(command[command.index("--tp-size") + 1], "1")
        self.assertEqual(command[command.index("--base-gpu-id") + 1], "0")
        self.assertEqual(command, q.command(d))
        self.assertNotIn("--speculative-algorithm", command)

    def test_prepare_auth_gate_precedes_key_metadata_and_any_docker_inspection(self):
        self.binding.documents.clear()
        self.manager.instance.update(obsolete_boot_owner_disabled=True,
                                     obsolete_boot_owner_evidence="SYNTHETIC source fixture")
        with patch.object(self.manager, "check_sources"), patch.object(self.manager, "host_guards"), \
                patch.object(self.manager, "check_artifacts"), \
                patch("lifecycle.manager.validate_key_metadata") as metadata, \
                patch.object(runtime_io, "_read_key", side_effect=AssertionError("unexpected key read")) as key:
            with self.assertRaises(LifecycleError):
                self.manager.prepare_start(self.d)
        metadata.assert_not_called()
        key.assert_not_called()
        self.assertEqual(self.docker.calls, [])

    def test_prepare_current_image_environment_drift_refuses_without_key_read(self):
        self.use_domain("oci_config")
        self.docker.image["Config"]["Env"] = self.docker.image["Config"]["Env"] + ["HOME=/unreviewed"]
        self.manager.instance.update(obsolete_boot_owner_disabled=True,
                                     obsolete_boot_owner_evidence="SYNTHETIC source fixture")
        with patch.object(self.manager, "check_sources"), patch.object(self.manager, "host_guards"), \
                patch.object(self.manager, "check_artifacts"), self.preflight_host_metadata(), \
                patch("lifecycle.manager.validate_key_metadata") as metadata, \
                patch.object(runtime_io, "_read_key", side_effect=AssertionError("unexpected key read")) as key:
            with self.assertRaisesRegex(LifecycleError, "qwen38_image_environment_mismatch"):
                self.manager.prepare_start(self.d)
        metadata.assert_called_once_with(self.d["auth"]["key_file"])
        key.assert_not_called()
        self.assertEqual(self.docker.calls, [("info", "--format", "{{.DockerRootDir}}"),
                                           ("image", "inspect", q.IMAGE_REFERENCE)])

    def test_inspect_or_proof_domain_drift_refuses_before_arguments_return(self):
        self.use_domain("oci_config")
        for name, value in (("Id", "sha256:" + "a" * 64), ("Architecture", "arm64"),
                            ("RepoDigests", [])):
            original = self.docker.image[name]
            self.docker.image[name] = value
            with self.subTest(name=name), self.assertRaises(LifecycleError):
                self.manager.create_args(self.d)
            self.docker.image[name] = original
        self.docker.image = inspected("oci_platform_manifest")
        self.docker.image["Config"]["Env"] = self.inspected["Config"]["Env"]
        with self.assertRaises(LifecycleError):
            self.manager.create_args(self.d)

    def test_installer_observed_domain_must_match_protected_proof_before_inspect(self):
        self.use_domain("oci_config")
        self.evidence()["docker_inspect"] = oci.expected_evidence(oci.MANIFEST_DIGEST)
        with self.assertRaisesRegex(LifecycleError, "qwen38_installer_observed_identity_mismatch"):
            self.manager.create_args(self.d)
        self.assertEqual(self.docker.calls, [])

    def test_same_image_digest_with_entrypoint_source_or_environment_drift_refuses(self):
        self.use_domain("oci_config")
        valid = copy.deepcopy(self.docker.image)
        changes = [("Entrypoint", ["python3"]), ("WorkingDir", "/tmp"),
                   ("Env", valid["Config"]["Env"] + [valid["Config"]["Env"][0]]),
                   ("Labels", {"org.opencontainers.image.revision": q.SOURCE_REVISION})]
        for key, value in changes:
            self.docker.image = copy.deepcopy(valid)
            self.docker.image["Config"][key] = value
            with self.subTest(key=key), self.assertRaises(LifecycleError):
                self.manager.create_args(self.d)

    def test_reuse_consumes_observed_image_domain_and_rejects_substitution(self):
        for domain in ("oci_config", "oci_platform_manifest"):
            self.use_domain(domain)
            c = container(self.d)
            c["Image"] = self.evidence()["docker_inspect"]["image_id"]
            self.manager.validate_reused_contract(c, self.d)
            c["Image"] = oci.MANIFEST_DIGEST if c["Image"] == oci.CONFIG_DIGEST else oci.CONFIG_DIGEST
            with self.assertRaisesRegex(LifecycleError, "runtime_image_id_mismatch"):
                self.manager.validate_reused_contract(c, self.d)

    def test_observe_rejects_reused_environment_drift_before_key_reading_probe(self):
        self.use_domain("oci_config")
        c = container(self.d)
        c["State"] = {"Running": True, "Status": "running"}
        c["NetworkSettings"]["Ports"] = copy.deepcopy(c["HostConfig"]["PortBindings"])
        c["Config"]["Env"].append("HOME=/unreviewed")
        self.manager.state.update(selected=self.d["id"], desired="running", observed="ready",
                                  container={"deployment": self.d["id"]})
        self.manager.sglang_probe = Mock(side_effect=AssertionError("probe before reuse validation"))
        with patch.object(self.manager, "trusted_container", return_value=c), \
                patch.object(self.manager, "deployment", return_value=self.d), \
                patch.object(runtime_io, "_read_key", side_effect=AssertionError("unexpected key read")) as key:
            observed = self.manager.observe()
        self.assertEqual(observed["observed"], "unhealthy")
        self.assertTrue(observed["container_running"])
        self.manager.sglang_probe.assert_not_called()
        key.assert_not_called()

    def test_completion_adapter_is_required_before_artifact_stat(self):
        with patch.object(self.manager, "check_sources"), \
                patch.object(q, "check_completion", side_effect=LifecycleError("q38_fixture_incomplete")) as checked, \
                patch.object(Path, "stat", side_effect=AssertionError("artifact read before completion")):
            with self.assertRaisesRegex(LifecycleError, "q38_fixture_incomplete"):
                self.manager.check_artifacts(self.d)
        checked.assert_called_once_with(self.d, self.manager.instance)

    def test_sglang_probe_dispatch_preserves_auth_and_uses_native_readiness(self):
        self.manager.sglang_probe = Mock(return_value="not_ready")
        self.manager.probe = Mock(side_effect=AssertionError("wrong backend probe"))
        self.assertEqual(self.manager.probe_deployment(self.d, 2), "not_ready")
        self.manager.sglang_probe.assert_called_once_with("http://127.0.0.1:30004/v1", "qwen3.8-27b",
            self.d["auth"]["key_file"], require_auth=True, timeout=2)


if __name__ == "__main__":
    unittest.main()
