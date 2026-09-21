"""Local safety/refusal checks only; none invokes a host Linux device tool."""

import importlib.util
import os
from pathlib import Path
import stat
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


MODULE = Path(__file__).resolve().parents[2] / "scripts/validation/i2p/loop_probe.py"
SPEC = importlib.util.spec_from_file_location("i2p_loop_probe", MODULE)
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)


class LoopSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name).resolve()

    def tearDown(self):
        self.temporary.cleanup()

    def test_dry_run_is_pure_and_bounded(self):
        with patch.object(probe.os, "open", side_effect=AssertionError("dry run wrote a file")), patch.object(probe.subprocess, "run", side_effect=AssertionError("dry run ran a command")):
            result = probe.plan("i2p-0123456789abcdef")
        self.assertEqual(result["mode"], "DRY_RUN")
        self.assertEqual(result["logical_bytes"], 64 * 1024 * 1024)

    def test_run_id_cannot_be_path_or_unit_injection(self):
        for value in ("../i2p-01234567", "i2p-01234567/extra", "i2p-01234567\n", "i2p-deadbeef;id", "i2p-123", "i2p-DEADBEEF"):
            with self.subTest(value=value), self.assertRaises(probe.LoopSafetyError):
                probe.plan(value)

    def test_existing_backing_is_never_truncated(self):
        path = self.directory / "existing.img"
        path.write_bytes(b"preserve-existing")
        with self.assertRaises(FileExistsError):
            probe._create_backing(path)
        self.assertEqual(path.read_bytes(), b"preserve-existing")

    def test_symlink_backing_is_never_followed(self):
        target = self.directory / "sentinel"
        target.write_bytes(b"do-not-change")
        link = self.directory / "backing.img"
        link.symlink_to(target)
        with self.assertRaises(OSError):
            probe._create_backing(link)
        self.assertEqual(target.read_bytes(), b"do-not-change")

    def test_backing_hardlink_refused(self):
        path = self.directory / "backing.img"
        fd, expected = probe._create_backing(path)
        try:
            os.link(path, self.directory / "second-link")
            with self.assertRaisesRegex(probe.LoopSafetyError, "one link"):
                probe._backing_identity(path, expected)
        finally:
            os.close(fd)

    def test_replaced_backing_inode_refused(self):
        path = self.directory / "backing.img"
        fd, expected = probe._create_backing(path)
        try:
            path.rename(self.directory / "old.img")
            replacement_fd, _ = probe._create_backing(path)
            os.close(replacement_fd)
            with self.assertRaisesRegex(probe.LoopSafetyError, "inode"):
                probe._backing_identity(path, expected)
        finally:
            os.close(fd)

    def test_backing_permission_change_refused(self):
        path = self.directory / "backing.img"
        fd, expected = probe._create_backing(path)
        try:
            path.chmod(0o644)
            with self.assertRaisesRegex(probe.LoopSafetyError, "private mode"):
                probe._backing_identity(path, expected)
        finally:
            os.close(fd)

    def test_non_loop_names_never_reach_a_command(self):
        with patch.object(probe, "_json_cmd", side_effect=AssertionError("invalid device reached command")):
            for device in ("/dev/sdb", "/dev/nvme0n1", "/dev/loop0p1", "/dev/loop0\n", "/dev/loop/by-id/x", ""):
                with self.subTest(device=device), self.assertRaises(probe.LoopSafetyError):
                    probe._loop_info(device)

    def test_existing_signature_refused_with_read_only_probe(self):
        with patch.object(probe, "_json_cmd", return_value={"signatures": [{"type": "ext4", "uuid": "not-our-new-uuid"}]}) as command:
            with self.assertRaisesRegex(probe.LoopSafetyError, "existing signatures"):
                probe._blank("/dev/loop9")
        self.assertEqual(command.call_args.args[0], ["wipefs", "--no-act", "--json", "--output", "TYPE,UUID", "/dev/loop9"])

    def test_backing_inode_mismatch_stops_before_sysfs_or_mutation(self):
        path = self.directory / "backing.img"
        expected = SimpleNamespace(st_ino=100, st_dev=os.makedev(8, 1))
        loop_stat = SimpleNamespace(st_mode=stat.S_IFBLK | 0o600, st_rdev=os.makedev(7, 9))
        row = {"name": "/dev/loop9", "maj:min": "7:9", "back-file": str(path), "back-ino": 101, "back-maj:min": "8:1"}
        with patch.object(probe, "_backing_identity"), patch.object(probe.os, "fstat", return_value=loop_stat), patch.object(probe.os, "lstat", return_value=loop_stat), patch.object(probe, "_loop_info", return_value=[row]):
            with self.assertRaisesRegex(probe.LoopSafetyError, "backing path, inode"):
                probe._loop_identity("/dev/loop9", path, expected, 123)

    def test_root_ancestry_includes_partition_parent(self):
        sysroot = self.directory / "sys-block"
        sysroot.mkdir()
        disk = self.directory / "disk"
        disk.mkdir()
        (disk / "dev").write_text("8:0\n")
        (disk / "slaves").mkdir()
        partition = disk / "partition-one"
        partition.mkdir()
        (partition / "dev").write_text("8:1\n")
        (partition / "partition").write_text("1\n")
        (sysroot / "8:0").symlink_to(disk)
        (sysroot / "8:1").symlink_to(partition)
        with patch.object(probe, "SYS_BLOCK", sysroot), patch.object(probe, "_mounts", return_value=[{"target": "/", "maj:min": "8:1"}]):
            self.assertEqual(probe._root_ancestry(), {"8:0", "8:1"})

    def test_root_device_never_passes_format_preconditions(self):
        with patch.object(probe, "_root_ancestry", return_value={"7:9"}), patch.object(probe, "_mounts", side_effect=AssertionError("must reject root first")):
            with self.assertRaisesRegex(probe.LoopSafetyError, "root-device ancestry"):
                probe._unmounted_and_unstacked("7:9", Path("/not-accessed"))

    def test_mounted_loop_refused(self):
        with patch.object(probe, "_root_ancestry", return_value={"8:1"}), patch.object(probe, "_mounts", return_value=[{"maj:min": "7:9", "target": "/somewhere"}]):
            with self.assertRaisesRegex(probe.LoopSafetyError, "is mounted"):
                probe._unmounted_and_unstacked("7:9", Path("/not-accessed"))

    def test_changed_mount_uuid_refuses_unmount(self):
        mountdir = self.directory / "mount"
        row = {"id": 88, "source": "/dev/loop9", "target": str(mountdir), "maj:min": "7:9", "fstype": "ext4", "uuid": "other-uuid"}
        with patch.object(probe, "_json_cmd", return_value={"filesystems": [row]}):
            with self.assertRaisesRegex(probe.LoopSafetyError, "UUID differs"):
                probe._mount_identity(mountdir, "/dev/loop9", "7:9", "expected-uuid", 88)

    def test_changed_mount_id_refuses_unmount(self):
        mountdir = self.directory / "mount"
        row = {"id": 89, "source": "/dev/loop9", "target": str(mountdir), "maj:min": "7:9", "fstype": "ext4", "uuid": "expected-uuid"}
        with patch.object(probe, "_json_cmd", return_value={"filesystems": [row]}):
            with self.assertRaisesRegex(probe.LoopSafetyError, "mount ID changed"):
                probe._mount_identity(mountdir, "/dev/loop9", "7:9", "expected-uuid", 88)

    def test_detached_recycled_loop_is_observed_without_detach(self):
        with patch.object(probe, "_loop_info", return_value=[{"back-file": "/unrelated/recycled.img"}]), patch.object(probe, "_cmd", side_effect=AssertionError("must not detach a recycled loop")):
            self.assertTrue(probe._detached("/dev/loop9", self.directory / "owned.img"))

    def test_command_does_not_inherit_credentials_or_echo_errors(self):
        completed = subprocess.CompletedProcess(["known-tool"], 1, stdout="private output", stderr="private error")
        with patch.object(probe.subprocess, "run", return_value=completed) as command, self.assertRaises(probe.LoopSafetyError) as failure:
            probe._cmd(["known-tool"])
        self.assertNotIn("private", str(failure.exception))
        self.assertEqual(command.call_args.kwargs["env"], {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C"})
        self.assertEqual(command.call_args.kwargs["timeout"], 30)

    def test_mac_live_run_refuses_before_device_commands(self):
        with patch.object(probe.platform, "system", return_value="Darwin"), patch.object(probe, "_cmd", side_effect=AssertionError("must refuse before any guest command")), self.assertRaisesRegex(probe.LoopSafetyError, "Linux amd64"):
            probe.run(self.directory, "i2p-0123456789abcdef")
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_uncertain_allocation_never_claims_cleanup_or_detaches(self):
        def fail_allocation(args, **kwargs):
            self.assertEqual(args[:4], ["losetup", "--find", "--show", "--nooverlap"])
            raise probe.LoopSafetyError("A bounded guest command could not complete")

        with patch.object(probe, "_environment", return_value=self.directory), patch.object(probe, "_cmd", side_effect=fail_allocation) as command:
            result = probe.run(self.directory, "i2p-0123456789abcdef")
        self.assertEqual(command.call_count, 1)
        self.assertEqual(result["status"], "FAIL")
        self.assertFalse(result["cleanup"]["detached"])
        self.assertFalse(result["cleanup"]["unmounted"])
        self.assertEqual(result["cleanup"]["allocation_identity"], "UNKNOWN")
        self.assertTrue((self.directory / "i2p-0123456789abcdef-blank.img").exists())

    def test_recycled_association_prevents_format_and_cleanup_detach(self):
        real_open = os.open

        def loop_open(path, *args, **kwargs):
            if path == "/dev/loop9":
                return real_open(self.directory / "i2p-0123456789abcdef-blank.img", os.O_RDWR)
            return real_open(path, *args, **kwargs)

        completed = subprocess.CompletedProcess([], 0, stdout="/dev/loop9\n", stderr="")
        with patch.object(probe, "_environment", return_value=self.directory), patch.object(probe, "_cmd", return_value=completed) as command, patch.object(probe.os, "open", side_effect=loop_open), patch.object(probe, "_loop_identity", side_effect=probe.LoopSafetyError("Loop backing path, inode, or filesystem does not match the exclusive file")):
            result = probe.run(self.directory, "i2p-0123456789abcdef")
        self.assertEqual(command.call_count, 1)
        self.assertEqual(result["status"], "FAIL")
        self.assertFalse(result["cleanup"]["detached"])
        self.assertIn("Loop backing", result["cleanup"]["error"])


if __name__ == "__main__":
    unittest.main()
