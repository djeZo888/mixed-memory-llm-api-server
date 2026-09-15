"""Controlled Docker lifetime tests; no daemon, image, GPU, or model execution."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "q38b_fixture_lifetime", ROOT / "tests/lifecycle/sglang38_fixture/run_fixture.py")
host = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(host)
OWN_ID = "a" * 64
SENTINEL_ID = "b" * 64


def response(command, code=0, stdout=b"", stderr=b""):
    return subprocess.CompletedProcess(command, code, stdout, stderr)


def fixture_container(repo, cache, context, *, name=None, token=None, image_id=None):
    """Reviewed inspect-shaped collaborator, independent of policy predicates."""
    token = "e" * 32 if token is None else token
    return {
        "Id": OWN_ID, "Name": "/" + (name or "q38b-fixture-" + token),
        "Image": image_id or host.IMAGE_ID,
        "Config": {
            "Image": host.IMAGE_REFERENCE, "Labels": {host.OWNER_LABEL: token},
            "Env": [key + "=" + value for key, value in {
                **cache, "NVIDIA_VISIBLE_DEVICES": "none", "CUDA_VISIBLE_DEVICES": "",
                "NVIDIA_DRIVER_CAPABILITIES": "compute,utility"}.items()],
            "Entrypoint": ["python3"], "User": "0:0", "WorkingDir": "/cache",
            "Cmd": ["-B", "/fixture/tests/lifecycle/sglang38_fixture/run_pinned_image.py",
                    "--actual-image", "--repo", "/fixture", "--context", str(context)],
        },
        "HostConfig": {
            "Runtime": "nvidia", "DeviceRequests": None, "Devices": [],
            "DeviceCgroupRules": None, "Privileged": False, "CapAdd": None,
            "CapDrop": ["ALL"], "ReadonlyRootfs": True, "NetworkMode": "none",
            "PortBindings": {}, "SecurityOpt": ["no-new-privileges"],
            "LogConfig": {"Type": "none", "Config": {}}, "Binds": None,
            "VolumesFrom": None, "PidMode": "", "UTSMode": "", "IpcMode": "private",
            "PidsLimit": 128, "Memory": 8 * 1024**3, "ShmSize": 64 * 1024**2,
            "AutoRemove": False, "RestartPolicy": {"Name": "no", "MaximumRetryCount": 0},
            "Tmpfs": {
                "/models": "rw,nosuid,nodev,noexec,size=8m,mode=0700",
                "/run/secrets": "rw,nosuid,nodev,noexec,size=1m,mode=0700",
                "/cache": "rw,nosuid,nodev,size=1g,mode=0700",
                "/tmp": "rw,nosuid,nodev,size=256m,mode=1777",
            },
        },
        "Mounts": [{"Type": "bind", "Source": str(repo), "Destination": "/fixture",
                    "RW": False, "Propagation": "rprivate"}],
        "State": {"Running": False, "Paused": False, "Restarting": False,
                  "Pid": 0, "Status": "created", "ExitCode": 0},
    }


class DockerDaemon:
    """Separate daemon state from CLI outcomes, including CLI death mid-run."""

    def __init__(self, mode="success", *, policy_mutator=None):
        self.mode = mode
        self.policy_mutator = policy_mutator
        self.calls = []
        self.objects = {SENTINEL_ID: {"Id": SENTINEL_ID, "Name": "/unrelated-sentinel",
                                    "Image": "sha256:" + "c" * 64,
                                    "Config": {"Image": "unrelated", "Labels": {}},
                                    "State": {"Running": True, "Paused": False,
                                              "Restarting": False, "Pid": 900,
                                              "Status": "running", "ExitCode": 0}}}
        self.sentinel = copy.deepcopy(self.objects[SENTINEL_ID])
        self.attached = False
        self.signal_handler_during_stop = None

    def __call__(self, command, *, timeout):
        self.calls.append((command, timeout))
        if command[1] == "create":
            name = command[command.index("--name") + 1]
            label, token = command[command.index("--label") + 1].split("=", 1)
            assert label == host.OWNER_LABEL
            mounted = command[command.index("--mount") + 1]
            repo = mounted.split("src=", 1)[1].split(",dst=", 1)[0]
            environment = dict(command[index + 1].split("=", 1)
                               for index, value in enumerate(command) if value == "--env")
            self.objects[OWN_ID] = fixture_container(repo, environment, int(command[-1]),
                                                    name=name, token=token)
            if self.policy_mutator is not None:
                self.policy_mutator(self.objects[OWN_ID])
            if self.mode == "create_timeout_not_observed":
                del self.objects[OWN_ID]
                raise subprocess.TimeoutExpired(command, timeout)
            if self.mode == "create_failure_no_container":
                del self.objects[OWN_ID]
                return response(command, 125, stderr=b"synthetic-sensitive-failure")
            if self.mode == "reused_name":
                self.objects[OWN_ID]["Id"] = "d" * 64
                self.objects[OWN_ID]["Config"]["Labels"] = {}
                raise subprocess.TimeoutExpired(command, timeout)
            if self.mode == "create_timeout":
                raise subprocess.TimeoutExpired(command, timeout)
            if self.mode == "create_failure":
                return response(command, 125, stderr=b"synthetic-sensitive-failure")
            return response(command, stdout=(OWN_ID + "\n").encode())
        assert command[1] == "container", command
        action, target = command[2], command[-1]
        if action == "ls":
            if self.mode == "daemon_unavailable" and self.attached:
                return response(command, 1, stderr=b"synthetic-sensitive-daemon-error")
            selector = command[command.index("--filter") + 1]
            ids = [value["Id"] for value in self.objects.values()
                   if (selector.startswith("id=") and value["Id"] == selector[3:])
                   or (selector.startswith("name=^/") and value["Name"] == selector[6:-1])]
            return response(command, stdout="\n".join(ids).encode())
        if action == "inspect":
            if self.mode == "daemon_unavailable" and self.attached:
                return response(command, 1)
            obj = self.objects.get(target)
            if obj is None:
                obj = next((value for value in self.objects.values()
                            if value["Name"] == "/" + target), None)
            if obj is None:
                return response(command, 1)
            result = copy.deepcopy(obj)
            if self.attached and self.mode.startswith("mismatch_"):
                field = self.mode.removeprefix("mismatch_")
                if field == "label":
                    result["Config"]["Labels"] = {}
                elif field == "reference":
                    result["Config"]["Image"] = "other"
                else:
                    result[field] = {"Id": SENTINEL_ID, "Name": "/reused-name",
                                     "Image": "sha256:" + "c" * 64}[field]
            return response(command, stdout=json.dumps([result]).encode())
        if action == "start":
            self.attached = True
            if self.mode == "start_failure_before_launch":
                return response(command, 125)
            self.objects[target]["State"].update(Running=True, Pid=100, Status="running")
            if self.mode in ("timeout", "stop_timeout", "not_quiescent"):
                raise subprocess.TimeoutExpired(command, timeout)
            if self.mode == "cancel":
                raise KeyboardInterrupt()
            if self.mode.startswith("signal_"):
                os.kill(os.getpid(), getattr(signal, self.mode.removeprefix("signal_")))
                raise AssertionError("signal did not interrupt")
            if self.mode in ("start_failure", "cli_death", "daemon_unavailable") \
                    or self.mode.startswith("mismatch_"):
                return response(command, -9, stderr=b"synthetic-sensitive-backend-output")
            if self.mode != "cli_zero_still_running":
                self.objects[target]["State"].update(Running=False, Pid=0, Status="exited")
            if self.mode == "cli_zero_container_failed":
                self.objects[target]["State"]["ExitCode"] = 1
            return response(command, stdout=b'{"native":"complete"}')
        if action == "stop":
            self.signal_handler_during_stop = signal.getsignal(signal.SIGTERM)
            assert target == OWN_ID, "unrelated container stop"
            if self.mode != "not_quiescent":
                self.objects[target]["State"].update(Running=False, Pid=0, Status="exited")
            if self.mode == "stop_timeout":
                raise subprocess.TimeoutExpired(command, timeout)
            return response(command)
        if action == "rm":
            assert target == OWN_ID, "unrelated container removal"
            assert "--force" not in command
            assert not self.objects[target]["State"]["Running"]
            del self.objects[target]
            return response(command)
        raise AssertionError(command)


class Qwen38FixtureLifetimeTests(unittest.TestCase):
    def invoke(self, daemon):
        return host.run_disposable_fixture(Path("/reviewed"), {}, 131072, docker=daemon)

    def assert_sentinel(self, daemon):
        self.assertEqual(daemon.objects[SENTINEL_ID], daemon.sentinel)
        mutations = [command for command, _ in daemon.calls
                     if command[1:3] in (["container", "stop"], ["container", "rm"])]
        self.assertTrue(all(command[-1] == OWN_ID for command in mutations))
        self.assertTrue(all(0 < timeout <= 600 for _, timeout in daemon.calls))

    def failure(self, mode):
        daemon = DockerDaemon(mode)
        with self.assertRaises(host.LifetimeFailure) as caught:
            self.invoke(daemon)
        self.assert_sentinel(daemon)
        self.assertNotIn("synthetic-sensitive", json.dumps(caught.exception.evidence))
        return daemon, caught.exception.evidence

    def assert_policy_refused(self, mutate):
        daemon = DockerDaemon(policy_mutator=mutate)
        with self.assertRaises(host.LifetimeFailure) as caught:
            self.invoke(daemon)
        self.assertEqual(caught.exception.evidence["outcome"], "CREATE_FAILED")
        self.assertEqual(caught.exception.evidence["cleanup"], "QUIESCENT_REMOVAL_VERIFIED")
        self.assertFalse(daemon.attached, "policy failure must precede native execution")
        self.assertNotIn(OWN_ID, daemon.objects)
        self.assert_sentinel(daemon)

    def test_runtime_device_privilege_and_network_drift_refused_before_start(self):
        drifts = {
            "Runtime": "runc", "DeviceRequests": [{"Count": -1, "Capabilities": [["gpu"]]}],
            "Devices": [{"PathOnHost": "/dev/nvidia0", "PathInContainer": "/dev/nvidia0"}],
            "DeviceCgroupRules": ["c 195:* rwm"], "Privileged": True,
            "CapAdd": ["SYS_ADMIN"], "CapDrop": [], "ReadonlyRootfs": False,
            "NetworkMode": "host", "PortBindings": {"30004/tcp": [{"HostPort": "30004"}]},
            "SecurityOpt": [], "LogConfig": {"Type": "json-file", "Config": {}},
        }
        for field, value in drifts.items():
            with self.subTest(field=field):
                self.assert_policy_refused(
                    lambda container, field=field, value=value:
                    container["HostConfig"].__setitem__(field, value))

    def test_host_namespace_and_bind_alias_drift_refused_before_start(self):
        for field, value in {
            "Binds": ["/host/secret:/run/secrets:ro"], "VolumesFrom": ["unrelated-sentinel"],
            "PidMode": "host", "UTSMode": "host", "IpcMode": "host",
        }.items():
            with self.subTest(field=field):
                self.assert_policy_refused(
                    lambda container, field=field, value=value:
                    container["HostConfig"].__setitem__(field, value))

    def test_resource_limits_restart_and_automatic_removal_drift_refused(self):
        for field, value in (
            ("PidsLimit", 0), ("PidsLimit", True), ("Memory", 0),
            ("ShmSize", 1024**3), ("AutoRemove", True),
            ("RestartPolicy", {"Name": "always", "MaximumRetryCount": 0}),
            ("RestartPolicy", {"Name": "on-failure", "MaximumRetryCount": 3}),
        ):
            with self.subTest(field=field, value=value):
                self.assert_policy_refused(
                    lambda container, field=field, value=value:
                    container["HostConfig"].__setitem__(field, value))

    def test_native_process_entrypoint_user_workspace_and_context_drift_refused(self):
        for field, value in {
            "Entrypoint": ["sh", "-c"], "User": "1000:1000", "WorkingDir": "/root",
            "Cmd": ["/fixture/tests/lifecycle/sglang38_fixture/run_pinned_image.py",
                    "--actual-image", "--repo", "/fixture", "--context", "1048576"],
        }.items():
            with self.subTest(field=field):
                self.assert_policy_refused(
                    lambda container, field=field, value=value:
                    container["Config"].__setitem__(field, value))

    def test_environment_gpu_enablement_void_and_duplicate_overrides_refused(self):
        for key, value in (("NVIDIA_VISIBLE_DEVICES", "all"),
                           ("NVIDIA_VISIBLE_DEVICES", "void"),
                           ("CUDA_VISIBLE_DEVICES", "0"),
                           ("NVIDIA_DRIVER_CAPABILITIES", "all")):
            def mutate(container, key=key, value=value):
                container["Config"]["Env"] = [entry for entry in container["Config"]["Env"]
                                               if not entry.startswith(key + "=")]
                container["Config"]["Env"].append(key + "=" + value)
            with self.subTest(key=key, value=value):
                self.assert_policy_refused(mutate)
        self.assert_policy_refused(lambda container:
            container["Config"]["Env"].append("NVIDIA_VISIBLE_DEVICES=none"))
        self.assert_policy_refused(lambda container:
            container["Config"].__setitem__("Env", ["NVIDIA_VISIBLE_DEVICES"]))

    def test_cache_environment_must_match_the_fixed_reviewed_resolver_paths(self):
        approved = {"HF_HOME": "/cache/huggingface"}
        value = fixture_container(Path("/reviewed"), approved, 262144)
        self.assertEqual(host.verify_fixture_runtime(value, Path("/reviewed"), approved, 262144)
                         ["status"], "PASS_HOST_INSPECT")
        value["Config"]["Env"] = [entry.replace("HF_HOME=/cache/huggingface", "HF_HOME=/root/cache")
                                   for entry in value["Config"]["Env"]]
        with self.assertRaises(host.FixtureError):
            host.verify_fixture_runtime(value, Path("/reviewed"), approved, 262144)

    def test_mount_model_secret_and_writable_fixture_drift_refused_before_start(self):
        mutations = [
            lambda container: container["Mounts"].append(
                {"Type": "bind", "Source": "/host/secrets", "Destination": "/run/secrets",
                 "RW": False, "Propagation": "rprivate"}),
            lambda container: container["Mounts"].append(
                {"Type": "volume", "Name": "production-models", "Destination": "/models"}),
            lambda container: container["Mounts"][0].__setitem__("Source", "/unreviewed"),
            lambda container: container["Mounts"][0].__setitem__("Destination", "/different"),
            lambda container: container["Mounts"][0].__setitem__("RW", True),
            lambda container: container["Mounts"][0].__setitem__("Propagation", "shared"),
            lambda container: container["HostConfig"]["Tmpfs"].__delitem__("/run/secrets"),
            lambda container: container["HostConfig"]["Tmpfs"].__setitem__(
                "/models", "rw,size=100g,mode=0777"),
            lambda container: container["Mounts"].append(
                {"Type": "tmpfs", "Destination": "/unreviewed-cache"}),
            lambda container: container["Mounts"].extend([
                {"Type": "tmpfs", "Destination": "/cache"},
                {"Type": "tmpfs", "Destination": "/cache"}]),
        ]
        for index, mutation in enumerate(mutations):
            with self.subTest(case=index):
                self.assert_policy_refused(mutation)

    def test_success_has_unique_identity_and_quiescent_removal_before_return(self):
        names = []
        for _ in range(2):
            daemon = DockerDaemon()
            child, evidence = self.invoke(daemon)
            self.assertEqual(child.stdout, b'{"native":"complete"}')
            self.assertEqual(evidence["container_id"], OWN_ID)
            self.assertEqual(evidence["cleanup"], "QUIESCENT_REMOVAL_VERIFIED")
            self.assertNotIn(OWN_ID, daemon.objects)
            self.assert_sentinel(daemon)
            names.append(evidence["container_name"])
            create = daemon.calls[0][0]
            self.assertNotIn("--rm", create)
            self.assertEqual(create[1], "create")
            self.assertEqual(daemon.calls[-1][0][2], "ls")
        self.assertNotEqual(*names)

    def test_timeout_cli_death_start_failure_and_cancel_stop_actual_container(self):
        for mode, outcome in (("timeout", "ATTACH_TIMEOUT"), ("cli_death", "ATTACH_FAILED"),
                              ("start_failure", "ATTACH_FAILED"), ("cancel", "CANCELLED")):
            with self.subTest(mode=mode):
                daemon, evidence = self.failure(mode)
                self.assertEqual(evidence["outcome"], outcome)
                self.assertEqual(evidence["cleanup"], "QUIESCENT_REMOVAL_VERIFIED")
                self.assertNotIn(OWN_ID, daemon.objects)
                self.assertEqual([cmd[2] for cmd, _ in daemon.calls
                                  if cmd[1:3] == ["container", "stop"]], ["stop"])

    def test_create_failure_and_timeout_recover_only_verified_own_container(self):
        for mode in ("create_failure", "create_timeout", "create_failure_no_container"):
            with self.subTest(mode=mode):
                daemon, evidence = self.failure(mode)
                self.assertNotIn(OWN_ID, daemon.objects)
                self.assertIn(evidence["cleanup"], ("QUIESCENT_REMOVAL_VERIFIED", "ABSENCE_VERIFIED"))
                self.assertFalse(any(cmd[2] == "start" for cmd, _ in daemon.calls
                                     if cmd[1] == "container"))

    def test_unacknowledged_create_absence_is_not_daemon_completion_proof(self):
        _, evidence = self.failure("create_timeout_not_observed")
        self.assertEqual(evidence["cleanup"], "FAILED_UNVERIFIED")
        self.assertIsNone(evidence["container_id"])

    def test_start_failure_before_launch_removes_only_verified_created_container(self):
        daemon, evidence = self.failure("start_failure_before_launch")
        self.assertEqual(evidence["cleanup"], "QUIESCENT_REMOVAL_VERIFIED")
        self.assertNotIn(OWN_ID, daemon.objects)
        self.assertFalse(any(cmd[1:3] == ["container", "stop"] for cmd, _ in daemon.calls))

    def test_zero_cli_exit_does_not_hide_running_or_failed_container(self):
        for mode in ("cli_zero_still_running", "cli_zero_container_failed"):
            with self.subTest(mode=mode):
                daemon, evidence = self.failure(mode)
                self.assertEqual(evidence["outcome"], "ATTACH_FAILED")
                self.assertEqual(evidence["cleanup"], "QUIESCENT_REMOVAL_VERIFIED")
                self.assertNotIn(OWN_ID, daemon.objects)

    def test_signals_cleanup_mask_repeated_signals_and_restore_handlers(self):
        previous = {number: signal.getsignal(number)
                    for number in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)}
        for name in ("SIGINT", "SIGTERM", "SIGHUP"):
            with self.subTest(name=name):
                daemon, evidence = self.failure("signal_" + name)
                self.assertEqual(evidence["outcome"], "CANCELLED")
                self.assertEqual(evidence["cleanup"], "QUIESCENT_REMOVAL_VERIFIED")
                self.assertEqual(daemon.signal_handler_during_stop, signal.SIG_IGN)
                self.assertEqual({number: signal.getsignal(number) for number in previous}, previous)

    def test_identity_mismatch_refuses_mutation_and_keeps_failure_identity(self):
        for field in ("Id", "Name", "Image", "label", "reference"):
            with self.subTest(field=field):
                daemon, evidence = self.failure("mismatch_" + field)
                self.assertEqual(evidence["container_id"], OWN_ID)
                self.assertEqual(evidence["cleanup"], "FAILED_UNVERIFIED")
                self.assertFalse(any(cmd[1:3] in (["container", "stop"], ["container", "rm"])
                                     for cmd, _ in daemon.calls))

    def test_reused_name_is_not_removed_after_create_cli_timeout(self):
        daemon, evidence = self.failure("reused_name")
        self.assertIsNone(evidence["container_id"])
        self.assertEqual(evidence["cleanup"], "FAILED_UNVERIFIED")
        self.assertFalse(any(cmd[1:3] in (["container", "stop"], ["container", "rm"])
                             for cmd, _ in daemon.calls))

    def test_timed_out_stop_cli_still_needs_independent_quiescence(self):
        daemon, evidence = self.failure("stop_timeout")
        self.assertEqual(evidence["cleanup"], "QUIESCENT_REMOVAL_VERIFIED")
        self.assertNotIn(OWN_ID, daemon.objects)
        daemon, evidence = self.failure("not_quiescent")
        self.assertEqual(evidence["cleanup"], "FAILED_UNVERIFIED")
        self.assertTrue(daemon.objects[OWN_ID]["State"]["Running"])
        self.assertFalse(any(cmd[1:3] == ["container", "rm"] for cmd, _ in daemon.calls))

    def test_daemon_failure_is_not_absence_proof(self):
        daemon, evidence = self.failure("daemon_unavailable")
        self.assertEqual(evidence["cleanup"], "FAILED_UNVERIFIED")
        self.assertTrue(daemon.objects[OWN_ID]["State"]["Running"])

    def test_cli_success_retains_streams_at_combined_limit_and_exit_code(self):
        source = "import os; os.write(1, b'o'*65536); os.write(2, b'e'*65536); raise SystemExit(17)"
        result = host.docker_call([sys.executable, "-c", source], timeout=5)
        self.assertEqual(result.returncode, 17)
        self.assertEqual(result.stdout, b"o" * 65536)
        self.assertEqual(result.stderr, b"e" * 65536)

    def capture_local_cli(self, source, *, timeout=5):
        children = []
        actual_popen = subprocess.Popen

        def launched(*args, **kwargs):
            child = actual_popen(*args, **kwargs)
            children.append(child)
            return child

        started = time.monotonic()
        with patch.object(host.subprocess, "Popen", side_effect=launched):
            with self.assertRaises((host.FixtureError, subprocess.TimeoutExpired)) as caught:
                host.docker_call([sys.executable, "-c", source], timeout=timeout)
        self.assertLess(time.monotonic() - started, 4)
        self.assertEqual(len(children), 1)
        self.assertIsNotNone(children[0].poll(), "failed CLI must be reaped")
        self.assertTrue(children[0].stdout.closed and children[0].stderr.closed)
        return caught.exception

    def test_combined_output_cap_kills_chattering_cli_without_disk_spool(self):
        for descriptor in (1, 2):
            with self.subTest(descriptor=descriptor):
                error = self.capture_local_cli(
                    f"import os; os.write(1, b'o'*65536); os.write(2, b'e'*65536); "
                    f"os.write({descriptor}, b'x'); import time; time.sleep(20)")
                self.assertEqual(str(error), "docker_cli_output_limit")

    def test_cli_timeout_kills_and_reaps_a_silent_local_process(self):
        error = self.capture_local_cli("import time; time.sleep(20)", timeout=0.1)
        self.assertIsInstance(error, subprocess.TimeoutExpired)

    def test_closed_streams_do_not_waive_cli_exit_deadline(self):
        error = self.capture_local_cli(
            "import os,time; os.close(1); os.close(2); time.sleep(20)", timeout=0.1)
        self.assertIsInstance(error, subprocess.TimeoutExpired)

    def test_cli_death_with_inherited_open_pipes_has_bounded_drain(self):
        pipes = [os.pipe(), os.pipe()]
        waited = []
        child = SimpleNamespace(returncode=-9,
            stdout=os.fdopen(pipes[0][0], "rb", buffering=0),
            stderr=os.fdopen(pipes[1][0], "rb", buffering=0),
            poll=lambda: -9, wait=lambda *, timeout: waited.append(timeout))
        started = time.monotonic()
        try:
            with patch.object(host.subprocess, "Popen", return_value=child):
                with self.assertRaises(subprocess.TimeoutExpired):
                    host.docker_call(["controlled-already-dead-cli"], timeout=0.05)
            self.assertLess(time.monotonic() - started, 1)
            self.assertEqual(waited, [host.CLI_DRAIN_TIMEOUT])
            self.assertTrue(child.stdout.closed and child.stderr.closed)
        finally:
            for _reader, writer in pipes:
                os.close(writer)

    def test_output_overflow_still_cleans_actual_controlled_container(self):
        daemon = DockerDaemon()

        def runner(command, *, timeout):
            if command[1:3] == ["container", "start"]:
                daemon.attached = True
                daemon.objects[OWN_ID]["State"].update(Running=True, Pid=100, Status="running")
                return host.docker_call([sys.executable, "-c",
                    "import os; os.write(1, b'x'*262144)"], timeout=5)
            return daemon(command, timeout=timeout)

        with self.assertRaises(host.LifetimeFailure) as caught:
            host.run_disposable_fixture(Path("/reviewed"), {}, 131072, docker=runner)
        self.assertEqual(caught.exception.evidence["outcome"], "ATTACH_FAILED")
        self.assertEqual(caught.exception.evidence["cleanup"], "QUIESCENT_REMOVAL_VERIFIED")
        self.assertNotIn(OWN_ID, daemon.objects)
        self.assert_sentinel(daemon)

    def test_cleanup_global_deadline_refuses_additional_unbounded_commands(self):
        daemon = DockerDaemon()
        owned = host.DisposableContainer(daemon, host.IMAGE_ID)
        owned.create_attempted = True
        with patch.object(host.time, "monotonic", side_effect=[10, 100]):
            with self.assertRaisesRegex(host.FixtureError, "container_cleanup_deadline"):
                owned.cleanup()
        self.assertEqual(daemon.calls, [])


if __name__ == "__main__":
    unittest.main()
