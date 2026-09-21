"""Focused dual-Q source/arm/package/owner checks; offline only, no key reads."""
from contextlib import ExitStack
from dataclasses import replace
import copy
import os
from pathlib import Path
import stat
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from benchmark import dualq_480k as contract, dualq_run as run, fixtures, profiles, runner
from benchmark.owner import CampaignOwner, OwnerError
from benchmark.lifecycle import digest
from tests.test_benchmark_owner import Fixture
from tests.test_benchmark_lifecycle import snapshot

SOURCES = {'scripts/benchmark/offline-fixture.py': b'# synthetic source closure\n'}


def predecessor():
    return {'schema': 1, **run.OLD, 'containers': [
        {'role': role, 'id': str(n) * 64, 'name': run.OLD['campaign'] + '-' + role.lower() + '-480000',
         'image_id': 'sha256:' + str(n + 2) * 64} for n, role in enumerate(('G1', 'Q1'), 1)],
        'canonical_release': {'control_path': '/private/saved/old/release.json',
                              'entrypoint': 'original reviewed release control only'}}


class ArmTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.task = Path(self.tmp.name) / 'task'; self.task.mkdir(mode=0o700)
        credentials = Path(self.tmp.name) / 'private-credentials'; credentials.mkdir(mode=0o700)
        self.meta = {}
        for path, directory in ((credentials, True), (credentials / 'inference-key', False),
                                (credentials / 'control-key', False)):
            if not directory:
                path.write_bytes(b'not-a-live-key'); path.chmod(0o600)
            self.meta[str(path)] = {'directory': directory, 'regular': not directory,
                'mode': '0o700' if directory else '0o600', 'uid': os.geteuid(), 'symlink': False, 'key_bytes_read': False}
        for name in run.INPUTS[:3]:
            path = self.task / name; path.write_text('Synthetic offline authority only.\n'); path.chmod(0o600)
        runner.save(self.task / 'predecessor-evidence.json', predecessor())
        runner.save(self.task / 'protected-key-metadata.json', self.meta)
        self.patches = ExitStack(); self.addCleanup(self.patches.close)
        self.patches.enter_context(patch.object(run.glmrepair, 'git', side_effect=
            lambda *args: 'a' * 40 if args == ('rev-parse', 'HEAD') else ''))
        self.patches.enter_context(patch.object(runner, 'source_files', return_value=SOURCES))
        self.arm = run.prepare(self.task, 'prep-session')
        self.receipt = run._json(self.task / 'arm-receipt.json')
        released = {'predecessor_evidence_sha256': self.arm['predecessor_evidence_sha256'],
            'status': 'RESTORED', 'original_endstate': 'STOPPED/manual', 'canonical_lease': 'LEASE_FREE',
            'benchmark_owned_resources': 0, 'benchmark_listeners': 0}
        self.release_path = Path(self.tmp.name) / 'release-receipt.json'; runner.save(self.release_path, released)
        self.go = {**self.receipt, 'decision': 'GO', 'vm_writer_handoff': True,
            'run_session_id': 'run-session', 'runtime': copy.deepcopy(contract.POLICY),
            'predecessor_evidence_sha256': self.arm['predecessor_evidence_sha256'],
            'release_receipt': {'path': str(self.release_path), 'sha256': fixtures.digest(self.release_path.read_bytes())},
            'actual_image_auth_receipts': {slot: {'registered_path': '/data/logs/auth/' + slot + '.json',
                'sha256': 'b' * 64} for slot in ('base', 'Q0', 'Q1')}}
        self.go_path = Path(self.tmp.name) / 'GO.json'; runner.save(self.go_path, self.go)

    def chain(self, **kwargs):
        return run.read_chain(self.task, self.go_path, 'run-session', **kwargs)

    def test_prepared_arm_closed_roles_policy_modes_and_private_files(self):
        self.assertEqual(profiles.scope_placements(contract.SCOPE), ('Q0', 'Q1'))
        self.assertEqual(profiles.scope_capacities(contract.SCOPE), (480000,))
        self.assertEqual(profiles.validate_arm_scope(self.arm), contract.SCOPE)
        self.assertEqual(self.arm['trial_plan']['measured_requests'], 2)
        self.assertNotIn('continuation_execution', self.arm)
        self.assertEqual(self.arm['production_acceptance'], 'NOT_GRANTED')
        self.assertEqual(run._json(self.task / 'GO.template.json')['decision'], 'NOT_AUTHORIZED')
        for path in self.task.rglob('*'):
            self.assertEqual(stat.S_IMODE(path.lstat().st_mode), 0o700 if path.is_dir() else 0o600)
        executed, keys = self.chain()
        self.assertEqual(executed['session_id'], 'run-session')
        self.assertEqual(executed['runtime']['request_timeout_seconds'], 7200)
        self.assertNotIn('deadline_epoch', executed['runtime'])
        self.assertEqual(keys.name, 'private-credentials')

    def test_no_source_arm_or_package_tamper_reaches_key_read_or_ssh(self):
        targets = ['arm.json', 'progress.json', 'predecessor-evidence.json', 'production-HANDOFF.md']
        for name in targets:
            with self.subTest(name=name):
                path = self.task / name; saved = path.read_bytes()
                path.write_bytes(saved + b' ')
                with patch.object(run.glmrepair, 'DiagnosticSSHHost') as ssh, patch('runtime.sglang38_file_auth.read_key') as key:
                    with self.assertRaises(ValueError):
                        run.run(self.task, self.go_path, 'run-session')
                    ssh.assert_not_called(); key.assert_not_called()
                path.write_bytes(saved)
        with patch.object(runner, 'source_files', return_value={'changed': b'changed'}):
            with self.assertRaisesRegex(ValueError, 'exact_source_arm'):
                self.chain()

    def test_fresh_session_release_auth_and_no_replay(self):
        with self.assertRaisesRegex(ValueError, 'fresh_run_session'):
            run.read_chain(self.task, self.go_path, 'prep-session')
        for mutation in ('release', 'auth', 'clock'):
            changed = copy.deepcopy(self.go)
            if mutation == 'release': changed['release_receipt']['sha256'] = 'f' * 64
            elif mutation == 'auth': changed['actual_image_auth_receipts'] = 'PENDING'
            else: changed['runtime']['request_timeout_seconds'] = 300
            runner.save(self.go_path, changed)
            with self.assertRaises(ValueError): self.chain()
        runner.save(self.go_path, self.go)
        executed, _ = self.chain(); runner.save(self.task / 'execution-arm.json', executed)
        with self.assertRaisesRegex(ValueError, 'no_rerun'):
            self.chain()
        self.assertEqual(self.chain(restore_only=True)[0], executed)

    def test_private_symlink_mode_and_key_stat_fail_before_network(self):
        path = self.task / 'ROOT-PLAN.md'; saved = path.read_bytes(); path.chmod(0o644)
        with self.assertRaisesRegex(ValueError, 'private_regular'):
            self.chain()
        path.chmod(0o600)
        key = next(Path(path) for path in self.meta if path.endswith('/control-key')); key.chmod(0o644)
        with self.assertRaisesRegex(ValueError, 'key_stat_changed'):
            self.chain()
        key.chmod(0o600)
        outside = Path(self.tmp.name) / 'outside.md'; outside.write_bytes(saved); outside.chmod(0o600)
        path.unlink(); path.symlink_to(outside)
        with self.assertRaisesRegex(ValueError, 'private_regular'):
            self.chain()

    def test_exact_old_keeper_and_no_arm_mutation(self):
        for field, value in (('remote_owner_pid', 9), ('source_commit', 'd' * 40), ('keeper_pid', 1)):
            bad = predecessor(); bad[field] = value
            with self.assertRaises(ValueError): run.validate_predecessor(bad)
        for field, value in (('mode', 'hold'), ('continuation_execution', {}), ('production_acceptance', 'ACCEPTED')):
            bad = copy.deepcopy(self.arm); bad[field] = value
            with self.assertRaises(ValueError): run.validate_arm(bad)


