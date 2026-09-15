"""Focused N1S source checks; real local file metadata, no host commands/apply.

Temporary files live under this worker checkout. The protected-reader fixture
maps only this ordinary worker's uid to root in stat results; permissions,
file type, links, traversal, sizes, identity and timestamps remain real.
"""
from __future__ import annotations

import configparser
import copy
from contextlib import ExitStack, redirect_stdout
import io
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from control import private_network as network


class ProtectedPolicyTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        folder = self.stack.enter_context(tempfile.TemporaryDirectory(
            prefix='.n1s-policy-test-', dir=ROOT))
        self.base = Path(folder)
        self.policy = self.base / 'policy' / 'network.json'
        self.policy.parent.mkdir(mode=0o700)
        self.policy.write_text(json.dumps(network.EXPECTED), encoding='utf-8')
        self.policy.chmod(0o600)
        self.bad_owner_inode = None
        self.real_stat = os.stat
        self.real_fstat = os.fstat
        self.worker_uid = os.getuid()
        self.stack.enter_context(patch.object(network, 'POLICY', self.policy))
        self.stack.enter_context(patch.object(network.os, 'stat', side_effect=self.stat))
        self.stack.enter_context(patch.object(network.os, 'fstat', side_effect=self.fstat))
        self.host_command = self.stack.enter_context(patch.object(
            network, '_run', side_effect=AssertionError('loader must not execute commands')))

    def root_view(self, metadata):
        result = {name: getattr(metadata, name) for name in dir(metadata)
                  if name.startswith('st_')}
        if metadata.st_uid == self.worker_uid:
            result['st_uid'] = 0
        if metadata.st_ino == self.bad_owner_inode:
            result['st_uid'] = 12345
        return SimpleNamespace(**result)

    def stat(self, *args, **kwargs):
        return self.root_view(self.real_stat(*args, **kwargs))

    def fstat(self, *args, **kwargs):
        return self.root_view(self.real_fstat(*args, **kwargs))

    def refused(self):
        with self.assertRaises(network.PrivateNetworkError):
            network.load_policy()

    def test_valid_fixed_loader_is_fresh_and_read_only(self):
        with patch.dict(os.environ, {'LLM_NETWORK_POLICY': '/ignored',
                                     'HOST': 'evil.example', 'ORIGIN': 'http://evil.example'}):
            first = network.load_policy()
            self.assertEqual(first, network.EXPECTED)
            first['ports']['control'] = 1
            first['allowed_client_ipv4'].clear()
            self.assertEqual(network.load_policy(), network.EXPECTED)
        self.host_command.assert_not_called()
        with self.assertRaises(TypeError):
            network.load_policy(self.policy)

    def test_missing_file_refused(self):
        self.policy.unlink()
        self.refused()

    def test_symlink_file_refused(self):
        target = self.policy.with_name('real.json')
        self.policy.rename(target)
        self.policy.symlink_to(target.name)
        self.refused()

    def test_symlink_parent_refused(self):
        parent = self.policy.parent
        target = parent.with_name('real-parent')
        parent.rename(target)
        parent.symlink_to(target.name, target_is_directory=True)
        self.refused()

    def test_hardlink_refused(self):
        os.link(self.policy, self.policy.with_name('second-link.json'))
        self.refused()

    def test_non_regular_file_refused_without_blocking(self):
        self.policy.unlink()
        os.mkfifo(self.policy, 0o600)
        self.refused()

    def test_wrong_file_mode_refused(self):
        for mode in (0o400, 0o640, 0o644, 0o660):
            with self.subTest(mode=oct(mode)):
                self.policy.chmod(mode)
                self.refused()

    def test_writable_parent_refused(self):
        for mode in (0o720, 0o702, 0o777):
            with self.subTest(mode=oct(mode)):
                self.policy.parent.chmod(mode)
                self.refused()

    def test_nonroot_file_and_parent_refused(self):
        for location in (self.policy, self.policy.parent):
            with self.subTest(location=location.name):
                self.bad_owner_inode = self.real_stat(location).st_ino
                self.refused()

    def test_oversized_file_refused(self):
        self.policy.write_bytes(b' ' * 4097)
        self.refused()

    def test_replaced_file_during_read_refused(self):
        real_read = os.read
        replaced = False

        def read_then_replace(fd, size):
            nonlocal replaced
            raw = real_read(fd, size)
            if not replaced:
                replaced = True
                replacement = self.policy.with_name('replacement.json')
                replacement.write_bytes(raw)
                replacement.chmod(0o600)
                replacement.replace(self.policy)
            return raw

        with patch.object(network.os, 'read', side_effect=read_then_replace):
            self.refused()


