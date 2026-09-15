"""Portable safety checks; no bind, systemd, package or Linux PASS implied."""
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[2]
HERE = ROOT / "scripts/validation/i2r"


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RUN = load("i2r_orchestration", "run.py")
CONTROL = load("i2r_control", "runnerctl.py")


class OrchestrationSafety(unittest.TestCase):
    def test_dry_run_is_portable_and_names_only_two_fake_bindings(self):
        p = subprocess.run([sys.executable, str(HERE / "run.py"), "--dry-run"],
                           capture_output=True, text=True, timeout=10)
        self.assertEqual(p.returncode, 0, p.stderr)
        plan = json.loads(p.stdout)
        self.assertEqual(plan["binds"], ["/usr/bin/apt-get", "/usr/bin/dpkg"])
        self.assertTrue(plan["readonly_binds"])
        self.assertIn("I1c_mount_loss_gate_marker_writes", plan["not_tested"])

    def test_mutation_refuses_empty_environment_before_output_creation(self):
        with tempfile.TemporaryDirectory() as d:
            output = Path(d) / "missing"
            p = subprocess.run([sys.executable, str(HERE / "run.py"), "--output-dir", str(output)],
                               env={}, capture_output=True, timeout=10)
            self.assertNotEqual(p.returncode, 0)
            self.assertFalse(output.exists())

    def test_exception_text_is_never_relayed(self):
        self.assertEqual(RUN.safe_code(RuntimeError("private arbitrary output")), "RuntimeError")

    def test_run_controller_rejects_wrong_ownership(self):
        record = {"id": 1, "head_sha": "a" * 40,
                  "repository": {"full_name": CONTROL.REPOSITORY},
                  "path": CONTROL.WORKFLOW, "head_branch": "milestone/i2r-package-linux", "event": "push"}
        CONTROL.validate_run(record, 1, "a" * 40)
        for key, wrong in (("id", 2), ("head_sha", "b" * 40), ("head_branch", "main"),
                           ("path", ".github/workflows/i2p-linux.yml"), ("event", "pull_request")):
            with self.subTest(key=key), self.assertRaises(RuntimeError):
                CONTROL.validate_run({**record, key: wrong}, 1, "a" * 40)

    def test_artifact_rejects_extra_or_traversal_paths(self):
        payload = io.BytesIO()
        with zipfile.ZipFile(payload, "w") as z:
            for name in CONTROL.EVIDENCE_FILES | {"../unexpected.json"}:
                z.writestr(name, "{}")
        with tempfile.TemporaryDirectory() as d, self.assertRaises(RuntimeError):
            CONTROL.unpack_evidence(payload.getvalue(), Path(d) / "evidence")

    def test_workflow_has_fixed_ephemeral_runner_and_pre_sudo_scrub(self):
        s = (ROOT / ".github/workflows/i2r-linux.yml").read_text()
        self.assertIn("runs-on: ubuntu-24.04", s)
        self.assertIn("persist-credentials: false", s)
        self.assertIn("contents: read", s)
        self.assertNotIn("secrets.", s)
        self.assertNotIn("self-hosted", s)
        self.assertIn("/usr/bin/env -i PATH=/usr/sbin:/usr/bin:/sbin:/bin", s)


if __name__ == "__main__":
    unittest.main()
