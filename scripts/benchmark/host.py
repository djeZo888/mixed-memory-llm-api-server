"""Concrete Linux BENCHRUN adapter. Import is inert; explicit CLI dispatch only.

Production Manager and lease imports must resolve to the pinned protected install.
Raw keys and logs never enter JSON-line replies. Evidence writes use installed
registered mounted guards and AnchoredRoot; no host-root or path override.
"""
from __future__ import annotations

import base64
import copy
import contextvars
import hashlib
import json
import math
import os
from pathlib import Path
import re
import secrets
import stat
import subprocess
import threading
import time
from types import SimpleNamespace
import urllib.error
import urllib.request

from .lifecycle import CONTROL_UNIT, BOOT_UNIT, PlanError, digest, require, validate_restored
from .owner import CampaignOwner, HostCallbacks, WorkerVerificationPending
from .campaign import CampaignBudget
from .profiles import (read_config, command_manifest, split_resources, validate_arm_scope,
                       G1_RAM_CAP_BYTES, glmrepair_manifest, cpu_set)
from .telemetry import collect_sample, required_host_demand
from .allocation import allocation_gate, parse_glm_log, parse_qwen_log

INSTALL = Path('/usr/local/lib/llm-server/control-api')
KEYS = {'inference': Path('/data/services/secrets/llm-api-key'), 'control': Path('/etc/llm-server/control-api-key')}
ENV = {'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LC_ALL': 'C'}
CID = re.compile(r'[a-f0-9]{64}\Z')
_COMMAND_DEADLINE = contextvars.ContextVar('benchmark_command_deadline', default=None)


class NativeInfoPending(Exception):
    """Only a startup timeout from Qwen's native-info GET; not proof acceptance."""


def command(argv, timeout=30, *, allow_missing=False):
    deadline = _COMMAND_DEADLINE.get()
    if deadline is not None:
        remaining = deadline - time.monotonic()
        require(remaining > 0, 'host_operation_deadline')
        timeout = min(timeout, remaining)
    result = subprocess.run(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, timeout=timeout, env=ENV, check=False)
    if result.returncode and not allow_missing:
        raise ValueError('host_command_failed')
    return result


def protected(path, *, private=False, maximum=16 * 1024 * 1024):
    """Protected ancestry, no symlinks, stable regular FD; never return key text."""
    path = Path(path)
    require(path.is_absolute() and '..' not in path.parts, 'unsafe_protected_path')
    for parent in reversed((path.parent, *path.parents[1:])):
        info = parent.lstat()
        require(stat.S_ISDIR(info.st_mode) and info.st_uid == 0 and not info.st_mode & 0o022,
                'unprotected_ancestry')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_uid == 0 and before.st_nlink == 1
                and not before.st_mode & (0o077 if private else 0o022) and before.st_size <= maximum,
                'unprotected_file')
        raw = b''
        while len(raw) <= maximum:
            block = os.read(fd, min(1024 * 1024, maximum + 1 - len(raw)))
            if not block:
                break
            raw += block
        after, named = os.fstat(fd), path.lstat()
        signature = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
        require(len(raw) <= maximum and signature(before) == signature(after) == signature(named),
                'protected_file_changed')
        metadata = {k: getattr(after, 'st_' + attr) for k, attr in
                    [('uid', 'uid'), ('gid', 'gid'), ('dev', 'dev'), ('ino', 'ino'), ('size', 'size'),
                     ('mtime_ns', 'mtime_ns'), ('ctime_ns', 'ctime_ns')]}
        metadata['mode'] = stat.S_IMODE(after.st_mode)
        return raw, metadata
    finally:
        os.close(fd)


