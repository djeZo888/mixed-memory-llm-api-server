#!/usr/bin/env python3
"""Offline safety tests. Run on ai-vm: PYTHONDONTWRITEBYTECODE=1 python3 scripts/d1/test_helpers.py."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace
import acquire
import storage_guard as sg

class Tests(unittest.TestCase):
    def setUp(self):
        self.manifest = json.loads((Path(__file__).resolve().parents[2] / 'reports/r2-flagship-artifact.json').read_text())

    def test_manifest_and_metadata(self):
        a = acquire.validate_manifest(self.manifest)
        rows = [{'path': x['path'], 'size': x['size_bytes'], 'type': 'file', 'lfs': {'oid': x['sha256'], 'size': x['size_bytes']}} for x in a]
        acquire.compare_metadata(a, rows)
        for field, value in [('revision', 'main'), ('total_bytes', 0), ('artifact_count', 10)]:
            m = copy.deepcopy(self.manifest); m[field] = value
            with self.assertRaises(acquire.IntegrityError): acquire.validate_manifest(m)
        for bad in [rows[:-1], rows + [rows[0]]]:
            with self.assertRaises(acquire.IntegrityError): acquire.compare_metadata(a, bad)
        for field in ['size', 'path']:
            bad = copy.deepcopy(rows); bad[0][field] = 0
            with self.assertRaises(acquire.IntegrityError): acquire.compare_metadata(a, bad)
        bad = copy.deepcopy(rows); bad[0]['lfs']['oid'] = '0'*64
        with self.assertRaises(acquire.IntegrityError): acquire.compare_metadata(a, bad)

    def test_range_resume(self):
        acquire.validate_response(SimpleNamespace(status=206, headers={'Content-Range': 'bytes 5-9/10', 'Content-Length': '5'}), 5, 10)
        acquire.validate_response(SimpleNamespace(status=200, headers={'Content-Length': '10'}), 0, 10)
        for status, cr, length in [(200,'bytes 5-9/10','5'), (206,'bytes 0-4/10','5'), (206,'bytes 5-9/11','5'), (206,'bytes 5-9/10','10')]:
            with self.assertRaises(acquire.IntegrityError):
                acquire.validate_response(SimpleNamespace(status=status, headers={'Content-Range': cr,'Content-Length': length}), 5, 10)

    def test_symlink_and_hash(self):
        with tempfile.TemporaryDirectory(dir='/data/build/d1-glm53-20260915/tmp') as d:
            p=Path(d)/'file'; p.write_bytes(b'abc')
            self.assertEqual(acquire.digest(p), 'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad')
            link=Path(d)/'link'; link.symlink_to(p)
            with self.assertRaises(acquire.IntegrityError): acquire.no_symlinks(link)

    def test_exact_mount(self):
        good={'target':'/data','source':'/dev/example','uuid':sg.DATA_UUID,'fstype':'ext4','options':'rw,relatime'}
        for key, val in [('target','/'), ('uuid',None), ('uuid','wrong'), ('fstype','tmpfs'), ('options','ro')]:
            row=dict(good); row[key]=val
            with patch.object(sg.subprocess,'check_output',return_value=json.dumps({'filesystems':[row]})):
                with self.assertRaises(RuntimeError): sg.mount('/data', sg.DATA_UUID)

    def test_low_root_and_shared_device(self):
        with patch.object(sg,'mount',return_value={}), patch.object(sg.os,'stat',side_effect=[SimpleNamespace(st_dev=1),SimpleNamespace(st_dev=2)]), patch.object(sg.shutil,'disk_usage',return_value=SimpleNamespace(free=4*1024**3-1)):
            with self.assertRaisesRegex(RuntimeError,'below 4 GiB'): sg.check()
        with patch.object(sg,'mount',return_value={}), patch.object(sg.os,'stat',return_value=SimpleNamespace(st_dev=1)):
            with self.assertRaisesRegex(RuntimeError,'shares root'): sg.check()

if __name__=='__main__': unittest.main()
