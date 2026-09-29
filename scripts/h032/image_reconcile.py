#!/usr/bin/env python3
"""One reviewed H032 abandoned image pair, never an API/admin cleanup interface.

No argv/env paths. API must already be paused by the reviewed deployment. This
helper never starts a model. A consumed intent is permanent even on failure.
"""
import copy
import hashlib
import types
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import time
import uuid

BASE = Path('/data/services/image21-runtime-20260923')
PREFIX = 'h032-image-reconcile/'
CASE = 'h032-image-recover01'
BOOT = '992bf979-efae-495b-9ab2-26e75ed5c5d0'
GPU = 'GPU-5d895991-b794-2b4c-b9c4-5f1b668afd23'
CID = 'd66478c5449611e521af17e918b8929c0d7d2d0a6526788d9ed55386b57cd539'
RUN = '6e8aa276397a451cb5a480b2c0aa90ea'
OLD_SERVICE = '26f7b17da42bd07806c49d6477b3169efb5d33003d551cf5b6bb972742547556'
OLD_CONFIG = '874794b83ed0182b6651b607517af44ac94f6125abc3b6c1509886aa82b359c9'
OLD_RECORDS = {
    'state.json': 'c0cfd3fa4878d3eda2112b3ced577b77fbcb5d15bbab0c15b24ae52b3f3cc748',
    'operation.json': '8eaaf68cd2bca7a4252c3e039c634a241c68a34e392a3a650a8366814e60e918',
    'recovery.json': 'f0e223083077561ec8d5556c3fb43ded811f47ab28429599e6876fc469866419'}
NATIVE = {'id': CID, 'pid': 1661054, 'cgroup': '/system.slice/docker-' + CID + '.scope'}
END = 1790685900  # Root-reviewed activation admission cutoff: 2026-09-29 12:45 UTC.
LIMIT = 2 * 1024 * 1024
NATIVE_UID, NATIVE_GID = 1000, 1001


def need(ok, code):
    if not ok:
        raise RuntimeError(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def js(value):
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()


def raw(anchor, name, limit=LIMIT):
    with anchor.open(name) as stream:
        need(stream.stat().st_size <= limit, 'evidence_size_bound')
        chunks = []
        while True:
            chunk = stream.read(min(1024 * 1024, limit + 1))
            if not chunk:
                break
            chunks.append(chunk)
            limit -= len(chunk)
            need(limit >= 0, 'evidence_size_bound')
        return b''.join(chunks)


def immutable(anchor, name, content):
    with anchor.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o400) as stream:
        stream.write(content)
        stream.fsync()
        os.fsync(stream.parent)
        stream.check()
    need(raw(anchor, name, max(LIMIT, len(content))) == content, 'archive_readback_changed')
    return sha(content)


def protected(path):
    lineage = []
    for parent in (path, *path.parents):
        info = parent.lstat()
        need(info.st_uid == 0 and not info.st_mode & 0o022
             and not stat.S_ISLNK(info.st_mode), 'unprotected_input')
        lineage.append((parent, info.st_dev, info.st_ino))
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        need(stat.S_ISREG(info.st_mode) and info.st_nlink == 1
             and info.st_size <= LIMIT
             and (info.st_dev, info.st_ino) == lineage[0][1:], 'unprotected_input')
        chunks, size = [], 0
        while True:
            chunk = os.read(fd, min(1024 * 1024, LIMIT + 1 - size))
            if not chunk:
                break
            chunks.append(chunk); size += len(chunk)
            need(size <= LIMIT, 'protected_input_bound')
        for parent, dev, ino in lineage:
            current = parent.lstat()
            need((current.st_dev, current.st_ino) == (dev, ino)
                 and current.st_uid == 0 and not current.st_mode & 0o022
                 and not stat.S_ISLNK(current.st_mode), 'protected_input_replaced')
        after = os.fstat(fd)
        need((after.st_size, after.st_mtime_ns, after.st_ctime_ns) ==
             (info.st_size, info.st_mtime_ns, info.st_ctime_ns), 'protected_input_changed')
        return b''.join(chunks)
    finally:
        os.close(fd)


