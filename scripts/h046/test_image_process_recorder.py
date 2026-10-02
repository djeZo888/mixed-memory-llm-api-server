"""Focused H046 offline checks, including real local child wait/reap checks.

These checks execute local Python/true children only. They do not qualify any
native model, remote lifecycle, GPU, Sova gate, or image request.
"""
import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('h046_image_recorder', HERE / 'image_process_recorder.py')
R = importlib.util.module_from_spec(spec)
spec.loader.exec_module(R)


def row(pid=100, *, ticks='100', ppid=1, pgid=100, sid=100, uid=None, boot='boot-A'):
    uid = os.geteuid() if uid is None else uid
    return {'pid': pid, 'ppid': ppid, 'pgid': pgid, 'sid': sid,
            'startTicks': ticks, 'bootId': boot, 'uid': uid,
            'uidTuple': [uid] * 4, 'cgroupPath': '/test',
            'executable': {'path': '/bin/test', 'device': 1, 'inode': 2}}


class Deadline:
    def __init__(self, seconds=15):
        self.end = time.monotonic() + seconds

    def remaining(self):
        return self.end - time.monotonic()

    def check(self, reserve=0):
        if self.remaining() <= reserve:
            raise TimeoutError('offline test deadline')


class InventoryChecks(unittest.TestCase):
    def setUp(self):
        self.owner = row()
        self.known = R.BirthRegistry()
        self.known[R.birth_key(self.owner)] = self.owner
        self.allowed = {os.geteuid()}

    def capture(self, rows, *, identity=None, reap=None, ambiguities=()):
        with patch.object(R, 'snapshot', return_value=R.Inventory(rows, ambiguities)), \
                patch.object(R, 'process_identity', side_effect=identity or (lambda pid: next(v for v in rows if v['pid'] == pid))):
            return R.capture(self.owner, self.known, self.allowed, reap_direct=reap)

    def test_direct_exe_disappearance_requires_actual_reap(self):
        calls = []
        def reaped():
            calls.append('actual direct wait')
            return True
        with self.assertRaises(R.DirectChildReaped) as caught:
            self.capture([self.owner], identity=FileNotFoundError('/proc/exe vanished'), reap=reaped)
        self.assertEqual(calls, ['actual direct wait'])
        self.assertEqual(caught.exception.observation['phase'], 'strict')
        self.assertEqual(self.known.ambiguities, [])
        # Reaping is not the absence proof: a new current inventory is required.
        self.assertEqual(self.capture([]), [])

    def test_direct_disappearance_without_reap_is_refused(self):
        with self.assertRaisesRegex(R.ProcessSamplingError, 'unresolved'):
            self.capture([self.owner], identity=FileNotFoundError(), reap=lambda: False)
        self.assertEqual(self.known.ambiguities[0]['error'], 'DIRECT_OBSERVATION_NOT_REAPED')

    def test_direct_basic_enoent_resolved_only_by_reap(self):
        ambiguity = {'pid': 100, 'observations': [], 'vanished': True, 'error': 'FileNotFoundError'}
        with self.assertRaises(R.DirectChildReaped) as caught:
            self.capture([], ambiguities=[ambiguity], reap=lambda: True)
        self.assertEqual(caught.exception.observation['phase'], 'basic')

    def test_direct_nonvanished_basic_error_not_excused(self):
        ambiguity = {'pid': 100, 'observations': [], 'vanished': False, 'error': 'PermissionError'}
        with self.assertRaises(R.ProcessSamplingError):
            self.capture([], ambiguities=[ambiguity], reap=lambda: self.fail('no direct exception'))

    def test_related_foreign_uid_not_excused_by_direct_exit(self):
        foreign = row(101, ticks='101', ppid=100, uid=os.geteuid() + 1)
        def current(pid):
            if pid == 100:
                raise FileNotFoundError()
            return foreign
        with self.assertRaisesRegex(R.ProcessSamplingError, 'unapproved related UID'):
            self.capture([self.owner, foreign], identity=current,
                         reap=lambda: self.fail('foreign UID must precede direct resolution'))

    def test_related_birth_is_saved_before_direct_reap(self):
        descendant = row(101, ticks='101', ppid=100)
        def current(pid):
            if pid == 100:
                raise FileNotFoundError()
            return descendant
        with self.assertRaises(R.DirectChildReaped):
            self.capture([self.owner, descendant], identity=current, reap=lambda: True)
        self.assertIn(R.birth_key(descendant), self.known)
        self.assertIn(R.birth_key(descendant), self.known.relatedHistory)

    def test_related_vanished_is_real_ambiguity(self):
        descendant = row(101, ticks='101', ppid=100)
        with self.assertRaises(R.ProcessSamplingError):
            self.capture([self.owner, descendant], identity=FileNotFoundError(),
                         reap=lambda: self.fail('sibling ambiguity must not be excused'))

    def test_reused_original_pid_is_refused(self):
        replacement = row(100, ticks='200', pgid=200, sid=200)
        with self.assertRaisesRegex(R.ProcessSamplingError, 'PID reused'):
            self.capture([replacement], reap=lambda: self.fail('reused PID'))

    def test_stale_group_relation_is_refused(self):
        stranger = row(103, ticks='103', ppid=1)
        with self.assertRaisesRegex(R.ProcessSamplingError, 'stale recorded'):
            self.capture([stranger])

    def test_changed_boot_is_refused(self):
        with patch.object(R, 'current_boot', return_value='boot-B'):
            with self.assertRaisesRegex(R.ProcessSamplingError, 'boot changed'):
                R.snapshot(self.owner, self.allowed)

    def test_uid_or_cgroup_change_is_refused(self):
        changed = copy.deepcopy(self.owner)
        changed['cgroupPath'] = '/foreign'
        with self.assertRaisesRegex(R.ProcessSamplingError, 'UID/cgroup changed'):
            self.capture([self.owner], identity=lambda _: changed)

    def test_independent_absence_remains_unknown_after_sampling_failure(self):
        events = []
        with patch.object(R, 'capture', side_effect=R.ProcessSamplingError('genuine ambiguity')), \
                patch.object(R.time, 'sleep'), \
                patch.object(R.time, 'monotonic', side_effect=range(100)):
            closure = R.settle_births(self.owner, self.known, self.allowed, events)
        self.assertEqual(closure['independentBirthGroupAbsence'], 'UNKNOWN')
        self.assertTrue(closure['settlementFailures'])


