"""Ordinary-user orchestration safety; these tests are not actual disk evidence."""
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[2]


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts/validation/i2s" / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


run = load("test_i2s_runner_module", "run.py")
ctl = load("test_i2s_runnerctl_module", "runnerctl.py")


class RunnerTests(unittest.TestCase):
    def test_dry_run_has_no_subprocess_or_writes(self):
        with patch.object(sys, "argv", ["run.py", "--dry-run"]), patch.object(run.subprocess, "Popen", side_effect=AssertionError), patch.object(Path, "mkdir", side_effect=AssertionError), patch("sys.stdout", new_callable=io.StringIO) as output:
            self.assertEqual(run.main(), 0)
        self.assertEqual(json.loads(output.getvalue())["aggregate_backing_budget_bytes"], 2 * 1024**3)

    def test_context_refuses_unapproved_host_before_capability(self):
        with patch.object(sys, "argv", ["run.py", "--apply"]), patch.dict(run.os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "refuse_context:GITHUB_ACTIONS"):
                run.main()

    def test_environment_is_exact_allowlist(self):
        context = dict.fromkeys(run.CONTEXT_KEYS, "fixture")
        context["UNTRUSTED_SECRET"] = "must-not-forward"
        env = run.safe_environment(context)
        self.assertNotIn("UNTRUSTED_SECRET", env)
        self.assertEqual(set(env), set(run.CONTEXT_KEYS) | set(run.ENV))

    def test_cleanup_ambiguity_stops_matrix(self):
        for value in (None, "NOT_TESTED", "NOT_ATTEMPTED", "UNKNOWN", "INCOMPLETE", "FAIL", {"status": "INCOMPLETE"}, {}):
            self.assertTrue(run.cleanup_uncertain(value))
        self.assertFalse(run.cleanup_uncertain({"status": "PASS"}))

    def test_manifest_includes_real_disk_and_writer_code(self):
        manifest = run.source_manifest()
        for filename in ("scripts/install/disk_init.py", "scripts/install/storage.py", "scripts/install/storage_io.py", "tests/install/loop_disk_transaction.sh", "tests/install/test_loop_disk_fixture.py", ".github/workflows/i2s-linux.yml"):
            self.assertRegex(manifest[filename], "^[0-9a-f]{64}$")

    def test_namespace_cleanup_cannot_be_inferred_from_exit_code(self):
        complete = {"writer": {"status": "FAIL", "cleanup": {"status": "PASS"}},
                    "process": {"status": "PASS", "cleanup": {"status": "PASS"}}}
        self.assertTrue(run.namespace_cleanup_confirmed(complete))
        for status in ("INCOMPLETE", "UNKNOWN", "FAIL"):
            bad = dict(complete, writer={"cleanup": {"status": status}})
            self.assertFalse(run.namespace_cleanup_confirmed(bad))
        self.assertFalse(run.namespace_cleanup_confirmed({"status": "FAIL"}))
        self.assertFalse(run.namespace_cleanup_confirmed(dict(complete, stop_reason="probe_ownership_unresolved")))

    def test_namespace_persists_cleanup_stop_before_return(self):
        class Probe:
            @staticmethod
            def run_probe():
                return {"status": "FAIL", "cleanup": {"status": "INCOMPLETE"}}
        writes = []
        with patch.object(run.os, "readlink", return_value="private-namespace"), patch.dict(run.os.environ, {"I2S_PARENT_NAMESPACE": "parent-namespace"}), patch.object(run.subprocess, "run") as command, patch.object(run, "load", return_value=Probe) as imported, patch.object(run, "write_json", side_effect=lambda path, data: writes.append(json.loads(json.dumps(data)))):
            command.return_value.stdout = "private\n"
            self.assertEqual(run.namespace_child(Path("/fixture/evidence")), 1)
        self.assertEqual(imported.call_count, 1)
        self.assertEqual(writes[-1]["stop_reason"], "probe_ownership_unresolved")

    def test_workflow_scope_and_credentials(self):
        text = (ROOT / ".github/workflows/i2s-linux.yml").read_text()
        self.assertIn("runs-on: ubuntu-24.04", text)
        self.assertIn("paths: ['scripts/validation/i2s/launch.json']", text)
        self.assertIn("persist-credentials: false", text)
        self.assertIn("fetch-depth: 2", text)
        self.assertIn("branches: ['milestone/i2sf-loop-fixture']", text)
        self.assertIn("--apply --affected-only --output-dir", text)
        self.assertIn("--dry-run --affected-only", text)
        self.assertIn("-p 'test_loop_disk_fixture.py' -v", text)
        self.assertIn("/usr/bin/env -i", text)
        for forbidden in ("self-hosted", "secrets.", "apt-get", "continue-on-error", "workflow_dispatch:"):
            self.assertNotIn(forbidden, text)

    def test_exact_run_identity(self):
        data = {"id": 123, "head_sha": "a" * 40, "repository": {"full_name": ctl.REPOSITORY},
                "path": ctl.WORKFLOW, "head_branch": ctl.BRANCH, "event": "push"}
        ctl.validate_run(data, 123, "a" * 40)
        for key, value in (("id", 124), ("head_sha", "b" * 40), ("path", ".github/workflows/i2p-linux.yml"),
                           ("head_branch", "main"), ("event", "workflow_dispatch")):
            with self.assertRaisesRegex(RuntimeError, "mismatched"):
                ctl.validate_run(dict(data, **{key: value}), 123, "a" * 40)

    def test_old_run_collection_requires_explicit_old_branch(self):
        old_branch = "milestone/i2s-storage-linux"
        data = {"id": 123, "head_sha": "a" * 40, "repository": {"full_name": ctl.REPOSITORY},
                "path": ctl.WORKFLOW, "head_branch": old_branch, "event": "push"}
        with self.assertRaisesRegex(RuntimeError, "mismatched"):
            ctl.validate_run(data, 123, "a" * 40)
        ctl.validate_run(data, 123, "a" * 40, old_branch)
        with self.assertRaisesRegex(RuntimeError, "mismatched"):
            ctl.validate_run(dict(data, head_branch="main"), 123, "a" * 40, "main")

    def test_affected_dry_run_and_namespace_entry_refusal(self):
        with patch.object(sys, "argv", ["run.py", "--dry-run", "--affected-only"]), patch.object(run.subprocess, "Popen", side_effect=AssertionError), patch.object(Path, "mkdir", side_effect=AssertionError), patch("sys.stdout", new_callable=io.StringIO) as output:
            self.assertEqual(run.main(), 0)
        plan = json.loads(output.getvalue())
        self.assertEqual(plan["actual_backing_allocation_limit_bytes"], 256 * 1024**2)
        self.assertIn("extended loop matrix", plan["not_tested"])
        with patch.object(sys, "argv", ["run.py", "--namespace-apply", "--affected-only"]), patch("sys.stderr", new_callable=io.StringIO), patch.object(run, "load", side_effect=AssertionError):
            with self.assertRaises(SystemExit) as result:
                run.main()
        self.assertEqual(result.exception.code, 2)

    @staticmethod
    def snapshot():
        return {"namespace": "mnt:[original]", "mountinfo": b"exact original mountinfo\n",
                "loops": [{"name": "/dev/loop7", "back-ino": 123}], "scratch": set()}

    def test_shipped_failure_stops_even_with_unchanged_parent_and_cleanup_pass(self):
        evidence = {}
        with patch.object(run, "parent_snapshot", side_effect=[self.snapshot(), self.snapshot()]), patch.object(run, "write_json"), patch.object(run, "bounded", side_effect=[{"status": "PASS", "returncode": 0}, {"status": "FAIL", "returncode": 1, "cleanup": "PASS"}]) as command:
            with self.assertRaisesRegex(RuntimeError, "shipped_failure_stop_matrix"):
                run.run_shipped(evidence, Path("/fixture/output"), {})
        self.assertEqual([c.args[0][-1] for c in command.call_args_list], ["--dry-run", "--apply"])
        self.assertTrue(evidence["shipped_cleanup_observer"]["parent_mountinfo_unchanged"])
        self.assertEqual(evidence["shipped"]["returncode"], 1)

    def test_shipped_dry_run_failure_observes_parent_without_apply(self):
        evidence = {}
        with patch.object(run, "parent_snapshot", side_effect=[self.snapshot(), self.snapshot()]), patch.object(run, "write_json"), patch.object(run, "bounded", return_value={"status": "FAIL", "returncode": 2}) as command:
            with self.assertRaisesRegex(RuntimeError, "shipped_prerequisite_blocker_no_apply"):
                run.run_shipped(evidence, Path("/fixture/output"), {})
        self.assertEqual(command.call_count, 1)
        self.assertNotIn("shipped", evidence)
        self.assertTrue(evidence["shipped_cleanup_observer"]["parent_namespace_unchanged"])

    def test_unknown_parent_loop_inventory_is_not_empty(self):
        for payload in ("{}", '{"loopdevices": null}', '{"loopdevices": {}}', "[]"):
            with self.subTest(payload=payload), patch.object(run.subprocess, "run", return_value=SimpleNamespace(stdout=payload)):
                with self.assertRaisesRegex(RuntimeError, "unknown_parent_loop_inventory"):
                    run.loop_inventory()
        with patch.object(run.subprocess, "run", return_value=SimpleNamespace(stdout='{"loopdevices": []}')):
            self.assertEqual(run.loop_inventory(), [])

    def test_exact_parent_changes_stop_after_successful_shipped_command(self):
        for key, change in (("namespace", "mnt:[changed]"), ("mountinfo", b"changed mountinfo\n"),
                            ("loops", []), ("scratch", {Path("/run/i1s-loop-test")})):
            with self.subTest(key=key):
                after = dict(self.snapshot(), **{key: change})
                evidence = {}
                with patch.object(run, "parent_snapshot", side_effect=[self.snapshot(), after]), patch.object(run, "write_json"), patch.object(run, "bounded", return_value={"status": "PASS", "returncode": 0}):
                    with self.assertRaisesRegex(RuntimeError, "shipped_cleanup_unresolved_stop_matrix"):
                        run.run_shipped(evidence, Path("/fixture/output"), {})
                observer = evidence["shipped_cleanup_observer"]
                self.assertNotIn("mountinfo", observer)
                self.assertEqual(observer["parent_mountinfo_sha256_before"], run.hashlib.sha256(self.snapshot()["mountinfo"]).hexdigest())

    def test_affected_apply_never_enters_other_probes(self):
        guard = SimpleNamespace(validate_context=lambda context: None,
                                capability=lambda temp: {"status": "PASS"})
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "evidence"
            context = dict.fromkeys(run.CONTEXT_KEYS, "fixture")
            context.update(RUNNER_TEMP=directory, GITHUB_SHA="a" * 40)
            def shipped(evidence, output_dir, env):
                evidence["shipped"] = {"status": "PASS", "returncode": 0}
                return "mnt:[original]"
            with patch.object(sys, "argv", ["run.py", "--apply", "--affected-only", "--output-dir", str(output)]), patch.dict(run.os.environ, context, clear=True), patch.object(run, "load", return_value=guard) as imported, patch.object(run, "source_manifest", return_value={}), patch.object(run.subprocess, "run", return_value=SimpleNamespace(stdout="a" * 40)), patch.object(run, "bounded", return_value={"status": "PASS", "returncode": 0}) as command, patch.object(run, "run_shipped", side_effect=shipped), patch.object(run, "namespace_child", side_effect=AssertionError), patch.object(run.os, "umask"):
                self.assertEqual(run.main(), 0)
            evidence = json.loads((output / "evidence.json").read_text())
        self.assertEqual(imported.call_count, 1)
        self.assertEqual(evidence["status"], "PASS")
        self.assertEqual(evidence["extended_loop"]["status"], "NOT_TESTED")
        self.assertEqual(evidence["namespace_probes"]["status"], "NOT_TESTED")
        self.assertIn("wipefs", evidence["tool_versions"])
        self.assertFalse(any("unshare" in call.args[0] for call in command.call_args_list))

    def test_collected_artifact_is_bound_to_source_and_run(self):
        buffer = io.BytesIO()
        evidence = {"source_sha": "a" * 40, "github_run_id": "123", "github_run_attempt": "1"}
        with zipfile.ZipFile(buffer, "w") as archive:
            for filename in ctl.i2p.EVIDENCE_FILES:
                archive.writestr(filename, json.dumps(evidence if filename == "evidence.json" else {}))
        self.assertIn("evidence.json", ctl.validate_payload(buffer.getvalue(), "a" * 40, 123, 1))
        with self.assertRaisesRegex(RuntimeError, "identity_mismatch"):
            ctl.validate_payload(buffer.getvalue(), "b" * 40, 123, 1)

    def test_artifact_path_traversal_refused(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("../evidence.json", "{}")
        with self.assertRaisesRegex(RuntimeError, "unexpected_artifact_files"):
            ctl.validate_payload(buffer.getvalue(), "a" * 40, 123, 1)


if __name__ == "__main__":
    unittest.main()
