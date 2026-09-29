#!/usr/bin/env python3
"""Exact ACTIVATE01 post-install continuation. Never repeats native cleanup.

No argv/env path controls. Reviewed once-only invocation; every refusal is final.
The original helper, plan, failure and archive remain immutable evidence.
"""
import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import time
import types

BASE = Path('/data/services/image21-runtime-20260923')
PREFIX = 'h032-image-reconcile/'
PINS = {
    'state.json': '6b1141fcdbf50bbaed75e66cf16391d5719933a8e472c0a58de03e67725fa646',
    'operation.json': '7d1082f053530cc3261c9247f40e36f186af0063f29f19c345a42a698965f884',
    'recovery.json': '0f110098f3fed42bf6554a3ab8742871ccf2c634948827f37252bcfaab47b808',
    'config.json': 'a3ca37b0deb2dcc2af5421dde3b5e204dc850ab7034665e576724eca5b1a632a',
    'source/service.py': '6b7ac0a1ff946b3b7be62caf24926b33adad566f595abd5398e7db3486b88fa6',
    PREFIX + 'helper.py': '069a6eb7c49b39b29be013c50d7c9ed245400cf41da8a1ce80e4b519a89a53df',
    PREFIX + 'plan.json': 'd4d9a0ce01f6c7cc6ca7a950fa10232d20eadaa448f7bdfb4599c8720921d31e',
    PREFIX + 'archive-manifest.json': '3b62733dde73a552ce4574728b21db082a58bed2e027a3b80a8449b8d86c6d4c',
    PREFIX + 'consumed.json': '172aaaf597daa953ad5ce4139ee18fc37329edfde2b6d8fae7260483fce934ca',
    PREFIX + 'settlement.json': '49b43a55cf83539dc19137a4d22b39219d2ebb997b46695123a1c04321d0843c',
}
FAILURE = '32a3ea39cefa48a598ca64c2ef2e6427'
FAILURE_SHA = 'fbc81a593b2400f48d1306c7801fbed87b07f59e9d51e1dbd990dff074c8a571'
UID, GID = 0, 1001
END = 1790684400  # This task's hard admission/closure cutoff: 12:20 UTC.


def need(ok, code):
    if not ok:
        raise RuntimeError(code)


def sha(value):
    return hashlib.sha256(value).hexdigest()


def original_helper():
    # Bootstrap only the exact retained helper; validate protected lineage and
    # held descriptor before executing its verified buffer.
    path = BASE / PREFIX / 'helper.py'
    lineage = [(p, p.lstat()) for p in (path, *path.parents)]
    for _, info in lineage:
        need(info.st_uid == 0 and not info.st_mode & 0o022
             and not stat.S_ISLNK(info.st_mode), 'unprotected_original_helper')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1
             and before.st_size < 1024 * 1024, 'original_helper_metadata')
        content = os.read(fd, 1024 * 1024)
        after = os.fstat(fd)
        signature = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
        need(signature(before) == signature(after) == signature(path.lstat()), 'original_helper_changed')
        for p, info in lineage:
            now = p.lstat()
            need((now.st_dev, now.st_ino, now.st_mode, now.st_uid) ==
                 (info.st_dev, info.st_ino, info.st_mode, info.st_uid), 'original_helper_lineage_changed')
        need(sha(content) == PINS[PREFIX + 'helper.py'], 'original_helper_pin')
    finally:
        os.close(fd)
    module = types.ModuleType('h032_retained_original_helper')
    module.__file__ = str(path)
    exec(compile(content, str(path), 'exec'), module.__dict__)
    return module


@contextlib.contextmanager
def held_lock(anchor, name):
    # Existing descriptors only: no create, unlink or stale-lock clearing.
    with anchor.open(name, os.O_RDWR) as stream:
        need(stat.S_IMODE(stream.stat().st_mode) == 0o600, 'lock_metadata_changed')
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        stream.check()
        yield stream


