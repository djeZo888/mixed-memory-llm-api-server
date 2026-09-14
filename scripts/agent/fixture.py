"""Disposable, constrained client-side tools for the A1 repair acceptance task.

This deliberately is not a general Python execution sandbox. Only one tiny
arithmetic function can be edited; the trusted unittest fixture is immutable.
"""

from __future__ import annotations

import ast
import difflib
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import selectors
import signal
import stat
import subprocess
import sys
import tempfile
import time

if __package__:
    from .protocol import AgentError, Budget, strict_json_loads
else:
    from protocol import AgentError, Budget, strict_json_loads


INITIAL_SOURCE = "def add(a, b):\n    return a - b\n"
TEST_SOURCE = '''"""Trusted immutable acceptance tests; execute with python -I -B."""
import pathlib
import unittest

namespace = {"__builtins__": {}}
exec(compile(pathlib.Path("calc.py").read_text(encoding="utf-8"), "calc.py", "exec"), namespace)
add = namespace["add"]

class AddTests(unittest.TestCase):
    def test_positive(self):
        self.assertEqual(add(2, 3), 5)

    def test_negative(self):
        self.assertEqual(add(-4, -3), -7)

    def test_zero(self):
        self.assertEqual(add(9, 0), 9)
        self.assertEqual(add(0, 9), 9)

if __name__ == "__main__":
    unittest.main(verbosity=2)
'''


def _schema(name, description, properties, required):
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object", "properties": properties,
                "required": required, "additionalProperties": False,
            },
        },
    }


