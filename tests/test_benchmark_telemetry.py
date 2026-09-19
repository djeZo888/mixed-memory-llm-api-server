"""Synthetic/offline telemetry evidence; no GPU, remote or production contacts."""
import importlib.util
import tempfile
import unittest
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "scripts/benchmark/telemetry.py"
spec = importlib.util.spec_from_file_location("benchmark_telemetry", SOURCE)
t = importlib.util.module_from_spec(spec)
spec.loader.exec_module(t)


class TelemetryTests(unittest.TestCase):
    def test_host_zero_unavailable_and_units(self):
        got = t.parse_meminfo("MemTotal: 8192 kB\nMemAvailable: 100 kB\nSwapTotal: 0 kB\nSwapFree: 0 kB\n")
        self.assertEqual(got["available_bytes"], 102400)
        self.assertEqual(got["swap_used_bytes"], 0)
        missing = t.parse_meminfo("MemTotal: bad kB\nMemAvailable: 10 bytes\n")
        self.assertIsNone(missing["available_bytes"])
        self.assertIsNone(missing["swap_used_bytes"])
        self.assertIsNone(t.parse_meminfo("SwapTotal: 1 kB\nSwapFree: 2 kB")["swap_used_bytes"])
        self.assertEqual(t.parse_vmstat("pgfault 100\npgmajfault 0\npswpout 2")["pgmajfault"], 0)
        self.assertIsNone(t.parse_vmstat("")["pgfault"])

    def test_cgroup_semantics_and_unavailable_peak(self):
        got = t.parse_cgroup({"memory.stat": "anon 1000\nfile 2000\nshmem 500\npgfault 20\npgmajfault 0\n",
                              "memory.current": "4096", "memory.swap.current": "0",
                              "memory.events": "oom 0\noom_kill 0\n"})
        self.assertEqual(got["anon_bytes"], 1000)
        self.assertEqual(got["file_bytes"], 2000)
        self.assertEqual(got["swap_bytes"], 0)
        self.assertIsNone(got["rss_bytes"])
        self.assertIsNone(got["peak_since_cgroup_creation_bytes"])
        self.assertEqual(got["events"]["oom"], 0)
        self.assertIsNone(got["events"]["max"])

    def test_gpu_per_uuid_and_unavailable_not_zero(self):
        rows = t.parse_gpu_csv("GPU-A, 98304, 16384, 81920, 0, 55.25\nGPU-B, 98304, N/A, 1000, [Not Supported], N/A\n")
        self.assertEqual(rows[0]["used_bytes"], 16384 * 1024 ** 2)
        self.assertEqual(rows[0]["utilization_percent"], 0)
        self.assertEqual(rows[0]["power_watts"], 55.25)
        self.assertIsNone(rows[1]["used_bytes"])
        self.assertIsNone(rows[1]["power_watts"])
        with self.assertRaises(ValueError):
            t.parse_gpu_csv("GPU-A, 1, 2, 3, 4, 5\nGPU-A, 1, 2, 3, 4, 5")
        with self.assertRaises(ValueError):
            t.parse_gpu_csv("unknown response")

    def test_collector_synthetic_files_no_pss_read(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "meminfo").write_text("MemAvailable: 20 kB\n")
            (root / "vmstat").write_text("pgfault 1\n")
            cg = root / "cg"
            cg.mkdir()
            (cg / "memory.current").write_text("42")
            (root / "123").mkdir()
            (root / "123/status").write_text("VmRSS: 12 kB\nVmSwap: 0 kB\n")
            # No smaps files exist, and no error is generated for them.
            ticks = iter([100.0, 100.1])
            row = t.collect_sample({"qwen": cg}, pids={"qwen": [123]}, proc_root=root,
                                   gpu_reader=lambda: "GPU-X, 100, 20, 80, 5, 10", clock=lambda: next(ticks))
            self.assertEqual(row["host"]["available_bytes"], 20 * 1024)
            self.assertEqual(row["processes"]["qwen"]["rss_bytes"], 12 * 1024)
            self.assertEqual(row["processes"]["qwen"]["swap_bytes"], 0)
            self.assertEqual(len(row["errors"]), 4)  # exactly missing cgroup files
            self.assertIsNone(row["pss_bytes"])
            self.assertAlmostEqual(row["collection_duration_s"], 0.1)
            self.assertEqual(row["cgroups"]["qwen"]["current_bytes"], 42)

    def test_coverage_and_sampled_peaks_include_missing(self):
        rows = [{"timestamp_monotonic_s": timestamp, "collection_duration_s": 0.1,
                 "host": {"available_bytes": value}, "gpus": []}
                for timestamp, value in [(1, 0), (2, None), (5, 100)]]
        summary = t.summarize_samples(rows, 0, 6)
        self.assertEqual(summary["coverage_fraction_estimate"], 0.5)
        self.assertEqual(summary["maximum_sample_gap_s"], 3)
        self.assertEqual(summary["leading_gap_s"], 1)
        self.assertEqual(summary["trailing_gap_s"], 1)
        metric = summary["metrics"]["host.available_bytes"]
        self.assertEqual(metric["available_samples"], 2)
        self.assertEqual(metric["first"], 0)
        self.assertEqual(metric["sampled_peak"], 100)
        self.assertEqual(metric["sampled_minimum"], 0)
        self.assertAlmostEqual(summary["collection_overhead_fraction"], 0.05)
        empty = t.summarize_samples([], 0, 6)
        self.assertEqual(empty["coverage_fraction_estimate"], 0)
        self.assertIsNone(empty["maximum_sample_gap_s"])

    def test_fault_deltas_and_counter_reset_are_explicit(self):
        rows = [{"timestamp_monotonic_s": 1, "vmstat": {"pgfault": 100, "pswpout": 5}},
                {"timestamp_monotonic_s": 2, "vmstat": {"pgfault": 110, "pswpout": 2}}]
        summary = t.summarize_samples(rows, 0, 3)
        self.assertEqual(summary["metrics"]["vmstat.pgfault"]["observed_counter_delta"], 10)
        self.assertIsNone(summary["metrics"]["vmstat.pswpout"]["observed_counter_delta"])
        self.assertTrue(summary["metrics"]["vmstat.pswpout"]["counter_reset_or_insufficient_samples"])

    def test_report_error_does_not_signal_request_or_abort_sampler(self):
        class FakeStop:
            rounds = 0
            def is_set(self):
                return self.rounds >= 3
            def wait(self, seconds):
                self.rounds += 1
        stop = FakeStop()
        calls = []
        def broken_report(row):
            calls.append(row)
            raise ValueError("synthetic parser failure")
        counts = t.sample_series(stop, broken_report, lambda: {"sample": True}, clock=lambda: 0)
        self.assertEqual(counts, {"collected": 3, "collection_errors": 0, "emit_errors": 3})
        self.assertEqual(len(calls), 3)

    def test_model_swap_not_preexisting_host_swap(self):
        self.assertEqual(t.model_swap_state(32768, [32768, 32768, 32768]), "NO_SUSTAINED_GROWTH_OBSERVED")
        self.assertEqual(t.model_swap_state(32768, [65536, 65536, 65536]), "STOP_SUSTAINED_MODEL_SWAP_GROWTH")
        self.assertEqual(t.model_swap_state(32768, [65536, None, 65536]), "UNAVAILABLE")
        self.assertEqual(t.model_swap_state(None, [0, 0, 0]), "UNAVAILABLE")
        self.assertEqual(t.model_swap_state(0, [1, 0, 1]), "NO_SUSTAINED_GROWTH_OBSERVED")
        self.assertEqual(t.model_swap_state(0, [1, 1]), "UNAVAILABLE")
        self.assertEqual(t.model_swap_state(0, [1, 1, 1, None, 0]), "STOP_SUSTAINED_MODEL_SWAP_GROWTH")
        self.assertEqual(t.model_swap_state(32768, [0, 0, 0]), "NO_SUSTAINED_GROWTH_OBSERVED")
        self.assertEqual(t.model_swap_state(0, [1, "bad", 1]), "UNAVAILABLE")
        self.assertEqual(t.model_swap_state(0, [True, True, True]), "UNAVAILABLE")


if __name__ == "__main__":
    unittest.main()
