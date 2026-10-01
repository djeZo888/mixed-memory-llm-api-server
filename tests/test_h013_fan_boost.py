"""Offline safety contract: no NVML library, device, protected path or service contact."""
import importlib.util
from pathlib import Path
import stat
from types import SimpleNamespace
import unittest
from unittest.mock import patch, Mock

SOURCE = Path(__file__).resolve().parents[1] / 'scripts/thermal/fan_boost.py'
spec = importlib.util.spec_from_file_location('h013_fan_boost_tested', SOURCE)
m = importlib.util.module_from_spec(spec)
with patch('ctypes.CDLL') as inert:
    spec.loader.exec_module(m)
    assert not inert.called, 'import must never load NVML'
U = m.INTEGRATED[0]


class Clock:
    now = 0.0
    def __call__(self): return self.now


class API:
    def __init__(self, count=3):
        self.n = count
        self.temp = 70
        self.policies = {i: 0 for i in range(count)}
        self.targets = {i: 30 for i in range(count)}
        self.calls = []
        self.fail_set = set()
        self.bad_readback = set()
        self.temp_error = False
        self.default_error = False
    def bind(self, uuid): self.calls.append(('bind', uuid))
    def count(self): return self.n
    def temperature(self):
        if self.temp_error: raise m.SafetyError('temperature-error')
        return self.temp
    def policy(self, fan): return self.policies[fan]
    def target(self, fan):
        if fan in self.bad_readback and self.policies[fan] == 1: return 99
        return self.targets[fan]
    def boost(self, fan):
        self.calls.append(('boost', fan))
        if fan in self.fail_set: raise m.SafetyError('set-error')
        self.policies[fan], self.targets[fan] = 1, 100
    def default(self, fan):
        self.calls.append(('default', fan))
        if self.default_error: raise m.SafetyError('default-error')
        self.policies[fan] = 0


class Store:
    def __init__(self, owned=False):
        self.owned = dict.fromkeys(m.INTEGRATED, owned)
        self.saves = []
        self.fail = False
    def load(self): return self.owned.copy()
    def save(self, owned):
        if self.fail: raise m.SafetyError('state-write-failed')
        self.saves.append(owned.copy())
        self.owned = owned.copy()


class Jobs:
    def __init__(self, clock, store):
        self.clock, self.store = clock, store
        self.apis = {u: API() for u in m.INTEGRATED}
        self.actions = []
        self.stale = False
    def batch(self, actions, owned):
        result = {}
        for uuid, action in actions.items():
            self.actions.append((uuid, action))
            if action != 'inspect':
                assert self.store.owned[uuid], 'setter preceded durable intent'
            try:
                result[uuid] = m.device_job(uuid, action, owned[uuid],
                    api_factory=lambda: self.apis[uuid], clock=self.clock)
                if action == 'inspect' and self.stale:
                    result[uuid]['sampled'] -= m.MAX_GAP + 1
            except Exception as exc:
                result[uuid] = {'ok': False, 'errors': [str(exc)]}
        return result


