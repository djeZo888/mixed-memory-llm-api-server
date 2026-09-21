"""Synthetic JSONL credential echoes through the ordinary verifier artifacts."""

import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import verify
from client_common import encode_key
from test_verify_events import encoded, passing_events


class SerializedCredentialTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path.home().resolve(), prefix="v2r-redaction-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.root.chmod(0o700)
        # Deliberately synthetic. All three complete representations differ:
        # raw, ordinary JSON escaping, and OpenCode's additional brace escaping.
        self.key = 'v2r-synthetic-"\\-{literal}-only'
        self.plain = json.dumps(self.key)[1:-1]
        self.opencode = encode_key(self.key.encode("ascii"))
        self.representations = (self.key, self.plain, self.opencode)
        self.assertEqual(len(set(self.representations)), 3)

    def assert_no_complete_secret(self, value):
        if isinstance(value, bytes):
            value = value.decode("utf-8", "replace")
        if isinstance(value, str):
            for representation in self.representations:
                self.assertNotIn(representation, value)
        elif isinstance(value, dict):
            for key, item in value.items():
                self.assert_no_complete_secret(key)
                self.assert_no_complete_secret(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                self.assert_no_complete_secret(item)

    def artifact_case(self, failed):
        prefix = self.root / "prefix"
        prefix.mkdir(mode=0o700)
        output = self.root / "run"
        settings = {"auth": {"kind": "env", "reference": "V2R_SYNTHETIC_REDACTION_KEY"},
                    "base_url": "http://127.0.0.1:1/v1", "model": "synthetic"}
        success = {"stdout": b"", "stderr": b"Ran 3 tests in 0.001s\nOK\n", "exit_code": 0,
                   "timed_out": False, "output_limited": False, "process_tree_reaped": True}
        diagnostic = " | ".join(self.representations)
        calls = []

        def execute(argv, workspace, env, **kwargs):
            calls.append(argv)
            if len(calls) == 1:
                self.assertEqual(argv, list(verify.FIXED_ARGV))
                return dict(success, stderr=b"Ran 3 tests in 0.001s\nFAILED (failures=5)\n", exit_code=1)
            if len(calls) == 2:
                self.assertEqual(env[verify.KEY_ENV], self.opencode)
                source = workspace / "text_utils.py"
                source.write_text(source.read_text().replace('text.split(" ")', "text.split()"))
                events = passing_events(workspace)
                events[1]["part"]["state"]["output"] = "Synthetic tool echo: " + self.key
                events[11]["part"]["text"] = "Synthetic final echo: " + self.key
                if failed:
                    events.insert(-3, {"type": "error", "error": {"message": self.key}})
                stdout = encoded(events)
                # This actual json.dumps JSONL boundary is the reviewed gap.
                self.assertIn(self.plain.encode(), stdout)
                self.assertNotIn(self.key.encode(), stdout)
                self.assertNotIn(self.opencode.encode(), stdout)
                return dict(success, stdout=stdout, stderr=diagnostic.encode(),
                            exit_code=1 if failed else 0,
                            # Synthetic runner metadata exercises both report
                            # and raw-evidence recursion without mocking the
                            # production parser, scrubber, or artifact writers.
                            synthetic_evidence={"text": diagnostic,
                                                "bytes": diagnostic.encode() + b"\xff",
                                                "nested": (diagnostic, [diagnostic.encode()])})
            self.assertEqual(argv, list(verify.FIXED_ARGV))
            self.assertNotIn(verify.KEY_ENV, env)
            return dict(success)

        # Serialization must retain current provenance, not the archived V2R snapshot.
        expected_manifest = verify.source_manifest()
        with mock.patch.object(verify, "verify_client", return_value=(settings, {})), \
             mock.patch.object(verify, "versions", return_value={}), \
             mock.patch.object(verify, "observe_model", return_value="synthetic"), \
             mock.patch.object(verify, "run_bounded", side_effect=execute), \
             mock.patch.dict(os.environ, {settings["auth"]["reference"]: self.key}):
            result = verify.verify(prefix, output, 10)

        self.assertEqual(len(calls), 3)
        self.assertEqual(result["status"], "FAIL" if failed else "PASS")
        saved = {}
        for name in ("report.json", "raw-evidence.json"):
            artifact = (output / name).read_bytes()
            self.assert_no_complete_secret(artifact)
            # Check the serialized complete representations too; outer JSON
            # escaping must not conceal a secret still present after decoding.
            for representation in self.representations:
                self.assertNotIn(json.dumps(representation)[1:-1].encode(), artifact)
            saved[name] = json.loads(artifact)
            self.assert_no_complete_secret(saved[name])
            self.assertEqual((output / name).stat().st_mode & 0o777, 0o600)
        report, raw = saved["report.json"], saved["raw-evidence.json"]
        self.assertEqual(report["status"], result["status"])
        self.assertEqual(report["artifacts"], expected_manifest)
        self.assertEqual(report["raw_evidence_sha256"],
                         hashlib.sha256((output / "raw-evidence.json").read_bytes()).hexdigest())
        lines = [json.loads(line) for line in raw["opencode"]["stdout"].splitlines()]
        self.assert_no_complete_secret(lines)
        self.assertEqual(lines[1]["part"]["state"]["output"], "Synthetic tool echo: [REDACTED]")
        self.assertEqual(report["process"]["synthetic_evidence"]["text"],
                         "[REDACTED] | [REDACTED] | [REDACTED]")
        self.assertEqual(raw["opencode"]["synthetic_evidence"]["bytes"],
                         "[REDACTED] | [REDACTED] | [REDACTED]\ufffd")
        self.assertFalse((output / "receipt.json").exists())
        if failed:
            self.assertIn("native_error_event", report["failures"])
            self.assertIn("opencode_process_failed", report["failures"])
            self.assertEqual(next(line for line in lines if line["type"] == "error")["error"]["message"],
                             "[REDACTED]")
        else:
            self.assertEqual(report["failures"], [])
            self.assertTrue(all(report["checks"].values()))

    def test_combined_character_jsonl_success_artifacts_are_redacted(self):
        self.artifact_case(failed=False)

    def test_combined_character_jsonl_failure_artifacts_are_redacted(self):
        self.artifact_case(failed=True)


if __name__ == "__main__":
    unittest.main()
