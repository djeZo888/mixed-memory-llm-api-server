"""One closed dual-Q PREP/RUN wrapper around the existing canonical owner.

PREP is local source/receipt work. RUN needs a source/arm/session-bound root GO,
reviewed predecessor release, fresh host proof, and actual-image auth receipts.
No continuing owner, adoption, held pair, automatic inference retry or activation.
"""
from __future__ import annotations

import copy
import os
from pathlib import Path
import re
import signal
import socket
import stat
import time

from agent import protocol
from . import client, concurrent_cpu_run as recovery, concurrent_run as prior
from . import dualq_480k as contract, fixtures, glmrepair, profiles, runner

BASE = 'f130ec46ebd9a27319d84e0d372746e0489a9972'
INPUTS = ('incoming-latest.md', 'ROOT-PLAN.md', 'production-HANDOFF.md',
          'predecessor-evidence.json', 'protected-key-metadata.json')
OLD = {'task': 'REAL72-FOLLOWUP-B3-RUN-20260920', 'campaign': 'benchrun-p72b3-20260920',
       'source_commit': 'b69bd5c2a34adb462ee87333e2a238bd1c05436d',
       'session_id': '01a0c0b6-2901-7943-acbd-dd02d87b7e29',
       'keeper_pid': 71966, 'ssh_pid': 71972, 'remote_owner_pid': 1292520}


def _private_read(path):
    path = Path(path)
    meta = path.lstat()
    if (not stat.S_ISREG(meta.st_mode) or meta.st_uid != os.geteuid()
            or stat.S_IMODE(meta.st_mode) != 0o600):
        raise ValueError('dualq_private_regular_file_required')
    return path.read_bytes()


def _json(path):
    return protocol.strict_json_loads(_private_read(path))


def validate_predecessor(value):
    if (not isinstance(value, dict) or value.get('schema') != 1
            or any(value.get(key) != expected for key, expected in OLD.items())):
        raise ValueError('dualq_exact_old_keeper_required')
    containers = value.get('containers')
    if (not isinstance(containers, list) or len(containers) != 2
            or {row.get('role') for row in containers} != {'G1', 'Q1'}):
        raise ValueError('dualq_exact_old_container_pair_required')
    for row in containers:
        if (not re.fullmatch(r'[a-f0-9]{64}', row.get('id', ''))
                or not re.fullmatch(r'sha256:[a-f0-9]{64}', row.get('image_id', ''))
                or not isinstance(row.get('name'), str) or not row['name'].startswith(OLD['campaign'] + '-')):
            raise ValueError('dualq_exact_old_container_identity_required')
    if len({row['id'] for row in containers}) != 2:
        raise ValueError('dualq_duplicate_old_container_identity')
    release = value.get('canonical_release', {})
    if (not isinstance(release, dict) or not isinstance(release.get('entrypoint'), str)
            or not release['entrypoint'] or not isinstance(release.get('control_path'), str)
            or not Path(release['control_path']).is_absolute()):
        raise ValueError('dualq_canonical_old_release_plan_required')
    return value


def validate_arm(armed):
    from .host import concurrent_capacity_policy
    if (armed.get('scope') != contract.SCOPE or armed.get('campaign') != contract.CAMPAIGN
            or armed.get('base_commit') != BASE
            or not re.fullmatch(r'[a-f0-9]{40}', armed.get('source_commit', ''))
            or not isinstance(armed.get('session_id'), str) or not armed['session_id']
            or armed.get('manifests') != [contract.manifest(slot) for slot in contract.SLOTS]
            or armed.get('trial_plan') != contract.trial_plan()
            or armed.get('runtime_policy') != contract.POLICY
            or armed.get('concurrent_capacity_policy') != concurrent_capacity_policy(contract.SCOPE)
            or armed.get('production_acceptance') != 'NOT_GRANTED'
            or armed.get('actual_image_auth_status') != 'PENDING_ACTUAL_IMAGE_TESTS'
            or 'continuation_execution' in armed or 'start_epoch' in armed
            or 'hold' in armed or 'mode' in armed):
        raise ValueError('dualq_exact_arm_scope_required')
    return contract.SCOPE


