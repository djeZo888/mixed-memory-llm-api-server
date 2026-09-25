#!/usr/bin/env python3
"""H005 fixed local systemd adapter; private UDS only, no caller-selected argv.

Source only. Existing systemd managers own lifecycle. A protected app admission
interlock is required before destructive actions; its absent default rejects them.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import http.server
import json
import os
from pathlib import Path
import pwd
import re
import signal
import socket
import socketserver
import sqlite3
import stat
import struct
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Callable

# Check the adjacent implementation before privileged import, not only after it
# has executed. Test imports never dispatch and remain usable as ordinary users.
if __name__ == "__main__" and os.geteuid() == 0:
    resource_source = Path(__file__).absolute().with_name("resource_observer.py")
    for protected in [resource_source, *resource_source.parents]:
        metadata = protected.lstat()
        if stat.S_ISLNK(metadata.st_mode) or metadata.st_uid != 0 or metadata.st_mode & 0o022:
            raise SystemExit("unsafe_protected_resource_source")
from resource_observer import ProcResources, ResourceCache

SOCKET_PATH = "/run/ai-harness-admin/helper.sock"
CONFIG_PATH = "/etc/ai-harness/local-admin.json"
STATE_PATH = "/var/lib/ai-harness-admin/operations.sqlite3"
MAX_BODY = 16384
MAX_OPERATIONS = 10000
HTTP_WORKERS = 4
SERVICES = {"harness": "ai-harness.service", "search": "ai-harness-searxng.service", "status": "ai-harness-status.service"}
ACTIONS = frozenset({"service.start", "service.stop", "service.restart", "node.reboot"})
KEY = re.compile(r"^[A-Za-z0-9_-]{8,128}$")
BOOT = re.compile(r"^[0-9a-f-]{36}$")


class Rejected(Exception):
    def __init__(self, code: str, status: int = 400):
        self.code, self.status = code, status
        super().__init__(code)


@dataclass(frozen=True)
class Identity:
    uid: int
    gid: int
    name: str
    home: str


def canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def timestamp(value: float) -> str:
    return datetime.fromtimestamp(value, timezone.utc).isoformat().replace("+00:00", "Z")


def validate_request(value: object) -> dict:
    if not isinstance(value, dict):
        raise Rejected("invalid_request")
    base = {"schema_version", "node_id", "action", "idempotency_key", "expected_boot_id", "expected_generation", "allow_interrupt"}
    action = value.get("action")
    if action == "gpu.reset":
        raise Rejected("gpu_reset_unsupported", 422)
    if not isinstance(action, str) or action not in ACTIONS:
        raise Rejected("action_not_allowed")
    if set(value) != base | ({"service_id"} if action.startswith("service.") else set()):
        raise Rejected("invalid_fields")
    if type(value["schema_version"]) is not int or value["schema_version"] != 1 or value["node_id"] != "ai-harness":
        raise Rejected("invalid_node")
    if action.startswith("service.") and (not isinstance(value["service_id"], str) or value["service_id"] not in SERVICES):
        raise Rejected("service_not_allowed")
    if not isinstance(value["idempotency_key"], str) or not KEY.fullmatch(value["idempotency_key"]):
        raise Rejected("idempotency_key_invalid")
    if not isinstance(value["expected_boot_id"], str) or not BOOT.fullmatch(value["expected_boot_id"]):
        raise Rejected("boot_identity_invalid")
    if type(value["expected_generation"]) is not int or value["expected_generation"] < 0 or type(value["allow_interrupt"]) is not bool:
        raise Rejected("confirmation_invalid")
    return value.copy()


class CommandOwner:
    """Only fixed commands to existing systemd owners. Never include stdout in audit."""
    def __init__(self, identity: Identity):
        self.identity = identity

    def user_command(self, *args: str) -> list[str]:
        user = self.identity
        return ["/usr/sbin/runuser", "--user", user.name, "--", "/usr/bin/env", "-i",
                "PATH=/usr/bin:/bin", "LANG=C", f"HOME={user.home}",
                f"XDG_RUNTIME_DIR=/run/user/{user.uid}",
                f"DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/{user.uid}/bus",
                "/usr/bin/systemctl", "--user", "--no-ask-password", "--no-pager", *args]

    def service_command(self, service: str, *args: str) -> list[str]:
        if service not in SERVICES:
            raise Rejected("service_not_allowed")
        if service == "status":
            return ["/usr/bin/systemctl", "--no-ask-password", "--no-pager", *args, SERVICES[service]]
        return self.user_command(*args, SERVICES[service])

    def command(self, request: dict) -> list[str]:
        request = validate_request(request)
        if request["action"] == "node.reboot":
            return ["/usr/bin/systemctl", "--no-ask-password", "reboot"]
        return self.service_command(request["service_id"], request["action"].split(".")[1])

    @staticmethod
    def run(argv: list[str], timeout: float) -> tuple[int, bytes]:
        proc = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, env={"PATH": "/usr/bin:/bin", "LANG": "C"},
                                start_new_session=True)
        try:
            output, _ = proc.communicate(timeout=timeout)
            if len(output) > MAX_BODY:
                raise Rejected("owner_response_invalid", 503)
            return proc.returncode, output
        except subprocess.TimeoutExpired:
            # Kill the command's process group, never the managed service.
            os.killpg(proc.pid, signal.SIGKILL)
            proc.communicate()
            raise Rejected("owner_timeout_unknown", 503) from None

    @staticmethod
    def boot_id() -> str:
        boot = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
        if not BOOT.fullmatch(boot):
            raise Rejected("boot_identity_unavailable", 503)
        return boot

    def observe_service(self, service: str) -> dict:
        rc, output = self.run(self.service_command(service, "show", "--property=LoadState,ActiveState,SubState,InvocationID"), 2)
        if rc:
            raise Rejected("service_observation_unavailable", 503)
        props = dict(line.split("=", 1) for line in output.decode("ascii").splitlines() if "=" in line)
        value = {"load": props.get("LoadState", "unknown"), "active": props.get("ActiveState", "unknown"),
                 "sub": props.get("SubState", "unknown"), "invocation": props.get("InvocationID", "")}
        if any(not re.fullmatch(r"[a-z-]{1,32}", value[k]) for k in ("load", "active", "sub")):
            raise Rejected("service_observation_invalid", 503)
        if value["invocation"] and not re.fullmatch(r"[0-9a-f]{32}", value["invocation"]):
            raise Rejected("service_observation_invalid", 503)
        return value

    def execute(self, request: dict) -> None:
        rc, _ = self.run(self.command(request), 90)
        if rc:
            raise Rejected("owner_failed_unknown", 503)


def missing_interlock(request: dict) -> Callable[[], None]:
    raise Rejected("local_admission_interlock_unavailable", 422)


class Operations:
    """Cached passive status and durable once-only dispatch; no restart replay."""
    def __init__(self, database: Path, boot: Callable[[], str], observe: Callable[[str], dict],
                 execute: Callable[[dict], None], freeze: Callable[[dict], Callable[[], None]] = missing_interlock,
                 clock: Callable[[], float] = time.time):
        self.boot, self.observe, self.execute, self.freeze, self.clock = boot, observe, execute, freeze, clock
        self.lock = threading.RLock()
        self.busy = False
        self.receipts = {}
        self.resources = ResourceCache(lambda _: {})
        self.node_generation = None
        self.observations: dict[str, dict] = {}
        self.probing: set[str] = set()
        self.db = sqlite3.connect(database, check_same_thread=False)
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("CREATE TABLE IF NOT EXISTS operations (id TEXT PRIMARY KEY, key TEXT UNIQUE, fingerprint TEXT, value TEXT)")
        self.db.execute("CREATE TABLE IF NOT EXISTS audit (sequence INTEGER PRIMARY KEY, at REAL, operation_id TEXT, status TEXT, reason TEXT)")
        self.db.execute("CREATE TABLE IF NOT EXISTS identities (target TEXT PRIMARY KEY, fingerprint TEXT, generation INTEGER)")
        with self.db:
            for operation_id, encoded in self.db.execute("SELECT id, value FROM operations").fetchall():
                op = json.loads(encoded)
                self.receipts[operation_id] = op.copy()
                if op["status"] in {"accepted", "running"}:
                    op.update(status="unknown", reason="helper_restarted_no_replay", updated_at=timestamp(self.clock()))
                    self._write(op)

    def _write(self, op: dict) -> None:
        self.db.execute("UPDATE operations SET value=? WHERE id=?", (canonical(op), op["operation_id"]))
        self.db.execute("INSERT INTO audit(at,operation_id,status,reason) VALUES(?,?,?,?)",
                        (self.clock(), op["operation_id"], op["status"], op.get("reason")))
        self.db.commit()
        self.receipts[op["operation_id"]] = op.copy()

    def _generation(self, target: str, identity: object) -> int:
        fingerprint = hashlib.sha256(canonical(identity).encode()).hexdigest()
        row = self.db.execute("SELECT fingerprint,generation FROM identities WHERE target=?", (target,)).fetchone()
        generation = 1 if row is None else row[1] + int(row[0] != fingerprint)
        if row is None or row[0] != fingerprint:
            self.db.execute("INSERT OR REPLACE INTO identities VALUES(?,?,?)", (target, fingerprint, generation))
        return generation

    def refresh(self, service: str) -> bool:
        # Poll callers do not replace a hung worker for this component.
        with self.lock:
            if service in self.probing:
                return False
            self.probing.add(service)
        try:
            boot = self.boot()
            value = self.observe(service)
            with self.lock, self.db:
                generation = self._generation(service, [boot, value])
                candidate = {"boot": boot, "value": value, "generation": generation,
                             "at": self.clock(), "state": "ok", "reason": None}
                merged = {**self.observations, service: candidate}
                identities = [(k, v["generation"], v["boot"]) for k, v in sorted(merged.items())]
                node_generation = self._generation("node", [boot, identities])
                self.db.commit()
                self.observations[service] = candidate
                self.node_generation = node_generation
            return True
        except Exception as error:
            with self.lock:
                prior = self.observations.get(service)
                if prior:
                    prior["state"] = "timeout" if isinstance(error, Rejected) and "timeout" in error.code else "error"
                    prior["reason"] = "service_observation_unavailable"
            return False
        finally:
            with self.lock:
                self.probing.discard(service)

    def _meta(self, observation: dict | None) -> dict:
        age = None if observation is None else max(0, round((self.clock() - observation["at"]) * 1000))
        return {"state": observation["state"] if observation else "unknown",
                "observed_at": timestamp(observation["at"]) if observation else None, "age_ms": age,
                "freshness": "unknown" if age is None else "fresh" if age <= 15000 else "stale",
                "reason": observation["reason"] if observation else "not_observed"}

    def status(self) -> dict:
        # Memory-only getter; never wait on audit fsync or command ownership.
        services = []
        for service in SERVICES:
            observation = self.observations.get(service)
            meta = self._meta(observation)
            good = meta["state"] == "ok" and meta["freshness"] == "fresh"
            value = observation["value"] if observation else {}
            available = "unknown" if not good else "available" if value.get("active") == "active" else "unavailable"
            services.append({**meta, "service_id": service, "generation": observation["generation"] if observation else None,
                             "installed_capabilities": {"harness": ["chat", "gateway"], "search": ["search"], "status": ["node.status", "node.actions"]}[service],
                             "availability": available, "ready": None, "admitting": None,
                             "required_gpu_uuids": [], "hardware_latched": False,
                             "activity": "unknown", "queue_depth": None, "active_requests": None,
                             "affected_services": [service],
                             "deployment_id": None, "model_alias": None, "configured_context_tokens": None,
                             "max_output_tokens": None, "operation_profiles": [],
                             "interrupt_required": True, "actions_supported": ["service.start"],
                             "action_limit_reason": "local_admission_interlock_unavailable"})
        observations = list(self.observations.values())
        latest = max(observations, key=lambda x: x["at"]) if observations else None
        boot = latest["boot"] if latest else None
        unknown = {"state": "unknown", "observed_at": None, "age_ms": None, "freshness": "unknown", "reason": "not_observed"}
        return {"schema_version": 1, "node_id": "ai-harness", "boot_id": boot,
                "generation": self.node_generation, **self._meta(latest), "services": services, "gpus": [],
                "inventory": {**unknown, "boot_id": boot, "complete": False, "observation_id": None, "gpu_uuids": [], "hardware_faults": {}},
                "resources": self.resources.snapshot(),
                "affected_services": list(SERVICES), "activity": "unknown", "interrupt_required": True,
                "actions_supported": [], "action_limit_reason": "local_admission_interlock_unavailable"}

    def _check_confirmation(self, request: dict) -> None:
        snapshot = self.status()
        target = snapshot if request["action"] == "node.reboot" else next(x for x in snapshot["services"] if x["service_id"] == request["service_id"])
        if snapshot["boot_id"] != request["expected_boot_id"] or target["generation"] != request["expected_generation"]:
            raise Rejected("confirmation_stale", 409)
        if target["freshness"] != "fresh" or target["state"] != "ok":
            raise Rejected("observation_unavailable", 503)
        # No claim that systemd inactivity proves all orphan task work absent.
        if not request["allow_interrupt"]:
            raise Rejected("interrupt_confirmation_required", 409)

    def get(self, operation_id: str) -> dict:
        value = self.receipts.get(operation_id)
        if value is None:
            raise Rejected("operation_not_found", 404)
        return value.copy()

    def submit(self, value: object) -> dict:
        request = validate_request(value)
        fingerprint = hashlib.sha256(canonical(request).encode()).hexdigest()
        with self.lock:
            prior = self.db.execute("SELECT fingerprint,value FROM operations WHERE key=?", (request["idempotency_key"],)).fetchone()
            if prior:
                if prior[0] != fingerprint:
                    raise Rejected("idempotency_conflict", 409)
                return json.loads(prior[1])
            if self.busy:
                raise Rejected("operation_in_progress", 409)
            if self.db.execute("SELECT COUNT(*) FROM operations").fetchone()[0] >= MAX_OPERATIONS:
                raise Rejected("audit_capacity_reached", 503)
            self._check_confirmation(request)
            if request["action"] != "service.start" and self.freeze is missing_interlock:
                raise Rejected("local_admission_interlock_unavailable", 422)
            op = {"schema_version": 1, "operation_id": str(uuid.uuid4()), "node_id": "ai-harness", "action": request["action"],
                  "service_id": request.get("service_id"), "gpu_uuid": None,
                  "expected_boot_id": request["expected_boot_id"], "expected_generation": request["expected_generation"],
                  "status": "accepted", "created_at": timestamp(self.clock()), "updated_at": timestamp(self.clock()),
                  "reason": None, "affected_services": list(SERVICES) if request["action"] == "node.reboot" else [request["service_id"]]}
            op["poll_url"] = f'/control/v1/node/operations/{op["operation_id"]}'
            with self.db:
                self.db.execute("INSERT INTO operations VALUES(?,?,?,?)", (op["operation_id"], request["idempotency_key"], fingerprint, canonical(op)))
                self._write(op)
            self.busy = True
            threading.Thread(target=self._run, args=(op["operation_id"], request), daemon=True).start()
            return op.copy()

    def _run(self, operation_id: str, request: dict) -> None:
        release = None
        dispatched = False
        try:
            # Refresh affected identity then recheck at dispatch. systemd remains
            # authoritative; the helper does not claim atomic drain/ownership.
            for service in SERVICES if request["action"] == "node.reboot" else [request["service_id"]]:
                if not self.refresh(service):
                    raise Rejected("dispatch_observation_unavailable", 503)
            with self.lock:
                self._check_confirmation(request)
                if request["action"] != "service.start":
                    release = self.freeze(request)
                    self._check_confirmation(request)
                op = self.get(operation_id)
                op.update(status="running", updated_at=timestamp(self.clock()))
                with self.db:
                    self._write(op)
            dispatched = True
            self.execute(request)
            with self.lock, self.db:
                # A successful reboot command merely schedules shutdown.
                op.update(status="unknown" if request["action"] == "node.reboot" else "succeeded",
                          reason="reboot_awaiting_changed_boot" if request["action"] == "node.reboot" else None,
                          updated_at=timestamp(self.clock()))
                self._write(op)
        except Exception as error:
            with self.lock, self.db:
                op = self.get(operation_id)
                reason = error.code if isinstance(error, Rejected) else "owner_error_unknown"
                op.update(status="unknown" if dispatched else "failed", reason=reason, updated_at=timestamp(self.clock()))
                self._write(op)
        finally:
            # An interlock implementation must retain its hold for uncertain or
            # stopped owners; callback decides based on authoritative owner state.
            if release is not None:
                try:
                    release()
                except Exception:
                    pass
            with self.lock:
                self.busy = False


def protected_path(path: Path, *, directory: bool = False) -> None:
    for item in [path, *path.parents]:
        st = item.lstat()
        if stat.S_ISLNK(st.st_mode) or st.st_uid != 0 or st.st_mode & 0o022:
            raise Rejected("unsafe_protected_path", 503)
    if not (path.is_dir() if directory else path.is_file()):
        raise Rejected("unsafe_protected_path", 503)


def load_identity() -> Identity:
    path = Path(CONFIG_PATH)
    protected_path(path)
    value = json.loads(path.read_text())
    if not isinstance(value, dict) or set(value) != {"harness_uid"} or type(value["harness_uid"]) is not int or value["harness_uid"] <= 0:
        raise Rejected("configuration_invalid", 503)
    user = pwd.getpwuid(value["harness_uid"])
    if not re.fullmatch(r"[a-z_][a-z0-9_-]{0,31}", user.pw_name):
        raise Rejected("configuration_invalid", 503)
    return Identity(user.pw_uid, user.pw_gid, user.pw_name, user.pw_dir)


def authorized_peer(connection: socket.socket, uid: int) -> bool:
    if not hasattr(socket, "SO_PEERCRED"):
        return False
    _, actual_uid, _ = struct.unpack("3i", connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
    return actual_uid == uid


class Server(socketserver.UnixStreamServer):
    # Fixed HTTP workers keep cached reads independent of a stalled audit write.
    # Admission capacity bounds the executor queue as well as running handlers.
    request_queue_size = 8
    def __init__(self, path: str, uid: int, operations: Operations):
        self.allowed_uid, self.operations = uid, operations
        self.http_slots = threading.BoundedSemaphore(HTTP_WORKERS)
        self.mutation_slot = threading.BoundedSemaphore(1)
        self.workers = ThreadPoolExecutor(max_workers=HTTP_WORKERS, thread_name_prefix="local-admin-http")
        super().__init__(path, Handler)

    def process_request(self, request: socket.socket, address: object) -> None:
        if not self.http_slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            self.workers.submit(self._handle_request, request, address)
        except Exception:
            self.http_slots.release()
            self.shutdown_request(request)

    def _handle_request(self, request: socket.socket, address: object) -> None:
        try:
            self.finish_request(request, address)
        except Exception:
            self.handle_error(request, address)
        finally:
            self.shutdown_request(request)
            self.http_slots.release()

    def server_close(self) -> None:
        super().server_close()
        self.workers.shutdown(wait=False, cancel_futures=True)

    def verify_request(self, request: socket.socket, address: object) -> bool:
        request.settimeout(2)
        return authorized_peer(request, self.allowed_uid)

    def handle_error(self, request: object, address: object) -> None:
        pass  # Never log attacker bytes, paths, keys, or raw exceptions.


class Handler(http.server.BaseHTTPRequestHandler):
    server: Server
    protocol_version = "HTTP/1.0"

    def log_message(self, *args: object) -> None:
        pass

    def send_error(self, code: int, message: str | None = None, explain: str | None = None) -> None:
        self.reply(code, {"error": {"code": "invalid_http_request"}})

    def reply(self, status: int, value: object) -> None:
        body = canonical(value).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        try:
            if self.path == "/control/v1/node/status":
                return self.reply(200, self.server.operations.status())
            prefix = "/control/v1/node/operations/"
            if self.path.startswith(prefix) and re.fullmatch(r"[a-f0-9-]{36}", self.path[len(prefix):]):
                return self.reply(200, self.server.operations.get(self.path[len(prefix):]))
            raise Rejected("route_not_found", 404)
        except Rejected as error:
            self.reply(error.status, {"error": {"code": error.code}})

    def do_POST(self) -> None:
        # A blocked SQLite/fsync submission can occupy only one HTTP worker.
        # Additional mutations fail promptly rather than queuing behind its lock.
        if not self.server.mutation_slot.acquire(blocking=False):
            return self.reply(503, {"error": {"code": "operation_admission_busy"}})
        try:
            if self.path != "/control/v1/node/actions":
                raise Rejected("route_not_found", 404)
            if self.headers.get("Transfer-Encoding") or len(self.headers.get_all("Content-Length", [])) != 1:
                raise Rejected("body_length_required")
            length = int(self.headers.get("Content-Length", "0"))
            if length < 1 or length > MAX_BODY or self.headers.get_content_type() != "application/json":
                raise Rejected("invalid_body")
            body = self.rfile.read(length)
            if len(body) != length:
                raise Rejected("invalid_body")
            value = json.loads(body, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
            self.reply(202, self.server.operations.submit(value))
        except Rejected as error:
            self.reply(error.status, {"error": {"code": error.code}})
        except (ValueError, UnicodeError):
            self.reply(400, {"error": {"code": "invalid_body"}})
        finally:
            self.server.mutation_slot.release()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="validate protected installed config and paths without serving or dispatch")
    args = parser.parse_args()
    if os.geteuid() != 0 or os.uname().sysname != "Linux":
        parser.error("root-owned Linux service only")
    protected_path(Path(__file__).absolute())
    identity = load_identity()
    protected_path(Path(STATE_PATH).parent, directory=True)
    protected_path(Path(SOCKET_PATH).parent, directory=True)
    if Path(STATE_PATH).exists() or Path(STATE_PATH).is_symlink():
        protected_path(Path(STATE_PATH))
    if args.check:
        return
    os.umask(0o077)
    owner = CommandOwner(identity)
    operations = Operations(Path(STATE_PATH), owner.boot_id, owner.observe_service, owner.execute)
    operations.resources = ResourceCache(ProcResources().observe)
    operations.resources.start()
    # Never unlink an occupied or unreviewed stale socket; systemd RuntimeDirectory
    # cleanup is the installed owner, and unexpected path requires operator review.
    server = Server(SOCKET_PATH, identity.uid, operations)
    os.chown(SOCKET_PATH, 0, identity.gid)
    os.chmod(SOCKET_PATH, 0o660)
    def poll(service: str) -> None:
        while True:
            started = time.monotonic()
            operations.refresh(service)
            time.sleep(max(0, 5 - (time.monotonic() - started)))
    for service in SERVICES:
        threading.Thread(target=poll, args=(service,), daemon=True).start()
    server.serve_forever(poll_interval=0.5)


if __name__ == "__main__":
    try:
        main()
    except Rejected as error:
        raise SystemExit(error.code) from None