class SafetyTests(unittest.TestCase):
    def setup_controller(self, owned=False, readonly=False, **kwargs):
        self.clock, self.store = Clock(), Store(owned)
        self.jobs = Jobs(self.clock, self.store)
        self.controller = m.Controller(self.store, self.jobs, readonly=readonly,
                                       clock=self.clock, **kwargs)
        return self.controller
    def at(self, second, temp=65, **kwargs):
        self.clock.now = float(second)
        for api in self.jobs.apis.values(): api.temp = temp
        return self.controller.cycle(**kwargs)
    def defaults(self): return [x for x in self.jobs.actions if x[1] == 'default']
    def test_exact_hot_threshold_and_every_enumerated_fan(self):
        self.setup_controller()
        self.at(0, 69)
        self.assertFalse(self.store.saves)
        self.assertEqual(len(m.INTEGRATED),4)
        self.assertNotIn(m.EXTERNAL,self.jobs.apis)
        for count, api in enumerate(self.jobs.apis.values(),1):
            api.n=count;api.policies=dict.fromkeys(range(count),0);api.targets=dict.fromkeys(range(count),30)
        self.at(2, 70)
        for api in self.jobs.apis.values():
            self.assertEqual([x[1] for x in api.calls if x[0]=='boost'],list(range(api.n)))
            self.assertEqual(list(api.targets.values()),[100]*api.n)
        self.assertTrue(all(self.store.owned.values()))
    def test_above_threshold_all_four_integrated_uuids_remain100(self):
        self.setup_controller();self.at(0,90)
        self.assertEqual(set(self.jobs.apis),set(m.KNOWN)-{m.EXTERNAL})
        for api in self.jobs.apis.values():self.assertEqual(list(api.targets.values()),[100]*api.n)
    def test_exact_cool_threshold_and_30_seconds(self):
        self.setup_controller()
        self.at(0, 70)
        for t in range(2, 32, 2): self.at(t, 65)
        self.assertFalse(self.defaults())
        self.at(32, 65)
        self.assertEqual(len(self.defaults()), len(m.INTEGRATED))
        self.assertFalse(any(self.store.owned.values()))
    def test_cooldown_resets_on_warm_gap_error_and_stale(self):
        for cause in ('warm', 'gap', 'error', 'stale'):
            with self.subTest(cause=cause):
                self.setup_controller(); self.at(0, 70)
                for t in range(2, 24, 2): self.at(t)
                if cause == 'warm': self.at(24, 66)
                elif cause == 'gap': self.at(32)
                elif cause == 'error':
                    for a in self.jobs.apis.values(): a.temp_error = True
                    self.at(24)
                    for a in self.jobs.apis.values(): a.temp_error = False
                else:
                    self.jobs.stale = True; self.at(24); self.jobs.stale = False
                start = 32 if cause == 'gap' else 26
                for t in range(start, start + 30, 2): self.at(t)
                self.assertFalse(self.defaults())
                self.at(start + 30)
                self.assertEqual(len(self.defaults()), len(m.INTEGRATED))
    def test_restart_owned_requires_new_continuous_cooldown(self):
        self.setup_controller(owned=True)
        self.at(0)
        self.assertTrue(all(a == 'boost' for _, a in self.jobs.actions if a != 'inspect'))
        for t in range(2, 32, 2): self.at(t)
        self.assertFalse(self.defaults())
        self.at(32)
        self.assertEqual(len(self.defaults()), len(m.INTEGRATED))
    def test_failed_setter_keeps_owner_and_other_devices_protected(self):
        self.setup_controller()
        self.jobs.apis[U].fail_set = {1}
        status = self.at(0, 70)
        self.assertEqual(status[U]['status'], 'degraded')
        self.assertTrue(self.store.owned[U])
        self.assertIn(('boost', 2), self.jobs.apis[U].calls)
        for u in m.INTEGRATED[1:]: self.assertEqual(status[u]['status'], 'boosted-intended-100')
    def test_failed_setter_recovers_then_full_cooldown_releases(self):
        self.setup_controller()
        self.jobs.apis[U].fail_set = {1}
        self.at(0, 70)
        for t in range(2, 24, 2): self.at(t)
        self.jobs.apis[U].fail_set.clear()
        for t in range(24, 54, 2): self.at(t)
        self.assertNotIn((U, 'default'), self.defaults())
        self.at(54)
        self.assertIn((U, 'default'), self.defaults())
        self.assertFalse(self.store.owned[U])
    def test_unowned_hot_with_auto_policy_and_target_error_attempts_boost(self):
        self.setup_controller()
        api = self.jobs.apis[U]
        target = api.target
        def unavailable_before_manual(fan):
            if api.policies[fan] == 0: raise m.SafetyError('target-read-error')
            return target(fan)
        api.target = unavailable_before_manual
        self.at(0, 70)
        self.assertTrue(self.store.owned[U])
        self.assertEqual([fan for action, fan in api.calls if action == 'boost'], [0,1,2])
    def test_missing_passive_device_isolated_external_explicit(self):
        self.setup_controller()
        self.jobs.apis[U].n = 0
        status = self.at(0, 70)
        self.assertEqual(status[U]['status'], 'degraded')
        self.assertEqual(status[m.EXTERNAL]['status'], 'external-control-needed')
        self.assertNotIn(m.EXTERNAL, self.jobs.apis)
        self.assertTrue(all(status[u]['status'] == 'boosted-intended-100' for u in m.INTEGRATED[1:]))
    def test_failed_readback_never_releases(self):
        self.setup_controller()
        self.jobs.apis[U].bad_readback = {0}
        self.at(0, 70)
        for t in range(2, 70, 2): self.at(t)
        self.assertNotIn((U, 'default'), self.defaults())
        self.assertTrue(self.store.owned[U])
    def test_hot_stale_and_watchdog_stop_never_default(self):
        for temp, stale in ((80, False), (65, True), (65, False)):
            with self.subTest(temp=temp, stale=stale):
                self.setup_controller(owned=True)
                self.at(0)
                for t in range(2, 32, 2): self.at(t)
                self.jobs.stale = stale
                self.at(32, temp, stopping=True)
                self.assertFalse(self.defaults())
                self.assertTrue(all(self.store.owned.values()))
    def test_late_stop_requested_converts_default_to_boost(self):
        requested = [False]
        self.setup_controller(stop_requested=lambda: requested[0])
        self.at(0, 70)
        for t in range(2, 32, 2): self.at(t)
        requested[0] = True
        self.at(32)
        self.assertFalse(self.defaults())
    def test_readonly_modes_never_submit_setters_or_save(self):
        for owned in (False, True):
            self.setup_controller(owned=owned, readonly=True)
            self.at(0, 80); self.at(2, 65, stopping=True)
            self.assertTrue(all(action == 'inspect' for _, action in self.jobs.actions))
            self.assertFalse(self.store.saves)
    def test_conflicting_manual_controller_not_taken_over(self):
        self.setup_controller()
        self.jobs.apis[U].policies[1] = 1
        status = self.at(0, 80)
        self.assertEqual(status[U]['status'], 'degraded-controller-conflict')
        self.assertFalse(self.store.owned[U])
        self.assertFalse(any(x[0] in ('boost','default') for x in self.jobs.apis[U].calls))
    def test_failed_intent_persistence_prevents_all_setters(self):
        self.setup_controller(); self.store.fail = True
        with self.assertRaises(m.SafetyError): self.at(0, 80)
        self.assertFalse(any(a != 'inspect' for _, a in self.jobs.actions))
    def test_inspect_never_sets_and_unowned_setter_refused(self):
        api = API()
        m.device_job(U, 'inspect', False, lambda: api)
        self.assertFalse(any(x[0] in ('boost','default') for x in api.calls))
        with self.assertRaises(m.SafetyError): m.device_job(U, 'boost', False, lambda: api)
    def test_default_invalid_or_hot_temp_reboosts_every_fan(self):
        for temp in (66, 70, float('nan'), -1):
            api = API(); api.temp = temp
            result = m.device_job(U, 'default', True, lambda: api)
            self.assertFalse(result['ok'])
            self.assertEqual([x[1] for x in api.calls if x[0] == 'boost'], [0,1,2])
            self.assertFalse(any(x[0] == 'default' for x in api.calls))
    def test_default_failure_reboosts_all_and_remains_degraded(self):
        api = API(); api.temp = 65; api.default_error = True
        result = m.device_job(U, 'default', True, lambda: api)
        self.assertFalse(result['ok'])
        self.assertEqual([x[1] for x in api.calls if x[0] == 'boost'], [0,1,2])
    def test_new_ada_uuid_is_stable_under_reordered_config(self):
        new = "GPU-14c23cbc-12f0-9c61-0fda-7aaf80fbd1bf"
        self.assertIn(new, m.INTEGRATED)
        value = {"version": 1, "devices": list(reversed(m.KNOWN))}
        self.assertEqual(m.validate_config(value), value)
        api = API(count=1)
        result = m.device_job(new, "inspect", False, lambda: api)
        self.assertTrue(result["ok"])
        self.assertEqual(api.calls, [("bind", new)])
        self.assertNotIn(m.EXTERNAL, m.INTEGRATED)

    def test_new_ada_preserves_hot_and_cool_hysteresis(self):
        new = "GPU-14c23cbc-12f0-9c61-0fda-7aaf80fbd1bf"
        self.setup_controller()
        self.at(0, 69)
        self.assertFalse(self.store.owned[new])
        self.at(2, 70)
        self.assertTrue(self.store.owned[new])
        for t in range(4, 34, 2): self.at(t, 65)
        self.assertNotIn((new, "default"), self.defaults())
        self.at(34, 65)
        self.assertIn((new, "default"), self.defaults())
        self.assertFalse(self.store.owned[new])

    def test_config_exact_identity_duplicates_unknown_and_extra(self):
        valid = {'version': 1, 'devices': list(m.KNOWN)}
        self.assertEqual(m.validate_config(valid), valid)
        for change in ({'version': True}, {'devices': [U]*4}, {'devices': list(m.KNOWN)[:-1]},
                       {'devices': list(m.KNOWN)[:-1]+['GPU-unknown']}, {'extra': 1}):
            with self.subTest(change=change), self.assertRaises(m.SafetyError):
                m.validate_config(dict(valid, **change))
        with self.assertRaises(m.SafetyError): m.decode('{"version":1,"version":1}')
    def test_root_ownership_modes_identity_and_link_protection(self):
        valid = dict(st_mode=stat.S_IFREG|0o600, st_uid=0, st_nlink=1)
        m.check_meta(SimpleNamespace(**valid), private=True)
        for change in ({'st_uid': 501}, {'st_mode': stat.S_IFREG|0o666},
                       {'st_mode': stat.S_IFLNK|0o600}, {'st_nlink':2}):
            with self.subTest(change=change), self.assertRaises(m.SafetyError):
                m.check_meta(SimpleNamespace(**dict(valid, **change)), private=True)
        with self.assertRaises(m.SafetyError):
            m.check_meta(SimpleNamespace(**dict(valid, st_mode=stat.S_IFREG|0o644)), private=True)
    def test_state_requires_exact_owner_uuids_and_boolean_intents(self):
        good = {'version':1, 'owner':m.OWNER, 'owned':dict.fromkeys(m.INTEGRATED, True)}
        self.assertEqual(m.validate_state(good), good['owned'])
        for change in ({'owner':'other-controller'}, {'owned':{}},
                       {'owned':dict.fromkeys(m.INTEGRATED, 1)}, {'extra':True}):
            with self.subTest(change=change), self.assertRaises(m.SafetyError):
                m.validate_state(dict(good, **change))


