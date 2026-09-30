#!/usr/bin/env python3
"""Offline generated-policy packet fixtures; these do NOT execute Linux nft/Slirp."""
import importlib.util
import ipaddress
import json
import math
from pathlib import Path
import re
import sys
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
DEPLOY = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec); spec.loader.exec_module(result)
    return result


policy = load('policy', DEPLOY / 'security/task-egress-policy.py')
guard = load('guard', DEPLOY / 'engine/task-egress.py')
nginx_guard = load('nginx_guard', DEPLOY / 'security/validate-nginx-boundary.py')
CONFIG = {'schema': 'h005-task-egress-v1', 'uid': 1000, 'dns_servers': ['127.0.0.53']}


def packet(rules, address, port, protocol='tcp', local=False, task=True):
    """Small independent interpreter of the emitted task_out rules, not kernel emulation."""
    if not task:
        return 'accept'
    ip = ipaddress.ip_address(address)
    for line in rules.split(' chain task_out {\n', 1)[1].split('\n }', 1)[0].splitlines():
        rule = line.strip()
        verdict = rule.rsplit(' ', 1)[-1]
        if rule == 'reject':
            return verdict
        if rule.startswith('fib '):
            if local:
                return verdict
            continue
        if rule.startswith(('ip ', 'ip6 ')):
            family, remainder = rule.split(' daddr ', 1)
            if (family == 'ip') != (ip.version == 4):
                continue
            if remainder.startswith('{'):
                addresses, remainder = remainder[1:].split('}', 1)
                networks = [ipaddress.ip_network(item.strip()) for item in addresses.split(',')]
            else:
                address_value, remainder = remainder.split(' ', 1)
                networks = [ipaddress.ip_network(address_value)]
            if not any(ip in network for network in networks):
                continue
            rule = remainder.strip()
        if rule.startswith('tcp ') and protocol != 'tcp':
            continue
        if rule.startswith('meta l4proto') and protocol not in ('tcp', 'udp'):
            continue
        if 'dport' in rule:
            expr = rule.split('dport ', 1)[1].rsplit(' ', 1)[0]
            ports = [int(item.strip()) for item in expr.strip('{} ').split(',')]
            if port not in ports:
                continue
        return verdict
    raise AssertionError('policy has no terminal rule')


class PacketFixtures(unittest.TestCase):
    def setUp(self):
        self.rules = policy.render(CONFIG)

    def test_slirp_private_host_and_node_control_denied_all_ports(self):
        # Host10.0.2.2 translation is127.0.0.1; DNS aliases and redirects end here too.
        for address in ('127.0.0.1', '127.2.3.4', '10.0.2.2', '10.156.100.61',
                        '10.156.100.60', '192.168.0.1', '172.19.0.1', '100.100.100.1',
                        '::1', 'fe80::1', 'fd00::61', '::ffff:10.156.100.61', '64:ff9b::a9c:643d'):
            for port in (80, 443, 8080, 8083, 30000, 30002, 30008, 65535):
                with self.subTest(address=address, port=port):
                    self.assertEqual(packet(self.rules, address, port), 'reject')

    def test_gateway_search_and_public_research_preserved(self):
        for port in (8081, 8082):
            self.assertEqual(packet(self.rules, '127.0.0.1', port, local=True), 'accept')
            self.assertEqual(packet(self.rules, '10.156.100.61', port, local=True), 'reject')
        for address in ('93.184.216.34', '2606:4700:4700::1111'):
            for port in (80, 443):
                self.assertEqual(packet(self.rules, address, port), 'accept')
            self.assertEqual(packet(self.rules, address, 30000), 'reject')
            self.assertEqual(packet(self.rules, address, 443, protocol='udp'), 'reject')
        self.assertEqual(packet(self.rules, '127.0.0.53', 53, protocol='udp', local=True), 'accept')
        self.assertEqual(packet(self.rules, '127.0.0.1', 53, protocol='udp', local=True), 'reject')

    def test_local_global_alias_rejected_other_host_processes_unaffected(self):
        self.assertEqual(packet(self.rules, '93.184.216.34', 80, local=True), 'reject')
        self.assertEqual(packet(self.rules, '10.156.100.60', 30000, task=False), 'accept')

    def test_configuration_cannot_inject_policy_or_general_flush(self):
        for updates in ({'uid': 0}, {'uid': True}, {'dns_servers': ['127.0.0.1; accept']},
                        {'dns_servers': ['::']}, {'dns_servers': []}, {'command': 'anything'}):
            with self.assertRaises((ValueError, TypeError)):
                policy.render(CONFIG | updates)
        self.assertNotIn('flush', self.rules)
        self.assertIn('socket cgroupv2 level 4 "user.slice/user-1000.slice/user@1000.service/aiharnesstasks.slice"', self.rules)


