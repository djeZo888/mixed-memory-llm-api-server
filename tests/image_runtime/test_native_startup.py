"""Local startup fixtures: no main, native packages, model or guest operations."""
import ast
import contextlib
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('image_native_startup',
                                             ROOT / 'scripts/image_runtime/native_server.py')
native = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(native)
INVOCATION = 'a' * 32
GPU = 'GPU-12345678-1234-1234-1234-123456789abc'
ARGS = ['native_server.py', INVOCATION, GPU]
ENV = {'CUDA_VISIBLE_DEVICES': GPU, 'NVIDIA_VISIBLE_DEVICES': GPU}


class ExecReplaced(BaseException):
    """Only the mocked exec boundary; never invoke a process."""


@contextlib.contextmanager
def fixture():
    with tempfile.TemporaryDirectory(prefix='image-startup-') as temporary:
        work = Path(temporary) / 'work'
        evidence = work / 'evidence'
        leaf = evidence / INVOCATION
        work.mkdir(mode=0o755)
        evidence.mkdir(mode=0o755)
        leaf.mkdir(mode=0o700)
        owners = {work.stat().st_ino: (0, 1001), evidence.stat().st_ino: (0, 1001),
                  leaf.stat().st_ino: (1000, 1001)}
        real_open, real_fstat = os.open, os.fstat
        overlay = Mock()
        execute = Mock(side_effect=ExecReplaced)
        redirect = Mock()
        state = SimpleNamespace(work=work, evidence=evidence, leaf=leaf, owners=owners,
                                overlay=overlay, execute=execute, redirect=redirect,
                                log_error=None)

        def open_fixed(path, flags, mode=0o777, *, dir_fd=None):
            if path == '/work':
                path = work
            if path == 'backend.log' and state.log_error is not None:
                raise state.log_error
            return real_open(path, flags, mode, dir_fd=dir_fd)

        def metadata(fd):
            meta = real_fstat(fd)
            fields = list(meta)
            fields[4:6] = owners.get(meta.st_ino, (1000, 1001))
            return os.stat_result(fields)

        with patch.object(native.os, 'open', side_effect=open_fixed), \
                patch.object(native.os, 'fstat', side_effect=metadata), \
                patch.object(native.os, 'geteuid', return_value=1000), \
                patch.object(native.os, 'getegid', return_value=1001), \
                patch.object(native, 'verify_adaptive_overlay', overlay), \
                patch.object(native.os, 'execvp', execute), \
                patch.object(native.os, 'dup2', redirect):
            yield state