def load_owner(expected):
    path = BASE / 'source/service.py'
    content = protected(path)
    need(sha(content) == expected, 'service_source_changed')
    module = types.ModuleType('h032_image_' + expected[:12])
    module.__file__ = str(path)
    # Execute the exact verified buffer, not a second pathname read.
    exec(compile(content, str(path), 'exec'), module.__dict__)
    return module


def absent(path):
    # exists() hides some access errors. Only ENOENT is proof; reused/zombie
    # PIDs and symlinks all refuse. The parent /proc remains trusted/readable.
    try:
        path.lstat()
    except FileNotFoundError:
        return True
    return False


def command(argv, limit=LIMIT):
    result = subprocess.run(argv, capture_output=True, timeout=8, check=True)
    need(len(result.stdout) + len(result.stderr) <= limit, 'evidence_command_size_bound')
    return result.stdout, result.stderr


def unit(name):
    out, _ = command(['systemctl', 'show', name, '-p',
                      'MainPID,ControlPID,ActiveState,SubState,InvocationID,Job,ControlGroup'])
    return dict(line.split('=', 1) for line in out.decode().splitlines())


def paused_owners(runtime):
    api = unit('llm-image-api.service')
    backend = unit('llm-image-backend.service')
    for value in (api, backend):
        need(value.get('MainPID') == value.get('ControlPID') == '0'
             and value.get('Job') == '' and value.get('ControlGroup') == ''
             and value.get('ActiveState') in ('inactive', 'failed'), 'live_image_unit_owner')
    need(backend.get('InvocationID') == RUN, 'backend_invocation_changed')
    jobs, _ = command(['systemctl', 'list-jobs', '--no-legend', '--no-pager'])
    need(not any(x in jobs for x in (b'llm-image-api', b'llm-image-backend')), 'image_unit_job')
    for pid in (1656742, 1655508):
        need(absent(Path('/proc') / str(pid)), 'recorded_owner_not_absent')
    # With API cgroup empty, no admitted owner/request can survive shutdown.
    # Also reject detached old runtime helper/telemetry/native-request children.
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit() or int(proc.name) == os.getpid():
            continue
        try:
            args = (proc / 'cmdline').read_bytes()
        except FileNotFoundError:
            continue
        if str(BASE / 'source').encode() in args:
            need(False, 'live_image_helper')
    return {'api': api, 'backend': backend, 'jobs': jobs.decode(),
            'recorded_owners_absent': [1656742, 1655508]}


def exact(runtime, anchor, plan):
    need(runtime.boot == BOOT == plan['boot'], 'boot_changed')
    expected = {**OLD_RECORDS, 'config.json': OLD_CONFIG, 'source/service.py': OLD_SERVICE}
    values = {name: raw(anchor, name) for name in expected}
    need(all(sha(values[n]) == h for n, h in expected.items()), 'predecessor_bytes_changed')
    state, op, recovery = (json.loads(values[n]) for n in ('state.json', 'operation.json', 'recovery.json'))
    need(op['status'] == recovery['status'] == 'active' and op['action'] == 'start'
         and op['token'] == '868d9b48784b44f4b702b52c05655a65'
         and recovery['token'] == op['recovery'] == '83be8882e6374f3fbc3918de6bc5107c'
         and op['invocation_id'] == recovery['child_start'] == state['run_id'] == RUN
         and op['boot'] == recovery['boot'] == BOOT
         and op['config_sha256'] == recovery['config_sha256'] == runtime.config_digest()
         and op['gpu_uuid'] == recovery['gpu_uuid'] == GPU
         and state['owner'] == runtime.config['owner'], 'predecessor_crosslink_changed')
    need(state['native_actions'] == {'create': 'received', 'start': 'received', 'warm': 'dispatched'},
         'uncertain_cleanup_action')
    native = runtime.exact_native(state)
    need(native['Id'] == CID and native['State']['Running'] is True
         and native['State']['OOMKilled'] is False
         and runtime.native_generation(native) == state['native_generation'], 'native_identity_changed')
    need((Path('/proc') / str(NATIVE['pid']) / 'cgroup').read_text().strip()
         == '0::' + NATIVE['cgroup'], 'native_cgroup_changed')
    return values, state, op, recovery, native


