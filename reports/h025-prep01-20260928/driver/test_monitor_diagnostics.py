"""Bounded monitor receipts retain static fault reasons without exception text."""
import errno
from pathlib import Path
import sys
import types
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'scripts'))
from install.storage_io import StorageIOError
from runner import Runner,monitor_error

class MonitorDiagnostics(unittest.TestCase):
    def test_known_storage_code_and_errno_are_retained(self):
        self.assertEqual(monitor_error(StorageIOError('invalid_storage_file_or_hardlink'),'sample'),
                         'StorageIOError:code=invalid_storage_file_or_hardlink:errno=None:stage=sample')
        self.assertEqual(monitor_error(OSError(errno.EIO,'SECRET-PAYLOAD','/secret/path'),'sample'),
                         'OSError:code=unclassified:errno=5:stage=sample')
    def test_arbitrary_exception_text_code_and_metadata_are_not_emitted(self):
        error=StorageIOError('SECRET'*10000);error.errno='SECRET'
        result=monitor_error(error,'SECRET')
        self.assertEqual(result,'StorageIOError:code=unclassified:errno=None:stage=monitor')
        self.assertNotIn('SECRET',monitor_error(type('SECRET',(Exception,),{})('SECRET'),'sample'))
    def test_monitor_failure_receipt_keeps_code_and_dispatches_stops(self):
        reasons=[];dispatched=[]
        phase=types.SimpleNamespace(clock=lambda:{'monotonic':1},settlement_deadline=1,fail=reasons.append,observe=lambda row:None)
        def sample(due):raise StorageIOError('registered_storage_mount_changed')
        runner=Runner(phase,types.SimpleNamespace(sample=sample))
        runner.dispatch_stops=lambda:dispatched.append(True)
        runner.monitor()
        self.assertEqual(reasons,['monitor_or_owner_read_failed:StorageIOError:code=registered_storage_mount_changed:errno=None:stage=sample'])
        self.assertEqual(dispatched,[True])
    def test_monitor_tick_stage_is_retained(self):
        reasons=[]
        def tick():raise TimeoutError(errno.ETIMEDOUT,'SECRET')
        phase=types.SimpleNamespace(clock=lambda:{'monotonic':1},settlement_deadline=1,
                                    fail=reasons.append,observe=lambda row:None,monitoring_tick=tick)
        runner=Runner(phase,types.SimpleNamespace(sample=lambda due:{}))
        runner.dispatch_stops=lambda:None
        runner.monitor()
        self.assertIn('errno='+str(errno.ETIMEDOUT)+':stage=monitoring_tick',reasons[0])
        self.assertNotIn('SECRET',reasons[0])

if __name__=='__main__':unittest.main()
