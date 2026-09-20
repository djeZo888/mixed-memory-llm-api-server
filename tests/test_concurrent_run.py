"""Closed concurrent RUN composition checks; all host and request I/O is fake.

These checks establish scheduling and recovery behavior, never native capacity,
model correctness, runtime allocation or measured concurrent performance.
"""
import copy
import json
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from benchmark import concurrent_run as run, fixtures, profiles, runner
from benchmark.host import LinuxHost


def row(identifier="offline", *, status="PASS", started=1.0, ended=3.0,
        first_output=0.5, last_output=1.5):
    return {"id": identifier, "status": status,
            "sample": {"request_started_monotonic_s": started,
                       "request_ended_monotonic_s": ended,
                       "client_timing": {"ttft_any_output_seconds": first_output,
                                         "last_output_seconds": last_output}}}


class ConcurrentSchedulingTests(unittest.TestCase):
    def test_first_pair_dispatches_both_even_if_glm_finishes_immediately(self):
        # This catches the race where glm_done incorrectly suppresses even the
        # first Qwen request. No delay is needed to make a short GLM legal.
        for _ in range(30):
            calls = []
            lock = threading.Lock()
            def invoke(job):
                with lock:
                    calls.append(job["id"])
                return row(job["id"])
            result = run.execute_round({"id": "g"}, [{"id": "q" + str(i)} for i in range(3)], invoke)
            self.assertEqual(result["status"], "COMPLETE")
            self.assertEqual(calls.count("g"), 1)
            self.assertEqual(calls.count("q0"), 1)

    def test_first_pair_runs_concurrently_and_qwen_lane_is_serial_bounded(self):
        for maximum in (3, 8):
            with self.subTest(maximum=maximum):
                entered = threading.Barrier(2)
                q_done = threading.Event()
                calls, outstanding = [], [0]
                guard = threading.Lock()
                def invoke(job):
                    identifier = job["id"]
                    if identifier in ("g", "q0"):
                        entered.wait(timeout=2)
                    if identifier == "g":
                        self.assertTrue(q_done.wait(timeout=2))
                    else:
                        with guard:
                            outstanding[0] += 1
                            self.assertEqual(outstanding[0], 1)
                            calls.append(identifier)
                            outstanding[0] -= 1
                        if identifier == "q" + str(maximum - 1):
                            q_done.set()
                    return row(identifier)
                result = run.execute_round({"id": "g"},
                                  [{"id": "q" + str(i)} for i in range(maximum)], invoke)
                self.assertEqual(result["status"], "COMPLETE", result)
                self.assertEqual(calls, ["q" + str(i) for i in range(maximum)])

    def test_framing_disposition_does_not_cancel_healthy_peer(self):
        paired = threading.Barrier(2)
        q_done = threading.Event()
        drained = []
        def invoke(job):
            if job["id"] in ("g", "q0"):
                paired.wait(timeout=2)
            if job["id"] == "g":
                self.assertTrue(q_done.wait(timeout=2))
                drained.append("g")
                return row("g")
            q_done.set()
            return {**row("q", status="PASS"),
                    "strict_framing": {"status": "HARNESS_FAILURE"},
                    "semantic_retrieval": {"status": "PASS"}}
        result = run.execute_round({"id": "g"}, [{"id": "q" + str(i)} for i in range(3)], invoke)
        self.assertEqual(result["status"], "COMPLETE")
        self.assertEqual(drained, ["g"])

    def test_output_cap_is_timing_only_and_low_decode_never_speed_abort(self):
        paired = threading.Barrier(2)
        calls = []
        def invoke(job):
            if job["id"] in ("g", "q0"):
                paired.wait(timeout=2)
            calls.append(job["id"])
            return {**row(job["id"], status="TIMING_ONLY"),
                    "finish_reason": "length", "completion_tokens": 256,
                    "native_tokens_per_second": 0.001}
        result = run.execute_round({"id": "g"}, [{"id": "q" + str(i)} for i in range(3)], invoke)
        self.assertEqual(result["status"], "COMPLETE")
        self.assertIn("g", calls)
        self.assertIn("q0", calls)

    def test_last_admitted_qwen_drains_and_no_filler_starts_after_glm_ends(self):
        q_started = threading.Event()
        g_started = threading.Event()
        glm_thread, calls = [], []
        def invoke(job):
            calls.append(job["id"])
            if job["id"] == "g":
                glm_thread.append(threading.current_thread())
                g_started.set()
                self.assertTrue(q_started.wait(timeout=2))
            else:
                q_started.set()
                self.assertTrue(g_started.wait(timeout=2))
                glm_thread[0].join(timeout=2)
                self.assertFalse(glm_thread[0].is_alive())
            return row(job["id"])
        result = run.execute_round({"id": "g"}, [{"id": "q" + str(i)} for i in range(8)], invoke)
        self.assertEqual(result["status"], "COMPLETE", result)
        self.assertCountEqual(calls, ["g", "q0"])

    def test_overlap_reports_actual_phase_intersections_and_tail(self):
        g = row("g", started=10, ended=30, first_output=15, last_output=19)
        q = row("q", started=12, ended=35, first_output=10, last_output=20)
        overlap = run.summarize_overlap(g, [q])["pairs"][0]
        self.assertEqual(overlap["request_request_seconds"], 18)
        self.assertEqual(overlap["prefill_proxy_prefill_proxy_seconds"], 10)
        self.assertEqual(overlap["prefill_proxy_decode_seconds"], 3)
        self.assertEqual(overlap["decode_prefill_proxy_seconds"], 0)
        self.assertEqual(overlap["decode_decode_seconds"], 4)
        self.assertEqual(overlap["qwen_tail_after_glm_seconds"], 5)
        unknown = run.summarize_overlap(row(first_output=None, last_output=None), [q])["pairs"][0]
        self.assertIsNone(unknown["decode_decode_seconds"])

    def test_interrupt_halts_filler_admission_but_admitted_pair_drains(self):
        stop, q_done = threading.Event(), threading.Event()
        paired = threading.Barrier(2)
        calls = []
        def invoke(job):
            calls.append(job["id"])
            paired.wait(timeout=2)
            if job["id"] == "g":
                self.assertTrue(q_done.wait(timeout=2))
            else:
                stop.set()
                q_done.set()
            return row(job["id"])
        result = run.execute_round({"id": "g"}, [{"id": "q" + str(i)} for i in range(8)],
                                   invoke, stop_event=stop)
        self.assertEqual(result["status"], "COMPLETE")
        self.assertCountEqual(calls, ["g", "q0"])

    def test_supervisor_join_interrupt_drains_all_admitted_lanes_before_propagating(self):
        entered, release = threading.Event(), threading.Event()
        mutex = threading.Lock()
        active, drained, joined, workers = [], [], [], []
        def invoke(job):
            with mutex:
                active.append(job["id"])
                workers.append(threading.current_thread())
                if len(active) == 2:
                    entered.set()
            self.assertTrue(release.wait(timeout=2))
            drained.append(job["id"])
            return row(job["id"])
        original_join = threading.Thread.join
        interrupted = [False]
        def join(thread, *args, **kwargs):
            joined.append(thread)
            if not interrupted[0]:
                self.assertTrue(entered.wait(timeout=2))
                interrupted[0] = True
                release.set()
                raise KeyboardInterrupt()
            return original_join(thread, *args, **kwargs)
        try:
            with patch.object(threading.Thread, "join", join):
                with self.assertRaises(KeyboardInterrupt):
                    run.execute_round({"id": "g"}, [{"id": "q" + str(i)} for i in range(3)], invoke)
            at_propagation = list(drained)
            alive_at_propagation = [thread.is_alive() for thread in joined]
        finally:
            release.set()
            for thread in set(workers):
                original_join(thread, timeout=2)
        self.assertTrue(interrupted[0])
        self.assertIn("g", at_propagation)
        self.assertIn("q0", at_propagation)
        self.assertFalse(any(alive_at_propagation))


