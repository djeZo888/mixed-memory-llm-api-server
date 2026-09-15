"""Native transcript refusal cases and real owned-process cleanup tests."""

import copy
import hashlib
import json
import os
from pathlib import Path
import secrets
import signal
import sys
import tempfile
import time
import unittest

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import verify_events as verifier


def native(kind, part, message="message-1"):
    return {"type": kind, "timestamp": 1000, "sessionID": "session-1",
            "part": {"id": "part-1", "sessionID": "session-1", "messageID": message,
                     "type": verifier.EVENT_TYPES[kind], **part}}


def tool(name, args, identity, output="Observed native tool output.", status="completed", **state):
    return native("tool_use", {"tool": name, "callID": identity,
                              "state": {"status": status, "input": args, "output": output,
                                        "metadata": {}, **state}})


def passing_events(workspace):
    return [
        native("step_start", {}),
        tool("read", {"filePath": str(workspace / "text_utils.py")}, "read-source"),
        tool("read", {"filePath": str(workspace / "test_text_utils.py")}, "read-test"),
        native("step_finish", {"reason": "tool-calls"}),
        native("step_start", {}),
        tool("edit", {"filePath": str(workspace / "text_utils.py"),
                      "oldString": 'text.split(" ")', "newString": "text.split()"}, "edit-source"),
        native("step_finish", {"reason": "tool-calls"}),
        native("step_start", {}),
        tool("bash", {"command": verifier.FIXED_COMMAND, "workdir": str(workspace)}, "test-call",
             output="...\n----------------------------------------------------------------------\nRan 3 tests in 0.001s\n\nOK\n",
             metadata={"exit": 0, "truncated": False}),
        native("step_finish", {"reason": "tool-calls", "tokens": {"input": 12, "output": 3,
                                                                       "cache": {"read": 4}}}),
        native("step_start", {}),
        native("text", {"text": "I fixed whitespace splitting; the requested tests passed."}),
        native("step_finish", {"reason": "stop"}),
    ]


def encoded(events):
    return b"".join(json.dumps(event).encode() + b"\n" for event in events)


class NativeEventTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="v2-native-")
        self.addCleanup(self.temp.cleanup)
        self.workspace = Path(self.temp.name).resolve()
        self.events = passing_events(self.workspace)

    def parse(self, events=None):
        return verifier.parse_events(encoded(self.events if events is None else events), self.workspace)

    def rejected(self, code, events=None):
        result = self.parse(events)
        self.assertNotEqual(result["result"], "pass")
        self.assertIn(code, result["failures"])
        return result

    def test_native_sequence_preserves_counts_identities_and_only_reported_usage(self):
        result = self.parse()
        self.assertEqual(result["result"], "pass")
        self.assertTrue(all(result["checks"].values()))
        self.assertEqual(result["event_counts"], {"step_start": 4, "step_finish": 4, "tool_use": 4, "text": 1})
        self.assertEqual([t["tool"] for t in result["tools"]], ["read", "read", "edit", "bash"])
        self.assertEqual(result["tools"][-1]["call_id_sha256"], hashlib.sha256(b"test-call").hexdigest())
        self.assertEqual(result["tools"][-1]["exit_code"], 0)
        self.assertEqual(result["steps"][2]["native_tokens"], {"input": 12, "output": 3, "cache": {"read": 4}})
        self.assertNotIn("native_tokens", result["steps"][0])
        self.assertEqual(result["provider_usage"], "NOT_REPORTED")

    def test_corrected_permission_denial_is_retained_without_hiding_later_success(self):
        denied = tool("read", {"filePath": "/outside/test_text_utils.py"}, "denied-read", status="error",
                      error=verifier.DENIAL_PREFIX + " external_directory permission deny")
        self.events.insert(2, denied)
        result = self.parse()
        self.assertEqual(result["result"], "pass")
        self.assertEqual(result["tools"][1]["classification"], "permission_denied")
        self.assertFalse(result["tools"][1]["path_within_workspace"])
        self.assertEqual(result["tools"][1]["status"], "error")

    def test_denied_wrong_command_is_not_counted_as_test_success(self):
        self.events[8]["part"]["state"].update(status="error", error=verifier.DENIAL_PREFIX)
        self.events[8]["part"]["state"]["input"]["command"] = "pwd"
        result = self.rejected("native_missing_passing_tool_result")
        self.assertFalse(result["checks"]["exact_test_command"])

    def test_executed_outside_read_and_path_traversal_fail(self):
        for path in ("/outside/test_text_utils.py", "../test_text_utils.py"):
            with self.subTest(path=path):
                events = copy.deepcopy(self.events)
                events[2]["part"]["state"]["input"]["filePath"] = path
                self.rejected("native_executed_outside_workspace", events)

    def test_symlink_outside_workspace_is_not_inside(self):
        (self.workspace / "escape").symlink_to(self.workspace.parent, target_is_directory=True)
        self.events[2]["part"]["state"]["input"]["filePath"] = "escape/test_text_utils.py"
        self.rejected("native_executed_outside_workspace")

    def test_wrong_or_compound_command_and_subdirectory_are_refused(self):
        for command, directory in (("python3 test_text_utils.py", self.workspace),
                                   (verifier.FIXED_COMMAND + "; echo OK", self.workspace),
                                   (verifier.FIXED_COMMAND, self.workspace / "nested")):
            with self.subTest(command=command, directory=directory):
                events = copy.deepcopy(self.events)
                events[8]["part"]["state"]["input"] = {"command": command, "workdir": str(directory)}
                self.rejected("native_executed_wrong_command", events)

    def test_missing_workdir_means_reviewed_launcher_workspace(self):
        del self.events[8]["part"]["state"]["input"]["workdir"]
        self.assertEqual(self.parse()["result"], "pass")

    def test_immutable_test_edit_is_never_accepted(self):
        for method in ("edit", "write"):
            with self.subTest(method=method):
                events = copy.deepcopy(self.events)
                events[5]["part"]["tool"] = method
                events[5]["part"]["state"]["input"]["filePath"] = str(self.workspace / "test_text_utils.py")
                self.rejected("native_edited_nonimplementation", events)

    def test_missing_read_and_edit_before_reads_fail(self):
        del self.events[2]
        self.rejected("native_edit_before_reads")

    def test_final_prose_alone_does_not_establish_success(self):
        self.rejected("native_final_before_passing_test", [self.events[10], self.events[11], self.events[12]])

    def test_zero_exit_without_actual_unittest_result_is_failure(self):
        self.events[8]["part"]["state"]["output"] = "The tests passed. OK."
        self.rejected("native_missing_passing_tool_result")

    def test_nonzero_missing_boolean_exit_or_failed_output_never_passes(self):
        for code, output in ((1, "Ran 3 tests in 0.001s\nOK\n"),
                             (None, "Ran 3 tests in 0.001s\nOK\n"),
                             (False, "Ran 3 tests in 0.001s\nOK\n"),
                             (0, "Ran 3 tests in 0.001s\nOK\nFAILED (failures=1)\n")):
            with self.subTest(exit=code):
                events = copy.deepcopy(self.events)
                events[8]["part"]["state"]["metadata"]["exit"] = code
                events[8]["part"]["state"]["output"] = output
                self.rejected("native_missing_passing_tool_result", events)

    def test_native_error_and_execution_error_are_failures(self):
        self.rejected("native_error_event", self.events + [{"type": "error", "error": {"message": "private"}}])
        self.events[2]["part"]["state"].update(status="error", error="File not found")
        self.rejected("native_tool_error")

    def test_length_is_token_exhaustion_even_with_all_prior_success(self):
        self.events[-1]["part"]["reason"] = "length"
        result = self.rejected("native_token_exhaustion")
        self.assertEqual(result["result"], "token_exhaustion")

    def test_missing_stop_partial_tool_duplicate_id_and_cross_session_refused(self):
        self.rejected("native_missing_terminal_stop", self.events[:-1])
        for status in ("pending", "running", "made-up"):
            events = copy.deepcopy(self.events)
            events[8]["part"]["state"]["status"] = status
            self.rejected("native_partial_tool", events)
        events = copy.deepcopy(self.events)
        events[2]["part"]["callID"] = events[1]["part"]["callID"]
        self.rejected("native_duplicate_call_id", events)
        events[2]["sessionID"] = events[2]["part"]["sessionID"] = "other-session"
        self.rejected("native_session_changed", events)

    def test_no_tool_after_terminal_stop(self):
        self.rejected("native_event_after_stop", self.events + [self.events[1]])

    def test_edit_after_pass_requires_another_actual_passing_test(self):
        events = copy.deepcopy(self.events)
        extra = copy.deepcopy(events[5])
        extra["part"]["callID"] = "edit-after-pass"
        events.insert(11, extra)
        self.rejected("native_missing_passing_tool_result", events)

    def test_malformed_partial_duplicate_keys_unknown_and_oversize_json_refused(self):
        for raw, code in ((b"", "native_events_empty"),
                          (b'{"type":', "native_partial_line"),
                          (b'{"type":\n', "native_malformed_json"),
                          (b'{"type":"text","type":"step_start"}\n', "native_malformed_json"),
                          (b'{"type":"extension"}\n', "native_unknown_event"),
                          (b'{"type":[]}\n', "native_unknown_event"),
                          (b'NaN\n', "native_malformed_json"),
                          (b"x" * (verifier.MAX_LINE + 1) + b"\n", "native_event_limit"),
                          (b"x" * (verifier.MAX_OUTPUT + 1), "native_output_limit")):
            with self.subTest(code=code):
                result = verifier.parse_events(raw, self.workspace)
                self.assertEqual(result["result"], "fail")
                self.assertIn(code, result["failures"])

    def test_untrusted_types_and_unicode_never_escape_parser_as_exception(self):
        for field, value in (("tool", []), ("callID", "\ud800"), ("state", [])):
            events = copy.deepcopy(self.events)
            events[1]["part"][field] = value
            self.assertEqual(self.parse(events)["result"], "fail")
        for field, value in (("reason", []), ("tokens", {"input": True}), ("cost", 10**400)):
            events = copy.deepcopy(self.events)
            events[9]["part"][field] = value
            self.assertEqual(self.parse(events)["result"], "fail")

    def test_secret_text_arguments_outputs_paths_and_native_ids_are_not_reported(self):
        forbidden = secrets.token_hex(32)
        self.events[1]["part"]["state"]["output"] = forbidden
        self.events[5]["part"]["state"]["input"]["newString"] = forbidden
        self.events[5]["part"]["state"]["output"] = forbidden
        self.events[11]["part"]["text"] = forbidden
        self.events[1]["part"]["callID"] = forbidden
        denied = tool("read", {"filePath": "/" + forbidden}, "denied", status="error",
                      error=verifier.DENIAL_PREFIX + forbidden)
        self.events.insert(2, denied)
        report = self.parse()
        self.assertEqual(report["result"], "pass")
        self.assertNotIn(forbidden, json.dumps(report))