class Fixture:
    """Fresh temporary workspace with read_file, write_file and run_tests tools."""

    schemas = [
        _schema("read_file", "Read calc.py or the immutable test_calc.py fixture.",
                {"path": {"type": "string", "enum": ["calc.py", "test_calc.py"]}}, ["path"]),
        _schema("write_file", "Replace calc.py only. It must contain exactly def add(a, b): "
                "with one return of arithmetic using a, b, numeric literals and + - * /. "
                "No imports, calls, attributes, annotations, decorators or other statements. "
                "Send this write alone, then request run_tests in a later call.",
                {"path": {"type": "string", "enum": ["calc.py"]},
                 "content": {"type": "string"}}, ["path", "content"]),
        _schema("run_tests", "Execute the fixed trusted unittest command on the client. "
                "No command arguments accepted. Send this call alone after writing the fix.", {}, []),
    ]

    def __init__(self, parent=None, budget: Budget | None = None,
                 max_output_bytes=16384, test_timeout=10):
        if type(max_output_bytes) is not int or not 128 <= max_output_bytes <= 1048576:
            raise AgentError("max_output_bytes must be an integer from 128 to 1048576")
        if not isinstance(test_timeout, (float, int)) or isinstance(test_timeout, bool) \
                or not math.isfinite(test_timeout) or test_timeout <= 0:
            raise AgentError("test_timeout must be finite and positive")
        self.parent = Path(parent).absolute() if parent is not None else None
        self.budget = budget
        self.max_output_bytes = max_output_bytes
        self.test_timeout = test_timeout
        self.path = None
        self.initial_result = None
        self.calls = []
        self._seen_ids = set()
        self._temp = None
        self._version = 0
        self._root_identity = None
        self._started = time.monotonic()
        self._closed = False
        self._evidence_cache = None
        self._evidence_signature = None

    def __enter__(self):
        if self._temp is not None:
            raise AgentError("fixture cannot be entered twice")
        self._check_budget()
        if self.parent is not None:
            self._reject_symlinks(self.parent)
            if not self.parent.is_dir():
                raise AgentError("workspace parent must be an existing directory")
        # macOS's system temp path may use /var, itself an OS-managed symlink.
        # Resolve that default once; explicitly supplied parents reject symlinks.
        parent = self.parent if self.parent is not None else Path(tempfile.gettempdir()).resolve()
        self._temp = tempfile.TemporaryDirectory(prefix="a1-agent-", dir=parent)
        self.path = Path(self._temp.name).absolute()
        os.chmod(self.path, 0o700)
        self._root_identity = (self.path.stat().st_dev, self.path.stat().st_ino)
        try:
            (self.path / "calc.py").write_text(INITIAL_SOURCE, encoding="utf-8")
            (self.path / "test_calc.py").write_text(TEST_SOURCE, encoding="utf-8")
            os.chmod(self.path / "calc.py", 0o600)
            os.chmod(self.path / "test_calc.py", 0o400)
            self.initial_result = self._run_tests()
            if self.initial_result["exit_code"] == 0:
                raise AgentError("fixture setup failed: initial tests unexpectedly passed")
            return self
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def __exit__(self, *_):
        if self._temp is not None:
            self.evidence()
            self._closed = True
            self._temp.cleanup()
        return False

    def _check_budget(self):
        if self.budget is not None:
            self.budget.check()

    @staticmethod
    def _reject_symlinks(path):
        # Every existing ancestor is checked, including the workspace itself.
        for entry in [path, *path.parents]:
            try:
                if stat.S_ISLNK(entry.lstat().st_mode):
                    raise AgentError("symlink paths or ancestors are forbidden")
            except FileNotFoundError:
                continue

    def _workspace(self):
        if self._closed or self.path is None or self._root_identity is None:
            raise AgentError("tools require an active fresh disposable fixture")
        self._reject_symlinks(self.path)
        try:
            info = self.path.stat()
        except OSError:
            raise AgentError("disposable workspace no longer exists") from None
        if not stat.S_ISDIR(info.st_mode) or (info.st_dev, info.st_ino) != self._root_identity:
            raise AgentError("disposable workspace identity changed")

    def _file(self, value, writing=False):
        self._workspace()
        if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
            raise AgentError("path must be a plain relative fixture filename")
        pure = PurePosixPath(value)
        if pure.is_absolute() or ".." in pure.parts or value != pure.as_posix():
            raise AgentError("absolute, traversal and noncanonical paths are forbidden")
        if value not in {"calc.py", "test_calc.py"}:
            raise AgentError("only calc.py and test_calc.py belong to this fixture")
        if writing and value != "calc.py":
            raise AgentError("test_calc.py is immutable; edit calc.py instead")
        path = self.path / value
        self._reject_symlinks(path)
        try:
            info = path.stat()
        except OSError:
            raise AgentError("required fixture file is missing") from None
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise AgentError("fixture files must be regular files without hard links")
        return path

    def _read(self, filename):
        path = self._file(filename)
        # Size-limited read even if another local process replaces the file.
        with path.open("rb") as handle:
            data = handle.read(self.max_output_bytes + 1)
        if len(data) > self.max_output_bytes:
            raise AgentError("fixture file exceeds max_output_bytes")
        try:
            return data.decode("utf-8")
        except UnicodeError:
            raise AgentError("fixture files must be UTF-8") from None

    @staticmethod
    def _hash(text):
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def _integrity(self):
        self._workspace()
        if self._read("test_calc.py") != TEST_SOURCE:
            raise AgentError("immutable fixture tests changed; acceptance is invalid")

    def _validate_source(self, source):
        if not isinstance(source, str) or self._utf8_size(source) > min(8192, self.max_output_bytes):
            raise AgentError("calc.py must be bounded UTF-8 source (at most 8192 bytes)")
        try:
            tree = ast.parse(source)
        except (SyntaxError, ValueError, RecursionError):
            raise AgentError("calc.py must be valid Python for a single arithmetic add(a, b)") from None
        nodes = list(ast.walk(tree))
        if len(nodes) > 128 or len(tree.body) != 1:
            raise AgentError("calc.py must contain one small arithmetic function")
        func = tree.body[0]
        if not isinstance(func, ast.FunctionDef) or func.name != "add" \
                or func.decorator_list or func.returns or func.type_comment \
                or getattr(func, "type_params", []) or len(func.body) != 1 \
                or not isinstance(func.body[0], ast.Return):
            raise AgentError("only undecorated def add(a, b) with one return statement is allowed")
        args = func.args
        if [arg.arg for arg in args.args] != ["a", "b"] or args.posonlyargs \
                or args.kwonlyargs or args.vararg or args.kwarg or args.defaults \
                or args.kw_defaults or any(arg.annotation or arg.type_comment for arg in args.args):
            raise AgentError("add must have exactly the unannotated arguments a, b")
        allowed = (ast.BinOp, ast.UnaryOp, ast.Name, ast.Constant, ast.Load,
                   ast.Add, ast.Sub, ast.Mult, ast.Div, ast.UAdd, ast.USub)
        expr = func.body[0].value
        if expr is None:
            raise AgentError("add must return an arithmetic expression")
        for node in ast.walk(expr):
            if not isinstance(node, allowed):
                raise AgentError("only arithmetic over a, b and numeric literals is allowed; no calls/imports")
            if isinstance(node, ast.Name) and (node.id not in {"a", "b"} or not isinstance(node.ctx, ast.Load)):
                raise AgentError("only a and b may be referenced")
            if isinstance(node, ast.Constant) and (type(node.value) not in {int, float}
                    or abs(node.value) > 1000000 or not math.isfinite(node.value)):
                raise AgentError("arithmetic literals must be finite numbers with magnitude at most 1000000")

    @staticmethod
    def _utf8_size(value):
        try:
            return len(value.encode("utf-8"))
        except UnicodeError:
            raise AgentError("tool text must be valid UTF-8 without unpaired surrogates") from None

    def _run_tests(self):
        self._check_budget()
        self._integrity()
        source = self._read("calc.py")
        self._validate_source(source)
        timeout = min(self.test_timeout, self.budget.remaining()) if self.budget else self.test_timeout
        command = [sys.executable, "-I", "-B", "test_calc.py"]
        started = time.monotonic()
        deadline = started + timeout
        chunks = bytearray()
        # No inherited API keys, PYTHONPATH, user-site settings, or shell.
        environment = {"PATH": os.defpath, "PYTHONIOENCODING": "utf-8", "PYTHONHASHSEED": "0"}
        proc = subprocess.Popen(command, cwd=self.path, env=environment,
                                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, start_new_session=True)
        try:
            with selectors.DefaultSelector() as selector:
                selector.register(proc.stdout, selectors.EVENT_READ)
                while selector.get_map():
                    self._check_budget()
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise AgentError("fixed fixture tests exceeded test/overall timeout")
                    for key, _ in selector.select(min(remaining, 0.1)):
                        part = os.read(key.fileobj.fileno(), min(4096, self.max_output_bytes + 1 - len(chunks)))
                        if not part:
                            selector.unregister(key.fileobj)
                            continue
                        chunks.extend(part)
                        if len(chunks) > self.max_output_bytes:
                            raise AgentError("fixed fixture test output exceeds max_output_bytes")
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise AgentError("fixed fixture tests exceeded test/overall timeout")
                try:
                    code = proc.wait(timeout=remaining)
                except subprocess.TimeoutExpired:
                    raise AgentError("fixed fixture tests exceeded test/overall timeout") from None
        finally:
            if proc.poll() is None:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                proc.wait()
            proc.stdout.close()
        self._check_budget()
        self._integrity()
        if self._read("calc.py") != source:
            raise AgentError("implementation changed while tests ran")
        return {"exit_code": code, "passed": code == 0,
                "output": chunks.decode("utf-8", errors="replace"),
                "elapsed_seconds": round(time.monotonic() - started, 6),
                "command": ["python3", "-I", "-B", "test_calc.py"],
                "implementation_sha256": self._hash(source),
                "tests_sha256": self._hash(TEST_SOURCE), "version": self._version}

    def _parse_call(self, call):
        if not isinstance(call, dict) or set(call) != {"id", "type", "function"}:
            raise AgentError("tool call must have exactly id, type and function")
        ident = call["id"]
        if not isinstance(ident, str) or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", ident) is None:
            raise AgentError("tool call requires a nonempty valid ID of at most 128 characters")
        if call["type"] != "function" or not isinstance(call["function"], dict) \
                or set(call["function"]) != {"name", "arguments"}:
            raise AgentError("tool call must use type function with name and arguments")
        function = call["function"]
        name = function["name"]
        if not isinstance(name, str) or name not in {"read_file", "write_file", "run_tests"}:
            raise AgentError("unknown tool; use read_file, write_file or run_tests")
        raw_args = function["arguments"]
        if not isinstance(raw_args, str) or self._utf8_size(raw_args) > self.max_output_bytes:
            raise AgentError("tool arguments must be a bounded JSON string")
        args = strict_json_loads(raw_args)
        expected = {"read_file": {"path"}, "write_file": {"path", "content"}, "run_tests": set()}[name]
        if not isinstance(args, dict) or set(args) != expected:
            raise AgentError("tool argument schema mismatch; no missing or additional fields allowed")
        if name in {"read_file", "write_file"}:
            self._file(args["path"], writing=name == "write_file")
        if name == "write_file":
            self._validate_source(args["content"])
        return ident, name, args

    def execute_calls(self, calls):
        """Validate a whole batch before execution; only reads can share a batch."""
        self._check_budget()
        self._integrity()
        if not isinstance(calls, list) or not 1 <= len(calls) <= 16:
            raise AgentError("each tool batch must contain from 1 to 16 calls")
        parsed = [self._parse_call(call) for call in calls]
        ids = [item[0] for item in parsed]
        if len(ids) != len(set(ids)) or any(ident in self._seen_ids for ident in ids):
            raise AgentError("duplicate tool ID; every call needs a new unique ID across rounds")
        if len(parsed) > 1 and any(name != "read_file" for _, name, _ in parsed):
            raise AgentError("dependent tool batch rejected: batch only read_file calls; "
                             "send each write_file or run_tests alone in a later round")
        self._seen_ids.update(ids)
        messages = []
        for ident, name, args in parsed:
            self._check_budget()
            started = time.monotonic()
            before = self._hash(self._read("calc.py"))
            event = {"id": ident, "name": name, "arguments": args,
                     "implementation_before_sha256": before, "version_before": self._version}
            try:
                if name == "read_file":
                    result = {"path": args["path"], "content": self._read(args["path"])}
                elif name == "write_file":
                    path = self._file(args["path"], writing=True)
                    path.write_text(args["content"], encoding="utf-8")
                    self._version += 1
                    result = {"path": "calc.py", "written_bytes": len(args["content"].encode("utf-8")),
                              "implementation_sha256": self._hash(args["content"]), "version": self._version}
                else:
                    result = self._run_tests()
                self._integrity()
                content = json.dumps(result, ensure_ascii=False, allow_nan=False)
                if len(content.encode("utf-8")) > self.max_output_bytes:
                    raise AgentError("encoded tool result exceeds max_output_bytes")
                event["result"] = result
                messages.append({"role": "tool", "tool_call_id": ident, "content": content})
            except AgentError as exc:
                event["error"] = str(exc)
                raise
            finally:
                event["elapsed_seconds"] = round(time.monotonic() - started, 6)
                event["version_after"] = self._version
                try:
                    event["implementation_after_sha256"] = self._hash(self._read("calc.py"))
                except (AgentError, OSError, ValueError):
                    event["implementation_after_sha256"] = None
                self.calls.append(event)
        return messages

    def evidence(self):
        if self._closed and self._evidence_cache is not None:
            return self._evidence_cache
        source = None
        tests_unchanged = False
        actual_tests_hash = None
        final_test = {"status": "NOT_TESTED", "passed": False,
                      "error": "fixture setup did not complete"}
        try:
            actual_tests_hash = self._hash(self._read("test_calc.py"))
            self._integrity()
            tests_unchanged = True
            source = self._read("calc.py")
            signature = (self._hash(source), len(self.calls))
            if self._evidence_cache is not None and signature == self._evidence_signature:
                return self._evidence_cache
            if self.initial_result is not None:
                final_test = self._run_tests()
                final_test["status"] = "PASS" if final_test["passed"] else "FAIL"
            self._evidence_signature = signature
        except (AgentError, OSError, ValueError) as exc:
            final_test = {"status": "NOT_TESTED", "passed": False,
                          "error": str(exc) if isinstance(exc, AgentError) else "Local fixture verification failed"}
        evidence = {
            "workspace": str(self.path), "disposable": True,
            "initial_test": self.initial_result, "calls": list(self.calls),
            "diff": "".join(difflib.unified_diff(INITIAL_SOURCE.splitlines(True), source.splitlines(True),
                                               fromfile="initial/calc.py", tofile="final/calc.py")) if source is not None else "",
            "implementation_changed": source is not None and source != INITIAL_SOURCE,
            "implementation_sha256": self._hash(source) if source is not None else None,
            "tests_unchanged": tests_unchanged, "tests_sha256": actual_tests_hash,
            "expected_tests_sha256": self._hash(TEST_SOURCE),
            "final_test": final_test, "elapsed_seconds": round(time.monotonic() - self._started, 6),
        }
        self._evidence_cache = evidence
        return evidence

    def verify_success(self):
        evidence = self.evidence()
        first_change = next((index for index, call in enumerate(self.calls)
                             if call["name"] == "write_file" and "result" in call
                             and call["implementation_before_sha256"] != call["implementation_after_sha256"]),
                            len(self.calls))
        reads = {call["arguments"]["path"] for call in self.calls[:first_change]
                 if call["name"] == "read_file" and "result" in call}
        writes = [call for call in self.calls if call["name"] == "write_file" and "result" in call]
        requested_pass = any(call["name"] == "run_tests" and call.get("result", {}).get("passed")
                             and call["result"]["version"] == self._version
                             and call["result"]["implementation_sha256"] == evidence["implementation_sha256"]
                             for call in self.calls)
        reasons = []
        if not self.initial_result or self.initial_result["exit_code"] == 0:
            reasons.append("initial actual failing test is missing")
        if reads != {"calc.py", "test_calc.py"}:
            reasons.append("model must request reads of calc.py and test_calc.py before its first implementation change")
        if not writes or not evidence["implementation_changed"]:
            reasons.append("model must write an actual implementation change to calc.py")
        if not requested_pass:
            reasons.append("model must request run_tests and receive a pass after its last write")
        if not evidence["final_test"]["passed"]:
            reasons.append("independent final fixture tests failed")
        evidence["success"] = not reasons
        evidence["failure_reasons"] = reasons
        if reasons:
            raise AgentError("Fixture acceptance failed: " + "; ".join(reasons))
        return evidence
