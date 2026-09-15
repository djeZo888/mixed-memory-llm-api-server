"""Bounded native OpenCode evidence parsing and owned POSIX process cleanup.

Only the fixed verifier task is accepted. Returned event metadata never includes
model text, tool output, arbitrary paths, commands, or unhashed call identities.
This runner supervises processes; it is not an OS security sandbox.
"""

import collections
import contextlib
import hashlib
import json
import math
import os
from pathlib import Path
import re
import selectors
import signal
import subprocess
import time


FIXED_ARGV = ("python3", "-I", "-B", "test_text_utils.py")
FIXED_COMMAND = " ".join(FIXED_ARGV)
MAX_OUTPUT = 8 * 1024 * 1024
MAX_EVENTS = 4096
MAX_LINE = 1024 * 1024
FILES = frozenset(("text_utils.py", "test_text_utils.py"))
TOOLS = frozenset(("read", "edit", "write", "bash", "glob", "grep"))
EVENT_TYPES = {"step_start": "step-start", "step_finish": "step-finish",
               "tool_use": "tool", "text": "text", "error": None}
DENIAL_PREFIX = "The user has specified a rule which prevents you from using this specific tool call."


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_key")
        result[key] = value
    return result


def _path(value, workspace):
    """Return only fixed basenames and location booleans, never attacker text."""
    if not isinstance(value, str) or not value or len(value) > 4096 or "\x00" in value:
        return None, False
    path = Path(value)
    if ".." in path.parts:
        return None, False
    if not path.is_absolute():
        path = workspace / path
    try:
        normalized = path.resolve()
    except (OSError, ValueError, RuntimeError):
        return None, False
    inside = normalized == workspace or workspace in normalized.parents
    filename = normalized.name if normalized.parent == workspace and normalized.name in FILES else None
    return filename, inside


def _native_tokens(value):
    if type(value) is not dict or not set(value) <= {"total", "input", "output", "reasoning", "cache"}:
        raise ValueError("invalid_native_tokens")
    result = {}
    for key, count in value.items():
        if key == "cache":
            if type(count) is not dict or not set(count) <= {"read", "write"}:
                raise ValueError("invalid_native_tokens")
            if any(type(v) is not int or v < 0 for v in count.values()):
                raise ValueError("invalid_native_tokens")
            result[key] = dict(count)
        elif type(count) is int and count >= 0:
            result[key] = count
        else:
            raise ValueError("invalid_native_tokens")
    return result