class StrictPolicyTests(unittest.TestCase):
    def test_fixed_schema_accepts_formatting_and_key_order(self):
        raw = json.dumps(dict(reversed(list(network.EXPECTED.items()))), indent=3).encode()
        self.assertEqual(network._validate_policy(raw), network.EXPECTED)

    def test_unknown_missing_and_wrong_typed_fields_refused(self):
        changes = [
            ('schema_version', True), ('schema_version', 1.0),
            ('mode', 'another_mode'), ('interface', 'lo'),
            ('private_address', '0.0.0.0'), ('private_address', '::'),
            ('private_address', '8.8.8.8'), ('private_address', '10.156.100.061'),
            ('private_address', 'server.local'), ('private_address', 'http://10.156.100.60'),
            ('prefix_length', 24.0), ('prefix_length', 32),
            ('allowed_client_ipv4', ['0.0.0.0/0']),
            ('allowed_client_ipv4', ['10.156.100.1/32']),
            ('allowed_client_ipv4', '10.156.100.0/24'),
            ('ports', {'control': 30000, 'glm': 30002, 'qwen38': '30004'}),
            ('ports', {'control': 30000, 'glm': 30000, 'qwen38': 30004}),
            ('command', '/bin/false'),
        ]
        for key, value in changes:
            with self.subTest(field=key, value=value):
                policy = copy.deepcopy(network.EXPECTED)
                policy[key] = value
                with self.assertRaises(network.PrivateNetworkError):
                    network._validate_policy(json.dumps(policy).encode())
        for key in network.EXPECTED:
            with self.subTest(missing=key):
                policy = copy.deepcopy(network.EXPECTED)
                del policy[key]
                with self.assertRaises(network.PrivateNetworkError):
                    network._validate_policy(json.dumps(policy).encode())

    def test_invalid_duplicate_nonfinite_or_alternate_encoding_refused(self):
        canonical = json.dumps(network.EXPECTED)
        samples = [b'', b'[]', b'null', b'NaN', b'{"x": Infinity}', b'\xff',
                   b' ' * 4097,
                   canonical.replace('"schema_version": 1',
                                     '"schema_version": 1, "schema_version": 1').encode(),
                   canonical.replace('"control": 30000',
                                     '"control": 30000, "control": 30000').encode(),
                   canonical.encode('utf-16'), canonical.encode('utf-32'),
                   b'\xef\xbb\xbf' + canonical.encode()]
        for number, raw in enumerate(samples):
            with self.subTest(sample=number):
                with self.assertRaises(network.PrivateNetworkError):
                    network._validate_policy(raw)


class InterfaceTests(unittest.TestCase):
    def valid(self):
        return [{'ifname': 'enp6s18', 'flags': ['BROADCAST', 'UP', 'LOWER_UP'],
                 'operstate': 'UP', 'addr_info': [
                     {'family': 'inet', 'local': '10.156.100.60', 'prefixlen': 24,
                      'scope': 'global', 'valid_life_time': 3600}]}]

    def inspect(self, data):
        with patch.object(network, '_run', return_value=json.dumps(data)) as run:
            network._interface()
            run.assert_called_once_with([network.IP, '-j', '-4', 'address',
                                         'show', 'dev', 'enp6s18'])

    def test_exact_live_address_on_up_interface_passes(self):
        self.inspect(self.valid())

    def test_absent_down_or_wrong_interface_refused(self):
        samples = [[], self.valid() * 2]
        for field, value in (('ifname', 'en0'), ('flags', ['BROADCAST']),
                             ('operstate', 'DOWN'), ('operstate', 'UNKNOWN')):
            data = self.valid()
            data[0][field] = value
            samples.append(data)
        for data in samples:
            with self.subTest(data=data):
                with self.assertRaises(network.PrivateNetworkError):
                    self.inspect(data)

    def test_address_prefix_scope_and_validity_drift_refused(self):
        for field, value in (('local', '10.156.100.61'), ('prefixlen', 32),
                             ('family', 'inet6'), ('scope', 'host'),
                             ('tentative', True), ('dadfailed', True),
                             ('valid_life_time', 0)):
            with self.subTest(field=field, value=value):
                data = self.valid()
                data[0]['addr_info'][0][field] = value
                with self.assertRaises(network.PrivateNetworkError):
                    self.inspect(data)

    def test_malformed_interface_data_refused(self):
        samples = [None, {}, [None], [[]]]
        for field, value in (('flags', 'UP'), ('addr_info', None), ('addr_info', [None])):
            data = self.valid()
            data[0][field] = value
            samples.append(data)
        for data in samples:
            with self.subTest(data=data):
                with self.assertRaises(network.PrivateNetworkError):
                    self.inspect(data)

    def test_missing_or_duplicate_address_refused(self):
        for addresses in ([], self.valid()[0]['addr_info'] * 2):
            with self.subTest(addresses=addresses):
                data = self.valid()
                data[0]['addr_info'] = addresses
                with self.assertRaises(network.PrivateNetworkError):
                    self.inspect(data)


