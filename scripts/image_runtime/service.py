#!/usr/bin/env python3
"""Fixed image-only systemd lifecycle. No request-derived commands or paths."""
from __future__ import annotations

import contextlib
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import shutil
import stat
import subprocess
import sys
import syslog
import time
import uuid
import urllib.error
import urllib.request

# Fixed candidate directory; the reviewed external manifest binds its commit and
# raw bytes. Do not derive this path from this file's hash (a circular binding),
# replace an existing nonidentical release, or fall back to an older release.
RELEASE = Path('/data/services/releases/h005-qwen0-mount-order-fix-20260925')
BASE = Path('/data/services/image21-runtime-20260923')
UNIT = 'llm-image-backend.service'
NAME = 'llm-image-backend'
NETWORK = 'llm-image-backend-private'
OWNER = 'IMAGE21-RUNTIME-20260923'
GPU_UUID = 'GPU-5d895991-b794-2b4c-b9c4-5f1b668afd23'
CHECKPOINT_REV = '790c92633540aa0cb11d9abf19eb46d861714758'
SOURCE_SHA = '0cd8be351d0825488f4b81c8931167bbab618eca'
CAP_BYTES = 96 * 1024**3
OPERATION_DEADLINE = None
SETTLEMENT_DEADLINE = None
NATIVE_UID, NATIVE_GID = 1000, 1001
# These are the exact executable runtime files and the complete import/guard
# closure used by this image owner. Protected config supplies their raw hashes;
# missing or extra entries are refused, including an omitted new dependency.
RUNTIME_SOURCE_FILES = ('native_request.py', 'native_server.py', 'service.py', 'telemetry.py')
RELEASE_SOURCE_FILES = (
    'scripts/common/lifecycle_lease.py', 'scripts/common/registered-storage.py',
    'scripts/control/__init__.py', 'scripts/control/installation.py',
    'scripts/control/hardware_latch.py',
    'scripts/install/__init__.py', 'scripts/install/storage.py', 'scripts/install/storage_io.py',
    'scripts/lifecycle/__init__.py', 'scripts/lifecycle/manager.py',
    'scripts/lifecycle/runtime_io.py', 'scripts/lifecycle/storage_binding.py',
    'scripts/lifecycle/qwen_next.py', 'scripts/lifecycle/slot_state.py',
    'scripts/lifecycle/hardware_policy.py',
    'scripts/runtime/qwen38_oci.py',
    'scripts/runtime/h005_runtime_binding.py', 'configs/runtimes/h005-runtime-binding.json',
    'scripts/runtime/verify_adaptive_idle_overlay.py',
    'scripts/runtime/adaptive_idle_sources.json', 'scripts/runtime/adaptive_idle_source_gate.py',
    'scripts/runtime/build_adaptive_idle_overlay.py',
    'scripts/runtime/adaptive_idle.py', 'scripts/runtime/adaptive_text.py',
    'scripts/runtime/adaptive_text_drain.py', 'scripts/runtime/adaptive_diffusion.py',
    'scripts/runtime/adaptive_diffusion_drain.py',
    'scripts/runtime/patches/text-adaptive-idle.patch',
    'scripts/runtime/patches/text-adaptive-drain.patch',
    'scripts/runtime/patches/text-adaptive-grammar.patch',
    'scripts/runtime/patches/diffusion-adaptive-idle.patch',
    'scripts/runtime/patches/diffusion-adaptive-drain.patch',
    'scripts/image_runtime/source-closure.json',
)
sys.path.insert(0, str(RELEASE / 'scripts'))
from common.lifecycle_lease import acquire_lease, LeaseBusy, LeaseError
from control.installation import protected_file
from install import storage_io
from install.storage import StorageError
from lifecycle.manager import StorageRunner
from lifecycle.runtime_io import validate_image_container
from lifecycle.storage_binding import RegisteredStorageBinding
from lifecycle.hardware_policy import HardwarePolicy, RegisteredLatchStore
from runtime.h005_runtime_binding import load as load_runtime_binding


def require(condition, code):
    if not condition:
        raise RuntimeError(code)


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