def native_evidence(runtime, anchor, native):
    """Read only this UID-owned generation through no-follow held directories."""
    need(native['HostConfig']['LogConfig'] == {'Type': 'none', 'Config': {}}, 'native_log_policy_changed')
    need(any(m.get('Type') == 'bind' and m.get('Source') == str(BASE / 'work')
             and m.get('Destination') == '/work' for m in native['Mounts']), 'native_work_bind_changed')
    parent_meta = anchor.stat('work/evidence')
    parent = os.open(BASE / 'work/evidence', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    directory = None
    evidence, metadata = {}, {}
    try:
        p = os.fstat(parent)
        need((p.st_dev, p.st_ino) == (parent_meta.st_dev, parent_meta.st_ino), 'native_parent_replaced')
        directory = os.open(RUN, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent)
        d = os.fstat(directory)
        need(d.st_uid == NATIVE_UID and d.st_gid == NATIVE_GID and not d.st_mode & 0o077
             and d.st_dev == p.st_dev, 'native_evidence_owner_changed')
        for name in ('backend.log', 'generation-request.json', 'generation-response.json',
                     'generation-summary.json', 'generation-perf.json', 'generation.png'):
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK, dir_fd=directory)
            try:
                before = os.fstat(fd)
                need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1
                     and before.st_uid == NATIVE_UID and before.st_gid == NATIVE_GID
                     and not before.st_mode & (0o022 if name == 'generation-perf.json' else 0o077)
                     and before.st_dev == p.st_dev, 'native_evidence_unsafe')
                bound = 1024 * 1024 if name == 'backend.log' else 4 * 1024 * 1024
                offset = max(0, before.st_size - bound) if name == 'backend.log' else 0
                need(name == 'backend.log' or before.st_size <= bound, 'native_evidence_bound')
                os.lseek(fd, offset, os.SEEK_SET)
                content = bytearray()
                while len(content) <= bound:
                    part = os.read(fd, min(1024 * 1024, bound + 1 - len(content)))
                    if not part:
                        break
                    content.extend(part)
                need(len(content) <= bound, 'native_evidence_grew')
                after, named = os.fstat(fd), os.stat(name, dir_fd=directory, follow_symlinks=False)
                need((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns)
                     == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)
                     and (named.st_dev, named.st_ino) == (before.st_dev, before.st_ino), 'native_evidence_changed')
                if name == 'backend.log':
                    lines = bytes(content).splitlines(keepends=True)
                    if len(lines) > 1000:
                        offset += sum(map(len, lines[:-1000])); content = bytearray(b''.join(lines[-1000:]))
                evidence['native-' + name] = bytes(content)
                metadata[name] = {'source_bytes': before.st_size, 'archived_bytes': len(content),
                                  'offset': offset, 'truncated': offset > 0, 'sha256': sha(content)}
            finally:
                os.close(fd)
        named = os.stat(RUN, dir_fd=parent, follow_symlinks=False)
        need((named.st_dev, named.st_ino) == (d.st_dev, d.st_ino), 'native_directory_replaced')
        anchor.check()
    finally:
        if directory is not None:
            os.close(directory)
        os.close(parent)
    summary = json.loads(evidence['native-generation-summary.json'])
    need(summary['run_id'] == RUN and summary['status'] == 'pass'
         and summary['output']['sha256'] == sha(evidence['native-generation.png'])
         and summary['response_bytes'] == len(evidence['native-generation-response.json'])
         and summary['request_body_sha256'] == sha(evidence['native-generation-request.json'])
         and summary['native_perf']['sha256'] == sha(evidence['native-generation-perf.json']),
         'native_output_digest_changed')
    evidence['native-log-bound.json'] = js({
        'docker_log_stream': 'ABSENT_BY_EXACT_LOG_DRIVER_NONE', 'native_log': 'backend.log',
        'run_id': RUN, 'since_native_started_at': native['State']['StartedAt'],
        'until_observed_utc': runtime_module.now(), 'line_cap': 1000, 'byte_cap': 1024 * 1024,
        'files': metadata})
    return evidence