class InstallationDriftTests(unittest.TestCase):
    """Installed metadata/manager observations are fixtures; no Linux calls."""
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.units = network.expected_units()
        self.policy_bytes = json.dumps(network.EXPECTED).encode()
        self.helper_bytes = (ROOT / 'scripts/control/private_network.py').read_bytes()
        self.changed_unit = None
        self.info_override = {}
        self.pending_dropin = None
        self.package = '255.4-1ubuntu8.16'
        self.stack.enter_context(patch.object(network, '__file__', str(network.HELPER)))
        self.stack.enter_context(patch.object(network.os, 'geteuid', return_value=0))
        self.stack.enter_context(patch.object(network.sys, 'platform', 'linux'))
        self.stack.enter_context(patch.object(network, '_protected', side_effect=self.protected))
        self.stack.enter_context(patch.object(network, '_show', side_effect=self.show))
        self.stack.enter_context(patch.object(network.Path, 'exists', autospec=True,
                                            side_effect=lambda path: str(path) == self.pending_dropin))
        self.stack.enter_context(patch.object(network.Path, 'is_symlink', return_value=False))
        self.stack.enter_context(patch.object(network.Path, 'is_file', return_value=True))
        self.stack.enter_context(patch.object(network.os, 'access', return_value=True))
        self.stack.enter_context(patch.object(network, '_run', side_effect=self.command))

    def protected(self, path, mode, maximum=1024 * 1024):
        if path == network.POLICY:
            return self.policy_bytes
        if path == network.HELPER:
            return self.helper_bytes
        self.assertEqual(path.parent, network.UNIT_DIR)
        content = self.units[path.name].encode()
        return content + b'# unreviewed edit\n' if path.name == self.changed_unit else content

    def show(self, name):
        return {'FragmentPath': str(network.UNIT_DIR / name), 'DropInPaths': '',
                'NeedDaemonReload': 'no', **self.info_override}

    def command(self, args):
        self.assertEqual(args, ['/usr/bin/dpkg-query', '--show',
                                '--showformat=${Version}', 'systemd'])
        return self.package

    def test_matching_installation_returns_all_source_hashes(self):
        signature = network._installation()
        self.assertEqual(set(signature), {'helper', 'policy', *self.units})
        self.assertTrue(all(len(value) == 64 for value in signature.values()))

    def test_modified_unit_bytes_refused(self):
        for name in self.units:
            with self.subTest(unit=name):
                self.changed_unit = name
                with self.assertRaisesRegex(network.PrivateNetworkError, 'unit drift'):
                    network._installation()

    def test_effective_override_or_stale_manager_refused(self):
        for field, value in (('FragmentPath', '/run/systemd/system/foreign.socket'),
                             ('FragmentPath', ''), ('DropInPaths', '/etc/override.conf'),
                             ('NeedDaemonReload', 'yes'), ('NeedDaemonReload', None)):
            with self.subTest(field=field, value=value):
                self.info_override = {field: value}
                with self.assertRaisesRegex(network.PrivateNetworkError, 'effective unit drift'):
                    network._installation()

    def test_pending_global_prefix_or_unit_dropins_refused(self):
        for directory in ('socket.d', 'service.d', 'llm-.socket.d',
                          'llm-private-.service.d', 'llm-private-control.socket.d', 'llm-private-control.socket.wants',
                          'llm-private-glm.service.requires', 'llm-private-qwen38.service.upholds'):
            with self.subTest(directory=directory):
                self.pending_dropin = '/run/systemd/system/' + directory
                with self.assertRaisesRegex(network.PrivateNetworkError, 'drop-in'):
                    network._installation()

    def test_unreviewed_systemd_package_refused(self):
        self.package = '255.4-1ubuntu8.17'
        with self.assertRaisesRegex(network.PrivateNetworkError, 'approved version'):
            network._installation()


