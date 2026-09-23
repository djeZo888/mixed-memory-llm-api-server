"""Offline regression for the observed systemd UMask=0077 traversal failure."""
from __future__ import annotations

import contextlib
import importlib.util
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest.mock import Mock, call, patch


REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
SPEC = importlib.util.spec_from_file_location(
    "image_runtime_service_permissions", REPO / "scripts/image_runtime/service.py"
)
service = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = service
SPEC.loader.exec_module(service)


class WorkDirectoryPermissions(unittest.TestCase):
    def test_restrictive_systemd_umask_keeps_parents_traversable_and_children_private(self):
        run_id = "a" * 32
        runtime = object.__new__(service.Runtime)
        real_fstat = os.fstat

        def root_owned_metadata(fd):
            # Preserve real filesystem mode/device/inode while allowing a non-root test.
            fields = list(real_fstat(fd))
            fields[4] = 0  # st_uid
            return os.stat_result(fields)

        with tempfile.TemporaryDirectory(prefix="image21-permissions-") as temporary:
            base = Path(temporary)
            anchored = Mock()
            anchored.mkdir.side_effect = lambda relative, mode: (base / relative).mkdir(
                mode=mode, exist_ok=True
            )
            runtime.anchor = Mock(return_value=contextlib.nullcontext(anchored))
            with patch.object(service, "BASE", base), \
                    patch.object(service.os, "fstat", side_effect=root_owned_metadata), \
                    patch.object(service.os, "chown") as chown:
                previous_umask = os.umask(0o077)
                try:
                    runtime.make_work(run_id)
                finally:
                    os.umask(previous_umask)

            for relative in ("work", "work/evidence", "work/tmp"):
                with self.subTest(protected_parent=relative):
                    self.assertEqual(stat.S_IMODE((base / relative).stat().st_mode), 0o755)
            private = ("work/cache", "work/tmp/" + run_id, "work/evidence/" + run_id)
            for relative in private:
                with self.subTest(private_directory=relative):
                    self.assertEqual(stat.S_IMODE((base / relative).stat().st_mode), 0o700)
            self.assertEqual(chown.call_args_list, [
                call(base / relative, service.NATIVE_UID, service.NATIVE_GID)
                for relative in private
            ])


if __name__ == "__main__":
    unittest.main()
