"""Stdlib regressions for real, constrained client tools; no inference needed."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "agent"))
from fixture import Fixture, INITIAL_SOURCE, TEST_SOURCE
from protocol import AgentError, Budget


FIXED_SOURCE = "def add(a, b):\n    return a + b\n"


def call(ident, name, args):
    return {"id": ident, "type": "function", "function": {
        "name": name, "arguments": json.dumps(args)}}


def read_both(fixture):
    return fixture.execute_calls([
        call("read-calc", "read_file", {"path": "calc.py"}),
        call("read-tests", "read_file", {"path": "test_calc.py"}),
    ])


def write_fix(fixture, ident="write-fix"):
    return fixture.execute_calls([call(ident, "write_file", {"path": "calc.py", "content": FIXED_SOURCE})])


class FixtureTests(unittest.TestCase):
    def test_real_initial_failure_and_success_evidence(self):
        with Fixture() as fixture:
            workspace = fixture.path
            self.assertNotEqual(fixture.initial_result["exit_code"], 0)
            self.assertIn("FAILED", fixture.initial_result["output"])
            self.assertIn("Ran 3 tests", fixture.initial_result["output"])
            messages = read_both(fixture)
            self.assertEqual([message["tool_call_id"] for message in messages], ["read-calc", "read-tests"])
            self.assertTrue(all(message["role"] == "tool" for message in messages))
            write_fix(fixture)
            result = fixture.execute_calls([call("test-fix", "run_tests", {})])
            self.assertEqual(json.loads(result[0]["content"])["exit_code"], 0)
            evidence = fixture.verify_success()
            self.assertTrue(evidence["success"])
            self.assertTrue(evidence["implementation_changed"])
            self.assertTrue(evidence["tests_unchanged"])
            self.assertEqual(evidence["final_test"]["status"], "PASS")
            self.assertIn("-    return a - b", evidence["diff"])
            self.assertIn("+    return a + b", evidence["diff"])
            self.assertEqual([item["name"] for item in evidence["calls"]],
                             ["read_file", "read_file", "write_file", "run_tests"])
            self.assertEqual(evidence["calls"][-1]["result"]["version"], 1)
        self.assertFalse(workspace.exists())
        self.assertEqual(fixture.evidence(), evidence)

    def test_claim_and_final_independent_pass_do_not_replace_model_test(self):
        with Fixture() as fixture:
            read_both(fixture)
            write_fix(fixture)
            with self.assertRaisesRegex(AgentError, "request run_tests"):
                fixture.verify_success()
            self.assertTrue(fixture.evidence()["final_test"]["passed"])

    def test_missing_read_fails_even_with_fix_and_real_test(self):
        with Fixture() as fixture:
            write_fix(fixture)
            fixture.execute_calls([call("test-fix", "run_tests", {})])
            with self.assertRaisesRegex(AgentError, "request reads"):
                fixture.verify_success()

    def test_reads_after_fix_do_not_count_as_inspecting_bug(self):
        with Fixture() as fixture:
            write_fix(fixture)
            read_both(fixture)
            fixture.execute_calls([call("test-fix", "run_tests", {})])
            with self.assertRaisesRegex(AgentError, "before its first implementation change"):
                fixture.verify_success()

    def test_unchanged_implementation_never_passes(self):
        with Fixture() as fixture:
            read_both(fixture)
            fixture.execute_calls([call("write-no-change", "write_file", {"path": "calc.py", "content": INITIAL_SOURCE})])
            fixture.execute_calls([call("test-unchanged", "run_tests", {})])
            with self.assertRaisesRegex(AgentError, "actual implementation change"):
                fixture.verify_success()

    def test_test_must_follow_last_write_even_if_same_bytes(self):
        with Fixture() as fixture:
            read_both(fixture)
            write_fix(fixture)
            fixture.execute_calls([call("test-fix", "run_tests", {})])
            write_fix(fixture, "write-again")
            with self.assertRaisesRegex(AgentError, "after its last write"):
                fixture.verify_success()

    def test_tests_immutable_to_tool(self):
        with Fixture() as fixture:
            with self.assertRaisesRegex(AgentError, "immutable"):
                fixture.execute_calls([call("rewrite-tests", "write_file", {"path": "test_calc.py", "content": "pass\n"})])
            self.assertEqual((fixture.path / "test_calc.py").read_text(), TEST_SOURCE)

    def test_external_test_change_is_detected_and_report_retained(self):
        with Fixture() as fixture:
            tests = fixture.path / "test_calc.py"
            tests.chmod(0o600)
            tests.write_text("raise SystemExit(0)\n")
            with self.assertRaisesRegex(AgentError, "immutable fixture tests changed"):
                read_both(fixture)
        self.assertFalse(fixture.evidence()["tests_unchanged"])
        self.assertNotEqual(fixture.evidence()["tests_sha256"], fixture.evidence()["expected_tests_sha256"])
        self.assertEqual(fixture.evidence()["final_test"]["status"], "NOT_TESTED")

    def test_only_fresh_subdirectory_is_used(self):
        with tempfile.TemporaryDirectory() as parent:
            directory = Path(parent).resolve()
            sentinel = directory / "calc.py"
            sentinel.write_text("untouched")
            with Fixture(parent=directory) as first, Fixture(parent=directory) as second:
                self.assertNotEqual(first.path, second.path)
                self.assertEqual(first.path.parent, directory)
                self.assertEqual(sentinel.read_text(), "untouched")
            self.assertEqual(sentinel.read_text(), "untouched")

    def test_tools_need_active_fixture(self):
        fixture = Fixture()
        with self.assertRaisesRegex(AgentError, "active fresh disposable"):
            read_both(fixture)
        with fixture:
            pass
        with self.assertRaisesRegex(AgentError, "active fresh disposable"):
            read_both(fixture)

    def test_paths_are_bounded_to_allowlist(self):
        bad_paths = ["/etc/passwd", "../calc.py", "a/../../calc.py", "a\\calc.py",
                     "./calc.py", "a//b", "a/../calc.py", "", "calc.py\x00", "missing.py", 4, None]
        with Fixture() as fixture:
            for index, path in enumerate(bad_paths):
                with self.subTest(path=path), self.assertRaises(AgentError):
                    fixture.execute_calls([call("bad-path-" + str(index), "read_file", {"path": path})])

    def test_symlink_file_cannot_be_read_or_written(self):
        with tempfile.TemporaryDirectory() as elsewhere:
            target = Path(elsewhere) / "target"
            target.write_text(INITIAL_SOURCE)
            with Fixture() as fixture:
                (fixture.path / "calc.py").unlink()
                (fixture.path / "calc.py").symlink_to(target)
                for name, args in [("read_file", {"path": "calc.py"}),
                                   ("write_file", {"path": "calc.py", "content": FIXED_SOURCE})]:
                    with self.subTest(name=name), self.assertRaisesRegex(AgentError, "symlink"):
                        fixture.execute_calls([call(name, name, args)])
            self.assertEqual(target.read_text(), INITIAL_SOURCE)

    def test_symlink_parent_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            parent = Path(temp).resolve()
            (parent / "real").mkdir()
            (parent / "alias").symlink_to(parent / "real", target_is_directory=True)
            with self.assertRaisesRegex(AgentError, "symlink"):
                with Fixture(parent=parent / "alias"):
                    self.fail("symlink parent accepted")

    def test_hard_link_rejected(self):
        with Fixture() as fixture:
            os.link(fixture.path / "calc.py", fixture.path / "second-link")
            with self.assertRaisesRegex(AgentError, "hard links"):
                read_both(fixture)

    def test_batch_dependencies_rejected_before_write(self):
        with Fixture() as fixture:
            batches = [
                [call("w1", "write_file", {"path": "calc.py", "content": FIXED_SOURCE}), call("t1", "run_tests", {})],
                [call("r1", "read_file", {"path": "calc.py"}), call("t2", "run_tests", {})],
                [call("w2", "write_file", {"path": "calc.py", "content": FIXED_SOURCE}),
                 call("w3", "write_file", {"path": "calc.py", "content": FIXED_SOURCE})],
            ]
            for batch in batches:
                with self.assertRaisesRegex(AgentError, "send each write_file or run_tests alone"):
                    fixture.execute_calls(batch)
                self.assertEqual((fixture.path / "calc.py").read_text(), INITIAL_SOURCE)
                self.assertEqual(fixture.calls, [])

    def test_malformed_json_and_schema(self):
        with Fixture() as fixture:
            malformed = ["{", "[]", "null", '{"path":"calc.py","path":"test_calc.py"}',
                         '{"path":NaN}', '{"path":"calc.py","extra":1}', '{}',
                         '{"path":"calc.py","content":"unused"}']
            for index, raw in enumerate(malformed):
                item = call("bad-json-" + str(index), "read_file", {})
                item["function"]["arguments"] = raw
                with self.subTest(raw=raw), self.assertRaises(AgentError):
                    fixture.execute_calls([item])
            for args in [{"command": "true"}, {"path": "calc.py"}]:
                with self.assertRaises(AgentError):
                    fixture.execute_calls([call("shell", "run_tests", args)])

    def test_unknown_tools_and_structures(self):
        with Fixture() as fixture:
            items = [call("unknown", "shell", {}), call("bad-name", [], {}),
                     {"id": "missing-function", "type": "function"},
                     {"id": "bad-type", "type": "other", "function": {"name": "run_tests", "arguments": "{}"}}]
            for item in items:
                with self.subTest(item=item), self.assertRaises(AgentError):
                    fixture.execute_calls([item])
            for items in [[], {}, [call(str(i), "run_tests", {}) for i in range(17)]]:
                with self.assertRaises(AgentError):
                    fixture.execute_calls(items)

    def test_ids_missing_invalid_duplicate_across_rounds(self):
        with Fixture() as fixture:
            for value in [None, "", 1, [], "has space", "x" * 129]:
                with self.subTest(value=value), self.assertRaisesRegex(AgentError, "valid ID"):
                    fixture.execute_calls([call(value, "read_file", {"path": "calc.py"})])
            item = call("missing", "read_file", {"path": "calc.py"})
            del item["id"]
            with self.assertRaises(AgentError):
                fixture.execute_calls([item])
            repeated = call("same", "read_file", {"path": "calc.py"})
            with self.assertRaisesRegex(AgentError, "duplicate tool ID"):
                fixture.execute_calls([repeated, repeated])
            fixture.execute_calls([repeated])
            with self.assertRaisesRegex(AgentError, "duplicate tool ID"):
                fixture.execute_calls([repeated])

    def test_code_subversion_rejected_before_write_or_execution(self):
        forbidden = [
            "import os\ndef add(a, b):\n return a + b\n",
            "def add(a, b):\n return __import__('os').system('true')\n",
            "def add(a, b):\n return a.__class__\n",
            "def add(a, b):\n while True: pass\n",
            "def add(a, b):\n return a ** 999999\n",
            "def add(a, b):\n return 1000001\n",
            "def add(a, b):\n return 1e999\n",
            "def add(a, b):\n return True\n",
            "def add(a, b):\n return 'text'\n",
            "def add(a, b):\n return [a,b]\n",
            "def add(a, b):\n return (x for x in [a,b])\n",
            "def add(a, b):\n return (lambda: 5)()\n",
            "@print\ndef add(a, b):\n return a + b\n",
            "def add(a: print('bad'), b):\n return a + b\n",
            "def add(a=print('bad'), b=0):\n return a + b\n",
            "def add(a, b):\n return a + b\nprint('bad')\n",
            "def add(a, b):\n return " + "+".join(["a"] * 100) + "\n",
            "def add(a, b):\n return " + "9" * 500 + "\n",
            "def add(a, b):\n return\n",
            "def add(a, b):\n return a + b\n#\ud800",
        ]
        with Fixture() as fixture:
            for index, source in enumerate(forbidden):
                with self.subTest(index=index), self.assertRaises(AgentError):
                    fixture.execute_calls([call("bad-code-" + str(index), "write_file", {"path": "calc.py", "content": source})])
                self.assertEqual((fixture.path / "calc.py").read_text(), INITIAL_SOURCE)

    def test_external_unsafe_code_never_runs(self):
        with Fixture() as fixture:
            (fixture.path / "calc.py").write_text("raise SystemExit(0)\n")
            with mock.patch("fixture.subprocess.Popen") as launch:
                with self.assertRaises(AgentError):
                    fixture.execute_calls([call("unsafe-test", "run_tests", {})])
                launch.assert_not_called()

    def test_output_and_arguments_bounded(self):
        with Fixture() as fixture:
            large = call("big-args", "write_file", {"path": "calc.py", "content": "#" * 17000})
            with self.assertRaisesRegex(AgentError, "bounded JSON"):
                fixture.execute_calls([large])
            (fixture.path / "calc.py").write_text("#" * 17000)
            with self.assertRaisesRegex(AgentError, "max_output_bytes"):
                fixture.execute_calls([call("big-read", "read_file", {"path": "calc.py"})])

    def test_subprocess_receives_no_inherited_credentials_and_fixed_command(self):
        real_popen = subprocess.Popen
        launches = []
        def inspect(*args, **kwargs):
            launches.append((args, kwargs))
            return real_popen(*args, **kwargs)
        with mock.patch.dict(os.environ, {"A1_FAKE_CREDENTIAL": "synthetic-only", "PYTHONPATH": "/untrusted"}):
            with mock.patch("fixture.subprocess.Popen", side_effect=inspect):
                with Fixture() as fixture:
                    fixture.execute_calls([call("test-fixed", "run_tests", {})])
        self.assertGreaterEqual(len(launches), 2)
        for args, kwargs in launches:
            self.assertEqual(args[0], [sys.executable, "-I", "-B", "test_calc.py"])
            self.assertNotIn("A1_FAKE_CREDENTIAL", kwargs["env"])
            self.assertNotIn("PYTHONPATH", kwargs["env"])
            self.assertFalse(kwargs.get("shell", False))
            self.assertTrue(kwargs["start_new_session"])

    def test_real_subprocess_timeout_is_bounded(self):
        real_popen = subprocess.Popen
        def sleepy(*args, **kwargs):
            return real_popen([sys.executable, "-I", "-c", "import time; time.sleep(5)"], **kwargs)
        with Fixture() as fixture:
            fixture.test_timeout = 0.05
            started = time.monotonic()
            with mock.patch("fixture.subprocess.Popen", side_effect=sleepy):
                with self.assertRaisesRegex(AgentError, "timeout"):
                    fixture.execute_calls([call("slow-test", "run_tests", {})])
            self.assertLess(time.monotonic() - started, 2)

    def test_real_subprocess_output_is_bounded(self):
        real_popen = subprocess.Popen
        def noisy(*args, **kwargs):
            return real_popen([sys.executable, "-I", "-c", "print('x' * 50000)"], **kwargs)
        with Fixture() as fixture:
            with mock.patch("fixture.subprocess.Popen", side_effect=noisy):
                with self.assertRaisesRegex(AgentError, "output exceeds"):
                    fixture.execute_calls([call("noisy-test", "run_tests", {})])

    def test_overall_budget_and_failure_evidence(self):
        with Fixture() as fixture:
            fixture.budget = Budget(0.001)
            time.sleep(0.01)
            with self.assertRaises(AgentError):
                read_both(fixture)
        self.assertEqual(fixture.evidence()["final_test"]["status"], "NOT_TESTED")
        self.assertIsNotNone(fixture.evidence()["initial_test"])

    def test_invalid_limits(self):
        for value in [0, -1, True, 1048577]:
            with self.assertRaises(AgentError):
                Fixture(max_output_bytes=value)
        for value in [0, -1, float("nan"), float("inf"), True]:
            with self.assertRaises(AgentError):
                Fixture(test_timeout=value)


if __name__ == "__main__":
    unittest.main()