def http_json(port, route, payload=None, timeout_s=30, *, control=False):
    allowed = (30000,) if control else (30002, 30004, 31002, 31004)
    require(port in allowed and isinstance(route, str) and route.startswith('/') and
            not route.startswith('//') and '\n' not in route and timeout_s <= 7200, 'unsafe_http_route')
    deadline = _COMMAND_DEADLINE.get()
    if deadline is not None:
        require(deadline > time.monotonic(), 'host_operation_deadline')
        timeout_s = min(timeout_s, deadline - time.monotonic())
    key, _ = protected(KEYS['control' if control else 'inference'], private=True, maximum=4096)
    token = key.decode().strip()
    require(token and not any(c.isspace() for c in token), 'invalid_protected_key')
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(f'http://127.0.0.1:{port}{route}', data=data,
          headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
    # No proxy environment; never log Request, headers or urllib exceptions.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(req, timeout=timeout_s) as reply:
        raw = reply.read(32 * 1024 * 1024 + 1)
        require(len(raw) <= 32 * 1024 * 1024 and token.encode() not in raw, 'http_response_invalid')
        return json.loads(raw)


class HostBudget(CampaignBudget):
    def __init__(self, host):
        self._mutex = threading.RLock()
        self.host, self.path, self.clock = host, Path(host.log_root) / 'budget.json', time.time
        self.budget_seconds = (1200 if getattr(host, 'campaign', None) == 'benchrun-glmrepair-g1fix-20260919' else 2700 if getattr(host, 'campaign', None) == 'benchrun-glmrepair-fix-20260919' else 3600) if getattr(host, 'scope', None) == 'glmrepair' else 21600
        self._data = host.read_json('budget.json', missing=True)
        if self._data is not None:
            self._validate()

    def _validate(self):
        super()._validate()
        if getattr(self.host, 'scope', None) == 'glmrepair':
            require(self._data.get('start_epoch') == self.host.start_epoch == self._data['started_at'] and
                    self._data.get('deadline_epoch') == self.host.deadline_epoch == self.host.start_epoch + self.budget_seconds,
                    'glmrepair_immutable_clock_changed')

    def start(self, kind):
        require(self.data is None and kind in {'maintenance', 'model_trial'}, 'budget_already_started')
        now = time.time()
        start = self.host.start_epoch if self.host.start_epoch is not None else now
        require(type(start) in (int, float) and 0 < start <= now and now - start < self.budget_seconds, 'invalid_stage_start_epoch')
        self._data = {'schema': 1, 'budget_seconds': self.budget_seconds, 'phase': 'MEASURING', 'start_kind': kind,
                     'started_at': start, 'last_seen_at': now, 'restoration_started_at': None}
        if getattr(self.host, 'scope', None) == 'glmrepair':
            self._data.update(start_epoch=start, deadline_epoch=self.host.deadline_epoch)
            self._validate()
        self._save()
        return dict(self.data)

    def _save(self):
        self.host.write_json('budget.json', self.data)


class LinuxHost:
    def __init__(self, campaign, manifest_file):
        require(os.geteuid() == 0 and re.fullmatch(r'benchrun-[a-z0-9-]{1,48}', campaign), 'root_reviewed_campaign_required')
        self.config, self.campaign = read_config(), campaign
        self.pin_sources()
        from lifecycle.manager import load_manager
        from common import lifecycle_lease
        from install import storage_io
        require(Path(__import__('lifecycle.manager', fromlist=['x']).__file__).resolve() ==
                INSTALL / 'scripts/lifecycle/manager.py', 'manager_not_installed_pinned_source')
        require(Path(lifecycle_lease.__file__).resolve() == INSTALL / 'scripts/common/lifecycle_lease.py',
                'lease_not_installed_pinned_source')
        self.manager = load_manager(SimpleNamespace(instance=None), INSTALL / 'configs')
        self.binding, self.storage_io = self.manager.binding, storage_io
        self.log_root = self.binding.path('logs', campaign)
        self.binding.validate_path('services', str(manifest_file))
        raw, _ = protected(manifest_file, private=True)
        data = json.loads(raw)
        values = data.get('commands', data.get('manifests', [])) if isinstance(data, dict) else data
        self.scope = validate_arm_scope(data)
        manifest_count = {'full': 12, 'q1-only': 3, 'q1-256k': 1, 'g1-only': 3, 'glmrepair': 1}[self.scope]
        require(isinstance(values, list) and len(values) == manifest_count, 'scope_reviewed_manifests_required')
        self.start_epoch = data.get('start_epoch', data.get('runtime', {}).get('start_epoch')) if isinstance(data, dict) else None
        if self.scope == 'glmrepair':
            self.start_epoch, self.deadline_epoch = self.glmrepair_clock(data)
        elif self.scope != 'full':
            require(data.get('runtime') == data.get('continuation_execution') and self.start_epoch is not None,
                    'q1_continuation_epoch_changed')
        source_root = Path(__file__).resolve().parents[2]
        require(isinstance(data, dict) and data.get('campaign') == campaign and isinstance(data.get('source_files'), dict),
                'protected_arm_source_manifest_required')
        for relative, sha in data['source_files'].items():
            require(not Path(relative).is_absolute() and '..' not in Path(relative).parts, 'unsafe_source_manifest_path')
            source_raw, _ = protected(source_root / relative)
            require(hashlib.sha256(source_raw).hexdigest() == sha, 'staged_source_pin_changed')
        self.manifests = {}
        for value in values:
            expected = glmrepair_manifest(campaign) if self.scope == 'glmrepair' else command_manifest(value['placement'], value['configured_capacity'], campaign=campaign,
                                        ram_cap=G1_RAM_CAP_BYTES if self.scope == 'g1-only' else None,
                                        log_verbosity=4 if self.scope == 'g1-only' else None)
            require(value == expected, 'manifest_not_current_generated_source')
            self.manifests[digest(value)] = value
        require(len(self.manifests) == manifest_count, 'duplicate_reviewed_manifest')
        self.mapping_helpers_verified = False
        self.allocation_proofs = {}
        self.original_secrets = None
        self.requests, self.load_manifests, self.samples = {}, {}, {}
        self.measured = self.read_json('measured-demand.json', missing=True) or {}
        self.worker_nonce, self.restored_at = None, None
        self.baseline_lock_identity = None
        self.owner = None
        self.budget = HostBudget(self)
        callbacks = HostCallbacks(**{name: getattr(self, name) for name in HostCallbacks.__dataclass_fields__})
        self.owner = CampaignOwner(campaign, self.manager, callbacks, self.budget,
                                  reviewed_manifest_hashes=self.manifests, lease_factory=lifecycle_lease.acquire_lease)

    @staticmethod
    def glmrepair_clock(armed):
        runtime = armed.get('runtime') or {}
        start, deadline = runtime.get('start_epoch'), runtime.get('deadline_epoch')
        seconds = 1200 if armed.get('campaign') == 'benchrun-glmrepair-g1fix-20260919' else 2700 if armed.get('campaign') == 'benchrun-glmrepair-fix-20260919' else 3600
        require('continuation_execution' not in armed and 'start_epoch' not in armed and
                type(start) in (int, float) and type(deadline) in (int, float) and
                math.isfinite(start) and math.isfinite(deadline) and start > 0 and
                deadline == start + seconds and runtime.get('budget_seconds') == seconds,
                'glmrepair_new_immutable_clock_required')
        return start, deadline

    def pin_sources(self):
        for entry in self.config['installed_source_identities'].values():
            raw, metadata = protected(entry['path'])
            require(hashlib.sha256(raw).hexdigest() == entry['sha256'] and
                    metadata['mode'] == int(entry['mode'], 8), 'installed_source_identity_changed')

    def guards(self, lease):
        if lease is not None:
            lease.validate()
        self.pin_sources()
        prefix = ['/usr/bin/python3', '-I', '-B', str(INSTALL / 'scripts/common/registered-storage.py'), '--json']
        storage = json.loads(command(prefix, 120).stdout)
        root = json.loads(command(prefix + ['--root-guard'], 300).stdout)
        expected = self.config['storage']
        for role, uuid in [('data', expected['data_uuid']), ('models', expected['model_uuid'])]:
            require(storage[role]['uuid'] == uuid and storage[role]['fstype'] == expected['fstype'] and
                    storage[role]['path'] == storage[role]['mount'] == expected['data_root' if role == 'data' else 'model_root'],
                    'registered_storage_pin_changed')
        require(root.get('root_payload_scan', {}).get('status') == 'pass', 'root_guard_failed')
        return storage

    def write_json(self, suffix, value):
        require(re.fullmatch(r'[a-zA-Z0-9_.-]+(?:/[a-zA-Z0-9_.-]+)*', suffix) and '..' not in suffix.split('/'), 'unsafe_evidence_suffix')
        lease = self.owner.lease if self.owner else None
        self.guards(lease)
        self.manager.persistent_json(self.binding.path('logs', self.campaign + '/' + suffix), value)
        self.guards(lease)

    def write_bytes(self, suffix, raw):
        require(re.fullmatch(r'[a-zA-Z0-9_.-]+(?:/[a-zA-Z0-9_.-]+)*', suffix), 'unsafe_evidence_suffix')
        lease = self.owner.lease if self.owner else None
        self.guards(lease)
        with self.binding.mounted_guard(self.storage_io, roles=('data',)) as guard:
            with self.storage_io.AnchoredRoot(self.binding.path('logs'), guard) as anchor:
                relative = self.campaign + '/' + suffix
                anchor.mkdir(str(Path(relative).parent), mode=0o700, parents=True)
                with anchor.open(relative, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600) as out:
                    for offset in range(0, len(raw), 1024 * 1024):
                        out.write(raw[offset:offset + 1024 * 1024])
                    out.fsync()
                anchor.check()
        self.guards(lease)

    def read_json(self, suffix, missing=False):
        path = self.binding.path('logs', self.campaign + '/' + suffix)
        local = self.binding.validate_path('logs', path)
        if missing and not local.exists():
            return None
        return self.binding.read_json('logs', path, maximum=16 * 1024 * 1024)

    def write(self, ledger):
        self.write_json('owner.json', ledger)
        self.write_json('measured-demand.json', self.measured)

    def units(self):
        result = {}
        for name in (CONTROL_UNIT, BOOT_UNIT):
            raw = command(['/usr/bin/systemctl', 'show', name, '--property=ActiveState,SubState,UnitFileState,FragmentPath,DropInPaths,ExecStop']).stdout.decode()
            fields = dict(line.split('=', 1) for line in raw.splitlines() if '=' in line)
            require(not fields.get('DropInPaths'), 'unreviewed_unit_dropin')
            unit_raw, _ = protected(fields['FragmentPath'])
            result[name] = {'active': fields['ActiveState'], 'substate': fields['SubState'],
                'enabled': fields['UnitFileState'], 'masked': fields['UnitFileState'].startswith('masked'),
                'unit_sha256': hashlib.sha256(unit_raw).hexdigest(),
                'exec_stop_uses_lifecycle': 'boot-stop' in fields.get('ExecStop', '')}
        return result

    def jobs(self):
        raw = command(['/usr/bin/systemctl', 'list-jobs', '--no-legend', '--no-pager']).stdout.decode().strip()
        require(not raw, 'pending_systemd_jobs')
        return []

    def credentials(self):
        values, private_hashes = {}, {}
        for role, path in KEYS.items():
            raw, values[role] = protected(path, private=True, maximum=4096)
            private_hashes[role] = hashlib.sha256(raw).hexdigest()
        if self.original_secrets is None:
            witness = self.read_json('preservation-witness.json', missing=True)
            if witness is not None:
                self.original_secrets = witness['credential_sha256']
                require(witness['lease_identity'] == self.baseline_lock_identity, 'recovery_lease_inode_changed')
            else:
                self.original_secrets = private_hashes
                self.write_json('preservation-witness.json', {'credential_sha256': private_hashes,
                                'lease_identity': self.baseline_lock_identity})
        require(self.original_secrets == private_hashes, 'credential_contents_changed')
        return values

    def capture(self, lease):
        storage = self.guards(lease)
        state = self.manager.status()
        from control.adapter import ManagerJournalStore
        from control.journal import Journal
        journal = Journal(ManagerJournalStore(lambda: self.manager)).read()
        require(not any(v['status'] in {'pending', 'running'} for v in journal['entries'].values()), 'control_operation_pending')
        source_raw, _ = protected('/usr/local/lib/llm-server/control-api.manifest.json')
        registration_raw, _ = protected('/etc/local-ai-server/storage.json', private=True)
        lock = Path(self.config['lease']).lstat()
        lock_identity = [lock.st_dev, lock.st_ino]
        if self.baseline_lock_identity is None:
            self.baseline_lock_identity = lock_identity
        require(lock_identity == self.baseline_lock_identity, 'canonical_lock_inode_changed')
        return {'schema_version': 1, 'evidence_kind': 'live_readonly', 'captured_at': str(time.time()),
            'manager': {**{key: state.get(key) for key in ('selected', 'desired', 'observed', 'container_running', 'boot_policy')},
                        'state_persisted': state.get('state_persisted', True), 'recovery_pending': bool(state.get('failure'))},
            'control': {'operation': None, 'fresh': True}, 'pending_systemd_jobs': self.jobs(),
            'lease': {'path': self.config['lease'], 'held': lease is not None, 'owned_by_campaign': lease is not None},
            'services': self.units(), 'guards': {'storage_passed': True, 'root_disk_passed': True,
                'installed_path': str(INSTALL / 'scripts/common/registered-storage.py'),
                'sha256': self.config['installed_source_identities']['scripts/common/registered-storage.py']['sha256'],
                'dependency_sha256': self.config['installed_source_identities']['scripts/install/storage.py']['sha256']},
            'storage': {'authority': '/etc/local-ai-server/storage.json', 'identity_sha256': hashlib.sha256(registration_raw).hexdigest(),
                        'protected_ancestry_verified': True},
            'source': {'manager_root': str(INSTALL), 'closure_sha256': hashlib.sha256(source_raw).hexdigest(),
                       'lease_semantics': 'same_process_capability'}, 'credentials': self.credentials()}

    def assert_idle(self):
        require(not self.requests, 'healthy_request_still_registered')
        lines = command(['/usr/bin/ss', '-Htn', 'state', 'established']).stdout.decode().splitlines()
        require(not any(re.search(r':(?:30002|30004|31002|31004)\b', line) for line in lines), 'inference_connection_active')

    def gate(self, stage, lease, original, resources):
        if stage == 'restore':
            # Owner.launch also invokes this on failure; restoration is outside
            # the measurement deadline even when admission/load just expired.
            _COMMAND_DEADLINE.set(None)
        lease.validate()
        self.pin_sources()
        self.jobs()
        units = self.units()
        require(units[BOOT_UNIT] == original['services'][BOOT_UNIT], 'boot_service_drift')
        if stage not in {'admission', 'freeze_control'}:
            require(units[CONTROL_UNIT]['active'] == 'inactive', 'control_not_frozen')
        if stage in {'admission', 'production_stop', 'restore', 'retire', 'stop', 'remove', 'pre_release'}:
            self.assert_idle()
        if stage == 'control_frozen':
            self.verify_mapping_helpers(lease)
        if stage in {'production_stopped', 'launch'}:
            state = self.manager.read_state()
            container = self.manager.trusted_container(state['container']) if state.get('container') else None
            require(not self.manager.running(container), 'production_still_running')
        if stage in {'benchmarks_absent', 'pre_release'}:
            require(not self.campaign_containers(), 'benchmark_containers_remain')
            self.credentials()

    def verify_mapping_helpers(self, lease):
        """No-GPU exact-image probes before production stop; no model or key mounts.

        Included model probes are tracked in the existing owner ledger and removed by full
        ID. Failure leaves production running and the normal owner restores only
        its control service; no Python is assumed in the GLM runtime.
        """
        if self.mapping_helpers_verified:
            return
        lease.validate()
        candidates = {kind: next(m for m in self.manifests.values() if m['placement'].startswith(kind))
                      for kind in ('G', 'Q') if any(m['placement'].startswith(kind) for m in self.manifests.values())}
        for kind, manifest in candidates.items():
            name = self.campaign + '-mapping-helper-' + kind.lower()
            probe = ['/usr/bin/docker', 'create', '--name', name, '--network', 'none', '--read-only',
                     '--restart', 'no', '--log-driver', 'none', '--runtime', 'nvidia',
                     '--env', 'NVIDIA_VISIBLE_DEVICES=none', '--env', 'NVIDIA_DRIVER_CAPABILITIES=compute,utility',
                     '--label', 'benchmark.campaign=' + self.campaign, '--label', 'benchmark.owner=llm-benchmark',
                     '--pull=never', '--entrypoint', '/bin/sh', manifest['image'], '-ec']
            check = ('test -x /opt/llama/llama-server; command -v nvidia-smi >/dev/null; /opt/llama/llama-server --help'
                     if kind == 'G' else "command -v python3 >/dev/null; python3 -c 'import ctypes,json,uuid; ctypes.CDLL(\"libcuda.so.1\")'")
            self.write_json('mapping-helper-' + kind.lower() + '.json',
                            {'phase': 'PLANNED', 'name': name, 'image': manifest['image'], 'no_gpu': True})
            self.guards(lease)
            cid = command([*probe, check], 60).stdout.decode().strip()
            require(bool(CID.fullmatch(cid)), 'mapping_helper_create_identity_invalid')
            container = self.docker_inspect(cid)
            resource = self.owner._resource(self.resource(container))
            require(resource['name'] == name and resource['image_id'] in manifest['expected_image_ids'],
                    'mapping_helper_image_changed')
            row = {'resource': resource, 'state': 'CREATED'}
            self.owner.resources.append(row)
            self.owner._save()
            try:
                self.guards(lease)
                completed = command(['/usr/bin/docker', 'start', '--attach', cid], 60)
                self.guards(lease)
                observed = self._exact(resource)
                require(not observed['State']['Running'] and observed['State'].get('ExitCode') == 0,
                        'mapping_helper_unavailable')
                if kind == 'G':
                    require(b'--list-devices' in completed.stdout + completed.stderr, 'native_enumeration_helper_unavailable')
                self.write_json('mapping-helper-' + kind.lower() + '.json',
                    {'phase': 'VERIFIED', 'name': name, 'id': cid, 'image_id': resource['image_id'],
                     'no_gpu': True, 'stdout_sha256': hashlib.sha256(completed.stdout).hexdigest()})
            finally:
                # Only this exact probe may be retired here, never production.
                self.guards(lease)
                current = self._exact(resource)
                if current['State']['Running']:
                    command(['/usr/bin/docker', 'stop', '--time', '2', cid], 10)
                require(not self._exact(resource)['State']['Running'], 'mapping_helper_still_running')
                command(['/usr/bin/docker', 'rm', cid], 30)
                require(self.docker_inspect(cid) is None, 'mapping_helper_removal_failed')
                row['state'] = 'REMOVED'
                self.owner._save()
                self.guards(lease)
        self.mapping_helpers_verified = True

    def cuda_mapping(self, cid, manifest, container, timeout_s=30):
        expected = manifest['gpu_uuids']
        if manifest['placement'].startswith('G'):
            # CUDA_VISIBLE_DEVICES is an explicit UUID-ordered launch contract,
            # verified on the actual container; management indices are not used
            # to infer CUDA order. Native enumeration proves available ordinals.
            values = [v.split('=', 1)[1] for v in container['Config'].get('Env', [])
                      if v.startswith('CUDA_VISIBLE_DEVICES=')]
            require(values == [','.join(expected)], 'glm_cuda_uuid_visibility_unproved')
            native = command(['/usr/bin/docker', 'exec', cid, '/opt/llama/llama-server', '--list-devices'], timeout_s)
            ordinals = re.findall(r'^\s*CUDA(\d+):', native.stdout.decode('utf-8', 'replace'), re.M)
            require(ordinals == [str(i) for i in range(len(expected))], 'glm_native_device_enumeration_mismatch')
            visible = command(['/usr/bin/docker', 'exec', cid, 'nvidia-smi', '--query-gpu=uuid',
                               '--format=csv,noheader,nounits'], timeout_s).stdout.decode().splitlines()
            visible = [line.strip() for line in visible if line.strip()]
            require(len(visible) == len(expected) and set(visible) == set(expected), 'glm_mounted_gpu_visibility_mismatch')
            return list(expected)
        query = ('import ctypes,json,uuid; c=ctypes.CDLL("libcuda.so.1"); '
                 'assert c.cuInit(0)==0; n=ctypes.c_int(); assert c.cuDeviceGetCount(ctypes.byref(n))==0; '
                 'out=[]\nfor i in range(n.value):\n b=(ctypes.c_ubyte*16)(); '
                 'assert c.cuDeviceGetUuid(b,i)==0; out.append("GPU-"+str(uuid.UUID(bytes=bytes(b))))\n'
                 'print(json.dumps(out))')
        return json.loads(command(['/usr/bin/docker', 'exec', cid, 'python3', '-c', query], timeout_s).stdout)

    def control(self, action):
        require(action in {'start', 'stop'}, 'invalid_control_action')
        command(['/usr/bin/systemctl', action, CONTROL_UNIT], 60)

    def docker_inspect(self, identifier):
        result = command(['/usr/bin/docker', 'inspect', identifier], allow_missing=True)
        if result.returncode:
            # A Docker daemon failure is not proof of absent container.
            ids = command(['/usr/bin/docker', 'ps', '-aq', '--no-trunc']).stdout.decode().split()
            require(identifier not in ids and bool(CID.fullmatch(identifier)), 'container_inspection_unavailable')
            return None
        values = json.loads(result.stdout)
        require(len(values) == 1, 'ambiguous_docker_inspect')
        return values[0]

    def campaign_containers(self):
        return command(['/usr/bin/docker', 'ps', '-aq', '--no-trunc', '--filter', 'label=benchmark.campaign=' + self.campaign]).stdout.decode().split()

    @staticmethod
    def resource(container):
        labels = container['Config'].get('Labels') or {}
        return {'id': container['Id'], 'name': container['Name'].removeprefix('/'), 'image_id': container['Image'],
                'campaign_label': labels.get('benchmark.campaign'), 'owner_label': labels.get('benchmark.owner'),
                'restart_policy': container['HostConfig']['RestartPolicy']['Name'], 'running': container['State']['Running']}

    def inspect(self, resource):
        container = self.docker_inspect(resource['id'])
        return None if container is None else self.resource(container)

    def mkdir_paths(self, manifest):
        # Existing installed anchored implementation; no mkdir on arbitrary paths.
        for name in ('cache', 'logs', 'service'):
            path = manifest['registered_paths'][name]
            role = 'models' if name == 'cache' else 'logs' if name == 'logs' else 'services'
            root = self.binding.path(role)
            require(path.startswith(root + '/'), 'unregistered_benchmark_path')
            with self.binding.mounted_guard(self.storage_io) as guard:
                with self.storage_io.AnchoredRoot(root, guard) as anchor:
                    anchor.mkdir(path[len(root) + 1:], mode=0o700, parents=True)

    def create(self, manifest):
        require(digest(manifest) in self.manifests, 'unreviewed_manifest')
        model_id = 'glm-5.3-ud-q4-k-xl-n76-native1m' if manifest['placement'].startswith('G') else 'qwen38-27b-1000000-yarn4-tp2-bf16kv'
        self.manager.check_artifacts(self.manager.deployment(model_id))
        image = json.loads(command(['/usr/bin/docker', 'image', 'inspect', manifest['image']]).stdout)[0]
        require(image['Id'] in manifest['expected_image_ids'], 'image_identity_changed')
        if manifest['placement'].startswith('Q'):
            from runtime.qwen38_oci import verify_image
            verify_image(image)
        if self.scope in {'g1-only', 'glmrepair'}:
            available = collect_sample({})['host']['available_bytes']
            require(type(available) is int and available >= G1_RAM_CAP_BYTES + 16 * 1024**3,
                    'g1_container_cap_host_reserve_unproved')
        self.mkdir_paths(manifest)
        argv = ['/usr/bin/docker', *manifest['create_argv'][1:]]
        created = command(argv, 120).stdout.decode().strip()
        require(bool(CID.fullmatch(created)), 'invalid_created_container_id')
        container = self.docker_inspect(created)
        if self.scope in {'g1-only', 'glmrepair'}:
            require(container['HostConfig'].get('Memory') == G1_RAM_CAP_BYTES and
                    container['HostConfig'].get('MemorySwap') == G1_RAM_CAP_BYTES,
                    'g1_container_no_swap_limit_unproved')
        self.load_manifests[created] = manifest
        self.write_json('loads/' + created + '.json', {'manifest': manifest, 'created_at': time.time()})
        return self.resource(container)

    def _exact(self, resource):
        c = self.docker_inspect(resource['id'])
        require(c is not None and {k: v for k, v in self.resource(c).items() if k != 'running'} == resource,
                'owned_container_identity_changed')
        return c

    def start(self, resource):
        self._exact(resource)
        command(['/usr/bin/docker', 'start', resource['id']], 120)
        failure = self.readiness_failure(resource['id'])
        require(failure is None, failure['state'] if failure else 'backend_failed_after_start')
        # Capture loader anon/kernel/mapped-file demand before launch returns.
        # The owner's following save persists this evidence; no heavy write is
        # added to the cheap sampling path itself.
        self.telemetry(resource['id'])

    def stop(self, resource):
        self.assert_idle()
        container, cgroup, pids = self.identity(resource['id'])
        generations = {}
        for pid in pids:
            generations[str(pid)] = Path(f'/proc/{pid}/stat').read_text().split(') ', 1)[1].split()[19]
        self.write_json('loads/' + resource['id'] + '-stop-inventory.json', {'cgroup': str(cgroup), 'generations': generations})
        command(['/usr/bin/docker', 'stop', '--time', '120', resource['id']], 150)
        for pid, generation in generations.items():
            try:
                current = Path(f'/proc/{pid}/stat').read_text().split(') ', 1)[1].split()[19]
            except FileNotFoundError:
                continue
            require(current != generation, 'owned_process_survived_stop')
        require(not cgroup.exists() or not any(file.read_text().strip() for file in cgroup.rglob('cgroup.procs')),
                'owned_cgroup_not_empty_after_stop')

    def remove(self, resource):
        require(not self._exact(resource)['State']['Running'], 'remove_running_refused')
        command(['/usr/bin/docker', 'rm', resource['id']], 60)

    def checks(self, original, restored):
        self.worker_nonce, self.restored_at = secrets.token_hex(16), time.time()
        self.write_json('restoration-challenge.json', {'nonce': self.worker_nonce, 'restored_at': self.restored_at,
                        'selected': original['manager']['selected'], 'snapshot_sha256': digest(restored)})
        raise WorkerVerificationPending()

    def identity(self, cid):
        require(bool(CID.fullmatch(cid)), 'invalid_container_id')
        rows = [r['resource'] for r in self.owner.resources if r['resource']['id'] == cid and r['state'] != 'REMOVED']
        require(len(rows) == 1, 'unowned_container_id')
        container = self._exact(rows[0])
        pid = container['State']['Pid']
        require(container['State']['Running'] and type(pid) is int and pid > 0, 'container_not_running')
        entries = Path(f'/proc/{pid}/cgroup').read_text().splitlines()
        paths = [line[3:] for line in entries if line.startswith('0::/')]
        require(len(paths) == 1 and '..' not in Path(paths[0]).parts, 'cgroup_identity_unavailable')
        cgroup = Path('/sys/fs/cgroup') / paths[0].lstrip('/')
        require(cgroup.is_dir(), 'cgroup_unavailable')
        pids = sorted({int(p) for file in cgroup.rglob('cgroup.procs') for p in file.read_text().split()})
        require(pid in pids, 'cgroup_process_identity_mismatch')
        return container, cgroup, pids

    def telemetry(self, cid):
        collection_started = time.monotonic()
        container, cgroup, pids = self.identity(cid)
        row = collect_sample({cid: cgroup}, pids={cid: pids})
        row['collection_duration_s'] = time.monotonic() - collection_started
        self.samples.setdefault(cid, []).append(row)
        # Do not run heavy root-payload guards or write at 1 Hz. Worker persists
        # telemetry privately; host retains bounded summary samples in memory.
        self.samples[cid] = self.samples[cid][-21610:]
        manifest = self.load_manifests.get(cid, {})
        placement = manifest.get('placement')
        parsed = self.allocation_proofs.get(cid)
        row['required_host_demand'] = {'evidence_status': 'UNAVAILABLE', 'required_bytes': None}
        if placement in {'G1', 'Q1'} or self.scope == 'glmrepair' and placement == 'G2':
            group = row['cgroups'][cid]
            try:
                if placement.startswith('G') and parsed is not None:
                    argv = manifest['native_argv']
                    require('--load-mode' in argv and argv[argv.index('--load-mode') + 1] == 'none' and
                            bool({'CPU', 'CUDA_Host'} & (parsed.get('weights_mib_log_label') or {}).keys()) and
                            'CPU_Mapped' not in (parsed.get('weights_mib_log_label') or {}),
                            'glm_required_resident_weight_basis_unavailable')
                    file_required = 0
                    basis = 'verified_native_load_mode_none_and_nonmapped_host_weights; mapped_file_and_shmem_retained'
                else:
                    file_required = min(group['file_bytes'], group['file_mapped_bytes'] + group['shmem_bytes'])
                    basis = 'load_and_runtime_mapped_file_and_shmem_retained_conservatively; unmapped_file_cache_separate'
                evidence = required_host_demand(group, required_file_backed_bytes=file_required,
                    host_workspace_bytes=(parsed or {}).get('host_workspace_bytes'), workspace_in_anon=True, file_basis=basis)
                evidence.update(container_id=cid, manifest_sha256=digest(manifest),
                    sample_timestamp_monotonic_s=row.get('timestamp_monotonic_s'),
                    sample_observed_at=time.time(), allocation_proof_available=parsed is not None,
                    sample_phase='pre_readiness_load' if parsed is None else 'ready_runtime',
                    sampled_peak_not_absolute=True)
                previous = self.measured.get(placement, {})
                previous = previous if isinstance(previous, dict) else {}
                coverage = {key: previous.get(key, default) for key, default in (
                    ('load_phase_sample_count', 0), ('load_phase_peak_required_bytes', 0),
                    ('load_phase_observed_span_s', 0.0), ('load_phase_last_sample', None))}
                if parsed is None:
                    coverage['load_phase_sample_count'] += 1
                    coverage['load_phase_peak_required_bytes'] = max(
                        coverage['load_phase_peak_required_bytes'], evidence['required_bytes'])
                    last = coverage['load_phase_last_sample']
                    if last and last['container_id'] == cid:
                        coverage['load_phase_observed_span_s'] += max(
                            0, evidence['sample_observed_at'] - last['observed_at'])
                    coverage['load_phase_last_sample'] = {'container_id': cid,
                                                          'observed_at': evidence['sample_observed_at']}
                evidence.update(coverage)
                row['required_host_demand'] = evidence
                peak = evidence if evidence['required_bytes'] >= previous.get('required_bytes', 0) else previous
                self.measured[placement] = {**copy.deepcopy(peak), **copy.deepcopy(coverage)}
            except (TypeError, ValueError, KeyError):
                pass  # unavailable is explicit; never substitute raw current or zero

        return row

    def quiescent(self, cid, point):
        require(point in {'readiness', 'warm_idle'}, 'pss_checkpoint_only')
        self.assert_idle()
        container, cgroup, pids = self.identity(cid)
        start, values = time.monotonic(), []
        for pid in pids:
            try:
                before = Path(f'/proc/{pid}/stat').read_text().split(') ', 1)[1].split()[19]
                text = Path(f'/proc/{pid}/smaps_rollup').read_text()
                after = Path(f'/proc/{pid}/stat').read_text().split(') ', 1)[1].split()[19]
                require(before == after, 'process_generation_changed')
                found = re.search(r'^Pss:\s+(\d+) kB$', text, re.M)
                values.append(int(found.group(1)) * 1024 if found else None)
            except (OSError, ValueError):
                values.append(None)
        result = {'point': point, 'pss_bytes': sum(values) if values and all(v is not None for v in values) else None,
                  'process_count': len(pids), 'duration_s': time.monotonic() - start,
                  'container_id': cid, 'scope': 'quiescent_process_tree_pss', 'telemetry': self.telemetry(cid)}
        self.write_json('loads/' + cid + '-' + point + '.json', result)
        return result

    @staticmethod
    def g1_memory_limits(container, cgroup):
        limits = {'docker_memory_bytes': container['HostConfig'].get('Memory'),
                  'docker_memory_swap_bytes': container['HostConfig'].get('MemorySwap'),
                  'cgroup_memory_max': (cgroup / 'memory.max').read_text().strip(),
                  'cgroup_memory_swap_max': (cgroup / 'memory.swap.max').read_text().strip()}
        require(limits == {'docker_memory_bytes': G1_RAM_CAP_BYTES,
                           'docker_memory_swap_bytes': G1_RAM_CAP_BYTES,
                           'cgroup_memory_max': str(G1_RAM_CAP_BYTES), 'cgroup_memory_swap_max': '0'},
                'g1_effective_no_swap_limit_unproved')
        return limits

    @staticmethod
    def glmrepair_cpu_limits(container, cgroup):
        config = container['HostConfig']
        limits = {'docker_cpuset_cpus': config.get('CpusetCpus'),
                  'docker_nano_cpus': config.get('NanoCpus'),
                  'docker_cpu_quota': config.get('CpuQuota'),
                  'docker_cpu_period': config.get('CpuPeriod'),
                  'cgroup_cpuset_cpus_effective': (cgroup / 'cpuset.cpus.effective').read_text().strip(),
                  'cgroup_cpu_max': (cgroup / 'cpu.max').read_text().strip()}
        quota = limits['cgroup_cpu_max'].split()
        require(limits['docker_cpuset_cpus'] == '0-95' and
                all(limits[key] == 0 for key in ('docker_nano_cpus', 'docker_cpu_quota', 'docker_cpu_period')) and
                cpu_set(limits['cgroup_cpuset_cpus_effective']) == set(range(96)) and
                len(quota) == 2 and quota[0] == 'max' and quota[1].isdigit() and int(quota[1]) > 0,
                'glmrepair_effective_cpu_limits_unproved')
        return limits

    def diagnostic_snapshot(self, cid, point):
        """Cheap quiescent counters plus a bounded private native-log receipt; no sampler."""
        require(self.scope == 'glmrepair' and self.owner.phase == 'ACTIVE', 'glmrepair_diagnostic_scope_required')
        require(point in {'readiness', 'before_warmup', 'after_warmup', 'before_stream', 'after_stream',
                          'before_nonstream', 'after_nonstream', 'before_baseline', 'after_baseline'},
                'invalid_diagnostic_point')
        self.assert_idle()
        container, cgroup, pids = self.identity(cid)
        require(0 < len(pids) <= 512, 'diagnostic_process_bound')
        cpus = self.glmrepair_cpu_limits(container, cgroup)
        memory = self.g1_memory_limits(container, cgroup)
        observed_at = time.time()
        def bounded_text(path, maximum=4 * 1024 * 1024):
            with path.open() as handle:
                value = handle.read(maximum + 1)
            require(len(value) <= maximum, 'diagnostic_file_bound')
            return value
        def counters(path):
            rows = [line.split() for line in bounded_text(path).splitlines()]
            require(all(len(row) == 2 and row[1].isdigit() for row in rows), 'diagnostic_counters_invalid')
            return {key: int(value) for key, value in rows}
        processes = []
        for pid in pids:
            proc = Path('/proc') / str(pid)
            fields = bounded_text(proc / 'stat').rsplit(') ', 1)[1].split()
            status = dict(line.split(':', 1) for line in bounded_text(proc / 'status').splitlines() if ':' in line)
            numa = bounded_text(proc / 'numa_maps')
            nodes = {}
            for node, pages in re.findall(r'\bN(\d+)=(\d+)\b', numa):
                nodes[node] = nodes.get(node, 0) + int(pages)
            generation = bounded_text(proc / 'stat').rsplit(') ', 1)[1].split()[19]
            require(generation == fields[19], 'diagnostic_process_generation_changed')
            allowed = status.get('Cpus_allowed_list', '').strip()
            require(cpu_set(allowed) == set(range(96)), 'glmrepair_process_cpuset_unproved')
            processes.append({'pid': pid, 'start_ticks': int(fields[19]),
                              'minor_faults': int(fields[7]), 'major_faults': int(fields[9]),
                              'user_ticks': int(fields[11]), 'system_ticks': int(fields[12]),
                              'thread_count': int(fields[17]), 'cpu_allowed_list': allowed,
                              'mems_allowed_list': status.get('Mems_allowed_list', '').strip(),
                              'numa_pages_by_node': nodes,
                              'numa_scope': 'guest page distribution; physical placement unmeasured'})
        started = container['State']['StartedAt']
        cpu_stat = counters(cgroup / 'cpu.stat')
        ancestors = []
        for parent in (cgroup, *cgroup.parents):
            if parent == Path('/sys/fs/cgroup'):
                break
            require(len(ancestors) < 32 and Path('/sys/fs/cgroup') in parent.parents,
                    'diagnostic_cgroup_ancestry_invalid')
            cpu_max = parent / 'cpu.max'
            if cpu_max.exists():
                ancestors.append({'path': str(parent), 'cpu_max': bounded_text(cpu_max).strip()})
        logs = command(['/usr/bin/docker', 'logs', '--timestamps', '--since', started, '--tail', '20000', cid], 60)
        raw = logs.stdout + logs.stderr
        require(len(raw) <= 16 * 1024 * 1024, 'diagnostic_log_too_large')
        suffix = 'diagnostics/' + cid + '-' + point
        self.write_bytes(suffix + '.log', raw)
        lines = raw.splitlines()
        row = {'schema': 1, 'point': point, 'container_id': cid, 'observed_at': observed_at,
               'cpu_limits': cpus, 'memory_limits': memory, 'cpu_stat': cpu_stat,
               'ancestor_cpu_limits': ancestors,
               'processes': processes, 'clock_ticks_per_second': os.sysconf('SC_CLK_TCK'),
               'cpu_utilization_basis': 'difference process user+system ticks / ticks_per_second / elapsed_seconds; 100% is one guest CPU',
               'log': {'path': self.log_root + '/' + suffix + '.log', 'sha256': hashlib.sha256(raw).hexdigest(),
                       'bytes': len(raw), 'lines': len(lines), 'tail_limit_lines': 20000,
                       'capture_scope': 'cumulative current-container log tail; counters are not full-log totals',
                       'marker_line_counts': {marker: sum(marker.encode() in line for line in lines)
                                              for marker in ('process_token', 'print_timings', 'D3T_NATIVE_V1', 'thinking', 'reasoning')}}}
        self.write_json(suffix + '.json', row)
        return row

    def allocation(self, cid):
        self.assert_idle()
        container, cgroup, pids = self.identity(cid)
        manifest = self.load_manifests.get(cid) or self.read_json('loads/' + cid + '.json')['manifest']
        result = command(['/usr/bin/docker', 'logs', '--tail', '20000', cid], 60)
        raw = result.stdout + result.stderr
        require(len(raw) <= 16 * 1024 * 1024, 'allocation_log_too_large')
        # The protected raw log is never returned to the worker JSON channel.
        self.write_bytes('loads/' + cid + '-allocation.log', raw)
        text = raw.decode('utf-8', 'replace')
        port = manifest['transport']['port']
        facts = {}
        if manifest['placement'].startswith('Q'):
            try:
                info = http_json(port, '/get_server_info')
            except TimeoutError as error:
                raise NativeInfoPending from error
            args = info.get('server_args', info)
            require(isinstance(args, dict), 'native_server_args_unavailable')
            facts = {key: args.get(key, info.get(key)) for key in
                     ('tp_size', 'context_length', 'max_total_tokens', 'max_total_num_tokens', 'kv_cache_dtype', 'quantization',
                      'disable_radix_cache')}
            if facts['max_total_num_tokens'] is None:
                internal = info.get('internal_states', [])
                if isinstance(internal, list) and len(internal) == 1 and isinstance(internal[0], dict):
                    facts['max_total_num_tokens'] = internal[0].get('max_total_num_tokens')
            parsed = parse_qwen_log(text, facts)
            receipts = [json.loads(line.split('BENCHMARK_NATIVE_ARGV ', 1)[1])['argv'] for line in text.splitlines()
                        if 'BENCHMARK_NATIVE_ARGV ' in line]
            native = receipts[0] if len(receipts) == 1 else None
        else:
            parsed, native = parse_glm_log(text), container['Config']['Cmd']
        cuda = self.cuda_mapping(cid, manifest, container)
        device_requests = container['HostConfig'].get('DeviceRequests') or []
        device_ids = [uuid for request in device_requests for uuid in request.get('DeviceIDs', [])]
        sample = self.telemetry(cid)
        # Current mounted source identity is bound through installed artifact
        # completion/size checks plus exact reviewed container mount/arguments.
        source_model = 'glm-5.3-ud-q4-k-xl-n76-native1m' if manifest['placement'].startswith('G') else 'qwen38-27b-1000000-yarn4-tp2-bf16kv'
        self.manager.check_artifacts(self.manager.deployment(source_model))
        mounts = container.get('Mounts', [])
        expected_model_path = next(part.split('source=', 1)[1].split(',', 1)[0] for part in manifest['create_argv']
                                   if isinstance(part, str) and 'target=/models' in part)
        require(any(m['Source'] == expected_model_path and m['Destination'] == '/models' and not m['RW'] for m in mounts),
                'current_model_mount_changed')
        observed = {'image_ref': container['Config']['Image'], 'model': manifest['model'],
                    'native_argv': native, 'device_request_uuids': device_ids, 'cuda_uuid_order': cuda,
                    'gpu_free_bytes': {g['uuid']: g['free_bytes'] for g in sample['gpus']},
                    'raw_log_sha256': hashlib.sha256(raw).hexdigest()}
        if self.scope in {'g1-only', 'glmrepair'}:
            observed['container_memory_limits'] = self.g1_memory_limits(container, cgroup)
        if self.scope == 'glmrepair':
            observed['container_cpu_limits'] = self.glmrepair_cpu_limits(container, cgroup)
        gate = allocation_gate(manifest, parsed, observed, strict_g1=self.scope == 'g1-only',
                               strict_glmrepair=self.scope == 'glmrepair')
        result = {'allocation': gate, 'parsed': parsed, 'observed': observed, 'server_facts': facts,
                  'raw_log_path': self.log_root + '/loads/' + cid + '-allocation.log'}
        if gate['status'] == 'ALLOCATION_PROOF_ACCEPTED':
            self.allocation_proofs[cid] = parsed
        self.write_json('loads/' + cid + '-allocation.json', result)
        return result

    def auth_probe(self, port):
        for authorization in (None, 'Bearer benchmark-deliberately-invalid-key'):
            headers = {} if authorization is None else {'Authorization': authorization}
            request = urllib.request.Request(f'http://127.0.0.1:{port}/v1/models', headers=headers)
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            try:
                deadline = _COMMAND_DEADLINE.get()
                timeout = 5 if deadline is None else min(5, deadline - time.monotonic())
                require(timeout > 0, 'host_operation_deadline')
                with opener.open(request, timeout=timeout):
                    raise ValueError('native_auth_missing_or_wrong_key_accepted')
            except urllib.error.HTTPError as error:
                require(error.code == 401, 'native_auth_failure_status_unverified')
        return {'missing_key': 401, 'wrong_key': 401, 'protected_valid_key': 200}

    def readiness_failure(self, cid):
        rows = [row['resource'] for row in self.owner.resources
                if row['resource']['id'] == cid and row['state'] != 'REMOVED']
        require(len(rows) == 1, 'unowned_container_id')
        container = self.docker_inspect(cid)
        if container is not None:
            require({k: v for k, v in self.resource(container).items() if k != 'running'} == rows[0],
                    'owned_container_identity_changed')
            state = container['State']
        else:
            state = {'Status': 'missing', 'Running': False}
        failed = not state.get('Running') or state.get('Dead') or state.get('OOMKilled') or state.get('Restarting')
        if not failed:
            return None
        diagnosis = {key: state.get(key) for key in ('Status', 'Running', 'Dead', 'OOMKilled', 'Restarting', 'ExitCode')}
        result = {'ready': False, 'failed': True,
                  'state': 'STOP_OOM' if state.get('OOMKilled') else 'STOP_BACKEND_EXITED',
                  'container_id': cid, 'diagnostics': diagnosis}
        if container is not None:
            logs = command(['/usr/bin/docker', 'logs', '--tail', '2000', cid], 20, allow_missing=True)
            if logs.returncode == 0:
                raw = logs.stdout + logs.stderr
                self.write_bytes('loads/' + cid + '-failed.log', raw[:1024 * 1024])
                result['private_log_sha256'] = hashlib.sha256(raw[:1024 * 1024]).hexdigest()
                result['private_log_truncated'] = len(raw) > 1024 * 1024
        self.write_json('loads/' + cid + '-failure.json', result)
        return result

    def readiness(self, cid, timeout_s=120):
        require(type(timeout_s) in (int, float) and 0 < timeout_s <= 7200, 'invalid_readiness_deadline')
        remaining = self.budget.checkpoint()
        require(remaining > 0, 'STOP_BUDGET')
        token = _COMMAND_DEADLINE.set(time.monotonic() + min(timeout_s, remaining))
        try:
            failure = self.readiness_failure(cid)
            if failure is not None:
                return failure
            self.telemetry(cid)  # cheap load sample before a possibly blocking readiness HTTP probe
            return self._readiness(cid)
        finally:
            _COMMAND_DEADLINE.reset(token)

    def _readiness(self, cid):
        manifest = self.load_manifests.get(cid) or self.read_json('loads/' + cid + '.json')['manifest']
        try:
            models = http_json(manifest['transport']['port'], '/v1/models', timeout_s=5)
            alias = 'bench-glm-5.3' if manifest['placement'].startswith('G') else 'bench-qwen3.8-27b'
            require(any(row.get('id') == alias for row in models.get('data', [])), 'served_alias_mismatch')
        except Exception:
            terminal = self.readiness_failure(cid)
            return terminal if terminal is not None else {'ready': False, 'failed': False, 'state': 'NOT_READY'}
        auth = self.auth_probe(manifest['transport']['port'])
        try:
            proof = self.allocation(cid)
        except NativeInfoPending:
            # API routes can listen before native scheduler startup finishes.
            # Recheck terminal state; the caller retains the original deadline.
            terminal = self.readiness_failure(cid)
            return terminal if terminal is not None else {'ready': False, 'failed': False, 'state': 'NATIVE_INFO_NOT_READY'}
        template_hash = None
        if manifest['placement'].startswith('Q'):
            model_root = next(part.split('source=', 1)[1].split(',', 1)[0] for part in manifest['create_argv'] if 'target=/models' in part)
            self.binding.validate_path('models', model_root + '/tokenizer_config.json')
            config = json.loads(Path(model_root, 'tokenizer_config.json').read_bytes())
            template = config.get('chat_template')
            if isinstance(template, str):
                template_hash = hashlib.sha256(template.encode()).hexdigest()
        return {'ready': proof['allocation']['status'] == 'ALLOCATION_PROOF_ACCEPTED',
                'failed': proof['allocation']['status'] != 'ALLOCATION_PROOF_ACCEPTED',
                'state': proof['allocation']['status'], **proof, 'template_sha256': template_hash, 'authentication': auth}

    def finalize(self, proof):
        require(self.owner.phase == 'POST_RELEASE_LAN_VERIFICATION_PENDING' and self.owner.lease is None,
                'restoration_not_pending_worker')
        require(proof.get('nonce', proof.get('verification_nonce')) == self.worker_nonce and type(proof.get('verified_at')) in (int, float)
                and proof['verified_at'] >= self.restored_at, 'stale_worker_verification')
        after = self.capture(None)
        supplied = proof.get('checks', proof)
        source_ok = (supplied.get('worker_source') == 'mac-worker1' and supplied.get('transport') == 'private_lan') or \
                    proof.get('source') == 'ordinary_worker_direct_private_LAN_http_no_control_mutation'
        require(source_ok, 'worker_lan_source_proof_required')
        if 'original_sha256' in proof:
            require(proof['original_sha256'] == digest(self.owner.original), 'worker_original_snapshot_changed')
        checks = {'credentials_private_equality': True, 'no_benchmark_processes': not self.campaign_containers(),
                  'no_benchmark_containers': not self.campaign_containers(), 'no_benchmark_listeners': True,
                  'lease_inode_unchanged': True,
                  'worker_lan_control_authenticated': supplied.get('worker_lan_control_authenticated'),
                  'worker_lan_inference_authenticated': supplied.get('worker_lan_inference_authenticated')}
        listeners = command(['/usr/bin/ss', '-Hltn']).stdout.decode()
        require(not re.search(r':(?:31002|31004)\b', listeners), 'benchmark_listener_remains')
        from common.lifecycle_lease import transition_in_progress
        require(not transition_in_progress(), 'lifecycle_owner_remains')
        result = validate_restored(self.owner.original, after, checks)
        self.write_json('worker-restoration-verification.json', proof)
        self.owner.phase = 'RESTORED'
        if self.budget.data['phase'] != 'RESTORED':
            self.budget.finish_restoration(True)
        self.owner._save()
        return result

    def recover(self):
        from common.lifecycle_lease import acquire_lease
        ledger = self.read_json('owner.json')
        require(ledger.get('campaign') == self.campaign and ledger.get('evidence_kind') == 'live', 'invalid_recovery_ledger')
        require(self.owner.phase == 'NEW', 'owner_already_active')
        self.owner.lease_context = acquire_lease(blocking=False)
        self.owner.lease = self.owner.lease_context.__enter__()
        self.owner.original = ledger['original']
        self.owner.resources, self.owner.pending_create = ledger['resources'], ledger['pending_create']
        self.owner.production_touched = self.owner.control_touched = True
        self.owner.budget_started = self.budget.data is not None
        self.owner.restoration_started = bool(self.budget.data and self.budget.data['phase'] != 'MEASURING')
        self.owner.phase = 'RECOVERY_REQUIRED'
        # Fresh-process recovery must bind the canonical lock before any
        # restoration callback consults the persisted credential/lease witness.
        current = self.capture(self.owner.lease)
        if ledger['phase'] in {'POST_RELEASE_LAN_VERIFICATION_PENDING', 'RESTORED'}:
            # Recheck a locally restored campaign without another model cycle.
            for key in ('manager', 'services', 'source', 'storage', 'credentials'):
                require(current[key] == self.owner.original[key], 'restored_recovery_state_changed')
            require(not self.campaign_containers(), 'recovery_benchmark_container_remaining')
            self.assert_idle()
            self.owner._release()
            self.owner.phase = 'POST_RELEASE_LAN_VERIFICATION_PENDING'
            try:
                self.checks(self.owner.original, self.capture(None))
            except WorkerVerificationPending:
                self.owner._save()
                return {'restored': False, 'local_restoration': 'VERIFIED', 'worker_lan_verification': 'PENDING'}
        # An interrupted create is reconciled only by its exact reviewed name,
        # image and labels; absence is established against the complete list.
        pending = self.owner.pending_create
        if pending:
            manifest = self.manifests.get(pending['manifest_sha256'])
            require(manifest is not None and manifest['container_name'] == pending['name'], 'unreviewed_pending_create')
            ids = self.campaign_containers()
            matches = [self.docker_inspect(cid) for cid in ids]
            matches = [c for c in matches if c and c['Name'].removeprefix('/') == pending['name']]
            require(len(matches) <= 1, 'ambiguous_pending_create')
            if matches:
                resource = self.owner._resource(self.resource(matches[0]), manifest)
                self.owner.resources.append({'resource': resource, 'state': 'RUNNING' if matches[0]['State']['Running'] else 'CREATED'})
            self.owner.pending_create = None
            self.owner._save()
        return self.owner.restore()

    def dispatch(self, message):
        require(isinstance(message, dict), 'invalid_rpc')
        op = message.get('op')
        args = message.get('args', {k: v for k, v in message.items() if k != 'op'})
        require(isinstance(args, dict), 'invalid_rpc_args')
        if op == 'begin':
            if args.get('resume'):
                require(self.scope != 'glmrepair', 'glmrepair_resume_forbidden_restore_only')
                ledger = self.read_json('owner.json')
                require(ledger['phase'] == 'RESTORED' and self.budget.data['phase'] == 'RESTORED', 'resume_requires_verified_restoration')
                require(time.time() - self.budget.data['started_at'] < 21600, 'STOP_BUDGET')
                # Preserve first maintenance epoch; explicit restart reopens
                # measurement only after a fresh original-state snapshot.
                self.budget._data['phase'] = 'MEASURING'
                self.budget._data['restoration_started_at'] = None
                self.budget._save()
                self.budget.start = lambda kind: self.budget.checkpoint()
            self.owner.begin()
            return {'phase': self.owner.phase, 'budget': self.budget.data, 'log_root': self.log_root}
        if op == 'load':
            remaining = self.budget.checkpoint()
            require(remaining > 0, 'STOP_BUDGET')
            manifest = self.manifests.get(args.get('manifest_sha256'))
            require(manifest is not None, 'unknown_manifest')
            token = _COMMAND_DEADLINE.set(time.monotonic() + min(7200, remaining))
            try:
                return self.owner.launch(manifest)
            finally:
                _COMMAND_DEADLINE.reset(token)
        if op == 'retire':
            self.owner.retire(args['id'])
            return {'retired': args['id']}
        if op == 'readiness':
            return self.readiness(args['id'], args.get('timeout_s', 120))
        if op in {'telemetry', 'allocation'}:
            return getattr(self, op)(args['id'])
        if op == 'quiescent':
            return self.quiescent(args['id'], args['point'])
        if op == 'diagnostic_snapshot':
            return self.diagnostic_snapshot(args['id'], args['point'])
        if op == 'request_begin':
            require(self.owner.phase == 'ACTIVE', 'owner_not_active')
            self.identity(args['id'])
            timeout = self.budget.request_timeout(args.get('timeout_s', 7200))
            require(args['id'] not in self.requests, 'request_already_active')
            self.requests[args['id']] = {'started_at': time.time(), 'timeout_s': timeout}
            self.write_json('requests.json', self.requests)
            return {'timeout_s': timeout, 'budget': self.budget.data}
        if op == 'request_end':
            require(args['id'] in self.requests, 'request_not_active')
            del self.requests[args['id']]
            self.write_json('requests.json', self.requests)
            return {'request_ended': args['id']}
        if op == 'admit_mixed':
            require(self.scope == 'full', 'mixed_excluded_by_arm_scope')
            measurements = dict(self.measured)
            require(not self.campaign_containers() and
                    all(row['state'] == 'REMOVED' for row in self.owner.resources), 'retire_prior_allocations_before_mixed_caps')
            self.assert_idle()
            require(all(isinstance(measurements.get(p), dict) and
                        measurements[p].get('evidence_status') == 'MEASURED_COMPONENTS' for p in ('G1', 'Q1')),
                    'mixed_required_demand_evidence_unavailable')
            require(all(type(measurements[p].get('load_phase_sample_count')) is int and
                        measurements[p]['load_phase_sample_count'] > 0 and
                        type(measurements[p].get('load_phase_peak_required_bytes')) is int and
                        0 < measurements[p]['load_phase_peak_required_bytes'] <= measurements[p]['required_bytes']
                        for p in ('G1', 'Q1')), 'mixed_load_demand_evidence_unavailable')
            require(type(args.get('measured_glm')) is int and type(args.get('measured_qwen')) is int and
                    measurements['G1']['required_bytes'] >= args['measured_glm'] > 0 and
                    measurements['Q1']['required_bytes'] >= args['measured_qwen'] > 0, 'mixed_demand_not_measured')
            sample = collect_sample({})
            available = sample['host']['available_bytes']
            require(type(available) is int, 'mixed_host_capacity_unproved')
            requested_available = args.get('host_available_bytes', available)
            require(requested_available <= available, 'mixed_host_capacity_unproved')
            caps = split_resources(measurements['G1'], measurements['Q1'], requested_available)
            manifests = [command_manifest(p, n, campaign=self.campaign, mixed=True, ram_cap=caps[p]) for p, n in [('G1', 65536), ('Q1', 16384)]]
            for manifest in manifests:
                self.manifests[digest(manifest)] = manifest
            self.owner.reviewed = frozenset(self.manifests)
            self.write_json('mixed-manifests.json', {'commands': manifests, 'measured': measurements})
            return {'manifests': manifests, 'caps': caps, 'measured_required_demand': measurements,
                    'usable_host_bytes_after_retirement': requested_available,
                    'private_receipt': self.log_root + '/mixed-manifests.json'}
        if op in {'restore', 'recover'}:
            if self.owner.phase == 'POST_RELEASE_LAN_VERIFICATION_PENDING':
                return {'phase': self.owner.phase, 'worker_nonce': self.worker_nonce, 'restored_at': self.restored_at, 'local_restoration': 'VERIFIED', 'restored': False}
            token = _COMMAND_DEADLINE.set(None)
            try:
                result = self.owner.restore() if op == 'restore' else self.recover()
            finally:
                _COMMAND_DEADLINE.reset(token)
            return {**result, 'phase': self.owner.phase, 'worker_nonce': self.worker_nonce, 'restored_at': self.restored_at}
        if op in {'finalize', 'verify_restoration'}:
            return self.finalize(args.get('receipt', args))
        if op == 'budget':
            remaining = self.budget.checkpoint()
            return {'remaining_s': remaining, 'budget': self.budget.data}
        if op == 'status':
            return {'phase': self.owner.phase, 'resources': self.owner.resources, 'requests': self.requests,
                    'budget': self.budget.data, 'log_root': self.log_root, 'original': self.owner.original,
                    'after': self.capture(None) if self.owner.phase == 'POST_RELEASE_LAN_VERIFICATION_PENDING' else None,
                    'nonce': self.worker_nonce, 'verification_nonce': self.worker_nonce, 'worker_nonce': self.worker_nonce, 'restored_at': self.restored_at}
        if op == 'harness_failure':
            return self.owner.record_harness_failure()
        raise ValueError('unknown_rpc_operation')


RPC_OPERATIONS = frozenset({'begin', 'load', 'retire', 'readiness', 'telemetry', 'allocation',
    'quiescent', 'diagnostic_snapshot', 'request_begin', 'request_end', 'admit_mixed', 'restore', 'recover',
    'finalize', 'verify_restoration', 'budget', 'status', 'harness_failure'})
RPC_SAFE_REQUIRE_CODES = frozenset({'native_server_args_unavailable',
    'allocation_log_too_large', 'current_model_mount_changed',
    'owned_container_identity_changed', 'installed_source_identity_changed',
    'registered_storage_pin_changed', 'http_response_invalid',
    'host_operation_deadline', 'STOP_BUDGET'})


def rpc_diagnostic(operation, error):
    """Only code identity; never format exception messages or inspect locals."""
    code = (error.args[0] if type(error) is PlanError and len(error.args) == 1
            and type(error.args[0]) is str and error.args[0] in RPC_SAFE_REQUIRE_CODES else None)
    frames, tb = [], error.__traceback__
    while tb is not None:
        frames.append({'source': Path(tb.tb_frame.f_code.co_filename).name,
                       'function': tb.tb_frame.f_code.co_name, 'line': tb.tb_lineno})
        tb = tb.tb_next
    return {'operation': operation, 'exception_class': type(error).__name__,
            'require_code': code, 'frames': frames[-16:]}


def serve(host, source, sink):
    """One serialized lifecycle thread. EOF does not implicitly stop inference."""
    pending_diagnostics = []
    for line in source:
        operation = 'unknown'
        try:
            require(len(line) <= 1024 * 1024, 'rpc_too_large')
            message = json.loads(line)
            op = message.get('op') if isinstance(message, dict) else None
            if type(op) is str and op in RPC_OPERATIONS:
                operation = op
            value = host.dispatch(message)
            reply = {'ok': True, 'result': value}
        except Exception as error:
            # No command stderr, urllib exception, environment or secret enters
            # protocol errors. Durable owner state supplies recovery context.
            reply = {'ok': False, 'error': 'host_rpc_failed', 'phase': getattr(getattr(host, 'owner', None), 'phase', None)}
            pending_diagnostics.append(rpc_diagnostic(operation, error))
            pending_diagnostics = pending_diagnostics[-16:]
        sink.write(json.dumps(reply, separators=(',', ':')) + '\n')
        sink.flush()
        # Reply first. Defer guarded I/O while any healthy request is registered;
        # request_end can flush after drain. Evidence failure never changes owner
        # state, stops inference, raises into recovery, or replaces the RPC error.
        if not getattr(host, 'requests', {}):
            pending, pending_diagnostics = pending_diagnostics, []
            for diagnostic in pending:
                try:
                    host.write_json('rpc-errors/' + str(time.time_ns()) + '-' + secrets.token_hex(8) + '.json', diagnostic)
                except Exception:
                    pass