class ExecutableChecks(unittest.TestCase):
    def fake_proc(self):
        root = Path(tempfile.mkdtemp(prefix='h046-recorder-proc-', dir='/codex/tmp'))
        proc = root / 'proc' / '100'
        proc.mkdir(parents=True)
        (proc / 'status').write_text('Uid:\t0\t0\t0\t0\n')
        (proc / 'cgroup').write_text('0::/test\n')
        return root

    def test_exe_disappears_in_zombie_transition(self):
        root = self.fake_proc()
        v = row()
        def redirect(value):
            p = Path(value)
            return root / p.relative_to('/') if p.is_absolute() else p
        with patch.object(R, 'P', side_effect=redirect), \
                patch.object(R, 'current_boot', return_value='boot-A'), \
                patch.object(R, '_stat', side_effect=[(v, 'R'), (v, 'Z'), (v, 'Z')]), \
                patch.object(R.os, 'readlink', side_effect=FileNotFoundError()):
            result = R.process_identity(100)
        self.assertIsNone(result['executable'])
        self.assertEqual(result['startTicks'], '100')

    def test_exe_disappearance_birth_change_is_not_exit_exception(self):
        root = self.fake_proc()
        v = row()
        replacement = row(ticks='200')
        def redirect(value):
            p = Path(value)
            return root / p.relative_to('/') if p.is_absolute() else p
        with patch.object(R, 'P', side_effect=redirect), \
                patch.object(R, 'current_boot', return_value='boot-A'), \
                patch.object(R, '_stat', side_effect=[(v, 'R'), (replacement, 'Z')]), \
                patch.object(R.os, 'readlink', side_effect=FileNotFoundError()):
            with self.assertRaisesRegex(R.ProcessSamplingError, 'birth changed'):
                R.process_identity(100)


