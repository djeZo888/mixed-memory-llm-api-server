"""Passive fixed Linux resource adapters; no mutation or caller-selected paths.

The outer BoundedObservers owns exactly one disk and one network callback slot.
These callbacks never spawn replacement threads. A hung filesystem call holds
its disk slot, while network/CPU/memory/status continue independently. Legacy
``disk`` capacity/rates describe root only; ``volumes`` describes root and each
registered role (shared filesystems must not be summed). All byte rates need two
samples. Linux diskstats sectors are 512 bytes, regardless of filesystem blocks.
"""
from __future__ import annotations

import os
from pathlib import Path
import re
import time

from install.storage import Storage, StorageError
from .passive import utc

VOLUME_IDS = ('root', 'data', 'models')
CAPACITY_FIELDS = ('total_bytes', 'available_bytes')
RATE_FIELDS = ('read_bytes_per_second', 'write_bytes_per_second')
MAX_READ = 1024 * 1024
DEVICE = re.compile(r'[0-9]+:[0-9]+\Z')
INTERFACE = re.compile(r'[A-Za-z0-9_.-]{1,15}\Z')


def _read(path):
    with Path(path).open('rb') as stream:
        value = stream.read(MAX_READ + 1)
    if len(value) > MAX_READ:
        raise ValueError('resource_output_limit')
    return value.decode('ascii')


class _DeadlineRunner:
    """Give shared read-only storage discovery one cumulative observer budget."""
    def __init__(self, run, deadline, clock):
        self.run_command, self.deadline, self.clock = run, deadline, clock

    def run(self, argv, *, timeout=30, env=None):
        commands = {'findmnt': '/usr/bin/findmnt', 'lsblk': '/usr/bin/lsblk'}
        if not argv or argv[0] not in commands:
            raise ValueError('resource_command_not_allowed')
        remaining = self.deadline - self.clock()
        if remaining <= 0:
            raise TimeoutError('resource_deadline')
        return self.run_command([commands[argv[0]], *argv[1:]], min(timeout, remaining))


def _stat_volume(path, device):
    """Capacity from the verified mount's open directory, never path fallback."""
    if not DEVICE.fullmatch(device):
        raise ValueError('volume_device_unknown')
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        before = os.fstat(fd)
        actual = f'{os.major(before.st_dev)}:{os.minor(before.st_dev)}'
        if actual != device:
            raise ValueError('volume_device_changed')
        value = os.fstatvfs(fd)
        size = value.f_frsize or value.f_bsize
        total, available = value.f_blocks * size, value.f_bavail * size
        if not 0 <= available <= total <= 2**53:
            raise ValueError('volume_capacity_unknown')
        return {'total_bytes': total, 'available_bytes': available}
    finally:
        os.close(fd)


def disk_counters(raw):
    result = {}
    for line in raw.splitlines():
        fields = line.split()
        if len(fields) < 14:
            raise ValueError('disk_counters_unknown')
        major, minor = int(fields[0]), int(fields[1])
        values = [int(v) for v in fields[3:]]
        if major < 0 or minor < 0 or any(v < 0 for v in values):
            raise ValueError('disk_counters_unknown')
        key = f'{major}:{minor}'
        if key in result:
            raise ValueError('disk_counters_ambiguous')
        result[key] = (values[2] * 512, values[6] * 512)
    return result


class _Rates:
    def __init__(self):
        self.previous = {}

    def sample(self, identity, counters, now):
        previous = self.previous.get(identity)
        self.previous[identity] = (now, counters)
        if previous is None or now <= previous[0]:
            return (None, None)
        elapsed = now - previous[0]
        return tuple((value - old) / elapsed if value >= old else None
                     for value, old in zip(counters, previous[1]))