# Exact codes only: exception text, subprocess output and arbitrary code-shaped
# strings are never diagnostics. Unknown exceptions collapse to a fixed code.
SAFE_FAILURE_CODES = frozenset({
    'ada_compute_process_already_present',
    'ada_current_margin_below_5_percent',
    'ada_identity_missing',
    'ada_initial_margin_below_5_percent',
    'ada_memory_unavailable',
    'ada_preload_weight_and_margin_unavailable',
    'ada_process_inventory_invalid',
    'ada_process_ownership_mismatch',
    'ada_sampled_peak_margin_below_5_percent',
    'anchored_rmtree_required',
    'checkpoint_path_mismatch',
    'checkpoint_receipt_changed',
    'checkpoint_receipt_incomplete',
    'config_identity_mismatch',
    'conflicting_backend_name',
    'deterministic_warm_failed',
    'hardware_boot_identity_unknown',
    'hardware_fault',
    'hardware_inventory_unknown',
    'hardware_latch_first_install_review_required',
    'hardware_latch_state_invalid',
    'hardware_latch_storage_unavailable',
    'hardware_missing',
    'hardware_target_unknown',
    'hardware_validation_stale',
    'host_headroom_below_15_percent',
    'host_sampled_margin_below_15_percent',
    'image_digest_required',
    'invalid_created_container_id',
    'invalid_fixed_action',
    'invalid_invocation',
    'invalid_owned_container_id',
    'invalid_tmp_owner',
    'lifecycle_busy',
    'native_backend_not_running',
    'native_backend_unready',
    'native_cgroup_swap_observed_or_unavailable',
    'native_exited_during_load',
    'native_network_attachment_mismatch',
    'native_port_already_owned',
    'native_readiness_timeout',
    'owned_backend_missing',
    'owned_backend_not_settled',
    'owned_backend_removal_failed',
    'owned_command_failed',
    'owned_network_id_required',
    'owned_operation_deadline',
    'owned_private_network_mismatch',
    'owned_service_terminated',
    'owned_start_deadline_required',
    'owned_systemd_restart_warm_failed',
    'owned_tmp_inventory_bound',
    'owned_warm_receipt_missing',
    'pin_mismatch',
    'registered_runtime_root_mismatch',
    'registered_storage_guard_failed',
    'registered_storage_verification_failed',
    'reset_owned_backend_before_start',
    'root_disk_guard_failed',
    'root_required',
    'runtime_image_binding_mismatch',
    'runtime_source_changed',
    'runtime_source_closure_mismatch',
    'runtime_source_digest_invalid',
    'state_identity_mismatch',
    'systemd_invocation_required',
    'telemetry_died_during_load',
    'telemetry_failed',
    'telemetry_start_failed',
    'tmp_owner_mismatch',
    'tmp_parent_identity_changed',
    'unprotected_native_parent',
    'unprotected_tmp_parent',
    'unrecorded_backend_container',
    'unsafe_native_workdir',
    'unsafe_owned_tmp_entry',
    'unsafe_owned_tmpdir',
})
ATTEMPT = None
START_ADMISSION_SECONDS = 2.0


def failure_code(error):
    candidate = error.args[0] if error.args else None
    if type(candidate) is str and candidate in SAFE_FAILURE_CODES:
        return candidate
    if isinstance(error, subprocess.TimeoutExpired):
        return 'owned_command_timeout'
    if isinstance(error, LeaseError):
        return 'canonical_lease_refused'
    if isinstance(error, (StorageError, storage_io.StorageIOError)):
        return 'registered_storage_refused'
    return 'owned_backend_failed'


def attempt_phase(phase):
    if ATTEMPT is not None:
        ATTEMPT.phase = phase


def attempt_failure(error):
    # Capture before settlement so a cleanup error cannot replace the trigger.
    if ATTEMPT is not None and ATTEMPT.failure is None:
        ATTEMPT.failure = (ATTEMPT.phase, failure_code(error))


def archive_failure_fields(state):
    """Keep legacy evidence in protected state, never project it as current.

    New per-attempt receipts retain subsequent failures independently. This
    bounded set of legacy fields is not copied to diagnostics or the journal.
    """
    fields = ('failure_type', 'failure_code', 'native_failure', 'recovery_failure')
    previous = {key: state.pop(key) for key in fields if key in state}
    if previous and 'historical_failure' not in state:
        # Freeze the first legacy snapshot: merging a later failure would
        # misattribute older fields to the later run. New receipts carry history.
        state['historical_failure'] = {**previous, 'run_id': state.get('run_id')}


def persist_attempt(record):
    """Unique immutable receipt; no shared lifecycle state or second lock.

    Exclusive creation needs no lifecycle lease (including on LeaseBusy).
    Never fall back to an unregistered/root path when the guards refuse.
    """
    binding = RegisteredStorageBinding.load(StorageRunner())
    logs = binding.path('logs')
    binding.validate_path('logs', logs)
    guard = binding.storage.root_payload_guard
    guard(binding.registry)
    try:
        with binding.mounted_guard(storage_io) as mounted:
            with storage_io.AnchoredRoot(logs, mounted) as anchored:
                anchored.mkdir('image-runtime-attempts', mode=0o700)
                relative = 'image-runtime-attempts/' + record['attempt_id'] + '.json'
                encoded = (json.dumps(record, sort_keys=True) + '\n').encode()
                require(len(encoded) <= 2048, 'attempt_record_too_large')
                with anchored.open(relative, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600) as output:
                    output.write(encoded)
                    output.fsync()
                    os.fsync(output.parent)
                    output.check()
                anchored.check()
    finally:
        guard(binding.registry)


