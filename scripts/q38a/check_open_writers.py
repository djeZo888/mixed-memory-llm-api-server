"""Read-only Q38A check: ssh ai-vm 'sudo -n python3 -' < this file.

Run before/after seal. Read only /proc descriptor/maps metadata for the exact81
payload inodes. Emit counts, no unrelated process names, paths or environments.
"""
import datetime
import json
import os
from pathlib import Path
import stat

root = Path('/data/models-large/qwen38-27b-fp8')
manifest = json.loads(Path('/data/services/q38a-20260915/repo/reports/q38s-acquisition-manifest.json').read_text())
assert len(manifest['artifacts']) == 81
targets = {}
for row in manifest['artifacts']:
    value = (root / row['path']).lstat()
    assert stat.S_ISREG(value.st_mode) and value.st_nlink == 1 and value.st_size == row['size_bytes']
    targets[(value.st_dev, value.st_ino)] = row['path']
assert len(targets) == 81
map_targets = {(os.major(dev), os.minor(dev), inode) for dev, inode in targets}
writers = []
mappings = []
unreadable = 0
processes = 0
for process in Path('/proc').iterdir():
    if not process.name.isdigit():
        continue
    processes += 1
    try:
        descriptors = list((process / 'fd').iterdir())
    except (FileNotFoundError, ProcessLookupError):
        continue
    except PermissionError:
        unreadable += 1
        continue
    for descriptor in descriptors:
        try:
            value = descriptor.stat()
            if (value.st_dev, value.st_ino) not in targets:
                continue
            info = (process / 'fdinfo' / descriptor.name).read_text()
            flags = int(next(line.split()[1] for line in info.splitlines() if line.startswith('flags:')), 8)
            if flags & os.O_ACCMODE in (os.O_WRONLY, os.O_RDWR):
                writers.append({'pid': int(process.name), 'fd': descriptor.name,
                                'artifact': targets[(value.st_dev, value.st_ino)]})
        except (FileNotFoundError, ProcessLookupError):
            continue
        except PermissionError:
            unreadable += 1
    try:
        with (process / 'maps').open() as stream:
            for line in stream:
                fields = line.split(maxsplit=5)
                if len(fields) < 5 or 'w' not in fields[1] or not fields[1].endswith('s'):
                    continue
                major, minor = (int(part, 16) for part in fields[3].split(':'))
                if (major, minor, int(fields[4])) in map_targets:
                    mappings.append({'pid': int(process.name), 'inode': int(fields[4])})
    except (FileNotFoundError, ProcessLookupError):
        continue
    except PermissionError:
        unreadable += 1
result = {'utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
          'artifact_count': 81, 'processes_observed': processes,
          'writable_descriptors': writers, 'shared_writable_mappings': mappings,
          'unreadable_entries': unreadable,
          'status': 'PASS' if not writers and not mappings and not unreadable else 'STOP'}
print(json.dumps(result, indent=2))
raise SystemExit(0 if result['status'] == 'PASS' else 1)
