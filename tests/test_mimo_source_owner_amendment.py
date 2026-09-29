"""Offline H032 amendment of the retained, already reconciled H031 timeout chain."""
import contextlib
import copy
import importlib.util
import json
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

spec = importlib.util.spec_from_file_location('timeout_amendment_fixture',
    Path(__file__).with_name('test_mimo_stop_timeout_source.py'))
f = importlib.util.module_from_spec(spec)
spec.loader.exec_module(f)
o, sha, BOOT = f.o, f.sha, f.BOOT


class SourceOwnerAmendmentTests(unittest.TestCase):
    save = f.StopTimeoutSourceTests.save
    snapshot = f.StopTimeoutSourceTests.snapshot

    def setUp(self):
        f.StopTimeoutSourceTests.setUp(self)
        o.prepare_source_stop_timeout(*f.StopTimeoutSourceTests.arguments(self))
        f.StopTimeoutSourceTests.install(self)
        self.receipt = f.StopTimeoutSourceTests.reconcile(self)
        self.current = copy.deepcopy(self.new)
        self.current_selection = self.receipt['selection']
        self.successor = copy.deepcopy(self.current)
        self.source_raw = Path(o.__file__).read_bytes()
        self.successor['source_sha256'][str(self.base / 'source/owner.py')] = sha(self.source_raw)
        self.proposal_path, self.delta_path = self.base / 'proposal.json', self.base / 'amendment-delta.json'
        self.proposal_path.write_text(json.dumps(self.successor))
        self.delta_path.write_text(json.dumps({str(self.base / 'source/owner.py'): {
            'old': self.current['source_sha256'][str(self.base / 'source/owner.py')],
            'new': sha(self.source_raw)}}))

    def arguments(self):
        return [sha((self.base / 'state.json').read_bytes()), BOOT, o.digest(self.current),
                sha((self.base / o.settled_source_names(BOOT, o.digest(self.current))[1]).read_bytes()),
                self.proposal_path, o.digest(self.successor), self.delta_path, sha(self.delta_path.read_bytes())]

    def prepare(self):
        return o.prepare_source_owner_amendment(*self.arguments())

    def install(self):
        (self.base / 'manifest.json').write_bytes(self.proposal_path.read_bytes())
        (self.base / 'source/owner.py').write_bytes(self.source_raw)

    def activate(self):
        return o.activate_source_owner_amendment(sha((self.base / 'state.json').read_bytes()), BOOT,
            o.digest(self.successor), sha((self.base / o.source_owner_amendment_name(self.state)).read_bytes()))

    def packet(self):
        self.prepare(); self.install()
        return self.activate()

    def test_prepare_keeps_all_installed_and_historical_bytes_and_no_selection_write(self):
        before, owner = self.snapshot(), (self.base / 'source/owner.py').read_bytes()
        amendment = self.prepare()
        self.assertEqual(amendment['receipt_sha256'], self.arguments()[3])
        self.assertEqual(amendment['installed_owner_raw'].encode(), owner)
        for n, raw in before.items(): self.assertEqual((self.base / n).read_bytes(), raw)
        self.assertEqual((self.base / 'source/owner.py').read_bytes(), owner)
        path = self.base / o.source_owner_amendment_name(self.state)
        self.assertEqual(path.stat().st_mode & 0o777, 0o400)
        with self.assertRaises(o.OwnerRefusal):
            o.settled_source_for_start(self.current, self.current_selection, self.state)
        self.assertFalse((self.base / self.receipt['consumed_name']).exists())

    def test_valid_activation_keeps_generation_failures_and_original_consumed_name(self):
        before = self.snapshot()
        receipt = self.packet()
        self.assertEqual(receipt['consumed_name'], self.receipt['consumed_name'])
        self.assertEqual(receipt['selection'], {**self.current_selection, 'manifest_sha256': o.digest(self.successor)})
        self.assertEqual(o.settled_source_for_start(self.successor, receipt['selection'], self.state), (receipt, self.old))
        for n, raw in before.items():
            if n not in ('manifest.json', 'selection.json'):
                self.assertEqual((self.base / n).read_bytes(), raw)
        self.assertEqual(self.state['primary_failure'], f.PRIMARY)
        self.assertEqual(self.state['settlement_failure'], f.SETTLEMENT)
        self.assertFalse((self.base / receipt['consumed_name']).exists())
        with self.assertRaises(o.OwnerRefusal): self.activate()

    def test_failed_preflight_preserves_every_record_then_consumes_original_once(self):
        receipt = self.packet()
        before = self.snapshot()
        self.supervise_attempts(receipt, self.successor, self.state)
        for n, raw in before.items():
            if n != 'state.json': self.assertEqual((self.base / n).read_bytes(), raw)
        self.assertTrue((self.base / self.receipt['consumed_name']).exists())
        self.assertFalse((self.base / o.settled_source_names(BOOT, o.digest(self.successor))[2]).exists())

    def supervise_attempts(self, receipt, manifest, previous):
        class EndFixture(RuntimeError): pass
        old_id, new_id = previous['native']['container_id'], 'd' * 64
        old_c = {'Id': old_id, 'State': {'Running': False, 'Pid': 0, 'Status': 'exited', 'OOMKilled': False}}
        new_c = {'Id': new_id, 'State': {'Running': True, 'Pid': 44}}
        before = self.snapshot()
        def run(argv, *args):
            if argv[:2] == ['systemctl', 'show']: return 'MainPID=0\nActiveState=inactive\n'
            if argv[:2] == ['docker', 'ps']: return old_id
            if argv == ['fixture-create']: return new_id
            return ''
        with contextlib.ExitStack() as stack:
            values = dict(unit_identity=Mock(return_value={'pid': os.getpid(), 'invocation_id': 'new'}),
                run=Mock(side_effect=run), memory=Mock(return_value={'MemAvailable': 10**16, 'MemTotal': 10**16}),
                temperature_limit=Mock(return_value=85), sample_guard=Mock(return_value={'hardware_validation': {}}),
                memory_policy=Mock(), latch=Mock(side_effect=[o.OwnerRefusal('owned_gpu_latch_unproven'),
                    {'hardware_latched': False}, {'hardware_latched': False}]),
                inspect=Mock(side_effect=lambda n: old_c if n == old_id else new_c),
                create_argv=Mock(return_value=['fixture-create']), native_identity=Mock(return_value={'container_id': new_id, 'pid': 44}),
                cgpath=Mock(return_value=Path('/fixture')), read_key=Mock(return_value=b'fixture'),
                timeout_physical=Mock(return_value=self.physical.return_value),
                native_ready=Mock(side_effect=EndFixture('fixture complete')), record_failure=Mock(), settle_state=Mock())
            for name, value in values.items(): stack.enter_context(patch.object(o, name, value))
            with self.assertRaisesRegex(o.OwnerRefusal, 'owned_gpu_latch_unproven'): o.supervise()
            self.assertEqual(self.snapshot(), before)
            self.assertIsNone(values['latch'].call_args.kwargs['evidence'])
            self.assertFalse((self.base / receipt['consumed_name']).exists())
            self.assertFalse(any(c.args[0][0] == 'docker' and c.args[0][1] in ('rename', 'rm', 'start')
                for c in values['run'].call_args_list))
            with self.assertRaises(EndFixture): o.supervise()
            successor = o.read(o.BASE / 'state.json')
            self.assertEqual(o.read(o.BASE / receipt['consumed_name'])['successor_launch_id'], successor['launch_id'])
            self.assertEqual(o.read(o.BASE / receipt['consumed_name'])['recovery_sha256'], o.digest(receipt))
            self.assertEqual(sum(c.args[0] == ['docker', 'rename', old_id, receipt['preserved_container_name']]
                for c in values['run'].call_args_list), 1)
            self.assertFalse(any(c.args[0][:2] == ['docker', 'rm'] for c in values['run'].call_args_list))
            values['settle_state'].assert_called_once()
            with self.assertRaisesRegex(o.OwnerRefusal, 'new_boot_recovery_consumed'):
                o.settled_source_for_start(manifest, receipt['selection'], previous)

    def test_missing_stale_and_forged_pins_fail_before_any_write(self):
        args = self.arguments()
        for i in (0, 1, 2, 3, 5, 7):
            changed = list(args); changed[i] = f.f.f.OLD if i == 1 else 'e' * 64
            before = self.snapshot()
            with self.subTest(pin=i), self.assertRaises(o.OwnerRefusal):
                o.prepare_source_owner_amendment(*changed)
            self.assertEqual(self.snapshot(), before)
        with patch.object(o, '__file__', str(self.base / 'source/owner.py')):
            with self.assertRaises(o.OwnerRefusal): self.prepare()

    def test_duplicate_preparation_cannot_rebind_manifest_or_renew_evidence(self):
        self.prepare(); before = self.snapshot()
        with self.assertRaises(FileExistsError): self.prepare()
        self.assertEqual(self.snapshot(), before)
        (self.base / self.receipt['consumed_name']).write_text('{}')
        with self.assertRaisesRegex(o.OwnerRefusal, 'new_boot_recovery_consumed'): self.prepare()

    def test_only_owner_changes_no_node_model_runtime_profile_or_selection_drift(self):
        for key in ('context', 'model', 'runtime_revision', 'memory', 'profile', 'native_argv'):
            proposed = {**self.successor, key: 'drift'}
            with self.subTest(key=key), self.assertRaises(o.OwnerRefusal):
                o.owner_amendment_delta(self.current, proposed, self.delta_path.read_bytes())
        proposed = copy.deepcopy(self.successor)
        proposed['source_sha256'][self.node_paths[0]] = 'e' * 64
        with self.assertRaises(o.OwnerRefusal):
            o.owner_amendment_delta(self.current, proposed, self.delta_path.read_bytes())
        self.save('selection.json', {**self.current_selection, 'generation': 13})
        with self.assertRaises(o.OwnerRefusal): self.prepare()

    def test_unrelated_failure_hold_native_identity_and_proxy_ambiguity_refuse(self):
        for name, original, changes in (
            ('state.json', self.state, [{'status': 'HELD'}, {'request_hold': True}, {'native': {}},
             {'primary_failure': {'code': 'mandatory_guard_timeout'}}, {'receipt_failure': {}},
             {'settlement_failure': {'code': 'other'}}, {'launch_id': 'e' * 32}]),
            ('proxy-state.json', self.proxy, [{'active_requests': 1}, {'active_requests': None},
             {'active_requests': False}, {'quarantined': True}, {'quarantined': None}, {'native': {}}])):
            for change in changes:
                self.save(name, {**original, **change}); before = self.snapshot()
                with self.subTest(name=name, change=change), self.assertRaises((o.OwnerRefusal, FileNotFoundError)):
                    self.prepare()
                self.assertEqual(self.snapshot(), before)
            self.save(name, original)

    def test_positive_unknown_hardware_and_absence_failures_at_prepare_and_activate(self):
        for value in (True, None):
            self.hardware.return_value = {'hardware_latched': value}; before = self.snapshot()
            with self.assertRaises(o.OwnerRefusal): self.prepare()
            self.assertEqual(self.snapshot(), before)
        self.hardware.return_value = {'hardware_latched': False}
        with patch.object(o, 'timeout_physical', side_effect=o.OwnerRefusal('new_boot_owner_present')):
            before = self.snapshot()
            with self.assertRaises(o.OwnerRefusal): self.prepare()
            self.assertEqual(self.snapshot(), before)
        self.prepare(); self.install(); before = self.snapshot()
        for value in (True, None):
            self.hardware.return_value = {'hardware_latched': value}
            with self.assertRaises(o.OwnerRefusal): self.activate()
            self.assertEqual(self.snapshot(), before)
        self.hardware.return_value = {'hardware_latched': False}
        with patch.object(o, 'timeout_physical', side_effect=o.OwnerRefusal('new_boot_owner_present')):
            with self.assertRaises(o.OwnerRefusal): self.activate()
            self.assertEqual(self.snapshot(), before)

    def test_original_and_new_evidence_tamper_source_change_and_consumed_reuse_refuse(self):
        receipt = self.packet()
        names = list(o.read(self.base / o.source_owner_amendment_name(self.state))['frozen_sha256'])
        names += [o.source_owner_amendment_name(self.state), 'manifest.json', 'source/owner.py']
        for n in names:
            p = self.base / n; raw = p.read_bytes(); p.chmod(0o600)
            if n == o.source_owner_amendment_name(self.state):
                self.save(n, {**json.loads(raw), 'receipt_sha256': 'e' * 64})
            else: p.write_bytes(raw + b'\n')
            try:
                with self.subTest(name=n), self.assertRaises(o.OwnerRefusal):
                    o.settled_source_for_start(self.successor, receipt['selection'], self.state)
            finally: p.write_bytes(raw)
        (self.base / self.receipt['consumed_name']).write_text('{}')
        with self.assertRaisesRegex(o.OwnerRefusal, 'new_boot_recovery_consumed'):
            o.settled_source_for_start(self.successor, receipt['selection'], self.state)

    def test_activation_requires_exact_amendment_hash_and_original_selection_bytes(self):
        self.prepare(); self.install(); before = self.snapshot()
        with self.assertRaises(o.OwnerRefusal):
            o.activate_source_owner_amendment(self.arguments()[0], BOOT, o.digest(self.successor), 'e' * 64)
        self.assertEqual(self.snapshot(), before)
        self.save('selection.json', {**self.current_selection, 'generation': 13})
        with self.assertRaises(o.OwnerRefusal): self.activate()
        self.assertFalse((self.base / self.receipt['consumed_name']).exists())

    def test_live_standalone_prior_owner_and_manifest_must_equal_archive_before_freezing(self):
        for n in ('source-successor-prior-owner.py', 'source-successor-prior-manifest.json'):
            path = self.base / n; raw = path.read_bytes(); path.write_bytes(raw + b'\n')
            try:
                before = self.snapshot()
                with self.subTest(name=n), self.assertRaises(o.OwnerRefusal): self.prepare()
                self.assertEqual(self.snapshot(), before)
            finally: path.write_bytes(raw)

    def test_prep_pin_mismatch_refuses_before_import_or_any_native_call(self):
        # setup is mocked in fixture; call the saved module function from its source.
        spec = importlib.util.spec_from_file_location('prep_pin_only', o.__file__)
        owner = importlib.util.module_from_spec(spec); spec.loader.exec_module(owner)
        with patch.object(owner, 'protected', return_value=b'wrong-prep'), \
             patch.object(owner.importlib.util, 'spec_from_file_location') as load:
            with self.assertRaisesRegex(owner.OwnerRefusal, 'guard_adapter_changed'): owner.setup()
            load.assert_not_called()

    def test_exact_current_h031_post_reconciliation_chain(self):
        supplied = os.environ.get('H032_ACTUAL_EVIDENCE_DIR')
        if not supplied: self.skipTest('supply private W1 current packet outside Git')
        captured = Path(supplied)
        actual_base = Path('/data/services/mimo-h016-20260927')
        current_raw = (captured / 'manifest.json').read_bytes()
        current, state = json.loads(current_raw), json.loads((captured / 'state.json').read_bytes())
        boot = state['boot_id']
        archive_name, receipt_name, consumed = o.settled_source_names(boot, o.digest(current))
        self.assertEqual(sha((captured / receipt_name).read_bytes()),
            'de52387f3f4505b3529b16606e1a4d11628cf4aeb51bb0cae640965a7d67dcb5')
        self.assertEqual(sha((captured / archive_name).read_bytes()),
            'a2d1b5c58611cd9d98be68d4be3279548f6a7d53bbe899b168da2660ab328a47')
        archive = json.loads((captured / archive_name).read_bytes())
        # W1 supplied current raw paths except prior-owner, whose exact bytes are
        # retained inside the immutable archive. Fixture-only reconstruction; the
        # production prepare command compares the LIVE standalone file to archive.
        raw_files = {n: (archive['files'][n].encode() if n == 'source-successor-prior-owner.py'
                        else (captured / n).read_bytes()) for n in set(archive['files']) |
                     {archive_name, receipt_name, 'manifest.json', 'source/owner.py'}}
        for name, raw in raw_files.items(): (self.base / name).write_bytes(raw)
        before = dict(raw_files)
        proposed = copy.deepcopy(current)
        owner_path = str(actual_base / 'source/owner.py')
        proposed['source_sha256'][owner_path] = sha(self.source_raw)
        self.proposal_path.write_text(json.dumps(proposed))
        self.delta_path.write_text(json.dumps({owner_path: {
            'old': current['source_sha256'][owner_path], 'new': sha(self.source_raw)}}))
        real_exists = Path.exists
        def exists(p):
            return real_exists(self.base / p.relative_to(actual_base)) if p.is_relative_to(actual_base) else real_exists(p)
        repo = Path(o.__file__).resolve().parents[3]
        def protected(p):
            p = Path(p)
            if p.is_relative_to(actual_base): return (self.base / p.relative_to(actual_base)).read_bytes()
            if str(p) in self.node_paths: return (repo / 'scripts/control' / p.name).read_bytes()
            return p.read_bytes()
        with patch.object(o, 'BASE', actual_base), patch.object(o, 'BOOT', SimpleNamespace(read_text=lambda: boot)), \
             patch.object(o, 'protected', side_effect=protected), patch.object(Path, 'exists', exists):
            self.physical.return_value = {'old_boot_id': boot, 'current_boot_id': boot,
                'container_id': state['native']['container_id'], 'native_pid_absent': True,
                'cgroup_empty': True, 'gpu_compute_empty': True, 'owner_absent': True}
            self.native['State'] = {'Running': False, 'Pid': 0, 'Status': 'exited', 'OOMKilled': False}
            args = [sha(raw_files['state.json']), boot, o.digest(current), sha(raw_files[receipt_name]),
                self.proposal_path, o.digest(proposed), self.delta_path, sha(self.delta_path.read_bytes())]
            o.prepare_source_owner_amendment(*args)
            for n, raw in before.items(): self.assertEqual((self.base / n).read_bytes(), raw)
            amendment_sha = sha((self.base / o.source_owner_amendment_name(state)).read_bytes())
            (self.base / 'manifest.json').write_bytes(self.proposal_path.read_bytes())
            (self.base / 'source/owner.py').write_bytes(self.source_raw)
            receipt = o.activate_source_owner_amendment(args[0], boot, o.digest(proposed), amendment_sha)
            self.assertEqual(o.settled_source_for_start(proposed, receipt['selection'], state)[0], receipt)
            self.assertEqual(receipt['consumed_name'], consumed)
            self.assertEqual(receipt['selection']['generation'], 12)
            for n, raw in before.items():
                if n not in ('manifest.json', 'selection.json', 'source/owner.py'):
                    self.assertEqual((self.base / n).read_bytes(), raw)
            self.assertEqual(state['primary_failure'], f.PRIMARY)
            self.assertEqual(state['settlement_failure'], f.SETTLEMENT)
            self.assertFalse((self.base / consumed).exists())
            self.supervise_attempts(receipt, proposed, state)


if __name__ == '__main__': unittest.main()
