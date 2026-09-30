#!/usr/bin/env python3
"""Guarded H019 package staging from a root-approved exact tar digest on stdin."""
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import sys
import tarfile

OWNER = Path('/data/services/mimo-h016-20260927/source/owner.py')
OLD_OWNER = '218c890f1f3d8f7f80998aaf5cf7463c32febf5e454713f40da76a9ed60027d0'

def main():
    for p in (OWNER, *OWNER.parents):
        st = p.lstat()
        assert st.st_uid == 0 and not st.st_mode & 0o022 and not stat.S_ISLNK(st.st_mode)
    assert hashlib.sha256(OWNER.read_bytes()).hexdigest() == OLD_OWNER
    spec = importlib.util.spec_from_file_location('h019_stage_old_owner', OWNER)
    o = importlib.util.module_from_spec(spec); spec.loader.exec_module(o); h = o.setup()
    raw = sys.stdin.buffer.read(4 * 1024 * 1024 + 1)
    assert len(raw) <= 4 * 1024 * 1024 and hashlib.sha256(raw).hexdigest() == sys.argv[1]
    with tarfile.open(fileobj=io.BytesIO(raw)) as t:
        members = t.getmembers(); assert len(members) <= 32
        assert len({m.name for m in members}) == len(members)
        for m in members:
            assert m.isfile() and not m.name.startswith('/') and '..' not in Path(m.name).parts
            assert m.name.startswith('scripts/') or m.name == 'QUIET.json'
        with h.MountedStorageGuard(h.s) as g, h.AnchoredRoot('/data/build', g) as a:
            h.s.root_payload_guard()
            assert not Path('/data/build/H019-20260928/package').exists()
            a.mkdir('H019-20260928/package')
            for m in members:
                target = 'H019-20260928/package/' + m.name
                a.mkdir(str(Path(target).parent))
                content = t.extractfile(m).read()
                with a.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600) as f:
                    f.write(content); f.fsync()
                assert hashlib.sha256(o.protected('/data/build/' + target)).hexdigest() == hashlib.sha256(content).hexdigest()
            a.check(); h.s.root_payload_guard()
    print(json.dumps({'status':'EXACT_PACKAGE_STAGED','archive_sha256':sys.argv[1]}))

if __name__ == '__main__': main()
