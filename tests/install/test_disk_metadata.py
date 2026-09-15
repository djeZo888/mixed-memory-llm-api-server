"""Regular-file metadata fixtures, not evidence of real GPT/ext4 formatting."""
import contextlib
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest
import uuid
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from install import disk_init as d
from install.storage import StorageError


class MetadataTests(unittest.TestCase):
    def setUp(self):
        self.file = tempfile.TemporaryFile()
        self.fd = self.file.fileno()
        self.size = 64 * d.MIB
        self.file.truncate(self.size)
        self.ids = {"disk_guid": str(uuid.uuid4()), "partition_uuid": str(uuid.uuid4()),
                    "filesystem_uuid": str(uuid.uuid4()), "filesystem_label": "ai-0123456789ab"}
        self.io = d.DiskIO(None)
        self.plan = {"identity": {"size_bytes": self.size},
                     "shape": {"sector_bytes": 512, "start_sector": 2048,
                               "size_sectors": (self.size // d.MIB - 2) * 2048}}

    def tearDown(self):
        self.file.close()

    def write_gpt(self, sector=512):
        total = self.size // sector
        self.plan["shape"].update(sector_bytes=sector, start_sector=d.MIB // sector,
                                  size_sectors=(self.size // d.MIB - 2) * (d.MIB // sector))
        shape = self.plan["shape"]
        entries = bytearray(16384)
        entries[:16] = uuid.UUID(d.LINUX_DATA).bytes_le
        entries[16:32] = uuid.UUID(self.ids["partition_uuid"]).bytes_le
        struct.pack_into("<QQQ", entries, 32, shape["start_sector"], shape["start_sector"] + shape["size_sectors"] - 1, 0)
        entries[56:128] = d.PART_NAME.encode("utf-16le").ljust(72, b"\0")
        mbr = bytearray(512)
        struct.pack_into("<B3sB3sII", mbr, 446, 0, b"\x00\x02\x00", 0xee, b"\xff\xff\xff", 1, total - 1)
        mbr[510:] = b"\x55\xaa"
        os.pwrite(self.fd, mbr, 0)
        for at, other, table in ((1, total - 1, 2), (total - 1, 1, total - 1 - 16384 // sector)):
            header = bytearray(sector)
            struct.pack_into("<8sIIIIQQQQ16sQIII", header, 0, b"EFI PART", 0x10000, 92, 0, 0,
                             at, other, shape["start_sector"], total - 16384 // sector - 2,
                             uuid.UUID(self.ids["disk_guid"]).bytes_le, table, 128, 128, zlib.crc32(entries))
            struct.pack_into("<I", header, 16, zlib.crc32(header[:92]))
            os.pwrite(self.fd, header, at * sector)
            os.pwrite(self.fd, entries, table * sector)

    def write_fs(self):
        shape = self.plan["shape"]
        raw = bytearray(1024)
        struct.pack_into("<I", raw, 4, shape["size_sectors"] * shape["sector_bytes"] // 4096)
        struct.pack_into("<I", raw, 24, 2)
        raw[56:58] = b"\x53\xef"
        raw[104:120] = uuid.UUID(self.ids["filesystem_uuid"]).bytes
        raw[120:136] = self.ids["filesystem_label"].encode().ljust(16, b"\0")
        at = shape["start_sector"] * shape["sector_bytes"] + 1024
        os.pwrite(self.fd, raw, at)
        return at

    def test_full_blank_scan_rejects_middle_payload(self):
        self.io.blank(self.fd, {"size_bytes": self.size})
        os.pwrite(self.fd, b"foreign", self.size // 2)
        with self.assertRaisesRegex(StorageError, "nonblank"):
            self.io.blank(self.fd, {"size_bytes": self.size})

    def test_both_gpt_copies_512_and_4096(self):
        for sector in (512, 4096):
            with self.subTest(sector=sector):
                self.file.truncate(0); self.file.truncate(self.size)
                self.write_gpt(sector)
                self.io.gpt(self.fd, self.plan, self.ids)
                os.pwrite(self.fd, bytes(sector), self.size - sector)
                with self.assertRaisesRegex(StorageError, "header"):
                    self.io.gpt(self.fd, self.plan, self.ids)

    def test_header_and_array_corruption_and_wrong_ids_refused(self):
        for offset in (512 + 16, 1024 + 10, self.size - 512 + 16, self.size - 512 - 16384 + 10, 446 + 4):
            with self.subTest(offset=offset):
                self.write_gpt()
                old = os.pread(self.fd, 1, offset)
                os.pwrite(self.fd, bytes([old[0] ^ 1]), offset)
                with self.assertRaises(StorageError):
                    self.io.gpt(self.fd, self.plan, self.ids)
        self.write_gpt()
        for key in ("disk_guid", "partition_uuid"):
            with self.subTest(key=key), self.assertRaises(StorageError):
                self.io.gpt(self.fd, self.plan, dict(self.ids, **{key: str(uuid.uuid4())}))

    def test_superblock_uuid_label_size_reserved_and_shift(self):
        self.assertFalse(self.io.filesystem(self.fd, self.plan, self.ids))
        at = self.write_fs()
        self.assertTrue(self.io.filesystem(self.fd, self.plan, self.ids))
        for offset, content in ((104, bytes(16)), (120, b"foreign"), (4, bytes(4)), (8, b"\x01\0\0\0"), (24, b"\xff" * 4)):
            with self.subTest(offset=offset):
                self.write_fs()
                os.pwrite(self.fd, content, at + offset)
                with self.assertRaises(StorageError):
                    self.io.filesystem(self.fd, self.plan, self.ids)


if __name__ == "__main__":
    unittest.main()