class Attempt:
    def __init__(self, action):
        self.action = action
        self.phase = 'construct'
        self.failure = None
        self.identity = uuid.uuid4().hex
        self.started = now()
        invocation = os.environ.get('INVOCATION_ID', '')
        self.invocation = invocation if re.fullmatch('[0-9a-f]{32}', invocation) else None
        try:
            boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
        except OSError:
            boot = ''
        self.boot = boot if re.fullmatch('[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', boot) else None

    def finish(self, error=None):
        original = self.failure or (self.phase, failure_code(error) if error else 'ok')
        record = {'schema_version': 1, 'attempt_id': self.identity,
                  'action': self.action, 'phase': original[0], 'code': original[1],
                  'status': 'failed' if error else 'succeeded',
                  'boot_id': self.boot, 'invocation_id': self.invocation,
                  'started_utc': self.started, 'finished_utc': now(),
                  'settlement_code': failure_code(error) if self.failure and error else None}
        self.emit(record, 'pending', error)
        storage_status = 'verified'
        try:
            persist_attempt(record)
        except Exception:
            # Even a guard refusal gets this small safe journal record. It is
            # explicitly NOT a protected-storage success or a recovery retry.
            storage_status = 'unavailable'
        self.emit(record, storage_status, error)

    @staticmethod
    def emit(record, storage_status, error):
        safe = json.dumps({**record, 'storage_status': storage_status}, sort_keys=True)
        try:
            print(safe, file=sys.stderr, flush=True)
        except (OSError, ValueError):
            pass
        # The fixed sudo helper's caller discards stderr. Authpriv preserves only
        # this same enumerated record, never native/sudo output or a traceback.
        try:
            syslog.openlog('llm-image-attempt', syslog.LOG_PID, syslog.LOG_AUTHPRIV)
            syslog.syslog(syslog.LOG_ERR if error or storage_status == 'unavailable' else syslog.LOG_INFO, safe)
        except Exception:
            pass


@contextlib.contextmanager
def start_admission():
    """Only retry entry contention, before any backend mutation (max 2s).

    The yielded body's exceptions are outside the retry loop. A systemd child
    must never be launched with a parent holding this canonical lease.
    """
    deadline = time.monotonic() + START_ADMISSION_SECONDS
    with contextlib.ExitStack() as stack:
        while True:
            try:
                lease = stack.enter_context(acquire_lease(blocking=False))
            except LeaseBusy:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise
                time.sleep(min(0.2, remaining))
                if time.monotonic() >= deadline:
                    raise
            else:
                break
        yield lease


def verify_source_closure(config):
    """Validate reviewed protected runtime/release maps without any mutation."""
    for field, root, expected in (
            ('source_sha256', BASE / 'source', RUNTIME_SOURCE_FILES),
            ('release_source_sha256', RELEASE, RELEASE_SOURCE_FILES)):
        source_hashes = config.get(field)
        require(type(source_hashes) is dict and set(source_hashes) == set(expected),
                'runtime_source_closure_mismatch')
        for name in expected:
            digest = source_hashes[name]
            require(type(digest) is str and re.fullmatch('[0-9a-f]{64}', digest),
                    'runtime_source_digest_invalid')
            require(hashlib.sha256(protected_file(root / name)).hexdigest() == digest,
                    'runtime_source_changed')


def run(argv, *, timeout=60, check=True):
    if OPERATION_DEADLINE is not None:
        timeout = min(timeout, OPERATION_DEADLINE - time.monotonic())
        require(timeout > 0, 'owned_operation_deadline')
    result = subprocess.run(argv, capture_output=True, text=True, timeout=timeout,
                            env={'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LC_ALL': 'C',
                                 'TMPDIR': str(BASE / 'tmp')})
    if check:
        require(result.returncode == 0, 'owned_command_failed')
    return result


def settle_sampler(sampler):
    """Bound the exact child; its failure must never skip backend settlement."""
    if sampler is None:
        return None
    if sampler.poll() is None:
        sampler.send_signal(signal.SIGTERM)
    try:
        return sampler.wait(timeout=5)
    except subprocess.TimeoutExpired:
        sampler.kill()
        try:
            return sampler.wait(timeout=2)
        except subprocess.TimeoutExpired:
            return 'sampler_unsettled'


