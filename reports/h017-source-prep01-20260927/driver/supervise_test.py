"""Offline clock/source fixtures; no host or inference."""
import unittest
import datetime
from pathlib import Path
from supervise import remaining,work_budget,ADMIT,SETTLE,HARD_SETTLE,CLEANUP_SECONDS,MIN_WORK_SECONDS
class Bounds(unittest.TestCase):
 def test_preflight_charged_and_dynamic_late_start(self):
  entry=ADMIT-150
  self.assertEqual(work_budget(entry,0,entry,0),870)
  self.assertEqual(work_budget(entry,0,entry+150,150),720)
  with self.assertRaises(ValueError):work_budget(entry,0,entry+151,151)
  self.assertEqual(150+720+CLEANUP_SECONDS,SETTLE-entry)
 def test_no_static_full_envelope_cutoff(self):
  entry=ADMIT-510 #20:26; still admits a full work budget
  self.assertEqual(work_budget(entry,0,entry,0),1200)
  self.assertEqual(work_budget(ADMIT,0,ADMIT,0),720)
  with self.assertRaises(ValueError):work_budget(ADMIT,0,ADMIT+0.001,0.001)
 def test_monotonic_absolute_and_cleanup(self):
  entry=ADMIT-600
  self.assertEqual(remaining(entry,0,entry-100,1380),0)
  self.assertEqual(remaining(entry,0,SETTLE,10),0)
  self.assertEqual(work_budget(entry,0,entry+480,480),720)
  for elapsed in (0,120,480):
   w=work_budget(entry,0,entry+elapsed,elapsed)
   self.assertLessEqual(w,1200)
   self.assertLessEqual(entry+elapsed+w+CLEANUP_SECONDS,SETTLE)
 def test_extended_absolute_instants(self):
  stamp=lambda n:datetime.datetime.fromtimestamp(n,datetime.timezone.utc).isoformat()
  self.assertEqual(stamp(ADMIT),"2026-09-27T20:34:30+00:00")
  self.assertEqual(stamp(SETTLE),"2026-09-27T20:49:30+00:00")
  self.assertEqual(stamp(HARD_SETTLE),"2026-09-27T20:50:00+00:00")
 def test_fixed_stop_and_no_replay(self):
  text=(Path(__file__).parent.parent/'launch-app-acceptance.sh').read_text()
  self.assertIn('min(1470,math.floor((stop-now).total_seconds()))',text)
  self.assertIn('TimeoutStopSec=30',text)
  self.assertIn("--on-calendar='2026-09-27 20:49:30 UTC'",text)
  self.assertNotIn('now<=latest',text)
  self.assertEqual(HARD_SETTLE-SETTLE,30)
  self.assertIn('os.O_EXCL',text);self.assertIn('Restart=no',text)
  self.assertLess(text.index('${H017_REVIEW:?'),text.index('systemd-run --user'))
  live=(Path(__file__).parent/'live.mjs').read_text()
  self.assertIn('MIN_WORK_SECONDS*1000',live)
  self.assertIn("status='SETTLEMENT_UNKNOWN'",live)
  self.assertIn('!existsSync(RUNROOT)',live)
if __name__=='__main__':unittest.main()
