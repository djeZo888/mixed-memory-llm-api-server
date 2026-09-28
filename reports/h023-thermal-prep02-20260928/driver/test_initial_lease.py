import contextlib,types,unittest
from unittest.mock import patch
from native import initial_lease
from contract import Refusal
class Busy(Exception):pass
class InitialLease(unittest.TestCase):
 def run_case(self,failures,drift=False):
  now=[0.];attempts=[0];stats=[0]
  @contextlib.contextmanager
  def acquire(**_):
   attempts[0]+=1
   if attempts[0]<=failures:raise Busy('fixture')
   yield 'exact-native-lease'
  def stat(*args,**kw):
   stats[0]+=1;return types.SimpleNamespace(st_dev=26,st_ino=1829+(1 if drift and stats[0]>1 else 0))
  with patch('native.os.stat',stat),patch('native.Path.read_text',return_value='current-boot'),patch('native.time.monotonic',side_effect=lambda:now[0]),patch('native.time.sleep',side_effect=lambda seconds:now.__setitem__(0,now[0]+seconds)):
   if drift:
    with self.assertRaises(Refusal):
     with initial_lease(acquire,Busy,'current-boot'):self.fail('drift admitted')
   elif failures>100:
    with self.assertRaises(Busy):
     with initial_lease(acquire,Busy,'current-boot'):self.fail('busy admitted')
    self.assertLessEqual(now[0],10.00001)
   else:
    with initial_lease(acquire,Busy,'current-boot') as lease:self.assertEqual(lease,'exact-native-lease')
    self.assertEqual(attempts[0],failures+1)
 def test_transient_busy_bounded(self):self.run_case(2)
 def test_sustained_busy_stops_at_ten_seconds(self):self.run_case(999)
 def test_inode_change_refuses(self):self.run_case(0,True)
