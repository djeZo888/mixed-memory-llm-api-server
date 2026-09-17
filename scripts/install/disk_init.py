"""Explicit, journal-owned single-disk transaction. No import-time host actions.

Public Python API: plan(storage, *, io=None), initialize(storage, *, io=None).
The injection seam is for isolated fixtures only; no CLI/env identity overrides.
"""
from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import stat
import struct
import subprocess
import tempfile
import time
import uuid
import zlib

from .storage import Storage, StorageError

JOURNAL = "/etc/local-ai-server/disk-initialization.json"
LOCK = "/etc/local-ai-server/disk-initialization.lock"
STAGES = ("prepared", "gpt_intent", "gpt_done", "fs_intent", "fs_done",
          "mount_intent", "mounted", "complete")
MIB = 1024 * 1024
LINUX_DATA = "0fc63daf-8483-4772-8e79-3d69d8477de4"
PART_NAME = "local-ai-data"
LIMIT = 32768


def fail(message):
    raise StorageError(message)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def config_digest(s):
    return digest({k: v for k, v in s.config.items() if k != "disk_plan"})


def canonical_uuid(value):
    try:
        return isinstance(value, str) and str(uuid.UUID(value)) == value and uuid.UUID(value).int != 0
    except (ValueError, AttributeError):
        return False


def _json_bytes(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                fail("duplicate JSON key")
            result[key] = value
        return result
    try:
        return json.loads(raw, object_pairs_hook=unique)
    except (ValueError, TypeError, UnicodeError):
        fail("invalid disk transaction JSON")


def protected_file(s, logical, *, private=True, optional=False):
    path = s._no_symlink(logical, protected=True)
    if optional and not path.exists():
        return None
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != s.owner or info.st_nlink != 1
                    or (stat.S_IMODE(info.st_mode) != 0o600 if private else bool(info.st_mode & 0o022)) or info.st_size > LIMIT):
                fail("unprotected or oversized disk transaction file")
            return stream.read(LIMIT + 1)
    except OSError:
        fail("disk transaction file unavailable")


def atomic_bytes(s, logical, content, mode=0o600):
    path = s._no_symlink(logical, protected=True)
    if path.exists():
        protected_file(s, logical, private=(mode == 0o600))
    temporary = None
    try:
        fd, temporary = tempfile.mkstemp(prefix=".disk-init-", dir=path.parent)
        with os.fdopen(fd, "wb") as stream:
            os.fchmod(stream.fileno(), mode)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        temporary = None
        dfd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)
    finally:
        if temporary is not None:
            os.unlink(temporary)


def save(s, journal, stage):
    journal["stage"] = stage
    raw = (json.dumps(journal, sort_keys=True, separators=(",", ":")) + "\n").encode()
    if len(raw) > LIMIT:
        fail("disk journal too large")
    atomic_bytes(s, JOURNAL, raw)


def policy(s):
    by_id = s.config.get("initialize_empty_disk")
    confirmation = s.config.get("confirm_disk_id")
    if (s.mode != "initialize" or not isinstance(by_id, str)
            or not re.fullmatch(r"/dev/disk/by-id/(?:scsi-|wwn-|nvme-)[A-Za-z0-9_.:+-]+", by_id)
            or Path(by_id).name != confirmation or re.search(r"-part\d+$", confirmation)):
        fail("initialization requires an exact stable by-id and matching disk ID")
    # A new data root is an explicit top-level dedicated mount, never a system subtree.
    if (not re.fullmatch(r"/[A-Za-z0-9_-]+", s.data_dir)
            or s.data_dir in {"/bin", "/sbin", "/lib", "/lib64", "/usr", "/etc", "/boot", "/dev",
                              "/proc", "/sys", "/run", "/tmp", "/var", "/root", "/home", "/opt", "/srv", "/mnt", "/media", "/lost+found"}):
        fail("initialization requires a dedicated top-level data mount")
    if not s.model_dir.startswith(s.data_dir + "/"):
        fail("initialization requires models nested on the single data filesystem; use existing/UUID mode for separate models")
    if s.config.get("model_uuid") not in (None, "", s.config.get("data_uuid")):
        fail("separate model UUID requires existing/UUID mode")
    if s.config.get("data_uuid") and not canonical_uuid(s.config["data_uuid"]):
        fail("invalid requested filesystem UUID")
    s._no_symlink(s.data_dir, protected=True)
    return by_id


