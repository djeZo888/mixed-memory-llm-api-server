"""Focused N1S ingress simulation: no actual firewall, units, network or API calls."""
from contextlib import nullcontext
import copy
import json
from pathlib import Path
import shlex
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.control import private_network as net

BASE = '-P INPUT ACCEPT\n-P FORWARD DROP\n-P OUTPUT ACCEPT\n-A INPUT -p tcp -m tcp --dport 22 -j ACCEPT\n'


class Filter:
    """Tiny command recorder; only the helper's narrow mutation vocabulary exists."""
    def __init__(self, raw=BASE):
        self.rows = [shlex.split(line) for line in raw.splitlines()]
        self.writes = []
        self.fail_at = None

    def raw(self):
        return '\n'.join(shlex.join(row) for row in self.rows) + '\n'

    def ipt(self, *args):
        if args == ('-S',):
            return self.raw()
        self.writes.append(args)
        if len(self.writes) == self.fail_at:
            raise net.PrivateNetworkError('simulated interrupted write')
        op, chain, *rest = args
        if op == '-N':
            self.rows.append(['-N', chain])
        elif op == '-A':
            self.rows.append(['-A', chain, *rest])
        elif op == '-I':
            assert rest.pop(0) == '1'
            position = next((i for i, row in enumerate(self.rows) if row[:2] == ['-A', chain]), len(self.rows))
            self.rows.insert(position, ['-A', chain, *rest])
        elif op == '-D':
            self.rows.remove(['-A', chain, *rest])
        elif op == '-X':
            assert not any(row[:2] == ['-A', chain] for row in self.rows)
            self.rows.remove(['-N', chain])
        else:
            raise AssertionError('unexpected or broad mutation: ' + repr(args))
        return ''


