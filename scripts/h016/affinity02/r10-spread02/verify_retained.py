#!/usr/bin/env python3
"""H016: verify only retained shard 12, promote, and inventory all GGUF headers."""
import argparse
import collections
import datetime
import hashlib
import importlib.util
import json
import os
import pathlib
import signal
import time

P = pathlib.Path
RUN = '/data/build/h014-pro-7ac59a6-20260927'
LOG = '/data/logs/H016-20260927/worker1-r10-spread02'
SESSION = '01a0e27e-32c5-7530-ac90-390e985795a2'
DEPENDENCY_SHA = '03c0933c194c79a6aca5e98e26bd1682f99927c0f9dbfe53f25d9938caf3724c'
MANIFEST_SHA = '6ac4242ac5d4df5b083b133062c78b792f1fdc7716d32c0e0000122e3263744b'


def dependency():
    source = P(RUN, 'prep.py')
    if hashlib.sha256(source.read_bytes()).hexdigest() != DEPENDENCY_SHA:
        raise RuntimeError('frozen_guard_adapter_changed')
    spec = importlib.util.spec_from_file_location('h014', source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.setup()
    return module


def identity(st):
    return {k: getattr(st, 'st_' + k) for k in ('dev', 'ino', 'size', 'mtime_ns', 'ctime_ns')}


def main():
    h = dependency()
    started = h.now()
    state = dict(status='VERIFYING_RETAINED_SHARD12', started_utc=started,
                 session=SESSION, pid=os.getpid(), ppid=os.getppid(),
                 source_sha256=hashlib.sha256(P(__file__).read_bytes()).hexdigest(),
                 deadline_utc=(datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=1200)).isoformat(),
                 model_loaded=False)

    def save(name='VERIFICATION-STATUS.json'):
        with h.transaction() as guard, h.AnchoredRoot(LOG, guard) as log:
            log.atomic_json(name, state)

    def stop(*_):
        raise TimeoutError('verification_deadline')

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGALRM, stop)
    signal.alarm(1200)
    try:
        h.require(P('/proc/sys/kernel/random/boot_id').read_text().strip() == h.BOOT, 'boot_changed')
        props = dict(x.split('=', 1) for x in h.output(['systemctl', 'show', 'h014-pro-download-20260927.service', '-p', 'MainPID,ControlPID,ActiveState']).splitlines())
        h.require(props['MainPID'] == props['ControlPID'] == '0' and props['ActiveState'] in ['inactive', 'failed'], 'prior_job_running')
        h.require(not P('/sys/fs/cgroup/system.slice/h014-pro-download-20260927.service').exists(), 'prior_cgroup_present')
        with h.transaction() as guard, h.AnchoredRoot(RUN, guard) as run, h.AnchoredRoot(h.LOG, guard) as old, h.AnchoredRoot(h.MODEL, guard) as model:
            run.check('SELECTED-ARTIFACT.json')
            manifest_bytes = P(RUN, 'SELECTED-ARTIFACT.json').read_bytes()
            h.require(hashlib.sha256(manifest_bytes).hexdigest() == MANIFEST_SHA, 'manifest_changed')
            manifest = h.manifest()
            old.check('download-STATUS.json')
            old_bytes = P(h.LOG, 'download-STATUS.json').read_bytes()
            previous = json.loads(old_bytes)
            state['historical_status_sha256'] = hashlib.sha256(old_bytes).hexdigest()
            state['manifest_sha256'] = MANIFEST_SHA
            cutoff = datetime.datetime.fromisoformat(previous['finished_utc']).timestamp()
            reused = []
            for i, f in enumerate(manifest['files']):
                if i == 11:
                    continue
                name = f['rfilename']
                old.check('hash-' + str(i) + '.txt')
                digest = P(h.LOG, 'hash-' + str(i) + '.txt').read_text().split()[0]
                row = previous['files'][name]
                st = model.stat(name)
                h.require(digest == row['sha256'] == f['lfs']['sha256'] and row['sha256_verified'] and row['status'] == 'VERIFIED', 'prior_receipt_mismatch')
                h.require(st.st_size == f['size'] and st.st_mtime <= cutoff and st.st_ctime <= cutoff, 'prior_file_changed')
                h.require(model.stat(name + '.partial', missing_ok=True) is None, 'unexpected_prior_partial')
                reused.append(dict(file=name, sha256=digest, stat=identity(st), provenance='H014 verified receipt; unchanged protected file stats'))
            f = manifest['files'][11]
            name, partial = f['rfilename'], f['rfilename'] + '.partial'
            h.require(model.stat(name, missing_ok=True) is None, 'final_already_exists_inspect_receipt_first')
            before = identity(model.stat(partial))
            h.require(before['size'] == 49382011904 == f['size'], 'partial_size_mismatch')
            h.require(f['lfs']['sha256'] == 'b48324c51d29df0a68a0c7f3a0fe9cbd10ded3a0fa109dc6cad5e42a59c1b9d3', 'shard12_pin_mismatch')
            state.update(reused_files=reused, retained_before=before, bytes_hashed=0)
        save()
        # Anchors remain live while hashing; no lifecycle lock across the long read.
        with h.MountedStorageGuard(h.s) as guard, h.AnchoredRoot(h.MODEL, guard) as model, model.open(partial) as stream:
            digest = hashlib.sha256()
            last = time.monotonic()
            fd = stream.fileno()
            while True:
                data = os.read(fd, 8 * 1024 * 1024)
                if not data:
                    break
                digest.update(data)
                state['bytes_hashed'] += len(data)
                if time.monotonic() - last >= 15:
                    stream.check()
                    state['updated_utc'] = h.now()
                    save()
                    last = time.monotonic()
            h.require(identity(stream.stat()) == before, 'shard_changed_during_hash')
            state['actual_sha256'] = digest.hexdigest()
            h.require(digest.hexdigest() == f['lfs']['sha256'], 'retained_shard_hash_mismatch')
            with h.transaction() as _guard:
                h.require(identity(model.stat(partial)) == before, 'shard_changed_before_promotion')
                h.require(model.stat(name, missing_ok=True) is None, 'destination_appeared')
                model.replace(partial, name)  # File fsync + atomic rename + directory fsync.
            state['promoted_stat'] = identity(model.stat(name))
        state.update(status='VERIFIED_COMPLETE', verified_shards=13, verified_bytes=577669438240, promoted_utc=h.now())
        save('VERIFICATION.json')
        from inspect_gguf import inspect
        with h.transaction() as guard, h.AnchoredRoot(h.MODEL, guard) as model, h.AnchoredRoot(LOG, guard) as log:
            inventory = []
            for f in manifest['files']:
                with model.open(f['rfilename']) as stream:
                    inventory.append(inspect('/proc/self/fd/' + str(stream.fileno())))
                    inventory[-1]['file'] = f['rfilename']
            counts = collections.Counter()
            for item in inventory:
                counts.update(item['tensor_type_ids'])
            h.require(dict(counts) == {39: 207, 30: 163, 0: 357}, 'actual_tensor_inventory_mismatch')
            log.atomic_json('GGUF-INVENTORY.json', dict(utc=h.now(), tensor_type_ids=dict(counts), tensors=sum(counts.values()), files=inventory))
            state['actual_tensor_types'] = {'MXFP4': counts[39], 'BF16': counts[30], 'F32': counts[0]}
        state.update(status='VERIFIED_AND_INVENTORIED', finished_utc=h.now(), exit_code=0)
    except BaseException as exc:
        state.update(status='STOPPED_INSPECT_BEFORE_RETRY', error_type=type(exc).__name__, error=str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__, finished_utc=h.now(), exit_code=1)
    finally:
        signal.alarm(0)
        save()
    return state['exit_code']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    raise SystemExit(main())