class ClosureAndOwnerTests(unittest.TestCase):
    def test_staging_source_inventory_has_full_production_and_fixture_read_chain(self):
        files = runner.source_files(contract.SCOPE)
        pair, qwen = profiles.candidate_modules()
        self.assertTrue(set(pair.source_identity()) <= set(files))
        self.assertTrue(set(qwen.PROFILE_HASHES) <= set(files))
        self.assertTrue({'scripts/benchmark/dualq_run.py', 'scripts/benchmark/dualq_480k.py',
            'scripts/benchmark/owner.py', 'scripts/bench/run-gpu-split.py',
            'tests/lifecycle/sglang38_fixture/run_pair_pinned_image.py'} <= set(files))
        for slot in ('q0', 'q1'):
            self.assertIn('configs/deployments/qwen38-27b-' + slot + '-480000-yarn4-bf16kv.json', files)
        with patch.object(profiles, 'read_config', side_effect=AssertionError('GLM must not gate Qwen')):
            runner.run_preflight(contract.SCOPE)

    def test_original_stopped_manual_is_preserved_and_running_refused_before_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            before = snapshot(); before['manager'].update(desired='stopped', observed='stopped',
                container_running=False, boot_policy='manual')
            fixture = Fixture(Path(tmp), original=before)
            template = fixture.build()
            owner = CampaignOwner(template.campaign, fixture, template.host, template.budget,
                reviewed_manifest_hashes=[digest(fixture.manifest)], lease_factory=fixture.lease_factory,
                synthetic_offline=True, scope=contract.SCOPE)
            fixture.owner = owner
            def dispatched_create(manifest):
                owner.mark_create_dispatched()
                return fixture.create(manifest)
            owner.host = replace(owner.host, create=dispatched_create)
            owner.begin(); self.assertFalse(owner.production_touched)
            owned = owner.launch(fixture.manifest)
            self.assertTrue(fixture.containers[owned['id']]['running'])
            self.assertTrue(owner.restore()['restored'])
            self.assertEqual(fixture.containers, {})
            self.assertFalse(any(row[0] == 'manager' for row in fixture.events))
            self.assertEqual(fixture.state['manager'], before['manager'])
            fixture.state['manager'].update(desired='running', observed='ready', container_running=True)
            owner = CampaignOwner(template.campaign, fixture, template.host, template.budget,
                reviewed_manifest_hashes=[digest(fixture.manifest)], lease_factory=fixture.lease_factory,
                synthetic_offline=True, scope=contract.SCOPE)
            fixture.owner = owner; fixture.events.clear()
            with self.assertRaises(OwnerError): owner.begin()
            self.assertEqual(owner.phase, 'FAILED_BEFORE_MUTATION')
            self.assertFalse(any(row[0] in {'manager', 'control', 'create'} for row in fixture.events))

    def test_actual_inherited_collector_distinguishes_missing_from_numeric_violation(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp); runner.save(state / 'progress.json', {'completed': {}, 'inflight': {}, 'errors': []})
            host = Mock(); job = runner.Campaign(state, {'scope': contract.SCOPE}, host, 'offline-key')
            cid = 'a' * 64; uuid = 'GPU-offline'
            event = threading.Event()
            job.active[cid] = {'manifest': {'placement': 'Q0', 'gpu_uuids': [uuid]},
                'baseline': {'swap_bytes': 0, 'events': {'oom': 0}}, 'cancel_event': event, 'phase': 'ready'}
            row = {'timestamp_monotonic_s': 1, 'cgroups': {cid: {'swap_bytes': 0, 'events': {'oom': 0}}},
                'gpus': [], 'host': {}, 'concurrent_resource_gate': {'status': 'UNAVAILABLE',
                    'reasons': [], 'latched_violations': {}, 'unavailable_reasons': ['gpu-missing']}}
            host.call.return_value = row; job.collect()
            self.assertFalse(event.is_set()); self.assertEqual(job.safety, {}); self.assertIsNotNone(job.proof_pending)
            row['gpus'] = [{'uuid': uuid, 'free_bytes': 32 * 1024**3}]
            row['host'] = {'available_bytes': 100 * 1024**3}
            row['concurrent_resource_gate'] = {'status': 'PASS', 'charges': {cid: {}}, 'reasons': [], 'latched_violations': {}}
            job.collect(); self.assertIsNone(job.proof_pending); self.assertFalse(event.is_set())
            row['concurrent_resource_gate'].update(status='STOP_RESOURCE_GATE', reasons=['numeric-low'])
            job.collect(); self.assertTrue(event.is_set()); self.assertEqual(job.safety[cid], 'STOP_RESOURCE_GATE')
            row['concurrent_resource_gate'].update(status='PASS', reasons=[])
            job.collect(); self.assertTrue(event.is_set()); self.assertEqual(job.safety[cid], 'STOP_RESOURCE_GATE')


if __name__ == '__main__':
    unittest.main()
