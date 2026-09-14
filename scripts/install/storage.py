"""Fail-closed dedicated storage registration for the fresh Linux installer.

Only adopt() mutates anything. system_root is an in-process test seam, never an
environment setting or public CLI option. Destructive initialization deliberately
stops at an explicit checkpoint in I1; its plan still rejects unsafe targets.
"""
from __future__ import annotations

import hashlib
import fnmatch
import json
import os
import re
import stat
import tempfile
from pathlib import Path


SCHEMA_VERSION = 1
REGISTRATION_PATH = "/etc/local-ai-server/storage.json"
GIB = 1024 ** 3
FSTYPES = {"ext4", "xfs"}
UUID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{3,127}$")


class StorageError(RuntimeError):
    """Safe operator error; raw subprocess output must not appear here."""


class StorageCheckpoint(StorageError):
    """Selected operation needs a separately completed implementation boundary."""


class Storage:
    def __init__(self, config, runner, system_root=Path("/")):
        self.config = dict(config)
        self.runner = runner
        self.system_root = Path(system_root).resolve()
        self.owner = 0 if self.system_root == Path("/") else os.geteuid()
        self.data_dir = self._path(config.get("data_dir", "/data"))
        self.model_dir = self._path(config.get("model_dir") or self.data_dir + "/models")
        self.mode = config.get("storage_mode", "existing")
        if self.mode not in {"existing", "mount", "initialize"}:
            raise StorageError("unknown storage mode")
        for key in ("data_uuid", "model_uuid"):
            if config.get(key) and not UUID_RE.fullmatch(str(config[key])):
                raise StorageError("invalid filesystem UUID")

    @staticmethod
    def _path(value):
        if not isinstance(value, str) or not re.fullmatch(r"/[A-Za-z0-9_./-]+", value):
            raise StorageError("storage path must be an absolute simple path")
        if value != str(Path(value)) or any(x in {".", ".."} for x in value.split("/")):
            raise StorageError("storage path must be normalized")
        if value == "/" or any(value == x or value.startswith(x + "/") for x in
                               ("/boot", "/etc", "/dev", "/proc", "/sys", "/run")):
            raise StorageError("reserved system path cannot be dedicated storage")
        return value

    def _local(self, path):
        return self.system_root / str(path).lstrip("/")

    def _no_symlink(self, path, protected=False):
        local = self._local(path)
        relative = local.relative_to(self.system_root)
        current = self.system_root
        for part in relative.parts:
            current = current / part
            if current.is_symlink():
                raise StorageError("symlink in storage or registration path")
            if current.exists():
                info = current.stat()
                if protected and (info.st_uid != self.owner or info.st_mode & 0o022):
                    raise StorageError("registration path is not owned and protected by root")
        return local

    def _run(self, argv):
        try:
            return self.runner.run(argv, timeout=30)
        except Exception:
            raise StorageError("storage command failed: " + argv[0]) from None

    def _json(self, argv):
        try:
            return json.loads(self._run(argv))
        except (ValueError, TypeError):
            raise StorageError("invalid storage discovery response") from None

    def _mount(self, path):
        rows = self._json(["findmnt", "--json", "--output",
                           "TARGET,SOURCE,UUID,FSTYPE,OPTIONS,MAJ:MIN", "--target", path]).get("filesystems", [])
        if len(rows) != 1:
            raise StorageError("ambiguous or missing filesystem for " + path)
        return rows[0]

    def _blocks(self):
        rows = self._json(["lsblk", "--json", "--bytes", "--paths", "--output",
                           "NAME,PATH,TYPE,PKNAME,MOUNTPOINTS,FSTYPE,UUID,SIZE,WWN,SERIAL,RO,MAJ:MIN"]).get("blockdevices", [])
        result = {}

        def walk(nodes, parent=None):
            for row in nodes:
                name = row.get("path") or row.get("name")
                if not isinstance(name, str) or not name.startswith("/dev/"):
                    raise StorageError("ambiguous block device identity")
                entry = result.setdefault(name, dict(row, parents=set()))
                if parent:
                    entry["parents"].add(parent)
                if row.get("pkname"):
                    pk = row["pkname"]
                    entry["parents"].add(pk if pk.startswith("/") else "/dev/" + pk)
                walk(row.get("children", []), name)
        walk(rows)
        if not result:
            raise StorageError("no block topology discovered")
        return result

    @staticmethod
    def _ancestors(blocks, device):
        seen = set()

        def visit(name):
            if name in seen:
                return
            if name not in blocks:
                raise StorageError("incomplete block ancestry")
            seen.add(name)
            for parent in blocks[name]["parents"]:
                visit(parent)
        visit(device)
        return seen

    @staticmethod
    def _device_for_mount(blocks, mount):
        matches = [p for p, row in blocks.items() if row.get("maj:min") == mount.get("maj:min")]
        if len(matches) != 1:
            raise StorageError("filesystem has ambiguous block identity")
        return matches[0]

    def _protected_disks(self, blocks):
        protected = set()
        for path in ("/", "/boot", "/boot/efi"):
            # findmnt --target intentionally resolves /boot on / when not separate.
            if path != "/" and not self._local(path).exists():
                continue
            mount = self._mount(path)
            source = self._device_for_mount(blocks, mount)
            protected.update(self._ancestors(blocks, source))
        return protected

    def _safe_block(self, blocks, source, protected):
        ancestors = self._ancestors(blocks, source)
        if ancestors & protected:
            raise StorageError("data device shares root or boot block ancestry")
        for path in ancestors:
            row = blocks[path]
            if row.get("type") not in {"disk", "part"} or row.get("ro") not in (False, 0):
                raise StorageError("LVM/RAID/mapper/read-only data storage is unsupported")
        return sorted(ancestors)

    def _registered_mount(self, path, expected_uuid, blocks, protected, exact=True):
        local = self._no_symlink(path, protected=True)
        mount = self._mount(path)
        if exact and mount.get("target") != path:
            raise StorageError("required dedicated mount is absent: " + path)
        if not local.is_dir():
            raise StorageError("dedicated mount path must be a directory")
        if mount.get("fstype") not in FSTYPES:
            raise StorageError("dedicated storage requires ext4 or xfs")
        if "rw" not in (mount.get("options") or "").split(","):
            raise StorageError("dedicated storage is not writable")
        fs_uuid = mount.get("uuid")
        if not isinstance(fs_uuid, str) or not UUID_RE.fullmatch(fs_uuid):
            raise StorageError("mounted filesystem UUID is unavailable")
        if expected_uuid and fs_uuid != expected_uuid:
            raise StorageError("registered filesystem UUID changed")
        source = self._device_for_mount(blocks, mount)
        same_uuid = [p for p, row in blocks.items() if row.get("uuid") == fs_uuid]
        if same_uuid != [source]:
            raise StorageError("filesystem UUID is duplicated or inconsistent")
        parents = self._safe_block(blocks, source, protected)
        return {"path": path, "mount": mount["target"], "uuid": fs_uuid,
                "fstype": mount["fstype"], "source": source,
                "device": mount["maj:min"], "parents": parents}

    def _roots(self):
        roots = {name: self.data_dir + "/" + suffix for name, suffix in {
            "hf_cache": "hf-cache", "docker": "docker", "containerd": "containerd",
            "build": "build", "logs": "logs", "backups": "backups", "services": "services",
            "secrets": "services/secrets", "state": "services/installer"}.items()}
        roots["models"] = self.model_dir
        return roots

    def _snapshot(self):
        blocks = self._blocks()
        protected = self._protected_disks(blocks)
        data = self._registered_mount(self.data_dir, self.config.get("data_uuid"), blocks, protected)
        model_mount = self._mount(self.model_dir if self._local(self.model_dir).exists() else self.data_dir)
        shares = (self.model_dir == self.data_dir or self.model_dir.startswith(self.data_dir + "/")) and model_mount.get("target") == self.data_dir
        if shares:
            if self.config.get("model_uuid") not in (None, "", data["uuid"]):
                raise StorageError("model UUID does not match the shared data filesystem")
            models = dict(data, path=self.model_dir)
        else:
            models = self._registered_mount(self.model_dir, self.config.get("model_uuid"), blocks, protected)
        for key, path in self._roots().items():
            self._no_symlink(path, protected=True)
            local = self._local(path)
            if local.exists():
                if not local.is_dir():
                    raise StorageError("required storage directory is not a directory")
                mount = self._mount(path)
                expected = models if key == "models" else data
                if mount.get("uuid") != expected["uuid"] or mount.get("target") != expected["mount"]:
                    raise StorageError("storage root crosses an unregistered mount")
        return {"schema_version": SCHEMA_VERSION, "storage_mode": self.mode,
                "data": data, "models": models, "roots": self._roots()}

    def _capacity(self, snapshot):
        def available(path):
            rows = self._run(["df", "--output=avail", "--block-size=1", path]).strip().splitlines()
            try:
                value = int(rows[-1].strip())
                if value < 0:
                    raise ValueError
                return value
            except (ValueError, IndexError):
                raise StorageError("cannot determine free storage capacity") from None
        return {"root_available_bytes": available("/"),
                "data_available_bytes": available(snapshot["data"]["mount"]),
                "model_available_bytes": available(snapshot["models"]["mount"]),
                "shared_model_filesystem": snapshot["data"]["uuid"] == snapshot["models"]["uuid"]}

    @staticmethod
    def _identity(value):
        return {"schema_version": value.get("schema_version"), "roots": value.get("roots"),
                **{key: {field: value.get(key, {}).get(field) for field in ("path", "mount", "uuid", "fstype")}
                   for key in ("data", "models")}}

    def read_registration(self):
        local = self._no_symlink(REGISTRATION_PATH, protected=True)
        if not local.exists():
            return None
        info = local.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077 or info.st_size > 16384 or info.st_nlink != 1:
            raise StorageError("storage registration must be a private small regular file")
        try:
            value = json.loads(local.read_text())
            if value.get("schema_version") != SCHEMA_VERSION or not isinstance(value.get("roots"), dict):
                raise ValueError
            for key in ("data", "models"):
                self._path(value[key]["path"])
                self._path(value[key]["mount"])
                if not UUID_RE.fullmatch(value[key]["uuid"]):
                    raise ValueError
        except (ValueError, KeyError, TypeError):
            raise StorageError("invalid registered storage schema") from None
        return value

    def verify(self, registration=None):
        trusted = self.read_registration()
        if registration is not None and trusted is not None and self._identity(registration) != self._identity(trusted):
            raise StorageError("caller registration conflicts with root-owned storage identity")
        expected = trusted or registration
        snapshot = self._snapshot()
        if expected is not None and self._identity(snapshot) != self._identity(expected):
            raise StorageError("configuration or mounted storage differs from registered identity")
        snapshot["capacity"] = self._capacity(snapshot)
        if snapshot["capacity"]["root_available_bytes"] < 4 * GIB:
            raise StorageError("root filesystem has less than the required 4 GiB free")
        snapshot["warnings"] = []
        if snapshot["capacity"]["root_available_bytes"] < 6 * GIB:
            snapshot["warnings"].append("root filesystem has less than 6 GiB free")
        if expected is not None:
            for path in snapshot["roots"].values():
                if not self._local(path).is_dir():
                    raise StorageError("registered directory disappeared")
            for key in ("secrets", "state"):
                info = self._local(snapshot["roots"][key]).stat()
                if info.st_uid != self.owner or info.st_mode & 0o077:
                    raise StorageError("private service directory ownership or mode changed")
        return snapshot

    guard = verify

    def root_payload_guard(self, registration=None):
        """Read-only root payload scan; never follows symlinks or other mounts.

        Capacity and exact mounted registration are checked before scanning. A
        caller can only write a report after this returns successfully.
        """
        snapshot = self.verify(registration)
        root_device = self.system_root.stat().st_dev
        excluded = [self._local(snapshot[key]["mount"]) for key in ("data", "models")]

        def on_root(path):
            return (not path.is_symlink() and path.exists() and path.stat().st_dev == root_device
                    and not any(path == mount or mount in path.parents for mount in excluded))

        try:
            for logical in ("/var/lib/docker", "/var/lib/containerd"):
                directory = self._local(logical)
                if on_root(directory) and directory.is_dir() and any(directory.iterdir()):
                    raise StorageError("existing container payload remains on root: " + logical)
            candidates = [self._local(p) for p in (
                "/root/.cache", "/var/tmp", "/tmp", "/opt", "/srv", "/var/lib",
                "/models", "/hf-cache", "/docker", "/containerd", "/build", "/logs")]
            homes = self._local("/home")
            if on_root(homes):
                candidates += [home / ".cache" for home in homes.iterdir() if not home.is_symlink() and home.is_dir()]
            patterns = ("*.gguf", "*.safetensors", "*.bin", "*.pt", "*.pth", "*.ckpt", "*.onnx",
                        "*.engine", "*.tar", "*.tar.gz", "*.tgz", "*.zip", "*.zst", "*.whl", "*.deb",
                        "*.parquet", "*.arrow", "pytorch_model*", "model-*", "tokenizer*", "consolidated*")
            scanned = 0

            def failed(_error):
                raise StorageError("root payload scan could not inspect a required directory")

            for start in candidates:
                if not on_root(start) or not start.is_dir():
                    continue
                for current, dirs, files in os.walk(start, topdown=True, followlinks=False, onerror=failed):
                    current = Path(current)
                    dirs[:] = [name for name in dirs if on_root(current / name)]
                    for name in files:
                        path = current / name
                        if not on_root(path):
                            continue
                        info = path.stat()
                        if not stat.S_ISREG(info.st_mode):
                            continue
                        scanned += 1
                        if info.st_size >= 128 * 1024 ** 2 and any(fnmatch.fnmatch(name.lower(), pattern) for pattern in patterns):
                            raise StorageError("large model/cache/archive payload found on root: /" + str(path.relative_to(self.system_root)))
        except OSError:
            raise StorageError("root payload scan could not inspect a required path") from None
        snapshot["root_payload_scan"] = {"status": "pass", "files_inspected": scanned,
                                         "large_payload_threshold_bytes": 128 * 1024 ** 2}
        return snapshot

    def _uuid_mount_plan(self):
        inside_data = self.model_dir == self.data_dir or self.model_dir.startswith(self.data_dir + "/")
        if not inside_data and (not self.config.get("model_uuid") or self.config.get("model_uuid") == self.config.get("data_uuid")):
            raise StorageError("separate model mount requires its own explicit UUID")
        if self.model_dir == self.data_dir and self.config.get("model_uuid") not in (None, "", self.config.get("data_uuid")):
            raise StorageError("one mountpoint cannot have two filesystem UUIDs")
        blocks = self._blocks()
        protected = self._protected_disks(blocks)
        mounts = []
        for index, (path, fs_uuid) in enumerate(((self.data_dir, self.config.get("data_uuid")),
                                                (self.model_dir, self.config.get("model_uuid")))):
            if index == 1 and (not fs_uuid or fs_uuid == self.config.get("data_uuid")):
                continue
            if not fs_uuid:
                raise StorageError("UUID mount mode requires an explicit data UUID")
            self._no_symlink(path, protected=True)
            matches = [(p, row) for p, row in blocks.items() if row.get("uuid") == fs_uuid]
            if len(matches) != 1:
                raise StorageError("requested UUID is unavailable or ambiguous")
            source, row = matches[0]
            self._safe_block(blocks, source, protected)
            if row.get("fstype") not in FSTYPES:
                raise StorageError("requested UUID is not ext4 or xfs")
            targets = [x for x in (row.get("mountpoints") or []) if x]
            if targets and targets != [path]:
                raise StorageError("requested UUID is already mounted elsewhere")
            if not targets and self._local(path).exists():
                if not self._local(path).is_dir() or any(self._local(path).iterdir()):
                    raise StorageError("refusing to cover a nonempty mountpoint")
            mounts.append({"path": path, "uuid": fs_uuid, "fstype": row["fstype"], "mounted": targets == [path]})
        self._fstab_content(mounts)
        return mounts

    def _fstab_content(self, mounts):
        local = self._no_symlink("/etc/fstab", protected=True)
        content = local.read_text() if local.exists() else ""
        additions = []
        for mount in mounts:
            present = False
            for line in content.splitlines():
                fields = line.split("#", 1)[0].split()
                if len(fields) < 2:
                    continue
                if fields[1] == mount["path"] or fields[0] == "UUID=" + mount["uuid"]:
                    if len(fields) < 4 or fields[:3] != ["UUID=" + mount["uuid"], mount["path"], mount["fstype"]] or set(fields[3].split(",")) & {"ro", "bind", "noauto"}:
                        raise StorageError("fstab contains a conflicting storage entry")
                    present = True
            if not present:
                additions.append("UUID={uuid} {path} {fstype} defaults 0 {passno}".format(
                    **mount, passno=2 if mount["fstype"] == "ext4" else 0))
        return content, content.rstrip("\n") + ("\n" if content else "") + "".join(x + "\n" for x in additions)

    def _disk_plan(self):
        by_id = self.config.get("initialize_empty_disk", "")
        confirmation = self.config.get("confirm_disk_id", "")
        if not re.fullmatch(r"/dev/disk/by-id/[A-Za-z0-9_.:+-]+", by_id) or Path(by_id).name != confirmation or "-part" in confirmation:
            raise StorageError("initialization requires an exact stable by-id and matching disk ID")
        target = self._local(by_id)
        if not target.is_symlink():
            raise StorageError("stable disk ID must resolve through an existing by-id link")
        resolved = target.resolve(strict=True)
        try:
            source = "/" + str(resolved.relative_to(self.system_root))
        except ValueError:
            raise StorageError("disk identity escaped system root") from None
        blocks = self._blocks()
        protected = self._protected_disks(blocks)
        if source not in blocks:
            raise StorageError("stable ID is absent from block topology")
        self._safe_block(blocks, source, protected)
        row = blocks[source]
        if row.get("type") != "disk" or row.get("children") or row["parents"] or row.get("uuid") or row.get("fstype") or any(row.get("mountpoints") or []):
            raise StorageError("initialization target is not an unused blank whole disk")
        holders = self._local("/sys/class/block/" + Path(source).name + "/holders")
        if not holders.is_dir() or any(holders.iterdir()):
            raise StorageError("disk holders are present or cannot be checked")
        signatures = self._json(["wipefs", "--no-act", "--json", "--output", "DEVICE,OFFSET,TYPE,UUID,LABEL", source]).get("signatures")
        if signatures != []:
            raise StorageError("disk contains signatures or signature discovery is incomplete")
        if not (row.get("wwn") or row.get("serial")) or int(row.get("size", 0)) <= 0:
            raise StorageError("disk serial/WWN or size is unavailable")
        identity = {"by_id": by_id, "serial": row.get("serial"), "wwn": row.get("wwn"), "size_bytes": int(row["size"])}
        digest = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
        return {"schema_version": 1, "mode": "initialize", "identity": identity,
                "identity_sha256": digest, "status": "pending_implementation",
                "checkpoint": "I1b: blank-disk mutation and disposable loopback verification required",
                "disk_mutation_performed": False}

    def plan(self):
        if self.mode == "initialize":
            return self._disk_plan()
        if self.mode == "mount" and self.read_registration() is None:
            return {"schema_version": 1, "mode": "mount", "mounts": self._uuid_mount_plan(),
                    "root_writes": ["tiny bootstrap/registration and UUID-based fstab"],
                    "restart_effects": "No reboot; mount selected UUID filesystems before data writes"}
        return self.verify()

    def _atomic_write(self, logical_path, text, mode=0o600):
        local = self._no_symlink(logical_path)
        temporary = None
        try:
            fd, temporary = tempfile.mkstemp(prefix=".installer-", dir=local.parent)
            with os.fdopen(fd, "w") as stream:
                os.fchmod(stream.fileno(), mode)
                stream.write(text)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, local)
            temporary = None
            directory = os.open(local.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            if temporary:
                os.unlink(temporary)

    def adopt(self):
        if self.mode == "initialize":
            current = self._disk_plan()
            plan_file = self.config.get("disk_plan")
            if not plan_file:
                raise StorageError("initialization requires a saved read-only disk plan")
            try:
                previous = json.loads(Path(plan_file).read_text())
            except (OSError, ValueError):
                raise StorageError("saved disk plan is unavailable or invalid") from None
            if previous.get("identity_sha256") != current["identity_sha256"]:
                raise StorageError("blank disk identity changed since plan")
            raise StorageCheckpoint(current["checkpoint"])
        if self.system_root == Path("/") and os.geteuid() != 0:
            raise StorageError("storage adoption requires root or sudo")
        if self.read_registration() is not None:
            return self.verify()
        mounts = self._uuid_mount_plan() if self.mode == "mount" else []
        for mount in mounts:
            if not mount["mounted"]:
                # Repeat all non-use/identity checks immediately before each mount.
                self._uuid_mount_plan()
                self._no_symlink(mount["path"]).mkdir(parents=True, exist_ok=True)
                self._run(["mount", "--source", "UUID=" + mount["uuid"], "--target", mount["path"],
                           "--types", mount["fstype"], "--options", "rw"])
        snapshot = self.verify()
        for key, path in snapshot["roots"].items():
            # Each creation rechecks current mount identities; never root fallback.
            self.verify()
            local = self._no_symlink(path)
            if local.exists() and key in {"secrets", "state"}:
                info = local.stat()
                if info.st_uid != self.owner or info.st_mode & 0o077:
                    raise StorageError("existing private service directory is not protected")
            local.mkdir(mode=0o700 if key in {"secrets", "state"} else 0o755, parents=True, exist_ok=True)
        if mounts:
            old, new = self._fstab_content(mounts)
            if old != new:
                self.verify()
                backup = snapshot["roots"]["backups"] + "/fstab." + hashlib.sha256(old.encode()).hexdigest() + ".backup"
                if not self._local(backup).exists():
                    self._atomic_write(backup, old)
                self._atomic_write("/etc/fstab", new, 0o644)
                self._run(["systemctl", "daemon-reload"])
        self.verify()
        parent = self._no_symlink("/etc/local-ai-server", protected=True)
        parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if parent.stat().st_mode & 0o077:
            raise StorageError("bootstrap directory must have mode 0700")
        self._atomic_write(REGISTRATION_PATH, json.dumps(snapshot, sort_keys=True, indent=2) + "\n")
        return self.verify()