def prepare(task, session):
    """Write a complete private arm package; no key reads, SSH or VM writes."""
    task = Path(task).resolve()
    client.private_artifact_directory(task)
    if (task / 'arm.json').exists() or not session or glmrepair.git('status', '--porcelain'):
        raise ValueError('dualq_clean_source_fresh_arm_session_required')
    for name in INPUTS:
        _private_read(task / name)
    validate_predecessor(_json(task / 'predecessor-evidence.json'))
    _key_metadata(_json(task / 'protected-key-metadata.json'), inspect=False)
    private = task / 'private'
    private.mkdir(mode=0o700, exist_ok=True)
    client.private_artifact_directory(private)
    runner.save(task / 'progress.json', {'phase': 'INITIAL', 'completed': {}, 'inflight': {}, 'errors': []})
    if not (task / 'run-control.json').exists():
        runner.save(task / 'run-control.json', {'action': 'CONTINUE'})
    if _json(task / 'run-control.json') != {'action': 'CONTINUE'}:
        raise ValueError('dualq_initial_control_not_continue')
    from .host import concurrent_capacity_policy
    inputs = (*INPUTS, 'progress.json', 'run-control.json')
    armed = {'schema': 1, 'scope': contract.SCOPE, 'campaign': contract.CAMPAIGN,
        'session_id': session, 'base_commit': BASE, 'source_commit': glmrepair.git('rev-parse', 'HEAD'),
        'runtime_policy': contract.POLICY, 'runtime_source_path': '/data/services/' + contract.CAMPAIGN + '/source',
        'manifests': [contract.manifest(slot) for slot in contract.SLOTS], 'trial_plan': contract.trial_plan(),
        'concurrent_capacity_policy': concurrent_capacity_policy(contract.SCOPE),
        'source_files': {p: fixtures.digest(b) for p, b in runner.source_files(contract.SCOPE).items()},
        'predecessor_evidence_sha256': fixtures.digest(_private_read(task / 'predecessor-evidence.json')),
        'frozen_inputs': {name: fixtures.digest(_private_read(task / name)) for name in INPUTS},
        'required_package_files': ['arm.json', 'arm-receipt.json', 'GO.template.json', *inputs],
        'initial_package_sha256': {name: fixtures.digest(_private_read(task / name)) for name in inputs},
        'production_acceptance': 'NOT_GRANTED', 'actual_image_auth_status': 'PENDING_ACTUAL_IMAGE_TESTS',
        'measurement_clock': 'NOT_STARTED_PREP_EXCLUDED'}
    validate_arm(armed)
    runner.save(task / 'arm.json', armed)
    receipt = {'source_commit': armed['source_commit'], 'preparation_session_id': session,
        'campaign': contract.CAMPAIGN, 'arm_sha256': fixtures.digest(_private_read(task / 'arm.json'))}
    runner.save(task / 'arm-receipt.json', receipt)
    runner.save(task / 'GO.template.json', {**receipt, 'decision': 'NOT_AUTHORIZED', 'vm_writer_handoff': False,
        'run_session_id': 'FRESH_RUN_SESSION_REQUIRED', 'runtime': contract.POLICY,
        'predecessor_evidence_sha256': armed['predecessor_evidence_sha256'],
        'release_receipt': {'path': 'REVIEWED_CANONICAL_RELEASE_RECEIPT_REQUIRED', 'sha256': None},
        'actual_image_auth_receipts': 'PENDING_POST_RELEASE_ACTUAL_IMAGE_FIXTURE_TESTS'})
    return armed


def _key_metadata(value, *, inspect):
    if not isinstance(value, dict) or len(value) != 3:
        raise ValueError('dualq_existing_protected_key_metadata_required')
    directories = [Path(path) for path, row in value.items() if row.get('directory') is True]
    if len(directories) != 1:
        raise ValueError('dualq_existing_protected_key_directory_required')
    root = directories[0]
    if not root.is_absolute() or root.name != 'private-credentials' or set(value) != {
            str(root), str(root / 'inference-key'), str(root / 'control-key')}:
        raise ValueError('dualq_existing_protected_key_paths_required')
    for name, row in value.items():
        directory = Path(name) == root
        if (row.get('mode') != ('0o700' if directory else '0o600')
                or row.get('uid') != os.geteuid() or row.get('symlink') is not False
                or row.get('key_bytes_read') is not False or row.get('regular') is not (not directory)
                or row.get('directory') is not directory):
            raise ValueError('dualq_existing_protected_key_metadata_invalid')
        if inspect:
            meta = Path(name).lstat()
            if (meta.st_uid != row['uid'] or stat.S_IMODE(meta.st_mode) != (0o700 if directory else 0o600)
                    or (not stat.S_ISDIR(meta.st_mode) if directory else not stat.S_ISREG(meta.st_mode))):
                raise ValueError('dualq_existing_protected_key_stat_changed')
    return root