def exact_saved(h, anchor):
    values = {name: h.raw(anchor, name) for name in PINS}
    need(all(sha(values[n]) == digest for n, digest in PINS.items()), 'saved_bytes_changed')
    for name in PINS:
        if name.startswith(PREFIX):
            need(stat.S_IMODE(anchor.stat(name).st_mode) == 0o400, 'evidence_mode_changed')
    for name in ('h032-image-handoff.json', 'h032-image-handoff-consumed.json',
                 'h032-image-mode02-consumed.json'):
        need(anchor.stat(name, missing_ok=True) is None, 'continuation_already_attempted')
    manifest = json.loads(values[PREFIX + 'archive-manifest.json'])
    for name, digest in manifest['files'].items():
        need(sha(h.raw(anchor, PREFIX + 'archive/' + name, 4 * 1024 * 1024)) == digest,
             'archive_changed')
        need(stat.S_IMODE(anchor.stat(PREFIX + 'archive/' + name).st_mode) == 0o400,
             'archive_mode_changed')
    state, op, recovery = (json.loads(values[n]) for n in ('state.json', 'operation.json', 'recovery.json'))
    need(state['phase'] == 'stopped' and state['container'] is None and state['warm'] is False
         and not state.get('native_actions') and not state.get('native_generation')
         and op['status'] == 'complete' and op['action'] == 'stop'
         and op['recovery'] == recovery['token']
         and recovery['status'] == 'active' and recovery['phase'] == 'settled_awaiting_reviewed_activation'
         and recovery['pid'] == 586481, 'settled_reservation_changed')
    return values, recovery


def absence(h, runtime):
    h.paused_owners(runtime)
    h.physical(runtime)
    need(h.absent(Path('/proc/586481')), 'original_helper_not_absent')
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit() or int(proc.name) == os.getpid():
            continue
        try:
            args = (proc / 'cmdline').read_bytes()
        except FileNotFoundError:
            continue
        need(str(BASE / PREFIX / 'helper.py').encode() not in args, 'original_helper_parent_alive')


