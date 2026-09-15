"""Unprivileged I2SF fixture safety regressions; no actual Linux result claims."""
import contextlib
import errno
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import struct
import subprocess
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

SPEC = importlib.util.spec_from_file_location("i2sf_fixture", Path(__file__).with_name("loop_disk_transaction.py"))
f = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(f)
RECORD = Path("/run/i1s-loop-owned/ownership.json")
LOOP = "/dev/loop9"
DATA = {"root": str(RECORD.parent), "backing": str(RECORD.parent / "backing.img"),
        "backing_inode": 123, "backing_device": os.makedev(0, 40),
        "loop": {"name": LOOP, "rdev": os.makedev(7, 9)}}
ROW = {"name": LOOP, "back-file": DATA["backing"], "back-ino": 123, "back-maj:min": "0:40",
       "maj:min": "7:9", "offset": 0, "sizelimit": 0, "ro": False, "autoclear": False}
SYS = Path("/sys/class/block/loop9")
TARGET = RECORD.parent / "root/dev"
MOUNT = {"id": "100", "parent": "1", "dev": "0:50", "root": "/", "target": str(TARGET),
         "options": "rw,nosuid,noexec,relatime", "optional": [], "fstype": "tmpfs",
         "source": "i2sf-owned-dev", "super_options": "rw,size=1024k,nr_inodes=64,mode=700"}


