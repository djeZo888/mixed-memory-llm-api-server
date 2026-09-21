"""Synthetic/offline actual trial/client boundaries; no host or inference I/O."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import test_benchmark_runner as runner_tests
from benchmark import client, profiles


class RequestWindows(unittest.TestCase):
    def test_fitting_and_reporting_peaks_excluded_from_each_actual_request(self):
        for kind in ("retrieval", "tool"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as directory:
                path = Path(directory)
                campaign, host, requests = runner_tests.IntegratedRunner().setup_case(path, [profiles.command_manifest("Q2", 16384)])
                host.call("begin")
                cid = campaign.loaded(campaign.armed["manifests"][0])
                now = [100.0]
                def clock():
                    now[0] += .01
                    return now[0]
                campaign.clock = clock
                campaign.samples[cid] = []
                def sample(memory, faults):
                    campaign.samples[cid].append({"timestamp_monotonic_s": now[0], "collection_duration_s": .001,
                        "cgroups": {cid: {"current_bytes": memory, "pgfault": faults}},
                        "vmstat": {"pgfault": faults}})
                native = campaign.json_factory
                def counted(*args, **kwargs):
                    call = native(*args, **kwargs)
                    def counting(*args):
                        now[0] += 1;sample(9000, 100000)
                        return call(*args)
                    return counting
                campaign.json_factory = counted
                transport = campaign.transport_factory
                def measured(*args):
                    send = transport(*args)
                    def chunks(*args):
                        for index, chunk in enumerate(send(*args)):
                            now[0] += 1;sample((index + 1) * 100, 200000 + index * 10)
                            yield chunk
                    return chunks
                campaign.transport_factory = measured
                parse = client.parse_response
                def reporting(*args):
                    now[0] += 10;sample(20000, 300000)
                    return parse(*args)
                with patch.object(client, "parse_response", side_effect=reporting):
                    result = campaign.trial(cid, "window-" + kind, kind)
                self.assertEqual(result["status"], "PASS")
                fit = result["fixture_preparation_telemetry"]
                self.assertEqual(fit["scope"], "fixture_fitting_counting")
                self.assertEqual(fit["metrics"][f"cgroups.{cid}.current_bytes"]["sampled_peak"], 9000)
                pairs = [("sample", "telemetry")]
                if kind == "tool":
                    pairs.append(("continuation", "continuation_telemetry"))
                    self.assertLess(result["sample"]["request_ended_monotonic_s"],
                                    result["continuation"]["request_started_monotonic_s"])
                for response, metric in pairs:
                    observed, summary = result[metric], result[response]
                    self.assertEqual(observed["sample_count"], 4)
                    self.assertEqual(observed["metrics"][f"cgroups.{cid}.current_bytes"]["sampled_peak"], 400)
                    self.assertEqual(observed["metrics"]["vmstat.pgfault"]["observed_counter_delta"], 30)
                    self.assertEqual(observed["metrics"][f"cgroups.{cid}.pgfault"]["observed_counter_delta"], 30)
                    self.assertEqual(observed["started_monotonic_s"], summary["request_started_monotonic_s"])
                    self.assertEqual(observed["ended_monotonic_s"], summary["request_ended_monotonic_s"])
                    self.assertLess(summary["client_elapsed_seconds"], 5)
                    self.assertGreater(observed["coverage_fraction_estimate"], .8)
                self.assertGreater(result["client_total_seconds"], 10)
                persisted = [json.loads(line) for line in (path / "samples.jsonl").read_text().splitlines()]
                self.assertEqual(len(persisted), len(pairs))
                self.assertEqual(persisted[0]["request_started_monotonic_s"], result["sample"]["request_started_monotonic_s"])
                self.assertIn("window-" + kind, json.loads((path / "progress.json").read_text())["completed"])

    def test_failed_fitting_does_not_invent_a_request_interval(self):
        with tempfile.TemporaryDirectory() as directory:
            campaign, host, requests = runner_tests.IntegratedRunner().setup_case(Path(directory), [profiles.command_manifest("Q2", 4096)])
            host.call("begin");cid = campaign.loaded(campaign.armed["manifests"][0])
            before = len(requests)
            with patch.object(campaign, "prepare_trial", side_effect=ValueError("synthetic fitting failure")):
                result = campaign.trial(cid, "unrequested")
            self.assertEqual(result["status"], "HARNESS_FAILURE")
            self.assertNotIn("telemetry", result)
            self.assertNotIn("sample", result)
            self.assertEqual(len(requests), before)


if __name__ == "__main__":
    unittest.main()