def read_chain(task, go_path, session, *, restore_only=False):
    """Validate all local public/private source and receipt bytes BEFORE SSH/keys."""
    task = Path(task).resolve()
    client.private_artifact_directory(task)
    client.private_artifact_directory(task / 'private')
    armed, receipt, go = _json(task / 'arm.json'), _json(task / 'arm-receipt.json'), _json(go_path)
    validate_arm(armed)
    if (os.geteuid() == 0 or go.get('decision') != 'GO' or go.get('vm_writer_handoff') is not True
            or any(go.get(k) != v for k, v in receipt.items())
            or receipt.get('source_commit') != armed['source_commit']
            or receipt.get('preparation_session_id') != armed['session_id']
            or receipt.get('campaign') != contract.CAMPAIGN
            or receipt.get('arm_sha256') != fixtures.digest(_private_read(task / 'arm.json'))
            or armed['source_commit'] != glmrepair.git('rev-parse', 'HEAD') or glmrepair.git('status', '--porcelain')
            or {p: fixtures.digest(b) for p, b in runner.source_files(contract.SCOPE).items()} != armed['source_files']):
        raise ValueError('dualq_root_exact_source_arm_GO_required')
    if not session or session == armed['session_id'] or go.get('run_session_id') != session:
        raise ValueError('dualq_fresh_run_session_required')
    contract.validate_clock(armed, go.get('runtime', {}))
    for name, sha in armed['frozen_inputs'].items():
        if fixtures.digest(_private_read(task / name)) != sha:
            raise ValueError('dualq_frozen_input_changed')
    validate_predecessor(_json(task / 'predecessor-evidence.json'))
    if go.get('predecessor_evidence_sha256') != armed['predecessor_evidence_sha256']:
        raise ValueError('dualq_reviewed_predecessor_required')
    reference = go.get('release_receipt', {})
    if (not isinstance(reference, dict) or not isinstance(reference.get('path'), str)
            or not Path(reference['path']).is_absolute()
            or not re.fullmatch(r'[a-f0-9]{64}', reference.get('sha256', ''))):
        raise ValueError('dualq_reviewed_canonical_release_reference_required')
    raw = _private_read(reference['path'])
    released = protocol.strict_json_loads(raw)
    if (fixtures.digest(raw) != reference.get('sha256')
            or released.get('predecessor_evidence_sha256') != armed['predecessor_evidence_sha256']
            or released.get('status') != 'RESTORED' or released.get('original_endstate') != 'STOPPED/manual'
            or released.get('canonical_lease') != 'LEASE_FREE'
            or any(type(released.get(name)) is not int or released[name] != 0
                   for name in ('benchmark_owned_resources', 'benchmark_listeners'))):
        raise ValueError('dualq_reviewed_canonical_release_receipt_required')
    auth = go.get('actual_image_auth_receipts')
    if not isinstance(auth, dict) or set(auth) != {'base', 'Q0', 'Q1'}:
        raise ValueError('dualq_post_release_actual_image_auth_receipts_required')
    for ref in auth.values():
        if (not isinstance(ref, dict) or set(ref) != {'registered_path', 'sha256'}
                or not isinstance(ref['registered_path'], str) or not ref['registered_path'].startswith('/data/')
                or '..' in Path(ref['registered_path']).parts
                or not re.fullmatch(r'[a-f0-9]{64}', ref['sha256'])):
            raise ValueError('dualq_protected_actual_image_auth_reference_required')
    execution = task / 'execution-arm.json'
    if not restore_only:
        if execution.exists():
            raise ValueError('dualq_no_rerun_or_clock_reset')
        for name in armed['required_package_files']:
            _private_read(task / name)
        prior.verify_initial_package(task, armed)
        glmrepair.checkpoint(task)
    keys = _key_metadata(_json(task / 'protected-key-metadata.json'), inspect=True)
    executed = {**armed, 'runtime': copy.deepcopy(go['runtime']), 'session_id': session,
                'preparation_arm_sha256': receipt['arm_sha256'],
                'release_receipt': copy.deepcopy(released),
                'release_receipt_sha256': reference['sha256'],
                'actual_image_auth_receipts': copy.deepcopy(go.get('actual_image_auth_receipts'))}
    if restore_only and _json(execution) != executed:
        raise ValueError('dualq_recovery_execution_changed')
    return executed, keys


