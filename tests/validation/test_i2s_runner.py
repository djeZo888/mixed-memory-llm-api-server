"""Ordinary-user orchestration safety; these tests are not actual disk evidence."""
import importlib.util
import io
import json
from pathlib import Path
import sys
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
        for filename in ("scripts/install/disk_init.py", "scripts/install/storage.py", "scripts/install/storage_io.py", "tests/install/loop_disk_transaction.sh", ".github/workflows/i2s-linux.yml"):
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
        self.assertIn("/usr/bin/env -i", text)
        for forbidden in ("self-hosted", "secrets.", "apt-get", "continue-on-error", "workflow_dispatch:"):
            self.assertNotIn(forbidden, text)

    def test_exact_run_identity(self):
        data = {"id": 123, "head_sha": "a" * 40, "repository": {"full_name": ctl.REPOSITORY},
                "path": ctl.WORKFLOW, "head_branch": "milestone/i2s-storage-linux", "event": "push"}
        ctl.validate_run(data, 123, "a" * 40)
        for key, value in (("id", 124), ("head_sha", "b" * 40), ("path", ".github/workflows/i2p-linux.yml"),
                           ("head_branch", "main"), ("event", "workflow_dispatch")):
            with self.assertRaisesRegex(RuntimeError, "mismatched"):
                ctl.validate_run(dict(data, **{key: value}), 123, "a" * 40)

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