class IngressTests(unittest.TestCase):
    def setUp(self):
        self.filter = Filter()
        self.receipt = None
        self.signature = {'helper': 'fixture-reviewed-hash'}
        self.stopped = True
        for name, replacement in (
            ('_installation', lambda: self.signature), ('_interface', lambda: None),
            ('_lock', nullcontext), ('_snapshot', self.filter.raw),
            ('_ipt', self.filter.ipt), ('_state', lambda _: self.receipt),
            ('_write_state', self.write_state), ('_units_stopped', self.require_stopped),
        ):
            active = patch.object(net, name, replacement)
            active.start()
            self.addCleanup(active.stop)

    def write_state(self, signature, before):
        self.receipt = {'owner': net.TAG, 'signature': signature, 'before_filter': before}

    def require_stopped(self):
        net._require(self.stopped, 'transport active')

    def test_apply_first_jump_chain_before_jump_idempotent_exact_inverse(self):
        net.operate('apply')
        self.assertEqual(self.filter.writes[0], ('-N', net.CHAIN))
        self.assertEqual(self.filter.writes[4][:3], ('-I', 'INPUT', '1'))
        self.assertEqual(net._inspect(self.filter.raw())[0], 'complete')
        self.assertEqual(self.receipt['before_filter'], BASE)
        count = len(self.filter.writes)
        net.operate('apply')
        net.operate('check')
        self.assertEqual(len(self.filter.writes), count)
        net.operate('remove')
        self.assertEqual(self.filter.raw(), BASE)
        self.assertIsNotNone(self.receipt)  # historical backup survives inverse
        self.assertTrue(all(c[0] in ('-N', '-A', '-I', '-D', '-X') for c in self.filter.writes))

    def test_absence_and_stale_receipt_are_not_effective_protection(self):
        with self.assertRaises(net.PrivateNetworkError):
            net.operate('check')
        net.operate('apply')
        self.filter.rows = Filter().rows  # reboot loses filter, receipt remains
        with self.assertRaises(net.PrivateNetworkError):
            net.operate('check')
        net.operate('apply')
        net.operate('check')

    def test_dry_run_no_rule_or_receipt_mutations(self):
        net.operate('apply', dry_run=True)
        self.assertEqual(self.filter.writes, [])
        self.assertIsNone(self.receipt)
        net.operate('apply')
        before, count = self.filter.raw(), len(self.filter.writes)
        net.operate('remove', dry_run=True)
        self.assertEqual(self.filter.raw(), before)
        self.assertEqual(len(self.filter.writes), count)

    def test_unowned_matching_assets_refused(self):
        net.operate('apply')
        self.receipt = None
        for action in ('apply', 'check', 'remove', 'preflight'):
            with self.subTest(action=action), self.assertRaises(net.PrivateNetworkError):
                net.operate(action)

    def test_precedence_duplicate_foreign_reference_and_extra_chain_rule_denied(self):
        net.operate('apply')
        original = copy.deepcopy(self.filter.rows)
        jump, _ = net._rules()
        bad_rows = [
            ['-A', 'INPUT', '-j', 'ACCEPT'],
            ['-A', 'INPUT', *jump],
            ['-A', 'FORWARD', '-j', net.CHAIN],
            ['-A', net.CHAIN, '-j', 'ACCEPT'],
        ]
        for row in bad_rows:
            self.filter.rows = [row, *copy.deepcopy(original)]
            for action in ('apply', 'check', 'remove'):
                with self.subTest(row=row, action=action), self.assertRaises(net.PrivateNetworkError):
                    net.operate(action)

    def test_interruption_never_exposes_partial_chain_and_exact_inverse_recovers(self):
        for fail_at in (1, 2, 3, 4, 5):
            with self.subTest(fail_at=fail_at):
                self.filter.rows = Filter().rows
                self.filter.writes = []
                self.receipt = None
                self.filter.fail_at = fail_at
                with self.assertRaises(net.PrivateNetworkError):
                    net.operate('apply')
                self.assertNotIn(['-A', 'INPUT', *net._rules()[0]], self.filter.rows)
                self.filter.fail_at = None
                net.operate('remove')
                self.assertEqual(self.filter.raw(), BASE)

    def test_inverse_refuses_active_transport(self):
        net.operate('apply')
        self.stopped = False
        before = self.filter.raw()
        with self.assertRaises(net.PrivateNetworkError):
            net.operate('remove')
        self.assertEqual(self.filter.raw(), before)

    def test_lan_interface_and_loopback_then_terminal_drop(self):
        jump, rules = net._rules()
        self.assertIn('10.156.100.60/32', jump)
        self.assertIn('30000,30002,30004,30006', jump)
        self.assertEqual(rules[0][:2], ['-i', 'lo'])
        self.assertEqual(rules[1][:4], ['-s', '10.156.100.0/24', '-i', 'enp6s18'])
        self.assertEqual(rules[2][-2:], ['-j', 'DROP'])


class OwnershipTests(unittest.TestCase):
    def test_static_inactive_services_and_disabled_sockets_allow_inverse(self):
        def show(name):
            return {'ActiveState': 'inactive', 'UnitFileState':
                    'disabled' if name.endswith('.socket') else 'static'}
        with patch.object(net, '_show', show):
            net._units_stopped()
        for info in ({'ActiveState': 'active', 'UnitFileState': 'static'},
                     {'ActiveState': 'inactive', 'UnitFileState': 'enabled'}):
            with patch.object(net, '_show', return_value=info), self.assertRaises(net.PrivateNetworkError):
                net._units_stopped()

    def test_receipt_signature_and_backup_drift_refused(self):
        signature = {'helper': 'reviewed'}
        receipt = {'owner': net.TAG, 'signature': signature, 'before_filter': BASE}
        with patch.object(Path, 'exists', return_value=True):
            with patch.object(net, '_protected', return_value=json.dumps(receipt)):
                self.assertEqual(net._state(signature), receipt)
                with self.assertRaises(net.PrivateNetworkError):
                    net._state({'helper': 'changed'})
            receipt['before_filter'] += '-N LLM-PRIVATE-IN\n'
            with patch.object(net, '_protected', return_value=json.dumps(receipt)), self.assertRaises(net.PrivateNetworkError):
                net._state(signature)


if __name__ == '__main__':
    unittest.main()
