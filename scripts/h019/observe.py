#!/usr/bin/env python3
"""Read-only 45-second canonical holder/proof observation; no lock acquisition."""
import datetime
import json
import os
from pathlib import Path
import time

LOCK = Path('/run/llmctl/lifecycle.lock')
PROOF = Path('/data/services/llm-manager/hardware-latch.json')

def observe(seconds=45):
    info = LOCK.stat()
    identity = (info.st_dev, info.st_ino)
    device = f'{os.major(info.st_dev):02x}:{os.minor(info.st_dev):02x}:{info.st_ino}'
    start = time.monotonic()
    samples, proofs, captures = [], [], {}
    last_proof = -1
    while time.monotonic() - start < seconds:
        elapsed = time.monotonic() - start
        current = LOCK.stat()
        if (current.st_dev, current.st_ino) != identity:
            raise RuntimeError('canonical_lock_changed')
        holders = []
        for line in Path('/proc/locks').read_text().splitlines():
            fields = line.split()
            if device not in fields:
                continue
            pos = fields.index(device)
            pid = fields[pos - 1]
            holders.append({'pid': pid, 'record': line})
            if pid not in captures and pid.isdecimal():
                root = Path('/proc') / pid
                try:
                    fds = []
                    for fd in (root / 'fd').iterdir():
                        try:
                            st = fd.stat()
                            if (st.st_dev, st.st_ino) == identity:
                                fds.append({'fd': fd.name, 'target': os.readlink(fd),
                                            'fdinfo': (root / 'fdinfo' / fd.name).read_text()})
                        except FileNotFoundError:
                            pass
                    captures[pid] = {'comm': (root / 'comm').read_text().strip(),
                                     'cgroup': (root / 'cgroup').read_text(), 'lock_fds': fds}
                except FileNotFoundError:
                    captures[pid] = {'exited_before_capture': True}
        samples.append({'elapsed_s': elapsed, 'holders': holders})
        if int(elapsed) != last_proof:
            last_proof = int(elapsed)
            raw = json.loads(PROOF.read_text())
            now = time.time()
            proofs.append({'elapsed_s': elapsed, 'proofs': {gpu: {
                'age_ms': (now - datetime.datetime.fromisoformat(v['observed_at'].replace('Z', '+00:00')).timestamp()) * 1000,
                'boot_id': v.get('boot_id'), 'observed_at': v['observed_at'],
                'hardware_latched': raw.get('targets', {}).get(gpu, {}).get('hardware_latched')}
                for gpu, v in raw.get('validated', {}).items()}})
        time.sleep(.1)
    intervals = []
    beginning = None
    for sample in samples + [{'elapsed_s': time.monotonic() - start, 'holders': []}]:
        if sample['holders'] and beginning is None:
            beginning = sample['elapsed_s']
        if not sample['holders'] and beginning is not None:
            intervals.append(sample['elapsed_s'] - beginning)
            beginning = None
    return {'utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'scope': 'read-only sampled observation; 100ms resolution, shorter holds may be missed; edge intervals censored',
            'canonical_lock': str(LOCK), 'identity': identity, 'seconds': seconds,
            'maximum_observed_continuous_busy_s': max(intervals, default=0),
            'maximum_proof_age_ms': max((v['age_ms'] for s in proofs for v in s['proofs'].values()), default=None),
            'holder_capture': captures, 'lock_samples': samples, 'proof_samples': proofs}

if __name__ == '__main__':
    print(json.dumps(observe(), sort_keys=True))
