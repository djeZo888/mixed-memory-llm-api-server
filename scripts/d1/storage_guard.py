#!/usr/bin/env python3
"""Strict task storage checks, supplementing unchanged repository common guards."""
import argparse
import json
import os
from pathlib import Path
import shutil
import sys
import subprocess

DATA_UUID = '8daf56f1-5649-4163-9d87-919c2d271875'
MIN_ROOT = 4 * 1024**3

def mount(path, expected):
    if not expected:
        raise RuntimeError('expected UUID is required')
    rows = json.loads(subprocess.check_output(
        ['findmnt', '--json', '-M', str(path), '-o', 'TARGET,SOURCE,UUID,FSTYPE,OPTIONS'], text=True))['filesystems']
    if len(rows) != 1:
        raise RuntimeError('ambiguous mount')
    row = rows[0]
    if row['target'] != str(path) or row.get('uuid') != expected or row.get('fstype') != 'ext4' or 'rw' not in row['options'].split(','):
        raise RuntimeError('mount target/UUID/type/writeability mismatch: ' + str(path))
    if Path(path).is_symlink() or Path(path).resolve() != Path(path):
        raise RuntimeError('symlinked mount path')
    return row

def check(model_uuid=None):
    data = mount('/data', DATA_UUID)
    root_dev, data_dev = os.stat('/').st_dev, os.stat('/data').st_dev
    if data_dev == root_dev:
        raise RuntimeError('/data shares root device')
    if shutil.disk_usage('/').free < MIN_ROOT:
        raise RuntimeError('root free bytes below 4 GiB')
    result = {'data': data, 'root_free_bytes': shutil.disk_usage('/').free}
    if model_uuid is not None:
        if model_uuid == DATA_UUID:
            raise RuntimeError('model UUID must differ from data UUID')
        model = mount('/data/models-large', model_uuid)
        if os.stat('/data/models-large').st_dev in (root_dev, data_dev):
            raise RuntimeError('model storage is not a distinct filesystem')
        result['models_large'] = model
    return result

def common(report):
    if report.is_symlink() or not report.parent.is_dir() or report.parent.resolve() != report.parent or os.stat(report.parent).st_dev != os.stat('/data').st_dev:
        raise RuntimeError('unsafe guard report path')
    repo = Path(__file__).resolve().parents[2]
    subprocess.run([str(repo / 'scripts/common/require-data-mounted.sh')], check=True, stdout=sys.stderr)
    subprocess.run([str(repo / 'scripts/common/root-disk-guard.sh'), '--report', str(report)], check=True, stdout=sys.stderr)

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--model-uuid')
    p.add_argument('--report', type=Path)
    args = p.parse_args()
    result = check(args.model_uuid)
    if args.report:
        # Report destination must resolve onto existing /data, never root or another mount.
        if not args.report.is_absolute() or not args.report.parent.is_dir() or os.stat(args.report.parent).st_dev != os.stat('/data').st_dev:
            p.error('report parent must exist on /data')
        common(args.report)
    print(json.dumps(result, indent=2))
