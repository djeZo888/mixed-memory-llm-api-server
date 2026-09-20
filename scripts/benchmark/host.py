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
                       G1_RAM_CAP_BYTES, glmrepair_manifest, g1_ladder_manifest, glm_decode_diag_manifest, cpu_set,
                       CONCURRENT_SCOPE, CONCURRENT_CAMPAIGN, CONCURRENT_Q1_RAM_CAP_BYTES, concurrent_manifest,
                       CANDIDATE_SCOPE, candidate_manifest, candidate_manifests, candidate_modules, candidate_profile)
from .cpu_budget_profiles import (CPU_SCOPE, CPU_CAMPAIGN, manifest as cpu_manifest,
                                  POSTRESTART_SCOPE, POSTRESTART_CAMPAIGN, postrestart_manifest)
from .telemetry import collect_sample, required_host_demand, concurrent_host_demand
from .allocation import allocation_gate, parse_glm_log, parse_qwen_log

INSTALL = Path('/usr/local/lib/llm-server/control-api')
KEYS = {'inference': Path('/data/services/secrets/llm-api-key'), 'control': Path('/etc/llm-server/control-api-key')}
ENV = {'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LC_ALL': 'C'}
CID = re.compile(r'[a-f0-9]{64}\Z')
_COMMAND_DEADLINE = contextvars.ContextVar('benchmark_command_deadline', default=None)


def concurrent_capacity_policy(scope=None):
    """Closed root-reviewed planning provision, never current measured components."""
    policy = {'evidence_status': 'ROOT_REVIEWED_HISTORICAL_PROVISIONAL_NOT_CURRENT_MEASURED',
            'caps_bytes': {'G1': G1_RAM_CAP_BYTES, 'Q1': CONCURRENT_Q1_RAM_CAP_BYTES},
            'host_headroom_numerator': 5, 'host_headroom_denominator': 4,
            'os_reserve_bytes': 16 * 1024**3, 'gpu_reserve_bytes': 16 * 1024**3,
            'saved_provenance': {
                'G1': {'path': 'reports/glm-g1-ladder-20260920.json',
                       'sha256': 'f9ed5c46c57ceb44e7af2d78838f4c65fb1bdfb1abd8734687a27401815d6cdc',
                       'basis': 'historical about592GiB already includes25percent; tested640GiB provision'},
                'Q1': {'path': 'reports/benchq1-verified-20260919.json',
                       'sha256': '3a96e83cfe45764cf67828523667328290d717719e64025c97205a445e7fc1da',
                       'required_bytes': 13287989248,
                       'basis': 'host_load_peak; failed initial4K loader;32GiB candidate needs current load proof'}},
            'headroom_observation': '5*sampled_peak_required_working_set_ESTIMATE<=4*cap; raw current/peak separate hard-cap guards',
            'G1_native_floor': {'bytes': math.ceil((409012.22 + 0.005) * 1024**2) + 159461408,
                'basis': 'same-pin historical G65536 CUDA_Host409012.22MiB rounded-up plus159461408B workspace; not current allocation proof',
                'report_sha256': 'f9ed5c46c57ceb44e7af2d78838f4c65fb1bdfb1abd8734687a27401815d6cdc',
                'raw_log_sha256': 'f2272149566ee0892384d6b7b62432a7e1d5cfa2d71ac55897043fd7d1c2d49a'},
            'preload_host_available_minimum_bytes': 688 * 1024**3,
            'actual_load_required': True, 'allocator_policy_change_allowed': False}
    if scope in {CPU_SCOPE, POSTRESTART_SCOPE}:
        policy.update(host_headroom_numerator=23, host_headroom_denominator=20,
            host_headroom_policy={'version': 'sampled-required-working-set-15pct-v1',
                'numerator': 23, 'denominator': 20,
                'basis': 'sampled_required_working_set_estimate_bytes'},
            headroom_observation='sampled_peak_required_working_set_ESTIMATE*1.15<=cap; raw current/peak separate hard-cap guards')
    return policy



class NativeInfoPending(Exception):
    """Only a startup timeout from Qwen's native-info GET; not proof acceptance."""