class DiskCollector:
    """Protected registry read + role-isolated exact mount/capacity observation.

    Storage's identity and root-block exclusion checks are reused without its
    writer free-space threshold. Observation of a full disk is not permission
    to write there. The in-process test seams are not environment/HTTP options.
    """
    def __init__(self, *, run=None, clock=time.monotonic, wall=time.time,
                 stat_volume=_stat_volume, read_diskstats=lambda: _read('/proc/diskstats'),
                 system_root=Path('/')):
        # Import lazily: node_collectors imports this module in its factory.
        if run is None:
            from .node_collectors import command
            run = command
        self.run, self.clock, self.wall = run, clock, wall
        self.stat_volume, self.read_diskstats = stat_volume, read_diskstats
        self.system_root = Path(system_root)
        self.rates = _Rates()

    def _entry(self, role, expected=None):
        return {'volume_id': role, 'mount_point': expected.get('mount') if expected else None,
                'filesystem_uuid': expected.get('uuid') if expected else None,
                'filesystem_type': expected.get('fstype') if expected else None,
                'state': 'unknown', 'reason': 'registration_unknown',
                'observed_at': None, 'age_ms': None, 'freshness': 'unknown',
                **{key: None for key in (*CAPACITY_FIELDS, *RATE_FIELDS)}}

    def _observe(self, storage, role, expected, blocks, protected, counters, sampled):
        entry = self._entry(role, expected)
        entry['reason'] = 'mount_identity_unavailable'
        try:
            if role == 'root':
                actual = storage._mount('/')
                if actual.get('target') != '/' or not DEVICE.fullmatch(actual.get('maj:min', '')):
                    raise ValueError('root_mount_unknown')
                mount, device = '/', actual['maj:min']
                entry.update(mount_point='/', filesystem_uuid=actual.get('uuid'),
                             filesystem_type=actual.get('fstype'))
            else:
                actual = storage._registered_mount(expected['mount'], expected['uuid'], blocks, protected)
                if actual['fstype'] != expected['fstype']:
                    raise ValueError('volume_filesystem_changed')
                namespace = storage._no_symlink(expected['path'], protected=True)
                if not namespace.is_dir():
                    raise ValueError('registered_namespace_missing')
                namespace_mount = storage._mount(expected['path'])
                if any(namespace_mount.get(k) != actual[v] for k, v in
                       (('uuid', 'uuid'), ('target', 'mount'), ('maj:min', 'device'), ('fstype', 'fstype'))):
                    raise ValueError('registered_namespace_changed')
                mount, device = actual['mount'], actual['device']
            entry['reason'] = 'capacity_unavailable'
            capacity = self.stat_volume(str(storage._local(mount)), device)
            # Reject identity changes during the capacity call; no stale path
            # can cause a missing dedicated mount to publish root capacity.
            after = storage._mount(mount)
            if (after.get('target') != mount or after.get('maj:min') != device or
                    (role != 'root' and (after.get('uuid') != expected['uuid'] or
                                        after.get('fstype') != expected['fstype']))):
                raise ValueError('volume_mount_changed')
            entry.update(capacity)
            entry.update(state='ok', reason=None, observed_at=utc(self.wall()),
                         age_ms=0, freshness='fresh')
            if device in counters:
                identity = (role, mount, device, entry['filesystem_uuid'])
                entry.update(zip(RATE_FIELDS, self.rates.sample(identity, counters[device], sampled)))
                self.rates.previous = {key: value for key, value in self.rates.previous.items()
                                       if key[0] != role or key == identity}
        except (StorageError, OSError, ValueError, TypeError, KeyError):
            # Do not promote a failed/unknown lookup to confirmed absent mount.
            # In particular no statvfs('/data/models') fallback is attempted.
            self.rates.previous = {key: value for key, value in self.rates.previous.items() if key[0] != role}
        return entry

    def __call__(self, seconds):
        started = self.clock()
        runner = _DeadlineRunner(self.run, started + seconds, self.clock)
        reader = Storage({}, runner, system_root=self.system_root)
        try:
            counters = disk_counters(self.read_diskstats())
        except (OSError, ValueError, UnicodeError):
            counters = {}
        sampled = self.clock()
        # Root remains independently observable even with missing registration.
        root = self._observe(reader, 'root', {'mount': '/'}, None, None, counters, sampled)
        entries = [root, self._entry('data'), self._entry('models')]
        try:
            registry = reader.read_registration()
            if registry is None:
                return {**{key: root[key] for key in (*CAPACITY_FIELDS, *RATE_FIELDS)}, 'volumes': entries}
            config = {'data_dir': registry['data']['path'], 'data_uuid': registry['data']['uuid'],
                      'model_dir': registry['models']['path'], 'model_uuid': registry['models']['uuid'],
                      'storage_mode': registry.get('storage_mode', 'existing')}
            storage = Storage(config, runner, system_root=self.system_root)
            if registry['roots'] != storage._roots() or registry['data']['path'] != registry['data']['mount']:
                raise ValueError('registered_layout_unknown')
            for role in ('data', 'models'):
                expected = registry[role]
                if any(len(expected[field]) > 512 for field in ('path', 'mount')) or expected.get('fstype') not in ('ext4', 'xfs') or (
                        expected['path'] != expected['mount'] and
                        not expected['path'].startswith(expected['mount'] + '/')):
                    raise ValueError('registered_layout_unknown')
            data, models = registry['data'], registry['models']
            if ((data['mount'] == models['mount']) != (data['uuid'] == models['uuid']) or
                    data['mount'] == models['mount'] and data['fstype'] != models['fstype']):
                raise ValueError('registered_alias_unknown')
            entries[1:] = [self._entry(role, registry[role]) for role in ('data', 'models')]
            blocks = storage._blocks()
            protected = storage._protected_disks(blocks)
            for index, role in enumerate(('data', 'models'), 1):
                entries[index] = self._observe(storage, role, registry[role], blocks, protected, counters, sampled)
            # A registration replacement cannot lend an earlier identity to a
            # newly observed mount; reset only the registered volume records.
            try:
                after = reader.read_registration()
            except (StorageError, OSError, ValueError, TypeError, KeyError):
                after = None
            if after is None or Storage._identity(after) != Storage._identity(registry):
                entries[1:] = [self._entry(role) for role in ('data', 'models')]
        except (StorageError, OSError, ValueError, TypeError, KeyError):
            pass
        return {**{key: root[key] for key in (*CAPACITY_FIELDS, *RATE_FIELDS)}, 'volumes': entries}


