"""Focused periodic persistence: no live I/O, scans or lifecycle lease."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import types
import unittest
from unittest.mock import Mock

def module(path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m

ROOT = Path(__file__).resolve().parents[2]
o = module(ROOT / 'scripts/runtime/mimo/owner.py')
s = module(ROOT / 'scripts/h019/short.py')

class PersistenceTests(unittest.TestCase):
    def harness(self, corrupt=False, path_error=False):
        storage = types.SimpleNamespace(root_payload_guard=Mock())
        g = Mock(); a = Mock(); values = {}
        if path_error: g.check_path.side_effect = RuntimeError('mount_changed')
        a.atomic_json.side_effect = lambda n,v: values.update({n:v})
        a.open.side_effect = lambda n: io.BytesIO(json.dumps({} if corrupt else values[n]).encode())
        h = types.SimpleNamespace(s=storage, MountedStorageGuard=lambda _: contextlib.nullcontext(g),
            AnchoredRoot=lambda *_: contextlib.nullcontext(a), acquire_lease=Mock(side_effect=AssertionError('no lease')))
        return h, g, a

    def test_guard_zero_scans_and_integrity(self):
        h,g,a = self.harness(); o.write(h,'guard.json',{'status':'ok'})
        h.s.root_payload_guard.assert_not_called(); h.acquire_lease.assert_not_called()
        g.check_path.assert_called_once_with(str(o.BASE / 'guard.json'))
        a.check.assert_called_once(); a.open.assert_called_once_with('guard.json')

    def test_other_write_boundaries_keep_two_scans(self):
        for name in ('state.json','selection.json','other.json'):
            h,_,_ = self.harness(); o.write(h,name,{'x':1})
            self.assertEqual(h.s.root_payload_guard.call_count,2)

    def test_short_zero_scans_and_integrity(self):
        h,g,a = self.harness(); s.write_guard_progress(h,{'status':'ok'})
        h.s.root_payload_guard.assert_not_called(); h.acquire_lease.assert_not_called()
        a.check.assert_called_once(); g.check_path.assert_called_once()

    def test_corrupt_readback_refuses_both_periodic_paths(self):
        for fn in (lambda h:o.write(h,'guard.json',{'x':1}),lambda h:s.write_guard_progress(h,{'x':1})):
            h,_,_ = self.harness(corrupt=True)
            with self.assertRaisesRegex(RuntimeError,'write_integrity'): fn(h)

    def test_changed_mount_refuses_before_write(self):
        for fn in (lambda h:o.write(h,'guard.json',{'x':1}),lambda h:s.write_guard_progress(h,{'x':1})):
            h,_,a = self.harness(path_error=True)
            with self.assertRaisesRegex(RuntimeError,'mount_changed'): fn(h)
            a.atomic_json.assert_not_called()

if __name__ == '__main__': unittest.main()