def command(argv, timeout=30, *, allow_missing=False, candidate_owner=None):
    deadline = _COMMAND_DEADLINE.get()
    if deadline is not None:
        remaining = deadline - time.monotonic()
        require(remaining > 0, 'host_operation_deadline')
        timeout = min(timeout, remaining)
    if candidate_owner is not None:
        require(candidate_owner.scope in {'candidate-pair-validation', CPU_SCOPE, POSTRESTART_SCOPE} and argv[:2] == ['/usr/bin/docker', 'create'],
                'candidate_dispatch_seam_requires_create')
        candidate_owner.mark_create_dispatched()
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
        if getattr(host, 'scope', None) in {'g1-ladder', 'glm-decode-diag'}:
            self.budget_seconds = 14400 if host.scope == 'glm-decode-diag' else 10800
        if getattr(host, 'scope', None) == CONCURRENT_SCOPE:
            self.budget_seconds = 7200
        if getattr(host, 'scope', None) in {CANDIDATE_SCOPE, CPU_SCOPE}:
            self.budget_seconds = host.deadline_epoch - host.start_epoch
        if getattr(host, 'scope', None) == 'glm-decode-diag' and getattr(host, 'mode', None) == 'cpu-profile-only':
            self.budget_seconds = 1200
        self._data = host.read_json('budget.json', missing=True)
        if self._data is not None:
            self._validate()

    def _validate(self):
        super()._validate()
        if getattr(self.host, 'scope', None) in {'glmrepair', 'g1-ladder', 'glm-decode-diag', CONCURRENT_SCOPE, CANDIDATE_SCOPE, CPU_SCOPE}:
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
        if getattr(self.host, 'scope', None) in {'glmrepair', 'g1-ladder', 'glm-decode-diag', CONCURRENT_SCOPE, CANDIDATE_SCOPE, CPU_SCOPE}:
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
        self.mode = data.get('mode') if self.scope == 'glm-decode-diag' else None
        self.decode_capture_policy = copy.deepcopy(data.get('capture', {})) if self.scope == 'glm-decode-diag' else {}
        manifest_count = {'full': 12, 'q1-only': 3, 'q1-256k': 1, 'g1-only': 3, 'glmrepair': 1, 'g1-ladder': 2, 'glm-decode-diag': 3, CONCURRENT_SCOPE: 2, CANDIDATE_SCOPE: 2, CPU_SCOPE: 4, POSTRESTART_SCOPE: 2}[self.scope]
        if self.mode == 'cpu-profile-only':
            manifest_count = 1
        require(isinstance(values, list) and len(values) == manifest_count, 'scope_reviewed_manifests_required')
        self.start_epoch = data.get('start_epoch', data.get('runtime', {}).get('start_epoch')) if isinstance(data, dict) else None
        if self.scope == 'glmrepair':
            self.start_epoch, self.deadline_epoch = self.glmrepair_clock(data)
        elif self.scope == 'g1-ladder':
            self.start_epoch, self.deadline_epoch = self.ladder_clock(data)
        elif self.scope == 'glm-decode-diag':
            self.start_epoch, self.deadline_epoch = self.decode_clock(data)
        elif self.scope == CANDIDATE_SCOPE:
            from .concurrent_validate import validate_clock, auth_fixture_module
            self.start_epoch, self.deadline_epoch = validate_clock(data, data.get('runtime', {}))
            auth_fixture_module().check_pair_receipt(data.get('actual_image_auth_proof', {}), Path(__file__).resolve().parents[2])
            auth_ref = data.get('actual_image_auth_receipt', {})
            auth_path = auth_ref.get('registered_path')
            require(isinstance(auth_path, str) and auth_path.startswith(self.binding.path('logs') + '/'),
                    'candidate_protected_auth_receipt_required')
            self.binding.validate_path('logs', auth_path)
            auth_raw, _ = protected(auth_path, private=True)
            require(hashlib.sha256(auth_raw).hexdigest() == auth_ref.get('sha256') and
                    json.loads(auth_raw) == data['actual_image_auth_proof'], 'candidate_protected_auth_receipt_changed')
            self.candidate_auth = data['actual_image_auth_proof']
            self.concurrent_resource_violations = {}
            require(data.get('candidate_capacity_policy') == concurrent_capacity_policy(), 'candidate_demand_policy_changed')
            require(values == candidate_manifests(self.binding), 'candidate_registered_manifests_changed')
        elif self.scope in {CONCURRENT_SCOPE, CPU_SCOPE, POSTRESTART_SCOPE}:
            if self.scope == POSTRESTART_SCOPE:
                from .postrestart72_run import validate_clock
                self.postrestart_measured_admissions = {'G1': 0, 'Q1': 0}
                self.followup_request = None
                self.followup_admitted = set()
                self.run_session_id = data.get('session_id')
                self.run_source_commit = data.get('source_commit')
                require(isinstance(self.run_source_commit, str) and bool(re.fullmatch(r'[0-9a-f]{40}', self.run_source_commit)),
                        'postrestart_source_commit_required')
                require(isinstance(self.run_session_id, str) and bool(self.run_session_id), 'postrestart_run_session_required')
                self.start_epoch, self.deadline_epoch = validate_clock(data, data.get('runtime', {}))
            elif self.scope == CPU_SCOPE:
                from .concurrent_cpu_run import validate_clock
                self.start_epoch, self.deadline_epoch = validate_clock(data, data.get('runtime', {}))
            else:
                self.start_epoch, self.deadline_epoch = self.concurrent_clock(data)
            require(data.get('concurrent_capacity_policy') == concurrent_capacity_policy(self.scope),
                    'concurrent_saved_capacity_authority_changed')
            self.concurrent_round = None
            self.concurrent_admitted = set()
            self.concurrent_resource_violations = {}
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
            expected = postrestart_manifest(value['placement']) if self.scope == POSTRESTART_SCOPE else cpu_manifest(value['layout'], value['placement']) if self.scope == CPU_SCOPE else candidate_manifest(value['placement'], self.binding) if self.scope == CANDIDATE_SCOPE else concurrent_manifest(value['placement'], value['configured_capacity']) if self.scope == CONCURRENT_SCOPE else glm_decode_diag_manifest(value['configured_capacity'], campaign) if self.scope == 'glm-decode-diag' else g1_ladder_manifest(value['configured_capacity']) if self.scope == 'g1-ladder' else glmrepair_manifest(campaign) if self.scope == 'glmrepair' else command_manifest(value['placement'], value['configured_capacity'], campaign=campaign,
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
        from .postrestart72_budget import PostrestartBudget
        self.budget = PostrestartBudget(self) if self.scope == POSTRESTART_SCOPE else HostBudget(self)
        callbacks = HostCallbacks(**{name: getattr(self, name) for name in HostCallbacks.__dataclass_fields__})
        self.owner = CampaignOwner(campaign, self.manager, callbacks, self.budget,
                                  reviewed_manifest_hashes=self.manifests, lease_factory=lifecycle_lease.acquire_lease,
                                  scope=self.scope if self.scope in {CANDIDATE_SCOPE, CPU_SCOPE, POSTRESTART_SCOPE} else None)

    @staticmethod
    def concurrent_clock(armed):
        runtime = armed.get('runtime') or {}
        start, deadline = runtime.get('start_epoch'), runtime.get('deadline_epoch')
        require(armed.get('campaign') == CONCURRENT_CAMPAIGN and
                'continuation_execution' not in armed and 'start_epoch' not in armed and
                type(start) in (int, float) and type(deadline) in (int, float) and
                math.isfinite(start) and math.isfinite(deadline) and start == 1789890954.308154 and
                deadline == 1789898154.308154 and deadline == start + 7200 and runtime.get('budget_seconds') == 7200 and
                runtime.get('request_max_seconds') == 7200 and
                runtime.get('clock_includes_preparation') is True and
                runtime.get('includes_load_warmup_fitting') is True and
                runtime.get('excludes_source_prep') is True and
                runtime.get('clock_starts') == 'RUN_DISPATCH' and
                runtime.get('restoration_outside_budget') is True,
                'concurrent_fresh_dispatch_clock_required')
        return start, deadline

    @staticmethod
    def decode_clock(armed):
        runtime = armed.get('runtime') or {}
        if armed.get('mode') == 'cpu-profile-only':
            from .decode_diag import validate_profile_clock
            require('continuation_execution' not in armed and 'start_epoch' not in armed,
                    'decode_profile_immutable_clock_required')
            validate_profile_clock(runtime)
            return runtime['start_epoch'], runtime['deadline_epoch']
        start, deadline = runtime.get('start_epoch'), runtime.get('deadline_epoch')
        require('continuation_execution' not in armed and 'start_epoch' not in armed and
                type(start) in (int, float) and type(deadline) in (int, float) and
                math.isfinite(start) and math.isfinite(deadline) and start > 0 and
                deadline == start + 14400 and runtime.get('budget_seconds') == 14400 and
                runtime.get('request_max_seconds') == 7200 and
                runtime.get('clock_includes_preparation') is True and runtime.get('restoration_outside_budget') is True,
                'decode_diagnostic_immutable_clock_required')
        return start, deadline

    @staticmethod
    def ladder_clock(armed):
        runtime = armed.get('runtime') or {}
        start, deadline = runtime.get('start_epoch'), runtime.get('deadline_epoch')
        require('continuation_execution' not in armed and 'start_epoch' not in armed and
                type(start) in (int, float) and type(deadline) in (int, float) and
                math.isfinite(start) and math.isfinite(deadline) and start > 0 and
                deadline == start + 10800 and runtime.get('budget_seconds') == 10800 and
                runtime.get('clock_includes_preparation') is True and runtime.get('restoration_outside_budget') is True,
                'g1_ladder_fresh_immutable_clock_required')
        return start, deadline

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

    def admit_concurrent(self, round_name):
        require(self.scope in {CONCURRENT_SCOPE, CPU_SCOPE, POSTRESTART_SCOPE} and self.owner.phase == 'ACTIVE',
                'concurrent_active_scope_required')
        require(not getattr(self, 'concurrent_resource_violations', {}), 'concurrent_latched_resource_failure')
        expected = ('P' if self.concurrent_round is None else None) if self.scope == POSTRESTART_SCOPE else ('A' if self.concurrent_round is None else 'B' if self.concurrent_round == 'A' else None) if self.scope == CPU_SCOPE else ('long' if self.concurrent_round is None else None)
        require(round_name is not None and round_name == expected, 'concurrent_closed_round_order_required')
        self.budget.checkpoint()
        self.guards(self.owner.lease)
        self.assert_idle()
        require(not self.campaign_containers() and
                all(row['state'] == 'REMOVED' for row in self.owner.resources),
                'concurrent_retire_prior_round_required')
        sample = collect_sample({})
        available = sample['host']['available_bytes']
        policy = concurrent_capacity_policy(self.scope)
        # Conservative capacity reservation, not a claim that caps equal demand.
        require(type(available) is int and available >= sum(policy['caps_bytes'].values()) + policy['os_reserve_bytes'],
                'concurrent_host_available_reserve_unproved')
        gpu_free = {g['uuid']: g.get('free_bytes') for g in sample['gpus']}
        sizes = (65536, 700160)
        manifests = ([postrestart_manifest(p) for p in ('G1', 'Q1')] if self.scope == POSTRESTART_SCOPE else
                     [cpu_manifest(round_name, p) for p in ('G1', 'Q1')] if self.scope == CPU_SCOPE else
                     [concurrent_manifest(p, n) for p, n in zip(('G1', 'Q1'), sizes)])
        for manifest in manifests:
            require(self.manifests.get(digest(manifest)) == manifest, 'concurrent_exact_manifest_required')
            for uuid in manifest['gpu_uuids']:
                require(type(gpu_free.get(uuid)) is int and gpu_free[uuid] >= policy['gpu_reserve_bytes'],
                        'concurrent_gpu_reserve_unproved')
        receipt = {'round': round_name, 'manifests': manifests, 'capacity_policy': policy,
                   'host_available_bytes': available, 'gpu_free_bytes': gpu_free,
                   'actual_allocation': 'NOT_YET_PROVED', 'captured_at': time.time()}
        self.write_json('concurrent-' + round_name + '-admission.json', receipt)
        self.concurrent_round = round_name
        self.concurrent_admitted = {digest(m) for m in manifests}
        return receipt

    @staticmethod
    def concurrent_limits(manifest, container, cgroup):
        placement = manifest['placement']
        expected = postrestart_manifest(placement) if manifest.get('campaign') == POSTRESTART_CAMPAIGN else cpu_manifest(manifest.get('layout'), placement) if manifest.get('campaign') == CPU_CAMPAIGN else candidate_manifest(placement) if manifest.get('campaign') == 'benchrun-candidate-pair-20260920' else concurrent_manifest(placement, manifest['configured_capacity'])
        require(manifest == expected, 'concurrent_exact_manifest_required')
        cap = concurrent_capacity_policy()['caps_bytes'][placement]
        cpus = expected['guest_cpuset']
        config = container['HostConfig']
        memory = {'docker_memory_bytes': config.get('Memory'),
                  'docker_memory_swap_bytes': config.get('MemorySwap'),
                  'cgroup_memory_max': (cgroup / 'memory.max').read_text().strip(),
                  'cgroup_memory_swap_max': (cgroup / 'memory.swap.max').read_text().strip()}
        require(memory == {'docker_memory_bytes': cap, 'docker_memory_swap_bytes': cap,
                           'cgroup_memory_max': str(cap), 'cgroup_memory_swap_max': '0'},
                'concurrent_effective_no_swap_limit_unproved')
        cpu = {'docker_cpuset_cpus': config.get('CpusetCpus'),
               'docker_nano_cpus': config.get('NanoCpus'), 'docker_cpu_quota': config.get('CpuQuota'),
               'docker_cpu_period': config.get('CpuPeriod'),
               'cgroup_cpuset_cpus_effective': (cgroup / 'cpuset.cpus.effective').read_text().strip(),
               'cgroup_cpu_max': (cgroup / 'cpu.max').read_text().strip()}
        require(cpu['docker_cpuset_cpus'] == cpus and cpu_set(cpu['cgroup_cpuset_cpus_effective']) == cpu_set(cpus) and
                all(cpu[k] == 0 for k in ('docker_nano_cpus', 'docker_cpu_quota', 'docker_cpu_period')) and
                bool(re.fullmatch(r'max [1-9][0-9]*', cpu['cgroup_cpu_max'])),
                'concurrent_effective_cpu_limits_unproved')
        if manifest.get('campaign') == POSTRESTART_CAMPAIGN:
            cpu['docker_cpuset_mems'] = config.get('CpusetMems', '')
            cpu['cgroup_cpuset_mems_effective'] = (cgroup / 'cpuset.mems.effective').read_text().strip()
            require(cpu['docker_cpuset_mems'] in ('', '0-7') and
                    cpu_set(cpu['cgroup_cpuset_mems_effective']) == set(range(8)),
                    'postrestart_all_memory_nodes_required')
        return memory, cpu

    def concurrent_pressure(self, row):
        """Latch numeric working-set estimates; raw charges remain independent."""
        policy, charges, reasons, unavailable = concurrent_capacity_policy(getattr(self, 'scope', None)), {}, [], []
        numeric_by_cid = {cid: [] for cid in row['cgroups']}
        valid = lambda value: type(value) is int and value >= 0
        if not hasattr(self, 'concurrent_demand_peaks'):
            self.concurrent_demand_peaks = {}
        for cid, group in row['cgroups'].items():
            manifest = self.load_manifests[cid]
            current, peak = group.get('current_bytes'), group.get('peak_since_cgroup_creation_bytes')
            floor, basis = None, 'UNAVAILABLE_no_native_host_weight_measurement'
            parsed = self.allocation_proofs.get(cid)
            if manifest['placement'] == 'G1':
                floor, basis = policy['G1_native_floor']['bytes'], policy['G1_native_floor']['basis']
                if parsed is not None:
                    weights = parsed.get('host_weights_mib_log_label') or {}
                    workspace = parsed.get('host_workspace_bytes')
                    if weights and all(type(v) in (int, float) and math.isfinite(v) and v >= 0 for v in weights.values()) and valid(workspace):
                        floor = max(floor, sum(math.ceil((v + 0.005) * 1024**2) for v in weights.values()) + workspace)
                        basis = 'max(same-pin historical floor,current accepted native rounded-up host weights+exact workspace)'
            demand = concurrent_host_demand(group, row.get('processes', {}).get(cid, {}),
                native_floor_bytes=floor, native_floor_basis=basis)
            observed = demand['required_bytes']
            if observed is None:
                unavailable.append('concurrent_required_demand_estimate_unavailable')
            else:
                self.concurrent_demand_peaks[cid] = max(observed, self.concurrent_demand_peaks.get(cid, 0))
            sampled_peak = self.concurrent_demand_peaks.get(cid)
            known = [v for v in (sampled_peak, demand['known_numeric_floor_bytes']) if valid(v)]
            comparison = max(known) if known else None
            cap = policy['caps_bytes'][manifest['placement']]
            numeric_failure = comparison is not None and policy['host_headroom_numerator'] * comparison > policy['host_headroom_denominator'] * cap
            charges[cid] = {**demand, 'current_bytes': current, 'lifetime_peak_bytes': peak,
                            'component_charge_bytes': demand['component_bracket_bytes'],
                            'headroom_comparison_bytes': comparison, 'sampled_peak_required_bytes': sampled_peak,
                            'placement': manifest['placement'], 'cap_bytes': cap,
                            'allocation_proof_available': parsed is not None,
                            ('cap_headroom_15_percent' if getattr(self, 'scope', None) in {CPU_SCOPE, POSTRESTART_SCOPE} else 'cap_headroom_25_percent'): False if numeric_failure else True if observed is not None else None,
                            'headroom_numerator': policy['host_headroom_numerator'], 'headroom_denominator': policy['host_headroom_denominator']}
            if getattr(self, 'scope', None) in {CPU_SCOPE, POSTRESTART_SCOPE}:
                charges[cid].update(sampled_required_working_set_estimate_bytes=comparison,
                    required_with_headroom_bytes=((comparison * 23 + 19) // 20 if comparison is not None else None),
                    host_headroom_policy=policy['host_headroom_policy'])
            if numeric_failure:
                numeric_by_cid[cid].append('concurrent_cap_15_percent_headroom_failed' if getattr(self, 'scope', None) in {CPU_SCOPE, POSTRESTART_SCOPE} else 'concurrent_cap_25_percent_headroom_failed')
            if any(valid(v) and v > cap for v in (current, peak)):
                numeric_by_cid[cid].append('concurrent_raw_hard_cap_exceeded')
        available = row['host'].get('available_bytes')
        if type(available) is not int:
            unavailable.append('concurrent_host_available_unavailable')
        elif available < policy['os_reserve_bytes']:
            reasons.append('concurrent_host_reserve_failed')
            for numeric in numeric_by_cid.values():
                numeric.append('concurrent_host_reserve_failed')
        free = {g['uuid']: g.get('free_bytes') for g in row['gpus']}
        for cid in row['cgroups']:
            for uuid in self.load_manifests[cid]['gpu_uuids']:
                if type(free.get(uuid)) is not int:
                    unavailable.append('concurrent_gpu_free_unavailable')
                elif free[uuid] < policy['gpu_reserve_bytes']:
                    numeric_by_cid[cid].append('concurrent_gpu_reserve_failed')
        if getattr(self, 'scope', None) in {CPU_SCOPE, POSTRESTART_SCOPE}:
            for cid in row['cgroups']:
                if self.load_manifests[cid]['placement'] == 'Q1':
                    gpu = next((g for g in row['gpus'] if g['uuid'] == self.load_manifests[cid]['gpu_uuids'][0]), {})
                    total, remaining = gpu.get('total_bytes'), gpu.get('free_bytes')
                    if not (type(total) is int and total > 0 and type(remaining) is int):
                        unavailable.append('cpu_qwen_ten_percent_unavailable')
                    elif remaining * 10 < total:
                        numeric_by_cid[cid].append('cpu_qwen_ten_percent_failed')
        if getattr(self, 'scope', None) == POSTRESTART_SCOPE:
            # Full *current* resource evidence, not a historical peak or a
            # literal read-error exemption. Missing observations never become
            # zeros; independently observed danger wins over incomplete proof.
            observed_gpus = [g.get('uuid') for g in row['gpus']]
            expected_gpus = set(self.config['gpu_uuids'])
            if (any(isinstance(uuid, str) and uuid not in expected_gpus for uuid in observed_gpus)
                    or len(observed_gpus) != len(set(observed_gpus))
                    or set(row.get('processes', {})) - set(self.load_manifests)):
                for faults in numeric_by_cid.values():
                    faults.append('postrestart_observed_identity_changed')
            if row.get('errors') != [] or not all(valid(row.get('vmstat', {}).get(k)) for k in
                    ('pgfault', 'pgmajfault', 'pswpin', 'pswpout', 'oom_kill')):
                unavailable.append('postrestart_sample_incomplete')
            if (not row['cgroups'] or set(row['cgroups']) != set(self.load_manifests)
                    or set(row['cgroups']) != set(row.get('processes', {}))):
                unavailable.append('postrestart_process_inventory_incomplete')
            for cid, group in row['cgroups'].items():
                process = row.get('processes', {}).get(cid, {})
                events = group.get('events', {})
                if (not all(valid(group.get(k)) for k in ('current_bytes', 'peak_since_cgroup_creation_bytes',
                        'file_bytes', 'anon_bytes', 'kernel_bytes', 'file_mapped_bytes', 'shmem_bytes', 'swap_bytes'))
                        or not all(valid(events.get(k)) for k in ('oom', 'oom_kill', 'oom_group_kill'))
                        or not all(valid(process.get(k)) for k in ('rss_bytes', 'swap_bytes'))
                        or not valid(process.get('known_process_count')) or process['known_process_count'] == 0):
                    unavailable.append('postrestart_owned_resource_incomplete')
                if any(valid(events.get(k)) and events[k] > 0 for k in ('oom', 'oom_kill', 'oom_group_kill')):
                    numeric_by_cid[cid].append('postrestart_owned_oom')
                if any(valid(v) and v > 0 for v in (group.get('swap_bytes'), process.get('swap_bytes'))):
                    numeric_by_cid[cid].append('postrestart_owned_swap')
        if not hasattr(self, 'concurrent_resource_violations'):
            self.concurrent_resource_violations = {}
        for cid, numeric in numeric_by_cid.items():
            if numeric:
                prior = self.concurrent_resource_violations.setdefault(cid, {
                    'reasons': [], 'first_sample_monotonic_s': row.get('timestamp_monotonic_s'),
                    'first_charge': copy.deepcopy(charges.get(cid)), 'host_available_bytes': available,
                    'gpu_free_bytes': copy.deepcopy(free)})
                prior['reasons'] = sorted(set(prior['reasons'] + numeric))
        for violation in self.concurrent_resource_violations.values():
            reasons.extend(violation['reasons'])
        return {'status': 'STOP_RESOURCE_GATE' if reasons else 'UNAVAILABLE' if unavailable else 'PASS',
                'reasons': sorted(set(reasons)), 'unavailable_reasons': sorted(set(unavailable)),
                'charges': charges, 'host_available_bytes': available,
                'latched_violations': copy.deepcopy(self.concurrent_resource_violations),
                'policy': policy['evidence_status'], 'required_demand_helper': 'ROOT_REVIEWED_WORKING_SET_ESTIMATE'}

    def candidate_container(self, manifest, container):
        """Production launch policy with the reviewed campaign mount exceptions."""
        cp, qwen = candidate_modules()
        d = candidate_profile(manifest['placement'], self.binding)
        cp.validate_reuse(container, d)
        qwen.validate_container_network(container, d['endpoint']['port'], d['container_port'])
        config = container['Config']
        expected_cmd = manifest['native_argv'] if manifest['placement'] == 'G1' else [qwen.PAIR_LAUNCHER_TARGET]
        require(config.get('Cmd') == expected_cmd and config.get('Entrypoint') == d['_runtime']['entrypoint']
                and config.get('Image') == manifest['image'] and container['Image'] in manifest['expected_image_ids'],
                'candidate_container_launch_changed')
        qwen_slot = manifest['placement'] == 'Q1'
        mounts = container.get('Mounts', [])
        require(isinstance(mounts, list) and all(isinstance(m, dict) for m in mounts),
                'candidate_container_mounts_changed')
        tmpfs = [m for m in mounts if m.get('Type') == 'tmpfs']
        require(len(tmpfs) <= (1 if qwen_slot else 0) and all(
                m.get('Destination') == '/tmp' and m.get('Source', '') == '' and m.get('RW') is True
                for m in tmpfs), 'candidate_container_mounts_changed')
        binds = [m for m in mounts if m not in tmpfs]
        expected = {(m['target'], m['source'], m['read_only']) for m in manifest['mounts']}
        require(len(binds) == len(expected) and all(m.get('Type') == 'bind' and type(m.get('RW')) is bool
                and m.get('Propagation') in ('rprivate', '') for m in binds) and
                {(m.get('Destination'), m.get('Source'), not m['RW']) for m in binds} == expected,
                'candidate_container_mounts_changed')
        env = dict(item.split('=', 1) for item in config.get('Env', []))
        if qwen_slot:
            inherited = d['_runtime']['image_environment']
        else:
            # The GLM declaration pins its immutable image rather than an Env
            # inventory. Read that exact image once; its ID cannot change bytes.
            inherited = getattr(self, '_candidate_glm_image_environment', None)
            if inherited is None:
                images = json.loads(command(['/usr/bin/docker', 'image', 'inspect', manifest['image']]).stdout)
                require(isinstance(images, list) and len(images) == 1 and images[0].get('Id') == manifest['image']
                        and images[0].get('Config', {}).get('Entrypoint') == d['_runtime']['entrypoint'],
                        'candidate_image_environment_unavailable')
                entries = images[0]['Config'].get('Env', [])
                require(isinstance(entries, list) and all(isinstance(item, str) and '=' in item for item in entries),
                        'candidate_image_environment_unavailable')
                inherited = dict(item.split('=', 1) for item in entries)
                require(len(inherited) == len(entries), 'candidate_image_environment_unavailable')
                self._candidate_glm_image_environment = inherited
        expected_env = {**inherited, **d['_runtime']['environment'], **d['launch_environment']}
        require(env == expected_env, 'candidate_runtime_environment_changed')
        host = container['HostConfig']
        require(host.get('CapDrop') == ['ALL'] and not host.get('CapAdd')
                and host.get('SecurityOpt') == ['no-new-privileges:true']
                and host.get('LogConfig') == {'Type': 'json-file', 'Config': {'max-size': '20m', 'max-file': '3'}}
                and not any(host.get(key) for key in ('Devices', 'DeviceCgroupRules', 'VolumesFrom', 'Binds', 'PidMode', 'UTSMode'))
                and host.get('IpcMode', 'private') == 'private', 'candidate_security_policy_changed')
        if qwen_slot:
            require(config.get('WorkingDir') == '/service' and config.get('User') == '0'
                    and config.get('Healthcheck') == {'Test': ['NONE']}
                    and host.get('ReadonlyRootfs') is True and host.get('ShmSize') == 8 * 1024**3
                    and host.get('Tmpfs') == {'/tmp': 'rw,nosuid,nodev,size=1g'}, 'candidate_qwen_process_storage_changed')
            limits = host.get('Ulimits')
            require(isinstance(limits, list) and all(isinstance(limit, dict) for limit in limits),
                    'candidate_qwen_core_limit_changed')
            core = [limit for limit in limits if limit.get('Name') == 'core']
            require(len(core) == 1 and type(core[0].get('Soft')) is int and core[0]['Soft'] == 1
                    and type(core[0].get('Hard')) is int and core[0]['Hard'] == 1,
                    'candidate_qwen_core_limit_changed')

    def candidate_pressure(self, row):
        """Same root-reviewed sampled ESTIMATE as LongPREP; stricter pair admission."""
        from .concurrent_validate import memory_obligations
        available = row['host'].get('available_bytes')
        # Preserve raw telemetry; invalid availability is no numeric comparison.
        pressure_row = row if type(available) is int and available >= 0 else {
            **row, 'host': {**row['host'], 'available_bytes': None}}
        result = self.concurrent_pressure(pressure_row)
        extra, unavailable = [], []
        try:
            result['remaining_cap_obligations'] = memory_obligations(row, self.load_manifests)
        except ValueError as error:
            result['remaining_cap_obligations'] = None
            # Only a complete comparison can establish insufficient reserve.
            # Missing/inconsistent accounting blocks admission without claiming
            # numeric pressure or cancelling a healthy admitted request.
            if str(error) == 'candidate_remaining_caps_host_reserve_failed':
                extra.append('candidate_remaining_caps_host_reserve_failed')
            else:
                unavailable.append('candidate_remaining_caps_accounting_unavailable')
        for group in row['cgroups'].values():
            if type(group.get('swap_bytes')) is not int or group['swap_bytes'] < 0:
                unavailable.append('candidate_owned_swap_unavailable')
            elif group['swap_bytes'] != 0:
                extra.append('candidate_owned_swap_failed')
            if any(type(group.get('events', {}).get(k)) is int and group['events'][k] > 0
                   for k in ('oom', 'oom_kill', 'oom_group_kill')):
                extra.append('candidate_oom_failed')
        qwen_uuid = candidate_modules()[0].GPU_UUIDS[1]
        qwen = next((g for g in row['gpus'] if g['uuid'] == qwen_uuid), {})
        total, free = qwen.get('total_bytes'), qwen.get('free_bytes')
        if type(total) is not int or type(free) is not int:
            unavailable.append('candidate_qwen_ten_percent_unavailable')
        elif free * 10 < total:
            extra.append('candidate_qwen_ten_percent_failed')
        if extra:
            previous = self.concurrent_resource_violations.setdefault('candidate', {'reasons': []})
            previous['reasons'] = sorted(set(previous['reasons'] + extra))
        latched = [r for v in self.concurrent_resource_violations.values() for r in v['reasons']]
        result['reasons'] = sorted(set(result['reasons'] + latched))
        result['unavailable_reasons'] = sorted(set(result['unavailable_reasons'] + unavailable))
        result['latched_violations'] = copy.deepcopy(self.concurrent_resource_violations)
        result['status'] = 'STOP_RESOURCE_GATE' if result['reasons'] else 'UNAVAILABLE' if result['unavailable_reasons'] else 'PASS'
        return result

    @staticmethod
    def concurrent_cpu_pressure(cgroups):
        """Cheap counters/PSI only; no process maps or profiler activity."""
        def read(path, kind):
            try:
                text = path.read_text()
                require(len(text) <= 16384, 'concurrent_pressure_file_bound')
                if kind == 'cpu':
                    return {cells[0]: int(cells[1]) for line in text.splitlines()
                            if len(cells := line.split()) == 2 and cells[0] in
                            {'usage_usec', 'user_usec', 'system_usec', 'nr_periods', 'nr_throttled', 'throttled_usec'}
                            and cells[1].isdigit()}
                out = {}
                for line in text.splitlines():
                    cells = line.split()
                    if cells and cells[0] in {'some', 'full'}:
                        values = {}
                        for cell in cells[1:]:
                            key, value = cell.split('=', 1)
                            if key in {'avg10', 'avg60', 'avg300', 'total'}:
                                number = int(value) if key == 'total' else float(value)
                                require(math.isfinite(number) and number >= 0, 'concurrent_pressure_value_invalid')
                                values[key] = number
                        out[cells[0]] = values
                return out
            except (OSError, ValueError):
                return None
        return {'host': {kind: read(Path('/proc/pressure') / kind, 'psi') for kind in ('cpu', 'memory')},
                'cgroups': {cid: {'cpu_stat': read(path / 'cpu.stat', 'cpu'),
                                 'cpu_pressure': read(path / 'cpu.pressure', 'psi'),
                                 'memory_pressure': read(path / 'memory.pressure', 'psi')}
                            for cid, path in cgroups.items()}}

    def rpc_diagnostics(self):
        """Read only existing bounded safe code/frame receipts; no raw exception text."""
        path = self.binding.validate_path('logs', self.log_root + '/rpc-errors')
        if not path.exists():
            return {'diagnostics': [], 'missing': True}
        rows = []
        files = sorted(path.iterdir(), key=lambda p: p.name)
        require(len(files) <= 256, 'rpc_diagnostic_inventory_bound')
        for file in files[-16:]:
            require(bool(re.fullmatch(r'[0-9]+-[a-f0-9]{16}\.json', file.name)), 'rpc_diagnostic_name_invalid')
            data = self.read_json('rpc-errors/' + file.name)
            frames = data.get('frames', [])
            require(isinstance(frames, list) and len(frames) <= 16, 'rpc_diagnostic_frames_invalid')
            projected = []
            for frame in frames:
                require(isinstance(frame, dict) and
                        bool(re.fullmatch(r'[A-Za-z0-9_.-]{1,128}', frame.get('source', ''))) and
                        bool(re.fullmatch(r'[A-Za-z0-9_<>]{1,128}', frame.get('function', ''))) and
                        type(frame.get('line')) is int and frame['line'] > 0, 'rpc_diagnostic_frame_invalid')
                projected.append({key: frame[key] for key in ('source', 'function', 'line')})
            exception = data.get('exception_class', '')
            require(bool(re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,63}', exception)), 'rpc_diagnostic_class_invalid')
            rows.append({'file': file.name, 'operation': data.get('operation') if data.get('operation') in RPC_OPERATIONS else 'unknown',
                         'exception_class': exception, 'require_code': data.get('require_code') if data.get('require_code') in RPC_SAFE_REQUIRE_CODES else None,
                         'frames': projected})
        return {'diagnostics': rows, 'missing': False, 'scope': 'saved_safe_RPC_identity_only'}

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
        if stage in {'admission', 'production_stop', 'restore', 'retire', 'stop', 'remove', 'pre_release', 'warm_hold'}:
            self.assert_idle()
        if self.scope in {CPU_SCOPE, POSTRESTART_SCOPE} and stage == 'admission':
            from .cpu_budget_host import pre_retirement_admission
            self.write_json('cpu-pre-retirement-admission.json', pre_retirement_admission(self, original))
        if self.scope == CANDIDATE_SCOPE and stage == 'admission':
            from .concurrent_validate import admission, preserve
            require(original['manager']['selected'] == 'qwen38-27b-1000000-yarn4-tp2-bf16kv'
                    and original['manager']['desired'] == 'running', 'candidate_original_singleton_required')
            self.write_json('candidate-pre-retirement-admission.json', admission(self))
            preserve(self)
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
            if self.scope in {CANDIDATE_SCOPE, CPU_SCOPE, POSTRESTART_SCOPE}:
                require(self.owner.pending_create is None, 'unresolved_create_intent')
                self.owner.pending_create = {'manifest_sha256': digest(manifest), 'name': name,
                    'image': manifest['image'], 'campaign': self.campaign,
                    'dispatch': 'not_dispatched', 'kind': 'mapping_helper'}
                self.owner._save()
            self.guards(lease)
            dispatch = {'candidate_owner': self.owner} if self.scope in {CANDIDATE_SCOPE, CPU_SCOPE, POSTRESTART_SCOPE} else {}
            cid = command([*probe, check], 60, **dispatch).stdout.decode().strip()
            require(bool(CID.fullmatch(cid)), 'mapping_helper_create_identity_invalid')
            container = self.docker_inspect(cid)
            resource = self.owner._resource(self.resource(container))
            require(resource['name'] == name and resource['image_id'] in manifest['expected_image_ids'],
                    'mapping_helper_image_changed')
            row = {'resource': resource, 'state': 'CREATED'}
            self.owner.resources.append(row)
            if self.scope in {CANDIDATE_SCOPE, CPU_SCOPE, POSTRESTART_SCOPE}:
                self.owner.pending_create = None
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
        if self.scope in {'g1-only', 'glmrepair', 'g1-ladder', 'glm-decode-diag'}:
            available = collect_sample({})['host']['available_bytes']
            require(type(available) is int and available >= G1_RAM_CAP_BYTES + 16 * 1024**3,
                    'g1_container_cap_host_reserve_unproved')
        if self.scope in {CONCURRENT_SCOPE, CPU_SCOPE, POSTRESTART_SCOPE}:
            require(digest(manifest) in self.concurrent_admitted, 'concurrent_round_not_admitted')
            require(not getattr(self, 'concurrent_resource_violations', {}), 'concurrent_latched_resource_failure')
            active = [row['resource']['id'] for row in self.owner.resources if row['state'] != 'REMOVED'
                      and row['resource']['id'] in self.load_manifests]
            require(all(self.load_manifests[cid]['placement'] != manifest['placement'] for cid in active),
                    'concurrent_duplicate_model_lane')
            policy = concurrent_capacity_policy(self.scope)
            occupied = {self.load_manifests[cid]['placement'] for cid in active}
            remaining = sum(cap for placement, cap in policy['caps_bytes'].items() if placement not in occupied)
            available = collect_sample({})['host']['available_bytes']
            require(type(available) is int and available >= remaining + policy['os_reserve_bytes'],
                    'concurrent_host_available_reserve_unproved')
        if self.scope in {CPU_SCOPE, POSTRESTART_SCOPE}:
            from .cpu_budget_host import resident_obligations
            self.write_json('cpu-preload-' + manifest['layout'] + '-' + manifest['placement'] + '.json', resident_obligations(self))
        if self.scope == CANDIDATE_SCOPE:
            from .concurrent_validate import admission
            require(not any(self.load_manifests.get(r['resource']['id'], {}).get('placement') == manifest['placement']
                            for r in self.owner.resources if r['state'] != 'REMOVED'), 'candidate_duplicate_load')
            require(manifest['placement'] == ('Q1' if self.load_manifests else 'G1'), 'candidate_fixed_load_order')
            self.write_json('candidate-preload-' + manifest['placement'] + '.json', admission(self))
            cp, qwen = candidate_modules()
            d = candidate_profile(manifest['placement'], self.binding)
            if manifest['placement'] == 'Q1':
                # Same protected bytes as validate_launcher; the not-yet-installed
                # pair wrapper is read only from the reviewed guarded source stage.
                for rel, path in [('scripts/runtime/sglang38_file_auth.py', self.binding.path('data', qwen.LAUNCHER_SUFFIX)),
                                  ('scripts/runtime/sglang38_pair_file_auth.py', manifest['registered_paths']['source'] + '/scripts/runtime/sglang38_pair_file_auth.py')]:
                    raw, _ = protected(path)
                    require(hashlib.sha256(raw).hexdigest() == cp.PINS[rel], 'candidate_protected_wrapper_changed')
        self.mkdir_paths(manifest)
        argv = ['/usr/bin/docker', *manifest['create_argv'][1:]]
        dispatch = {'candidate_owner': self.owner} if self.scope in {CANDIDATE_SCOPE, CPU_SCOPE, POSTRESTART_SCOPE} else {}
        created = command(argv, 120, **dispatch).stdout.decode().strip()
        require(bool(CID.fullmatch(created)), 'invalid_created_container_id')
        container = self.docker_inspect(created)
        if self.scope == CANDIDATE_SCOPE:
            self.candidate_container(manifest, container)
        if self.scope in {'g1-only', 'glmrepair', 'g1-ladder', 'glm-decode-diag'}:
            require(container['HostConfig'].get('Memory') == G1_RAM_CAP_BYTES and
                    container['HostConfig'].get('MemorySwap') == G1_RAM_CAP_BYTES,
                    'g1_container_no_swap_limit_unproved')
        if self.scope in {CONCURRENT_SCOPE, CPU_SCOPE, POSTRESTART_SCOPE}:
            cap = concurrent_capacity_policy()['caps_bytes'][manifest['placement']]
            require(container['HostConfig'].get('Memory') == cap and container['HostConfig'].get('MemorySwap') == cap,
                    'concurrent_container_no_swap_limit_unproved')
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
        if self.scope == CANDIDATE_SCOPE:
            manifest = next((m for m in self.manifests.values() if m['container_name'] == container['Name'].removeprefix('/')), None)
            if manifest is not None:
                self.candidate_container(manifest, container)
            else:
                require(container['Name'].removeprefix('/') in {self.campaign + '-mapping-helper-g',
                        self.campaign + '-mapping-helper-q'}, 'candidate_unreviewed_owned_identity')
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
        if self.scope == CANDIDATE_SCOPE:
            from .concurrent_validate import identity_stamp
            before_identity = identity_stamp(self, cid)
        options = {'decode_diagnostic': True} if self.scope == 'glm-decode-diag' else {}
        groups, members = {cid: cgroup}, {cid: pids}
        if self.scope in {CONCURRENT_SCOPE, CANDIDATE_SCOPE, CPU_SCOPE, POSTRESTART_SCOPE}:
            for resource in self.owner.resources:
                peer = resource['resource']['id']
                if resource['state'] == 'RUNNING' and peer != cid and peer in self.load_manifests:
                    _, groups[peer], members[peer] = self.identity(peer)
        row = collect_sample(groups, pids=members, **options)
        if self.scope in {CONCURRENT_SCOPE, CANDIDATE_SCOPE, CPU_SCOPE, POSTRESTART_SCOPE}:
            row['concurrent_resource_gate'] = self.candidate_pressure(row) if self.scope == CANDIDATE_SCOPE else self.concurrent_pressure(row)
            row['cpu_pressure'] = self.concurrent_cpu_pressure(groups)
        if self.scope == 'glm-decode-diag':
            previous = getattr(self, '_decode_last_sample', {}).get(cid, float('-inf'))
            if collection_started - previous >= 5:
                from .decode_telemetry import collect_decode_sample
                try:
                    row['decode_cpu'] = collect_decode_sample({cid: cgroup}, pids={cid: pids})
                except Exception as exc:
                    row['decode_cpu'] = {'status': 'UNAVAILABLE', 'error_class': type(exc).__name__}
                if not hasattr(self, '_decode_last_sample'):
                    self._decode_last_sample = {}
                self._decode_last_sample[cid] = collection_started
        if self.scope in {CPU_SCOPE, POSTRESTART_SCOPE}:
            from .cpu_budget_telemetry import collect_sample as collect_cpu
            row['cpu_budget'] = collect_cpu(groups, pids=members)
        row['collection_duration_s'] = time.monotonic() - collection_started
        self.samples.setdefault(cid, []).append(row)
        # Do not run heavy root-payload guards or write at 1 Hz. Worker persists
        # telemetry privately; host retains bounded summary samples in memory.
        self.samples[cid] = self.samples[cid][-21610:]
        manifest = self.load_manifests.get(cid, {})
        placement = manifest.get('placement')
        parsed = self.allocation_proofs.get(cid)
        if self.scope in {CONCURRENT_SCOPE, CANDIDATE_SCOPE, CPU_SCOPE, POSTRESTART_SCOPE}:
            # The legacy helper claims measured components and double-counts this
            # mapped/shmem overlap. This closed campaign reports only ESTIMATE.
            row['required_host_demand'] = copy.deepcopy(row['concurrent_resource_gate']['charges'][cid])
            evidence = row['required_host_demand']
            evidence.update(container_id=cid, manifest_sha256=digest(manifest),
                sample_timestamp_monotonic_s=row.get('timestamp_monotonic_s'),
                sample_phase='ready_runtime' if parsed is not None else 'pre_readiness_load',
                sampled_peak_not_absolute=True)
            if evidence['required_bytes'] is not None:
                previous = self.measured.get(placement, {})
                if evidence['required_bytes'] >= previous.get('required_bytes', 0):
                    self.measured[placement] = copy.deepcopy(evidence)
            if self.scope == CANDIDATE_SCOPE:
                require(before_identity == identity_stamp(self, cid), 'candidate_sampling_identity_changed')
                row['identity'] = before_identity
            return row
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

        if self.scope == CANDIDATE_SCOPE:
            require(before_identity == identity_stamp(self, cid), 'candidate_sampling_identity_changed')
            row['identity'] = before_identity
        return row

    def quiescent(self, cid, point):
        require(point in {'readiness', 'warm_idle'}, 'pss_checkpoint_only')
        self.assert_idle()
        container, cgroup, pids = self.identity(cid)
        if self.scope == POSTRESTART_SCOPE:
            from .cpu_budget_host import postrestart_cpu_anchor
            cpu_anchor = postrestart_cpu_anchor(container, cgroup)
        if self.scope in {CONCURRENT_SCOPE, CANDIDATE_SCOPE, CPU_SCOPE, POSTRESTART_SCOPE}:
            result = {'point': point, 'pss_bytes': None, 'pss_unavailable_reason': 'concurrent_no_profiling',
                      'container_id': cid, 'scope': 'cheap_quiescent_counters', 'telemetry': self.telemetry(cid)}
            if self.scope == CPU_SCOPE:
                from .cpu_budget_telemetry import numa_snapshot
                result['numa_pages'] = numa_snapshot({cid: pids})
            if self.scope == POSTRESTART_SCOPE:
                require(result['telemetry']['concurrent_resource_gate']['status'] != 'STOP_RESOURCE_GATE',
                        'concurrent_current_resource_gate_failed')
                from .cpu_budget_host import coherent_postrestart_cpu_proof
                result['actual_cpu_scope'] = coherent_postrestart_cpu_proof(self, cid, self.load_manifests[cid], expected_anchor=cpu_anchor)
                numa = result['actual_cpu_scope']['numa_pages']
                result['numa_pages'] = {**numa, 'processes': {cid: numa['processes']['owned']}}
            self.write_json('loads/' + cid + '-' + point + '.json', result)
            return result
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
        if self.scope == 'glm-decode-diag':
            from .decode_telemetry import quiescent_snapshot
            try:
                result['decode_quiescent'] = quiescent_snapshot({cid: pids})
            except Exception as exc:
                result['decode_quiescent'] = {'status': 'UNAVAILABLE', 'error_class': type(exc).__name__}
        self.write_json('loads/' + cid + '-' + point + '.json', result)
        return result

    def decode_progress(self, cid):
        """Explicit bounded snapshot, never called by the periodic sampler."""
        require(self.scope == 'glm-decode-diag' and self.owner.phase == 'ACTIVE', 'decode_scope_required')
        require(cid in self.requests, 'decode_request_not_registered')
        self.identity(cid)
        start = time.monotonic()
        slots = http_json(31002, '/slots', timeout_s=5)
        end = time.monotonic()
        require(isinstance(slots, list) and len(slots) == 1, 'native_single_slot_required')
        slot = slots[0]
        require(isinstance(slot, dict), 'native_slot_object_required')
        # Retained b29c606 server-context.cpp:707 explicitly emits a singleton
        # array. Accept the direct object shape defensively, without guessing
        # counters from tokens, SSE events or any other fields.
        next_token = slot.get('next_token')
        if isinstance(next_token, list):
            next_token = next_token[0] if len(next_token) == 1 else None
        count = next_token.get('n_decoded') if isinstance(next_token, dict) else None
        if type(count) is not int or count < 0:
            count = None
        return {'slot_id': slot.get('id') if type(slot.get('id')) is int else None,
                'task_id': slot.get('id_task') if type(slot.get('id_task')) is int else None,
                'is_processing': slot.get('is_processing') if type(slot.get('is_processing')) is bool else None,
                'n_decoded': count,
                'counter_status': 'AVAILABLE' if count is not None else 'UNAVAILABLE',
                'host_started_monotonic_s': start, 'host_finished_monotonic_s': end}

    def decode_cpu_capture_start(self, cid, client_before):
        from .decode_capture import CpuCapture
        require(self.scope == 'glm-decode-diag' and self.owner.phase == 'ACTIVE', 'decode_scope_required')
        require(getattr(self, 'decode_capture_policy', {}).get('cpu') is True, 'decode_cpu_capture_not_armed')
        require(cid in self.requests, 'decode_request_not_registered')
        require(not getattr(self, '_decode_cpu_captures', {}), 'decode_cpu_single_sample_no_retry')
        capture = CpuCapture(self, cid, client_before)
        self._decode_cpu_captures = {capture.capture_id: capture}
        return capture.start()

    def decode_cpu_capture_status(self, cid, capture_id, client_after=None):
        require(self.scope == 'glm-decode-diag', 'decode_scope_required')
        capture = getattr(self, '_decode_cpu_captures', {}).get(capture_id)
        require(capture is not None and capture.cid == cid, 'decode_capture_identity_mismatch')
        return capture.status(client_after)

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
        if self.scope == POSTRESTART_SCOPE:
            from .cpu_budget_host import postrestart_cpu_anchor
            cpu_anchor = postrestart_cpu_anchor(container, cgroup)
        if self.scope == CANDIDATE_SCOPE:
            from .concurrent_validate import identity_stamp
            allocation_identity = identity_stamp(self, cid)
        manifest = self.load_manifests.get(cid) or self.read_json('loads/' + cid + '.json')['manifest']
        result = command(['/usr/bin/docker', 'logs', '--tail', '20000', cid], 60)
        raw = result.stdout + result.stderr
        require(len(raw) <= 16 * 1024 * 1024, 'allocation_log_too_large')
        # The protected raw log is never returned to the worker JSON channel.
        self.write_bytes('loads/' + cid + '-allocation.log', raw)
        text = raw.decode('utf-8', 'replace')
        port = manifest['transport']['port']
        facts = {}
        native_capacity = None
        if manifest['placement'].startswith('Q'):
            try:
                info = http_json(port, '/get_server_info')
            except TimeoutError as error:
                raise NativeInfoPending from error
            if self.scope in {CPU_SCOPE, POSTRESTART_SCOPE}:
                from .cpu_budget_host import qwen_native_diagnostic
                self.write_json('loads/' + cid + '-native-numeric-diagnostic.json', qwen_native_diagnostic(info))
            if self.scope == POSTRESTART_SCOPE:
                from .cpu_budget_host import qwen_native_view
                args = qwen_native_view(info)
            else:
                args = info.get('server_args', info)
            require(isinstance(args, dict), 'native_server_args_unavailable')
            facts = {key: args.get(key, info.get(key)) for key in
                     ('tp_size', 'context_length', 'max_total_tokens', 'max_total_num_tokens', 'kv_cache_dtype', 'quantization',
                      'disable_radix_cache')}
            if facts['max_total_num_tokens'] is None:
                internal = info.get('internal_states', [])
                if isinstance(internal, list) and len(internal) == 1 and isinstance(internal[0], dict):
                    facts['max_total_num_tokens'] = internal[0].get('max_total_num_tokens')
            if self.scope == CANDIDATE_SCOPE:
                from .concurrent_validate import native_proof
                native_capacity = native_proof(self, cid, info)
                facts['max_total_num_tokens'] = native_capacity['native_pool_tokens']
            if self.scope in {CPU_SCOPE, POSTRESTART_SCOPE}:
                from .cpu_budget_host import qwen_native_proof
                native_capacity = qwen_native_proof(info, **({'scope': POSTRESTART_SCOPE} if self.scope == POSTRESTART_SCOPE else {}))
                facts['max_total_num_tokens'] = native_capacity['native_pool_tokens']
            parsed = parse_qwen_log(text, facts)
            receipts = [json.loads(line.split('BENCHMARK_NATIVE_ARGV ', 1)[1])['argv'] for line in text.splitlines()
                        if 'BENCHMARK_NATIVE_ARGV ' in line]
            native = receipts[0] if len(receipts) == 1 else None
            if self.scope == CANDIDATE_SCOPE:
                native = manifest['native_argv']  # resolving-view validation above, not argv-only proof
        else:
            parsed, native = parse_glm_log(text), container['Config']['Cmd']
            if self.scope == CANDIDATE_SCOPE:
                from .concurrent_validate import native_proof
                native_capacity = native_proof(self, cid)
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
        if self.scope in {'g1-only', 'glmrepair', 'g1-ladder', 'glm-decode-diag'}:
            observed['container_memory_limits'] = self.g1_memory_limits(container, cgroup)
        if self.scope in {'glmrepair', 'g1-ladder', 'glm-decode-diag'}:
            observed['container_cpu_limits'] = self.glmrepair_cpu_limits(container, cgroup)
        if self.scope in {CONCURRENT_SCOPE, CANDIDATE_SCOPE, CPU_SCOPE, POSTRESTART_SCOPE}:
            memory, cpu = self.concurrent_limits(manifest, container, cgroup)
            observed.update(container_memory_limits=memory, container_cpu_limits=cpu)
        gate = allocation_gate(manifest, parsed, observed, strict_g1=self.scope in {'g1-only', 'g1-ladder', 'glm-decode-diag', CONCURRENT_SCOPE, CANDIDATE_SCOPE, CPU_SCOPE, POSTRESTART_SCOPE} and manifest['placement'] == 'G1',
                               strict_glmrepair=self.scope == 'glmrepair')
        if self.scope in {CONCURRENT_SCOPE, CANDIDATE_SCOPE, CPU_SCOPE, POSTRESTART_SCOPE}:
            pressure = sample['concurrent_resource_gate']
            if pressure['status'] != 'PASS':
                gate['status'] = 'STOP_ALLOCATION_PROOF'
                gate['reasons'].extend(pressure['reasons'] + pressure['unavailable_reasons'])
            if manifest['placement'] == 'Q1':
                ranks = parsed.get('ranks') or {}
                if not ranks or not all(type(rank.get(key)) in (int, float) and rank[key] > 0
                                        for rank in ranks.values() for key in ('k_gb_log_label', 'v_gb_log_label')):
                    gate['status'] = 'STOP_ALLOCATION_PROOF'
                    gate['reasons'].append('concurrent_positive_native_kv_allocation_required')
        if self.scope == CANDIDATE_SCOPE:
            from .concurrent_validate import identity_stamp
            require(allocation_identity == native_capacity['identity'] == identity_stamp(self, cid), 'candidate_allocation_identity_changed')
            observed['native_capacity'] = native_capacity
            observed['evidence_status'] = 'CANDIDATE_OBSERVATION_NOT_ACCEPTANCE'
        result = {'allocation': gate, 'parsed': parsed, 'observed': observed, 'server_facts': facts,
                  'raw_log_path': self.log_root + '/loads/' + cid + '-allocation.log'}
        if self.scope in {CPU_SCOPE, POSTRESTART_SCOPE} and manifest['placement'] == 'Q1':
            result['observed']['native_capacity'] = native_capacity
        if self.scope == POSTRESTART_SCOPE:
            # Keep ordinary readiness/admission failed. Only retained hold may
            # distinguish absent sampled resource proof from a proven fault.
            missing_resource_reasons = set(pressure['unavailable_reasons']) | {
                'gpu_reserve_unproved:' + uuid for uuid in manifest['gpu_uuids']
                if type(observed['gpu_free_bytes'].get(uuid)) is not int}
            result['resource_proof_unavailable_only'] = (
                gate['status'] == 'STOP_ALLOCATION_PROOF' and pressure['status'] == 'UNAVAILABLE' and
                not pressure['reasons'] and bool(gate['reasons']) and
                set(gate['reasons']) <= missing_resource_reasons)
            from .cpu_budget_host import coherent_postrestart_cpu_proof
            if gate['status'] == 'ALLOCATION_PROOF_ACCEPTED' or result['resource_proof_unavailable_only']:
                result['observed']['actual_cpu_scope'] = coherent_postrestart_cpu_proof(
                    self, cid, manifest, expected_anchor=cpu_anchor)
            else:
                result['observed']['actual_cpu_scope'] = {'status': 'UNAVAILABLE', 'reason': 'allocation_refused'}
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
            if self.scope != POSTRESTART_SCOPE:
                return self._readiness(cid)
            attempts = []
            attempt_receipt = 'loads/' + cid + '-resource-readiness-' + secrets.token_hex(8) + '.json'
            for attempt in range(3):
                require(time.monotonic() < _COMMAND_DEADLINE.get(), 'host_operation_deadline')
                proof = self._readiness(cid)
                attempts.append({'attempt': attempt + 1, 'ready': proof.get('ready'),
                    'resource_proof_unavailable_only': proof.get('resource_proof_unavailable_only'),
                    'allocation': proof.get('allocation')})
                if any(row['resource_proof_unavailable_only'] is True for row in attempts):
                    self.write_json(attempt_receipt, {'attempt_limit': 3, 'attempts': attempts})
                if proof.get('resource_proof_unavailable_only') is not True:
                    return proof
            return proof  # persistent missing proof still refuses readiness
        finally:
            _COMMAND_DEADLINE.reset(token)

    def _readiness(self, cid):
        manifest = self.load_manifests.get(cid) or self.read_json('loads/' + cid + '.json')['manifest']
        try:
            models = http_json(manifest['transport']['port'], '/v1/models', timeout_s=5)
            alias = manifest['served_model'] if self.scope == CANDIDATE_SCOPE else 'bench-glm-5.3' if manifest['placement'].startswith('G') else 'bench-qwen3.8-27b'
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
        if self.scope == CANDIDATE_SCOPE:
            require(not re.search(r':30002\b', listeners), 'candidate_glm_listener_remains')
            require(all(row['state'] == 'REMOVED' and self.docker_inspect(row['resource']['id']) is None
                        for row in self.owner.resources) and self.owner.pending_create is None,
                    'candidate_validation_identity_remains')
            # Restored singleton Qwen legitimately owns production 30004.
            require(after['manager']['selected'] == 'qwen38-27b-1000000-yarn4-tp2-bf16kv',
                    'candidate_restored_qwen_identity_changed')
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
        candidate = self.scope in {CANDIDATE_SCOPE, CPU_SCOPE, POSTRESTART_SCOPE}
        require(ledger.get('validation_scope') == (self.scope if candidate else None),
                'recovery_scope_changed')
        if candidate:
            require(type(ledger.get('production_touched')) is bool and type(ledger.get('control_touched')) is bool,
                    'candidate_recovery_mutation_boundary_required')
        require(self.owner.phase == 'NEW', 'owner_already_active')
        self.owner.lease_context = acquire_lease(blocking=False)
        self.owner.lease = self.owner.lease_context.__enter__()
        self.owner.original = ledger['original']
        self.owner.resources, self.owner.pending_create = ledger['resources'], ledger['pending_create']
        self.owner.production_touched = self.owner.control_touched = True
        if candidate:
            self.owner.production_touched = ledger['production_touched']
            self.owner.control_touched = ledger['control_touched']
        if self.scope == POSTRESTART_SCOPE:
            require(ledger.get('warm_hold_reason') in {None, 'complete', 'preliminary_review', 'paused', 'quality_review'} and
                    type(ledger.get('warm_hold_resumed')) is bool and type(ledger.get('additional_followup_used')) is bool, 'postrestart_recovery_hold_state_required')
            self.owner.warm_hold_reason = ledger['warm_hold_reason']
            self.owner.warm_hold_resumed = ledger['warm_hold_resumed']
            self.owner.additional_followup_used = ledger['additional_followup_used']
        self.owner.budget_started = self.budget.data is not None
        self.owner.restoration_started = bool(self.budget.data and self.budget.data['phase'] in {'RESTORING', 'RESTORED', 'RESTORE_FAILED'})
        self.owner.phase = 'RECOVERY_REQUIRED'
        # Fresh-process recovery must bind the canonical lock before any
        # restoration callback consults the persisted credential/lease witness.
        current = self.capture(self.owner.lease)
        if ledger['phase'] in {'POST_RELEASE_LAN_VERIFICATION_PENDING', 'RESTORED'}:
            if candidate:
                require(self.owner.pending_create is None and
                        all(row['state'] == 'REMOVED' for row in self.owner.resources),
                        'candidate_restored_ownership_unresolved')
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
        # Reconcile by exact reviewed name, image and labels. Historical scopes
        # retain their inventory absence rule; candidate dispatch requires a
        # positive immutable identity and never settles from an empty list.
        pending = self.owner.pending_create
        if pending:
            manifest = self.manifests.get(pending['manifest_sha256'])
            require(manifest is not None, 'unreviewed_pending_create')
            if candidate:
                require(pending.get('dispatch') in {'not_dispatched', 'uncertain'} and pending.get('kind') in {'model', 'mapping_helper'} and
                        pending.get('campaign') == self.campaign and pending.get('image') == manifest['image'],
                        'unreviewed_pending_create')
                if pending['kind'] == 'mapping_helper':
                    manifest = {**manifest, 'container_name': self.campaign + '-mapping-helper-' + manifest['placement'][0].lower()}
            require(manifest['container_name'] == pending['name'], 'unreviewed_pending_create')
            ids = self.campaign_containers()
            matches = [self.docker_inspect(cid) for cid in ids]
            matches = [c for c in matches if c and c['Name'].removeprefix('/') == pending['name']]
            require(len(matches) <= 1, 'ambiguous_pending_create')
            if candidate and not matches and pending['dispatch'] == 'uncertain':
                # A timed-out create can complete in the daemon after this
                # inventory. Keep the durable intent and lease; do not drain a
                # healthy owned peer or restore production over unresolved work.
                self.owner._record_failure('candidate_dispatched_create_unresolved')
                require(False, 'candidate_dispatched_create_unresolved')
            if matches:
                resource = self.owner._resource(self.resource(matches[0]), manifest)
                if candidate:
                    require(not any(row['state'] != 'REMOVED' and
                                    (row['resource']['id'] == resource['id'] or row['resource']['name'] == resource['name'])
                                    for row in self.owner.resources), 'candidate_pending_identity_already_owned')
                self.owner.resources.append({'resource': resource, 'state': 'RUNNING' if matches[0]['State']['Running'] else 'CREATED'})
            self.owner.pending_create = None
            self.owner._save()
        return self.owner.restore()

    def postrestart_hold_proof(self):
        require(self.scope == POSTRESTART_SCOPE and self.owner.phase in {'ACTIVE', 'WARM_HOLD'},
                'postrestart_hold_scope_or_phase')
        self.assert_idle()
        self.owner._gate('warm_hold')
        self.guards(self.owner.lease)
        require(not self.concurrent_resource_violations and self.owner.pending_create is None,
                'postrestart_unsafe_hold_forbidden')
        live = [row['resource']['id'] for row in self.owner.resources if row['state'] != 'REMOVED']
        require(len(live) == 2 and set(live) == set(self.load_manifests) == set(self.allocation_proofs),
                'postrestart_hold_requires_exact_resident_pair')
        pair, review = {}, []
        for cid in live:
            manifest = self.load_manifests[cid]
            require(manifest == postrestart_manifest(manifest['placement']), 'postrestart_hold_manifest_changed')
            proof = self._readiness(cid)
            if proof.get('ready') is not True:
                unavailable_only = (proof.get('resource_proof_unavailable_only') is True and
                                    proof.get('state') == 'STOP_ALLOCATION_PROOF')
                require(proof.get('failed') is not True or unavailable_only, 'postrestart_hold_native_ready_failed')
                if unavailable_only:
                    require(self.readiness_failure(cid) is None, 'postrestart_hold_native_ready_failed')
                current = self.hold_checkpoint(entering=True)
                review.extend(current['unavailable_reasons'] + [manifest['placement'] + '_fresh_allocation_proof_unavailable'])
                container, cgroup, _ = self.identity(cid)
                memory, cpu = self.concurrent_limits(manifest, container, cgroup)
                observed = {'container_memory_limits': memory, 'container_cpu_limits': cpu,
                            'native_capacity': 'PREVIOUS_ACCEPTED_ALLOCATION_ONLY_CURRENT_PROOF_UNAVAILABLE'}
            else:
                require(proof['allocation']['status'] == 'ALLOCATION_PROOF_ACCEPTED', 'postrestart_unsafe_hold_forbidden')
                observed = proof['observed']
            pair[manifest['placement']] = {'container_id': cid, 'manifest': manifest,
                'manifest_sha256': digest(manifest), 'effective': observed,
                'transport': manifest['transport']}
        require(set(pair) == {'G1', 'Q1'}, 'postrestart_hold_pair_identity_changed')
        self.guards(self.owner.lease)
        return {'scope': self.scope, 'campaign': self.campaign, 'run_session_id': self.run_session_id,
            'host_owner_pid': os.getpid(), 'canonical_lease_path': self.config['lease'],
            'canonical_lease_retained': True, 'no_active_inference': True,
            'pair': pair, 'captured_at': time.time(), 'budget': self.budget.data,
            'status': 'REVIEW_REQUIRED' if review else 'HELD',
            'unavailable_reasons': sorted(set(review)),
            'release_target': {'selected': self.owner.original['manager']['selected'],
                               'desired': 'stopped', 'boot_policy': 'manual'},
            'crash_policy': 'EOF while idle hold attempts canonical restoration; hard kill requires fresh protected-ledger recovery'}

    def hold_checkpoint(self, *, entering=False):
        require(self.scope == POSTRESTART_SCOPE and (self.owner.phase == 'WARM_HOLD' or
                entering is True and self.owner.phase == 'ACTIVE'),
                'postrestart_hold_scope_or_phase')
        token = _COMMAND_DEADLINE.set(time.monotonic() + 60)
        try:
            self.owner._gate('warm_hold')  # actual PID-bound lease, control freeze, idle TCP/request registrations
            self.guards(self.owner.lease)
            self.credentials()
            require(self.owner.pending_create is None and not self.concurrent_resource_violations,
                    'postrestart_unsafe_hold_forbidden')
            live = [row['resource']['id'] for row in self.owner.resources if row['state'] != 'REMOVED']
            require(len(live) == 2 and set(live) == set(self.load_manifests) == set(self.allocation_proofs),
                    'postrestart_hold_requires_exact_resident_pair')
            groups, members, unavailable = {}, {}, []
            for cid in live:
                container, cgroup, pids = self.identity(cid)
                manifest = self.load_manifests[cid]
                self.concurrent_limits(manifest, container, cgroup)
                groups[cid], members[cid] = cgroup, pids
                try:
                    models = http_json(manifest['transport']['port'], '/v1/models', timeout_s=5)
                    alias = 'bench-glm-5.3' if manifest['placement'] == 'G1' else 'bench-qwen3.8-27b'
                    if not any(row.get('id') == alias for row in models.get('data', [])):
                        unavailable.append(manifest['placement'] + '_native_ready_unproved')
                    if manifest['placement'] == 'Q1':
                        from .cpu_budget_host import qwen_native_proof
                        qwen_native_proof(http_json(manifest['transport']['port'], '/get_server_info', timeout_s=5),
                                          scope=POSTRESTART_SCOPE)
                except (TimeoutError, urllib.error.URLError, json.JSONDecodeError):
                    unavailable.append(manifest['placement'] + '_native_read_unavailable')
            sample = collect_sample(groups, pids=members)
            pressure = self.concurrent_pressure(sample)
            require(pressure['status'] != 'STOP_RESOURCE_GATE', 'postrestart_unsafe_hold_forbidden')
            for group in sample['cgroups'].values():
                require(not any(type(group.get('events', {}).get(k)) is int and group['events'][k] > 0
                                for k in ('oom', 'oom_kill', 'oom_group_kill')) and
                        not (type(group.get('swap_bytes')) is int and group['swap_bytes'] > 0),
                        'postrestart_unsafe_hold_forbidden')
            unavailable.extend(pressure['unavailable_reasons'])
            self.guards(self.owner.lease)
            return {'phase': 'WARM_HOLD', 'status': 'REVIEW_REQUIRED' if unavailable else 'HELD',
                    'guarded': True, 'no_active_inference': True, 'canonical_lease_retained': True,
                    'unavailable_reasons': sorted(set(unavailable)), 'checked_at': time.time(), 'budget': self.budget.data}
        finally:
            _COMMAND_DEADLINE.reset(token)

    def warm_hold(self, reason, preliminary_result_sha256=None):
        require(reason in {'complete', 'preliminary_review', 'paused', 'quality_review'} and
                (preliminary_result_sha256 is None or isinstance(preliminary_result_sha256, str) and
                 bool(re.fullmatch(r'[0-9a-f]{64}', preliminary_result_sha256))), 'postrestart_hold_reason_invalid')
        if reason == 'preliminary_review':
            require(preliminary_result_sha256 is not None, 'postrestart_preliminary_result_required')
        proof = self.postrestart_hold_proof()
        self.owner.warm_hold(reason)
        receipt = {**proof, 'phase': 'WARM_HOLD', 'reason': reason,
                   'preliminary_result_sha256': preliminary_result_sha256}
        self.write_json('warm-hold.json', receipt)
        return receipt

    def resume_measurements(self, followup_session_id, source_commit, preliminary_result_sha256):
        require(self.scope == POSTRESTART_SCOPE and self.owner.phase == 'WARM_HOLD' and
                self.owner.warm_hold_reason == 'preliminary_review' and not self.owner.warm_hold_resumed,
                'postrestart_hold_resume_forbidden')
        saved = self.read_json('warm-hold.json')
        require(isinstance(followup_session_id, str) and bool(followup_session_id) and
                followup_session_id != self.run_session_id and source_commit == self.run_source_commit and
                preliminary_result_sha256 == saved.get('preliminary_result_sha256') and
                isinstance(preliminary_result_sha256, str) and bool(re.fullmatch(r'[0-9a-f]{64}', preliminary_result_sha256)),
                'postrestart_followup_identity_required')
        proof = self.postrestart_hold_proof()
        if proof['status'] != 'HELD':
            return {'phase': 'WARM_HOLD', 'proof_pending': True, 'admitted': False, 'proof': proof}
        identity = {'session_id': followup_session_id, 'source_commit': source_commit,
                    'preliminary_result_sha256': preliminary_result_sha256}
        self.owner.resume_measurements(identity)
        self.followup_admitted = set()
        receipt = {'phase': self.owner.phase, 'resumed_from': 'preliminary_review', 'resumed_at': time.time(),
                   'retained_owner_session_id': self.run_session_id, 'followup_identity': identity, 'budget': self.budget.data}
        self.write_json('warm-hold-resume.json', receipt)
        return receipt

    def admit_followup(self, go):
        from .fixtures import canonical
        require(self.scope == POSTRESTART_SCOPE and self.owner.phase == 'WARM_HOLD' and
                self.owner.warm_hold_reason in {'complete', 'quality_review', 'paused'} and
                not self.owner.additional_followup_used, 'postrestart_additional_followup_forbidden')
        fields = {'decision', 'source_commit', 'owner_run_session_id', 'followup_session_id', 'campaign',
                  'warm_hold_receipt_sha256', 'placement', 'manifest_sha256', 'request_sha256',
                  'fixture_sha256', 'request_id', 'preset', 'policy'}
        require(type(go) is dict and set(go) == fields and go['decision'] == 'GO' and
                go['source_commit'] == self.run_source_commit and go['owner_run_session_id'] == self.run_session_id and
                go['campaign'] == self.campaign and isinstance(go['followup_session_id'], str) and
                bool(go['followup_session_id']) and go['followup_session_id'] != self.run_session_id and
                go['preset'] in {'P-G4K', 'P-G65008', 'P-Qnear480K'} and
                go['placement'] == {'P-G4K': 'G1', 'P-G65008': 'G1', 'P-Qnear480K': 'Q1'}[go['preset']] and
                isinstance(go['request_id'], str) and
                bool(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,95}', go['request_id'])) and
                all(isinstance(go[k], str) and bool(re.fullmatch(r'[0-9a-f]{64}', go[k]))
                    for k in ('warm_hold_receipt_sha256', 'manifest_sha256', 'request_sha256', 'fixture_sha256')),
                'postrestart_additional_followup_binding_invalid')
        require(go['policy'] == {'measurement_admission_seconds': 21600, 'request_timeout_seconds': 7200,
                'request_clock_starts': 'HTTP_DISPATCH', 'admission_deadline_refuses_new_only': True},
                'postrestart_followup_clock_policy_changed')
        saved = self.read_json('warm-hold.json')
        require(go['warm_hold_receipt_sha256'] == hashlib.sha256(canonical(saved) + b'\n').hexdigest() and
                go['manifest_sha256'] == digest(postrestart_manifest(go['placement'])),
                'postrestart_additional_followup_identity_changed')
        previous = self.budget.data
        if 'followup_identity' in previous:
            require(go['followup_session_id'] != previous['followup_identity']['session_id'],
                    'postrestart_fresh_followup_session_required')
        proof = self.postrestart_hold_proof()
        if proof['status'] != 'HELD':
            return {'phase': 'WARM_HOLD', 'proof_pending': True, 'admitted': False, 'proof': proof}
        identity = {'session_id': go['followup_session_id'], 'source_commit': go['source_commit'],
                    **{k: go[k] for k in ('request_id', 'placement', 'manifest_sha256', 'request_sha256',
                                         'fixture_sha256', 'warm_hold_receipt_sha256')}}
        self.owner.admit_followup(identity)
        self.followup_request, self.followup_admitted = copy.deepcopy(go), set()
        receipt = {'phase': 'ACTIVE', 'followup_identity': identity, 'budget': self.budget.data}
        self.write_json('additional-followup.json', receipt)
        return receipt

    def dispatch(self, message):
        require(isinstance(message, dict), 'invalid_rpc')
        op = message.get('op')
        args = message.get('args', {k: v for k, v in message.items() if k != 'op'})
        require(isinstance(args, dict), 'invalid_rpc_args')
        if self.scope in {CPU_SCOPE, POSTRESTART_SCOPE}:
            require(op in {'begin', 'load', 'retire', 'readiness', 'telemetry', 'allocation', 'quiescent',
                'request_begin', 'request_end', 'admit_concurrent', 'rpc_diagnostics', 'restore', 'recover',
                'finalize', 'verify_restoration', 'budget', 'status', 'harness_failure'} |
                ({'warm_hold', 'resume_measurements', 'hold_checkpoint', 'admit_followup'} if self.scope == POSTRESTART_SCOPE else set()), 'cpu_operation_outside_scope')
        if self.scope == CANDIDATE_SCOPE:
            require(op in {'begin', 'load', 'retire', 'readiness', 'telemetry', 'allocation', 'quiescent',
                    'request_begin', 'request_end', 'candidate_denials', 'candidate_evidence', 'rpc_diagnostics',
                    'restore', 'recover', 'finalize', 'verify_restoration', 'budget', 'status', 'harness_failure'},
                    'candidate_operation_outside_scope')
        if op == 'admit_followup':
            return self.admit_followup(args.get('go'))
        if op == 'hold_checkpoint':
            return self.hold_checkpoint()
        if op == 'warm_hold':
            return self.warm_hold(args.get('reason'), args.get('preliminary_result_sha256'))
        if op == 'resume_measurements':
            return self.resume_measurements(args.get('followup_session_id'), args.get('source_commit'),
                                            args.get('preliminary_result_sha256'))
        if op == 'begin':
            if args.get('resume'):
                require(self.scope not in {'glmrepair', 'g1-ladder', 'glm-decode-diag', CONCURRENT_SCOPE, CANDIDATE_SCOPE, CPU_SCOPE, POSTRESTART_SCOPE}, 'glmrepair_resume_forbidden_restore_only')
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
            if self.scope in {CONCURRENT_SCOPE, CPU_SCOPE, POSTRESTART_SCOPE}:
                require(digest(manifest) in self.concurrent_admitted, 'concurrent_round_not_admitted')
            token = _COMMAND_DEADLINE.set(time.monotonic() + min(7200, remaining))
            try:
                return self.owner.launch(manifest)
            finally:
                _COMMAND_DEADLINE.reset(token)
        if op == 'retire':
            if self.scope == 'glm-decode-diag':
                from .decode_capture import stop_captures
                stop_captures(self, args['id'])
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
        if op == 'decode_progress':
            return self.decode_progress(args['id'])
        if op == 'decode_cpu_capture_start':
            return self.decode_cpu_capture_start(args['id'], args.get('client_before'))
        if op == 'decode_cpu_capture_status':
            return self.decode_cpu_capture_status(args['id'], args['capture_id'], args.get('client_after'))
        if op == 'request_begin':
            require(self.owner.phase == 'ACTIVE', 'owner_not_active')
            container, cgroup, _ = self.identity(args['id']) if self.scope in {CONCURRENT_SCOPE, CANDIDATE_SCOPE, CPU_SCOPE, POSTRESTART_SCOPE} else (None, None, None)
            if self.scope in {CONCURRENT_SCOPE, CANDIDATE_SCOPE, CPU_SCOPE, POSTRESTART_SCOPE}:
                require(args['id'] in self.allocation_proofs, 'concurrent_current_allocation_required')
                self.concurrent_limits(self.load_manifests[args['id']], container, cgroup)
                sample = self.telemetry(args['id'])
                if self.scope == POSTRESTART_SCOPE and sample['concurrent_resource_gate']['status'] == 'UNAVAILABLE':
                    return {'proof_pending': True, 'admitted': False,
                            'resource_gate': sample['concurrent_resource_gate'], 'sample': sample}
                require(sample['concurrent_resource_gate']['status'] == 'PASS', 'concurrent_current_resource_gate_failed')
            else:
                self.identity(args['id'])
            if self.scope in {CPU_SCOPE, POSTRESTART_SCOPE}:
                from .cpu_budget_host import resident_obligations
                resident_obligations(self)
            if self.scope == CANDIDATE_SCOPE:
                from .concurrent_validate import admission
                require(len(self.allocation_proofs) == 2 and len(self.load_manifests) == 2,
                        'candidate_both_resident_required')
                admission(self)
            if self.scope == POSTRESTART_SCOPE and args.get('measured') is True and self.followup_request is not None:
                go = self.followup_request
                require(not self.followup_admitted and self.load_manifests[args['id']]['placement'] == go['placement'] and
                        args.get('request_identity') == {k: go[k] for k in ('request_id', 'request_sha256', 'manifest_sha256')},
                        'postrestart_only_bound_additional_request')
            if self.scope == POSTRESTART_SCOPE and args.get('measured') is True and not self.owner.warm_hold_resumed and self.followup_request is None:
                placement = self.load_manifests[args['id']]['placement']
                require(self.postrestart_measured_admissions[placement] < (2 if placement == 'G1' else 1),
                        'postrestart_initial_closed_three_measurements')
            if self.scope == POSTRESTART_SCOPE and (self.owner.warm_hold_resumed or self.followup_request is not None) and args.get('measured') is True:
                require(args['id'] not in self.followup_admitted and len(self.followup_admitted) < 2,
                        'postrestart_followup_only_remaining_pair')
            timeout = self.budget.request_timeout(args.get('timeout_s', 7200),
                **({'measured': args.get('measured', False)} if self.scope == POSTRESTART_SCOPE else {}))
            require(args['id'] not in self.requests, 'request_already_active')
            if self.scope == POSTRESTART_SCOPE and (self.owner.warm_hold_resumed or self.followup_request is not None) and args.get('measured') is True:
                self.followup_admitted.add(args['id'])
            if self.scope == POSTRESTART_SCOPE and args.get('measured') is True and not self.owner.warm_hold_resumed and self.followup_request is None:
                self.postrestart_measured_admissions[placement] += 1
            self.requests[args['id']] = {'started_at': time.time(), 'timeout_s': timeout}
            self.write_json('requests.json', self.requests)
            return {'timeout_s': timeout, 'budget': self.budget.data}
        if op == 'request_end':
            require(args['id'] in self.requests, 'request_not_active')
            if self.scope == 'glm-decode-diag':
                from .decode_capture import stop_captures
                stop_captures(self, args['id'])
            del self.requests[args['id']]
            self.write_json('requests.json', self.requests)
            return {'request_ended': args['id']}
        if op == 'candidate_denials':
            require(self.scope == CANDIDATE_SCOPE and len(self.allocation_proofs) == 2 and not self.requests,
                    'candidate_both_resident_required')
            from .concurrent_validate import admission
            admission(self)
            evidence = {}
            for cid, manifest in self.load_manifests.items():
                before = self.resource(self.identity(cid)[0])
                try:
                    http_json(manifest['transport']['port'], '/v1/chat/completions',
                              {'model': 'candidate-deliberately-wrong-alias',
                               'messages': [{'role': 'user', 'content': 'Reply OK.'}],
                               'max_tokens': 1, 'stream': False}, timeout_s=min(5, self.budget.checkpoint()))
                    raise ValueError('candidate_wrong_alias_accepted')
                except urllib.error.HTTPError as error:
                    require(error.code in (400, 404), 'candidate_alias_denial_unproved')
                    evidence[manifest['placement']] = {'wrong_alias_status': error.code}
                require(before == self.resource(self.identity(cid)[0]), 'candidate_denial_identity_changed')
            self.write_json('candidate-alias-denials.json', evidence)
            return evidence
        if op == 'candidate_evidence':
            require(self.scope == CANDIDATE_SCOPE and not self.requests, 'candidate_evidence_scope_required')
            checks = args.get('checks', {})
            require(set(checks) == {'G1-smoke', 'G1-tool', 'Q1-smoke', 'Q1-tool'}
                    and all(v.get('status') == 'PASS' for v in checks.values()), 'candidate_checks_incomplete')
            slots = {}
            for cid, manifest in self.load_manifests.items():
                placement = manifest['placement']
                occupied = []
                for value in checks.values():
                    if value.get('placement') != placement:
                        continue
                    for name in ('sample', 'continuation'):
                        counters = value.get(name, {}).get('counters', {})
                        prompt, completion = counters.get('prompt_tokens'), counters.get('completion_tokens')
                        if name in value:
                            require(type(prompt) is int and type(completion) is int and prompt > 0 and completion > 0,
                                    'candidate_evidence_native_counts_missing')
                            occupied.append(prompt + completion)
                require(occupied, 'candidate_evidence_checks_missing')
                samples = self.samples.get(cid, [])
                self.write_json('loads/' + cid + '-samples.json', samples)
                gpu = [g for sample in samples for g in sample['gpus'] if g['uuid'] in manifest['gpu_uuids']]
                frees = [g['free_bytes'] for g in gpu if type(g.get('free_bytes')) is int]
                require(frees, 'candidate_evidence_gpu_samples_missing')
                slots[placement] = {'configured_context': manifest['configured_capacity'],
                    'largest_occupied_context_in_checks': max(occupied),
                    'minimum_free_gpu_bytes_sampled': min(frees),
                    'host_demand': self.measured.get(placement, {'evidence_status': 'UNAVAILABLE'}),
                    'samples_path': self.log_root + '/loads/' + cid + '-samples.json',
                    'samples_sha256': digest(samples), 'sampled_not_absolute': True}
            self.write_json('candidate-evidence.json', {'status': 'CANDIDATE_PASS', 'slots': slots,
                'timing_scope': 'short checks at G480000 and Q700160; no occupied-capacity or G64-speed extrapolation',
                'production_acceptance': 'NOT_GRANTED', 'checks': checks, 'actual_image_auth': self.candidate_auth,
                'manifests': list(self.manifests.values()), 'measured_demand_helper': self.measured,
                'allocation': {cid: self.read_json('loads/' + cid + '-allocation.json') for cid in self.load_manifests},
                'alias_denials': self.read_json('candidate-alias-denials.json')})
            return {'status': 'CANDIDATE_PASS', 'production_acceptance': 'NOT_GRANTED'}
        if op == 'admit_concurrent':
            return self.admit_concurrent(args.get('round'))
        if op == 'rpc_diagnostics':
            return self.rpc_diagnostics()
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
            if self.scope == 'glm-decode-diag':
                from .decode_capture import stop_captures
                stop_captures(self)
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
    'quiescent', 'diagnostic_snapshot', 'decode_progress', 'decode_cpu_capture_start', 'decode_cpu_capture_status',
    'candidate_denials', 'candidate_evidence', 'request_begin', 'request_end', 'admit_mixed', 'admit_concurrent', 'rpc_diagnostics', 'restore', 'recover',
    'finalize', 'verify_restoration', 'budget', 'status', 'harness_failure', 'warm_hold', 'resume_measurements', 'hold_checkpoint', 'admit_followup'})
RPC_SAFE_REQUIRE_CODES = frozenset({'native_server_args_unavailable',
    'allocation_log_too_large', 'current_model_mount_changed',
    'owned_container_identity_changed', 'installed_source_identity_changed',
    'registered_storage_pin_changed', 'http_response_invalid',
    'host_operation_deadline', 'STOP_BUDGET',
    'postrestart_cpu_snapshot_unavailable', 'postrestart_cpu_snapshot_identity_changed',
    'postrestart_cpu_snapshot_read_failed', 'postrestart_cpu_snapshot_malformed',
    'postrestart_process_allowed_scope_mismatch', 'postrestart_effective_cpus_mismatch',
    'postrestart_all_memory_nodes_required', 'postrestart_quiescent_numa_unproved',
    'postrestart_numa_proc_read_failed', 'postrestart_numa_proc_read_limit',
    'postrestart_numa_proc_encoding_invalid', 'postrestart_numa_proc_stat_malformed',
    'postrestart_numa_maps_malformed', 'concurrent_current_resource_gate_failed'})


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
    """Only idle actual72 WARM_HOLD has an EOF canonical-cleanup policy."""
    try:
        return _serve_lines(host, source, sink)
    finally:
        if (getattr(host, 'scope', None) == POSTRESTART_SCOPE and
                getattr(getattr(host, 'owner', None), 'phase', None) == 'WARM_HOLD' and
                not getattr(host, 'requests', {})):
            host.owner.restore()


def _serve_lines(host, source, sink):
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
