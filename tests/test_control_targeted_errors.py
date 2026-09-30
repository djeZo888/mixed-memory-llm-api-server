"""Finite diagnostic-error fixtures; no VM, lifecycle operation or inference."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import sys
import unittest

sys.path.insert(0, str(Path(__file__).parent))
from test_control_fixtures import HTTPHarness
from test_control_slots import PairBackend
from control.protocol import ControlError


class TargetedErrorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.h = HTTPHarness(self.root, backend=PairBackend(self.root))
        self.addCleanup(self.h.close)

    def test_targeted_failed_refresh_preserves_safe_code_and_status_without_publication_or_retry(self):
        before = deepcopy(self.h.app._state)
        calls = list(self.h.backend.calls)
        for code, status in [('stale_state', 409), ('lifecycle_busy', 409), ('deadline_exceeded', 503)]:
            with self.subTest(code=code), patch.object(self.h.app, '_try_refresh', return_value=(status, {'error': {'code': code}})) as refresh:
                for slot in ('glm', 'qwen'):
                    self.assertEqual(self.h.request(path='/control/v1/status/' + slot), (status, {'error': {'code': code}}))
                self.assertEqual(refresh.call_count, 2)  # Exactly once per GET.
            self.assertEqual(self.h.app._state, before)
            self.assertEqual(self.h.backend.calls, calls)

    def test_whole_status_failed_refresh_retains_original_fallback(self):
        for code, status in [('stale_state', 409), ('lifecycle_busy', 409), ('deadline_exceeded', 503)]:
            with self.subTest(code=code), patch.object(self.h.app, '_try_refresh', return_value=(status, {'error': {'code': code}})):
                actual, snapshot = self.h.request()
            self.assertEqual(actual, 200)
            self.assertEqual(snapshot['failure_code'], code)
            self.assertFalse(snapshot['observation_available'])
            self.assertNotEqual(snapshot['observed'], 'ready')

    def test_untrusted_error_content_and_status_are_not_returned(self):
        with patch.object(self.h.app, '_try_refresh', return_value=(599, {'error': {'code': 'PRIVATE_SECRET'}})):
            self.assertEqual(self.h.request(path='/control/v1/status/glm'), (503, {'error': {'code': 'observation_unavailable'}}))
        with patch.object(self.h.app, '_try_refresh', return_value=None), patch.object(self.h.backend, 'open', side_effect=RuntimeError('PRIVATE_SECRET')):
            self.assertEqual(self.h.request(path='/control/v1/status/glm'), (503, {'error': {'code': 'observation_unavailable'}}))

    def test_valid_single_owner_and_unknown_route_keep_genuine_target_errors(self):
        with TemporaryDirectory() as root:
            h = HTTPHarness(Path(root))
            try:
                self.assertEqual(h.request(path='/control/v1/status/glm'), (409, {'error': {'code': 'target_unavailable'}}))
            finally:
                h.close()
        self.assertEqual(self.h.request(path='/control/v1/status/not-a-slot'), (404, {'error': {'code': 'unknown_route'}}))


if __name__ == '__main__':
    unittest.main()
