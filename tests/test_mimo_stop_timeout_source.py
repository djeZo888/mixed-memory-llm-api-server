"""Bounded offline replay of H031's actual idle stop + late settlement shape."""
import contextlib
import copy
import importlib.util
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('clean_source_fixture', Path(__file__).with_name('test_mimo_same_boot_source.py'))
f = importlib.util.module_from_spec(spec)
spec.loader.exec_module(f)
o, sha, BOOT = f.o, f.sha, f.BOOT

# Exact sanitized failure records from the retained 2026-09-29 normal stop.
PRIMARY = {'code': 'owner_interrupted', 'cycle_elapsed_s': 4.80748,
           'observed_at': '2026-09-29T09:24:39.606796+00:00',
           'operation': 'cycle_sleep', 'phase': 'RUNNING'}
SETTLEMENT = {'code': 'command_timeout', 'observed_at': '2026-09-29T09:24:47.370273+00:00',
              'operation': 'settlement', 'phase': 'SETTLING'}


class StopTimeoutSourceTests(unittest.TestCase):
    # Reuse setup helpers only; do not inherit/count the clean tests again.
    save = f.SameBootSourceTests.save

    def setUp(self):
        f.SameBootSourceTests.setUp(self)
        self.node_paths = ['/usr/local/lib/llm-server/node-api/scripts/control/' + n
                           for n in ('node.py', 'node_collectors.py')]
        for p in self.node_paths:
            self.old['source_sha256'][p] = sha(b'old-node')
            self.new['source_sha256'][p] = sha(b'new-node')
            self.delta[p] = {'old': sha(b'old-node'), 'new': sha(b'new-node')}
        self.selected['manifest_sha256'] = o.digest(self.old)
        for state in (self.state, self.running):
            state['manifest_sha256'] = o.digest(self.old)
            state['selection'] = copy.deepcopy(self.selected)
        self.guard.update(manifest_sha256=o.digest(self.old), selection=self.selected,
                          observed_at='2026-09-29T09:24:26.000000+00:00')
        for n, value in [('manifest.json', self.old), ('state.json', self.state),
                         ('selection.json', self.selected), ('guard.json', self.guard),
                         ('source-successor-delta.json', self.delta)]:
            self.save(n, value)
        self.delta_sha = sha((self.base / 'source-successor-delta.json').read_bytes())
        f.SameBootSourceTests.prepare(self)
        self.intent_name = o.source_stop_name(self.state)
        self.intent_sha = sha((self.base / self.intent_name).read_bytes())
        self.state.update(status='SETTLED', settlement={'pid_released': True, 'cgroup_empty': True,
                          'gpu_compute_empty': True}, primary_failure=copy.deepcopy(PRIMARY),
                          settlement_failure=copy.deepcopy(SETTLEMENT))
        self.save('state.json', self.state)
        self.native['State'] = {'Running': False, 'Pid': 0, 'Status': 'exited', 'OOMKilled': False}
        self.physical.return_value.update(container_id=self.state['native']['container_id'],
            native_pid_absent=True, cgroup_empty=True, gpu_compute_empty=True, owner_absent=True)
        self.corrected = copy.deepcopy(self.delta)
        self.corrected[str(self.base / 'source/owner.py')]['new'] = sha(b'corrected-owner')
        self.new['source_sha256'][str(self.base / 'source/owner.py')] = sha(b'corrected-owner')
        self.save(o.CORRECTED_DELTA, self.corrected)
        self.save(o.CORRECTED_MANIFEST, self.new)
        self.corrected_sha = sha((self.base / o.CORRECTED_DELTA).read_bytes())
        self.stack.enter_context(patch.object(o, 'protected', side_effect=lambda p:
            b'new-node' if str(p) in self.node_paths else Path(p).read_bytes()))

    def arguments(self):
        return [sha((self.base / 'state.json').read_bytes()), BOOT, o.digest(self.old), self.delta_sha,
                self.intent_sha, self.corrected_sha, o.digest(self.new)]

    def prepare(self):
        return o.prepare_source_stop_timeout(*self.arguments())

    def install(self):
        self.save('source-successor-prior-manifest.json', self.old)
        (self.base / 'source-successor-prior-owner.py').write_bytes(b'old-source')
        self.save('manifest.json', self.new)
        (self.base / 'source/owner.py').write_bytes(b'corrected-owner')

    def reconcile(self):
        return o.reconcile_settled_source(sha((self.base / 'state.json').read_bytes()), BOOT,
            o.digest(self.new), self.corrected_sha, same_boot=True, stop_timeout=True,
            expected_supplement_sha256=sha((self.base / o.source_supplement_name(self.state)).read_bytes()))

    def packet(self):
        self.prepare()
        self.install()
        return self.reconcile()

    def snapshot(self):
        return {p.name: p.read_bytes() for p in self.base.iterdir() if p.is_file()}

    def test_actual_failure_shape_keeps_both_records_original_intent_delta_and_all_bytes(self):
        before = self.snapshot()
        supplement = self.prepare()
        self.assertEqual(supplement['files']['state.json'].encode(), before['state.json'])
        for n, raw in before.items(): self.assertEqual((self.base / n).read_bytes(), raw)
        self.assertEqual((self.base / o.source_supplement_name(self.state)).stat().st_mode & 0o777, 0o400)
        self.install()
        receipt = self.reconcile()
        self.assertEqual(receipt['transition'], o.STOP_TIMEOUT_TRANSITION)
        self.assertEqual(receipt['prior_request_outcome'], o.STOP_TIMEOUT_OUTCOME)
        archived = o.read(self.base / receipt['archive_name'])['files']
        for n in ('state.json', 'proxy-state.json', 'guard.json', self.intent_name, 'source-successor-delta.json'):
            self.assertEqual(archived[n].encode(), before[n])
            self.assertEqual((self.base / n).read_bytes(), before[n])
        self.assertEqual(json.loads(archived['state.json'])['primary_failure'], PRIMARY)
        self.assertEqual(json.loads(archived['state.json'])['settlement_failure'], SETTLEMENT)
        self.assertEqual(o.settled_source_for_start(self.new, receipt['selection'], self.state)[0], receipt)

    def test_unrelated_failure_code_phase_operation_fields_and_state_drift_refuse(self):
        cases = []
        for field in ('primary_failure', 'settlement_failure'):
            for key, value in [('code', 'mandatory_guard_timeout'), ('phase', 'LOADING'),
                               ('operation', 'native_readiness'), ('unknown', True),
                               ('observed_at', '2026-09-29T09:25:00')]:
                changed = copy.deepcopy(self.state); changed[field][key] = value; cases.append(changed)
        for change in ({'status': 'HELD'}, {'request_hold': True}, {'receipt_failure': {}},
                       {'settlement_recheck_failure': {}}, {'selection': {}}, {'native': {}},
                       {'settlement': {}}, {'launch_id': 'b' * 32}, {'manifest_sha256': 'e' * 64}):
            cases.append({**self.state, **change})
        for candidate in cases:
            with self.subTest(change=candidate.keys()):
                self.save('state.json', candidate)
                before = self.snapshot()
                with self.assertRaises((o.OwnerRefusal, FileNotFoundError)): self.prepare()
                self.assertEqual(self.snapshot(), before)
        self.save('state.json', self.state)

    def test_missing_stale_wrong_raw_input_pins_refuse_without_writes(self):
        args = self.arguments()
        for index in range(len(args)):
            changed = list(args); changed[index] = f.f.OLD if index == 1 else 'e' * 64
            before = self.snapshot()
            with self.subTest(pin=index), self.assertRaises(o.OwnerRefusal):
                o.prepare_source_stop_timeout(*changed)
            self.assertEqual(self.snapshot(), before)
        path = self.base / self.intent_name
        path.chmod(0o600); path.write_text('{}')
        with self.assertRaises(o.OwnerRefusal): o.prepare_source_stop_timeout(*args)

    def test_only_new_owner_pin_may_advance_and_node_delta_is_immutable(self):
        for target in ('node_new', 'node_old', 'owner_old', 'owner_unchanged', 'context', 'model', 'runtime', 'selection'):
            delta, proposed = copy.deepcopy(self.corrected), copy.deepcopy(self.new)
            if target.startswith('node_'): delta[self.node_paths[0]][target[5:]] = 'e' * 64
            elif target == 'owner_old': delta[str(self.base / 'source/owner.py')]['old'] = 'e' * 64
            elif target == 'owner_unchanged': delta[str(self.base / 'source/owner.py')] = self.delta[str(self.base / 'source/owner.py')]
            else: proposed[target] = 'drift'
            with self.subTest(target=target), self.assertRaises(o.OwnerRefusal):
                o.timeout_proposal(self.old, json.dumps(self.delta), json.dumps(delta), proposed)
        original = (self.base / 'source-successor-delta.json').read_bytes()
        (self.base / 'source-successor-delta.json').write_bytes(original + b'\n')
        self.delta_sha = sha(original + b'\n')
        with self.assertRaises(o.OwnerRefusal): self.prepare()

    def test_active_ambiguous_or_changed_final_proxy_refuses_supplement(self):
        for change in ({'active_requests': 1}, {'active_requests': None}, {'active_requests': False},
                       {'quarantined': True}, {'quarantined': None}, {'pid_start_ticks': 'other'},
                       {'parent_pid': 1}, {'launch_id': 'b'*32}, {'native': {}}):
            self.save('proxy-state.json', {**self.proxy, **change})
            with self.subTest(change=change), self.assertRaises(o.OwnerRefusal): self.prepare()
        self.save('proxy-state.json', self.proxy)

    def test_positive_unknown_hardware_and_physical_failure_preserve_evidence(self):
        for value in (True, None):
            self.hardware.return_value = {'hardware_latched': value}
            before = self.snapshot()
            with self.assertRaises(o.OwnerRefusal): self.prepare()
            self.assertEqual(self.snapshot(), before)
        self.hardware.return_value = {'hardware_latched': False}
        self.physical.side_effect = o.OwnerRefusal('new_boot_owner_present')
        before = self.snapshot()
        with self.assertRaises(o.OwnerRefusal): self.prepare()
        self.assertEqual(self.snapshot(), before)

    def test_reconcile_requires_explicit_mode_and_unchanged_installed_sources(self):
        self.prepare(); self.install()
        with self.assertRaises(o.OwnerRefusal):
            o.reconcile_settled_source(self.arguments()[0], BOOT, o.digest(self.new), self.delta_sha, same_boot=True)
        (self.base / 'source/owner.py').write_bytes(b'other')
        with self.assertRaises(o.OwnerRefusal): self.reconcile()
        self.assertEqual(o.read(self.base / 'selection.json'), self.selected)

    def test_supplement_receipt_archive_and_live_input_tampering_cannot_admit(self):
        receipt = self.packet()
        receipt_name = o.settled_source_names(BOOT, o.digest(self.new))[1]
        targets = [self.intent_name, o.source_supplement_name(self.state), receipt_name, receipt['archive_name'],
                   'state.json', 'proxy-state.json', 'guard.json', 'source-successor-delta.json',
                   o.CORRECTED_DELTA, o.CORRECTED_MANIFEST]
        for name in targets:
            p = self.base / name; raw = p.read_bytes(); p.chmod(0o600); p.write_bytes(raw + b'\n')
            try:
                # Receipt itself is semantically parsed; mutate its binding explicitly.
                if name == receipt_name: self.save(name, {**receipt, 'supplement_sha256': 'e'*64})
                with self.subTest(name=name), self.assertRaises(o.OwnerRefusal):
                    o.settled_source_for_start(self.new, receipt['selection'], self.state)
            finally: p.write_bytes(raw)
        with self.assertRaises((o.OwnerRefusal, FileExistsError)): self.reconcile()

    def test_failed_preflight_preserves_full_chain_then_success_consumes_once(self):
        # Execute the existing substantive supervise test body against this timeout
        # packet. It checks failed hardware preflight, strict evidence=None,
        # unchanged predecessor, one rename, one consumption and replay refusal.
        self.prepare()
        self.install()
        self.prepare = lambda: None
        self.finish_stop = lambda: None
        with patch.object(o, 'timeout_physical', side_effect=lambda *a, **kw: self.physical.return_value):
            f.SameBootSourceTests.test_start_preflight_failure_preserves_predecessor_then_consumes_and_renames_once(self)

    def test_exact_private_capture_chain_when_explicitly_supplied(self):
        evidence = os.environ.get('H031_ACTUAL_EVIDENCE_DIR')
        if not evidence:
            self.skipTest('exact private captures must be supplied outside Git')
        captured = Path(evidence)
        manifest_raw = (captured / 'manifest.json').read_bytes()
        old = json.loads(manifest_raw)
        actual_base = Path('/data/services/mimo-h016-20260927')
        state = json.loads((captured / 'state.json').read_bytes())
        boot = state['boot_id']
        intent_name = o.source_stop_name(state)
        self.assertEqual(sha((captured / intent_name).read_bytes()),
                         '9cabae3e1335bda0028497638e5e968623e0870ef7cc339bd8d9a576243d8eee')
        self.assertEqual(sha((captured / 'source-successor-delta.json').read_bytes()),
                         'cd9b4a0fbb22e9d97f6ab826492282f6560402685c73b7e1023d94a6a7914e59')
        original_raw = (captured / 'source-successor-delta.json').read_bytes()
        original = json.loads(original_raw)
        owner_path = str(actual_base / 'source/owner.py')
        corrected_raw = original_raw.replace(original[owner_path]['new'].encode(), sha(b'corrected-owner').encode())
        corrected = json.loads(corrected_raw)
        proposed = copy.deepcopy(old)
        for path, pins in corrected.items(): proposed['source_sha256'][path] = pins['new']
        raw_files = {n: (captured / n).read_bytes() for n in ('state.json', 'proxy-state.json',
                     'guard.json', 'selection.json', 'manifest.json', 'source-successor-delta.json', intent_name)}
        raw_files[o.CORRECTED_DELTA] = corrected_raw
        raw_files[o.CORRECTED_MANIFEST] = json.dumps(proposed).encode()
        raw_files['source/owner.py'] = (captured / 'source/owner.py').read_bytes()
        for name, raw in raw_files.items(): (self.base / name).write_bytes(raw)
        actual_state_sha = sha(raw_files['state.json'])
        original_bytes = {n: raw for n, raw in raw_files.items()}
        node_bytes = {str(n): (captured.parent / 'W2-SOURCE01/reviewed-source' / Path(n).name).read_bytes()
                      for n in self.node_paths}
        real_exists = Path.exists
        def exists(path):
            if path.is_relative_to(actual_base): return real_exists(self.base / path.relative_to(actual_base))
            return real_exists(path)
        def protected(path):
            path = Path(path)
            if str(path) in node_bytes: return node_bytes[str(path)]
            return (self.base / path.relative_to(actual_base)).read_bytes()
        with patch.object(o, 'BASE', actual_base), patch.object(o, 'BOOT', f.SimpleNamespace(read_text=lambda: boot)), \
             patch.object(o, 'protected', side_effect=protected), patch.object(Path, 'exists', exists):
            self.physical.return_value = {'old_boot_id': boot, 'current_boot_id': boot,
                'physical_release': 'NORMAL_OWNER_STOP', 'prior_request_outcome': 'IDLE_INTENTIONAL_STOP',
                'container_id': state['native']['container_id'], 'native_pid_absent': True,
                'cgroup_empty': True, 'gpu_compute_empty': True, 'owner_absent': True}
            args = [actual_state_sha, boot, o.digest(old), sha(original_raw), sha(raw_files[intent_name]),
                    sha(corrected_raw), o.digest(proposed)]
            supplement = o.prepare_source_stop_timeout(*args)
            for n, raw in original_bytes.items(): self.assertEqual((self.base / n).read_bytes(), raw)
            self.assertEqual(state['primary_failure'], PRIMARY)
            self.assertEqual(state['settlement_failure'], SETTLEMENT)
            (self.base / 'source-successor-prior-owner.py').write_bytes(raw_files['source/owner.py'])
            (self.base / 'source-successor-prior-manifest.json').write_bytes(manifest_raw)
            (self.base / 'manifest.json').write_bytes(raw_files[o.CORRECTED_MANIFEST])
            (self.base / 'source/owner.py').write_bytes(b'corrected-owner')
            receipt = o.reconcile_settled_source(actual_state_sha, boot, o.digest(proposed), sha(corrected_raw),
                same_boot=True, stop_timeout=True,
                expected_supplement_sha256=sha((self.base / o.source_supplement_name(state)).read_bytes()))
            self.assertEqual(o.settled_source_for_start(proposed, receipt['selection'], state)[0], receipt)
            for n in ('state.json', 'proxy-state.json', 'guard.json', intent_name, 'source-successor-delta.json'):
                self.assertEqual((self.base / n).read_bytes(), original_bytes[n])
            self.assertEqual(supplement['intent_sha256'], args[4])

    def test_timeout_disposition_rejects_oom_unknown_and_native_reappearance(self):
        for change in ({'OOMKilled': True}, {'OOMKilled': None}, {'Running': True},
                       {'Pid': 999}, {'Status': 'running'}):
            prior = self.native['State']
            self.native['State'] = {**prior, **change}
            try:
                with self.subTest(change=change), self.assertRaises(o.OwnerRefusal): self.prepare()
            finally:
                self.native['State'] = prior

    def test_duplicate_preparation_cannot_renew_or_rebind_supplement(self):
        self.prepare()
        before = self.snapshot()
        with self.assertRaises(FileExistsError): self.prepare()
        self.assertEqual(self.snapshot(), before)


if __name__ == '__main__': unittest.main()