def continue_handoff(h, module, runtime, *, prove=absence):
    """External proof producers may be fixture-substituted; anchored I/O is real."""
    with runtime.anchor() as anchor, held_lock(anchor, 'recovery.lock') as recovery_lock, \
            held_lock(anchor, 'operation.lock') as operation_lock:
        values, prior = exact_saved(h, anchor)
        with runtime.binding.mounted_guard(module.storage_io) as guard:
            with module.storage_io.AnchoredRoot(runtime.binding.path('logs'), guard) as logs:
                need(sha(h.raw(logs, 'image-runtime-attempts/' + FAILURE + '.json')) == FAILURE_SHA,
                     'original_failure_changed')
        prove(h, runtime)
        # Hold both known operational inodes through metadata repair and normal
        # Runtime construction; never replace their names or write their bytes.
        with contextlib.ExitStack() as stack:
            files = {n: stack.enter_context(anchor.open(n))
                     for n in ('source/service.py', 'config.json')}
            before = {n: f.stat() for n, f in files.items()}
            for info in before.values():
                need((stat.S_IMODE(info.st_mode), info.st_uid, info.st_gid) == (0o400, UID, GID),
                     'operational_metadata_changed')
            with runtime.critical(hardware=True):
                recovery_lock.check(); operation_lock.check()
                need(time.time() < END, 'continuation_deadline')
                need(exact_saved(h, anchor)[0] == values, 'changed_before_mutation')
                # Slow guards ran after opening both files. Revalidate BOTH
                # metadata identities before the first marker/chmod mutation.
                signature = lambda s: (s.st_dev, s.st_ino, s.st_uid, s.st_gid,
                    s.st_mode, s.st_nlink, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
                for name, stream in files.items():
                    need(signature(stream.stat()) == signature(before[name]),
                         'operational_metadata_changed_before_mutation')
                h.immutable(anchor, 'h032-image-mode02-consumed.json', h.js({
                    'case': 'h032-mode02', 'original_failure': FAILURE, 'raw_sha256': PINS,
                    'helper_sha256': sha(h.protected(Path(__file__)))}))
                for name, stream in files.items():
                    stream.check()
                    need(sha(h.raw(anchor, name)) == PINS[name], 'operational_bytes_changed')
                    os.fchmod(stream.fileno(), 0o600)
                    stream.fsync()
                    after, old = stream.stat(), before[name]
                    need((after.st_dev, after.st_ino, after.st_uid, after.st_gid,
                          after.st_size, after.st_mtime_ns) ==
                         (old.st_dev, old.st_ino, old.st_uid, old.st_gid, old.st_size, old.st_mtime_ns)
                         and stat.S_IMODE(after.st_mode) == 0o600, 'mode_repair_changed_identity')
                    need(sha(h.raw(anchor, name)) == PINS[name], 'mode_repair_changed_bytes')
            updated = module.Runtime()  # The full unmodified production constructor.
            updated.boot = h.BOOT
            prove(h, updated)
            with updated.critical(hardware=True):
                recovery_lock.check(); operation_lock.check()
                need(time.time() < END, 'continuation_deadline')
                for n, digest in PINS.items():
                    need(sha(h.raw(anchor, n)) == digest, 'changed_before_handoff')
                need(updated.record('recovery.json') == prior, 'reservation_changed')
                updated.write_record('recovery.json', dict(prior, config_sha256=updated.config_digest()))
                hashes = {n: sha(h.raw(anchor, n)) for n in
                          ('state.json', 'operation.json', 'recovery.json', 'config.json', 'source/service.py')}
                h.immutable(anchor, 'h032-image-handoff.json', h.js({
                    'schema_version': 1, 'case': h.CASE, 'boot': h.BOOT, 'gpu_uuid': h.GPU,
                    'raw_sha256': hashes, 'archive_sha256': PINS[PREFIX + 'archive-manifest.json'],
                    'plan_sha256': PINS[PREFIX + 'plan.json'],
                    'settlement_sha256': PINS[PREFIX + 'settlement.json'], 'native': h.NATIVE,
                    'cleanup_consumption_sha256': PINS[PREFIX + 'consumed.json']}))
            return {'status': 'MODE_REPAIRED_HANDOFF_PUBLISHED_API_STILL_PAUSED', 'raw_sha256': hashes}


def main():
    need(os.geteuid() == 0 and len(sys.argv) == 1 and time.time() < END, 'execution_not_authorized')
    h = original_helper()
    config_raw = h.protected(BASE / 'config.json')
    need(sha(config_raw) == PINS['config.json'], 'config_pin_changed')
    config = json.loads(config_raw)
    # Verify the pinned complete import closure before importing production code.
    for field, root in (('source_sha256', BASE / 'source'),
                        ('release_source_sha256', Path('/data/services/releases/h005-qwen0-mount-order-fix-20260925'))):
        for name, digest in config[field].items():
            need(sha(h.protected(root / name)) == digest, 'source_closure_changed')
    module = h.load_owner(PINS['source/service.py'])
    module.ATTEMPT = module.Attempt('h032_mode02_continuation')
    module.OPERATION_DEADLINE = time.monotonic() + min(90, END - time.time())
    failure = None
    try:
        # Pre-mode proof context uses exact config bytes, never bypasses the
        # production JSON reader. No start/native method is invoked on it.
        runtime = object.__new__(module.Runtime)
        runtime.binding = module.RegisteredStorageBinding.load(module.StorageRunner())
        need(runtime.binding.path('services', 'image21-runtime-20260923') == str(BASE), 'registered_root_changed')
        runtime.binding.validate_path('services', str(BASE))
        runtime.binding.validate_path('services', str(module.RELEASE))
        runtime.config = config
        runtime.boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
        need(runtime.boot == h.BOOT, 'boot_changed')
        print(json.dumps(continue_handoff(h, module, runtime), sort_keys=True))
    except BaseException as error:
        failure = error
        module.attempt_failure(error)
        raise
    finally:
        module.ATTEMPT.finish(failure)
        module.ATTEMPT = None
        module.OPERATION_DEADLINE = None


if __name__ == '__main__':
    main()
