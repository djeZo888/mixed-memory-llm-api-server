#!/usr/bin/env python3
"""Offline generated-policy packet fixtures; these do NOT execute Linux nft/Slirp."""
import importlib.util
import ipaddress
import json
import math
import os
import subprocess
import tempfile
import time
import shutil
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
receipts = load('causal_receipts', DEPLOY / 'engine/codex_receipts.py')
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


class OriginalCreationFixtures(unittest.TestCase):
    def identity(self, pid=None):
        pid=os.getpid() if pid is None else pid
        q=self.real_popen(['/bin/ps','-p',str(pid),'-o','lstart='],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        raw,err=q.communicate(timeout=2)
        if q.returncode!=0:raise ValueError('missing actual fixture birth')
        birth=str(int(time.mktime(time.strptime(raw.decode().strip(),'%a %b %d %H:%M:%S %Y'))))
        return {'pid':pid,'startTicks':birth,'uid':os.getuid(),'bootId':'source-mac-fixture','cgroupPath':'/fixture/parent'}

    def fixture(self,path,fail=None):
        self.real_popen=subprocess.Popen
        binding={'nonce':'a'*64,'runId':'h043-run','sessionId':'h043-session','sources':{'synthetic':'b'*64}}
        config=(path,binding)
        child=path/'creator.py'
        child.write_text("import os,sys,json\nfrom pathlib import Path\ngate=int(sys.argv[1])\nif os.read(gate,2)!=b'G':sys.exit(64)\nPath(sys.argv[2]).write_text(json.dumps({'actualPid':os.getpid(),'parentPid':os.getppid()}))\nsys.exit(7)\n")
        seen=[]
        def spawn(argv,**kwargs):
            if len(argv)>1 and argv[1]==str(DEPLOY/'engine/task-egress.py'):
                original=receipts.original(config,'scope-intent')
                self.assertEqual(original['creationState'],'PENDING')
                self.assertEqual(argv[4],original['unit'])
                self.assertFalse((path/'started.json').exists())
                p=self.real_popen([sys.executable,str(child),argv[3],str(path/'started.json')],**kwargs)
                seen.append({'argv':argv,'pid':p.pid,'pgid':os.getpgid(p.pid)})
                return p
            return self.real_popen(argv,**kwargs)
        module={k:getattr(receipts,k) for k in ('publish_scope_intent','publish_scope_creator','publish_scope_terminal')}
        module['process_identity']=self.identity
        if fail=='intent':module['publish_scope_intent']=lambda *a:(_ for _ in ()).throw(OSError('intent publication failed'))
        if fail=='creator':module['publish_scope_creator']=lambda *a:(_ for _ in ()).throw(OSError('creator publication failed'))
        with patch.object(guard.subprocess,'Popen',spawn),patch.object(receipts,'process_identity',self.identity):
            if fail=='intent':
                with self.assertRaises(OSError):guard.supervise_scope(['fixture'],module,config)
                code=None
            else:code=guard.supervise_scope(['fixture'],module,config)
        evidence=os.environ.get('H043_FIXTURE_EVIDENCE_DIR')
        if evidence:
            target=Path(tempfile.mkdtemp(prefix='scope-',dir=evidence));shutil.copytree(path,target,dirs_exist_ok=True)
            (target/'fixture-result.json').write_text(json.dumps({'failure':fail,'actualSupervisorResult':code,'actualCreatedProcesses':seen,'qualification':'MAC_SOURCE_FIXTURE_ONLY'}))
        return code,seen,config

    def test_original_intent_and_creator_birth_precede_real_gate_release_and_actual_terminal(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root).resolve();path.chmod(0o700);code,seen,config=self.fixture(path)
            self.assertEqual(code,7);self.assertEqual(len(seen),1)
            creator=receipts.original(config,'scope-creator');terminal=receipts.original(config,'scope-terminal')
            actual=json.loads((path/'started.json').read_text())
            self.assertEqual(actual['actualPid'],creator['creator']['pid']);self.assertEqual(actual['parentPid'],creator['parent']['pid'])
            self.assertEqual(terminal['creatorExit'],7);self.assertTrue(terminal['creatorReaped']);self.assertEqual(terminal['resourceState'],'UNKNOWN')
            self.assertFalse((path/'scope.ready').exists());self.assertFalse((path/'producer.ready').exists())

    def test_failed_intent_publication_has_no_creation_subprocess(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root).resolve();path.chmod(0o700);code,seen,config=self.fixture(path,'intent')
            self.assertEqual(seen,[]);self.assertFalse((path/'started.json').exists())

    def test_failed_creator_receipt_closes_pipe_without_hidden_child_creation(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root).resolve();path.chmod(0o700);code,seen,config=self.fixture(path,'creator')
            self.assertEqual(code,125);self.assertEqual(len(seen),1);self.assertFalse((path/'started.json').exists())
            terminal=receipts.original(config,'scope-terminal')
            self.assertEqual(terminal['creatorExit'],64);self.assertTrue(terminal['creatorReaped'])
            self.assertEqual(terminal['resourceState'],'UNKNOWN');self.assertFalse((path/'scope-creator.ready').exists())

    def test_unit_name_and_missing_or_contradictory_originals_fail_closed(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root).resolve();path.chmod(0o700)
            config=(path,{'nonce':'a'*64,'runId':'r','sessionId':'s','sources':{'fixture':'b'*64}})
            with self.assertRaises(FileNotFoundError):receipts.original(config,'scope-intent')
            with self.assertRaises(ValueError):receipts.publish_scope_intent(config,'caller-guess.scope',{})
            receipts.write_once(path,'scope-intent',receipts.causal(config,'codex-scope-intent-v1',unit='ai-harness-codex-'+'a'*32+'.scope',parent={},creationState='PENDING'))
            with self.assertRaises(ValueError):receipts.original((path,dict(config[1],nonce='c'*64)),'scope-intent')
            with self.assertRaises(FileNotFoundError):receipts.verify_creator(config,'ai-harness-codex-'+'a'*32+'.scope')
            self.assertEqual(receipts.original(config,'scope-intent')['creationState'],'PENDING')


if __name__ == '__main__':
    unittest.main(verbosity=2)
