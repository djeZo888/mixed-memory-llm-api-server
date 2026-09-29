"""Exact private ACTIVATE01 captures; real anchored metadata, no VM calls."""
import contextlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_h032_reconcile as original
from lifecycle.storage_binding import RegisteredStorageBinding

protocol, h = original.protocol, original.reconcile
SPEC = importlib.util.spec_from_file_location('h032_mode02_fixture',
    protocol.REPO / 'scripts/h032/image_mode02.py')
mode = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mode)
RETAINED = protocol.REPO.parent / 'output/private/retained'
CAPTURE = RETAINED / 'data/services/image21-runtime-20260923'


class Retained:
    def __enter__(self):
        self.base = protocol.OperationProtocol()
        self.base.setUp()
        self.stack, self.anchor = self.base.stack, self.base.anchor
        self.root, self.runtime = self.base.root, self.base.runtime
        self.base.boot = self.runtime.boot = h.BOOT
        manifest = json.loads((CAPTURE / (mode.PREFIX + 'archive-manifest.json')).read_bytes())
        self.names = list(mode.PINS) + [mode.PREFIX + 'archive/' + n for n in manifest['files']]
        self.names.append('logs/image-runtime-attempts/' + mode.FAILURE + '.json')
        for name in self.names:
            source = (RETAINED / 'data' / name) if name.startswith('logs/') else CAPTURE / name
            self.anchor.mkdir(str(Path(name).parent)) if '/' in name else None
            with self.anchor.open(name, os.O_WRONLY | os.O_CREAT | os.O_TRUNC) as stream:
                stream.write(source.read_bytes())
                os.fchmod(stream.fileno(), 0o400 if name in ('config.json', 'source/service.py')
                          or name.startswith(mode.PREFIX) or name.startswith('logs/') else 0o600)
        for name in ('recovery.lock', 'operation.lock'):
            with self.anchor.open(name, os.O_WRONLY | os.O_CREAT):
                pass
        self.before = {name: h.raw(self.anchor, name, 4 * 1024 * 1024) for name in self.names}
        self.runtime.config = json.loads(self.before['config.json'])
        self.binding = types.SimpleNamespace(path=lambda role: str(self.root / 'logs'),
            mounted_guard=lambda _io: contextlib.nullcontext(self.base.storage_guard))
        self.runtime.binding = self.binding
        self.module = types.SimpleNamespace(storage_io=types.SimpleNamespace(
            AnchoredRoot=lambda path, guard: protocol.storage_io.AnchoredRoot(path, guard, uid=os.geteuid())),
            Runtime=self.new_runtime)
        self.stack.enter_context(patch.object(mode, 'UID', os.geteuid()))
        self.stack.enter_context(patch.object(mode, 'GID', os.getegid()))
        self.stack.enter_context(patch.object(mode, 'time', types.SimpleNamespace(time=lambda: mode.END - 60)))
        self.stack.enter_context(patch.object(protocol.service, 'run', side_effect=AssertionError('native replay')))
        def protected(path):
            assert Path(path) == Path(mode.__file__)
            return Path(path).read_bytes()
        self.stack.enter_context(patch.object(h, 'protected', side_effect=protected))
        self.constructed = self.proofs = 0
        return self

    def __exit__(self, *_args):
        self.base.doCleanups()

    def new_runtime(self):
        reader = RegisteredStorageBinding(types.SimpleNamespace(owner=os.geteuid()), self.base.snapshot)
        def validate_path(role, path):
            assert role == 'services' and Path(path) == self.root / 'config.json'
            return Path(path)
        reader.validate_path = validate_path
        updated = self.base.make_runtime()
        updated.config = reader.read_json('services', self.root / 'config.json')
        updated.boot = h.BOOT
        updated.binding = self.binding
        self.constructed += 1
        return updated

    def prove(self, helper, runtime):
        self.proofs += 1
        for name in ('recovery.lock', 'operation.lock'):
            with self.base.assertRaises(BlockingIOError):
                with mode.held_lock(self.anchor, name):
                    raise AssertionError('lock not held')
        self.base.assert_common_available()

    def run(self):
        return mode.continue_handoff(h, self.module, self.runtime, prove=self.prove)


