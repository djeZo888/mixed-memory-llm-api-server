"""Offline behavior checks only: no Docker, systemd, GPU or protected VM reads."""
from __future__ import annotations

import contextlib
import copy
import importlib.util
import json
from pathlib import Path
import signal
import subprocess
import sys
import unittest
from unittest.mock import Mock, patch


REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
SPEC = importlib.util.spec_from_file_location("image_runtime_service_review", REPO / "scripts/image_runtime/service.py")
service = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = service
SPEC.loader.exec_module(service)
CID = "a" * 64
IMAGE = "sha256:" + "b" * 64
RUN_ID = "c" * 32


def completed(argv, stdout="", returncode=0):
    return subprocess.CompletedProcess(argv, returncode, stdout, "")


def owned_container():
    return {
        "Id": CID, "Name": "/" + service.NAME, "Image": IMAGE,
        "Config": {"User": "1000:1001", "Labels": {
            "io.llm-image.owner": service.OWNER, "io.llm-image.invocation": RUN_ID,
            "io.llm-image.gpu": service.GPU_UUID}},
        "HostConfig": {"DeviceRequests": [{"DeviceIDs": [service.GPU_UUID]}],
            "CpusetCpus": "8-15", "Memory": service.CAP_BYTES,
            "MemorySwap": service.CAP_BYTES, "RestartPolicy": {"Name": "no"},
            "NetworkMode": "llm-image-backend-private",
            "PortBindings": {"30007/tcp": [{"HostIp": "127.0.0.1", "HostPort": "30007"}]}},
        "State": {"Running": True},
        "NetworkSettings": {"Ports": {"30007/tcp": [{"HostIp": "127.0.0.1", "HostPort": "30007"}]}},
    }


def owned_state():
    return {"run_id": RUN_ID, "container": {"id": CID, "image_id": IMAGE},
            "phase": "warm", "warm": True}