class Runtime:
    def __init__(self):
        require(os.geteuid() == 0, 'root_required')
        self.binding = RegisteredStorageBinding.load(StorageRunner())
        require(self.binding.path('services', 'image21-runtime-20260923') == str(BASE),
                'registered_runtime_root_mismatch')
        self.binding.validate_path('services', str(BASE))
        self.binding.validate_path('services', str(RELEASE))
        self.config = self.binding.read_json('services', str(BASE / 'config.json'))
        require(self.config['schema_version'] == 1 and self.config['owner'] == OWNER,
                'config_identity_mismatch')
        require(re.fullmatch('sha256:[0-9a-f]{64}', self.config['image_id']), 'image_digest_required')
        require(self.config['image_id'] == load_runtime_binding()['image']['image_id'],
                'runtime_image_binding_mismatch')
        require(re.fullmatch('[0-9a-f]{64}', self.config['network_id']), 'owned_network_id_required')
        require(self.config['source_commit'] == SOURCE_SHA and
                self.config['checkpoint_revision'] == CHECKPOINT_REV, 'pin_mismatch')
        self.model = self.binding.path('models', 'qwen-image-2.1-' + CHECKPOINT_REV)
        require(self.config['checkpoint_path'] == self.model, 'checkpoint_path_mismatch')
        checkpoint = self.binding.read_json('models', self.model + '/CHECKPOINT-RECEIPT.json')
        require(checkpoint['status'] == 'COMPLETE_VERIFIED' and checkpoint['revision'] == CHECKPOINT_REV
                and checkpoint['file_count'] == 26 and checkpoint['total_bytes'] == 33131614782,
                'checkpoint_receipt_incomplete')
        require(hashlib.sha256(protected_file(Path(self.model) / 'CHECKPOINT-RECEIPT.json')).hexdigest()
                == self.config['checkpoint_receipt_sha256'], 'checkpoint_receipt_changed')
        verify_source_closure(self.config)

    def require_hardware(self):
        lease = getattr(self, 'lease', None)
        store = RegisteredLatchStore(self.binding, lease=lease, storage_io=storage_io)
        HardwarePolicy(store, lease=lease,
                       run=lambda argv, timeout: run(argv, timeout=timeout).stdout).require_start([GPU_UUID])

    def guards(self):
        for extra in ([], ['--root-guard']):
            result = run(['/usr/bin/python3', '-I', '-B', str(RELEASE / 'scripts/common/registered-storage.py'),
                          '--json', *extra], check=False)
            require(result.returncode == 0,
                    'root_disk_guard_failed' if extra else 'registered_storage_guard_failed')
        self.binding.verify()

    @contextlib.contextmanager
    def anchor(self):
        with self.binding.mounted_guard(storage_io) as guard:
            with storage_io.AnchoredRoot(str(BASE), guard) as anchored:
                yield anchored

    def state(self):
        if not (BASE / 'state.json').exists():
            return {'schema_version': 1, 'owner': OWNER, 'phase': 'absent', 'container': None}
        value = self.binding.read_json('services', str(BASE / 'state.json'))
        require(value['schema_version'] == 1 and value['owner'] == OWNER, 'state_identity_mismatch')
        return value

    def save(self, value):
        value['updated_utc'] = now()
        with self.anchor() as anchored:
            anchored.atomic_json('state.json', value)

    def inspect_owned(self, state, *, missing_ok=False):
        identity = state.get('container')
        if not identity:
            result = run(['docker', 'inspect', NAME], check=False)
            require(result.returncode != 0, 'unrecorded_backend_container')
            return None
        require(re.fullmatch('[0-9a-f]{64}', identity['id']), 'invalid_owned_container_id')
        result = run(['docker', 'inspect', identity['id']], check=False)
        if result.returncode:
            require(missing_ok, 'owned_backend_missing')
            require(run(['docker', 'inspect', NAME], check=False).returncode != 0,
                    'conflicting_backend_name')
            return None
        value = json.loads(result.stdout)[0]
        return validate_image_container(value, state, self.config)

    def reset_owned(self):
        attempt_phase('reset_preflight')
        self.guards()
        state = self.state()
        value = self.inspect_owned(state, missing_ok=True)
        if value:
            attempt_phase('reset_container')
            if value['State']['Running']:
                run(['docker', 'stop', '--time', '30', value['Id']], timeout=45)
            value = self.inspect_owned(state)
            require(not value['State']['Running'], 'owned_backend_not_settled')
            run(['docker', 'rm', value['Id']])
            require(run(['docker', 'inspect', value['Id']], check=False).returncode != 0,
                    'owned_backend_removal_failed')
        attempt_phase('reset_state')
        if state.get('run_id'):
            state['last_tmp_cleanup'] = self.cleanup_tmp(state['run_id'])
        state.update(phase='stopped', container=None, warm=False)
        self.save(state)
        self.guards()

    def tmp_snapshot(self, run_id):
        require(re.fullmatch('[0-9a-f]{32}', run_id), 'invalid_tmp_owner')
        path = BASE / 'work/tmp' / run_id
        if not path.exists():
            return {'path': str(path), 'exists': False, 'entries': []}
        require(not path.is_symlink() and path.is_dir(), 'unsafe_owned_tmpdir')
        entries = []
        for current, dirs, files in os.walk(path, followlinks=False):
            for name in sorted(dirs + files):
                item = Path(current) / name
                info = item.lstat()
                require(not stat.S_ISLNK(info.st_mode) and info.st_dev == BASE.stat().st_dev,
                        'unsafe_owned_tmp_entry')
                entries.append({'path': str(item.relative_to(path)), 'bytes': info.st_size,
                                'directory': stat.S_ISDIR(info.st_mode), 'uid': info.st_uid})
                require(len(entries) <= 1000, 'owned_tmp_inventory_bound')
        return {'path': str(path), 'exists': True, 'entries': entries}

    def cleanup_tmp(self, run_id):
        """Only after exact backend removal; never traverse another invocation."""
        snapshot = self.tmp_snapshot(run_id)
        if not snapshot['exists']:
            return snapshot
        require(shutil.rmtree.avoids_symlink_attacks, 'anchored_rmtree_required')
        with self.anchor() as anchored:
            parent = BASE / 'work/tmp'
            info = parent.lstat()
            require(stat.S_ISDIR(info.st_mode) and info.st_uid == 0 and not info.st_mode & 0o022,
                    'unprotected_tmp_parent')
            fd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                require((os.fstat(fd).st_dev, os.fstat(fd).st_ino) == (info.st_dev, info.st_ino),
                        'tmp_parent_identity_changed')
                child = os.stat(run_id, dir_fd=fd, follow_symlinks=False)
                require(stat.S_ISDIR(child.st_mode) and child.st_uid == NATIVE_UID
                        and child.st_dev == info.st_dev, 'tmp_owner_mismatch')
                anchored.check()
                shutil.rmtree(run_id, dir_fd=fd)
                os.fsync(fd)
                anchored.check()
            finally:
                os.close(fd)
        return {**snapshot, 'removed_exact_owned_invocation': True}

    def current_device(self):
        # Select the dedicated UUID before querying: unrelated missing/faulted
        # cards must not become an image admission prerequisite. A shared driver
        # failure can still fail this read; no GPU/driver isolation is claimed.
        data = run(['nvidia-smi', '--id=' + GPU_UUID,
                    '--query-gpu=uuid,memory.total,memory.free',
                    '--format=csv,noheader,nounits'], timeout=5).stdout
        require(isinstance(data, str) and len(data) <= 4096, 'ada_memory_unavailable')
        rows = [tuple(part.strip() for part in line.split(','))
                for line in data.splitlines() if line.strip()]
        require(len(rows) == 1 and len(rows[0]) == 3 and rows[0][0] == GPU_UUID,
                'ada_identity_missing')
        require(all(value.isascii() and value.isdigit() for value in rows[0][1:]),
                'ada_memory_unavailable')
        total, free = (int(value) * 1024**2 for value in rows[0][1:])
        require(total > 0 and 0 <= free <= total, 'ada_memory_unavailable')
        return {'uuid': GPU_UUID, 'total_bytes': total, 'free_bytes': free}

    def host_headroom(self):
        values = {}
        for line in Path('/proc/meminfo').read_text().splitlines():
            field, value = line.split(':', 1)
            if field in {'MemTotal', 'MemAvailable', 'SwapTotal', 'SwapFree'}:
                values[field] = int(value.split()[0]) * 1024
        require(values['MemAvailable'] * 100 >= values['MemTotal'] * 15,
                'host_headroom_below_15_percent')
        return values

    def check_ports(self):
        # Only 30007 is published in the host namespace. Scheduler/store ports
        # remain inside the exact owned bridge network verified at start/reuse.
        # Host 30008 belongs to the independent node observer/management service.
        output = run(['ss', '-H', '-ltn']).stdout
        for line in output.splitlines():
            fields = line.split()
            if len(fields) >= 4:
                require(fields[3].rsplit(':', 1)[-1] != '30007',
                        'native_port_already_owned')

    def require_ada_idle(self):
        output = run(['nvidia-smi', '--id=' + GPU_UUID, '--query-compute-apps=gpu_uuid,pid',
                      '--format=csv,noheader,nounits'], timeout=5).stdout
        require(isinstance(output, str) and len(output) <= 65536, 'ada_process_inventory_invalid')
        rows = [tuple(value.strip() for value in line.split(','))
                for line in output.splitlines() if line.strip()]
        require(all(len(row) == 2 and row[0] == GPU_UUID and row[1].isascii()
                    and row[1].isdigit() and int(row[1]) > 0 for row in rows),
                'ada_process_inventory_invalid')
        require(len({row[1] for row in rows}) == len(rows), 'ada_process_inventory_invalid')
        require(not rows, 'ada_compute_process_already_present')

    def check_network(self, state):
        network = json.loads(run(['docker', 'network', 'inspect', self.config['network_id']]).stdout)[0]
        allowed = {state['container']['id']} if state.get('container') else set()
        require(network['Id'] == self.config['network_id'] and network['Name'] == NETWORK
                and network['Driver'] == 'bridge' and network['Internal'] is False
                and network['Scope'] == 'local' and network.get('Ingress') is False
                and (network.get('Labels') or {}).get('io.llm-image.owner') == OWNER
                and set(network.get('Containers') or {}).issubset(allowed),
                'owned_private_network_mismatch')

    def make_work(self, run_id):
        require(re.fullmatch('[0-9a-f]{32}', run_id), 'invalid_invocation')
        # Parent is protected and fixed. Only native data/cache descendants are user-owned.
        with self.anchor() as anchored:
            for relative in ('work', 'work/evidence', 'work/tmp'):
                path = BASE / relative
                anchored.mkdir(relative, mode=0o755)
                fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
                try:
                    meta = os.fstat(fd)
                    require(stat.S_ISDIR(meta.st_mode) and meta.st_uid == 0 and
                            not meta.st_mode & 0o022 and meta.st_dev == BASE.stat().st_dev,
                            'unprotected_native_parent')
                    # mkdir(mode) is filtered by systemd UMask=0077. Set only
                    # these fixed protected parents traversable for native UID.
                    os.fchmod(fd, 0o755)
                    os.fsync(fd)
                    anchored.check()
                finally:
                    os.close(fd)
            for relative in ('work/cache', 'work/tmp/' + run_id, 'work/evidence/' + run_id):
                path = BASE / relative
                if path.exists():
                    require(path.is_dir() and not path.is_symlink(), 'unsafe_native_workdir')
                else:
                    path.mkdir(mode=0o700)
                os.chown(path, NATIVE_UID, NATIVE_GID)
            anchored.check()

    def create_argv(self, run_id):
        env = {
            'CUDA_VISIBLE_DEVICES': GPU_UUID, 'NVIDIA_VISIBLE_DEVICES': GPU_UUID,
            'CUDA_DEVICE_ORDER': 'PCI_BUS_ID', 'SGLANG_CACHE_DIT_ENABLED': 'false',
            'HF_HUB_OFFLINE': '1', 'TRANSFORMERS_OFFLINE': '1',
            'HF_HOME': '/work/cache/hf', 'HF_HUB_CACHE': '/work/cache/hf/hub',
            'HOME': '/work/cache', 'XDG_CACHE_HOME': '/work/cache',
            'FLASHINFER_WORKSPACE_BASE': '/work/cache', 'TMPDIR': '/work/tmp/' + run_id,
            'TORCH_HOME': '/work/cache/torch', 'TORCH_EXTENSIONS_DIR': '/work/cache/extensions',
            'TORCHINDUCTOR_CACHE_DIR': '/work/cache/inductor',
            'TRITON_CACHE_DIR': '/work/cache/triton', 'CUDA_CACHE_PATH': '/work/cache/cuda',
            'SGLANG_DIFFUSION_CACHE_ROOT': '/work/cache/sglang',
            'SGLANG_DIFFUSION_CONFIG_ROOT': '/work/cache/sglang-config',
            'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONUNBUFFERED': '1',
        }
        argv = ['docker', 'create', '--name', NAME, '--label', 'io.llm-image.owner=' + OWNER,
                '--label', 'io.llm-image.invocation=' + run_id, '--label', 'io.llm-image.gpu=' + GPU_UUID,
                '--gpus', 'device=' + GPU_UUID, '--network', NETWORK,
                '--publish', '127.0.0.1:30007:30007/tcp', '--user', '1000:1001',
                '--cpuset-cpus', '8-15', '--cpuset-mems', '0', '--memory', '96g',
                '--memory-swap', '96g', '--pids-limit', '1024', '--shm-size', '1g',
                '--restart', 'no', '--log-driver', 'none', '--read-only',
                '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
                '--mount', 'type=bind,src=' + self.model + ',dst=/models,readonly',
                '--mount', 'type=bind,src=' + str(BASE / 'source') + ',dst=/runtime,readonly',
                '--mount', 'type=bind,src=' + str(BASE / 'work') + ',dst=/work',
                '--mount', 'type=bind,src=' + str(BASE / 'work/tmp' / run_id) + ',dst=/tmp']
        for key, value in env.items():
            argv.extend(['--env', key + '=' + value])
        return [*argv, '--entrypoint', '/opt/image-venv/bin/python', self.config['image_id'],
                '-I', '-B', '/runtime/native_server.py', run_id]

    def native_health(self):
        try:
            with urllib.request.urlopen('http://127.0.0.1:30007/health', timeout=2) as response:
                return response.status == 200
        except (OSError, urllib.error.URLError):
            return False

    def verify_resident(self, state):
        value = self.inspect_owned(state)
        require(value['State']['Running'] and not value['State']['OOMKilled'], 'native_backend_not_running')
        self.check_network(state)
        attached = value['NetworkSettings']['Networks']
        require(set(attached) == {NETWORK} and attached[NETWORK]['NetworkID'] == self.config['network_id'],
                'native_network_attachment_mismatch')
        require(self.native_health(), 'native_backend_unready')
        pids = {int(line.split()[0]) for line in run(['docker', 'top', value['Id'], '-eo', 'pid']).stdout.splitlines()[1:]}
        output = run(['nvidia-smi', '--id=' + GPU_UUID,
                      '--query-compute-apps=gpu_uuid,pid,used_memory',
                      '--format=csv,noheader,nounits'], timeout=5).stdout
        require(isinstance(output, str) and len(output) <= 65536, 'ada_process_inventory_invalid')
        ada = [tuple(part.strip() for part in line.split(','))
               for line in output.splitlines() if line.strip()]
        require(ada and all(len(row) == 3 and row[0] == GPU_UUID and row[1].isascii()
                            and row[1].isdigit() and int(row[1]) > 0
                            and row[2].isascii() and row[2].isdigit() for row in ada)
                and len({row[1] for row in ada}) == len(ada), 'ada_process_inventory_invalid')
        require(all(int(row[1]) in pids for row in ada), 'ada_process_ownership_mismatch')
        # Exact protected DeviceRequests, CUDA/NVIDIA visible-device settings,
        # absence of privileged/device bypass, and target process ownership prove
        # this container's assignment. No unassigned/peer GPU query is needed.
        device = self.current_device()
        require(device['free_bytes'] * 20 >= device['total_bytes'], 'ada_current_margin_below_5_percent')
        return {'container_id': value['Id'], 'started_at': value['State']['StartedAt'],
                'gpu_processes': ada, 'device_current': device, 'host_current': self.host_headroom()}

    def start(self):
        global OPERATION_DEADLINE
        attempt_phase('start_preflight')
        run_id = os.environ.get('INVOCATION_ID', '')
        require(re.fullmatch('[0-9a-f]{32}', run_id), 'systemd_invocation_required')
        deadline = OPERATION_DEADLINE
        require(deadline is not None, 'owned_start_deadline_required')
        self.guards()
        attempt_phase('hardware_preflight')
        self.require_hardware()
        attempt_phase('backend_preflight')
        state = self.state()
        require(self.inspect_owned(state, missing_ok=True) is None, 'reset_owned_backend_before_start')
        self.check_network(state)
        self.check_ports()
        self.require_ada_idle()
        self.host_headroom()
        device = self.current_device()
        require(device['free_bytes'] * 20 >= device['total_bytes'], 'ada_initial_margin_below_5_percent')
        attempt_phase('prepare_work')
        self.make_work(run_id)
        archive_failure_fields(state)
        state.update(run_id=run_id, phase='creating', warm=False, container=None, start_utc=now())
        self.save(state)
        attempt_phase('container_create')
        cid = run(self.create_argv(run_id), timeout=60).stdout.strip()
        require(re.fullmatch('[0-9a-f]{64}', cid), 'invalid_created_container_id')
        state.update(phase='loading', container={'id': cid, 'image_id': self.config['image_id']})
        self.save(state)
        self.inspect_owned(state)
        attempt_phase('telemetry_start')
        telemetry_rel = 'receipts/' + run_id + '-telemetry.jsonl'
        sampler = None
        try:
            with self.anchor() as anchored:
                with anchored.open(telemetry_rel, os.O_WRONLY | os.O_CREAT | os.O_EXCL) as output:
                    sampler = subprocess.Popen(['/usr/bin/python3', '-I', '-B', str(BASE / 'source/telemetry.py'),
                                                '--output-fd', str(output.fileno()), '--output-path', str(BASE / telemetry_rel),
                                                '--cgroup', '/sys/fs/cgroup/system.slice/docker-' + cid + '.scope'],
                                               pass_fds=(output.fileno(),), stdout=subprocess.DEVNULL,
                                               stderr=subprocess.DEVNULL)
                    try:
                        time.sleep(0.4)
                        require(sampler.poll() is None, 'telemetry_start_failed')
                        self.guards()
                        self.require_hardware()
                        self.require_ada_idle()
                        require(self.current_device()['free_bytes'] >= 33131614782 + device['total_bytes'] // 20,
                                'ada_preload_weight_and_margin_unavailable')
                        load_start = time.monotonic()
                        attempt_phase('container_start')
                        run(['docker', 'start', cid])
                        attempt_phase('native_readiness')
                        while not self.native_health():
                            require(time.monotonic() < deadline - 5, 'native_readiness_timeout')
                            require(self.inspect_owned(state)['State']['Running'], 'native_exited_during_load')
                            require(sampler.poll() is None, 'telemetry_died_during_load')
                            self.host_headroom()
                            time.sleep(2)
                        state.update(phase='warming', native_ready_seconds=time.monotonic() - load_start)
                        state['tmp_before_generation'] = self.tmp_snapshot(run_id)
                        self.save(state)
                        self.guards()
                        attempt_phase('warm_generation')
                        result = run(['docker', 'exec', cid, '/opt/image-venv/bin/python', '-I', '-B',
                                      '/runtime/native_request.py', '--mode', 'generation', '--run-id', run_id],
                                     timeout=max(1, deadline - time.monotonic()))
                        summary = json.loads(result.stdout)
                        require(summary['status'] == 'pass', 'deterministic_warm_failed')
                        attempt_phase('residency_verify')
                        residency = self.verify_resident(state)
                        state['tmp_after_generation'] = self.tmp_snapshot(run_id)
                        before_names = {item['path'] for item in state['tmp_before_generation']['entries']}
                        state['tmp_new_entries_after_generation'] = [item for item in state['tmp_after_generation']['entries']
                                                                      if item['path'] not in before_names]
                    except BaseException as error:
                        attempt_failure(error)
                        raise
                    finally:
                        sampler_result = settle_sampler(sampler)
                        output.fsync()
                    require(sampler_result == 0, 'telemetry_failed')
                    anchored.check()
            attempt_phase('telemetry_verify')
            samples = [json.loads(line) for line in (BASE / telemetry_rel).read_text().splitlines()]
            end = samples[-1]
            require(end['sampled_min_free_bytes'] is not None and
                    end['sampled_min_free_bytes'] * 20 >= device['total_bytes'],
                    'ada_sampled_peak_margin_below_5_percent')
            hosts = [sample['host']['meminfo_bytes']['value']['values'] for sample in samples
                     if sample.get('host', {}).get('meminfo_bytes', {}).get('status') == 'ok']
            require(hosts and all(value['MemAvailable'] * 100 >= value['MemTotal'] * 15 for value in hosts),
                    'host_sampled_margin_below_15_percent')
            swaps = [sample['host']['cgroup_bytes']['memory.swap.current']['value'] for sample in samples
                     if sample.get('host', {}).get('cgroup_bytes', {}).get('memory.swap.current', {}).get('status') == 'ok']
            require(swaps and max(swaps) == 0, 'native_cgroup_swap_observed_or_unavailable')
            archive_failure_fields(state)
            state.update(phase='warm', warm=True, generation=summary, residency=residency,
                         telemetry_path=str(BASE / telemetry_rel), telemetry_summary=end, completed_utc=now())
            state['sampled_min_host_available_bytes'] = min(value['MemAvailable'] for value in hosts)
            state['sampled_max_cgroup_swap_bytes'] = max(swaps)
            self.save(state)
            self.guards()
            print(json.dumps({'status': 'warm', 'run_id': run_id, 'container_id': cid}), flush=True)
        except BaseException as error:
            attempt_failure(error)
            OPERATION_DEADLINE = SETTLEMENT_DEADLINE
            cleanup = {'sampler': settle_sampler(sampler)}
            try:
                value = self.inspect_owned(state, missing_ok=True)
                if value and value['State']['Running']:
                    run(['docker', 'stop', '--time', '30', cid], timeout=45)
                cleanup['backend_stopped'] = True
            except Exception as cleanup_error:
                cleanup['backend_stop_error'] = type(cleanup_error).__name__
                try:
                    value = self.inspect_owned(state, missing_ok=True)
                    if value and value['State']['Running']:
                        run(['docker', 'kill', cid], timeout=5)
                    cleanup['backend_forced_settle'] = True
                except Exception as final_error:
                    cleanup['backend_forced_settle_error'] = type(final_error).__name__
            state.update(phase='failed', warm=False, failure_type=type(error).__name__,
                         failure_code=failure_code(error),
                         telemetry_path=str(BASE / telemetry_rel), cleanup=cleanup)
            self.save(state)
            self.guards()
            raise


