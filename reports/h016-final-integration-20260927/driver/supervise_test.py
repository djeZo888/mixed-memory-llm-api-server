"""Offline clock arithmetic only: no sleep, subprocess, inference or host contact."""
import unittest
from supervise import remaining, work_budget, ADMIT, SETTLE, CLEANUP_SECONDS
class Bounds(unittest.TestCase):
    def test_preflight_delay_counts_in_total(self):
        self.assertEqual(work_budget(ADMIT-600,10,ADMIT-600,10),1200)
        self.assertEqual(work_budget(ADMIT-600,10,ADMIT-480,130),1080)
        self.assertEqual(120+1080+CLEANUP_SECONDS,1380)
    def test_late_entry_and_delayed_admission(self):
        with self.assertRaises(ValueError):work_budget(ADMIT+0.001,0,ADMIT+0.001,0)
        with self.assertRaises(ValueError):work_budget(ADMIT-60,0,ADMIT+1,61)
        self.assertEqual(work_budget(ADMIT,0,ADMIT,0),1200)
    def test_monotonic_total_and_absolute_settlement(self):
        self.assertEqual(remaining(ADMIT,0,ADMIT+1380,1380),0)
        self.assertEqual(remaining(ADMIT,0,SETTLE,10),0)
        self.assertEqual(remaining(ADMIT,0,ADMIT-100,1380),0)
        self.assertEqual(remaining(ADMIT,0,ADMIT+1300,1300),80)
    def test_systemd_joint_bound(self):
        from pathlib import Path
        text=(Path(__file__).parent.parent/'launch-app-acceptance.sh').read_text()
        self.assertIn('RuntimeMaxSec=1470',text);self.assertIn('TimeoutStopSec=30',text)
        self.assertEqual(1470+30,SETTLE-ADMIT)
if __name__=='__main__':unittest.main()