class ActualWaitChecks(unittest.TestCase):
    def test_actual_kernel_pid_status_recorded_and_cached_honestly(self):
        child = SimpleNamespace(pid=100, args=['/usr/bin/true'], returncode=None)
        receipts = []
        with patch.object(R.os, 'waitpid', return_value=(100, 7 << 8)) as actual_wait:
            self.assertEqual(R.actual_child_wait(child, receipts), 7)
            self.assertEqual(R.actual_child_wait(child, receipts), 7)
        actual_wait.assert_called_once_with(100, 0)
        self.assertEqual(receipts[0]['actualWaitStatus'], 7 << 8)
        self.assertEqual(receipts[0]['pid'], 100)

    def test_echild_refuses_synthesized_zero(self):
        child = SimpleNamespace(pid=100, args=['/usr/bin/true'], returncode=None)
        receipts = []
        with patch.object(R.os, 'waitpid', side_effect=ChildProcessError('external reaper')):
            with self.assertRaises(ChildProcessError):
                R.actual_child_wait(child, receipts)
        self.assertIsNone(child.returncode)
        self.assertEqual(receipts, [])

    def test_cached_zero_without_kernel_receipt_refused(self):
        child = SimpleNamespace(pid=100, args=['/usr/bin/true'], returncode=0)
        with self.assertRaisesRegex(R.ProcessSamplingError, 'no actual wait receipt'):
            R.actual_child_wait(child, [])

    def test_wrong_kernel_wait_pid_refused(self):
        child = SimpleNamespace(pid=100, args=['/usr/bin/true'], returncode=None)
        with patch.object(R.os, 'waitpid', return_value=(200, 0)):
            with self.assertRaisesRegex(R.ProcessSamplingError, 'PID/status mismatch'):
                R.actual_child_wait(child, [])