def run(task, go_path, session, *, restore_only=False):
    task = Path(task).resolve()
    executed, keys = read_chain(task, go_path, session, restore_only=restore_only)
    runner.run_preflight(contract.SCOPE)
    from runtime.sglang38_file_auth import read_key
    key, control = read_key(keys / 'inference-key'), read_key(keys / 'control-key')
    job = contract.DualQRun(task, executed, None, key)
    if not restore_only:
        runner.save(task / 'execution-arm.json', executed)
    host = glmrepair.DiagnosticSSHHost(executed, stage=not restore_only)
    job.host = host
    failed, restored, errors = False, False, []
    handlers = {sig: signal.getsignal(sig) for sig in (signal.SIGINT, signal.SIGTERM)}
    for sig in handlers:
        signal.signal(sig, lambda signum, frame: job.interrupted.set())
    def safe_save(path, value):
        try:
            runner.save(path, value)
        except BaseException as error:
            errors.append({'phase': 'evidence_write', 'error_class': type(error).__name__})
    try:
        if not restore_only:
            try:
                job.execute()  # Existing execute drains every lane before return.
            except BaseException as error:
                failed = True
                from .host import rpc_diagnostic
                errors.append({'phase': 'measurement', **rpc_diagnostic('measurement', error)})
        try:
            phase = host.call('status')['phase']
            if phase not in {'FAILED_BEFORE_OWNERSHIP', 'FAILED_BEFORE_MUTATION'} and (restore_only or phase != 'NEW'):
                host = recovery.restore_once(host, executed, task, key, control)
                restored = True
        except BaseException as error:
            failed = True
            if isinstance(error, recovery.RecoveryRequired):
                host = error.recovery_host
            errors.append({'phase': 'restoration', 'error_class': type(error).__name__})
    finally:
        for sig, handler in handlers.items():
            signal.signal(sig, handler)
        try:
            terminal = 'RESTORED' if restored else host.call('status')['phase']
            if terminal in {'RESTORED', 'NEW', 'FAILED_BEFORE_OWNERSHIP', 'FAILED_BEFORE_MUTATION'}:
                host.close()
                ports = {}
                for port in (31002, 31004):
                    with socket.socket() as sock:
                        sock.settimeout(1)
                        ports[str(port)] = 'CLOSED' if sock.connect_ex(('127.0.0.1', port)) else 'OPEN'
                failed |= set(ports.values()) != {'CLOSED'}
                safe_save(task / 'final-restoration-receipt.json', {'restored': restored,
                    'status': 'RESTORED_WITH_MEASUREMENT_FAILURE' if restored and failed else 'RESTORED' if restored else 'FAIL',
                    'authenticated_worker_LAN': restored, 'local_tunnels': ports, 'original_endstate': 'STOPPED/manual'})
        except BaseException as error:
            failed = True
            errors.append({'phase': 'host_close', 'error_class': type(error).__name__})
        outcome = {'measurement_failed': failed, 'restored': restored, 'errors': errors,
            'source_commit': executed['source_commit'], 'session_id': session, 'clock_policy': contract.POLICY,
            'completed': list(job.progress['completed']), 'production_acceptance': 'NOT_GRANTED'}
        safe_save(task / ('recovery-outcome.json' if restore_only else 'run-outcome.json'), outcome)
        safe_save(task / 'status.json', {**outcome, 'phase': 'RESTORED' if restored else 'RECOVERY_REQUIRED'})
    return 1 if failed or not restored or errors else 0