class FixtureSafety(unittest.TestCase):
    def association_context(self, rows=None, *, backing=DATA["backing"], size=f.SIZE // 512,
                            sector=512, key=None, holders=False):
        stack = contextlib.ExitStack()
        stack.enter_context(patch.object(f, "loop_node", return_value=(key or DATA["loop"], SYS)))
        stack.enter_context(patch.object(f, "active_loops", return_value=[ROW] if rows is None else rows))
        def read(path):
            if path.name == "backing_file":
                if backing is None:
                    raise FileNotFoundError()
                return backing
            return str(sector if path.name == "logical_block_size" else size)
        stack.enter_context(patch.object(f.Path, "read_text", read))
        stack.enter_context(patch.object(f.Path, "iterdir", side_effect=lambda _: iter([Path("holder")] if holders else []), autospec=True))
        return stack

    def test_owned_kernel_backing(self):
        with self.association_context():
            self.assertEqual(f.association(DATA, LOOP)[0], "owned")

    def test_explicit_unbound_name_row_is_never_queried(self):
        # util-linux emits a NAME row for an explicit unbound device. The new
        # active inventory intentionally does not select a device argument.
        with patch.object(f, "execute", return_value='{"loopdevices": []}') as command:
            self.assertEqual(f.active_loops(), [])
        self.assertNotIn(LOOP, command.call_args.args[0])
        self.assertIn("BACK-INO,BACK-MAJ:MIN", command.call_args.args[0][-1])
        with self.association_context([], backing=None, size=0):
            self.assertEqual(f.association(DATA, LOOP)[0], "unbound")

    def test_missing_null_and_incomplete_active_inventory_refuse(self):
        for value in ({}, {"loopdevices": None}, {"loopdevices": [{"name": LOOP}]}):
            with self.subTest(value=value), patch.object(f, "execute", return_value=json.dumps(value)):
                with self.assertRaises(RuntimeError):
                    f.active_loops()

    def test_backing_inode_filesystem_path_and_device_drift_refuse(self):
        for key, value in (("back-ino", 999), ("back-maj:min", "8:1"),
                           ("back-file", "/other.img"), ("maj:min", "7:10")):
            with self.subTest(key=key), self.association_context([dict(ROW, **{key: value})]):
                with self.assertRaises(RuntimeError):
                    f.association(DATA, LOOP)

    def test_duplicate_or_moved_backing_refuses(self):
        for rows in ([ROW, ROW], [dict(ROW, name="/dev/loop10")]):
            with self.subTest(rows=rows), self.association_context(rows):
                with self.assertRaises(RuntimeError):
                    f.association(DATA, LOOP)

    def test_unknown_sysfs_or_recycled_identity_refuses(self):
        for kwargs in ({"backing": "/other.img"}, {"key": dict(DATA["loop"], rdev=os.makedev(7, 10))},
                       {"rows": [], "backing": DATA["backing"]}, {"rows": [], "backing": None, "size": 1}):
            with self.subTest(kwargs=kwargs), self.association_context(**kwargs):
                with self.assertRaises(RuntimeError):
                    f.association(DATA, LOOP)

    def test_geometry_mode_and_busy_checks_retained(self):
        for key, value in (("offset", 1), ("sizelimit", 1024), ("ro", True), ("autoclear", True)):
            with self.subTest(key=key), self.association_context([dict(ROW, **{key: value})]):
                with self.assertRaises(RuntimeError):
                    f.association(DATA, LOOP)
        for kwargs in ({"size": 1}, {"sector": 4096}, {"holders": True}):
            with self.subTest(kwargs=kwargs), self.association_context(**kwargs):
                with self.assertRaises(RuntimeError):
                    f.association(DATA, LOOP)

    def detach_context(self, states, pending=False, mounts=()):
        stack = contextlib.ExitStack()
        stack.enter_context(patch.object(f, "identity", return_value=DATA))
        stack.enter_context(patch.object(f.Path, "exists", return_value=pending))
        stack.enter_context(patch.object(f, "mount_rows", return_value=list(mounts)))
        stack.enter_context(patch.object(f, "association", side_effect=states))
        stack.enter_context(patch.object(f, "owned", return_value=DATA))
        stack.enter_context(patch.object(f, "diagnostic"))
        return stack

    def test_detach_once_then_exact_unbound(self):
        with self.detach_context([("owned", {}), ("unbound", {})]), patch.object(f, "detach_descriptor") as command:
            f.detach_owned(RECORD, LOOP)
        command.assert_called_once_with(RECORD, LOOP)

    def test_detach_descriptor_is_pinned_and_verifies_kernel_identity(self):
        fields = [DATA["backing_device"], 123, 0, 0, 0, 9, 0, 0, 8, b"", b"", b"", 0, 0]
        node = SimpleNamespace(st_mode=stat.S_IFBLK | 0o600, st_rdev=DATA["loop"]["rdev"])
        for index in (None, 0, 1, 3, 4, 5, 8):
            candidate = list(fields)
            if index is not None:
                candidate[index] = 999
            raw = struct.pack("=QQQQQIIII64s64s32sQQ", *candidate)
            with self.subTest(index=index), patch.object(f, "owned", return_value=DATA), \
                    patch.object(f.os, "open", return_value=77) as opened, patch.object(f.os, "fstat", return_value=node), \
                    patch.object(f.os, "close") as closed, patch.object(f.fcntl, "ioctl", side_effect=[raw, 0]) as ioctl, \
                    patch.object(f, "diagnostic"):
                if index is None:
                    f.detach_descriptor(RECORD, LOOP)
                    self.assertEqual(ioctl.call_args_list[-1].args, (77, 0x4C01, 0))
                    self.assertEqual(ioctl.call_count, 2)
                else:
                    with self.assertRaisesRegex(RuntimeError, "backing identity"):
                        f.detach_descriptor(RECORD, LOOP)
                    self.assertEqual(ioctl.call_count, 1)
                self.assertTrue(opened.call_args.args[1] & os.O_NOFOLLOW)
                closed.assert_called_once_with(77)

    def test_already_unbound_never_detaches(self):
        with self.detach_context([("unbound", {}), ("unbound", {})]), patch.object(f, "detach_descriptor", side_effect=AssertionError("detach")):
            f.detach_owned(RECORD, LOOP)

    def test_recycled_after_detach_never_retries(self):
        with self.detach_context([("owned", {}), RuntimeError("recycled")]), patch.object(f, "detach_descriptor") as command:
            with self.assertRaisesRegex(RuntimeError, "recycled"):
                f.detach_owned(RECORD, LOOP)
        command.assert_called_once_with(RECORD, LOOP)

    def test_unknown_identity_pending_producer_or_unexpected_mount_never_detaches(self):
        cases = (([RuntimeError("unknown")], False, ()), ([], True, ()),
                 ([], False, ({"target": DATA["root"] + "/unknown"},)))
        for states, pending, mounts in cases:
            with self.subTest(pending=pending, mounts=mounts), self.detach_context(states, pending, mounts), patch.object(f, "detach_descriptor", side_effect=AssertionError("detach")):
                with self.assertRaises(RuntimeError):
                    f.detach_owned(RECORD, LOOP)

    def test_only_observed_nodev_eacces_with_failed_wipefs_authorizes_mount(self):
        yes = {"containing_mount": {"options": "rw,nosuid,nodev"}, "open_errno": errno.EACCES, "wipefs_returncode": 1}
        self.assertTrue(f.nodev_confirmed(yes))
        for changed in ({"open_errno": errno.EBUSY}, {"open_errno": None}, {"wipefs_returncode": 0},
                        {"containing_mount": {"options": "rw"}}):
            self.assertFalse(f.nodev_confirmed(dict(yes, **changed)))

    def mount_context(self):
        return patch.object(f.Path, "lstat", return_value=SimpleNamespace(st_mode=stat.S_IFDIR | 0o700, st_uid=0))

    def test_device_tmpfs_limits_and_flags(self):
        usage = SimpleNamespace(f_blocks=256, f_frsize=4096, f_files=64)
        with self.mount_context():
            f.validate_dev_mount(MOUNT, TARGET, usage)
            for changed in ({"options": "rw,nodev,nosuid,noexec"}, {"target": "/run"},
                            {"fstype": "ext4"}, {"optional": ["shared:1"]}, {"source": "tmpfs"}):
                with self.subTest(changed=changed), self.assertRaises(RuntimeError):
                    f.validate_dev_mount(dict(MOUNT, **changed), TARGET, usage)
            for usage in (SimpleNamespace(f_blocks=257, f_frsize=4096, f_files=64),
                          SimpleNamespace(f_blocks=256, f_frsize=4096, f_files=65)):
                with self.assertRaises(RuntimeError):
                    f.validate_dev_mount(MOUNT, TARGET, usage)

    def test_replaced_or_stacked_mount_id_refuses(self):
        for rows in ([dict(MOUNT, id="101")], [MOUNT, MOUNT], []):
            with patch.object(f, "mount_rows", return_value=rows), self.assertRaises(RuntimeError):
                f.exact_mount(TARGET, MOUNT)

    def test_wipefs_failure_preserves_errno_rc_path_mount_flags(self):
        node_info = SimpleNamespace(st_mode=stat.S_IFBLK | 0o600, st_rdev=DATA["loop"]["rdev"])
        result = subprocess.CompletedProcess([], 7, "", "wipefs: Permission denied\n")
        with patch.object(f, "owned", return_value=DATA), patch.object(f.Path, "lstat", return_value=node_info), \
                patch.object(f, "containing_mount", return_value=dict(MOUNT, options="rw,nodev")), \
                patch.object(f.os, "open", side_effect=PermissionError(errno.EACCES, "denied")), \
                patch.object(f, "command_result", return_value=result), patch.object(f, "diagnostic") as emit:
            observed = f.probe_node(RECORD, LOOP, "original_before_transaction")
        self.assertEqual(observed["open_errno"], 13)
        self.assertEqual(observed["wipefs_returncode"], 7)
        self.assertEqual((observed["major"], observed["minor"]), (7, 9))
        self.assertEqual(observed["node"], str(TARGET / "loop9"))
        self.assertEqual(emit.call_args.kwargs["wipefs_stderr"], "wipefs: Permission denied\n")

    def test_failed_signature_is_never_empty_success(self):
        with patch.object(f, "command_result", return_value=subprocess.CompletedProcess([], 5, '{"signatures": []}', "denied")), patch.object(f, "diagnostic"):
            with self.assertRaisesRegex(RuntimeError, "rc=5"):
                f.execute(["wipefs", "--no-act", str(TARGET / "loop9")])

    def test_malformed_success_signature_refuses(self):
        node_info = SimpleNamespace(st_mode=stat.S_IFBLK | 0o600, st_rdev=DATA["loop"]["rdev"])
        with patch.object(f, "owned", return_value=DATA), patch.object(f.Path, "lstat", return_value=node_info), \
                patch.object(f, "containing_mount", return_value=MOUNT), patch.object(f.os, "open", return_value=10), \
                patch.object(f.os, "fstat", return_value=node_info), patch.object(f.os, "close"), \
                patch.object(f, "command_result", return_value=subprocess.CompletedProcess([], 0, '{}', '')), patch.object(f, "diagnostic"):
            with self.assertRaisesRegex(RuntimeError, "signature discovery incomplete"):
                f.probe_node(RECORD, LOOP, "before")

    def test_prepare_refuses_unexplained_failure_without_mount(self):
        observation = {"containing_mount": {"options": "rw"}, "open_errno": errno.EACCES, "wipefs_returncode": 1}
        with patch.object(f, "owned", return_value=dict(DATA)), patch.object(f.Path, "mkdir"), \
                patch.object(f.Path, "iterdir", return_value=iter([])), patch.object(f, "sync_nodes"), \
                patch.object(f, "probe_node", return_value=observation), patch.object(f, "execute", side_effect=AssertionError("mount")):
            with self.assertRaisesRegex(RuntimeError, "no transaction"):
                f.prepare_devices(RECORD, LOOP)

    def test_confirmed_nodev_mounts_only_tiny_exact_owned_target_then_reprobes(self):
        before = {"containing_mount": {"options": "rw,nodev"}, "open_errno": errno.EACCES, "wipefs_returncode": 1}
        after = {"containing_mount": MOUNT, "open_errno": None, "wipefs_returncode": 0}
        with patch.object(f, "owned", return_value=dict(DATA)), patch.object(f.Path, "mkdir"), \
                patch.object(f.Path, "iterdir", return_value=iter([])), patch.object(f, "sync_nodes"), \
                patch.object(f, "probe_node", side_effect=[before, after]) as probes, \
                patch.dict(f.os.environ, {"I1S_FIXTURE_PARENT_NAMESPACE": "mnt:parent"}), \
                patch.object(f.os, "readlink", return_value="mnt:child"), patch.object(f, "mount_rows", return_value=[]), \
                patch.object(f, "execute", side_effect=["private", ""]) as command, \
                patch.object(f, "containing_mount", return_value=MOUNT), patch.object(f, "update_identity"), \
                patch.object(f, "check_dev_mount"), patch.object(f, "diagnostic"):
            f.prepare_devices(RECORD, LOOP)
        self.assertEqual(command.call_args_list[-1].args[0],
                         ["mount", "-t", "tmpfs", "-o", "rw,nosuid,noexec,mode=0700,size=1M,nr_inodes=64",
                          "i2sf-owned-dev", str(TARGET)])
        self.assertEqual(probes.call_count, 2)

    def test_command_timeout_or_surviving_producer_retains_uncertainty(self):
        for timeout in (True, False):
            process = Mock(pid=123, returncode=0)
            process.communicate.side_effect = subprocess.TimeoutExpired("owned-tool", 30) if timeout else None
            process.communicate.return_value = ("", "")
            with self.subTest(timeout=timeout), patch.object(f, "PRODUCERS_UNCERTAIN", False), \
                    patch.object(f.subprocess, "Popen", return_value=process), patch.object(f.os, "killpg"):
                with self.assertRaises((RuntimeError, subprocess.TimeoutExpired)):
                    f.command_result(["owned-tool"])
                self.assertTrue(f.PRODUCERS_UNCERTAIN)
                process.kill.assert_not_called()

    def test_sanitized_errors_are_bounded(self):
        result = f.sanitized_error("token=private\x00\n" + "x" * 5000)
        self.assertNotIn("private", result)
        self.assertNotIn("\x00", result)
        self.assertLess(len(result), 2100)

    def test_shell_has_no_external_device_option(self):
        script = Path(__file__).with_name("loop_disk_transaction.sh")
        result = subprocess.run(["bash", str(script), "--dry-run", "/dev/sdb"], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 2)

    def test_pending_producer_cannot_be_removed(self):
        with patch.object(f, "identity", return_value=DATA), patch.object(f.Path, "exists", return_value=True), \
                patch.object(f, "active_loops", side_effect=AssertionError("inventory")), \
                patch.object(f.shutil, "rmtree", side_effect=AssertionError("remove")):
            with self.assertRaisesRegex(RuntimeError, "producer lifetime"):
                f.remove_owned(RECORD)


if __name__ == "__main__":
    unittest.main()