class LocalChildChecks(unittest.TestCase):
    def evidence(self):
        parent = Path(os.environ.get('H046_RECORDER_TEST_EVIDENCE', '/codex/tmp'))
        parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        return Path(tempfile.mkdtemp(prefix='local-child-', dir=parent))

    def run_child(self, argv, *, capture_patch=None):
        directory = self.evidence()
        env = {'PATH': '/usr/bin:/bin', 'LC_ALL': 'C', 'TMPDIR': str(directory)}
        kwargs = dict(argv=argv, cwd=str(directory), env=env,
                      out=directory/'stdout', err=directory/'stderr',
                      launch=directory/'launch.json', terminal_path=directory/'terminal.json',
                      seconds=3, deadline=Deadline(), gate=HERE/'image_command_gate.py',
                      python=sys.executable)
        if capture_patch:
            with patch.object(R, 'capture', side_effect=capture_patch):
                result = R.run_gated(**kwargs)
        else:
            result = R.run_gated(**kwargs)
        return result, directory

    def assert_closed(self, result, directory, code=0):
        self.assertEqual(result['actualExitCode'], code)
        self.assertIsNone(result['failure'])
        self.assertTrue(result['reaped'])
        self.assertTrue(result['directWaitEvidence'])
        self.assertIs(result['closure']['independentBirthGroupAbsence'], True)
        self.assertEqual(result['closure']['remainingKnownBirthsOrGroups'], [])
        self.assertEqual(json.loads((directory/'terminal.json').read_text())['actualExitCode'], code)
        self.assertIs(json.loads((directory/'terminal.json.closure').read_text())['independentBirthGroupAbsence'], True)
        with self.assertRaises(ProcessLookupError):
            os.killpg(result['pgid'], 0)

    def test_actual_fast_zero_exit_reaped_and_independent_absent(self):
        for _ in range(8):
            result, directory = self.run_child(['/usr/bin/true'])
            self.assert_closed(result, directory)

    def test_actual_nonzero_exit_is_preserved(self):
        result, directory = self.run_child([sys.executable, '-I', '-S', '-B', '-c', 'raise SystemExit(7)'])
        self.assert_closed(result, directory, code=7)

    def test_terminal_precedes_independent_postreap_check(self):
        original = R.capture
        observed = []
        def race(owner, known, allowed, reap_direct=None):
            if reap_direct is not None:
                if reap_direct():
                    observed.append('actual_reap')
                    raise R.DirectChildReaped({'phase': 'injected direct exe ENOENT'})
            else:
                # /proc sampling after reaping must only happen after terminal.
                candidates = list(Path(os.environ['H046_RECORDER_TEST_EVIDENCE']).glob('local-child-*/terminal.json'))
                relevant = [p for p in candidates if json.loads(p.read_text())['pid'] == owner['pid']]
                self.assertEqual(len(relevant), 1)
                observed.append('fresh independent scan after terminal')
            return original(owner, known, allowed, reap_direct=reap_direct)
        result, directory = self.run_child(['/usr/bin/true'], capture_patch=race)
        self.assert_closed(result, directory)
        self.assertEqual(observed[0], 'actual_reap')
        self.assertIn('fresh independent scan after terminal', observed)

    def test_actual_child_wait_resolves_injected_direct_exe_disappearance(self):
        original = R.capture
        identity = R.process_identity
        def vanished(owner, known, allowed, reap_direct=None):
            if reap_direct is None:
                return original(owner, known, allowed)
            def proc_identity(pid):
                if pid == owner['pid']:
                    raise FileNotFoundError('injected /proc/direct-child/exe race')
                return identity(pid)
            with patch.object(R, 'process_identity', side_effect=proc_identity):
                return original(owner, known, allowed, reap_direct=reap_direct)
        result, directory = self.run_child(['/usr/bin/true'], capture_patch=vanished)
        self.assert_closed(result, directory)
        resolved = [v for v in result['closure']['signals']
                    if 'directExitObservationResolvedByActualWait' in v]
        self.assertTrue(resolved)
        self.assertIs(resolved[0]['independentAbsenceStillRequired'], True)
        self.assertEqual(result['closure']['basicAmbiguities'], [])

    def test_refused_sampling_error_survives_later_clear_scan(self):
        original = R.capture
        first = True
        def ambiguous(owner, known, allowed, reap_direct=None):
            nonlocal first
            if first:
                first = False
                raise R.ProcessSamplingError('genuine injected foreign ambiguity')
            return original(owner, known, allowed, reap_direct=reap_direct)
        result, directory = self.run_child(['/usr/bin/true'], capture_patch=ambiguous)
        self.assertTrue(result['reaped'])
        self.assertIn('genuine injected foreign ambiguity', result['failure']['message'])
        self.assertIs(result['closure']['independentBirthGroupAbsence'], True)
        # A later closure never clears the first execution failure.
        self.assertIsNotNone(json.loads((directory/'terminal.json').read_text())['failure'])

    def test_original_receipts_cannot_be_overwritten(self):
        directory = self.evidence()
        path = directory / 'receipt.json'
        R.put(path, b'original-failure\n')
        with self.assertRaises(FileExistsError):
            R.put(path, b'later-pass\n')
        self.assertEqual(path.read_bytes(), b'original-failure\n')


if __name__ == '__main__':
    os.umask(0o077)
    os.environ.setdefault('H046_RECORDER_TEST_EVIDENCE', tempfile.mkdtemp(prefix='h046-recorder-tests-', dir='/codex/tmp'))
    unittest.main(verbosity=2)