class BoundedAndLoggingTests(unittest.TestCase):
    def test_blocked_child_remains_isolated_then_reaped_and_retried(self):
        jobs = m.BoundedJobs()
        blocked = Mock()
        blocked.is_alive.return_value = True
        jobs.blocked[U] = blocked
        read, write, process = Mock(), Mock(), Mock()
        read.poll.return_value = True
        read.recv.return_value = {'ok': True, 'errors': []}
        process.is_alive.return_value = False
        jobs.context = Mock()
        jobs.context.Pipe.return_value = (read, write)
        jobs.context.Process.return_value = process
        other = m.INTEGRATED[1]
        owned = dict.fromkeys(m.INTEGRATED, True)
        results = jobs.batch({U: 'boost', other: 'boost'}, owned)
        self.assertFalse(results[U]['ok'])
        self.assertTrue(results[other]['ok'])
        self.assertEqual(jobs.context.Process.call_count, 1)
        blocked.close.assert_not_called()
        blocked.is_alive.return_value = False
        result = jobs.batch({U: 'boost'}, owned)
        self.assertTrue(result[U]['ok'])
        self.assertNotIn(U, jobs.blocked)
        blocked.close.assert_called_once()
        self.assertEqual(jobs.context.Process.call_count, 2)
    def test_logging_deduplicates_samples_but_not_status_and_errors(self):
        clock, emit = Clock(), Mock()
        log = m.TransitionLog(clock=clock, emit=emit)
        status = {U: {'status':'observed', 'sample':{'temperature':70, 'sampled':0, 'errors':[]}}}
        log.write(status)
        for second in range(1, 60):
            clock.now = second
            status[U]['sample'].update(temperature=70+second/100, sampled=second)
            log.write(status)
        self.assertEqual(emit.call_count, 1)
        clock.now = 60; log.write(status)
        self.assertEqual(emit.call_count, 2)
        status[U]['status'] = 'degraded'; log.write(status)
        self.assertEqual(emit.call_count, 3)
        status[U]['sample']['errors'] = ['setter-failure']; log.write(status)
        self.assertEqual(emit.call_count, 4)


if __name__ == '__main__': unittest.main()
