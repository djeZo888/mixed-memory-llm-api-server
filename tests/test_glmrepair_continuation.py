"""Narrow offline checks for explicit root control and the restored second attempt."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from benchmark import fixtures, glmrepair as g

START = 1789850405.174489
DEADLINE = 1789854005.174489


def save(path, value):
    path.write_text(json.dumps(value))


class ExplicitRootControl(unittest.TestCase):
    def test_missing_control_and_changed_note_do_not_stop(self):
        with tempfile.TemporaryDirectory() as directory:
            task = Path(directory)
            g.checkpoint(task)
            for note in (b'Root reviewed the running task.',
                         b'Historical STOP is preserved; PAUSE was not requested. Do not interrupt.'):
                (task/'incoming-latest.md').write_bytes(note)
                (task/'incoming-reviewed.sha256').write_text('obsolete hash')
                g.checkpoint(task)
                observed = json.loads((task/'incoming-observed.json').read_bytes())
                self.assertEqual(observed['sha256'], fixtures.digest(note))

    def test_exact_control_actions_only(self):
        with tempfile.TemporaryDirectory() as directory:
            task = Path(directory)
            save(task/'run-control.json', {'action': 'CONTINUE'})
            g.checkpoint(task)
            for action in ('STOP', 'PAUSE'):
                save(task/'run-control.json', {'action': action})
                with self.assertRaisesRegex(RuntimeError, '^ROOT_CONTROL_' + action + '$'):
                    g.checkpoint(task)
            for value in ({'action': 'stop'}, {'action': 'PLEASE STOP'}, {'action': 'UNKNOWN'}, {}):
                save(task/'run-control.json', value)
                with self.assertRaises((RuntimeError, ValueError)):
                    g.checkpoint(task)

    def test_attempt2_reads_parent_control_and_records_parent_note(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); task = root/'attempt2'; task.mkdir()
            note = b'Keep historical STOP receipt; no interruption to this request.'
            (root/'incoming-latest.md').write_bytes(note)
            save(root/'run-control.json', {'action': 'CONTINUE'})
            save(task/'run-control.json', {'action': 'STOP'})
            g.checkpoint(task)
            observed = json.loads((task/'incoming-observed.json').read_bytes())
            self.assertEqual(observed['sha256'], fixtures.digest(note))
            save(root/'run-control.json', {'action': 'PAUSE'})
            with self.assertRaisesRegex(RuntimeError, '^ROOT_CONTROL_PAUSE$'):
                g.checkpoint(task)


class RestoredContinuation(unittest.TestCase):
    def state(self, root):
        clock = {'start_epoch': START, 'deadline_epoch': DEADLINE, 'budget_seconds': 3600,
                 'clock': 'UTC_wall_seconds_first_staging_maintenance', 'restoration_outside_budget': True}
        status = {'campaign': 'benchrun-glmrepair-20260919', 'phase': 'RESTORED', 'host_session_closed': True,
                  'completed': [], 'inflight': {}, 'clock': copy.deepcopy(clock)}
        progress = {'phase': 'RESTORED', 'completed': {}, 'inflight': {},
                    'errors': [{'error_class': 'RuntimeError'}]}
        for name, value in (('execution', clock), ('status', status), ('progress', progress)):
            save(root/(name + '.json'), value)
        return clock, status, progress

    def test_verified_empty_attempt_keeps_original_clock_exactly(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); task = root/'attempt2'; task.mkdir()
            original, _, _ = self.state(root)
            before = {name: (root/name).read_bytes() for name in ('execution.json', 'status.json', 'progress.json')}
            self.assertEqual(g.continuation_execution(task), original)
            self.assertEqual({name: (root/name).read_bytes() for name in before}, before)

    def test_continuation_requires_restoration_closed_session_and_no_requests(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); task = root/'attempt2'; task.mkdir()
            mutations = [('status', 'campaign', 'benchrun-unrelated'), ('status', 'phase', 'RESTORING'),
                         ('status', 'host_session_closed', False), ('status', 'completed', ['stream']),
                         ('status', 'inflight', {'stream': {}}), ('progress', 'phase', 'ACTIVE'),
                         ('progress', 'completed', {'warmup': {}}), ('progress', 'inflight', {'stream': {}})]
            for filename, key, value in mutations:
                with self.subTest(filename=filename, key=key):
                    self.state(root)
                    path = root/(filename + '.json'); data = json.loads(path.read_bytes()); data[key] = value
                    save(path, data)
                    with self.assertRaises((RuntimeError, ValueError)):
                        g.continuation_execution(task)

    def test_changed_epoch_deadline_or_budget_cannot_reset_window(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); task = root/'attempt2'; task.mkdir()
            for key, value in (('start_epoch', START + 1), ('deadline_epoch', DEADLINE + 1),
                               ('budget_seconds', 21600)):
                with self.subTest(key=key):
                    clock, status, _ = self.state(root)
                    clock[key] = value; status['clock'] = copy.deepcopy(clock)
                    save(root/'execution.json', clock); save(root/'status.json', status)
                    with self.assertRaises((RuntimeError, ValueError)):
                        g.continuation_execution(task)


if __name__ == '__main__':
    unittest.main()
