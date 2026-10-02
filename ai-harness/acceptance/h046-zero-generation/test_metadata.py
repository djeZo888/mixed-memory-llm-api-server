#!/usr/bin/env python3
"""Offline original-ledger and current-owner guard fixtures; no live action."""
import copy
import datetime as dt
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile
import unittest
from types import SimpleNamespace

import key_inventory as inventory
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
SERVER = HERE.parents[1] / 'server' / 'src'
SPEC = importlib.util.spec_from_file_location('h046_metadata', HERE / 'metadata.py')
metadata = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(metadata)


class MetadataFixtures(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='.metadata-fixture-', dir=HERE)
        self.root = Path(self.temporary.name).resolve(); os.chmod(self.root, 0o700)
        self.database = self.root / 'harness.sqlite'
        connection = sqlite3.connect(self.database)
        # Schema comes from the exact sealed existing source, including lazily
        # created recovery tables, not a mirror typed into the test.
        for name in ('store.ts', 'gateway-ownership.ts', 'image-broker.ts'):
            source = (SERVER / name).read_text()
            statements = re.findall(r'CREATE TABLE IF NOT EXISTS [A-Za-z0-9_]+\s*\(.*?\);', source, re.S)
            self.assertTrue(statements, name)
            for statement in statements:
                connection.execute(statement)
        connection.execute("INSERT INTO sessions(id,title,created_at,updated_at,status,context,workspace_id) VALUES('s1','original','a','a','idle','PRIVATE ORIGINAL CONTEXT','w1')")
        connection.execute("INSERT INTO messages VALUES('m1','s1','user','PRIVATE ORIGINAL MESSAGE','a','r1','[]')")
        connection.execute("INSERT INTO runs VALUES('r1','s1','w1','turn','PRIVATE ORIGINAL PROMPT','[]','completed','a','a')")
        connection.execute("INSERT INTO files VALUES('f1','s1','input','original.txt','original.txt','text/plain',5)")
        connection.execute("INSERT INTO h021_session_engines(session_id,engine_kind,workspace_id) VALUES('s1','codex','w1')")
        connection.execute("INSERT INTO h021_gateway_requests VALUES('g1','s1','settled','PRIVATE ORIGINAL GATEWAY JSON')")
        connection.execute("INSERT INTO h041_gateway_admissions(sequence,request_id,session_id) VALUES(7,'g1','s1')")
        connection.execute("INSERT INTO h003_image_outputs VALUES('w1','image.png','image1')")
        connection.execute("INSERT INTO h002_message_meta VALUES('m1','PRIVATE ORIGINAL META')")
        connection.commit(); connection.close(); os.chmod(self.database, 0o600)
        self.database_spec = {'path': str(self.database), 'identity': metadata.file_identity(self.database), 'retainedSessionIds': ['s1']}

    def tearDown(self):
        self.temporary.cleanup()

    def change(self, sql):
        connection = sqlite3.connect(self.database)
        connection.execute(sql); connection.commit(); connection.close()

    def test_source_schema_and_stable_originals(self):
        before = metadata.observe_database(self.database_spec)
        self.assertEqual(before, metadata.observe_database(self.database_spec))
        self.assertEqual(before[1], {'global': 7, 'sessions': {'s1': 7}})
        self.assertEqual(before[2], ['g1'])
        self.assertEqual(before[3]['sessions']['s1']['h003_image_outputs']['rows'], 1)
        self.assertEqual(before[3]['sessions']['s1']['h002_message_meta']['rows'], 1)
        self.assertNotIn(b'PRIVATE ORIGINAL', metadata.canonical(before))

    def test_message_and_companion_original_changes(self):
        before = metadata.observe_database(self.database_spec)[3]
        self.change("UPDATE messages SET content='changed original'")
        changed = metadata.observe_database(self.database_spec)[3]
        self.assertNotEqual(before['sessions']['s1']['messages'], changed['sessions']['s1']['messages'])
        self.change("UPDATE h002_message_meta SET data='changed companion'")
        after = metadata.observe_database(self.database_spec)[3]
        self.assertNotEqual(changed['sessions']['s1']['h002_message_meta'], after['sessions']['s1']['h002_message_meta'])

    def test_gateway_originals_and_sequence_preserved(self):
        before = metadata.observe_database(self.database_spec)
        self.change("INSERT INTO h041_gateway_admissions(sequence,request_id,session_id) VALUES(8,'g2','s1')")
        after = metadata.observe_database(self.database_spec)
        self.assertNotEqual(before[1], after[1])
        self.assertNotEqual(before[3]['gatewayAdmissions'], after[3]['gatewayAdmissions'])

    def test_active_runs_and_nonidle_owners_denied(self):
        self.change("UPDATE runs SET status='running'")
        with self.assertRaises(metadata.Refused): metadata.observe_database(self.database_spec)
        self.change("UPDATE runs SET status='completed'")
        self.change("UPDATE h021_session_engines SET ownership='uncertain'")
        with self.assertRaises(metadata.Refused): metadata.observe_database(self.database_spec)

    def retained_owner_fixture(self):
        connection = sqlite3.connect(self.database)
        connection.execute("INSERT INTO sessions(id,title,created_at,updated_at,status,context,workspace_id) VALUES('historical-s2','preserve failed original','a','a','interrupted','PRIVATE FAILED ORIGINAL CONTEXT','w2')")
        connection.execute("INSERT INTO messages VALUES('historical-m2','historical-s2','assistant','PRIVATE FAILED ORIGINAL ANSWER','a','historical-r2','[]')")
        connection.execute("INSERT INTO runs VALUES('historical-r2','historical-s2','w2','turn','PRIVATE FAILED ORIGINAL PROMPT','[]','interrupted','a','a')")
        connection.execute("INSERT INTO h021_session_engines(session_id,engine_kind,workspace_id,ownership,active_turn_id) VALUES('historical-s2','codex','w2','uncertain','native-historical-turn')")
        connection.commit(); connection.close()
        retained = dict(self.database_spec, retainedUncertainOwners=[['historical-s2','uncertain','native-historical-turn','interrupted']])
        return retained

    def test_exact_root_listed_historical_uncertain_preserved_globally(self):
        retained = self.retained_owner_fixture()
        with self.assertRaises(metadata.Refused): metadata.observe_database(self.database_spec)
        before = metadata.observe_database(retained)
        self.assertEqual(before, metadata.observe_database(retained))
        self.assertEqual(before[4]['activeRuns'], 0)
        self.assertEqual(before[4]['nonidleEngines'], 1)
        self.assertEqual(before[4]['retainedUncertainOwners'], retained['retainedUncertainOwners'])
        self.assertEqual(before[3]['nonidleNativeEngineOriginals']['rows'], 1)
        self.assertEqual(before[3]['sessions']['historical-s2']['messages']['rows'], 1)
        self.assertNotIn(b'PRIVATE FAILED ORIGINAL', metadata.canonical(before))
        self.change("UPDATE messages SET content='changed failed original' WHERE id='historical-m2'")
        self.assertNotEqual(before[3], metadata.observe_database(retained)[3])

    def test_historical_owner_packet_stale_or_running_denied(self):
        retained = self.retained_owner_fixture()
        stale = dict(retained, retainedUncertainOwners=[['historical-s2','uncertain','wrong-turn','interrupted']])
        with self.assertRaises(metadata.Refused): metadata.observe_database(stale)
        self.change("UPDATE sessions SET status='running' WHERE id='historical-s2'")
        with self.assertRaises(metadata.Refused): metadata.observe_database(retained)
        running_packet = dict(retained, retainedUncertainOwners=[['historical-s2','uncertain','native-historical-turn','running']])
        with self.assertRaises(metadata.Refused): metadata.observe_database(running_packet)

    def test_historical_root_listing_never_allows_active_run(self):
        retained = self.retained_owner_fixture()
        self.change("UPDATE runs SET status='running' WHERE id='historical-r2'")
        with self.assertRaises(metadata.Refused): metadata.observe_database(retained)

    def test_stale_database_inode_denied(self):
        replacement = self.root / 'replacement.sqlite'
        replacement.write_bytes(self.database.read_bytes()); os.chmod(replacement, 0o600)
        replacement.replace(self.database)
        with self.assertRaises(metadata.Refused): metadata.observe_database(self.database_spec)

    def test_only_source_derived_native_evidence_absence_permitted(self):
        native_key = Path(str(self.database) + '.h041-native-evidence.key')
        expected = {'path': str(native_key), 'identity': None}
        observed = metadata.observe_protected(expected, str(self.database))
        self.assertEqual(observed, dict(expected, state='ABSENT'))
        self.assertEqual(observed, metadata.observe_protected(expected, str(self.database)))
        self.assertFalse(native_key.exists())
        for missing in ('ordinary.key', 'credential.key', 'other.h041-native-evidence.key'):
            with self.subTest(path=missing), self.assertRaises(metadata.Refused):
                metadata.observe_protected({'path': str(self.root / missing), 'identity': None}, str(self.database))
        native_key.write_bytes(b'PRIVATE EXISTING NATIVE EVIDENCE KEY'); os.chmod(native_key, 0o600)
        with self.assertRaises(metadata.Refused): metadata.observe_protected(expected, str(self.database))
        actual = metadata.file_identity(native_key)
        self.assertEqual(metadata.observe_protected({'path': str(native_key), 'identity': actual}, str(self.database)),
                         {'path': str(native_key), 'identity': actual})

    def test_stale_unit_source_denied_without_systemctl(self):
        unit = self.root / 'sova.service'; unit.write_text('[Service]\nExecStart=/usr/bin/false\n'); os.chmod(unit, 0o600)
        spec = {'unit': 'sova.service', 'unitFile': str(unit), 'unitSha256': '0' * 64}
        with patch.object(metadata.subprocess, 'run') as command:
            with self.assertRaises(metadata.Refused): metadata.observe_unit(spec, {'uid': os.getuid()})
            command.assert_not_called()

    def test_current_owner_independent_proc_observation(self):
        owner = {'bootId': '12345678-1234-1234-1234-123456789abc', 'uid': os.getuid(), 'pid': 1234,
                 'startTicks': '4321', 'pgid': 1234, 'cgroupPath': '/fixture.scope'}
        fields = ['S', '100', '1234', '1234'] + ['0'] * 15 + ['4321']
        values = {'/proc/1234/stat': '1234 (actual process) ' + ' '.join(fields),
                  '/proc/1234/status': 'Uid:\t' + '\t'.join([str(os.getuid())] * 4),
                  '/proc/1234/cgroup': '0::/fixture.scope\n',
                  '/proc/sys/kernel/random/boot_id': owner['bootId']}
        def read(value, *args, **kwargs): return values[str(value)]
        with patch.object(Path, 'read_text', read):
            self.assertEqual(metadata.observe_owner(owner), owner)
            for field, bad in [('startTicks', '9999'), ('pgid', 2222), ('cgroupPath', '/wrong'), ('bootId', 'wrong')]:
                stale = dict(owner, **{field: bad})
                with self.subTest(field=field), self.assertRaises(metadata.Refused): metadata.observe_owner(stale)

    def test_duplicate_and_nonfinite_json_denied(self):
        for raw in (b'{"x":1,"x":2}', b'{"x":NaN}'):
            with self.assertRaises(metadata.Refused): metadata.strict_json(raw)