class ConcurrentRecoveryTests(unittest.TestCase):
    def test_recovery_uses_canonical_recover_then_authenticated_lan_finalize(self):
        calls = []
        phase = ["NEW"]
        status = {"phase": "POST_RELEASE_LAN_VERIFICATION_PENDING", "original_snapshot": "offline-preserved"}
        receipt = {"offline_lan_verified": True}
        def host_call(op, **kwargs):
            calls.append((op, kwargs))
            if op == "status":
                return {**status, "phase": phase[0]}
            if op == "verify_restoration":
                self.assertEqual(kwargs, {"receipt": receipt})
                phase[0] = "RESTORED"
                return {"phase": "RESTORED"}
            self.assertEqual(op, "recover")
            phase[0] = "POST_RELEASE_LAN_VERIFICATION_PENDING"
            return {"phase": "POST_RELEASE_LAN_VERIFICATION_PENDING"}
        host = Mock()
        host.call.side_effect = host_call
        def verify(observed, key, control_key):
            self.assertEqual(observed, status)
            self.assertEqual((key, control_key), ("offline-inference", "offline-control"))
            calls.append(("lan_verify", {}))
            return receipt
        run.restore_and_finalize(host, "offline-inference", "offline-control", verify=verify)
        self.assertEqual([op for op, _ in calls],
                         ["status", "recover", "status", "lan_verify", "verify_restoration", "status"])
        self.assertNotIn("restore", [op for op, _ in calls])

    def test_lan_failure_preserves_ledger_without_finalize_or_old_wrapper(self):
        host = Mock()
        host.call.return_value = {"phase": "POST_RELEASE_LAN_VERIFICATION_PENDING"}
        verify = Mock(side_effect=RuntimeError("offline_lan_failure"))
        with self.assertRaisesRegex(RuntimeError, "offline_lan_failure"):
            run.restore_and_finalize(host, "offline-inference", "offline-control", verify=verify)
        self.assertEqual([call.args[0] for call in host.call.call_args_list], ["status", "status"])

    def exercise_failed_load_before_registration(self, *, fail_record=False):
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            task = root / "task"
            credentials = root / "BENCHRUN-20260919/private-credentials"
            credentials.mkdir(mode=0o700, parents=True)
            armed = {"session_id": "prep", "source_commit": "a" * 40, "scope": run.SCOPE,
                     "runtime_policy": run.POLICY, "source_files": {}, "frozen_inputs": {}}
            runner.save(task / "arm.json", armed)
            receipt = {"arm_sha256": fixtures.digest((task / "arm.json").read_bytes())}
            runner.save(task / "arm-receipt.json", receipt)
            runner.save(task / "progress.json", {"phase": "OFFLINE", "completed": {},
                                                  "inflight": {}, "errors": []})
            runner.save(task / "GO.json", {**receipt, "decision": "GO", "vm_writer_handoff": True,
                "run_session_id": "fresh-run", "runtime": {**run.POLICY,
                                                             "start_epoch": 1000, "deadline_epoch": 6400}})
            calls, observed_jobs = [], []
            phase = ["NEW"]
            def call(op, **kwargs):
                calls.append(op)
                if op == "begin":
                    phase[0] = "ACTIVE"
                elif op == "budget":
                    return {"remaining_s": 5400}
                elif op == "load":
                    raise RuntimeError("offline_load_failed_after_owned_mutation")
                elif op == "restore":
                    self.assertEqual(observed_jobs[0].active, {})
                    phase[0] = "POST_RELEASE_LAN_VERIFICATION_PENDING"
                elif op == "verify_restoration":
                    self.assertEqual(kwargs, {"receipt": {"offline_LAN": True}})
                    phase[0] = "RESTORED"
                elif op != "status":
                    self.fail("unexpected host operation " + op)
                return {"phase": phase[0]}
            host = Mock()
            host.call.side_effect = call
            def failed_execute(job):
                observed_jobs.append(job)
                job.host.call("begin")
                job.loaded({"placement": "G1", "configured_capacity": 16384})
            def lan(status, key, control):
                calls.append("LAN")
                self.assertEqual(status["phase"], "POST_RELEASE_LAN_VERIFICATION_PENDING")
                return {"offline_LAN": True}
            canonical = run.restore_and_finalize
            original_record = run.ConcurrentRun.record
            record_failed = []
            def record(job, phase=None):
                if fail_record and phase == "RESTORING_AFTER_FAILURE":
                    record_failed.append(True)
                    raise OSError("offline_report_write_failed")
                return original_record(job, phase)
            real_lstat = Path.lstat
            def lstat(path, *args, **kwargs):
                if path == credentials:
                    return SimpleNamespace(st_uid=502, st_mode=0o40700)
                return real_lstat(path, *args, **kwargs)
            socket = Mock()
            socket.return_value.__enter__ = Mock(return_value=Mock(connect_ex=Mock(return_value=1)))
            socket.return_value.__exit__ = Mock(return_value=False)
            with patch.object(runner, "source_files", return_value={}), \
                 patch.object(run.os, "geteuid", return_value=502), \
                 patch.object(Path, "lstat", lstat), \
                 patch.object(run.time, "time", return_value=1000), \
                 patch("runtime.sglang38_file_auth.read_key", return_value="offline-key"), \
                 patch.object(runner, "run_preflight"), \
                 patch.object(run.glmrepair, "DiagnosticSSHHost", return_value=host), \
                 patch.object(run.ConcurrentRun, "execute", failed_execute), \
                 patch.object(run.ConcurrentRun, "record", record), \
                 patch.object(run, "restore_and_finalize", side_effect=lambda h, k, c: canonical(h, k, c, verify=lan)), \
                 patch.object(run.socket, "socket", socket), \
                 patch.object(run.signal, "signal"):
                self.assertEqual(run.run(task, task / "GO.json", "fresh-run"), 1)
            self.assertEqual(calls, ["begin", "budget", "load", "status", "status", "restore",
                                     "status", "LAN", "verify_restoration", "status"])
            host.close.assert_called_once_with()
            final = json.loads((task / "final-restoration-receipt.json").read_bytes())
            self.assertEqual(final["status"], "PASS")
            self.assertTrue(final["authenticated_worker_LAN"])
            self.assertEqual(observed_jobs[0].active, {})
            self.assertEqual(bool(record_failed), fail_record)

    def test_failed_load_before_client_registration_still_restores_and_lan_finalizes(self):
        self.exercise_failed_load_before_registration()

    def test_reporting_failure_during_measurement_stop_cannot_skip_canonical_restore(self):
        self.exercise_failed_load_before_registration(fail_record=True)


