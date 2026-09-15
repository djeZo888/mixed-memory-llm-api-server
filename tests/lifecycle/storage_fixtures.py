"""Synthetic mount discovery with real shared Storage validation; no host I/O."""
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from install.storage import Storage
from lifecycle.storage_binding import RegisteredStorageBinding


class MountRunner:
    def __init__(self, data, models, split):
        self.blocks = []
        self.calls = []
        self.add_disk("/dev/sda", "8:0", "/dev/sda1", "8:1", "root-uuid", "/")
        self.add_disk("/dev/sdb", "8:16", "/dev/sdb1", "8:17", "data-uuid", data)
        if split:
            self.add_disk("/dev/sdc", "8:32", "/dev/sdc1", "8:33", "models-uuid", models)

    def add_disk(self, parent, major, child, minor, uuid, mount):
        self.blocks.extend([
            {"name": parent, "path": parent, "type": "disk", "ro": False,
             "maj:min": major, "mountpoints": [None], "uuid": None},
            {"name": child, "path": child, "type": "part", "pkname": parent, "ro": False,
             "maj:min": minor, "mountpoints": [mount], "uuid": uuid, "fstype": "ext4"},
        ])

    def run(self, argv, *, timeout=30, env=None):
        self.calls.append(argv)
        if argv[0] == "lsblk":
            return json.dumps({"blockdevices": self.blocks})
        if argv[0] == "df":
            return "Avail\n107374182400\n"
        if argv[0] == "findmnt":
            path = argv[-1]
            choices = [(point, row) for row in self.blocks for point in row["mountpoints"]
                       if point and (point == "/" or path == point or path.startswith(point + "/"))]
            point, row = max(choices, key=lambda item: len(item[0]))
            return json.dumps({"filesystems": [{"target": point, "source": row["path"],
                                                "uuid": row["uuid"], "fstype": row["fstype"],
                                                "options": "rw,relatime", "maj:min": row["maj:min"]}]})
        raise AssertionError("unexpected fixture command: " + argv[0])


class RegisteredFixture:
    def __init__(self, data="/srv/ai", models=None, split=False):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.data, self.models = data, models or data + "/models"
        self.runner = MountRunner(data, self.models, split)
        config = {"data_dir": data, "model_dir": self.models, "data_uuid": "data-uuid",
                  "model_uuid": "models-uuid" if split else "data-uuid", "storage_mode": "existing"}
        self.storage = Storage(config, self.runner, system_root=self.root)
        for role, path in self.storage._roots().items():
            self.local(path).mkdir(parents=True, exist_ok=True)
            self.local(path).chmod(0o700 if role in {"secrets", "state"} else 0o755)
        self.registration = self.storage._snapshot()
        self.registry_path = "/etc/local-ai-server/storage.json"
        self.jsonfile(self.registry_path, self.registration)
        self.local("/etc/local-ai-server").chmod(0o700)

    def close(self):
        self.temp.cleanup()

    def local(self, path):
        return self.root / str(path).lstrip("/")

    def jsonfile(self, path, value):
        local = self.local(path)
        local.parent.mkdir(parents=True, exist_ok=True)
        local.write_text(json.dumps(value))
        local.chmod(0o600)
        return local

    def binding(self):
        return RegisteredStorageBinding.load(self.runner, system_root=self.root)
