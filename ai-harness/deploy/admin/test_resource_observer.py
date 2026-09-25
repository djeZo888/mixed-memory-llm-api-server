import os
import threading
import time
from types import SimpleNamespace
import unittest
from resource_observer import ProcResources, ResourceCache


class Resources(unittest.TestCase):
    def test_counters_units_null_first_sample_and_no_generation_owner(self):
        now = [1.]
        sources = {"/proc/stat": "cpu 100 0 50 850 0 0 0 0 0 0\ncpu0 1\ncpu1 1\n",
                   "/proc/meminfo": "MemTotal: 1000 kB\nMemAvailable: 500 kB\nSwapTotal: 100 kB\nSwapFree: 75 kB\n",
                   "/proc/pressure/memory": "some avg10=1.50 avg60=1 avg300=1 total=1\nfull avg10=0.10 avg60=0 avg300=0 total=0\n",
                   "/proc/diskstats": "8 1 sda1 1 0 100 0 1 0 200 0 0 0 0\n",
                   "/proc/net/dev": "lo: 999 0 0 0 0 0 0 0 999 0 0 0 0 0 0 0\neth0: 100 0 0 0 0 0 0 0 200 0 0 0 0 0 0 0\n"}
        collector = ProcResources(read=lambda p: sources[p], statvfs=lambda _: SimpleNamespace(f_blocks=100, f_bavail=40, f_frsize=4096),
                                  root_device=lambda: os.makedev(8, 1), monotonic=lambda: now[0])
        first = {component: collector.observe(component) for component in ("cpu", "memory", "disk", "network")}
        self.assertIsNone(first["cpu"]["percent"])
        self.assertEqual(first["cpu"]["logical_count"], 2)
        self.assertEqual(first["memory"]["total_bytes"], 1024000)
        self.assertEqual(first["memory"]["pressure_some_avg10"], 1.5)
        self.assertEqual(first["disk"]["total_bytes"], 409600)
        self.assertIsNone(first["disk"]["read_bytes_per_second"])
        now[0] += 5
        sources["/proc/stat"] = "cpu 150 0 100 950 0 0 0 0 0 0\ncpu0 1\ncpu1 1\n"
        sources["/proc/diskstats"] = "8 1 sda1 1 0 110 0 1 0 220 0 0 0 0\n"
        sources["/proc/net/dev"] = "eth0: 150 0 0 0 0 0 0 0 300 0 0 0 0 0 0 0\n"
        self.assertEqual(collector.observe("cpu")["percent"], 50)
        self.assertEqual(collector.observe("disk")["read_bytes_per_second"], 1024)
        self.assertEqual(collector.observe("network"), {"rx_bytes_per_second": 10, "tx_bytes_per_second": 20})

    def test_hung_resource_has_one_slot_timeout_and_preserves_original_age(self):
        now = [0.]
        entered, release = threading.Event(), threading.Event()
        def observe(component):
            if now[0]:
                entered.set()
                release.wait(2)
            return {"percent": 10, "logical_count": 2}
        cache = ResourceCache(observe, monotonic=lambda: now[0], clock=lambda: 1000 + now[0])
        cache.refresh("cpu")
        now[0] = 5
        thread = threading.Thread(target=cache.refresh, args=("cpu",))
        thread.start()
        self.assertTrue(entered.wait(1))
        now[0] = 16
        self.assertFalse(cache.refresh("cpu"))
        value = cache.snapshot()["cpu"]
        self.assertEqual(value["state"], "timeout")
        self.assertEqual(value["freshness"], "stale")
        self.assertEqual(value["age_ms"], 16000)
        self.assertEqual(value["percent"], 10)
        release.set()
        thread.join(2)


if __name__ == "__main__":
    unittest.main()
