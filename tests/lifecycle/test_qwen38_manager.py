"""Q38 dispatch against real Manager methods with synthetic evidence/inspect.

No Docker daemon, key, model or VM is used. Existing lease/storage/start suites
exercise retained transaction behavior; these checks cover the new dispatch.
"""
import copy
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from lifecycle.manager import Manager
from lifecycle import qwen38 as q
from lifecycle import qwen_next
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

    def test_both_native_profiles_create_exact_core_limit_before_image(self):
        for identifier in q.VARIANTS:
            with self.subTest(identifier=identifier):
                d = self.manager.deployment(identifier)
                argv = self.manager.create_args(d)
                self.assertEqual(argv.count("--ulimit"), 1)
                self.assertEqual(argv.count("core=1:1"), 1)
                option = argv.index("--ulimit")
                self.assertEqual(argv[option + 1], "core=1:1")
                self.assertLess(option + 1, argv.index(q.IMAGE_REFERENCE))

    def test_both_native_profiles_reuse_core_with_unrelated_daemon_limits(self):
        for identifier in q.VARIANTS:
            d = self.manager.deployment(identifier)
            for unrelated in ([], [{"Name": "nofile", "Soft": 1024, "Hard": 65536},
                                   {"Name": "memlock", "Soft": -1, "Hard": -1}]):
                with self.subTest(identifier=identifier, unrelated=unrelated):
                    c = container(d)
                    c["HostConfig"]["Ulimits"] += unrelated
                    before = copy.deepcopy(c["HostConfig"]["Ulimits"])
                    self.manager.validate_reused_contract(c, d)
                    self.assertEqual(c["HostConfig"]["Ulimits"], before)

    def test_both_native_profiles_refuse_invalid_core_before_start(self):
        exact = {"Name": "core", "Soft": 1, "Hard": 1}
        missing = object()
        invalid = [missing, None, [], {}, "core=1:1", [None],
                   [{"Name": "nofile", "Soft": 1024, "Hard": 65536}],
                   [exact, dict(exact)], [exact, {"Name": "core", "Soft": 0, "Hard": 0}]]
        for field in ("Soft", "Hard"):
            for value in (0, -1, 2, True, False, "1", 1.0, None, [], {}):
                invalid.append([dict(exact, **{field: value})])
            absent = dict(exact)
            absent.pop(field)
            invalid.append([absent])
        self.docker.start = Mock(side_effect=AssertionError("start before core validation"))
        for identifier in q.VARIANTS:
            d = self.manager.deployment(identifier)
            for limits in invalid:
                with self.subTest(identifier=identifier, limits=limits):
                    c = container(d)
                    if limits is missing:
                        c["HostConfig"].pop("Ulimits")
                    else:
                        c["HostConfig"]["Ulimits"] = copy.deepcopy(limits)
                    self.manager.state.update(selected=identifier, container={"deployment": identifier})
                    with patch.object(self.manager, "prepare_start"), \
                            patch.object(self.manager, "trusted_container", return_value=c):
                        with self.assertRaisesRegex(LifecycleError, "qwen38_reused_core_limit_mismatch"):
                            self.manager._start()
        self.docker.start.assert_not_called()

    def test_representative_glm_and_deferred_argv_bytes_unchanged(self):
        # NUL-separated argv snapshots captured from the authorized base before
        # Q38CORE edits. Host I/O is synthetic; production argv/validation run.
        expected = {
            "glm-5.3-ud-q4-k-xl-8k": "17983c7e1c181d89a407451a2106fe8f4e5c8ff3c8e3bb8f46a1fa7613a340f9",
            "qwen3-coder-next": "dd316e9e9d53f16a085ba6692331b6469e678b1653b5ef2a9a400fe8b789a9a5",
        }
        for identifier, digest in expected.items():
            with self.subTest(identifier=identifier):
                d = self.manager.deployment(identifier)
                rt = d["_runtime"]
                image_id = rt.get("image_id") or "sha256:" + "b" * 64
                self.manager.instance["runtime_evidence"][d["runtime"]] = {
                    "image_id": image_id, "flags_verified": True,
                    "supported_flags": rt["required_cli_flags"], "load_mode": "none",
                    "evidence": "SYNTHETIC unchanged argv regression",
                    "launcher_sha256": qwen_next.launcher_hash(), "auth_gate_passed": True,
                    "auth_gate_evidence": "SYNTHETIC unchanged argv regression"}
                image = {"Id": image_id, "Config": {"Entrypoint": rt["entrypoint"]}}
                installed = self.binding.path("data", qwen_next.LAUNCHER_SUFFIX)
                real_stat = Path.stat
                with patch.object(self.docker, "capture", return_value=json.dumps([image])), \
                        patch.object(qwen_next, "protected_bytes", return_value=
                                     (ROOT / "scripts/lifecycle/sglang_file_auth.py").read_bytes()), \
                        patch.object(Path, "stat", lambda p, *a, **kw: SimpleNamespace(st_mode=0o100644)
                                     if str(p) == installed else real_stat(p, *a, **kw)):
                    argv = self.manager.create_args(d)
                self.assertEqual(hashlib.sha256("\0".join(argv).encode()).hexdigest(), digest)
                self.assertNotIn("--ulimit", argv)

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