def recover():
    global OPERATION_DEADLINE
    started = time.monotonic()
    OPERATION_DEADLINE = started + 840
    attempt_phase('construct')
    runtime = Runtime()
    attempt_phase('recover_admission')
    # Do not hold a lease while a separately invoked systemd ExecStart borrows it.
    # Every subprocess lifecycle owner independently takes the SAME canonical lease.
    # A latched recovery attempt must not stop a healthy peer or existing work.
    # Gate outside cleanup: failure before mutation must cause no stop/reset.
    try:
        with acquire_lease(blocking=False) as lease:
            runtime.lease = lease
            runtime.guards()
            runtime.require_hardware()
    except BaseException:
        OPERATION_DEADLINE = None
        raise
    mutation_started = False
    attempt_phase('recover_mutation_admission')
    try:
        with acquire_lease(blocking=False) as lease:
            runtime.lease = lease
            runtime.guards()
            runtime.require_hardware()
            mutation_started = True
            runtime.reset_owned()
        attempt_phase('systemd_restart')
        result = run(['systemctl', 'restart', UNIT], timeout=840, check=False)
        require(result.returncode == 0, 'owned_systemd_restart_warm_failed')
        attempt_phase('recover_verify')
        with acquire_lease(blocking=False):
            runtime.guards()
            state = runtime.state()
            require(state['phase'] == 'warm' and state['warm'] is True, 'owned_warm_receipt_missing')
            runtime.verify_resident(state)
            runtime.guards()
        print(json.dumps({'status': 'warm', 'run_id': state['run_id']}), flush=True)
    except BaseException as error:
        attempt_failure(error)
        # A second-lease contention or changed guard/latch can refuse after the
        # initial preflight. No reset/restart was dispatched, so cleanup must
        # not stop work belonging to the intervening owner.
        if not mutation_started:
            raise
        # Stop/cancel the exact systemd job as well as its Docker workload.
        # Killing only the systemctl or docker-exec client is not cancellation.
        OPERATION_DEADLINE = started + 900
        try:
            run(['systemctl', 'stop', UNIT], timeout=40, check=False)
        except (subprocess.TimeoutExpired, RuntimeError):
            run(['systemctl', 'kill', '--kill-whom=all', '--signal=KILL', UNIT], timeout=5, check=False)
        with acquire_lease(blocking=False):
            runtime.guards()
            failed = runtime.state()
            value = runtime.inspect_owned(failed, missing_ok=True)
            if value and value['State']['Running']:
                run(['docker', 'kill', value['Id']], timeout=5)
            failed.update(phase='failed', warm=False, recovery_failure='reset_warm_failed_no_retry')
            runtime.save(failed)
            runtime.guards()
        raise
    finally:
        OPERATION_DEADLINE = None