class NativeStartup(unittest.TestCase):
    def records(self, state):
        raw = (state.leaf / 'startup.jsonl').read_bytes()
        self.assertLessEqual(len(raw), 5 * 256)
        self.assertNotIn(b'PRIVATE_SENTINEL', raw)
        records = [json.loads(line) for line in raw.splitlines()]
        self.assertLessEqual(len(records), 5)
        for row in records:
            self.assertEqual(set(row), {'stage', 'code', 'exceptionClass', 'causeClass'})
        return records

    def test_visibility_refusal_retained_before_overlay_or_log(self):
        for args, env in [(ARGS[:-1] + ['0'], ENV),
                          (ARGS[:-1] + [GPU[:-1]], ENV),
                          (ARGS, {}),
                          (ARGS, dict(ENV, CUDA_VISIBLE_DEVICES='0')),
                          (ARGS, dict(ENV, NVIDIA_VISIBLE_DEVICES='PRIVATE_SENTINEL'))]:
            with self.subTest(args_valid=args[-1] == GPU), fixture() as state:
                with self.assertRaises(RuntimeError):
                    native.launch_owned(args, env)
                row = self.records(state)[-1]
                self.assertEqual(row, {'stage': 'visibility', 'code': 'unexpected_gpu_visibility',
                                       'exceptionClass': 'RuntimeError', 'causeClass': 'none'})
                state.overlay.assert_not_called()
                state.execute.assert_not_called()
                self.assertFalse((state.leaf / 'backend.log').exists())

    def test_overlay_errors_and_fixed_cause_classes_retained(self):
        class PRIVATE_SENTINEL_Error(Exception):
            pass
        wrapped = RuntimeError('PRIVATE_SENTINEL')
        wrapped.__cause__ = PermissionError('PRIVATE_SENTINEL')
        for error, code, cls, cause in [
                (RuntimeError('adaptive_overlay_verifier_mismatch'),
                 'adaptive_overlay_verifier_mismatch', 'RuntimeError', 'none'),
                (ValueError('adaptive_overlay_digest_mismatch'),
                 'adaptive_overlay_digest_mismatch', 'ValueError', 'none'),
                (FileNotFoundError('PRIVATE_SENTINEL'), 'overlay_failed', 'FileNotFoundError', 'none'),
                (PRIVATE_SENTINEL_Error('PRIVATE_SENTINEL'), 'overlay_failed', 'Exception', 'none'),
                (wrapped, 'overlay_failed', 'RuntimeError', 'PermissionError')]:
            with self.subTest(code=code, cls=cls), fixture() as state:
                state.overlay.side_effect = error
                with self.assertRaises(Exception) as caught:
                    native.launch_owned(ARGS, ENV)
                self.assertIs(caught.exception, error)
                self.assertEqual(self.records(state)[-1],
                                 {'stage': 'overlay', 'code': code,
                                  'exceptionClass': cls, 'causeClass': cause})
                state.execute.assert_not_called()
                self.assertFalse((state.leaf / 'backend.log').exists())

    def test_log_open_failure_retained_and_exec_blocked(self):
        with fixture() as state:
            state.log_error = PermissionError('PRIVATE_SENTINEL')
            with self.assertRaises(PermissionError):
                native.launch_owned(ARGS, ENV)
            self.assertEqual(self.records(state)[-1],
                             {'stage': 'log_open', 'code': 'log_open_failed',
                              'exceptionClass': 'PermissionError', 'causeClass': 'none'})
            state.execute.assert_not_called()
            state.redirect.assert_not_called()

    def test_exec_failure_retained_after_exclusive_log_open(self):
        with fixture() as state:
            state.execute.side_effect = FileNotFoundError('PRIVATE_SENTINEL')
            with self.assertRaises(FileNotFoundError):
                native.launch_owned(ARGS, ENV)
            self.assertEqual(self.records(state)[-1],
                             {'stage': 'exec', 'code': 'exec_failed',
                              'exceptionClass': 'FileNotFoundError', 'causeClass': 'none'})
            self.assertEqual((state.leaf / 'backend.log').read_bytes(), b'')

    def test_success_reaches_same_fixed_launch_and_only_entry_receipts(self):
        expected_functions = {
            'launch_argv': '8f30f822e625bf2e9e180f24f9e84974dca150cd1407cb316c4bf15cec78f331',
            'selected_gpu': '71ca8666f6b1258991b19fac3466a2ae55f6ed0c25278f82af8758e5198b0752',
            'verify_adaptive_overlay': '6b8427b0b67017357f3730edf74a7eefbb014ef49a0a5db39c79ab61e38a92ae',
        }
        for node in ast.parse(Path(native.__file__).read_text()).body:
            if isinstance(node, ast.FunctionDef) and node.name in expected_functions:
                self.assertEqual(hashlib.sha256(ast.dump(node, include_attributes=False).encode()).hexdigest(),
                                 expected_functions[node.name])
        with fixture() as state:
            before_env = ENV.copy()
            with self.assertRaises(ExecReplaced):
                native.launch_owned(ARGS, ENV)
            self.assertEqual(ENV, before_env)
            launch = native.launch_argv()
            state.execute.assert_called_once_with(launch[0], launch)
            state.overlay.assert_called_once_with()
            self.assertEqual([call.args[1] for call in state.redirect.call_args_list], [1, 2])
            self.assertEqual([row['stage'] for row in self.records(state)],
                             ['visibility', 'overlay', 'log_open', 'exec'])
            self.assertTrue(all(row['code'] == 'entered' for row in self.records(state)))
            for name in ('startup.jsonl', 'backend.log'):
                self.assertEqual(stat.S_IMODE((state.leaf / name).stat().st_mode), 0o600)

    def test_malformed_invocation_refused_before_any_evidence(self):
        for args in [[], ARGS[:1], ARGS[:2], ARGS + ['extra'],
                     [ARGS[0], '../escape', GPU], [ARGS[0], 'A' * 32, GPU]]:
            with self.subTest(length=len(args)), fixture() as state:
                with self.assertRaises(RuntimeError):
                    native.launch_owned(args, ENV)
                self.assertEqual(list(state.leaf.iterdir()), [])
                state.overlay.assert_not_called()
                state.execute.assert_not_called()

    def test_symlink_in_any_evidence_component_refused_without_fallback(self):
        for part in ('work', 'evidence', 'leaf'):
            with self.subTest(part=part), fixture() as state:
                original = getattr(state, part)
                target = original.with_name(original.name + '-preserved')
                original.rename(target)
                original.symlink_to(target, target_is_directory=True)
                with self.assertRaises(OSError):
                    native.launch_owned(ARGS, ENV)
                self.assertFalse(list(state.work.rglob('startup.jsonl')))
                state.overlay.assert_not_called()
                state.execute.assert_not_called()

    def test_unsafe_owner_group_or_mode_refused_without_receipt(self):
        for part, owner, mode in [('work', (1000, 1001), None),
                                  ('evidence', (1000, 1001), None),
                                  ('leaf', (0, 1001), None),
                                  ('leaf', (1000, 0), None),
                                  ('leaf', None, 0o755),
                                  ('work', None, 0o777),
                                  ('evidence', None, 0o775)]:
            with self.subTest(part=part, owner=owner, mode=mode), fixture() as state:
                path = getattr(state, part)
                if owner is not None:
                    state.owners[path.stat().st_ino] = owner
                if mode is not None:
                    path.chmod(mode)
                with self.assertRaises(RuntimeError):
                    native.launch_owned(ARGS, ENV)
                self.assertEqual(list(state.leaf.iterdir()), [])
                state.overlay.assert_not_called()
                state.execute.assert_not_called()

    def test_existing_receipt_or_backend_log_never_overwritten(self):
        for name in ('startup.jsonl', 'backend.log'):
            for symlink in (False, True):
                with self.subTest(name=name, symlink=symlink), fixture() as state:
                    path = state.leaf / name
                    preserved = state.work / 'preserved'
                    if symlink:
                        preserved.write_bytes(b'PRIVATE_SENTINEL preserved')
                        path.symlink_to(preserved)
                    else:
                        path.write_bytes(b'PRIVATE_SENTINEL preserved')
                    with self.assertRaises(FileExistsError):
                        native.launch_owned(ARGS, ENV)
                    self.assertEqual(path.read_bytes(), b'PRIVATE_SENTINEL preserved')
                    state.execute.assert_not_called()
                    if name == 'startup.jsonl':
                        state.overlay.assert_not_called()
                    else:
                        self.assertEqual(self.records(state)[-1]['exceptionClass'], 'FileExistsError')

    def test_receipt_write_failure_blocks_exec_and_original_error_survives(self):
        with fixture() as state, patch.object(native.os, 'write', side_effect=OSError('PRIVATE_SENTINEL')):
            with self.assertRaises(OSError):
                native.launch_owned(ARGS, ENV)
            state.overlay.assert_not_called()
            state.execute.assert_not_called()
        with fixture() as state:
            original = PermissionError('PRIVATE_SENTINEL')
            state.overlay.side_effect = original
            real_write = os.write
            calls = 0
            def fail_failure_record(fd, raw):
                nonlocal calls
                calls += 1
                if calls == 3:
                    raise OSError('PRIVATE_SENTINEL')
                return real_write(fd, raw)
            with patch.object(native.os, 'write', side_effect=fail_failure_record), \
                    self.assertRaises(PermissionError) as caught:
                native.launch_owned(ARGS, ENV)
            self.assertIs(caught.exception, original)
            state.execute.assert_not_called()


if __name__ == '__main__':
    unittest.main()