class RemoteTopology(unittest.TestCase):
    def fixture(self):
        now = 1780401600.0
        executable = {'path': '/opt/reviewed/llama-server', 'sha256': '2' * 64,
                      'identity': {'dev': 1, 'ino': 2, 'uid': 1000, 'gid': 1000,
                                   'mode': 0o755, 'nlink': 1, 'size': 123, 'mtimeNs': 111, 'ctimeNs': 222}}
        source = dict(executable, path='/opt/reviewed/run-engine.sh', sha256='3' * 64)
        owners = {name: {'bootId': '12345678-1234-1234-1234-123456789abc',
                  'uid': 1000, 'pid': pid, 'startTicks': str(pid * 10), 'pgid': pid,
                  'cgroupPath': '/models/' + name, 'executable': executable,
                  'cmdlineSha256': '4' * 64, 'sourceFiles': {'launcher': source}}
                  for name, pid in [('qwen1', 1111), ('qwen2', 2222), ('mimo', 3333)]}
        policy = {'schema': 'h046-root-remote-owner-policy-v1', 'purpose': 'native-carrier',
                  'localHost': 'aiharness', 'remoteHost': 'ai-vm', 'kernelHost': 'aivm',
                  'sourceCommit': '1' * 40, 'bindingId': 'a' * 64,
                  'collectorSha256': hashlib.sha256(b'READ_ONLY_SOURCE_FIXTURE').hexdigest(),
                  'sshArgv': ['/usr/bin/ssh', '-o', 'BatchMode=yes', '-o', 'ForwardAgent=no',
                              '-o', 'ClearAllForwardings=yes', 'ai-vm', 'python3 -I -B -'],
                  'beforePath': '/root-originals/' + 'a' * 64 + '.before.remote-original.json',
                  'afterPath': '/root-originals/' + 'a' * 64 + '.after.remote-original.json',
                  'afterAnchor': '/proof/channel-scope-terminal.json',
                  'clockDomain': 'ai-harness-realtime-utc'}
        packet = {'schema': 'h046-root-remote-owner-original-v1', 'stage': 'before',
                  'policySha256': hashlib.sha256(inventory.canonical(policy)).hexdigest(),
                  'startedUtc': dt.datetime.fromtimestamp(now - 2, dt.timezone.utc).isoformat(),
                  'finishedUtc': dt.datetime.fromtimestamp(now - 1, dt.timezone.utc).isoformat(),
                  'argv': policy['sshArgv'], 'actualExitCode': 0,
                  'stdin': 'READ_ONLY_SOURCE_FIXTURE',
                  'stdout': inventory.canonical({'host': 'ai-vm', 'kernelHost': 'aivm', 'owners': owners}).decode(),
                  'stderr': '', 'anchor': None}
        return now, owners, policy, packet

    def observe(self, owners, policy, packet, now, stage='before'):
        with patch.object(inventory, 'root_original', return_value=inventory.canonical(packet)), \
             patch.object(inventory.os, 'uname', return_value=SimpleNamespace(nodename='aiharness')), \
             patch.object(inventory.time, 'time', return_value=now), \
             patch.object(inventory, 'observe_process', side_effect=AssertionError('foreign PID in local proc')):
            return inventory.observe_remote_owners(owners, policy, stage)

    def test_local_app_and_three_remote_models_never_share_proc_or_boot(self):
        now, owners, policy, packet = self.fixture()
        observed = self.observe(owners, policy, packet, now)
        self.assertEqual(set(observed), {'qwen1', 'qwen2', 'mimo'})
        self.assertTrue(all(v['host'] == 'ai-vm' for v in observed.values()))
        app = {'bootId': 'different-local-boot', 'uid': 1000, 'pid': 5555,
               'startTicks': '999', 'pgid': 5555, 'cgroupPath': '/app.slice/ai-harness.service'}
        helper = HERE / 'key_inventory.py'
        value = {'appSourceCommit': policy['sourceCommit'], 'controlRunId': policy['bindingId'],
                 'output': '/proof', 'fileGraph': {str(helper): metadata.sha(helper.read_bytes())},
                 'metadata': {'application': {'unit': 'ai-harness.service',
                     'unitFile': '/home/user/.config/systemd/user/ai-harness.service', 'owner': app},
                     'generalOwners': owners, 'remoteOwnerObservation': policy,
                     'database': {'path': '/home/user/.local/share/ai-harness/harness.sqlite'},
                     'protectedFiles': [{'path': '/protected', 'identity': {}}]}}
        with patch.object(metadata.os, 'getuid', return_value=1000), \
             patch.object(metadata.os, 'geteuid', return_value=1000), \
             patch.object(metadata, 'observe_owner', return_value=app) as local, \
             patch.object(metadata, 'observe_unit', return_value={}), \
             patch.object(metadata, 'observe_protected', return_value={'path': '/protected', 'identity': {}}), \
             patch.object(metadata, 'observe_database', return_value=({}, {}, [], {}, {})), \
             patch.object(metadata, 'observe_remote_owners', return_value=observed) as remote:
            before = metadata.snapshot(value, 'before')
            after = metadata.snapshot(value, 'after')
        self.assertEqual(before, after)
        self.assertEqual(before['identity']['applicationHost'], 'ai-harness')
        self.assertEqual([call.args[0]['pid'] for call in local.call_args_list], [5555] * 4)
        self.assertEqual([call.args[2] for call in remote.call_args_list], ['before', 'before', 'after', 'after'])

    def test_wrong_remote_host_boot_birth_source_or_original_exit_refused(self):
        now, owners, policy, packet = self.fixture()
        for change in ('host', 'bootId', 'startTicks', 'executable', 'exit', 'source'):
            altered = copy.deepcopy(packet); observed = inventory.remote_json(altered['stdout'].encode())
            if change == 'host': observed['kernelHost'] = 'aiharness'
            elif change == 'exit': altered['actualExitCode'] = True
            elif change == 'source': altered['stdin'] = 'OTHER_SOURCE'
            elif change == 'executable': observed['owners']['qwen1']['executable']['sha256'] = '0' * 64
            else: observed['owners']['qwen1'][change] = 'wrong'
            altered['stdout'] = inventory.canonical(observed).decode()
            with self.subTest(change=change), self.assertRaises(inventory.InventoryError):
                self.observe(owners, policy, altered, now)

    def test_distinct_after_original_must_start_after_exact_owned_shutdown(self):
        now, owners, policy, packet = self.fixture()
        with self.assertRaises(inventory.InventoryError): self.observe(owners, policy, packet, now, 'after')
        after = dict(packet, stage='after', anchor={'path': policy['afterAnchor'],
                        'sha256': hashlib.sha256(b'GENUINE_ORIGINAL_FIXTURE').hexdigest()})
        with patch.object(inventory, 'absolute', return_value=Path(policy['afterAnchor'])), \
             patch.object(inventory, 'bounded_read', return_value=b'GENUINE_ORIGINAL_FIXTURE'), \
             patch.object(Path, 'stat', return_value=SimpleNamespace(st_mtime=now - 3)):
            self.assertEqual(self.observe(owners, policy, after, now, 'after'),
                             self.observe(owners, policy, packet, now))
            with self.assertRaises(inventory.InventoryError): self.observe(owners, policy, after, now - 3, 'after')
        with patch.object(inventory, 'identity', return_value={'uid': 1000, 'mode': 0o600, 'nlink': 1}), \
             patch.object(inventory, 'absolute', return_value=Path('/fixture/original')), \
             patch.object(inventory, 'ancestry'):
            with self.assertRaises(inventory.InventoryError): inventory.root_original('/fixture/original')


if __name__ == '__main__':
    unittest.main(verbosity=2)