class ConcurrentDecodePairTests(unittest.TestCase):
    def test_supervisor_wait_interrupt_drains_admitted_glm_before_propagating(self):
        entered, release = threading.Event(), threading.Event()
        calls, workers, drained = [], [], []
        main_thread = threading.current_thread()
        original_wait = threading.Event.wait
        def invoke(job, **kwargs):
            calls.append(job["id"])
            workers.append(threading.current_thread())
            entered.set()
            self.assertTrue(release.wait(timeout=2))
            drained.append(job["id"])
            return row(job["id"], status="TIMING_ONLY")
        def wait(event, timeout=None):
            if threading.current_thread() is main_thread and timeout == .05:
                self.assertTrue(original_wait(entered, 2))
                release.set()
                raise KeyboardInterrupt()
            return original_wait(event, timeout)
        try:
            with patch.object(threading.Event, "wait", wait):
                with self.assertRaises(KeyboardInterrupt):
                    run.execute_decode_pair({"id": "g"}, {"id": "q"}, invoke)
            at_propagation = list(drained)
            alive_at_propagation = [worker.is_alive() for worker in workers]
        finally:
            release.set()
            for worker in workers:
                worker.join(timeout=2)
        self.assertEqual(calls, ["g"])
        self.assertEqual(at_propagation, ["g"])
        self.assertFalse(any(alive_at_propagation))

    def test_qwen_starts_on_first_glm_output_and_both_admitted_requests_drain(self):
        q_started = threading.Event()
        actions = []
        def invoke(job, *, first_output=None):
            if job["id"] == "g":
                self.assertIsInstance(first_output, threading.Event)
                actions.append("glm-start")
                self.assertNotIn("qwen-start", actions)
                actions.append("glm-output")
                first_output.set()
                self.assertTrue(q_started.wait(timeout=2))
                actions.append("glm-drained")
            else:
                self.assertIn("glm-output", actions)
                actions.append("qwen-start")
                q_started.set()
                actions.append("qwen-drained")
            return row(job["id"], status="TIMING_ONLY")
        run.execute_decode_pair({"id": "g"}, {"id": "q"}, invoke)
        self.assertEqual(actions[:3], ["glm-start", "glm-output", "qwen-start"])
        self.assertCountEqual(actions[3:], ["glm-drained", "qwen-drained"])

    def test_no_glm_output_never_fabricates_qwen_trigger(self):
        calls = []
        def invoke(job, *, first_output=None):
            calls.append(job["id"])
            return row(job["id"], status="TIMING_ONLY", first_output=None,
                       last_output=None)
        run.execute_decode_pair({"id": "g"}, {"id": "q"}, invoke)
        self.assertEqual(calls, ["g"])

    def test_optional_pair_native_or_transport_failure_is_not_unavailable(self):
        for failure in ("STOP_NATIVE_OR_TRANSPORT", RuntimeError("offline_transport_failure")):
            def invoke(job, **kwargs):
                if isinstance(failure, BaseException):
                    raise failure
                return row(job["id"], status=failure, first_output=None, last_output=None)
            with self.subTest(failure=str(failure)):
                result = run.execute_decode_pair({"id": "g"}, {"id": "q"}, invoke)
                self.assertEqual(result["status"], "FAILED")