class SourceUnitsTests(unittest.TestCase):
    def test_exact_six_fixed_units_and_prebind_rule_order(self):
        expected_names = {f'llm-private-{role}.{kind}'
                          for role in ('control', 'glm', 'qwen38')
                          for kind in ('socket', 'service')}
        self.assertEqual(set(network.expected_units()), expected_names)
        for role, port in (('control', 30000), ('glm', 30002), ('qwen38', 30004)):
            with self.subTest(role=role):
                prefix = ROOT / 'configs/network' / ('llm-private-' + role)
                socket = Path(str(prefix) + '.socket').read_text()
                service = Path(str(prefix) + '.service').read_text()
                s = configparser.ConfigParser(strict=False, interpolation=None)
                s.read_string(socket)
                p = configparser.ConfigParser(strict=False, interpolation=None)
                p.read_string(service)
                self.assertEqual(s['Socket']['ListenStream'], f'10.156.100.60:{port}')
                self.assertEqual(s['Socket']['Accept'], 'no')
                self.assertEqual(s['Socket']['FreeBind'], 'no')
                self.assertEqual(s['Socket']['BindToDevice'], 'enp6s18')
                pre = [line for line in socket.splitlines() if line.startswith('ExecStartPre=')]
                self.assertEqual(pre, [
                    'ExecStartPre=/usr/bin/python3 -I -B /usr/local/lib/llm-server/'
                    'private-network/private_network.py apply',
                    'ExecStartPre=/usr/bin/python3 -I -B /usr/local/lib/llm-server/'
                    'private-network/private_network.py check'])
                self.assertEqual(s['Unit']['DefaultDependencies'], 'no')
                self.assertIn('network-online.target', s['Unit']['After'].split())
                self.assertEqual(s['Install']['WantedBy'], 'multi-user.target')
                self.assertEqual(p['Service']['Type'], 'notify')
                self.assertEqual(p['Service']['DynamicUser'], 'yes')
                self.assertEqual(p['Service']['NoNewPrivileges'], 'yes')
                self.assertEqual(p['Service']['PrivateNetwork'], 'no')
                self.assertEqual(p['Service']['StandardOutput'], 'null')
                self.assertEqual(p['Service']['StandardError'], 'null')
                self.assertEqual(p['Service']['ExecStart'],
                                 '/usr/lib/systemd/systemd-socket-proxyd '
                                 f'--connections-max=16 127.0.0.1:{port}')
                self.assertEqual(p['Unit']['BindsTo'], f'llm-private-{role}.socket')
                self.assertNotIn('--exit-idle-time', service)
                self.assertNotIn('RuntimeMaxSec', service)
                self.assertNotIn('Environment', socket + service)
                self.assertNotIn('LoadCredential', socket + service)

    def test_source_check_executes_no_host_commands(self):
        with patch.object(network, '_run', side_effect=AssertionError('host command forbidden')):
            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(network.main(['source-check']), 0)
            self.assertIn('systemd runtime NOT_TESTED', output.getvalue())

    def test_source_check_refuses_policy_or_unit_drift(self):
        with tempfile.TemporaryDirectory(prefix='.n1s-source-test-', dir=ROOT) as folder:
            root = Path(folder)
            config = root / 'configs/network'
            config.mkdir(parents=True)
            script = root / 'scripts/control/private_network.py'
            script.parent.mkdir(parents=True)
            policy = ROOT / 'configs/network/ai-vm-private-api.json'
            originals = {'ai-vm-private-api.json': policy.read_text(), **network.expected_units()}
            for name, content in originals.items():
                (config / name).write_text(content)
            with patch.object(network, '__file__', str(script)):
                network.source_check()
                for name, content in originals.items():
                    with self.subTest(file=name):
                        changed = (content.replace('10.156.100.60', '0.0.0.0')
                                   if name.endswith(('.json', '.socket'))
                                   else content.replace('127.0.0.1:', '0.0.0.0:'))
                        (config / name).write_text(changed)
                        with self.assertRaises(network.PrivateNetworkError):
                            network.source_check()
                        (config / name).write_text(content)


if __name__ == '__main__':
    unittest.main()