def parse_events(raw, workspace):
    """Parse bounded native JSONL, returning safe checks and failure diagnostics.

The native CLI emits terminal tool states once per callID. Success requires
ordered reads, implementation edit, actual exact-command exit/output, final
text, and terminal stop. Filesystem immutability and independent execution are
separate caller checks. Native token counters are never called provider usage.
"""
    checks = dict.fromkeys(("file_reads", "implementation_edit", "exact_test_command",
                            "passing_tool_result", "final_response"), False)
    result = {"checks": checks, "failures": [], "result": "fail", "event_counts": {},
              "tools": [], "steps": [], "provider_usage": "NOT_REPORTED"}
    failures = result["failures"]

    def fail(code):
        if code not in failures:
            failures.append(code)

    if not isinstance(raw, bytes) or not raw:
        fail("native_events_empty")
        return result
    if len(raw) > MAX_OUTPUT:
        fail("native_output_limit")
        return result
    if not raw.endswith(b"\n"):
        fail("native_partial_line")
        return result
    lines = raw.splitlines()
    if len(lines) > MAX_EVENTS or any(len(line) > MAX_LINE for line in lines):
        fail("native_event_limit")
        return result
    try:
        workspace = Path(workspace).resolve(strict=True)
        events = [json.loads(line.decode("utf-8"), object_pairs_hook=_object,
                             parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
                  for line in lines]
    except (OSError, ValueError, RecursionError, UnicodeError):
        fail("native_malformed_json")
        return result
    counts = collections.Counter()
    reads, identities = set(), set()
    session, message, active, terminal = None, None, False, False
    step_tools, step_text, passed_at, final_at = 0, False, -1, -1
    exhausted = False
    for sequence, event in enumerate(events, 1):
        if type(event) is not dict or not isinstance(event.get("type"), str) or event.get("type") not in EVENT_TYPES:
            fail("native_unknown_event")
            continue
        kind = event["type"]
        counts[kind] += 1
        if terminal:
            fail("native_event_after_stop")
        if kind == "error":
            fail("native_error_event")
            continue
        part = event.get("part")
        if type(part) is not dict or part.get("type") != EVENT_TYPES[kind]:
            fail("native_invalid_part")
            continue
        session_id, message_id = event.get("sessionID"), part.get("messageID")
        if (not isinstance(session_id, str) or not 0 < len(session_id) <= 256 or
                not isinstance(message_id, str) or not 0 < len(message_id) <= 256 or
                part.get("sessionID") != session_id):
            fail("native_invalid_identity")
            continue
        if session is None:
            session = session_id
        elif session != session_id:
            fail("native_session_changed")
        if kind == "step_start":
            if active:
                fail("native_overlapping_step")
            active, message, step_tools, step_text = True, message_id, 0, False
            continue
        if not active or message_id != message:
            fail("native_step_order")
        if kind == "text":
            text = part.get("text")
            if not isinstance(text, str) or not text.strip():
                fail("native_empty_text")
            else:
                step_text = True
                if passed_at > 0:
                    final_at = sequence
            continue
        if kind == "step_finish":
            reason = part.get("reason")
            allowed = {"tool-calls", "stop", "length", "error", "content-filter", "unknown"}
            step = {"reason": reason if isinstance(reason, str) and reason in allowed else "unknown"}
            if "tokens" in part:
                try:
                    step["native_tokens"] = _native_tokens(part["tokens"])
                except ValueError:
                    fail("native_invalid_usage")
            if "cost" in part:
                cost = part["cost"]
                if type(cost) not in (int, float) or cost < 0 or cost > 1e100 or not math.isfinite(cost):
                    fail("native_invalid_usage")
                else:
                    step["native_cost"] = cost
            result["steps"].append(step)
            if reason == "length":
                exhausted = True
                fail("native_token_exhaustion")
            elif reason == "tool-calls":
                if not step_tools:
                    fail("native_tool_finish_without_tool")
            elif reason == "stop":
                terminal = True
                checks["final_response"] = bool(step_text and final_at > passed_at > 0)
                if not checks["final_response"]:
                    fail("native_final_before_passing_test")
            else:
                fail("native_nonaccepting_finish")
            active = False
            continue
        step_tools += 1
        tool, call_id, state = part.get("tool"), part.get("callID"), part.get("state")
        if not isinstance(call_id, str) or not 0 < len(call_id) <= 512 or type(state) is not dict:
            fail("native_invalid_tool")
            continue
        try:
            identity = hashlib.sha256(call_id.encode()).hexdigest()
        except UnicodeError:
            fail("native_invalid_tool_identity")
            continue
        if identity in identities:
            fail("native_duplicate_call_id")
        identities.add(identity)
        status = state.get("status")
        item = {"event_sequence": sequence, "tool": tool if isinstance(tool, str) and tool in TOOLS else "unknown",
                "call_id_sha256": identity,
                "status": status if status in ("completed", "error", "pending", "running") else "unknown"}
        result["tools"].append(item)
        args = state.get("input")
        if type(args) is not dict or status not in ("completed", "error"):
            fail("native_partial_tool")
            continue
        if not isinstance(tool, str) or tool not in TOOLS:
            fail("native_unsupported_tool")
            continue
        if tool in ("read", "edit", "write"):
            filename, inside = _path(args.get("filePath"), workspace)
            item.update(file=filename, path_within_workspace=inside)
        else:
            filename, inside = _path(args.get("workdir" if tool == "bash" else "path", str(workspace)), workspace)
            item["path_within_workspace"] = inside
        # The native error string is fixed by OpenCode permissions. Arbitrary
        # runtime tool errors (including failed shell execution) are not denials.
        error = state.get("error")
        if status == "error":
            denied = isinstance(error, str) and error.startswith(DENIAL_PREFIX)
            item["classification"] = "permission_denied" if denied else "tool_error"
            if not denied:
                fail("native_tool_error")
            continue
        output, metadata = state.get("output"), state.get("metadata", {})
        if not isinstance(output, str) or type(metadata) is not dict:
            fail("native_invalid_tool_result")
            continue
        if not inside:
            fail("native_executed_outside_workspace")
            continue
        if tool == "read":
            if filename not in FILES or not output.strip() or metadata.get("truncated") is True:
                fail("native_invalid_read")
            else:
                reads.add(filename)
                checks["file_reads"] = reads == FILES
        elif tool in ("edit", "write"):
            if filename != "text_utils.py":
                fail("native_edited_nonimplementation")
            elif not checks["file_reads"]:
                fail("native_edit_before_reads")
            elif tool == "edit" and (not isinstance(args.get("oldString"), str) or
                    not isinstance(args.get("newString"), str) or args["oldString"] == args["newString"]):
                fail("native_empty_edit")
            elif tool == "write" and not isinstance(args.get("content"), str):
                fail("native_empty_edit")
            else:
                checks["implementation_edit"] = True
                if passed_at > 0:
                    checks["passing_tool_result"] = False
                    passed_at = -1
        elif tool == "bash":
            # Missing workdir means the reviewed launcher cwd. Explicit workdir
            # must identify that exact directory, not merely one of its children.
            workdir = args.get("workdir", str(workspace))
            try:
                exact_dir = Path(workdir).resolve() == workspace if Path(workdir).is_absolute() else (workspace / workdir).resolve() == workspace
            except (OSError, ValueError, TypeError, RuntimeError):
                exact_dir = False
            exact = args.get("command") == FIXED_COMMAND and exact_dir
            item["exact_test_command"] = exact
            if not exact:
                fail("native_executed_wrong_command")
                continue
            if not checks["implementation_edit"]:
                fail("native_test_before_edit")
                continue
            checks["exact_test_command"] = True
            exit_code = metadata.get("exit")
            item["exit_code"] = exit_code if type(exit_code) is int else None
            ok = bool(re.search(r"(?m)^Ran 3 tests? in [0-9.]+s\s*$", output) and
                      re.search(r"(?m)^OK\s*$", output) and
                      not re.search(r"(?m)^(?:FAILED|ERROR:|FAIL:|Traceback|ImportError|ModuleNotFoundError)", output))
            passed = type(exit_code) is int and exit_code == 0 and ok and metadata.get("truncated") is not True
            item["test_output_passed"] = passed
            checks["passing_tool_result"] = passed
            passed_at = sequence if passed else -1
    result["event_counts"] = dict(counts)
    if active or not terminal:
        fail("native_missing_terminal_stop")
    for name, passed in checks.items():
        if not passed:
            fail("native_missing_" + name)
    result["result"] = "token_exhaustion" if exhausted else ("fail" if failures else "pass")
    return result


def _process_snapshot():
    """PID ancestry and stable start stamp only; never process argv/environment."""
    completed = subprocess.run(["/bin/ps", "-axo", "pid=,ppid=,pgid=,lstart="],
                               stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                               timeout=1, check=True)
    result = {}
    for line in completed.stdout.decode("ascii").splitlines():
        fields = line.split(None, 3)
        if len(fields) == 4:
            result[int(fields[0])] = (int(fields[1]), int(fields[2]), fields[3])
    return result


def run_bounded(argv, cwd, env, input=None, timeout=1800, max_output=MAX_OUTPUT, cancel_requested=None):
    """Execute an internal argv without a shell; bound bytes, time, and cleanup.

The caller provides only reviewed argv. Children run in a fresh session. We
track observed descendants, including changed process groups, and reap the
direct child. Cleanup errors are surfaced as process_tree_reaped=False.
An optional cancellation predicate enters the same cleanup without throwing
from a signal handler or discarding the captured process result.
"""
    if (os.name != "posix" or not isinstance(argv, (list, tuple)) or not argv or
            any(not isinstance(arg, str) or "\x00" in arg for arg in argv) or
            type(timeout) not in (int, float) or not math.isfinite(timeout) or not 0 < timeout <= 7200 or
            type(max_output) is not int or not 0 < max_output <= MAX_OUTPUT or
            cancel_requested is not None and not callable(cancel_requested) or
            input is not None and (not isinstance(input, bytes) or len(input) > MAX_LINE)):
        raise ValueError("invalid_bounded_process_arguments")
    started = time.monotonic()
    process = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.PIPE if input is not None else subprocess.DEVNULL,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
    selector = selectors.DefaultSelector()
    stdout, stderr = bytearray(), bytearray()
    timed_out, limited, cleaned, tracking_ok = False, False, False, True
    tracked = {}
    pending = memoryview(input or b"")

    def observe():
        nonlocal tracking_ok
        try:
            snapshot = _process_snapshot()
        except (OSError, ValueError, subprocess.SubprocessError, UnicodeError):
            tracking_ok = False
            return {}
        owned = {process.pid}
        owned.update(pid for pid, stamp in tracked.items() if pid in snapshot and snapshot[pid][2] == stamp)
        while True:
            added = {pid for pid, (parent, group, _) in snapshot.items()
                     if group == process.pid or parent in owned}
            if added <= owned:
                break
            owned.update(added)
        for pid in owned:
            if pid in snapshot:
                tracked[pid] = snapshot[pid][2]
        return snapshot

    def signal_owned(sig):
        snapshot = observe()
        with contextlib.suppress(ProcessLookupError):
            os.killpg(process.pid, sig)
        for pid, stamp in tracked.items():
            if pid != process.pid and pid in snapshot and snapshot[pid][2] == stamp:
                with contextlib.suppress(ProcessLookupError):
                    os.kill(pid, sig)

    try:
        for stream, label in ((process.stdout, "stdout"), (process.stderr, "stderr")):
            os.set_blocking(stream.fileno(), False)
            selector.register(stream, selectors.EVENT_READ, label)
        if process.stdin:
            if pending:
                os.set_blocking(process.stdin.fileno(), False)
                selector.register(process.stdin, selectors.EVENT_WRITE, "stdin")
            else:
                process.stdin.close()
        next_observation = 0.0
        parent_exited = None
        while True:
            now = time.monotonic()
            if now >= next_observation:
                observe()
                next_observation = now + 0.025
            returncode = process.poll()
            if cancel_requested is not None and cancel_requested():
                break
            if now - started >= timeout:
                timed_out = returncode is None or bool(selector.get_map())
                break
            if returncode is not None and not selector.get_map():
                break
            # A completed launcher cannot leave descendants holding output open.
            if returncode is not None:
                if parent_exited is None:
                    parent_exited = now
                    signal_owned(signal.SIGTERM)
                elif now - parent_exited >= 0.3:
                    signal_owned(signal.SIGKILL)
            for key, _ in selector.select(min(0.025, max(0, timeout - (now - started)))):
                stream, label = key.fileobj, key.data
                if label == "stdin":
                    try:
                        sent = os.write(stream.fileno(), pending[:65536])
                        pending = pending[sent:]
                    except BrokenPipeError:
                        pending = pending[len(pending):]
                    if not pending:
                        selector.unregister(stream)
                        stream.close()
                    continue
                try:
                    block = os.read(stream.fileno(), 65536)
                except BlockingIOError:
                    continue
                if not block:
                    selector.unregister(stream)
                    stream.close()
                    continue
                capacity = max_output - len(stdout) - len(stderr)
                (stdout if label == "stdout" else stderr).extend(block[:capacity])
                if len(block) > capacity:
                    limited = True
                    break
            if limited:
                break
    finally:
        try:
            signal_owned(signal.SIGTERM)
            try:
                process.wait(timeout=0.3)
            except subprocess.TimeoutExpired:
                pass
            signal_owned(signal.SIGKILL)
            process.wait(timeout=2)
            deadline = time.monotonic() + 2
            while True:
                snapshot = observe()
                survivors = [pid for pid, stamp in tracked.items() if pid in snapshot and snapshot[pid][2] == stamp]
                try:
                    os.killpg(process.pid, 0)
                    group_exists = True
                except ProcessLookupError:
                    group_exists = False
                if not survivors and not group_exists:
                    cleaned = tracking_ok
                    break
                if time.monotonic() >= deadline:
                    break
                time.sleep(0.025)
        except (OSError, subprocess.SubprocessError):
            cleaned = False
        selector.close()
        for stream in (process.stdin, process.stdout, process.stderr):
            if stream:
                stream.close()
    return {"stdout": bytes(stdout), "stderr": bytes(stderr), "exit_code": process.returncode,
            "timed_out": timed_out, "output_limited": limited, "process_tree_reaped": cleaned,
            "elapsed_seconds": round(time.monotonic() - started, 6)}
