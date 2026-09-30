"""Crash-safe Ada status writes on real temporary files and a real local lease.

Only registration/mount discovery is synthetic; no service or network calls.
"""
import contextlib
import copy
import io as text_io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
sys.path.insert(0,str(ROOT/'scripts/h028'))
import ada_supervisor as supervisor
from common import lifecycle_lease as lease
from install import storage_io as storage

ACQUIRE = lease.acquire_lease
ANCHOR = storage.AnchoredRoot


class AtomicStatusTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='.ada-status-test-', dir=ROOT)
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        (self.base/'run').mkdir(mode=0o700)
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.status = self.base/'status.json'
        self.legacy = self.base/'status.new'
        self.status.write_bytes(b'{"boot_id":"old","ready":true}\n')
        self.status.chmod(0o600)
        self.legacy.write_bytes(b'{"boot_id":"old","partial":')
        self.legacy.chmod(0o600)
        self.original = self.status.read_bytes()
        self.old_temporary = self.legacy.read_bytes()
        self.stack.enter_context(patch.object(supervisor.owner, 'BASE', str(self.base)))
        self.stack.enter_context(patch.object(supervisor.owner, 'storage', return_value=SimpleNamespace(root_payload_guard=Mock())))
        self.stack.enter_context(patch.object(lease, 'acquire_lease', side_effect=self.acquire))
        info = self.base.stat()
        identity = {'path':str(self.base), 'mount':str(self.base), 'uuid':'fixture', 'fstype':'fixture',
                    'device':f'{os.major(info.st_dev)}:{os.minor(info.st_dev)}'}
        snapshot = {'schema_version':1,'data':identity,'models':identity,
                    'roots':{'state':str(self.base),'models':str(self.base)}}
        class Guard:
            def __enter__(self): return self
            def __exit__(self,*args): pass
            def __call__(self): return copy.deepcopy(snapshot)
            def check_path(self, _): return self()
        self.stack.enter_context(patch.object(storage, 'MountedStorageGuard', side_effect=lambda _:Guard()))
        self.stack.enter_context(patch.object(storage, 'AnchoredRoot', side_effect=lambda path,guard:ANCHOR(path,guard,uid=os.geteuid())))

    def acquire(self, **kwargs):
        return ACQUIRE(**kwargs, system_root=self.base, trusted_uid=os.geteuid())

    def test_stale_fixed_temporary_preserved_and_new_status_atomically_replaces(self):
        inode = self.status.stat().st_ino
        with patch.object(storage.os, 'fsync', wraps=os.fsync) as sync:
            self.assertTrue(supervisor.write(self.status,{'boot_id':'new','ready':False}))
        self.assertGreaterEqual(sync.call_count,3)
        self.assertEqual(json.loads(self.status.read_bytes()), {'boot_id':'new','ready':False})
        self.assertNotEqual(self.status.stat().st_ino,inode)
        self.assertEqual(self.status.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.legacy.read_bytes(),self.old_temporary)
        self.assertFalse(list(self.base.glob('.installer-*')))
        self.assertTrue(supervisor.write(self.base/'terminal.json',{'reason':'fixture retained failure'}))

    def test_active_canonical_writer_defers_without_clobber_or_native_cleanup(self):
        journal = text_io.StringIO()
        with self.acquire(blocking=False), contextlib.redirect_stderr(journal), patch.object(supervisor.owner,'operate') as operate:
            self.assertFalse(supervisor.write(self.status,{'boot_id':'new'}))
            with self.assertRaises(lease.LeaseBusy):
                supervisor.write(self.base/'terminal.json',{'reason':'cleanup:LeaseBusy:lifecycle_busy'})
            operate.assert_not_called()
        self.assertEqual(self.status.read_bytes(),self.original)
        self.assertEqual(self.legacy.read_bytes(),self.old_temporary)
        self.assertFalse((self.base/'terminal.json').exists())
        rows = [json.loads(row) for row in journal.getvalue().splitlines()]
        self.assertEqual([row['file'] for row in rows],['status.json','terminal.json'])
        self.assertTrue(all(row['event']=='ada_status_write_deferred' for row in rows))
        self.assertTrue(supervisor.write(self.status,{'boot_id':'new'}))

    def test_old_temporary_active_writer_keeps_its_inode_and_bytes(self):
        with self.legacy.open('ab') as writer:
            inode=os.fstat(writer.fileno()).st_ino
            self.assertTrue(supervisor.write(self.status,{'boot_id':'new'}))
            writer.write(b'"unfinished"}');writer.flush()
            self.assertEqual(self.legacy.stat().st_ino,inode)
        self.assertEqual(self.legacy.read_bytes(),self.old_temporary+b'"unfinished"}')

    def test_destination_symlink_refused_and_legacy_symlink_never_followed(self):
        target=self.base/'unrelated';target.write_bytes(b'preserve target');target.chmod(0o600)
        self.status.unlink();self.status.symlink_to(target)
        with self.assertRaises(storage.StorageIOError):supervisor.write(self.status,{'boot_id':'new'})
        self.assertTrue(self.status.is_symlink())
        self.assertEqual(target.read_bytes(),b'preserve target')
        self.status.unlink();self.legacy.unlink();self.legacy.symlink_to(target)
        self.assertTrue(supervisor.write(self.status,{'boot_id':'new'}))
        self.assertTrue(self.legacy.is_symlink())
        self.assertEqual(target.read_bytes(),b'preserve target')

    def test_partial_write_and_promotion_failure_preserve_previous_complete_status(self):
        actual_write = os.write
        calls=[]
        def fail_after_prefix(fd,data):
            calls.append(1)
            if len(calls)==1:return actual_write(fd,data[:5])
            raise OSError('fixture disk write interrupted')
        with patch.object(storage.os,'write',side_effect=fail_after_prefix):
            with self.assertRaisesRegex(OSError,'fixture disk write interrupted'):
                supervisor.write(self.status,{'boot_id':'new','ready':False})
        self.assertEqual(self.status.read_bytes(),self.original)
        self.assertEqual(self.legacy.read_bytes(),self.old_temporary)
        with patch.object(ANCHOR,'replace',side_effect=InterruptedError('fixture promotion interrupted')):
            with self.assertRaises(InterruptedError):supervisor.write(self.status,{'boot_id':'new'})
        self.assertEqual(self.status.read_bytes(),self.original)
        self.assertTrue(supervisor.write(self.status,{'boot_id':'new'}))

    def test_short_writes_complete_before_promotion(self):
        actual_write=os.write
        with patch.object(storage.os,'write',side_effect=lambda fd,data:actual_write(fd,data[:3])):
            self.assertTrue(supervisor.write(self.status,{'boot_id':'new','ready':False}))
        self.assertEqual(json.loads(self.status.read_bytes()),{'boot_id':'new','ready':False})

    def test_invalid_status_path_cannot_touch_unrelated_files(self):
        for path in (self.base/'state.json', self.base/'source/status.json', self.base/'../status.json'):
            with self.subTest(path=path), self.assertRaisesRegex(ValueError,'ada_status_path_invalid'):
                supervisor.write(path,{'boot_id':'new'})
        self.assertEqual(self.status.read_bytes(),self.original)

    @contextlib.contextmanager
    def normal_stop(self, operate=None):
        config={'source_sha256':{'ada_launcher.py':'fixture'},'model_metadata_sha256':{}}
        config['profile_qualification']={'status':'PASS','profile':supervisor.immutable_profile(config)}
        (self.base/'config.json').write_text(json.dumps(config))
        (self.base/'state.json').write_text(json.dumps({'owner':supervisor.owner.OWNER,'container':{'id':'fixture'}}))
        (self.base/'log').mkdir()
        read_text=Path.read_text
        def read(path,*args,**kwargs):
            if str(path)=='/proc/sys/kernel/random/boot_id':return 'fixture-boot'
            if str(path)=='/data/services/secrets/llm-api-key':return 'fixture-key'
            return read_text(path,*args,**kwargs)
        with patch.object(supervisor,'stopping',True), patch.object(supervisor.signal,'signal'), \
             patch.object(supervisor.owner,'LOG',str(self.base/'log')), \
             patch.object(supervisor.owner,'operate',side_effect=operate), patch.object(Path,'read_text',read):
            yield

    def test_unsaved_terminal_makes_normal_supervisor_stop_fail(self):
        journal=text_io.StringIO()
        with self.normal_stop(), self.acquire(blocking=False), contextlib.redirect_stderr(journal):
            with self.assertRaises(lease.LeaseBusy):supervisor.main()
        self.assertFalse((self.base/'terminal.json').exists())
        self.assertIn('ada_terminal_write_failed',journal.getvalue())

    def test_cleanup_busy_makes_normal_stop_fail_with_durable_reason(self):
        def operate(action):
            if action=='stop':raise lease.LeaseBusy()
        with self.normal_stop(operate):
            with self.assertRaises(lease.LeaseBusy):supervisor.main()
        terminal=json.loads((self.base/'terminal.json').read_bytes())
        self.assertIn('cleanup:LeaseBusy:lifecycle_busy',terminal['reason'])

    def test_primary_error_survives_cleanup_and_terminal_failures(self):
        original=ValueError('fixture original failure')
        def operate(action):
            if action=='start':raise original
            raise lease.LeaseBusy()
        journal=text_io.StringIO()
        with self.normal_stop(operate), patch.object(supervisor,'write',side_effect=OSError('fixture terminal failure')), contextlib.redirect_stderr(journal):
            with self.assertRaises(ValueError) as caught:supervisor.main()
        self.assertIs(caught.exception,original)
        self.assertIn('fixture original failure',journal.getvalue())
        self.assertIn('cleanup:LeaseBusy:lifecycle_busy',journal.getvalue())
        self.assertIn('fixture terminal failure',journal.getvalue())


if __name__ == '__main__':unittest.main()