class GuardFixtures(unittest.TestCase):
    def setUp(self):
        self.value = {'schema': 'h005-task-egress-v1', 'uid': 1000, 'boot_id': 'fixture-boot',
                      'cgroup_path': policy.cgroup_path(1000), 'cgroup_inode': 23,
                      'nft_sha256': 'a' * 64, 'checked_boottime': 100}

    def test_fresh_exact_boot_slice_and_identity_required(self):
        self.assertEqual(guard.validate(self.value, 1000, 'fixture-boot', 23, 105), policy.cgroup_path(1000))
        for delta in ({'boot_id': 'old-boot'}, {'uid': 1001}, {'cgroup_inode': 24},
                      {'cgroup_path': 'other.slice'}, {'checked_boottime': 98},
                      {'checked_boottime': 106}, {'checked_boottime': math.nan},
                      {'nft_sha256': 'bad'}):
            with self.subTest(delta=delta), self.assertRaises(ValueError):
                guard.validate(self.value | delta, 1000, 'fixture-boot', 23, 105)

    def test_unconfigured_launch_fails_closed_before_exec(self):
        with patch.object(guard, 'RECEIPT', Path('/nonexistent-h005-fixture/receipt')):
            with self.assertRaises(FileNotFoundError):
                guard.verify()

    def test_no_scope_or_policy_bypass_knob(self):
        source = (DEPLOY / 'engine/task-egress.py').read_text()
        self.assertNotIn('os.environ', source)
        self.assertIn("'--expand-environment=no'", source)
        self.assertIn("startswith('0::/' + prefix + '/')", source)


class ProxyFixtures(unittest.TestCase):
    def test_inherited_forwarded_peer_rewriting_rejected_without_dumping_config(self):
        merged = '\n'.join((DEPLOY / 'nginx' / name).read_text() for name in
                           ('ai-harness.conf', 'status-proxy.inc', 'admin-peer-deny.inc'))
        nginx_guard.validate(merged)
        for directive in ('set_real_ip_from 127.0.0.1;', 'real_ip_header X-Forwarded-For;', 'real_ip_recursive on;'):
            with self.assertRaises(ValueError):
                nginx_guard.validate(directive + '\n' + merged)

    def test_independent_uds_routes_admin_peer_policy_and_read_only_alias(self):
        nginx = (DEPLOY / 'nginx/ai-harness.conf').read_text()
        proxy = (DEPLOY / 'nginx/status-proxy.inc').read_text()
        deny = (DEPLOY / 'nginx/admin-peer-deny.inc').read_text()
        self.assertIn('proxy_pass http://unix:/run/ai-harness-status/http.sock;', proxy)
        for prefix in ('location = /admin', 'location ^~ /api/admin/'):
            section = nginx.split(prefix, 1)[1].split('\n    }', 1)[0]
            self.assertIn('include /etc/ai-harness/admin-peer-deny.inc;', section)
        for peer in ('127.0.0.0/8', '::1', '10.156.100.61'):
            self.assertIn('deny ' + peer + ';', deny)
        alias = nginx.split('server_name status.ai-harness;', 1)[1]
        self.assertNotIn('location = /admin', alias)
        self.assertIn('location / { return 404; }', alias)
        self.assertIn('limit_except GET { deny all; }', alias)
        # Original human-only canvas approval mint route remains actual-peer guarded.
        approval = nginx.split('approval-token$', 1)[1].split('\n    }', 1)[0]
        self.assertIn('deny 10.156.100.61;', approval)
        self.assertIn('/etc/ai-harness/image-approval-proxy.conf;', approval)
        launcher = (DEPLOY / 'run-engine.sh').read_text()
        self.assertNotIn('--volume /run', launcher)


if __name__ == '__main__':
    unittest.main(verbosity=2)