class ConcurrentRuntimeTests(unittest.TestCase):
    def test_fresh_dispatch_clock_is_exact_5400_with_7200_request_ceiling(self):
        armed = {"runtime_policy": copy.deepcopy(run.POLICY), "session_id": "prep-session"}
        go = {"run_session_id": "fresh-run", "runtime": {**run.POLICY,
              "start_epoch": 1000.0, "deadline_epoch": 6400.0}}
        original = copy.deepcopy(go)
        self.assertEqual(run.bind_runtime(armed, go, "fresh-run", 1000), go["runtime"])
        self.assertEqual(go, original)
        for changes, session, now in [({"start_epoch": True}, "fresh-run", 1000),
                                     ({"start_epoch": float("nan")}, "fresh-run", 1000),
                                     ({"deadline_epoch": float("inf")}, "fresh-run", 1000),
                                     ({"deadline_epoch": 6401}, "fresh-run", 1000),
                                     ({"request_max_seconds": 7201}, "fresh-run", 1000),
                                     ({"budget_seconds": 7200}, "fresh-run", 1000),
                                     ({}, "prep-session", 1000), ({}, "fresh-run", 999),
                                     ({}, "fresh-run", 6400)]:
            candidate = {**go, "runtime": {**go["runtime"], **changes}}
            with self.subTest(changes=changes, session=session, now=now), self.assertRaises(ValueError):
                run.bind_runtime(armed, candidate, session, now)

    def test_existing_execution_cannot_reset_clock_or_construct_host(self):
        with tempfile.TemporaryDirectory() as directory:
            task = Path(directory)
            armed = {"session_id": "prep", "runtime_policy": run.POLICY,
                     "source_files": {}, "frozen_inputs": {}}
            runner.save(task / "arm.json", armed)
            receipt = {"arm_sha256": fixtures.digest((task / "arm.json").read_bytes())}
            runner.save(task / "arm-receipt.json", receipt)
            runner.save(task / "execution-arm.json", {"existing_execution": True})
            runner.save(task / "GO.json", {**receipt, "decision": "GO", "vm_writer_handoff": True})
            with patch.object(runner, "source_files", return_value={}), \
                 patch.object(run.os, "geteuid", return_value=502), \
                 patch.object(run.glmrepair, "DiagnosticSSHHost") as host:
                with self.assertRaisesRegex(ValueError, "no_rerun_or_clock_reset"):
                    run.run(task, task / "GO.json", "fresh-run")
                host.assert_not_called()