def main():
    global OPERATION_DEADLINE, SETTLEMENT_DEADLINE
    require(len(sys.argv) == 2 and sys.argv[1] in {'start', 'stop', 'recover'}, 'invalid_fixed_action')
    if sys.argv[1] == 'recover':
        recover()
        return
    started = time.monotonic()
    OPERATION_DEADLINE = started + (775 if sys.argv[1] == 'start' else 100)
    SETTLEMENT_DEADLINE = started + (835 if sys.argv[1] == 'start' else 115)
    runtime = Runtime()
    attempt_phase('start_admission' if sys.argv[1] == 'start' else 'stop_admission')
    with (start_admission() if sys.argv[1] == 'start' else acquire_lease(blocking=False)) as lease:
        runtime.lease = lease
        if sys.argv[1] == 'start':
            attempt_phase('admitted_guards')
            runtime.guards()
            runtime.start()
        else:
            runtime.reset_owned()


def entrypoint():
    global ATTEMPT
    action = sys.argv[1] if len(sys.argv) == 2 and sys.argv[1] in {'start', 'stop', 'recover'} else 'invalid'
    ATTEMPT = Attempt(action)
    try:
        main()
    except Exception as error:
        ATTEMPT.finish(error)
        return 1
    else:
        ATTEMPT.finish()
        return 0
    finally:
        ATTEMPT = None


if __name__ == '__main__':
    def interrupted(_signum, _frame):
        raise RuntimeError('owned_service_terminated')
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    raise SystemExit(entrypoint())