class DiskIO:
    """Only disk-local subprocesses; retained lock/device FDs survive parent death.

    Existing read-only Storage discovery still uses its supplied Runner. New
    commands are encapsulated here, leaving the concurrently owned Runner intact.
    """
    def __init__(self, storage):
        self.s = storage
        self.lock_fd = None

    def command(self, argv, timeout=30, input_text=None, pass_fds=()):
        inherited = tuple(set(pass_fds + (() if self.lock_fd is None else (self.lock_fd,))))
        process = None
        completed = False
        try:
            process = subprocess.Popen(argv, stdin=subprocess.PIPE if input_text is not None else subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, start_new_session=True,
                pass_fds=inherited, env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C"})
            output, _ = process.communicate(input_text, timeout=timeout)
            try:
                os.killpg(process.pid, 0)
            except ProcessLookupError:
                pass
            else:
                fail("disk command left surviving children; intent retained")
            completed = True
            if process.returncode != 0:
                fail("disk command failed; intent retained: " + Path(argv[0]).name)
            return output
        except (OSError, subprocess.TimeoutExpired):
            fail("disk command unavailable or timed out; intent retained")
        finally:
            # Also accounts for KeyboardInterrupt/SystemExit, not just timeouts.
            if process is not None and not completed:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.communicate()

    def prerequisites(self):
        if os.uname().sysname != "Linux" or os.geteuid() != 0:
            fail("disk initialization requires Linux root")
        if not getattr(self.s.runner, "writable", False):
            fail("disk initialization requires a writable installer runner")
        for name in ("sfdisk", "mkfs.ext4", "e2fsck", "mount", "udevadm"):
            if not shutil.which(name, path="/usr/sbin:/usr/bin:/sbin:/bin"):
                fail("disk initialization prerequisite unavailable: " + name)

    def observe(self):
        s = self.s
        by_id = policy(s)
        s._no_symlink("/dev/disk/by-id", protected=True)
        link = s._local(by_id)
        if not link.is_symlink() or link.lstat().st_uid != s.owner:
            fail("stable disk ID must be a root-owned by-id symlink")
        # Require one direct udev-style link into /dev, no arbitrary symlink chain.
        target = os.readlink(link)
        if not re.fullmatch(r"../../[A-Za-z0-9_-]+", target):
            fail("unsafe stable disk symlink")
        source = "/dev/" + target[6:]
        s._no_symlink(source)
        blocks = s._blocks()
        protected = s._protected_disks(blocks)
        if source not in blocks:
            fail("stable ID is absent from block topology")
        s._safe_block(blocks, source, protected)
        row = blocks[source]
        if row.get("type") != "disk" or row["parents"] or row.get("ro") not in (False, 0):
            fail("initialization requires a direct whole disk")
        for key in ("serial", "wwn"):
            value = row.get(key)
            if value and (not isinstance(value, str) or len(value) > 256
                          or len([r for r in blocks.values() if r.get("type") == "disk" and r.get(key) == value]) != 1):
                fail("ambiguous disk serial/WWN")
        if not (row.get("serial") or row.get("wwn")):
            fail("disk serial/WWN is unavailable")
        try:
            sector = int(s._local("/sys/class/block/" + Path(source).name + "/queue/logical_block_size").read_text())
            size = int(row["size"])
        except (ValueError, TypeError, KeyError, OSError):
            fail("disk geometry unavailable")
        if sector not in (512, 4096) or size < 64 * MIB or size % sector:
            fail("unsupported disk geometry")
        identity = {"by_id": by_id, "serial": row.get("serial"), "wwn": row.get("wwn"),
                    "size_bytes": size, "sector_bytes": sector}
        return identity, source, row, blocks, protected

    @contextlib.contextmanager
    def open_device(self, source, row, write=False):
        path = self.s._no_symlink(source)
        fd = os.open(path, (os.O_RDWR if write else os.O_RDONLY) | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            info = os.fstat(fd)
            if (not stat.S_ISBLK(info.st_mode) or info.st_uid != self.s.owner or info.st_mode & 0o002
                    or f"{os.major(info.st_rdev)}:{os.minor(info.st_rdev)}" != row.get("maj:min")):
                fail("device descriptor differs from discovered block identity")
            size = struct.unpack("Q", fcntl.ioctl(fd, 0x80081272, bytes(8)))[0]  # BLKGETSIZE64
            if size != int(row["size"]):
                fail("device size changed")
            yield fd
        finally:
            os.close(fd)

    def exclusive_probe(self, fd):
        # Check kernel-wide use, including other mount namespaces. Tools must
        # subsequently obtain their own claims; retaining ours makes sfdisk/
        # mke2fs refuse their own busy checks. Never bypass those tool checks.
        claimed = os.open(f"/proc/self/fd/{fd}", os.O_RDWR | os.O_EXCL | os.O_CLOEXEC)
        try:
            if os.fstat(claimed).st_rdev != os.fstat(fd).st_rdev:
                fail("exclusive device claim changed identity")
        finally:
            os.close(claimed)

    def unique_ids(self, ids, source, part):
        result = _json_bytes(self.command(["lsblk", "--json", "--paths", "--output", "PATH,TYPE,PTUUID,PARTUUID,UUID"]))
        found = {key: set() for key in ("disk_guid", "partition_uuid", "filesystem_uuid")}
        seen = set()
        def walk(rows):
            for row in rows:
                path = row.get("path")
                if not isinstance(path, str) or not path.startswith("/dev/"):
                    fail("global UUID topology incomplete")
                seen.add(path)
                for key, field in (("disk_guid", "ptuuid"), ("partition_uuid", "partuuid"), ("filesystem_uuid", "uuid")):
                    if (row.get(field) or "").lower() == ids[key]:
                        found[key].add(path)
                walk(row.get("children", []))
        if not isinstance(result, dict) or not isinstance(result.get("blockdevices"), list):
            fail("global UUID discovery incomplete")
        walk(result["blockdevices"])
        # lsblk may expose the parent PTUUID on its partition too.
        if (found["disk_guid"] - {source, part} or found["partition_uuid"] - {part}
                or found["filesystem_uuid"] - {part}):
            fail("intended disk/partition/filesystem UUID is foreign or duplicated")
        if source not in seen or (part is not None and part not in seen):
            fail("global UUID topology incomplete")

    def signatures(self, source):
        result = self.s._json(["wipefs", "--no-act", "--json", "--output", "DEVICE,OFFSET,TYPE,UUID,LABEL", source])
        signatures = result.get("signatures")
        if not isinstance(signatures, list):
            fail("signature discovery incomplete")
        return signatures

    def holders(self, source):
        path = self.s._local("/sys/class/block/" + Path(source).name + "/holders")
        if not path.is_dir() or any(path.iterdir()):
            fail("disk/partition holders present or unavailable")

    def blank(self, fd, identity):
        size = identity["size_bytes"]
        deadline = time.monotonic() + 3600
        zeros = bytes(8 * MIB)
        for offset in range(0, size, len(zeros)):
            if time.monotonic() > deadline:
                fail("full blank-device scan timed out")
            length = min(len(zeros), size - offset)
            raw = os.pread(fd, length, offset)
            if len(raw) != length or raw != zeros[:length]:
                fail("nonblank or partially initialized device without exact owned metadata")

    def gpt(self, fd, plan, ids):
        """Validate both on-disk GPTs without libfdisk's in-memory recovery."""
        shape = plan["shape"]
        sector, total = shape["sector_bytes"], plan["identity"]["size_bytes"] // shape["sector_bytes"]
        mbr = os.pread(fd, 512, 0)
        expected_entry = struct.pack("<B3sB3sII", 0, b"\x00\x02\x00", 0xee, b"\xff\xff\xff", 1, min(total - 1, 0xffffffff))
        # CHS fields are tool-dependent; only status, type and LBA geometry matter.
        if len(mbr) != 512 or mbr[510:] != b"\x55\xaa" or any(mbr[:446]) or any(mbr[462:510]):
            fail("foreign protective MBR")
        if mbr[446] != 0 or mbr[450] != 0xee or mbr[454:462] != expected_entry[8:16]:
            fail("foreign protective MBR layout")
        arrays = []
        table_sectors = (128 * 128) // sector
        for at, other, table_at in ((1, total - 1, 2), (total - 1, 1, total - 1 - table_sectors)):
            raw = os.pread(fd, sector, at * sector)
            if len(raw) != sector or raw[:8] != b"EFI PART":
                fail("missing owned GPT header")
            revision, length, crc, reserved = struct.unpack_from("<IIII", raw, 8)
            if revision != 0x10000 or length != 92 or reserved or any(raw[92:]):
                fail("unsupported GPT header")
            checked = bytearray(raw[:92]); checked[16:20] = bytes(4)
            if zlib.crc32(checked) != crc:
                fail("GPT header CRC mismatch")
            current, backup, first, last = struct.unpack_from("<QQQQ", raw, 24)
            table, count, width, table_crc = struct.unpack_from("<QIII", raw, 72)
            if ((current, backup, first, last, table, count, width)
                    != (at, other, shape["start_sector"], total - table_sectors - 2, table_at, 128, 128)
                    or str(uuid.UUID(bytes_le=raw[56:72])) != ids["disk_guid"]):
                fail("GPT disk identity or geometry differs from intended plan")
            entries = os.pread(fd, count * width, table * sector)
            if len(entries) != count * width or zlib.crc32(entries) != table_crc:
                fail("GPT partition array CRC mismatch")
            if any(entries[128:]):
                fail("foreign or additional GPT partitions")
            entry = entries[:128]
            start, end, attrs = struct.unpack_from("<QQQ", entry, 32)
            if (str(uuid.UUID(bytes_le=entry[:16])) != LINUX_DATA
                    or str(uuid.UUID(bytes_le=entry[16:32])) != ids["partition_uuid"]
                    or (start, end, attrs) != (shape["start_sector"], shape["start_sector"] + shape["size_sectors"] - 1, 0)
                    or entry[56:] != PART_NAME.encode("utf-16le").ljust(72, b"\0")):
                fail("GPT partition differs from intended identity/layout")
            arrays.append(entries)
        if arrays[0] != arrays[1]:
            fail("GPT copies differ")

    def filesystem(self, fd, plan, ids):
        shape = plan["shape"]
        offset = shape["start_sector"] * shape["sector_bytes"]
        raw = os.pread(fd, 1024, offset + 1024)
        if len(raw) != 1024:
            fail("filesystem superblock unavailable")
        if not any(raw):
            return False
        if (raw[56:58] != b"\x53\xef" or str(uuid.UUID(bytes=raw[104:120])) != ids["filesystem_uuid"]
                or raw[120:136] != ids["filesystem_label"].encode().ljust(16, b"\0")):
            fail("foreign or incomplete filesystem signature")
        if struct.unpack_from("<I", raw, 24)[0] != 2:
            fail("unsupported filesystem block size")
        block_size = 4096
        blocks = struct.unpack_from("<I", raw, 4)[0]
        reserved = struct.unpack_from("<I", raw, 8)[0]
        incompat = struct.unpack_from("<I", raw, 96)[0]
        if incompat & 0x80:
            blocks += struct.unpack_from("<I", raw, 336)[0] << 32
            reserved += struct.unpack_from("<I", raw, 340)[0] << 32
        size = shape["size_sectors"] * shape["sector_bytes"]
        if block_size != 4096 or blocks * block_size != size or reserved:
            fail("filesystem size or reserved blocks differ from plan")
        return True

    def partition(self, fd, plan, ids):
        shape = plan["shape"]
        total = plan["identity"]["size_bytes"] // shape["sector_bytes"]
        text = (f'label: gpt\nlabel-id: {ids["disk_guid"]}\nunit: sectors\n'
                f'sector-size: {shape["sector_bytes"]}\nfirst-lba: {shape["start_sector"]}\n'
                f'last-lba: {total - 16384 // shape["sector_bytes"] - 2}\n'
                f'start={shape["start_sector"]}, size={shape["size_sectors"]}, type={LINUX_DATA}, '
                f'uuid={ids["partition_uuid"]}, name="{PART_NAME}"\n')
        self.blank(fd, plan["identity"])
        self.exclusive_probe(fd)
        self.command(["sfdisk", "--lock=nonblock", "--wipe=never", "--wipe-partitions=never", f"/proc/self/fd/{fd}"],
                     timeout=60, input_text=text, pass_fds=(fd,))
        os.fsync(fd)

    def refresh(self, fd):
        fcntl.ioctl(fd, 0x125f)  # BLKRRPART; only used while unmounted
        self.command(["udevadm", "settle", "--timeout=10"], timeout=15, pass_fds=(fd,))

    def format(self, partition_fd, ids):
        size = struct.unpack("Q", fcntl.ioctl(partition_fd, 0x80081272, bytes(8)))[0]
        self.blank(partition_fd, {"size_bytes": size})
        self.exclusive_probe(partition_fd)
        self.command(["mkfs.ext4", "-b", "4096", "-U", ids["filesystem_uuid"], "-L", ids["filesystem_label"],
                      "-m", "0", "-E", "lazy_itable_init=0,lazy_journal_init=0,nodiscard", f"/proc/self/fd/{partition_fd}"],
                     timeout=600, pass_fds=(partition_fd,))
        os.fsync(partition_fd)
        self.command(["udevadm", "settle", "--timeout=10"], timeout=15, pass_fds=(partition_fd,))

    def check_fs(self, partition_fd):
        self.exclusive_probe(partition_fd)
        self.command(["e2fsck", "-f", "-n", f"/proc/self/fd/{partition_fd}"], timeout=600, pass_fds=(partition_fd,))

    def mount(self, partition_fd, fs_uuid):
        # UUID resolution is freshly checked globally and again after mount.
        # A transient /proc/self/fd source would break subsequent findmnt UUID
        # discovery after the child exits, so mounting uses the stable UUID.
        self.command(["mount", "--internal-only", "--types", "ext4", "--options", "rw",
                      "--source", "UUID=" + fs_uuid, "--target", str(self.s._local(self.s.data_dir))],
                     timeout=30, pass_fds=(partition_fd,))


def protected_evidence(s, blocks, protected):
    return sorted([{k: blocks[p].get(k) for k in ("type", "serial", "wwn", "size", "uuid")}
                   for p in protected], key=lambda x: json.dumps(x, sort_keys=True))


def mountpoint(s, *, mounted=False):
    path = s._no_symlink(s.data_dir, protected=True)
    if path.exists() and (not path.is_dir() or (not mounted and any(path.iterdir()))):
        fail("refusing nonempty or invalid underlying mountpoint")
    if not mounted and s._mount(s.data_dir).get("target") == s.data_dir:
        fail("data mountpoint already in use")


def fstab(s, fs_uuid, *, write=False, required=False):
    old = protected_file(s, "/etc/fstab", private=False, optional=True) or b""
    expected = ["UUID=" + fs_uuid, s.data_dir, "ext4", "defaults", "0", "2"]
    matches = 0
    try:
        for line in old.decode("utf-8").splitlines():
            fields = line.split("#", 1)[0].split()
            if len(fields) >= 2:
                target = re.sub(r"\\([0-7]{3})", lambda m: chr(int(m[1], 8)), fields[1])
                if target == s.data_dir or fields[0] == expected[0]:
                    if fields != expected:
                        fail("fstab contains a conflicting storage entry")
                    matches += 1
    except UnicodeError:
        fail("fstab encoding cannot be safely inspected")
    if required and matches != 1:
        fail("completed transaction fstab entry disappeared")
    if matches > 1:
        fail("duplicate fstab storage entries")
    if write and not matches:
        # Every old byte is a prefix of the new file, including CRLF/trailing LFs.
        new = old + (b"\n" if old and not old.endswith(b"\n") else b"") + (" ".join(expected) + "\n").encode()
        if len(new) > LIMIT:
            fail("fstab exceeds bounded bootstrap file limit")
        atomic_bytes(s, "/etc/fstab", new, 0o644)


def plan(storage, *, io=None):
    s, io = storage, io or DiskIO(storage)
    identity, source, row, blocks, protected = io.observe()
    if s.read_registration() is not None or s._local(JOURNAL).exists() or s._local(JOURNAL).is_symlink():
        fail("existing transaction: retain original saved plan and resume")
    children = [p for p in blocks if source in blocks[p]["parents"]]
    io.holders(source)
    if children or row.get("fstype") or row.get("uuid") or any(row.get("mountpoints") or []):
        fail("initialization target is not an unused blank whole disk")
    if io.signatures(source) != []:
        fail("disk contains signatures")
    with io.open_device(source, row) as fd:
        io.blank(fd, identity)
    mountpoint(s)
    fstab(s, s.config.get("data_uuid") or "not-yet-assigned")
    sector = identity["sector_bytes"]
    return {"schema_version": 1, "mode": "initialize", "identity": identity,
            "identity_sha256": digest(identity), "config_sha256": config_digest(s),
            "shape": {"table": "gpt", "partitions": 1, "sector_bytes": sector,
                      "start_sector": MIB // sector, "size_sectors": (identity["size_bytes"] // MIB - 2) * (MIB // sector),
                      "fstype": "ext4", "block_bytes": 4096, "reserved_percent": 0,
                      "data_mount": s.data_dir, "models": s.model_dir, "partition_name": PART_NAME},
            "precondition": {"signatures": [], "partition_table": "absent", "children": [], "holders": [],
                             "mounts": [], "protected": protected_evidence(s, blocks, protected)},
            "disk_mutation_performed": False}


def load_plan(s):
    path = s.config.get("disk_plan")
    if not isinstance(path, str) or not Path(path).is_absolute():
        fail("initialization requires a saved read-only disk plan")
    # Saved input can be ordinary-user owned, but must be a single regular file.
    try:
        if Path(path).is_symlink():
            fail("unsafe saved plan symlink")
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > 262144:
                fail("invalid saved plan file")
            value = _json_bytes(stream.read(262145))
    except OSError:
        fail("saved disk plan unavailable")
    if isinstance(value, dict) and "storage" in value:
        value = value["storage"]
    if not isinstance(value, dict) or value.get("config_sha256") != config_digest(s):
        fail("saved disk plan/config changed")
    return value


def validate_journal(s, journal, previous):
    if (not isinstance(journal, dict) or set(journal) != {"schema_version", "transaction_id", "plan", "plan_sha256", "config_sha256", "ids", "stage"}
            or type(journal.get("schema_version")) is not int or journal.get("schema_version") != 1 or journal.get("stage") not in STAGES
            or journal.get("plan") != previous or journal.get("plan_sha256") != digest(previous)
            or journal.get("config_sha256") != config_digest(s) or not canonical_uuid(journal.get("transaction_id"))):
        fail("disk journal ownership/plan/config/stage changed")
    ids = journal.get("ids")
    if (not isinstance(ids, dict) or set(ids) != {"disk_guid", "partition_uuid", "filesystem_uuid", "filesystem_label"}
            or any(not canonical_uuid(ids[k]) for k in ("disk_guid", "partition_uuid", "filesystem_uuid"))
            or len({journal["transaction_id"], *(ids[k] for k in ("disk_guid", "partition_uuid", "filesystem_uuid"))}) != 4
            or ids["filesystem_label"] != "ai-" + journal["transaction_id"].replace("-", "")[:12]
            or s.config.get("data_uuid") not in (None, "", ids["filesystem_uuid"])):
        fail("invalid intended disk identities")


def check_live(s, io, previous, ids=None, *, allow_mount=False):
    identity, source, row, blocks, protected = io.observe()
    if identity != previous["identity"] or protected_evidence(s, blocks, protected) != previous["precondition"]["protected"]:
        fail("disk identity changed or root/boot evidence drifted since plan")
    io.holders(source)
    if any(row.get("mountpoints") or []) or row.get("fstype") or row.get("uuid"):
        fail("whole disk is in use")
    children = [p for p in blocks if source in blocks[p]["parents"]]
    if len(children) > 1:
        fail("unexpected disk topology")
    part = None
    if children:
        part = children[0]
        item = blocks[part]
        io.holders(part)
        s._safe_block(blocks, part, protected)
        if item["parents"] != {source} or item.get("type") != "part":
            fail("unsafe partition topology")
        targets = [p for p in item.get("mountpoints", []) if p]
        if targets and (not allow_mount or targets != [s.data_dir]):
            fail("partition is mounted or in use")
        shape = previous["shape"]
        try:
            start = int(s._local("/sys/class/block/" + Path(part).name + "/start").read_text()) * 512
        except (ValueError, OSError):
            fail("kernel partition geometry unavailable")
        if start != shape["start_sector"] * shape["sector_bytes"] or int(item["size"]) != shape["size_sectors"] * shape["sector_bytes"]:
            fail("kernel partition geometry differs from plan")
    if ids:
        for key in ("filesystem_uuid",):
            matches = [p for p in blocks if blocks[p].get("uuid") == ids[key]]
            if matches and matches != [part]:
                fail("intended filesystem UUID is duplicated or foreign")
    if ids:
        io.unique_ids(ids, source, part)
    return source, row, blocks, part


@contextlib.contextmanager
def transaction_lock(s, io):
    parent = s._no_symlink("/etc/local-ai-server", protected=True)
    parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if parent.stat().st_uid != s.owner or stat.S_IMODE(parent.stat().st_mode) != 0o700:
        fail("disk journal directory must be root-owned 0700")
    # Persist creation of the tiny bootstrap trust directory itself.
    dfd = os.open(parent.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(dfd)
    finally:
        os.close(dfd)
    path = s._no_symlink(LOCK, protected=True)
    fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != s.owner or stat.S_IMODE(info.st_mode) != 0o600:
            fail("unsafe disk transaction lock")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            fail("disk transaction or surviving child is active")
        io.lock_fd = fd
        yield
    finally:
        io.lock_fd = None
        # Do NOT LOCK_UN: an inherited child must retain the same lock on parent death.
        os.close(fd)


def initialize(storage, *, io=None):
    s, io = storage, io or DiskIO(storage)
    policy(s)
    io.prerequisites()
    previous = load_plan(s)
    with transaction_lock(s, io):
        raw = protected_file(s, JOURNAL, optional=True)
        if raw is None:
            if s.read_registration() is not None:
                fail("registered disk has no initialization journal")
            current = plan(s, io=io)
            if previous != current:
                fail("blank disk identity changed or saved plan/config drifted")
            txid = str(uuid.uuid4())
            ids = {"disk_guid": str(uuid.uuid4()), "partition_uuid": str(uuid.uuid4()),
                   "filesystem_uuid": s.config.get("data_uuid") or str(uuid.uuid4()),
                   "filesystem_label": "ai-" + txid.replace("-", "")[:12]}
            journal = {"schema_version": 1, "transaction_id": txid, "plan": previous,
                       "plan_sha256": digest(previous), "config_sha256": config_digest(s), "ids": ids, "stage": "prepared"}
            validate_journal(s, journal, previous)
            fstab(s, ids["filesystem_uuid"])
            save(s, journal, "prepared")
        else:
            journal = _json_bytes(raw)
            validate_journal(s, journal, previous)
        ids = journal["ids"]
        stage = journal["stage"]
        allow_mount = STAGES.index(stage) >= STAGES.index("mount_intent")
        source, row, blocks, part = check_live(s, io, previous, ids, allow_mount=allow_mount)
        with io.open_device(source, row, write=True) as fd:
            sigs = io.signatures(source)
            blank = sigs == []
            if stage in ("prepared", "gpt_intent") and blank:
                if part:
                    fail("kernel has partition on blank disk")
                io.blank(fd, previous["identity"])
                mountpoint(s)
                fstab(s, ids["filesystem_uuid"])
                save(s, journal, "gpt_intent")
                check_live(s, io, previous, ids)
                io.partition(fd, previous, ids)
                io.gpt(fd, previous, ids)
            else:
                if stage == "prepared" or blank or not sigs or any(x.get("type") not in {"gpt", "PMBR"} for x in sigs):
                    fail("disk signatures inconsistent with journal stage")
                io.gpt(fd, previous, ids)
            if stage in ("prepared", "gpt_intent"):
                save(s, journal, "gpt_done")
            if not part or not any(blocks[part].get("mountpoints") or []):
                io.refresh(fd)
            source2, row2, blocks, part = check_live(s, io, previous, ids, allow_mount=allow_mount)
            if source2 != source or row2.get("maj:min") != row.get("maj:min") or part is None:
                fail("disk changed or owned kernel partition unavailable")
            with io.open_device(part, blocks[part], write=True) as pfd:
                fs_exists = io.filesystem(fd, previous, ids)
                signatures = io.signatures(part)
                mounted = any(blocks[part].get("mountpoints") or [])
                if journal["stage"] in ("gpt_done", "fs_intent") and not fs_exists:
                    if mounted or signatures:
                        fail("refusing format of nonblank partition")
                    # Check both edges: partial formats/foreign payload must fail closed.
                    io.blank(pfd, {"size_bytes": int(blocks[part]["size"])})
                    save(s, journal, "fs_intent")
                    check_live(s, io, previous, ids)
                    io.gpt(fd, previous, ids)
                    io.format(pfd, ids)
                    if not io.filesystem(fd, previous, ids):
                        fail("format did not create intended filesystem")
                else:
                    if not fs_exists or journal["stage"] == "gpt_done":
                        fail("filesystem inconsistent with journal stage")
                    if not signatures or any(x.get("type") != "ext4" or x.get("uuid") != ids["filesystem_uuid"] for x in signatures):
                        fail("foreign filesystem signatures")
                signatures = io.signatures(part)
                if not signatures or any(x.get("type") != "ext4" or x.get("uuid") != ids["filesystem_uuid"] for x in signatures):
                    fail("filesystem signatures differ after format/reconciliation")
                io.gpt(fd, previous, ids)
                if not mounted:
                    io.check_fs(pfd)
                    if journal["stage"] in ("fs_intent", "fs_done"):
                        save(s, journal, "fs_done")
                    if journal["stage"] == "complete":
                        fail("completed filesystem lost its mount; restore expected mount explicitly")
                    mountpoint(s)
                    fstab(s, ids["filesystem_uuid"])
                    path = s._no_symlink(s.data_dir, protected=True)
                    path.mkdir(mode=0o700, exist_ok=True)
                    if stat.S_IMODE(path.stat().st_mode) != 0o700:
                        path.chmod(0o700)
                    for directory in (path, path.parent):
                        dfd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
                        try:
                            os.fsync(dfd)
                        finally:
                            os.close(dfd)
                    save(s, journal, "mount_intent")
                    check_live(s, io, previous, ids)
                    io.mount(pfd, ids["filesystem_uuid"])
                adapted = dict(s.config, storage_mode="existing", data_uuid=ids["filesystem_uuid"], model_uuid=ids["filesystem_uuid"])
                adopted = Storage(adapted, s.runner, s.system_root)
                # Uses the exact mounted UUID/root exclusion checks before directory writes.
                adopted.verify()
                if journal["stage"] == "complete":
                    fstab(s, ids["filesystem_uuid"], required=True)
                    result = adopted.verify()
                    if s.read_registration() is None:
                        fail("completed transaction lost registration")
                    return result
                save(s, journal, "mounted")
                result = adopted.adopt()
                fstab(s, ids["filesystem_uuid"], write=True)
                adopted.verify()
                save(s, journal, "complete")
                return result