def archive(runtime, anchor, plan_raw, values, native, owners):
    anchor.mkdir(PREFIX + 'archive', mode=0o700, parents=False)
    evidence = {('service.py' if n == 'source/service.py' else n): b for n, b in values.items()}
    evidence.update({'native-inspect.json': js(native), 'owner-proof.json': js(owners),
                     'plan.json': plan_raw,
                     'hardware-proof.json': js(runtime.hardware_observation),
                     'native-generation.json': js(runtime.native_generation(native))})
    # Match the original failing attempts, not a broad journal/receipt sweep.
    with runtime.binding.mounted_guard(runtime_module.storage_io) as guard:
        with runtime_module.storage_io.AnchoredRoot(runtime.binding.path('logs'), guard) as logs:
            for attempt in ('03b0c9d00efd493fa1ec9f065ce4de5e', '1518f23193164d529609b02871873b12'):
                evidence['attempt-' + attempt + '.json'] = raw(logs, 'image-runtime-attempts/' + attempt + '.json')
    for attempt, action, code in (('03b0c9d00efd493fa1ec9f065ce4de5e', 'start', 'image_operation_changed'),
                                  ('1518f23193164d529609b02871873b12', 'recover', 'owned_systemd_restart_warm_failed')):
        receipt = json.loads(evidence['attempt-' + attempt + '.json'])
        need(receipt['attempt_id'] == attempt and receipt['action'] == action and receipt['code'] == code,
             'original_failure_receipt_changed')
    evidence['telemetry.jsonl'] = raw(anchor, 'receipts/' + RUN + '-telemetry.jsonl')
    evidence.update(native_evidence(runtime, anchor, native))
    for invocation in (RUN, '32af9e02739e449a84621814de680205'):
        evidence['journal-' + invocation + '.jsonl'], _ = command([
            'journalctl', '--no-pager', '-o', 'json', '--since', '2026-09-29 09:55:00 UTC',
            '--until', '2026-09-29 09:57:10 UTC', '-n', '1000', '_SYSTEMD_INVOCATION_ID=' + invocation])
    # The exact run's native files above are copied and hashed; retain original
    # references/history too, without reading any other invocation directory.
    state = json.loads(values['state.json'])
    need(json.loads(evidence['native-generation-summary.json']) == state['generation'],
         'original_generation_summary_changed')
    evidence['native-output-references.json'] = js({
        'run_id': RUN, 'directory': str(BASE / 'work/evidence' / RUN),
        'generation': state['generation'], 'telemetry_path': state['telemetry_path'],
        'historical_failure': state.get('historical_failure')})
    files = {name: immutable(anchor, PREFIX + 'archive/' + name, content)
             for name, content in evidence.items()}
    manifest = {'schema_version': 1, 'case': CASE, 'boot': BOOT, 'files': files}
    digest = immutable(anchor, PREFIX + 'archive-manifest.json', js(manifest))
    # Read every archived file after all writes, before intent or native mutation.
    need(all(sha(raw(anchor, PREFIX + 'archive/' + n, 4 * 1024 * 1024)) == h for n, h in files.items()),
         'archive_digest_changed')
    return digest


def physical(runtime):
    runtime.prove_absent(CID)
    need(absent(Path('/proc') / str(NATIVE['pid']))
         and absent(Path('/sys/fs/cgroup' + NATIVE['cgroup'])), 'native_physical_settlement_missing')
    runtime.require_ada_idle()
    runtime.check_ports()


def phase(name):
    recorder = getattr(globals().get('runtime_module'), 'attempt_phase', None)
    if recorder:
        recorder(name)