@unittest.skipUnless(CAPTURE.is_dir(), 'private retained ACTIVATE01 records unavailable')
class Mode02Tests(unittest.TestCase):
    def test_only_two_modes_change_and_original_evidence_survives_handoff(self):
        with Retained() as fixture:
            names = ('config.json', 'source/service.py')
            identity = lambda n: tuple(getattr(fixture.anchor.stat(n), k) for k in
                ('st_dev', 'st_ino', 'st_uid', 'st_gid', 'st_size', 'st_mtime_ns'))
            before = {n: identity(n) for n in names}
            with patch.object(mode.os, 'fchmod', wraps=os.fchmod) as chmod:
                result = fixture.run()
            self.assertEqual(chmod.call_count, 2)
            self.assertTrue(all(call.args[1] == 0o600 for call in chmod.call_args_list))
            self.assertEqual(result['status'], 'MODE_REPAIRED_HANDOFF_PUBLISHED_API_STILL_PAUSED')
            self.assertEqual((fixture.constructed, fixture.proofs), (1, 2))
            for name in names:
                self.assertEqual(identity(name), before[name])
                self.assertEqual(fixture.anchor.stat(name).st_mode & 0o777, 0o600)
            for name, value in fixture.before.items():
                if name != 'recovery.json':
                    self.assertEqual(h.raw(fixture.anchor, name, 4 * 1024 * 1024), value)
            handoff = fixture.anchor.read_json('h032-image-handoff.json')
            self.assertEqual(handoff['archive_sha256'], mode.PINS[mode.PREFIX + 'archive-manifest.json'])
            self.assertEqual(handoff['cleanup_consumption_sha256'], mode.PINS[mode.PREFIX + 'consumed.json'])
            self.assertEqual(fixture.runtime.record('recovery.json')['status'], 'active')
            with self.assertRaisesRegex(RuntimeError, 'saved_bytes_changed|continuation_already_attempted'):
                fixture.run()

    def test_changed_operational_state_archive_failure_or_mode_refuses_before_mutation(self):
        cases = [('config.json', 'bytes'), ('source/service.py', 'bytes'), ('state.json', 'bytes'),
                 ('operation.json', 'bytes'), ('recovery.json', 'bytes'),
                 (mode.PREFIX + 'archive/state.json', 'bytes'),
                 (mode.PREFIX + 'archive/state.json', 'mode'),
                 ('logs/image-runtime-attempts/' + mode.FAILURE + '.json', 'bytes'),
                 ('config.json', 'mode'), ('source/service.py', 'mode')]
        for name, change in cases:
            with self.subTest(name=name, change=change), Retained() as fixture:
                path = fixture.root / name
                if change == 'mode':
                    path.chmod(0o600)
                else:
                    path.chmod(0o600)
                    path.write_bytes(fixture.before[name] + b' ')
                with patch.object(mode.os, 'fchmod', wraps=os.fchmod) as chmod:
                    with self.assertRaisesRegex(RuntimeError,
                            'saved_bytes_changed|archive_changed|archive_mode_changed|original_failure_changed|operational_metadata_changed'):
                        fixture.run()
                self.assertEqual(chmod.call_count, 0)
                self.assertIsNone(fixture.anchor.stat('h032-image-mode02-consumed.json', missing_ok=True))
                self.assertIsNone(fixture.anchor.stat('h032-image-handoff.json', missing_ok=True))
                self.assertEqual(fixture.constructed, 0)

    def test_busy_existing_descriptor_refuses_before_mode_change(self):
        for name in ('recovery.lock', 'operation.lock'):
            with self.subTest(name=name), Retained() as fixture:
                with mode.held_lock(fixture.anchor, name):
                    with patch.object(mode.os, 'fchmod', wraps=os.fchmod) as chmod:
                        with self.assertRaises(BlockingIOError):
                            fixture.run()
                        self.assertEqual(chmod.call_count, 0)
                for leaf in ('config.json', 'source/service.py'):
                    self.assertEqual(fixture.anchor.stat(leaf).st_mode & 0o777, 0o400)
                self.assertIsNone(fixture.anchor.stat('h032-image-mode02-consumed.json', missing_ok=True))

    def test_second_file_mode_race_after_guard_refuses_before_marker_or_fchmod(self):
        with Retained() as fixture:
            critical = fixture.runtime.critical
            @contextlib.contextmanager
            def raced(**kwargs):
                with critical(**kwargs):
                    (fixture.root / 'config.json').chmod(0o600)
                    yield
            with patch.object(fixture.runtime, 'critical', raced), \
                 patch.object(mode.os, 'fchmod', wraps=os.fchmod) as chmod:
                with self.assertRaisesRegex(RuntimeError, 'operational_metadata_changed'):
                    fixture.run()
            self.assertEqual(chmod.call_count, 0)
            self.assertEqual(fixture.anchor.stat('source/service.py').st_mode & 0o777, 0o400)
            self.assertIsNone(fixture.anchor.stat('h032-image-mode02-consumed.json', missing_ok=True))
            self.assertIsNone(fixture.anchor.stat('h032-image-handoff.json', missing_ok=True))

    def test_boot_hardware_or_storage_guard_refuses_before_mode_change(self):
        for guard in ('boot', 'hardware_valid', 'storage_valid'):
            with self.subTest(guard=guard), Retained() as fixture:
                setattr(fixture.base, guard, 'changed-boot' if guard == 'boot' else False)
                with patch.object(mode.os, 'fchmod', wraps=os.fchmod) as chmod:
                    with self.assertRaisesRegex(RuntimeError,
                            'image_boot_changed|hardware_validation_stale|fixture_mount_lost'):
                        fixture.run()
                self.assertEqual(chmod.call_count, 0)
                # Restore only fixture proof to inspect unmodified anchored files.
                setattr(fixture.base, guard, h.BOOT if guard == 'boot' else True)
                for leaf in ('config.json', 'source/service.py'):
                    self.assertEqual(fixture.anchor.stat(leaf).st_mode & 0o777, 0o400)
                self.assertIsNone(fixture.anchor.stat('h032-image-mode02-consumed.json', missing_ok=True))
                self.assertIsNone(fixture.anchor.stat('h032-image-handoff.json', missing_ok=True))


if __name__ == '__main__':
    unittest.main()