class ServiceReview(unittest.TestCase):
    def tearDown(self):
        service.OPERATION_DEADLINE = None
        service.SETTLEMENT_DEADLINE = None

    def runtime(self):
        runtime = object.__new__(service.Runtime)
        runtime.config = {"image_id": IMAGE}
        return runtime

    def test_cli_rejects_extra_or_user_controlled_actions_before_runtime(self):
        for argv in (["service.py", "recover", "--unit", "other.service"],
                     ["service.py", "arbitrary"], ["service.py"]):
            with self.subTest(argv=argv), patch.object(service.sys, "argv", argv), \
                    patch.object(service, "Runtime") as runtime:
                with self.assertRaisesRegex(RuntimeError, "invalid_fixed_action"):
                    service.main()
                runtime.assert_not_called()

    def test_recovery_shell_refuses_arguments_before_fixed_exec(self):
        # The shell exits64 before the fixed VM Python path can execute.
        result = subprocess.run(["/bin/sh", str(REPO / "scripts/image_runtime/llm-image-backend-recover"),
                                 "other.service"], capture_output=True, text=True, timeout=2)
        self.assertEqual(result.returncode, 64)
        self.assertEqual(result.stdout, "")

    def test_systemd_start_sets_its_own_active_and_settlement_deadlines(self):
        runtime = Mock()
        def start():
            self.assertEqual(service.OPERATION_DEADLINE, 795)
            self.assertEqual(service.SETTLEMENT_DEADLINE, 855)
        runtime.start.side_effect = start
        with patch.object(service.sys, "argv", ["service.py", "start"]), \
                patch.object(service.time, "monotonic", return_value=20), \
                patch.object(service, "Runtime", return_value=runtime), \
                patch.object(service, "acquire_lease", side_effect=lambda **kw: contextlib.nullcontext()):
            service.main()
        runtime.start.assert_called_once_with()

    def test_command_budget_is_capped_and_expired_budget_starts_no_process(self):
        service.OPERATION_DEADLINE = 101
        with patch.object(service.time, "monotonic", return_value=100), \
                patch.object(service.subprocess, "run", return_value=completed([])) as run:
            service.run(["fixed-command"], timeout=60)
            self.assertEqual(run.call_args.kwargs["timeout"], 1)
            run.reset_mock()
            service.OPERATION_DEADLINE = 99
            with self.assertRaisesRegex(RuntimeError, "owned_operation_deadline"):
                service.run(["fixed-command"], timeout=60)
            run.assert_not_called()

    def test_foreign_container_is_never_stopped_or_removed(self):
        mutations = (
            lambda value: value.update(Id="d" * 64),
            lambda value: value.update(Name="/foreign"),
            lambda value: value["Config"]["Labels"].update({"io.llm-image.owner": "foreign"}),
            lambda value: value["Config"]["Labels"].update({"io.llm-image.invocation": "d" * 32}),
            lambda value: value["Config"]["Labels"].update({"io.llm-image.gpu": "GPU-foreign"}),
            lambda value: value["HostConfig"]["DeviceRequests"][0].update(DeviceIDs=["GPU-foreign"]),
            lambda value: value["HostConfig"].update(NetworkMode="host"),
            lambda value: value["HostConfig"].update(PortBindings={"30007/tcp": [{"HostIp": "0.0.0.0", "HostPort": "30007"}]}),
        )
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                runtime = self.runtime()
                runtime.guards = Mock()
                runtime.state = Mock(return_value=owned_state())
                runtime.save = Mock()
                value = owned_container()
                mutate(value)
                with patch.object(service, "run", return_value=completed([], json.dumps([value]))) as run:
                    with self.assertRaisesRegex(RuntimeError, "owned_backend_(identity|policy)_mismatch"):
                        runtime.reset_owned()
                self.assertEqual([call.args[0] for call in run.call_args_list], [["docker", "inspect", CID]])
                runtime.save.assert_not_called()

    def test_ada_idle_gate_rejects_ada_but_allows_text_gpu_processes(self):
        runtime = self.runtime()
        for rows, allowed in (("GPU-text, 7\n", True),
                              ("GPU-text, 7\n" + service.GPU_UUID + ", 8\n", False)):
            with self.subTest(rows=rows), patch.object(service, "run", return_value=completed([], rows)):
                if allowed:
                    runtime.require_ada_idle()
                else:
                    with self.assertRaisesRegex(RuntimeError, "ada_compute_process_already_present"):
                        runtime.require_ada_idle()

    def test_sampler_hang_kills_only_exact_child_and_returns(self):
        sampler = Mock()
        sampler.poll.return_value = None
        sampler.wait.side_effect = [subprocess.TimeoutExpired("sampler", 5), -9]
        self.assertEqual(service.settle_sampler(sampler), -9)
        sampler.send_signal.assert_called_once_with(signal.SIGTERM)
        sampler.kill.assert_called_once_with()
        self.assertEqual([call.kwargs["timeout"] for call in sampler.wait.call_args_list], [5, 2])

    def test_sampler_still_unsettled_is_a_result_not_an_exception(self):
        sampler = Mock()
        sampler.poll.return_value = None
        sampler.wait.side_effect = [subprocess.TimeoutExpired("sampler", 5),
                                    subprocess.TimeoutExpired("sampler", 2)]
        self.assertEqual(service.settle_sampler(sampler), "sampler_unsettled")

    def exercise_recover_timeout(self, *, stop_timeout=False, foreign=False):
        runtime = Mock()
        runtime.state.return_value = owned_state()
        if foreign:
            runtime.inspect_owned.side_effect = RuntimeError("owned_backend_identity_mismatch")
        else:
            runtime.inspect_owned.return_value = owned_container()
        held = [False]
        @contextlib.contextmanager
        def lease(**_kwargs):
            self.assertFalse(held[0])
            held[0] = True
            try:
                yield
            finally:
                held[0] = False
        calls = []
        def run(argv, **kwargs):
            calls.append(argv)
            if argv[:2] == ["systemctl", "restart"]:
                self.assertFalse(held[0])
                self.assertEqual(service.OPERATION_DEADLINE, 840)
                raise subprocess.TimeoutExpired(argv, 840)
            if argv[:2] == ["systemctl", "stop"]:
                self.assertFalse(held[0])
                self.assertEqual(service.OPERATION_DEADLINE, 900)
                if stop_timeout:
                    raise subprocess.TimeoutExpired(argv, 40)
            if argv[:2] == ["docker", "kill"]:
                self.assertTrue(held[0])
            return completed(argv)
        with patch.object(service, "Runtime", return_value=runtime), \
                patch.object(service, "acquire_lease", side_effect=lease), \
                patch.object(service.time, "monotonic", return_value=0), \
                patch.object(service, "run", side_effect=run):
            expected = RuntimeError if foreign else subprocess.TimeoutExpired
            with self.assertRaises(expected):
                service.recover()
        self.assertIsNone(service.OPERATION_DEADLINE)
        self.assertFalse(held[0])
        return calls, runtime

    def test_recovery_timeout_stops_exact_unit_and_owned_docker_under_lease(self):
        calls, runtime = self.exercise_recover_timeout()
        self.assertEqual(calls, [["systemctl", "restart", service.UNIT],
                                ["systemctl", "stop", service.UNIT], ["docker", "kill", CID]])
        state = runtime.save.call_args.args[0]
        self.assertFalse(state["warm"])
        self.assertEqual(state["phase"], "failed")

    def test_recovery_stop_timeout_uses_fixed_unit_kill_fallback(self):
        calls, _runtime = self.exercise_recover_timeout(stop_timeout=True)
        self.assertEqual(calls[2], ["systemctl", "kill", "--kill-whom=all", "--signal=KILL", service.UNIT])
        self.assertEqual(calls[3], ["docker", "kill", CID])

    def test_recovery_never_kills_container_failing_identity_check(self):
        calls, runtime = self.exercise_recover_timeout(foreign=True)
        self.assertFalse(any(argv[:2] == ["docker", "kill"] for argv in calls))
        runtime.save.assert_not_called()

    def test_warm_failure_stops_backend_even_when_sampler_is_unsettled(self):
        runtime = self.runtime()
        state = {"container": None}
        for method in ("guards", "check_ports", "check_network", "require_ada_idle", "host_headroom", "make_work"):
            setattr(runtime, method, Mock())
        runtime.state = Mock(return_value=state)
        runtime.inspect_owned = Mock(side_effect=[None, owned_container(), owned_container()])
        runtime.current_device = Mock(return_value={"total_bytes": 50 * 1024**3, "free_bytes": 49 * 1024**3})
        runtime.save = Mock()
        runtime.create_argv = Mock(return_value=["docker", "create", "fixed-owned-fixture"])
        runtime.native_health = Mock(return_value=True)
        runtime.tmp_snapshot = Mock(return_value={"entries": []})
        output = Mock()
        output.fileno.return_value = 987
        anchored = Mock()
        anchored.open.return_value = contextlib.nullcontext(output)
        runtime.anchor = Mock(side_effect=lambda: contextlib.nullcontext(anchored))
        sampler = Mock()
        sampler.poll.return_value = None
        calls = []
        def run(argv, **_kwargs):
            calls.append(argv)
            if argv[:2] == ["docker", "create"]:
                return completed(argv, CID)
            if argv[:2] == ["docker", "exec"]:
                raise subprocess.TimeoutExpired(argv, 1)
            return completed(argv)
        with patch.dict(service.os.environ, {"INVOCATION_ID": RUN_ID}), \
                patch.object(service, "OPERATION_DEADLINE", service.time.monotonic() + 775), \
                patch.object(service, "SETTLEMENT_DEADLINE", service.time.monotonic() + 835), \
                patch.object(service, "run", side_effect=run), \
                patch.object(service.time, "sleep"), \
                patch.object(service.subprocess, "Popen", return_value=sampler), \
                patch.object(service, "settle_sampler", return_value="sampler_unsettled"):
            with self.assertRaises(subprocess.TimeoutExpired):
                runtime.start()
        self.assertIn(["docker", "stop", "--time", "30", CID], calls)
        self.assertEqual(state["phase"], "failed")
        self.assertFalse(state["warm"])
        self.assertEqual(state["cleanup"]["sampler"], "sampler_unsettled")


if __name__ == "__main__":
    unittest.main()
