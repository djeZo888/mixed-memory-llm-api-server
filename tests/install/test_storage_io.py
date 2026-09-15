"""Real local-FS tests plus optional isolated Linux mount-namespace detach test.

Run: python3 -B -m unittest discover -s tests/install -p test_storage_io.py -v
The mount test only executes in a new private namespace with CAP_SYS_ADMIN;
it mounts a disposable 16 MiB tmpfs and never uses a host block device.
"""
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
from install import storage_io as io


def snapshot(path):
    info = path.stat()
    identity = {"path": str(path), "mount": str(path), "uuid": "synthetic-storage-uuid",
                "fstype": "ext4", "device": f"{os.major(info.st_dev)}:{os.minor(info.st_dev)}"}
    return {"schema_version": 1, "data": dict(identity), "models": dict(identity),
            "roots": {"models": str(path), "state": str(path)}}


class Guard:
    def __init__(self, path):
        self.value = snapshot(path)
        self.calls, self.lost = 0, False

    def __call__(self):
        self.calls += 1
        if self.lost:
            raise io.StorageIOError("fixture_mount_lost")
        return copy.deepcopy(self.value)


class StorageIOTests(unittest.TestCase):
    def setUp(self):
        # Do not bypass protected ancestry checks for /tmp. This source checkout
        # is already required to be a protected installer input.
        self.tmp = tempfile.TemporaryDirectory(prefix=".storage-io-test-", dir=REPO)
        self.path = Path(self.tmp.name)
        self.guard = Guard(self.path)
        self.root = io.AnchoredRoot(str(self.path), self.guard, uid=os.geteuid())

    def tearDown(self):
        self.root.close()
        self.tmp.cleanup()

    def write(self, relative, data):
        with self.root.open(relative, os.O_RDWR | os.O_CREAT | os.O_EXCL) as stream:
            stream.write(data)
            stream.fsync()

    def test_create_read_seek_truncate_and_child_directory(self):
        self.root.mkdir("models/nested")
        with self.root.directory("models/nested") as child:
            with child.open("partial", os.O_RDWR | os.O_CREAT) as stream:
                self.assertEqual(stream.write(b"abcdef"), 6)
                stream.seek(2)
                self.assertEqual(stream.read(2), b"cd")
                stream.truncate(4)
                stream.fsync()
                self.assertEqual(stream.stat().st_size, 4)
        self.assertEqual((self.path / "models/nested/partial").read_bytes(), b"abcd")

    def test_atomic_json_private_durable_and_replaces_old_version(self):
        self.root.mkdir("state")
        self.root.atomic_json("state/progress.json", {"complete": ["one"]})
        first = self.root.stat("state/progress.json").st_ino
        self.root.atomic_json("state/progress.json", {"complete": ["one", "two"]})
        self.assertEqual(self.root.read_json("state/progress.json"), {"complete": ["one", "two"]})
        self.assertEqual(self.root.stat("state/progress.json").st_mode & 0o777, 0o600)
        self.assertNotEqual(first, self.root.stat("state/progress.json").st_ino)
        self.assertEqual(sorted(path.name for path in (self.path / "state").iterdir()), ["progress.json"])

    def test_atomic_json_interruption_preserves_previous_and_resume(self):
        self.root.atomic_json("progress.json", {"complete": ["one"]})
        with patch.object(self.root, "replace", side_effect=InterruptedError):
            with self.assertRaises(InterruptedError):
                self.root.atomic_json("progress.json", {"complete": ["one", "two"]})
        self.assertEqual(self.root.read_json("progress.json"), {"complete": ["one"]})
        self.root.atomic_json("progress.json", {"complete": ["one", "two"]})
        self.assertEqual(self.root.read_json("progress.json")["complete"], ["one", "two"])

    def test_mount_loss_preserves_old_state_without_error_fallback(self):
        self.root.atomic_json("state.json", {"complete": ["one"]})
        original = self.root.replace

        def lose_mount(*args):
            self.guard.lost = True
            return original(*args)

        with patch.object(self.root, "replace", side_effect=lose_mount):
            with self.assertRaisesRegex(io.StorageIOError, "fixture_mount_lost"):
                self.root.atomic_json("state.json", {"complete": ["two"]})
        self.assertEqual(json.loads((self.path / "state.json").read_text()), {"complete": ["one"]})
        self.assertTrue(list(self.path.glob(".installer-*")))

    def test_mutations_and_reads_fail_on_guard_loss(self):
        self.write("partial", b"saved")
        self.guard.lost = True
        operations = [lambda: self.root.mkdir("new"), lambda: self.root.open("new", os.O_CREAT | os.O_WRONLY),
                      lambda: self.root.unlink("partial"), lambda: self.root.replace("partial", "complete"),
                      lambda: self.root.atomic_json("state", {}), lambda: self.root.stat("partial")]
        for operation in operations:
            with self.assertRaisesRegex(io.StorageIOError, "fixture_mount_lost"):
                operation()
        self.assertEqual((self.path / "partial").read_bytes(), b"saved")
        self.assertEqual([path.name for path in self.path.iterdir()], ["partial"])

    def test_guard_rechecked_between_each_bounded_write(self):
        actual_write, calls = os.write, []

        def lose_mount_after_write(fd, data):
            calls.append(len(data))
            result = actual_write(fd, data)
            self.guard.lost = True
            return result

        with self.root.open("partial", os.O_CREAT | os.O_WRONLY) as stream:
            with patch.object(io.os, "write", side_effect=lose_mount_after_write):
                with self.assertRaisesRegex(io.StorageIOError, "fixture_mount_lost"):
                    stream.write(b"x" * (2 * io.MAX_CHUNK + 9))
        self.assertEqual(calls, [io.MAX_CHUNK])
        self.assertEqual((self.path / "partial").stat().st_size, io.MAX_CHUNK)

    def test_short_writes_are_retried_without_data_loss(self):
        actual_write, calls = os.write, []

        def short_write(fd, data):
            calls.append(len(data))
            return actual_write(fd, data[:3])

        with patch.object(io.os, "write", side_effect=short_write):
            self.write("partial", b"abcdefghi")
        self.assertEqual((self.path / "partial").read_bytes(), b"abcdefghi")
        self.assertEqual(calls, [9, 6, 3])

    def test_registration_identity_drift_rejected_even_same_device(self):
        self.guard.value["data"]["uuid"] = "changed-uuid"
        with self.assertRaisesRegex(io.StorageIOError, "registered_storage_identity_changed"):
            self.root.mkdir("forbidden")
        self.assertFalse((self.path / "forbidden").exists())

    def test_guard_cannot_attest_wrong_descriptor_device(self):
        self.guard.value["models"]["device"] = "7:123"
        with self.assertRaisesRegex(io.StorageIOError, "storage_anchor_device_mismatch"):
            self.root.check()

    def test_constructor_rejects_guard_device_mismatch_before_any_write(self):
        bad = Guard(self.path)
        bad.value["models"]["device"] = "7:123"
        with self.assertRaisesRegex(io.StorageIOError, "storage_anchor_device_mismatch"):
            io.AnchoredRoot(str(self.path), bad, uid=os.geteuid())
        self.assertEqual(list(self.path.iterdir()), [])

    def test_capacity_and_device_observation_metadata_not_identity(self):
        self.guard.value["capacity"] = {"data_available_bytes": 123}
        self.guard.value["data"]["source"] = "/dev/fixture-renumbered"
        self.root.check()

    def test_ancestor_replacement_rejected_despite_stale_guard(self):
        self.root.mkdir("parent/child")
        with self.root.directory("parent/child") as child:
            os.rename(self.path / "parent", self.path / "old-parent")
            (self.path / "parent/child").mkdir(parents=True)
            with self.assertRaisesRegex(io.StorageIOError, "storage_directory_detached_or_replaced"):
                child.open("payload", os.O_CREAT | os.O_WRONLY)
        self.assertFalse((self.path / "parent/child/payload").exists())
        self.assertFalse((self.path / "old-parent/child/payload").exists())

    def test_held_file_parent_replaced_during_write_is_detected(self):
        self.root.mkdir("parent")
        with self.root.open("parent/partial", os.O_CREAT | os.O_WRONLY) as stream:
            stream.write(b"preserved")
            os.rename(self.path / "parent", self.path / "old-parent")
            (self.path / "parent").mkdir()
            with self.assertRaisesRegex(io.StorageIOError, "storage_directory_detached_or_replaced"):
                stream.write(b"forbidden")
        self.assertFalse((self.path / "parent/partial").exists())
        self.assertEqual((self.path / "old-parent/partial").read_bytes(), b"preserved")

    def test_write_race_after_guard_stays_on_held_directory(self):
        self.root.mkdir("parent")
        actual_write = os.write
        with self.root.open("parent/partial", os.O_CREAT | os.O_WRONLY) as stream:
            def exchange_then_write(fd, data):
                os.rename(self.path / "parent", self.path / "old-parent")
                (self.path / "parent").mkdir()
                return actual_write(fd, data)

            with patch.object(io.os, "write", side_effect=exchange_then_write):
                with self.assertRaisesRegex(io.StorageIOError, "storage_directory_detached_or_replaced"):
                    stream.write(b"anchored")
        self.assertFalse((self.path / "parent/partial").exists())
        self.assertEqual((self.path / "old-parent/partial").read_bytes(), b"anchored")

    def test_symlink_ancestry_and_file_symlinks_refused(self):
        self.root.mkdir("real")
        (self.path / "alias").symlink_to(self.path / "real", target_is_directory=True)
        (self.path / "link").symlink_to(self.path / "real/file")
        for name in ("alias/file", "link"):
            with self.assertRaises((OSError, io.StorageIOError)):
                self.root.open(name, os.O_CREAT | os.O_WRONLY)
        with self.assertRaises((OSError, io.StorageIOError)):
            self.root.directory("alias")
        self.assertFalse((self.path / "real/file").exists())

    def test_hardlink_truncate_and_replace_rejected_without_changing_bytes(self):
        self.write("original", b"saved")
        os.link(self.path / "original", self.path / "alias")
        with self.assertRaisesRegex(io.StorageIOError, "hardlink"):
            self.root.open("alias", os.O_WRONLY | os.O_TRUNC)
        self.write("replacement", b"other")
        with self.assertRaisesRegex(io.StorageIOError, "hardlink"):
            self.root.replace("replacement", "alias")
        self.assertEqual((self.path / "original").read_bytes(), b"saved")
        self.assertEqual((self.path / "replacement").read_bytes(), b"other")

    def test_file_or_parent_permission_drift_rejected(self):
        self.root.mkdir("parent")
        self.write("parent/file", b"saved")
        (self.path / "parent/file").chmod(0o666)
        with self.assertRaisesRegex(io.StorageIOError, "owner_or_mode"):
            self.root.open("parent/file", os.O_WRONLY | os.O_TRUNC)
        (self.path / "parent/file").chmod(0o600)
        (self.path / "parent").chmod(0o777)
        with self.assertRaisesRegex(io.StorageIOError, "owner_or_mode"):
            self.root.unlink("parent/file")
        self.assertEqual((self.path / "parent/file").read_bytes(), b"saved")

    def test_fifo_open_does_not_block_and_is_rejected(self):
        os.mkfifo(self.path / "fifo", 0o600)
        with self.assertRaises((OSError, io.StorageIOError)):
            self.root.open("fifo")

    def test_relative_traversal_and_unsafe_create_modes_refused(self):
        for relative in ("", "/absolute", "../outside", "a/../outside", "a//b", "a/./b", "a/"):
            with self.assertRaisesRegex(io.StorageIOError, "relative_path"):
                self.root.open(relative, os.O_CREAT | os.O_WRONLY)
        with self.assertRaises(io.StorageIOError):
            self.root.mkdir("bad", mode=0o777)
        with self.assertRaises(io.StorageIOError):
            self.root.open("bad", os.O_CREAT | os.O_WRONLY, mode=0o666)
        self.assertEqual(list(self.path.iterdir()), [])

    def test_json_requires_private_regular_bounded_object(self):
        self.write("public.json", b"{}")
        (self.path / "public.json").chmod(0o644)
        with self.assertRaisesRegex(io.StorageIOError, "owner_or_mode"):
            self.root.read_json("public.json")
        self.write("list.json", b"[]")
        with self.assertRaisesRegex(io.StorageIOError, "invalid_storage_json"):
            self.root.read_json("list.json")
        self.write("large.json", b"{" + b"x" * 10)
        with self.assertRaisesRegex(io.StorageIOError, "too_large"):
            self.root.read_json("large.json", max_bytes=5)

    def test_atomic_promotion_and_unlink(self):
        self.root.mkdir("partial")
        self.root.mkdir("complete")
        self.write("partial/file", b"verified-content")
        self.root.replace("partial/file", "complete/file")
        self.assertIsNone(self.root.stat("partial/file", missing_ok=True))
        self.assertEqual((self.path / "complete/file").read_bytes(), b"verified-content")
        self.root.unlink("complete/file")
        self.root.unlink("complete/file", missing_ok=True)
        self.assertFalse((self.path / "complete/file").exists())

    def test_stat_missing_parent_returns_none_and_does_not_create(self):
        self.assertIsNone(self.root.stat("not/created/state.json", missing_ok=True))
        self.assertFalse((self.path / "not").exists())

    def test_exact_registered_data_path_may_be_anchored(self):
        value = snapshot(self.path)
        value["roots"] = {"models": str(self.path / "models")}
        with io.AnchoredRoot(str(self.path), lambda: value, uid=os.geteuid()) as root:
            root.mkdir("models")
            self.assertEqual(root.proc_path("models"), f"/proc/{os.getpid()}/fd/{root.fileno()}/models")

    def test_closed_anchor_refuses_use(self):
        self.root.close()
        self.root.close()
        with self.assertRaisesRegex(io.StorageIOError, "storage_anchor_closed"):
            self.root.fileno()

    def test_actual_linux_lazy_unmount_during_write(self):
        if not sys.platform.startswith("linux") or not shutil.which("unshare"):
            self.skipTest("actual mount-loss NOT_TESTED: needs Linux and unshare/CAP_SYS_ADMIN")
        probe = subprocess.run(["unshare", "--mount", "--propagation", "private", "true"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        if probe.returncode:
            self.skipTest("actual mount-loss NOT_TESTED: disposable private mount namespace unavailable")
        result = subprocess.run(["unshare", "--mount", "--propagation", "private", sys.executable,
                                 "-B", str(Path(__file__).resolve()), "--mount-loss-child", str(self.path)],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=30, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {"actual_mount_loss": "PASS", "root_fallthrough": False})


class MountedStorageGuardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix=".mount-guard-test-", dir=REPO)
        self.base = Path(self.tmp.name)
        self.data = self.base / "disk"
        self.data.mkdir(mode=0o700)
        (self.data / "build").mkdir(mode=0o700)
        self.registry = self.base / "etc/local-ai-server/storage.json"
        self.registry.parent.mkdir(mode=0o700, parents=True)
        value = snapshot(self.data)
        value["roots"]["build"] = str(self.data / "build")

        class StorageFixture:
            owner = os.geteuid()
            system_root = self.base
            calls = 0

            def guard(storage):
                storage.calls += 1
                return copy.deepcopy(value)

        self.storage = StorageFixture()
        self.value = value
        self.registry.write_text(json.dumps(value))
        self.registry.chmod(0o600)
        self.mountinfo = ("1 0 0:1 / / rw - ext4 /dev/fixture-root rw\n"
                          f"2 1 {value['data']['device']} / {self.data} rw,relatime - ext4 /dev/fixture-data rw\n")
        self.guard = io.MountedStorageGuard(self.storage, mountinfo_reader=lambda: self.mountinfo)

    def tearDown(self):
        self.guard.close()
        self.tmp.cleanup()

    def test_no_subprocess_or_full_storage_check_per_chunk(self):
        for _ in range(5):
            self.assertEqual(self.guard()["data"]["uuid"], "synthetic-storage-uuid")
        self.assertEqual(self.storage.calls, 1)
        self.value["capacity"] = {"data_available_bytes": 321}
        self.assertNotIn("capacity", self.guard())
        self.assertEqual(self.guard.verify_full()["capacity"]["data_available_bytes"], 321)
        self.assertEqual(self.storage.calls, 2)

    def test_missing_mount_rejected_without_full_guard(self):
        self.mountinfo = self.mountinfo.splitlines()[0] + "\n"
        with self.assertRaisesRegex(io.StorageIOError, "registered_storage_mount_changed"):
            self.guard()
        self.assertEqual(self.storage.calls, 1)

    def test_same_device_replacement_mount_id_rejected(self):
        self.mountinfo = self.mountinfo.replace("2 1 ", "9 1 ")
        with self.assertRaisesRegex(io.StorageIOError, "mount_identity_changed"):
            self.guard()

    def test_new_nested_bind_mount_rejected_even_on_same_device(self):
        self.mountinfo += (f"3 2 {self.value['data']['device']} /elsewhere {self.data}/build rw "
                           "- ext4 /dev/fixture-data rw\n")
        with self.assertRaisesRegex(io.StorageIOError, "registered_storage_mount_changed"):
            self.guard()

    def test_read_only_mount_change_rejected(self):
        self.mountinfo = self.mountinfo.replace("rw,relatime", "ro,relatime")
        with self.assertRaisesRegex(io.StorageIOError, "mount_identity_changed"):
            self.guard()

    def test_unrelated_mount_does_not_invalidate(self):
        self.mountinfo += "4 1 0:4 / /unrelated rw - tmpfs fixture rw\n"
        self.guard()

    def test_registry_byte_drift_rejected_with_same_inode(self):
        value = self.registry.read_text()
        self.registry.write_text(value.replace("synthetic-storage-uuid", "different-storage-uuid"))
        with self.assertRaisesRegex(io.StorageIOError, "bytes_changed"):
            self.guard()

    def test_registry_replacement_with_identical_bytes_rejected(self):
        value = self.registry.read_bytes()
        self.registry.rename(self.registry.with_suffix(".old"))
        self.registry.write_bytes(value)
        self.registry.chmod(0o600)
        with self.assertRaisesRegex(io.StorageIOError, "file_changed"):
            self.guard()

    def test_registry_mode_drift_rejected(self):
        self.registry.chmod(0o644)
        with self.assertRaisesRegex(io.StorageIOError, "owner_or_mode"):
            self.guard()

    def test_registry_ancestor_replacement_rejected(self):
        self.registry.parent.rename(self.registry.parent.with_name("old-registry"))
        self.registry.parent.mkdir(mode=0o700)
        with self.assertRaisesRegex(io.StorageIOError, "path_changed"):
            self.guard()

    def test_malformed_or_ambiguous_mountinfo_rejected(self):
        original = self.mountinfo
        for value in ("", "malformed\n", original + original.splitlines()[1] + "\n"):
            self.mountinfo = value
            with self.assertRaises(io.StorageIOError):
                self.guard()

    def test_guarded_write_detects_mount_loss_through_fast_guard(self):
        with io.AnchoredRoot(str(self.data), self.guard, uid=os.geteuid()) as root:
            with root.open("partial", os.O_CREAT | os.O_WRONLY) as stream:
                stream.write(b"first")
                self.mountinfo = self.mountinfo.splitlines()[0] + "\n"
                with self.assertRaisesRegex(io.StorageIOError, "mount_changed"):
                    stream.write(b"forbidden")
        self.assertEqual((self.data / "partial").read_bytes(), b"first")

    def test_closed_guard_refuses_use(self):
        self.guard.close()
        self.guard.close()
        with self.assertRaisesRegex(io.StorageIOError, "storage_guard_closed"):
            self.guard()


def mount_loss_child(base):
    """Called only after successful unshare probe, never in host mount namespace."""
    base = Path(base)
    mount = base / "disposable-mount"
    mount.mkdir(mode=0o700)
    (mount / "underlying-marker").write_bytes(b"root-unchanged")
    subprocess.run(["mount", "-t", "tmpfs", "-o", "size=16m,mode=0700", "tmpfs", str(mount)], check=True)
    try:
        # Intentionally stale verifier exercises independent descriptor identity
        # detection. Detach occurs after the pre-write check, inside os.write.
        guard = Guard(mount)
        actual_write = os.write
        with io.AnchoredRoot(str(mount), guard, uid=os.geteuid()) as root:
            root.mkdir("files")
            with root.open("files/partial", os.O_CREAT | os.O_WRONLY) as stream:
                def detach_then_write(fd, data):
                    subprocess.run(["umount", "--lazy", str(mount)], check=True)
                    return actual_write(fd, data)

                with patch.object(io.os, "write", side_effect=detach_then_write):
                    try:
                        stream.write(b"stays-on-detached-filesystem")
                    except io.StorageIOError as exc:
                        assert exc.code == "storage_directory_detached_or_replaced", exc.code
                    else:
                        raise AssertionError("detached mount was not detected")
        assert not (mount / "files").exists()
        assert (mount / "underlying-marker").read_bytes() == b"root-unchanged"
        print(json.dumps({"actual_mount_loss": "PASS", "root_fallthrough": False}))
    finally:
        # Harmless failure if the tested lazy detach already succeeded.
        subprocess.run(["umount", "--lazy", str(mount)], stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, check=False)


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--mount-loss-child":
        mount_loss_child(sys.argv[2])
    else:
        unittest.main()
