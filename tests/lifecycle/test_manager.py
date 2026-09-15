"""Worker-only lifecycle regressions: no Docker, credentials, or model payloads.

The fake Docker object uses the actual inspect schema. Cross-process tests share
its small JSON inventory so lifecycle locking is exercised beyond Python threads.
"""

from __future__ import annotations

import copy
import argparse
from contextlib import ExitStack, redirect_stdout
import io
import json
import multiprocessing
import os
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from fixture_storage import HistoricalBinding, FixtureWriter

from lifecycle.manager import Manager, cli, process_lock  # noqa: E402
from lifecycle.runtime_io import LifecycleError  # noqa: E402

PROOF = "glm-5.3-ud-q4-k-xl-8k"
MEASURE = "glm-5.3-ud-q4-k-xl-32k"
IMAGE = "sha256:" + "b" * 64


class FakeDocker:
    """An inspect-compatible Docker fake; every mutation is recorded."""

    def __init__(self, path=None, events=None, release=None, entered=None):
        self.path = Path(path) if path else None
        self.records = []
        self.calls = []
        self.events = events
        self.release = release
        self.entered = entered
        self.fail_create = False
        self.fail_start = False
        self.fail_stop = False
        self.exit_on_start = False
        self.compose = None

    def _read(self):
        if self.path and self.path.exists():
            return json.loads(self.path.read_text())
        return copy.deepcopy(self.records)

    def _write(self, records):
        self.records = copy.deepcopy(records)
        if self.path:
            self.path.write_text(json.dumps(records))

    def _event(self, event):
        self.calls.append(event)
        if self.events is not None:
            self.events.put(event)

    def inventory(self):
        self._event(("inventory",))
        return self._read()

    def inspect(self, identity):
        self._event(("inspect", identity))
        return next((record for record in self._read()
                     if record["Id"] == identity or record["Name"] == "/" + identity), None)

    def run(self, args, timeout=30):
        self._event(("run", tuple(args)))
        if args[0] == "info":
            return "/data/docker\n"
        if args[0:2] == ["image", "inspect"]:
            if "--format" in args:
                return IMAGE + "\n"
            return json.dumps([{"Id": IMAGE, "Config": {"Entrypoint": ["/opt/llama/llama-server"]}}])
        if args[0:2] == ["network", "inspect"]:
            return "bridge\n" if "--format" in args else json.dumps([{"Driver": "bridge"}])
        if args[0] == "compose" and self.compose is not None:
            return json.dumps(self.compose)
        raise AssertionError(f"unexpected fake Docker operation: {args[0:2]}")

    def capture(self, *args, timeout=30):
        return self.run(list(args), timeout=timeout)

    def create(self, argv):
        self._event(("create", tuple(argv)))
        if self.fail_create:
            raise LifecycleError("command_failed")
        name = argv[argv.index("--name") + 1]
        labels = {}
        for index, item in enumerate(argv):
            if item == "--label":
                key, value = argv[index + 1].split("=", 1)
                labels[key] = value
        publish = argv[argv.index("--publish") + 1]
        host, host_port, target = publish.split(":")
        target = target.removesuffix("/tcp")
        records = self._read()
        identity = f"{len(records) + 1:064x}"
        binding = {f"{target}/tcp": [{"HostIp": host, "HostPort": host_port}]}
        mounts, environment, log_options = [], [], {}
        for index, item in enumerate(argv[:argv.index(IMAGE)]):
            if item == "--mount":
                fields = argv[index + 1].split(",")
                mapping = dict(field.split("=", 1) for field in fields if "=" in field)
                mounts.append({"Type": "bind", "Source": mapping["source"],
                               "Destination": mapping["target"], "RW": "readonly" not in fields})
            elif item == "--env":
                environment.append(argv[index + 1])
            elif item == "--log-opt":
                key, value = argv[index + 1].split("=", 1)
                log_options[key] = value
        devices = argv[argv.index("--gpus") + 1].strip('"').removeprefix("device=").split(",")
        record = {"Id": identity, "Name": "/" + name, "Image": IMAGE,
                  "State": {"Running": False, "Status": "created"},
                  "Config": {"Labels": labels, "Image": IMAGE, "Env": environment,
                             "Entrypoint": [argv[argv.index("--entrypoint") + 1]],
                             "Cmd": argv[argv.index(IMAGE) + 1:]},
                  "Mounts": mounts,
                  "HostConfig": {"NetworkMode": "bridge", "PortBindings": binding,
                                 "PublishAllPorts": False, "RestartPolicy": {"Name": "no"},
                                 "LogConfig": {"Type": "json-file", "Config": log_options},
                                 "DeviceRequests": [{"DeviceIDs": devices}]},
                  "NetworkSettings": {"Ports": {}, "Networks": {"bridge": {}}}}
        records.append(record)
        self._write(records)
        return identity

    def start(self, identity):
        self._event(("start_enter", identity))
        if self.entered:
            self.entered.set()
        if self.release and not self.release.wait(15):
            raise AssertionError("concurrency test release timed out")
        if self.fail_start:
            raise LifecycleError("command_failed")
        records = self._read()
        record = next(item for item in records if item["Id"] == identity)
        record["State"] = {"Running": not self.exit_on_start,
                           "Status": "exited" if self.exit_on_start else "running"}
        record["NetworkSettings"]["Ports"] = ({} if self.exit_on_start
                                                else copy.deepcopy(record["HostConfig"]["PortBindings"]))
        self._write(records)
        self._event(("start_exit", identity))

    def stop(self, identity, timeout=120):
        self._event(("stop", identity))
        if self.fail_stop:
            raise LifecycleError("command_failed")
        records = self._read()
        record = next(item for item in records if item["Id"] == identity)
        record["State"] = {"Running": False, "Status": "exited"}
        record["NetworkSettings"]["Ports"] = {}
        self._write(records)

    def remove(self, identity):
        self._event(("remove", identity))
        self._write([item for item in self._read() if item["Id"] != identity])


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class FixtureManager(Manager):
    """Replace only host I/O; real state parsing, locking and transitions run."""

    def __init__(self, config_root, instance, **kwargs):
        instance = copy.deepcopy(instance)
        binding = kwargs.pop('binding', HistoricalBinding())
        instance['storage_identity'] = binding.identity
        instance['historical_import'] = True
        # Only volatile and tiny fixture state paths point into this temporary root.
        fixture_root = Path(instance['paths']['state']).parent
        kwargs.setdefault('lease_system_root', fixture_root)
        kwargs.setdefault('storage_io', FixtureWriter)
        super().__init__(config_root, instance, binding=binding, **kwargs)

    def persistent_json(self, path, value):
        # Explicit tiny-file substitute; real AnchoredRoot integration has its own tests.
        with self.persistent_writer().AnchoredRoot(str(Path(path).parent), lambda: self.binding.verify()) as anchor:
            anchor.atomic_json(Path(path).name, value)
            anchor.check()

    def check_package_admission(self):
        pass  # No package services in the explicit worker fixture.

    def host_path(self, value, *, expected_role=None):
        if self.test_paths and isinstance(value, str) and value.endswith('/state'):
            return value
        return super().host_path(value, expected_role=expected_role)

    def check_mounts(self, targets=None):
        pass

    def host_guards(self):
        pass

    def check_artifacts(self, deployment):
        pass

    def image_evidence(self, deployment):
        return {"image_id": IMAGE, "load_mode": "mmap"}

    def prepare_start(self, deployment):
        # Start's stat-only bind source checks are local filesystem I/O too. Keep
        # their real ordering while modeling declared VM paths as existing dirs.
        real_exists, real_is_dir = Path.exists, Path.is_dir
        with patch.object(Path, "exists", lambda p: True if str(p).startswith("/data/") else real_exists(p)), \
                patch.object(Path, "is_dir", lambda p: True if str(p).startswith("/data/") else real_is_dir(p)):
            super().prepare_start(deployment)