class ConcurrentLoadingTelemetryTests(unittest.TestCase):
    """Real worker load/collect/admission and Linux pressure/request gates; fake I/O."""
    def setup_case(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        state = Path(temp.name)
        runner.save(state / "progress.json", {"phase": "OFFLINE", "completed": {}, "inflight": {}, "errors": []})
        manifest = profiles.concurrent_manifest("G1", 16384)
        gib = 1024**3
        good = {"errors": [], "host": {"available_bytes": 300 * gib},
                "gpus": [{"uuid": manifest["gpu_uuids"][0], "free_bytes": 64 * gib}],
                "cgroups": {"g": {"current_bytes": 401 * gib, "peak_since_cgroup_creation_bytes": 402 * gib,
                    "anon_bytes": 400 * gib, "kernel_bytes": gib, "file_bytes": 0,
                    "file_mapped_bytes": 0, "shmem_bytes": 0, "swap_bytes": 0, "events": {"oom": 0}}}}
        gap = {**copy.deepcopy(good), "errors": ["gpu_TimeoutExpired"], "gpus": []}
        rows = {"current": good, "loading": gap, "ready": good,
                "native": "ALLOCATION_PROOF_ACCEPTED"}
        host = LinuxHost.__new__(LinuxHost)
        host.scope = run.SCOPE
        host.owner = SimpleNamespace(phase="ACTIVE")
        host.load_manifests, host.allocation_proofs, host.requests = {"g": manifest}, {}, {}
        host.budget = Mock(); host.budget.request_timeout.return_value = 17
        host.identity = Mock(return_value=({}, Path("/not-read"), []))
        host.concurrent_limits, host.write_json = Mock(), Mock()
        def telemetry(cid):
            sample = copy.deepcopy(rows["current"])
            sample["concurrent_resource_gate"] = host.concurrent_pressure(sample)
            return sample
        host.telemetry = telemetry
        def call(op, **args):
            if op == "budget": return {"remaining_s": 100}
            if op == "load": return {"id": "g"}
            if op == "telemetry":
                rows["current"] = rows["loading"] if job.active.get("g", {}).get("phase") == "loading" else rows["ready"]
                return host.telemetry(args["id"])
            if op == "readiness":
                if rows["native"] == "ALLOCATION_PROOF_ACCEPTED": host.allocation_proofs["g"] = {"offline": True}
                return {"ready": True, "allocation": {"status": rows["native"]}}
            if op == "quiescent":
                rows["current"] = rows["ready"]
                return {"telemetry": host.telemetry(args["id"])}
            return host.dispatch({"op": op, **args})
        remote = Mock(); remote.call.side_effect = call
        armed = {"scope": run.SCOPE, "session_id": "offline", "source_commit": "a" * 40,
                 "runtime": {"deadline_epoch": 6400}}
        job = run.ConcurrentRun(state, armed, remote, "offline-key")
        job.warm = Mock(side_effect=lambda cid, *_: job.admission(cid, 120))
        return job, host, rows, manifest

    def activate(self, job, rows, manifest, phase="loading"):
        job.active["g"] = {"manifest": manifest, "phase": phase,
            "baseline": copy.deepcopy(rows["ready"]["cgroups"]["g"]), "cancel_event": threading.Event()}

    def test_loading_timeout_then_fresh_ready_proof_allows_actual_admission(self):
        job, host, rows, manifest = self.setup_case()
        self.assertEqual(job.loaded(manifest), "g")
        job.warm.assert_called_once()
        self.assertIn("g", host.requests)
        self.assertEqual(job.safety, {})
        self.assertFalse(job.active["g"]["cancel_event"].is_set())
        saved = [json.loads(line) for line in (job.state / "results.jsonl").read_text().splitlines()]
        gap = next(row["sample"] for row in saved if row["type"] == "telemetry")
        self.assertEqual(gap["errors"], ["gpu_TimeoutExpired"])
        self.assertEqual(gap["gpus"], [])
        self.assertEqual(gap["concurrent_resource_gate"]["status"], "UNAVAILABLE")
        self.assertEqual(gap["concurrent_resource_gate"]["unavailable_reasons"], ["concurrent_gpu_free_unavailable"])
        self.assertEqual(gap["concurrent_resource_gate"]["latched_violations"], {})

    def test_loading_gap_still_requires_fresh_gpu_host_native_and_request_gate(self):
        for missing in ("gpu", "host", "native", "components"):
            with self.subTest(missing=missing):
                job, host, rows, manifest = self.setup_case()
                if missing == "gpu": rows["ready"]["gpus"] = []
                if missing == "host": rows["ready"]["host"]["available_bytes"] = None
                if missing == "native": rows["native"] = "STOP_ALLOCATION_PROOF"
                if missing == "components": rows["ready"]["cgroups"]["g"]["anon_bytes"] = None
                with self.assertRaisesRegex((RuntimeError, ValueError),
                        "SKIP_UNSAFE_PLACEMENT|STOP_ALLOCATION_PROOF|concurrent_current_resource_gate_failed"):
                    job.loaded(manifest)
                self.assertEqual(host.requests, {})
                if missing != "components": job.warm.assert_not_called()

    def test_numeric_oom_swap_and_reserve_stops_remain_latched_after_valid_sample(self):
        for violation in ("cap", "host", "gpu", "oom", "swap"):
            with self.subTest(violation=violation):
                job, host, rows, manifest = self.setup_case()
                self.activate(job, rows, manifest)
                group = rows["loading"]["cgroups"]["g"]
                if violation == "cap": group["current_bytes"] = 513 * 1024**3
                if violation == "host": rows["loading"]["host"]["available_bytes"] = 0
                if violation == "gpu":
                    rows["loading"]["gpus"] = [{"uuid": manifest["gpu_uuids"][0], "free_bytes": 0}]
                if violation == "oom": group["events"]["oom"] = 1
                if violation == "swap": group["swap_bytes"] = 4096
                for _ in range(3 if violation == "swap" else 1): job.collect()
                latched = dict(job.safety)
                self.assertTrue(latched)
                self.assertTrue(job.active["g"]["cancel_event"].is_set())
                job.active["g"]["phase"] = "ready"
                job.collect()
                self.assertTrue(job.safety)
                self.assertTrue(job.active["g"]["cancel_event"].is_set())
                with self.assertRaises(RuntimeError): job.admission("g")
                self.assertEqual(host.requests, {})
                if violation in ("cap", "host", "gpu"):
                    self.assertTrue(host.concurrent_resource_violations)
                    self.assertEqual(job.samples["g"][-1]["concurrent_resource_gate"]["status"], "STOP_RESOURCE_GATE")
                else:
                    self.assertEqual(job.safety, latched)

    def test_running_timeout_remains_blocked_after_complete_sample_without_cancellation(self):
        job, host, rows, manifest = self.setup_case()
        self.activate(job, rows, manifest, phase="ready")
        good = rows["ready"]
        rows["ready"] = rows["loading"]
        job.collect()
        rows["ready"] = good
        job.collect()
        self.assertEqual(job.safety, {"g": "SKIP_UNSAFE_PLACEMENT"})
        self.assertFalse(job.active["g"]["cancel_event"].is_set())
        with self.assertRaisesRegex(RuntimeError, "SKIP_UNSAFE_PLACEMENT"): job.admission("g")
        self.assertEqual(host.requests, {})

    def test_other_loading_gaps_are_not_forgiven(self):
        for missing in ("error", "extra_error", "host", "components"):
            with self.subTest(missing=missing):
                job, host, rows, manifest = self.setup_case()
                self.activate(job, rows, manifest)
                if missing == "error": rows["loading"]["errors"] = ["gpu_ValueError"]
                if missing == "extra_error": rows["loading"]["errors"].append("host_ValueError")
                if missing == "host": rows["loading"]["host"]["available_bytes"] = None
                if missing == "components": rows["loading"]["cgroups"]["g"]["anon_bytes"] = None
                job.collect()
                self.assertEqual(job.safety, {"g": "SKIP_UNSAFE_PLACEMENT"})
                self.assertFalse(job.active["g"]["cancel_event"].is_set())
                with self.assertRaisesRegex(RuntimeError, "SKIP_UNSAFE_PLACEMENT"): job.admission("g")
                self.assertEqual(host.requests, {})


class ConcurrentCallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.state = Path(self.temp.name)
        runner.save(self.state / "progress.json", {"phase": "OFFLINE", "completed": {},
                                                  "inflight": {}, "errors": []})
        self.host = Mock()
        self.host.call.return_value = {"timeout_s": 17}
        self.armed = {"session_id": "offline-run", "source_commit": "a" * 40,
                      "scope": run.SCOPE, "runtime": {"deadline_epoch": 6400},
                      "optional_decode_pair": True}

    def job(self, transport=None):
        job = run.ConcurrentRun(self.state, self.armed, self.host, "offline-key",
                               transport_factory=Mock(return_value=transport))
        job.active["g"] = {"manifest": {"placement": "G1", "configured_capacity": 16384,
                                        "transport": {"port": 31002}, "gpu_uuids": ["offline-gpu0"]},
                           "baseline": {"swap_bytes": 0, "events": {"oom": 0}},
                           "cancel_event": threading.Event(), "phase": "ready"}
        job.telemetry_window = Mock(return_value={"scope": "offline"})
        return job

    def prepared(self, job, identifier="offline"):
        sample = fixtures.build_sample("bench-glm-5.3", 12, "offline-seed-1729", "fresh-offline-001")
        raw = fixtures.serialize_validate(sample)
        return {"cid": "g", "id": identifier, "sample": sample, "raw": raw,
                "count": {"input_tokens": 650, "body_sha256": fixtures.digest(raw)},
                "manifest_sha256": fixtures.digest(fixtures.canonical(job.active["g"]["manifest"])),
                "generation": False, "preparation_seconds": 0}

    def response(self, prepared, *, finish="stop", changes=None, fenced=False):
        counters = {"prompt_tokens": 650, "completion_tokens": 5, "cached_tokens": 0,
                    "evaluated_prompt_tokens": 650, "decode_tokens": 5,
                    "prompt_ms": 100, "decode_ms": 1000000}
        counters.update(changes or {})
        content = fixtures.canonical(prepared["sample"]["scorer"]["retrieval"]).decode()
        if fenced:
            content = "```json\n" + content + "\n```"
        status = "OUTPUT_LIMIT" if finish == "length" else "COMPLETE"
        return {"summary": {**row()["sample"], "status": status, "counters": counters},
                "parsed": {"status": status, "finish_reason": finish,
                           "message": {"role": "assistant", "content": content}}}

    def test_actual_measure_retains_strict_and_semantic_verdict_and_short_output_count(self):
        job = self.job()
        prepared = self.prepared(job)
        job.request = Mock(return_value=self.response(prepared, fenced=True))
        result = job.measure(prepared)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["strict"]["status"], "HARNESS_FAILURE")
        self.assertEqual(result["semantic"]["status"], "PASS")
        self.assertEqual(result["occupied_tokens"], 655)
        self.assertEqual(result["sample"]["counters"]["completion_tokens"], 5)
        self.assertLess(result["native_n_minus_one_decode_tps"], 0.01)
        self.assertIn("no_speed_stop", result["limitations"])
        with self.assertRaisesRegex(RuntimeError, "no_measurement_retry"):
            job.measure(prepared)
        self.assertEqual(job.request.call_count, 1)

    def test_actual_measure_invalid_native_counts_cannot_pass(self):
        for changes in ({"prompt_tokens": 649}, {"cached_tokens": 1},
                        {"evaluated_prompt_tokens": 649}, {"decode_tokens": 4}):
            with self.subTest(changes=changes):
                job = self.job()
                prepared = self.prepared(job, "native-" + next(iter(changes)))
                job.request = Mock(return_value=self.response(prepared, changes=changes))
                result = job.measure(prepared)
                self.assertNotIn(result["status"], run.SUCCESS)
                self.assertFalse(result["native_count_valid"])

    def test_actual_request_first_output_ignores_role_and_ends_admission_once(self):
        first = threading.Event()
        def sse(event):
            return b"data: " + fixtures.canonical(event) + b"\n\n"
        def transport(raw, timeout):
            self.assertEqual(timeout, 17)
            yield sse({"model": "bench-glm-5.3", "choices": [{"index": 0,
                "delta": {"role": "assistant"}, "finish_reason": None}]})
            self.assertFalse(first.is_set())
            yield sse({"model": "bench-glm-5.3", "choices": [{"index": 0,
                "delta": {"content": "offline"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 650, "completion_tokens": 5, "total_tokens": 655},
                "timings": {"cache_n": 0, "prompt_n": 650, "prompt_ms": 100,
                            "predicted_n": 5, "predicted_ms": 250}})
            self.assertTrue(first.is_set())
            yield b"data: [DONE]\n\n"
        job = self.job(transport)
        prepared = self.prepared(job)
        result = job.request("g", prepared["raw"], "first-output", first_output=first)
        self.assertEqual(result["summary"]["status"], "COMPLETE")
        self.assertEqual([call.args[0] for call in self.host.call.call_args_list],
                         ["request_begin", "request_end"])
        kwargs = job.transport_factory.call_args.kwargs
        self.assertIs(kwargs["cancel_event"], job.active["g"]["cancel_event"])
        self.assertEqual(kwargs["deadline_epoch"], 6400)

    def test_proven_oom_cancels_both_lanes_missing_telemetry_does_not(self):
        for oom in (True, False):
            with self.subTest(oom=oom):
                job = self.job()
                job.active["q"] = {"manifest": {"placement": "Q1", "gpu_uuids": ["offline-gpu1"]},
                                   "baseline": {"swap_bytes": 0, "events": {"oom": 0}},
                                   "cancel_event": threading.Event(), "phase": "ready"}
                current_oom = [oom]
                def telemetry(op, **kwargs):
                    self.assertEqual(op, "telemetry")
                    cid = kwargs["id"]
                    return {"host": {"available_bytes": 64 * 1024**3},
                            "gpus": [{"uuid": "offline-gpu" + str(i), "free_bytes": 64 * 1024**3}
                                     for i in range(2)] if oom else [],
                            "cgroups": {cid: {"swap_bytes": 0, "events": {"oom": int(current_oom[0] and cid == "g")}}}}
                self.host.call.side_effect = telemetry
                job.collect()
                self.assertTrue(job.safety)
                self.assertEqual([v["cancel_event"].is_set() for v in job.active.values()], [oom, oom])
                if oom:
                    latched = dict(job.safety)
                    current_oom[0] = False
                    job.collect()
                    self.assertEqual(job.safety, latched)
                    self.assertTrue(all(v["cancel_event"].is_set() for v in job.active.values()))
                    self.assertTrue(all(v["abort_reason"] == "STOP_OOM" for v in job.active.values()))

    def test_retirement_waits_for_collector_and_preserves_last_sample(self):
        job = self.job()
        collecting, release, retire_attempted, retired = (threading.Event() for _ in range(4))
        errors, order = [], []
        underlying = threading.RLock()
        class ObservedLock:
            def __enter__(self):
                if threading.current_thread().name == "offline-retirer":
                    retire_attempted.set()
                underlying.acquire()
                return self
            def __exit__(self, *args):
                underlying.release()
        job.lock = ObservedLock()
        def host_call(op, **kwargs):
            self.assertEqual(kwargs, {"id": "g"})
            if op == "telemetry":
                order.append("collect-start")
                collecting.set()
                self.assertTrue(release.wait(timeout=2))
                self.assertIn("g", job.active)
                order.append("collect-return")
                return {"host": {"available_bytes": 64 * 1024**3},
                        "gpus": [{"uuid": "offline-gpu0", "free_bytes": 64 * 1024**3}],
                        "cgroups": {"g": {"swap_bytes": 0, "events": {"oom": 0}}},
                        "retained_marker": "final-before-retirement"}
            self.assertEqual(op, "retire")
            self.assertEqual(len(job.samples["g"]), 1)
            self.assertEqual(job.samples["g"][0]["retained_marker"], "final-before-retirement")
            order.append("retire")
            retired.set()
            return {}
        self.host.call.side_effect = host_call
        def capture(action):
            try:
                action()
            except BaseException as exc:
                errors.append(exc)
        collector = threading.Thread(target=lambda: capture(job.collect), name="offline-collector")
        retirer = threading.Thread(target=lambda: capture(job.retire_all), name="offline-retirer")
        try:
            collector.start()
            self.assertTrue(collecting.wait(timeout=2))
            retirer.start()
            self.assertTrue(retire_attempted.wait(timeout=2))
            self.assertFalse(retired.is_set())
            self.assertIn("g", job.active)
        finally:
            release.set()
            collector.join(timeout=2)
            if retirer.ident is not None:
                retirer.join(timeout=2)
        self.assertFalse(collector.is_alive())
        self.assertFalse(retirer.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(order, ["collect-start", "collect-return", "retire"])
        self.assertEqual(job.active, {})
        self.assertEqual(len(job.samples["g"]), 1)
        saved = [json.loads(line) for line in (self.state / "results.jsonl").read_text().splitlines()]
        self.assertEqual(saved[0]["sample"]["retained_marker"], "final-before-retirement")

    def test_peer_finished_before_or_during_admission_unregisters_without_dispatch(self):
        for during_admission in (False, True):
            with self.subTest(during_admission=during_admission):
                job = self.job()
                peer_done = threading.Event()
                if not during_admission:
                    peer_done.set()
                prepared = {**self.prepared(job, "not-admitted-" + str(during_admission)),
                            "stop_admission": peer_done}
                self.host.reset_mock()
                def call(op, **kwargs):
                    if op == "request_begin":
                        peer_done.set()
                        return {"timeout_s": 17}
                    self.assertEqual(op, "request_end")
                    return {}
                self.host.call.side_effect = call
                with self.assertRaises(run.PeerFinished):
                    job.measure(prepared)
                self.assertEqual(job.progress["inflight"], {})
                self.assertNotIn(prepared["id"], job.progress["completed"])
                job.transport_factory.assert_not_called()
                self.assertEqual([call.args[0] for call in self.host.call.call_args_list],
                                 ["request_begin", "request_end"] if during_admission else [])

    def test_interruption_blocks_new_requests_without_resource_cancelling_peer(self):
        job = self.job()
        job.interrupted.set()
        with self.assertRaisesRegex(RuntimeError, "ROOT_INTERRUPTED"):
            job.admission("g")
        self.host.call.assert_not_called()
        self.assertFalse(job.active["g"]["cancel_event"].is_set())

    def test_glm_saved_fixture_record_counts_and_schema_survive_fresh_recount(self):
        for capacity, tokens, records in ((16384, 15831, 384), (65536, 65008, 1600)):
            with self.subTest(capacity=capacity):
                job = self.job()
                job.active["g"]["manifest"]["configured_capacity"] = capacity
                job.boundary = Mock()
                saved = fixtures.build_sample("bench-glm-5.3", records, run.g1_ladder.SEED,
                                              "preserved-offline-nonce")
                runner.save(job.private / ("G1-" + str(capacity) + "-saved-fixture.json"), saved)
                calls = []
                def counter(raw):
                    calls.append(raw)
                    body = json.loads(raw)
                    self.assertEqual(body["max_tokens"], 256)
                    self.assertEqual(body["temperature"], 1.0)
                    self.assertEqual(body["seed"], 1729)
                    self.assertEqual(body["response_format"], run.g1_ladder.SCHEMA)
                    return {"input_tokens": tokens, "body_sha256": fixtures.digest(raw),
                            "source": "native_apply_template_tokenize", "configured_context": capacity,
                            "template_sha256": "a" * 64, "token_ids_sha256": "b" * 64}
                job.counter = Mock(return_value=counter)
                prepared = job.prepare_job("g", "preserved-" + str(capacity))
                self.assertEqual(calls, [prepared["raw"]])
                self.assertEqual(prepared["count"]["input_tokens"], tokens)
                for field in ("records", "seed", "fixture_sha256", "scorer"):
                    self.assertEqual(prepared["sample"][field], saved[field])
                self.assertNotEqual(prepared["sample"]["nonce"], saved["nonce"])

    def test_exact_two_rounds_and_same_large_pool_fillers_then_matched_idle_reference(self):
        for observed_overlap, optional_status in ((True, "COMPLETE"), (False, "COMPLETE"), (False, "FAILED")):
            with self.subTest(observed_overlap=observed_overlap, optional_status=optional_status):
                job = self.job()
                job.active.clear()
                job.boundary = Mock()
                events, prepared_jobs, rounds = [], [], []
                def call(op, **kwargs):
                    if op == "begin":
                        events.append("begin")
                        return {}
                    self.assertEqual(op, "admit_concurrent")
                    pair = (16384, 262144) if kwargs["round"] == "short" else (65536, 700160)
                    return {"manifests": [{"placement": p, "configured_capacity": c}
                                          for p, c in zip(("G1", "Q1"), pair)]}
                self.host.call.side_effect = call
                def loaded(manifest):
                    cid = manifest["placement"] + "-" + str(manifest["configured_capacity"])
                    events.append("load-" + cid)
                    job.active[cid] = {"manifest": manifest}
                    return cid
                job.loaded = loaded
                def prepare(cid, identifier, **kwargs):
                    prepared = {"id": identifier, "cid": cid, "sample": {"logical_fixture": identifier},
                                "options": kwargs}
                    prepared_jobs.append(prepared)
                    return prepared
                job.prepare_job = prepare
                def measured(prepared, **kwargs):
                    events.append(prepared["id"])
                    return row(prepared["id"])
                job.measure = measured
                def retire():
                    events.append("retire")
                    job.active.clear()
                job.retire_all = retire
                def execute(g, q, invoke, **kwargs):
                    rounds.append((g, q))
                    events.append("round-" + g["id"])
                    return {"status": "COMPLETE", "overlap": {"pairs": [
                        {"decode_decode_seconds": int(observed_overlap)}]}}
                optional = Mock(return_value={"status": optional_status})
                with patch.object(run, "execute_round", side_effect=execute), \
                     patch.object(run, "execute_decode_pair", optional):
                    if optional_status == "FAILED":
                        with self.assertRaisesRegex(RuntimeError, "STOP_OPTIONAL_DECODE_GATE"):
                            job.sequence()
                    else:
                        job.sequence()
                self.assertEqual(events, ["begin", "load-G1-16384", "load-Q1-262144", "round-short-G1",
                    "retire", "load-G1-65536", "load-Q1-700160", "round-long-G1",
                    "large-Q1-resident-idle-reference"])
                self.assertEqual([len(q) for _, q in rounds], [3, 8])
                short, long = rounds[0][1], rounds[1][1]
                self.assertEqual([p["options"]["target"] for p in short], [262144] * 3)
                self.assertEqual([p["options"]["target"] for p in long], [700160] + [262144] * 7)
                self.assertTrue(all(p["cid"] == "Q1-700160" for p in long))
                self.assertIsNone(long[1]["options"]["matched"])
                self.assertEqual(long[2]["options"]["matched"], long[1]["sample"])
                baseline = next(p for p in prepared_jobs if p["id"] == "large-Q1-resident-idle-reference")
                self.assertEqual(baseline["options"], {"target": 700160, "matched": long[0]["sample"]})
                self.assertEqual(optional.call_count, int(not observed_overlap))
                if not observed_overlap:
                    self.assertEqual([p["id"] for p in prepared_jobs[-2:]], ["decode-G1", "decode-Q1"])
                    self.assertTrue(all(p["options"] == {"generation": True} for p in prepared_jobs[-2:]))
                if optional_status == "FAILED":
                    self.assertNotEqual(job.progress["phase"], "MEASUREMENTS_COMPLETE")
                else:
                    self.assertEqual(job.progress["phase"], "MEASUREMENTS_COMPLETE")


if __name__ == "__main__":
    unittest.main()
