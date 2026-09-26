"""Offline policy and patch execution; no native, CUDA, network or VM contact."""
import ast
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from runtime.adaptive_idle import Activity, AdaptiveIdle
from runtime import adaptive_idle_source_gate as source_gate


IDLE = Activity(0, 0, 0, 0)


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


class AdaptiveIdleTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.policy = AdaptiveIdle(clock=self.clock)
        self.waits = []

    def wait(self):
        self.waits.append(self.clock.now)

    def test_startup_exact_transition_and_status_does_not_renew(self):
        self.clock.now = 599.999
        self.assertFalse(self.policy.maybe_wait(IDLE, self.wait))
        for _ in range(100):
            self.assertEqual(self.policy.snapshot()["last_real_work_monotonic"], 0)
        self.clock.now = 600
        self.assertTrue(self.policy.maybe_wait(IDLE, self.wait))
        self.assertEqual(self.waits, [600])

    def test_last_real_completion_not_start_controls_grace(self):
        self.clock.now = 400
        self.policy.record_real_work()  # Arrival/warmup begins.
        self.clock.now = 1900
        self.assertFalse(self.policy.maybe_wait(Activity(1, 0, 0, 0), self.wait))
        self.clock.now = 1917
        self.policy.record_real_work()  # Final result/stream/async completion.
        self.clock.now = 2516.999
        self.assertFalse(self.policy.maybe_wait(IDLE, self.wait))
        self.clock.now = 2517
        self.assertTrue(self.policy.maybe_wait(IDLE, self.wait))

    def test_all_busy_and_unknown_counters_prevent_blocking(self):
        for field in ("active", "queued", "streaming", "pending_async"):
            for value in (1, None):
                with self.subTest(field=field, value=value):
                    counters = dict(active=0, queued=0, streaming=0, pending_async=0)
                    counters[field] = value
                    self.clock.now += 1000
                    self.assertFalse(self.policy.maybe_wait(Activity(**counters), self.wait))
        self.assertEqual(self.waits, [])

    def test_unknown_never_renews_grace_but_still_cannot_sleep(self):
        self.clock.now = 800
        self.assertFalse(self.policy.maybe_wait(Activity(), self.wait))
        self.assertEqual(self.policy.snapshot()["last_real_work_monotonic"], 0)
        self.assertTrue(self.policy.maybe_wait(IDLE, self.wait))

    def test_each_gpu_grace_is_independent(self):
        peer = AdaptiveIdle(clock=self.clock)
        self.clock.now = 550
        peer.record_real_work()
        self.clock.now = 600
        self.assertTrue(self.policy.maybe_wait(IDLE, self.wait))
        self.assertFalse(peer.maybe_wait(IDLE, self.wait))

    def test_management_or_spurious_wake_is_not_real_work(self):
        self.clock.now = 900
        self.assertTrue(self.policy.maybe_wait(IDLE, self.wait))
        self.assertTrue(self.policy.maybe_wait(IDLE, self.wait))
        self.assertEqual(self.policy.snapshot()["last_real_work_monotonic"], 0)

    def test_event_blocks_then_wakes_and_real_work_renews(self):
        entered, request, completed = threading.Event(), threading.Event(), threading.Event()
        self.clock.now = 600

        def level_wait():
            entered.set()
            request.wait()

        def worker():
            self.policy.maybe_wait(IDLE, level_wait)
            self.policy.record_real_work()
            completed.set()

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        try:
            self.assertTrue(entered.wait(1))
            self.assertFalse(completed.is_set())
            self.clock.now = 601
            request.set()
            self.assertTrue(completed.wait(1))
        finally:
            request.set()
            thread.join(1)
        self.clock.now = 1200.999
        self.assertFalse(self.policy.maybe_wait(IDLE, self.wait))
        self.clock.now = 1201
        self.assertTrue(self.policy.maybe_wait(IDLE, self.wait))

    def test_request_between_check_and_wait_is_not_lost(self):
        request = threading.Event()
        self.clock.now = 600

        def race_wait():
            request.set()  # Arrives immediately after the policy idle check.
            self.assertTrue(request.wait(0))

        self.assertTrue(self.policy.maybe_wait(IDLE, race_wait))

    def test_invalid_or_regressed_clock_and_counters_rejected(self):
        for value in (-1, True, 0.0, "0"):
            with self.assertRaisesRegex(ValueError, "invalid_activity_counter"):
                Activity(active=value)
        self.clock.now = float("nan")
        with self.assertRaisesRegex(ValueError, "invalid_monotonic_clock"):
            self.policy.maybe_wait(IDLE, self.wait)
        self.clock.now = -1
        with self.assertRaisesRegex(ValueError, "monotonic_clock_regressed"):
            self.policy.maybe_wait(IDLE, self.wait)


class CandidatePatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture = ROOT / "tests/fixtures/adaptive_idle/idle_sleeper.pinned.py"
        cls.before = fixture.read_text()
        with tempfile.TemporaryDirectory() as directory:
            native = Path(directory) / "python/sglang/srt/managers/scheduler_components/idle_sleeper.py"
            native.parent.mkdir(parents=True)
            native.write_text(cls.before)
            subprocess.run(["git", "apply", str(ROOT / "scripts/runtime/patches/sglang38-adaptive-idle-candidate.patch")],
                           cwd=directory, check=True, capture_output=True)
            cls.after = native.read_text()

    def test_fixture_matches_retained_normalized_hash_not_raw_byte_claim(self):
        manifest = json.loads(source_gate.MANIFEST.read_text())
        key = "python/sglang/srt/managers/scheduler_components/idle_sleeper.py"
        self.assertEqual(hashlib.sha256(self.before.strip().encode()).hexdigest(),
                         manifest["historical_normalized_evidence"]["text"]["files"][key])
        self.assertFalse(manifest["historical_normalized_evidence"]["raw_byte_pins_available"])
        self.assertFalse(manifest["native_integration_accepted"])

    def test_candidate_preserves_cache_and_uses_indefinite_event_wait(self):
        clock, polls = Clock(), []
        tensors = {"weights": object(), "kv_cache": object(), "allocator_cache": object()}
        original = dict(tensors)

        class Poller:
            def register(self, socket, event):
                self.registered = (socket, event)

            def poll(self, *args, **kwargs):
                polls.append((args, kwargs))

        class Platform:
            def empty_cache(self):
                tensors.clear()
                raise AssertionError("candidate must preserve cache")

        namespace = {"AdaptiveIdle": lambda: AdaptiveIdle(clock=clock),
                     "zmq": SimpleNamespace(Poller=Poller, POLLIN=1),
                     "current_platform": Platform(),
                     "envs": SimpleNamespace(SGLANG_EMPTY_CACHE_INTERVAL=SimpleNamespace(get=lambda: 1))}
        tree = ast.parse(self.after)
        idle_class = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "IdleSleeper")
        exec(compile(ast.Module(body=[idle_class], type_ignores=[]), "candidate_idle_sleeper.py", "exec"), namespace)
        sleeper_class = namespace["IdleSleeper"]
        with self.assertRaises(TypeError):
            sleeper_class([object()])  # Cannot be activated with the old caller.
        sleeper = sleeper_class([object()], activity_provider=lambda: IDLE)
        clock.now = 599
        self.assertFalse(sleeper.maybe_sleep())
        clock.now = 600
        self.assertTrue(sleeper.maybe_sleep())
        self.assertEqual(polls, [((), {})])  # No periodic 1000ms timeout.
        self.assertEqual(tensors, original)
        self.assertTrue(all(tensors[key] is original[key] for key in tensors))
        sleeper.record_real_work()
        clock.now = 1199
        self.assertFalse(sleeper.maybe_sleep())

    def test_unsupported_rust_path_is_unchanged(self):
        marker = "class RustServerIdleSleeper:"
        self.assertEqual(self.before.split(marker)[1], self.after.split(marker)[1])

    def test_source_gate_rejects_missing_or_changed_source_without_acceptance(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(ValueError, "pinned_native_source_missing"):
                source_gate.verify(root, "text")
            # Synthetic complete source set checks gate behavior only, not
            # availability/authenticity of the missing native schedulers.
            files = {"python/scheduler.py": "scheduler fixture\n"}
            manifest = {"text": {"upstream_revision": "synthetic", "files": {}}}
            for relative, content in files.items():
                path = root / relative
                path.parent.mkdir(parents=True)
                path.write_text(content)
                manifest["text"]["files"][relative] = hashlib.sha256(content.encode()).hexdigest()
            manifest_path = root / "manifest.json"
            manifest_path.write_text(json.dumps(manifest))
            with patch.object(source_gate, "MANIFEST", manifest_path):
                checked = source_gate.verify(root, "text")
                self.assertFalse(checked["native_integration_accepted"])
                self.assertEqual(checked["source_identity"], "matched_official_upstream_raw_bytes")
                (root / "python/scheduler.py").write_text("changed")
                with self.assertRaisesRegex(ValueError, "pinned_native_source_hash_mismatch"):
                    source_gate.verify(root, "text")


if __name__ == "__main__":
    unittest.main()