def _external_interface(name):
    """Guest physical/virtio NICs only, avoiding bridge/veth double counting."""
    if not INTERFACE.fullmatch(name) or name == 'lo':
        return None
    base = Path('/sys/class/net') / name
    if not (base / 'device').exists():
        return None
    index = int(_read(base / 'ifindex').strip())
    if index <= 0:
        raise ValueError('network_identity_unknown')
    return index


class NetworkCollector:
    def __init__(self, *, read=lambda: _read('/proc/net/dev'),
                 interface=_external_interface, clock=time.monotonic):
        self.read, self.interface, self.clock = read, interface, clock
        self.rates = _Rates()

    def __call__(self, _seconds):
        rows, seen = [], set()
        raw = self.read().splitlines()
        if len(raw) < 2 or 'Inter-' not in raw[0] or 'Receive' not in raw[0]:
            raise ValueError('network_counters_unknown')
        for line in raw[2:]:
            if not line.strip():
                continue
            name, fields = line.rsplit(':', 1)
            name = name.strip()
            if not INTERFACE.fullmatch(name) or name in seen:
                raise ValueError('network_identity_ambiguous')
            seen.add(name)
            values = [int(v) for v in fields.split()]
            if len(values) != 16 or any(v < 0 for v in values):
                raise ValueError('network_counters_unknown')
            index = self.interface(name)
            if index is not None:
                rows.append((name, index, values[0], values[8]))
        # No externally identifiable NIC is unknown, not a measured zero rate.
        if not rows:
            self.rates.previous.clear()
            return {'rx_bytes_per_second': None, 'tx_bytes_per_second': None}
        identity = tuple(sorted((row[0], row[1]) for row in rows))
        counters = (sum(row[2] for row in rows), sum(row[3] for row in rows))
        rates = self.rates.sample(identity, counters, self.clock())
        self.rates.previous = {identity: self.rates.previous[identity]}
        return dict(zip(('rx_bytes_per_second', 'tx_bytes_per_second'), rates))


def resource_callbacks():
    return {'disk': DiskCollector(), 'network': NetworkCollector()}