def reconcile(runtime, plan_raw, collect=archive, owners=paused_owners):
    phase('reconcile_preflight')
    plan = json.loads(plan_raw)
    need(plan['case'] == CASE and plan['boot'] == BOOT and plan['gpu_uuid'] == GPU
         and plan['native'] == NATIVE and plan['old_service_sha256'] == OLD_SERVICE
         and plan['old_config_sha256'] == OLD_CONFIG
         and plan['activation_deadline_unix'] == END and time.time() < END, 'wrong_reviewed_case')
    runtime.boot = BOOT
    plan_sha = sha(plan_raw)
    with runtime.anchor() as anchor, runtime.singleton('recovery.lock') as lock:
        with runtime.singleton('operation.lock') as operation:
            need(anchor.stat(PREFIX + 'consumed.json', missing_ok=True) is None, 'plan_already_consumed')
            proof = owners(runtime)
            values, state, op, prior, native = exact(runtime, anchor, plan)
            with runtime.critical(hardware=True):
                lock.check(); operation.check()
            phase('reconcile_archive')
            archive_sha = collect(runtime, anchor, plan_raw, values, native, proof)
            # Slow archive/system evidence ran outside the common lease. Check
            # exact predecessor/native again before any durable authority change.
            owners(runtime)
            need(exact(runtime, anchor, plan)[0] == values, 'predecessor_changed_during_archive')
            phase('reconcile_ownership')
            with runtime.critical(hardware=True):
                lock.check(); operation.check()
                immutable(anchor, PREFIX + 'consumed.json', js({
                    'schema_version': 1, 'case': CASE, 'boot': BOOT,
                    'archive_sha256': archive_sha, 'plan_sha256': plan_sha}))
                op.update(status='failed', reason='abandoned_owner_reconciliation', archive_sha256=archive_sha)
                runtime.write_record('operation.json', op)
                prior = dict(prior, token=uuid.uuid4().hex, pid=os.getpid(),
                             process=runtime.process_stamp(os.getpid()), phase='settle',
                             reconciliation={'case': CASE, 'archive_sha256': archive_sha, 'plan_sha256': plan_sha})
                runtime.write_record('recovery.json', prior)
                runtime.recovery_record = prior
        # Only this operation descriptor is reacquired; recovery ownership stays.
        original_dispatch = runtime.dispatch
        def cleanup_dispatch(state, action, argv, **kwargs):
            lock.check()
            need(runtime.record('recovery.json') == runtime.recovery_record, 'cleanup_owner_changed')
            need(action in ('stop', 'remove') and argv[-1] == CID, 'cleanup_action_not_exact')
            # A PID/start-ticks change cannot borrow the reviewed generation.
            value = runtime.exact_native(state)
            if value['State']['Running']:
                need(runtime.native_generation(value) == state['native_generation'], 'native_identity_changed')
            return original_dispatch(state, action, argv, **kwargs)
        runtime.dispatch = cleanup_dispatch
        try:
            runtime.reset_owned()  # first stop/remove only; historical warm never called
        finally:
            runtime.dispatch = original_dispatch
        phase('reconcile_physical_settlement')
        physical(runtime)
        with runtime.critical():
            need(runtime.record('recovery.json') == prior, 'cleanup_owner_changed')
            settlement_sha = immutable(anchor, PREFIX + 'settlement.json', js({
                'schema_version': 1, 'case': CASE, 'boot': BOOT, 'gpu_uuid': GPU,
                'native': NATIVE, 'archive_sha256': archive_sha,
                'plan_sha256': plan_sha, 'physically_absent': True,
                'original_attempt': {'operation_token': '868d9b48784b44f4b702b52c05655a65',
                    'recovery_token': '83be8882e6374f3fbc3918de6bc5107c',
                    'status': 'failed', 'reason': 'abandoned_owner_reconciliation'},
                'last_native_actions': runtime.state().get('last_native_actions')}))
            prior = dict(prior, phase='settled_awaiting_reviewed_activation')
            runtime.write_record('recovery.json', prior)
            runtime.recovery_record = prior
        install(runtime, anchor, lock, plan, plan_sha, archive_sha, settlement_sha, prior, owners)


