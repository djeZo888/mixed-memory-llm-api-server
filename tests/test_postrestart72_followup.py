"""Synthetic private mailbox/count checks; no SSH, inference or lifecycle I/O."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from benchmark import cpu_budget_profiles as profile, fixtures, g1_ladder, runner
from benchmark import postrestart72_followup as followup


class FollowupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.state = Path(self.temp.name); self.private = self.state / 'private'; self.private.mkdir(mode=0o700)
        self.armed = {'scope': profile.POSTRESTART_SCOPE, 'campaign': profile.POSTRESTART_CAMPAIGN,
                      'source_commit': 'a'*40, 'session_id': 'original-owner-session'}
        self.hold_sha = 'b'*64

    def mailbox(self, placement='G1', preset=None):
        preset = preset or ('P-G4K' if placement == 'G1' else 'P-Qnear480K')
        frozen = followup.PRESETS[preset]
        sample = fixtures.build_sample('bench-glm-5.3' if placement == 'G1' else 'bench-qwen3.8-27b',
                                       frozen['records'], frozen['seed'], 'fresh-followup-prefix')
        raw = g1_ladder.body_bytes(sample) if placement == 'G1' else fixtures.serialize_validate(sample)
        (self.private / 'followup.request.json').write_bytes(raw)
        (self.private / 'followup.request.json').chmod(0o600)
        runner.save(self.private / 'followup.fixture.json', sample)
        go = {'decision': 'GO', 'source_commit': self.armed['source_commit'],
            'owner_run_session_id': self.armed['session_id'], 'followup_session_id': 'fresh-followup-session',
            'campaign': profile.POSTRESTART_CAMPAIGN, 'warm_hold_receipt_sha256': self.hold_sha,
            'placement': placement, 'preset': preset,
            'manifest_sha256': fixtures.digest(fixtures.canonical(profile.postrestart_manifest(placement))),
            'request_sha256': fixtures.digest(raw),
            'fixture_sha256': fixtures.digest((self.private / 'followup.fixture.json').read_bytes()),
            'request_id': 'F-reviewed-request', 'policy': copy.deepcopy(followup.POLICY)}
        runner.save(self.state / 'followup-GO.json', go)
        return go, raw

    def read(self, **kwargs):
        return followup.read_candidate(self.state, self.armed, self.hold_sha, **kwargs)

    def counter(self, raw):
        body = json.loads(raw)
        records = body['messages'][0]['content'].count('record=')
        return {'source': 'native_apply_template_tokenize', 'body_sha256': fixtures.digest(raw),
                'configured_context': 480000, 'input_tokens': {108: 3546, 2028: 65008, 12150: 479487}[records],
                'template_sha256': 'c'*64, 'token_ids_sha256': 'd'*64}

    def test_G_and_Q_exact_mailbox_prepare_one_final_count_no_dispatch_or_refit(self):
        for preset, frozen in followup.PRESETS.items():
            placement = frozen['placement']
            go, raw = self.mailbox(placement, preset)
            candidate = self.read(); count = Mock(side_effect=self.counter)
            ticks = iter([5, 7])
            job = followup.prepare_job(candidate, 'owned-' + placement, count,
                                      templates={placement: 'c'*64}, clock=lambda: next(ticks))
            count.assert_called_once_with(raw)
            self.assertEqual(job['raw'], raw)
            self.assertEqual(job['id'], go['request_id'])
            self.assertEqual(job['preparation_seconds'], 2)
            self.assertGreaterEqual(job['count']['input_tokens'], frozen['input_tokens_minimum'])
            self.assertFalse(job['generation'])
            self.assertEqual(job['followup_session_id'], go['followup_session_id'])
            self.assertFalse((self.state / (go['request_id'] + '-result.json')).exists())

    def test_stale_malformed_or_second_GO_rejected_before_count(self):
        go, _ = self.mailbox()
        cases = [lambda v: v.update(decision='RELEASE'), lambda v: v.update(source_commit='f'*40),
            lambda v: v.update(owner_run_session_id='new-unowned-session'),
            lambda v: v.update(followup_session_id=self.armed['session_id']),
            lambda v: v.update(warm_hold_receipt_sha256='e'*64),
            lambda v: v.update(preset='arbitrary-retrieval'), lambda v: v.update(preset='P-Qnear480K'),
            lambda v: v.update(placement='G2'), lambda v: v.update(manifest_sha256='f'*64),
            lambda v: v.update(request_id='../request'), lambda v: v.update(arbitrary_code='forbidden'),
            lambda v: v['policy'].update(request_timeout_seconds=3600)]
        for change in cases:
            bad = copy.deepcopy(go); change(bad); runner.save(self.state / 'followup-GO.json', bad)
            with self.assertRaises(ValueError): self.read()
        runner.save(self.state / 'followup-GO.json', go)
        for options in ({'used_sessions': ['previous-followup']}, {'completed_ids': [go['request_id']]}):
            with self.assertRaises(ValueError): self.read(**options)
        self.assertEqual(self.read()['go'], go)  # Rejection did not mutate owner/control files.

    def test_changed_body_flags_fixture_nonce_and_digest_are_rejected(self):
        for field, value in (('max_tokens', 512), ('temperature', True), ('seed', 9),
                             ('stream', False), ('reasoning_effort', 'none'), ('tools', [])):
            go, _ = self.mailbox()
            body = fixtures.canonical({**fixtures.build_sample('bench-glm-5.3', 108,
                'followup-fixture-seed', 'fresh-followup-prefix')['body'], field: value})
            (self.private / 'followup.request.json').write_bytes(body)
            go['request_sha256'] = fixtures.digest(body); runner.save(self.state / 'followup-GO.json', go)
            with self.subTest(field=field), self.assertRaises(ValueError): self.read()
        go, raw = self.mailbox()
        (self.private / 'followup.request.json').write_bytes(raw + b' ')
        with self.assertRaisesRegex(ValueError, 'payload_digest'): self.read()
        go['request_sha256'] = fixtures.digest(raw + b' '); runner.save(self.state / 'followup-GO.json', go)
        self.assertEqual(self.read()['raw'], raw + b' ')  # Exact reviewed bytes are preserved.
        # Even a fully self-consistent GO/body/fixture cannot introduce an
        # arbitrary retrieval archive outside the three historical presets.
        go, _ = self.mailbox()
        sample = fixtures.build_sample('bench-glm-5.3', 109, 'arbitrary-fixture-seed', 'fresh-arbitrary-prefix')
        raw = g1_ladder.body_bytes(sample)
        (self.private / 'followup.request.json').write_bytes(raw)
        runner.save(self.private / 'followup.fixture.json', sample)
        go.update(request_sha256=fixtures.digest(raw),
                  fixture_sha256=fixtures.digest((self.private / 'followup.fixture.json').read_bytes()))
        runner.save(self.state / 'followup-GO.json', go)
        with self.assertRaisesRegex(ValueError, 'historical_logical_fixture'): self.read()

    def test_private_files_no_symlink_or_mode_drift_and_unique_prefix_or_request(self):
        go, raw = self.mailbox()
        file = self.private / 'followup.request.json'; file.chmod(0o644)
        with self.assertRaisesRegex(ValueError, 'private_regular'): self.read()
        file.chmod(0o600); file.rename(self.private / 'original-body.json')
        file.symlink_to(self.private / 'original-body.json')
        with self.assertRaises(OSError): self.read()
        file.unlink(); file.write_bytes(raw); file.chmod(0o600)
        previous = self.private / 'old-id.request.json'; previous.write_bytes(raw); previous.chmod(0o600)
        with self.assertRaisesRegex(ValueError, 'prefix_already'): self.read()
        previous.unlink()
        runner.save(self.state / (go['request_id'] + '-result.json'), {'status': 'UNAVAILABLE'})
        with self.assertRaisesRegex(ValueError, 'already_used'): self.read()

    def test_native_count_capacity_template_or_candidate_mutation_never_refits(self):
        self.mailbox(); candidate = self.read()
        for key, value in (('input_tokens', 479489), ('template_sha256', 'f'*64), ('configured_context', 262144)):
            counter = Mock(side_effect=lambda raw: {**self.counter(raw), key: value})
            with self.assertRaises(ValueError):
                followup.prepare_job(candidate, 'owned-g', counter, templates={'G1': 'c'*64})
            counter.assert_called_once()
        for section, key, value in (('go', 'source_commit', 'e'*40), ('manifest', 'guest_cpuset', '0-111')):
            bad = copy.deepcopy(candidate); bad[section][key] = value; counter = Mock()
            with self.assertRaises(ValueError): followup.prepare_job(bad, 'owned-g', counter, templates={'G1': 'c'*64})
            counter.assert_not_called()


if __name__ == '__main__':
    unittest.main()