def make_instance(root):
    instance = json.loads((ROOT / "configs/deployments/instances/ai-vm-d0b.json").read_text())
    instance["paths"] = {"state": str(root / "state"),
                         "lock": str(root / "run/llmctl/lifecycle.lock"),
                         "recovery": str(root / "run/llmctl/recovery.json")}
    instance["obsolete_boot_owner_disabled"] = True
    instance["obsolete_boot_owner_evidence"] = "deterministic worker fixture"
    return instance


class ManagerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.configs = self.root / "configs"
        shutil.copytree(ROOT / "configs", self.configs)
        self.instance = make_instance(self.root)
        self.docker = FakeDocker()
        self.clock = FakeClock()
        self.probe_result = "ready"
        self.probe_calls = []
        self.manager = FixtureManager(
            self.configs, self.instance, docker=self.docker,
            probe_fn=self.probe, run_fn=self.fake_run,
            sleep_fn=self.clock.sleep, monotonic_fn=self.clock.monotonic,
            test_paths=True,
        )
        self.key_patch = patch("lifecycle.manager.validate_key_metadata", return_value=None)
        self.key_patch.start()
        self.addCleanup(self.key_patch.stop)

    def probe(self, *args, **kwargs):
        self.probe_calls.append((args, kwargs))
        return self.probe_result

    def fake_run(self, args, **kwargs):
        raise AssertionError(f"unexpected worker subprocess: {args[:2]}")

    def state(self):
        return json.loads((self.root / "state/active.json").read_text())

    def save_state(self, state):
        path = self.root / "state/active.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state))

    def select(self, profile=PROOF, **kwargs):
        return self.manager.dispatch("select", deployment_id=profile, **kwargs)

    def start(self):
        self.select()
        return self.manager.dispatch("start")

    def mutations(self):
        return [call for call in self.docker.calls if call[0] in
                {"create", "start_enter", "start_exit", "stop", "remove"}]

    def test_missing_selection_refuses_start_without_docker(self):
        with self.assertRaises(LifecycleError):
            self.manager.dispatch("start")
        self.assertEqual(self.mutations(), [])
        self.assertNotIn("qwen3-0.6b-smoke", json.dumps(self.state()) if
                         (self.root / "state/active.json").exists() else "")

    def test_missing_state_status_is_stopped_without_smoke_selection(self):
        status = self.manager.status()
        self.assertIsNone(status["selected"])
        self.assertEqual(status["desired"], "stopped")
        self.assertNotEqual(status["observed"], "ready")
        self.assertEqual(self.probe_calls, [])

    def test_invalid_json_refuses_start_without_subprocess(self):
        path = self.root / "state/active.json"
        path.parent.mkdir(parents=True)
        path.write_text('{"model_profile": "invalid-json-sentinel"')
        with self.assertRaises(LifecycleError) as raised:
            self.manager.dispatch("start")
        self.assertNotIn("invalid-json-sentinel", str(raised.exception))
        self.assertEqual(self.docker.calls, [])

    def test_invalid_state_shapes_fail_closed(self):
        for state in ([], {"schema_version": 999}, {"selected": "unknown"}):
            with self.subTest(state=state):
                self.save_state(state)
                with self.assertRaises(LifecycleError):
                    self.manager.dispatch("start")
        self.assertEqual(self.mutations(), [])

    def test_select_records_intentionally_stopped_manual_intent(self):
        self.select()
        state = self.state()
        self.assertEqual(state["selected"], PROOF)
        self.assertEqual(state["desired"], "stopped")
        self.assertEqual(state["boot_policy"], "manual")
        self.assertNotEqual(state["observed"], "ready")
        self.assertEqual(self.mutations(), [])

    def test_unknown_profile_cannot_replace_selection(self):
        self.select()
        before = self.state()
        with self.assertRaises(LifecycleError):
            self.select("missing-profile")
        self.assertEqual(self.state(), before)

    def test_dry_run_start_does_not_write_or_create(self):
        self.select()
        before = (self.root / "state/active.json").read_bytes()
        self.manager.dispatch("start", dry_run=True)
        self.assertEqual((self.root / "state/active.json").read_bytes(), before)
        self.assertEqual(self.mutations(), [])

    def test_successful_start_records_real_ready_container(self):
        self.start()
        state = self.state()
        self.assertEqual(state["observed"], "ready")
        self.assertEqual(state["desired"], "running")
        self.assertTrue(state["container_running"])
        self.assertEqual(len(state["container"]["id"]), 64)
        self.assertTrue(self.docker.inspect(state["container"]["id"])["State"]["Running"])
        self.assertTrue(self.probe_calls)
        self.assertIn("glm-5.3", str(self.probe_calls))

    def test_successful_stop_preserves_selection(self):
        self.start()
        identity = self.state()["container"]["id"]
        self.manager.dispatch("stop")
        state = self.state()
        self.assertEqual(state["selected"], PROOF)
        self.assertEqual(state["desired"], "stopped")
        self.assertEqual(state["observed"], "stopped")
        self.assertFalse(state["container_running"])
        self.assertIn(("stop", identity), self.docker.calls)

    def test_restart_stops_before_starting_and_finishes_ready(self):
        self.start()
        self.docker.calls.clear()
        self.manager.dispatch("restart")
        operations = [call[0] for call in self.mutations()]
        self.assertLess(operations.index("stop"), operations.index("start_enter"))
        self.assertEqual(self.state()["observed"], "ready")

    def test_deactivate_keeps_stopped_tombstone_and_never_resurrects(self):
        self.start()
        self.manager.dispatch("deactivate")
        state = self.state()
        self.assertIsNone(state["selected"])
        self.assertEqual(state["desired"], "stopped")
        self.docker.calls.clear()
        with self.assertRaises(LifecycleError):
            self.manager.dispatch("start")
        self.assertEqual(self.mutations(), [])

    def test_start_guards_fail_before_docker_or_artifact_access(self):
        self.select()
        self.docker.calls.clear()
        with patch.object(self.manager, "check_mounts", side_effect=LifecycleError("mount_uuid_mismatch")), \
                patch.object(self.manager, "check_artifacts") as artifacts:
            with self.assertRaises(LifecycleError):
                self.manager.dispatch("start")
        artifacts.assert_not_called()
        self.assertEqual(self.docker.calls, [])
        self.assertNotEqual(self.state()["observed"], "ready")

    def test_stop_survives_failed_start_guards_and_missing_key(self):
        self.start()
        with patch.object(self.manager, "check_mounts", side_effect=LifecycleError("mount_uuid_mismatch")), \
                patch.object(self.manager, "host_guards", side_effect=LifecycleError("root_pressure")), \
                patch.object(self.manager, "check_artifacts", side_effect=LifecycleError("artifact_missing")), \
                patch("lifecycle.manager.validate_key_metadata", side_effect=LifecycleError("key_file_invalid")):
            result = self.manager.dispatch("stop")
        recovery = json.loads((self.root / "run/llmctl/recovery.json").read_text())
        self.assertFalse(result["container_running"])
        self.assertEqual(result["desired"], "stopped")
        self.assertFalse(result["state_persisted"])
        self.assertFalse(recovery["container_running"])
        self.assertEqual(recovery["desired"], "stopped")

    def test_timeout_records_running_failure_and_explicit_stop_recovers(self):
        self.select()
        self.probe_result = "not_ready"
        with self.assertRaises(LifecycleError):
            self.manager.dispatch("start")
        state = self.state()
        self.assertEqual(state["observed"], "failed")
        self.assertTrue(state["container_running"])
        self.assertTrue(state["failure"])
        self.manager.dispatch("stop")
        self.assertEqual(self.state()["observed"], "stopped")

    def test_auth_failure_is_never_ready(self):
        self.select()
        self.probe_result = "auth_error"
        with self.assertRaises(LifecycleError):
            self.manager.dispatch("start")
        self.assertEqual(self.state()["observed"], "failed")
        self.assertTrue(self.state()["container_running"])

    def test_wrong_model_is_never_ready(self):
        self.select()
        self.probe_result = "wrong_model"
        with self.assertRaises(LifecycleError):
            self.manager.dispatch("start")
        self.assertEqual(self.state()["observed"], "failed")
        self.assertTrue(self.state()["container_running"])

    def test_container_exit_during_start_records_not_running_failure(self):
        self.select()
        self.docker.exit_on_start = True
        with self.assertRaises(LifecycleError):
            self.manager.dispatch("start")
        self.assertEqual(self.state()["observed"], "failed")
        self.assertFalse(self.state()["container_running"])

    def test_create_failure_never_claims_running(self):
        self.select()
        self.docker.fail_create = True
        with self.assertRaises(LifecycleError):
            self.manager.dispatch("start")
        self.assertEqual(self.state()["observed"], "failed")
        self.assertFalse(self.state()["container_running"])

    def test_start_command_failure_retains_container_identity_for_stop(self):
        self.select()
        self.docker.fail_start = True
        with self.assertRaises(LifecycleError):
            self.manager.dispatch("start")
        self.assertIsNotNone(self.state()["container"])
        self.assertEqual(self.state()["observed"], "failed")
        self.manager.dispatch("stop")
        self.assertFalse(self.state()["container_running"])

    def test_stop_failure_never_claims_stopped(self):
        self.start()
        self.docker.fail_stop = True
        with self.assertRaises(LifecycleError):
            self.manager.dispatch("stop")
        state = self.state()
        self.assertEqual(state["desired"], "stopped")
        self.assertEqual(state["observed"], "failed")
        self.assertTrue(state["container_running"])

    def test_status_does_not_trust_ready_state_when_container_has_exited(self):
        self.start()
        identity = self.state()["container"]["id"]
        self.docker.stop(identity)
        status = self.manager.status()
        self.assertNotEqual(status["observed"], "ready")
        self.assertFalse(status["container_running"])

    def test_status_wrong_model_is_unhealthy_without_artifact_or_guard_checks(self):
        self.start()
        self.probe_result = "wrong_model"
        with patch.object(self.manager, "check_artifacts", side_effect=AssertionError("weights touched")), \
                patch.object(self.manager, "host_guards", side_effect=AssertionError("start guard used")):
            status = self.manager.status()
        self.assertEqual(status["observed"], "unhealthy")

    def test_selection_conflict_requires_explicit_stop_first(self):
        self.start()
        self.docker.calls.clear()
        with self.assertRaises(LifecycleError):
            self.select(MEASURE)
        self.assertEqual(self.state()["selected"], PROOF)
        self.assertEqual(self.mutations(), [])

    def test_legacy_backend_on_other_port_blocks_start(self):
        self.start()
        self.manager.dispatch("stop")
        records = self.docker._read()
        other = copy.deepcopy(records[0])
        other["Id"] = "e" * 64
        other["Name"] = "/minimax-m3-mxfp8-poc"
        other["Config"]["Labels"] = {"com.docker.compose.project": "compose"}
        other["State"] = {"Running": True, "Status": "running"}
        other["HostConfig"]["PortBindings"] = {
            "30000/tcp": [{"HostIp": "127.0.0.1", "HostPort": "30999"}]}
        other["NetworkSettings"]["Ports"] = copy.deepcopy(other["HostConfig"]["PortBindings"])
        records.append(other)
        self.docker._write(records)
        self.docker.calls.clear()
        with self.assertRaises(LifecycleError):
            self.manager.dispatch("start")
        self.assertEqual(self.mutations(), [])
        self.assertTrue(self.docker.inspect(other["Id"])["State"]["Running"])

    def test_stop_refuses_changed_ownership_labels(self):
        self.start()
        records = self.docker._read()
        records[0]["Config"]["Labels"] = {}
        self.docker._write(records)
        self.docker.calls.clear()
        with self.assertRaises(LifecycleError):
            self.manager.dispatch("stop")
        self.assertNotIn("stop", [call[0] for call in self.docker.calls])
        self.assertTrue(self.docker._read()[0]["State"]["Running"])
        self.assertEqual(self.state()["observed"], "failed")
        self.assertTrue(self.state()["failure"])

    def test_stop_does_not_follow_reused_container_name(self):
        self.start()
        records = self.docker._read()
        records[0]["Id"] = "f" * 64
        records[0]["Config"]["Labels"] = {}
        self.docker._write(records)
        self.docker.calls.clear()
        try:
            self.manager.dispatch("stop")
        except LifecycleError:
            pass  # Refusal or exact-ID absence are both safe outcomes.
        self.assertNotIn(("stop", "f" * 64), self.docker.calls)
        self.assertTrue(self.docker._read()[0]["State"]["Running"])

    def test_unrelated_running_container_is_never_stopped(self):
        self.start()
        records = self.docker._read()
        unrelated = copy.deepcopy(records[0])
        unrelated["Id"] = "a" * 64
        unrelated["Name"] = "/unrelated-worker-service"
        unrelated["Config"]["Labels"] = {"service": "unrelated"}
        records.append(unrelated)
        self.docker._write(records)
        self.manager.dispatch("stop")
        self.assertTrue(self.docker.inspect(unrelated["Id"])["State"]["Running"])
        self.assertNotIn(("stop", unrelated["Id"]), self.docker.calls)

    def test_legacy_qwen_active_flag_migrates_to_stopped_intent(self):
        model = "qwen3-30b-a3b-instruct-2507"
        self.save_state({"model_profile": model, "runtime_profile": "sglang",
                         "compose_file": "/data/services/llm-manager/compose/sglang-qwen3-30b.compose.yml",
                         "container_name": "sglang-qwen3-30b-a3b-instruct-2507",
                         "bind": "127.0.0.1", "port": 30001,
                         "endpoint": "http://127.0.0.1:30001/v1",
                         "model_path": "/data/models/qwen3-30b-a3b-instruct-2507",
                         "image": "lmsysorg/sglang:v0.5.14-cu130", "status": "active"})
        status = self.manager.status()
        self.assertIn(model, status["selected"])
        self.assertEqual(status["desired"], "stopped")
        self.assertEqual(status["boot_policy"], "manual")
        self.assertNotEqual(status["observed"], "ready")
        self.assertEqual(self.mutations(), [])

    def test_resume_selection_alone_does_not_boot_start(self):
        self.select(boot_policy="resume")
        self.docker.calls.clear()
        self.manager.dispatch("boot-start")
        self.assertEqual(self.mutations(), [])
        self.assertEqual(self.state()["desired"], "stopped")

    def test_manual_policy_does_not_resume_after_boot_stop(self):
        self.start()
        self.manager.dispatch("boot-stop")
        self.assertEqual(self.state()["desired"], "running")
        self.docker.calls.clear()
        self.manager.dispatch("boot-start")
        self.assertEqual(self.mutations(), [])

    def test_resume_policy_replays_running_intent_after_boot_stop(self):
        self.select(boot_policy="resume")
        self.manager.dispatch("start")
        self.manager.dispatch("boot-stop")
        self.assertEqual(self.state()["desired"], "running")
        self.manager.dispatch("boot-start")
        self.assertEqual(self.state()["observed"], "ready")

    def test_explicit_stop_disables_resume_even_with_resume_policy(self):
        self.select(boot_policy="resume")
        self.manager.dispatch("start")
        self.manager.dispatch("stop")
        self.docker.calls.clear()
        self.manager.dispatch("boot-start")
        self.assertEqual(self.mutations(), [])
        self.assertEqual(self.state()["desired"], "stopped")

    def test_recover_stop_uses_trusted_identity_despite_corrupt_primary(self):
        self.start()
        identity = self.state()["container"]["id"]
        (self.root / "state/active.json").write_text("broken")
        with patch.object(self.manager, "check_mounts", side_effect=LifecycleError("unmounted_required_disk")):
            result = self.manager.dispatch("recover-stop")
        self.assertFalse(result["container_running"])
        self.assertIn(("stop", identity), self.docker.calls)

    def test_recover_stop_rejects_untrusted_recovery_id(self):
        self.start()
        recovery_path = self.root / "run/llmctl/recovery.json"
        recovery = json.loads(recovery_path.read_text())
        recovery["container"]["id"] = "--all"
        recovery_path.write_text(json.dumps(recovery))
        self.docker.calls.clear()
        with self.assertRaises(LifecycleError):
            self.manager.dispatch("recover-stop")
        self.assertEqual(self.mutations(), [])

    def test_status_reports_unhealthy_when_docker_probe_cannot_establish_identity(self):
        self.start()
        with patch.object(self.docker, "inspect", side_effect=LifecycleError("command_failed")):
            result = self.manager.status()
        self.assertEqual(result["observed"], "unhealthy")
        self.assertIsNone(result["container_running"])

    def test_emergency_stop_journal_overrides_stale_running_intent(self):
        self.select(boot_policy="resume")
        self.manager.dispatch("start")
        with patch.object(self.manager, "check_mounts", side_effect=LifecycleError("unmounted_required_disk")):
            self.manager.dispatch("stop")
        self.assertEqual(self.state()["desired"], "running", "fixture primary should remain stale")
        self.assertEqual(self.manager.status()["desired"], "stopped")
        self.docker.calls.clear()
        self.manager.dispatch("boot-start")
        self.assertEqual(self.mutations(), [])

    def test_state_selection_cannot_disagree_with_container_deployment(self):
        self.start()
        state = self.state()
        state["selected"] = MEASURE
        self.save_state(state)
        self.docker.calls.clear()
        with self.assertRaisesRegex(LifecycleError, "state_deployment_identity_mismatch"):
            self.manager.dispatch("start")
        self.assertEqual(self.mutations(), [])

    def test_changed_context_cannot_reuse_same_alias_as_readiness(self):
        self.start()
        self.manager.dispatch("stop")
        path = self.configs / "deployments" / (PROOF + ".json")
        profile = json.loads(path.read_text())
        profile["launch"]["context_size"] = 32768
        path.write_text(json.dumps(profile))
        self.docker.calls.clear()
        with self.assertRaisesRegex(LifecycleError, "container_launch_contract_mismatch"):
            self.manager.dispatch("start")
        self.assertNotIn("start_enter", [call[0] for call in self.docker.calls])
        self.assertEqual(self.state()["observed"], "failed")

    def test_reused_container_rejects_changed_runtime_contract(self):
        self.start()
        self.manager.dispatch("stop")
        original = self.docker._read()
        mutations = {
            "image": lambda c: c.update(Image="sha256:" + "d" * 64),
            "entrypoint": lambda c: c["Config"].update(Entrypoint=["/bin/sh"]),
            "mount": lambda c: c["Mounts"][0].update(RW=True),
            "environment": lambda c: c["Config"].update(Env=["XDG_CACHE_HOME=/root"]),
            "logs": lambda c: c["HostConfig"].update(LogConfig={"Type": "json-file", "Config": {}}),
            "gpu": lambda c: c["HostConfig"].update(DeviceRequests=[{"DeviceIDs": ["0"]}]),
        }
        for name, mutate in mutations.items():
            with self.subTest(contract=name):
                records = copy.deepcopy(original)
                mutate(records[0])
                self.docker._write(records)
                self.docker.calls.clear()
                with self.assertRaises(LifecycleError):
                    self.manager.dispatch("start")
                self.assertNotIn("start_enter", [call[0] for call in self.docker.calls])
        self.docker._write(original)

    def test_status_cannot_certify_ready_for_changed_launch_even_with_ready_api(self):
        self.start()
        records = self.docker._read()
        command = records[0]["Config"]["Cmd"]
        command[command.index("--ctx-size") + 1] = "32768"
        self.docker._write(records)
        self.probe_calls.clear()
        result = self.manager.status()
        self.assertEqual(result["observed"], "unhealthy")
        self.assertEqual(self.probe_calls, [])

    def test_untrusted_extra_state_fields_are_not_reported(self):
        self.start()
        state = self.state()
        state["extra_private_metadata"] = "fixture-private-sentinel"
        state["container"]["extra_private_metadata"] = "fixture-private-sentinel"
        self.save_state(state)
        result = self.manager.status()
        self.assertNotIn("fixture-private-sentinel", json.dumps(result))

    def test_invalid_failure_text_is_not_echoed(self):
        self.select()
        state = self.state()
        state["failure"] = "invalid body fixture-private-sentinel"
        self.save_state(state)
        with self.assertRaises(LifecycleError) as raised:
            self.manager.status()
        self.assertNotIn("fixture-private-sentinel", str(raised.exception))

    def install_legacy_fixture(self, profile):
        d = self.manager.deployment(profile)
        binding = {"30000/tcp": [{"HostIp": "127.0.0.1", "HostPort": str(d["endpoint"]["port"])}]}
        record = {"Id": "c" * 64, "Name": "/" + d["container_name"], "Image": IMAGE,
                  "State": {"Running": False, "Status": "exited"},
                  "Config": {"Image": d["image_tag"],
                             "Labels": {"com.docker.compose.project": "compose",
                                        "com.docker.compose.service": d["compose_service"]},
                             "Cmd": ["python3", "-m", "sglang.launch_server", "--model-path",
                                     d["paths"]["model"], "--served-model-name", profile,
                                     "--host", "0.0.0.0", "--port", "30000"]},
                  "Mounts": [{"Source": "/data/models", "Destination": "/data/models", "RW": False}],
                  "HostConfig": {"NetworkMode": "compose_default", "IpcMode": "host",
                                 "PortBindings": binding, "PublishAllPorts": False,
                                 "RestartPolicy": {"Name": "no"}},
                  "NetworkSettings": {"Ports": {}, "Networks": {"compose_default": {}}}}
        self.docker._write([record])
        self.docker.compose = {"services": {d["compose_service"]: {
            "image": d["image_tag"], "container_name": d["container_name"],
            "ipc": "host", "restart": "no", "ports": [
                {"host_ip": "127.0.0.1", "published": str(d["endpoint"]["port"]),
                 "target": 30000, "protocol": "tcp"}]}}}
        return record

    def test_existing_qwen30b_start_stop_restart_retains_identity(self):
        profile = "qwen3-30b-a3b-instruct-2507"
        record = self.install_legacy_fixture(profile)
        self.select(profile)
        self.manager.dispatch("start")
        self.assertEqual(self.state()["observed"], "ready")
        self.manager.dispatch("restart")
        self.assertEqual(self.state()["observed"], "ready")
        self.assertEqual(self.state()["container"]["id"], record["Id"])
        self.manager.dispatch("stop")
        self.assertEqual(self.state()["observed"], "stopped")
        self.assertNotIn("create", [call[0] for call in self.docker.calls])

    def test_existing_smoke_requires_explicit_selection_and_still_starts(self):
        profile = "qwen3-0.6b-smoke"
        self.install_legacy_fixture(profile)
        with self.assertRaises(LifecycleError):
            self.manager.dispatch("start")
        self.select(profile)
        self.manager.dispatch("start")
        self.assertEqual(self.state()["selected"], profile)
        self.assertEqual(self.state()["observed"], "ready")

    def test_legacy_rendered_extra_public_mapping_blocks_start(self):
        profile = "qwen3-30b-a3b-instruct-2507"
        self.install_legacy_fixture(profile)
        self.select(profile)
        service = next(iter(self.docker.compose["services"].values()))
        service["ports"].append({"host_ip": "0.0.0.0", "published": "39999", "target": 39999})
        self.docker.calls.clear()
        with self.assertRaisesRegex(LifecycleError, "network_policy_invalid"):
            self.manager.dispatch("start")
        self.assertNotIn("start_enter", [call[0] for call in self.docker.calls])

    def test_existing_legacy_stop_survives_missing_compose_and_profile_guards(self):
        profile = "qwen3-30b-a3b-instruct-2507"
        self.install_legacy_fixture(profile)
        self.select(profile)
        self.manager.dispatch("start")
        self.docker.compose = None
        with patch.object(self.manager, "deployment", side_effect=LifecycleError("invalid_or_missing_json")), \
                patch.object(self.manager, "host_guards", side_effect=LifecycleError("root_pressure")):
            result = self.manager.dispatch("stop")
        self.assertEqual(result["observed"], "stopped")

    def test_stop_uses_valid_primary_even_when_optional_recovery_is_corrupt(self):
        self.start()
        identity = self.state()["container"]["id"]
        (self.root / "run/llmctl/recovery.json").write_text("broken journal")
        result = self.manager.dispatch("stop")
        self.assertFalse(result["container_running"])
        self.assertIn(("stop", identity), self.docker.calls)

    def test_stop_with_missing_primary_uses_recovery_instead_of_erasing_identity(self):
        self.start()
        identity = self.state()["container"]["id"]
        (self.root / "state/active.json").unlink()
        with patch.object(self.manager, "check_mounts", side_effect=LifecycleError("unmounted_required_disk")):
            result = self.manager.dispatch("stop")
        self.assertIn(("stop", identity), self.docker.calls)
        self.assertFalse(result["container_running"])
        self.assertFalse(self.docker.inspect(identity)["State"]["Running"])
        recovery = json.loads((self.root / "run/llmctl/recovery.json").read_text())
        self.assertEqual(recovery["container"]["id"], identity)

    def test_stop_continues_when_both_state_journals_cannot_be_written(self):
        self.start()
        identity = self.state()["container"]["id"]
        with patch("lifecycle.manager.atomic_json", side_effect=OSError("fixture write failure")), \
                patch.object(FixtureWriter.AnchoredRoot, 'atomic_json', side_effect=OSError('fixture write failure')):
            result = self.manager.dispatch("stop")
        self.assertFalse(result["container_running"])
        self.assertFalse(result["state_persisted"])
        self.assertIn(("stop", identity), self.docker.calls)

    def test_interrupted_start_keeps_stoppable_identity_and_failed_state(self):
        self.select()
        with patch.object(self.docker, "start", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.manager.dispatch("start")
        self.assertIsNotNone(self.state()["container"])
        self.assertEqual(self.state()["observed"], "failed")
        self.manager.dispatch("stop")
        self.assertFalse(self.state()["container_running"])

    def test_stale_starting_flag_without_live_transition_is_unhealthy(self):
        self.start()
        state = self.state()
        state["observed"] = "starting"
        self.save_state(state)
        self.probe_result = "not_ready"
        self.assertEqual(self.manager.status()["observed"], "unhealthy")


class OfflineStatusTests(unittest.TestCase):
    setUp = ManagerTests.setUp
    probe = ManagerTests.probe
    fake_run = ManagerTests.fake_run
    state = ManagerTests.state
    save_state = ManagerTests.save_state
    select = ManagerTests.select
    start = ManagerTests.start

    def forbid_live_io(self):
        stack = ExitStack()
        for method in ("inventory", "inspect", "capture", "create", "start", "stop", "remove"):
            stack.enter_context(patch.object(self.docker, method, side_effect=AssertionError("offline Docker access")))
        for method in ("probe", "run", "deployment", "host_guards", "check_artifacts", "image_evidence"):
            stack.enter_context(patch.object(self.manager, method, side_effect=AssertionError("offline live access")))
        stack.enter_context(patch("lifecycle.manager.validate_key_metadata", side_effect=AssertionError("offline key access")))
        return stack

    def test_saved_ready_is_recorded_only_without_live_access_or_writes(self):
        self.start()
        before = (self.root / "state/active.json").read_bytes()
        with self.forbid_live_io():
            result = self.manager.offline_status()
        self.assertEqual(result["recorded_observed"], "ready")
        self.assertIsNone(result["observed"])
        self.assertIsNone(result["container_running"])
        self.assertEqual(result["observation"], "not_performed_offline")
        self.assertEqual(result["selected"], PROOF)
        self.assertEqual((self.root / "state/active.json").read_bytes(), before)

    def test_saved_stopped_preserves_intent_without_claiming_live_stop(self):
        self.select()
        with self.forbid_live_io():
            result = self.manager.offline_status()
        self.assertEqual(result["desired"], "stopped")
        self.assertEqual(result["recorded_observed"], "stopped")
        self.assertIsNone(result["observed"])
        self.assertIsNone(result["container_running"])

    def test_missing_state_offline_has_no_smoke_or_live_observation(self):
        with self.forbid_live_io():
            result = self.manager.offline_status()
        self.assertTrue(result["configured"])
        self.assertIsNone(result["selected"])
        self.assertEqual(result["desired"], "stopped")
        self.assertIsNone(result["observed"])
        self.assertIsNone(result["container_running"])
        self.assertFalse((self.root / "state/active.json").exists())

    def test_invalid_state_offline_fails_without_live_access_or_echo(self):
        path = self.root / "state/active.json"
        path.parent.mkdir()
        path.write_text('{"broken": "fixture-invalid-sentinel"')
        with self.forbid_live_io(), self.assertRaises(LifecycleError) as raised:
            self.manager.offline_status()
        self.assertNotIn("fixture-invalid-sentinel", str(raised.exception))

    def test_cli_missing_instance_is_unconfigured_offline_and_live_failure(self):
        for offline in (True, False):
            with self.subTest(offline=offline):
                args = argparse.Namespace(command="status", offline=offline,
                                          instance=self.root / "absent-instance.json")
                output = io.StringIO()
                with patch("lifecycle.manager.Manager", side_effect=AssertionError("constructed live manager")), \
                        patch("lifecycle.manager.signal.signal"), redirect_stdout(output):
                    code = cli(args)
                result = json.loads(output.getvalue())
                self.assertIsNone(result["container_running"])
                if offline:
                    self.assertEqual(code, 0)
                    self.assertFalse(result["configured"])
                    self.assertIsNone(result["recorded_observed"])
                    self.assertIsNone(result["observed"])
                else:
                    self.assertEqual(code, 1)
                    self.assertEqual(result["observed"], "failed")
                    self.assertEqual(result["failure"], "instance_missing_observation_unavailable")


class StorageValidationTests(unittest.TestCase):
    setUp = ManagerTests.setUp
    probe = ManagerTests.probe
    fake_run = ManagerTests.fake_run

    def test_registered_mount_check_delegates_to_shared_binding(self):
        with patch.object(self.manager.binding, 'verify') as verify:
            Manager.check_mounts(self.manager)
            verify.assert_called_once_with(roles=('data', 'models'))
        self.assertEqual(self.docker.calls, [])

    def test_data_only_check_requests_data_role(self):
        with patch.object(self.manager.binding, 'verify') as verify:
            Manager.check_mounts(self.manager, {'data'})
            verify.assert_called_once_with(roles={'data'})

    def test_bad_registered_mount_fails_before_docker(self):
        from lifecycle.storage_binding import BindingError
        with patch.object(self.manager.binding, 'verify', side_effect=BindingError('wrong_uuid')):
            with self.assertRaisesRegex(LifecycleError, 'registered_storage_verification_failed'):
                Manager.check_mounts(self.manager)
        self.assertEqual(self.docker.calls, [])

    def test_instance_cannot_override_registered_identity(self):
        self.manager.instance['storage_identity']['models']['uuid'] = 'wrong'
        # Keep fixture binding independent, as the real binding identity property is.
        self.manager.binding.identity = copy.deepcopy(HistoricalBinding().identity)
        with self.assertRaisesRegex(LifecycleError, 'registry_instance_identity_mismatch'):
            Manager.check_mounts(self.manager)

    def artifact_fixture(self):
        d = self.manager.deployment(PROOF)
        root = self.root / "tiny-model"
        root.mkdir()
        entries = []
        for index in range(1, 12):
            path = f"retained/shard-{index:02}.gguf"
            output = root / path
            output.parent.mkdir(exist_ok=True)
            output.write_bytes(b"x" * index)
            entries.append({"path": path, "size_bytes": index})
        d["_model"].update(model_root=str(root), artifacts=entries, artifact_count=11,
                           total_bytes=sum(range(1, 12)), load_entry=entries[0]["path"])
        self.manager.instance["model_integrity"][d["model"]] = {
            "verified": True, "revision": d["_model"]["revision"], "evidence": "synthetic fixture"}
        return d, root

    def test_all_eleven_artifact_sizes_pass_without_payload_hashing(self):
        d, _ = self.artifact_fixture()
        with patch.object(Path, "read_bytes", side_effect=AssertionError("payload read")):
            Manager.check_artifacts(self.manager, d)

    def test_missing_eleventh_artifact_fails(self):
        d, root = self.artifact_fixture()
        (root / d["_model"]["artifacts"][-1]["path"]).unlink()
        with self.assertRaisesRegex(LifecycleError, "artifact_missing_or_symlink"):
            Manager.check_artifacts(self.manager, d)

    def test_wrong_artifact_size_fails(self):
        d, root = self.artifact_fixture()
        (root / d["_model"]["artifacts"][0]["path"]).write_bytes(b"wrong size")
        with self.assertRaisesRegex(LifecycleError, "artifact_size_mismatch"):
            Manager.check_artifacts(self.manager, d)

    def test_artifact_symlink_fails(self):
        d, root = self.artifact_fixture()
        first = root / d["_model"]["artifacts"][0]["path"]
        first.unlink()
        first.symlink_to(root / d["_model"]["artifacts"][1]["path"])
        with self.assertRaisesRegex(LifecycleError, "artifact_missing_or_symlink"):
            Manager.check_artifacts(self.manager, d)

    def test_missing_d1_integrity_evidence_fails(self):
        d, _ = self.artifact_fixture()
        self.manager.instance["model_integrity"][d["model"]]["verified"] = False
        with self.assertRaisesRegex(LifecycleError, "d1_integrity_evidence_required"):
            Manager.check_artifacts(self.manager, d)


def process_hold_lock(path, entered, release):
    with process_lock(Path(path)):
        entered.set()
        if not release.wait(15):
            raise AssertionError("test lock release timed out")


def process_action(configs, instance, action, inventory, event_queue, attempted,
                   finished, release=None, entered=None):
    """Spawn target; all external operations remain inside this fake."""
    docker = FakeDocker(inventory, event_queue, release, entered)
    clock = FakeClock()
    manager = FixtureManager(Path(configs), instance, docker=docker,
                             probe_fn=lambda *args, **kwargs: "ready",
                             run_fn=lambda *args, **kwargs: "",
                             sleep_fn=clock.sleep, monotonic_fn=clock.monotonic,
                             test_paths=True)
    attempted.set()
    try:
        with patch("lifecycle.manager.validate_key_metadata", return_value=None):
            manager.dispatch(action)
        event_queue.put(("completed", action))
    except BaseException as exc:
        event_queue.put(("failed", action, type(exc).__name__, str(exc)))
        raise
    finally:
        finished.set()


class ProcessSerializationTests(unittest.TestCase):
    """Two real processes share the filesystem state and actual OS mutex."""

    setUp = ManagerTests.setUp
    probe = ManagerTests.probe
    fake_run = ManagerTests.fake_run
    state = ManagerTests.state
    select = ManagerTests.select
    start = ManagerTests.start
    save_state = ManagerTests.save_state

    def test_status_reports_starting_only_with_real_mutation_in_progress(self):
        self.start()
        state = self.state()
        state["observed"] = "starting"
        self.save_state(state)
        self.probe_result = "not_ready"
        context = multiprocessing.get_context("spawn")
        entered, release = context.Event(), context.Event()
        process = context.Process(target=process_hold_lock,
                                  args=(str(self.manager.lock_file), entered, release))
        try:
            process.start()
            self.assertTrue(entered.wait(10))
            self.assertEqual(self.manager.status()["observed"], "starting")
            release.set()
            process.join(10)
            self.assertEqual(process.exitcode, 0)
            self.assertEqual(self.manager.status()["observed"], "unhealthy")
        finally:
            release.set()
            if process.pid is not None and process.is_alive():
                process.terminate()
            if process.pid is not None:
                process.join(5)

    def test_process_stop_waits_for_complete_start_and_rereads_identity(self):
        self.select()
        context = multiprocessing.get_context("spawn")
        queue = context.Queue()
        release, entered = context.Event(), context.Event()
        start_attempted, start_finished = context.Event(), context.Event()
        stop_attempted, stop_finished = context.Event(), context.Event()
        inventory = str(self.root / "docker.json")
        start = context.Process(target=process_action,
                                args=(str(self.configs), self.instance, "start", inventory,
                                      queue, start_attempted, start_finished, release, entered))
        stop = context.Process(target=process_action,
                               args=(str(self.configs), self.instance, "stop", inventory,
                                     queue, stop_attempted, stop_finished))
        processes = [start, stop]
        try:
            start.start()
            self.assertTrue(entered.wait(10), "start did not reach fake Docker.start")
            stop.start()
            self.assertTrue(stop_attempted.wait(10), "stop process did not begin")
            self.assertFalse(stop_finished.wait(0.25), "stop bypassed in-progress start's mutex")
            self.assertFalse(start_finished.is_set())
            release.set()
            start.join(10)
            stop.join(10)
            self.assertEqual(start.exitcode, 0)
            self.assertEqual(stop.exitcode, 0)
            self.assertEqual(self.state()["observed"], "stopped")
            self.assertEqual(self.state()["desired"], "stopped")
            self.assertFalse(self.state()["container_running"])
            events = []
            while not queue.empty():
                events.append(queue.get(timeout=1))
            start_exit = next(i for i, event in enumerate(events) if event[0] == "start_exit")
            stopped = next(i for i, event in enumerate(events) if event[0] == "stop")
            self.assertLess(start_exit, stopped)
            self.assertEqual(events[start_exit][1], events[stopped][1],
                             "stop did not reread the identity written under start's lock")
        finally:
            release.set()
            for process in processes:
                if process.pid is not None and process.is_alive():
                    process.terminate()
                if process.pid is not None:
                    process.join(5)
            queue.close()


if __name__ == "__main__":
    unittest.main()