@unittest.skipUnless(os.name == "posix", "The reviewed client targets macOS and Linux")
class BoundedProcessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="v2-process-")
        self.addCleanup(self.temp.cleanup)
        self.workspace = Path(self.temp.name).resolve()
        self.env = {"PATH": "/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE": "1"}

    def run_code(self, code, **kwargs):
        return verifier.run_bounded([sys.executable, "-I", "-B", "-c", code],
                                   self.workspace, self.env, **kwargs)

    def absent(self, pid):
        with self.assertRaises(ProcessLookupError):
            os.kill(pid, 0)

    def test_real_success_captures_both_streams_and_input_without_echoing(self):
        result = self.run_code("import sys; data=sys.stdin.buffer.read(); sys.stdout.buffer.write(data); sys.stderr.write('stderr')",
                               input=b"private input\n", timeout=3)
        self.assertEqual(result["stdout"], b"private input\n")
        self.assertEqual(result["stderr"], b"stderr")
        self.assertEqual(result["exit_code"], 0)
        self.assertTrue(result["process_tree_reaped"])
        self.assertFalse(result["timed_out"] or result["output_limited"])

    def test_real_nonzero_exit_is_preserved(self):
        result = self.run_code("raise SystemExit(7)", timeout=3)
        self.assertEqual(result["exit_code"], 7)
        self.assertTrue(result["process_tree_reaped"])

    def test_real_timeout_reaps_term_ignoring_process(self):
        result = self.run_code("import os,signal,time; from pathlib import Path; "
                               "signal.signal(signal.SIGTERM,signal.SIG_IGN); "
                               "Path('pid').write_text(str(os.getpid())); time.sleep(60)", timeout=0.2)
        self.assertTrue(result["timed_out"])
        self.assertTrue(result["process_tree_reaped"])
        self.assertLess(result["elapsed_seconds"], 5)
        self.absent(int((self.workspace / "pid").read_text()))

    def test_streaming_output_limit_terminates_before_unbounded_capture(self):
        result = self.run_code("import os; "
                               "exec('while True: os.write(1,b\"x\"*65536); os.write(2,b\"y\"*65536)')",
                               timeout=3, max_output=20000)
        self.assertTrue(result["output_limited"])
        self.assertEqual(len(result["stdout"]) + len(result["stderr"]), 20000)
        self.assertTrue(result["process_tree_reaped"])
        self.assertFalse(result["timed_out"])

    def descendant_case(self, detached=False, inherited_pipes=False):
        child = ("import os,signal,time; from pathlib import Path; "
                 "signal.signal(signal.SIGTERM,signal.SIG_IGN); "
                 "Path('descendant-pid').write_text(str(os.getpid())); time.sleep(60)")
        redirect = "" if inherited_pipes else ",stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL"
        code = ("import os,subprocess,sys,time\nfrom pathlib import Path\n"
                "Path('parent-pid').write_text(str(os.getpid()))\n"
                "p=subprocess.Popen([sys.executable,'-I','-B','-c'," + repr(child) + "],"
                "start_new_session=" + str(detached) + redirect + ")\n"
                "deadline=time.monotonic()+3\n"
                "while not Path('descendant-pid').exists():\n"
                " if time.monotonic()>deadline: raise SystemExit(2)\n"
                " time.sleep(.01)\n"
                "time.sleep(.2)\n")
        try:
            result = self.run_code(code, timeout=5)
            self.assertEqual(result["exit_code"], 0)
            self.assertTrue(result["process_tree_reaped"])
            self.assertFalse(result["timed_out"])
            self.assertLess(result["elapsed_seconds"], 4)
            self.absent(int((self.workspace / "parent-pid").read_text()))
            self.absent(int((self.workspace / "descendant-pid").read_text()))
        finally:
            for name in ("parent-pid", "descendant-pid"):
                file = self.workspace / name
                if file.exists():
                    try:
                        os.kill(int(file.read_text()), signal.SIGKILL)
                    except ProcessLookupError:
                        pass

    def test_successful_parent_cannot_leave_closed_pipe_descendant(self):
        self.descendant_case()

    def test_successful_parent_cannot_leave_inherited_pipe_descendant(self):
        self.descendant_case(inherited_pipes=True)

    def test_observed_detached_descendant_is_tracked_and_reaped(self):
        self.descendant_case(detached=True)

    def test_invalid_limits_are_rejected_before_execution(self):
        for kwargs in ({"timeout": 0}, {"timeout": float("inf")}, {"max_output": 0},
                       {"max_output": verifier.MAX_OUTPUT + 1}, {"input": "not bytes"},
                       {"cancel_requested": "not callable"}):
            with self.subTest(kwargs=kwargs), self.assertRaisesRegex(ValueError, "invalid_bounded_process_arguments"):
                self.run_code("raise SystemExit(99)", **kwargs)


if __name__ == "__main__":
    unittest.main()