def install(runtime, anchor, lock, plan, plan_sha, archive_sha, settlement_sha, prior, owners):
    """API remains paused; active ownership closes every partial install/crash."""
    phase('reconcile_install')
    with runtime.singleton('operation.lock') as operation:
        owners(runtime); physical(runtime)
        new_source = raw(anchor, PREFIX + 'candidate-service.py')
        new_config = raw(anchor, PREFIX + 'candidate-config.json')
        need(sha(new_source) == plan['new_service_sha256']
             and sha(new_config) == plan['new_config_sha256'], 'candidate_changed')
        config = json.loads(new_config)
        expected = copy.deepcopy(runtime.config)
        expected['source_sha256']['service.py'] = plan['new_service_sha256']
        need(config == expected, 'config_delta_not_service_only')
        with runtime.critical(hardware=True):
            lock.check(); operation.check()
            need(runtime.record('recovery.json') == prior, 'cleanup_owner_changed')
            for name, old, content in [('source/service.py', OLD_SERVICE, new_source),
                                       ('config.json', OLD_CONFIG, new_config)]:
                need(sha(raw(anchor, name)) == old, 'install_cas_changed')
                # Exclusive staging leaves survive all failed attempts.
                temp = PREFIX + 'install-' + name.replace('/', '-')
                immutable(anchor, temp, content)
                anchor.replace(temp, name)
        # Source/config are now consistent. New owner checks complete closure.
        updated_module = load_owner(plan['new_service_sha256'])
        updated_module.OPERATION_DEADLINE = getattr(runtime_module, 'OPERATION_DEADLINE', None)
        updated = updated_module.Runtime()
        updated.boot = BOOT
        phase('reconcile_handoff')
        with updated.critical(hardware=True):
            lock.check(); operation.check()
            need(updated.record('recovery.json') == prior, 'cleanup_owner_changed')
            prior = dict(prior, config_sha256=updated.config_digest())
            updated.write_record('recovery.json', prior)
            hashes = {name: sha(raw(anchor, name)) for name in
                      ('state.json', 'operation.json', 'recovery.json', 'config.json', 'source/service.py')}
            immutable(anchor, 'h032-image-handoff.json', js({
                'schema_version': 1, 'case': CASE, 'boot': BOOT, 'gpu_uuid': GPU,
                'raw_sha256': hashes, 'archive_sha256': archive_sha, 'plan_sha256': plan_sha,
                'settlement_sha256': settlement_sha, 'native': NATIVE,
                'cleanup_consumption_sha256': sha(raw(anchor, PREFIX + 'consumed.json'))}))
    # No backend start. Only the ordinary API startup may consume this handoff.


def main():
    global runtime_module
    need(os.geteuid() == 0 and len(sys.argv) == 1 and time.time() < END, 'execution_not_authorized')
    runtime_module = load_owner(OLD_SERVICE)
    runtime_module.ATTEMPT = runtime_module.Attempt('h032_reconcile')
    failure = None
    try:
        runtime = runtime_module.Runtime()
        with runtime.anchor() as anchor:
            plan_raw = raw(anchor, PREFIX + 'plan.json')
            need(json.loads(plan_raw)['helper_sha256'] == sha(protected(Path(__file__))), 'helper_pin_changed')
        # Once admitted, cleanup retains its own finite settlement budget.
        runtime_module.OPERATION_DEADLINE = time.monotonic() + 120
        reconcile(runtime, plan_raw)
        print(json.dumps({'status': 'SETTLED_INSTALLED_AWAITING_ONE_API_START', 'case': CASE}))
    except BaseException as error:
        failure = error
        runtime_module.attempt_failure(error)
        raise
    finally:
        # Existing immutable attempt store + safe journal fallback. Receipt
        # failure does not replace the primary failure or trigger another action.
        runtime_module.ATTEMPT.finish(failure)
        runtime_module.ATTEMPT = None
        runtime_module.OPERATION_DEADLINE = None


if __name__ == '__main__':
    main()
