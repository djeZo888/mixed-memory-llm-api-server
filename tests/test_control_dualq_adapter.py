"""Actual ManagerSession placement admission with synthetic owner I/O only."""
from contextlib import nullcontext
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from control.adapter import ManagerSession
from control.catalog import QWEN0_PROFILE, QWEN1_PROFILE
from control.protocol import ControlError, Deadline


class DualQwenAdapterTests(unittest.TestCase):
    def session(self, identifier, port):
        manager = Mock(recovery_only=False)
        manager.deployment.return_value = {
            'id': identifier, '_model': {'repo_id': 'Qwen/Qwen3.8-27B-FP8'},
            'endpoint': {'port': port}}
        return ManagerSession(manager, lambda *_: []), manager

    def test_same_model_instances_preflight_their_exact_physical_target(self):
        for identifier, port, slot in ((QWEN0_PROFILE, 30002, 'glm'),
                                      (QWEN1_PROFILE, 30004, 'qwen')):
            with self.subTest(identifier=identifier):
                session, manager = self.session(identifier, port)
                with patch('control.adapter._lease'), \
                     patch.object(session, '_bounded', return_value=nullcontext()):
                    session.preflight(identifier, object(), Deadline.after(1), slot=slot)
                manager.preflight_slot_admission.assert_called_once_with(manager.deployment.return_value, slot)
                manager.prepare_start.assert_called_once_with(manager.deployment.return_value)
                manager.create_args.assert_called_once_with(manager.deployment.return_value)
                manager.dispatch.assert_not_called()

    def test_same_logical_model_does_not_admit_wrong_physical_slot(self):
        for identifier, port, wrong_slot in ((QWEN0_PROFILE, 30002, 'qwen'),
                                            (QWEN1_PROFILE, 30004, 'glm')):
            session, manager = self.session(identifier, port)
            with self.subTest(identifier=identifier), patch('control.adapter._lease'), \
                 patch.object(session, '_bounded', return_value=nullcontext()), \
                 self.assertRaises(ControlError):
                session.preflight(identifier, object(), Deadline.after(1), slot=wrong_slot)
            manager.preflight_slot_admission.assert_not_called()
            manager.prepare_start.assert_not_called()
            manager.create_args.assert_not_called()
            manager.dispatch.assert_not_called()


if __name__ == '__main__':
    unittest.main()
