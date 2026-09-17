import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
import warnings
import zipfile

PATH = Path(__file__).resolve().parents[2] / "scripts/validation/i2p/runnerctl.py"
SPEC = importlib.util.spec_from_file_location("i2p_runnerctl", PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class RunnerIdentity(unittest.TestCase):
    def valid(self):
        return {"id": 123, "head_sha": "a" * 40,
                "repository": {"full_name": MODULE.REPOSITORY}, "path": MODULE.WORKFLOW,
                "head_branch": "milestone/i2p-disposable-linux", "event": "push"}

    def test_valid(self):
        MODULE.validate_run(self.valid(), 123, "a" * 40)

    def test_mismatches_refuse(self):
        for key, value in (("id", 1), ("head_sha", "b" * 40), ("repository", {}),
                           ("path", ".github/workflows/ci.yml"), ("head_branch", "main"),
                           ("event", "pull_request")):
            with self.subTest(key=key):
                data = self.valid()
                data[key] = value
                with self.assertRaises(RuntimeError):
                    MODULE.validate_run(data, 123, "a" * 40)

    def archive(self, names):
        payload = io.BytesIO()
        with zipfile.ZipFile(payload, "w") as archive:
            for name in names:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", UserWarning)
                    archive.writestr(name, json.dumps({"synthetic": True}))
        return payload.getvalue()

    def test_only_sanitized_json_filenames_allowed(self):
        with tempfile.TemporaryDirectory() as root:
            output = Path(root) / "out"
            for names in (["../escape.json"], ["raw.log"],
                          list(MODULE.EVIDENCE_FILES) + ["evidence.json"]):
                with self.assertRaises(RuntimeError):
                    MODULE.unpack_evidence(self.archive(names), output)
                self.assertFalse(output.exists())

    def test_no_overwrite_private_collection(self):
        with tempfile.TemporaryDirectory() as root:
            output = Path(root) / "out"
            payload = self.archive(MODULE.EVIDENCE_FILES)
            MODULE.unpack_evidence(payload, output)
            self.assertEqual(output.stat().st_mode & 0o777, 0o700)
            self.assertEqual((output / "evidence.json").stat().st_mode & 0o777, 0o600)
            with self.assertRaises(FileExistsError):
                MODULE.unpack_evidence(payload, output)


if __name__ == "__main__":
    unittest.main()
