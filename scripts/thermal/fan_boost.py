#!/usr/bin/env python3
"""Offline H013 candidate. Import is inert; only explicit run/failsafe can set fans."""
from __future__ import annotations

import argparse
import ctypes as C
import fcntl
import json
import math
import multiprocessing as MP
import os
from pathlib import Path
import signal
import socket
import stat
import time

KNOWN = {
    "GPU-88058d9d-08e5-cb1e-a77a-04cbc1488237": "Qwen0",
    "GPU-69acfa26-8b60-61b5-702d-aee252c163cc": "Flash",
    "GPU-5d895991-b794-2b4c-b9c4-5f1b668afd23": "Ada",
    "GPU-93dbfca8-ef3a-9628-a798-6a4afd0af528": "Server",
}
EXTERNAL = next(u for u, label in KNOWN.items() if label == "Server")
INTEGRATED = tuple(u for u in KNOWN if u != EXTERNAL)
HOT, COOL, COOL_SECONDS = 70, 65, 30
POLL, MAX_GAP, CALL_TIMEOUT = 2.0, 6.0, 2.0
OWNER = "h013-nvml-fan-boost-v1"
CONFIG = "/etc/local-ai-server/fan-boost.json"
STATE_DIR = "/var/lib/local-ai-fan-boost"


class SafetyError(Exception):
    pass


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise SafetyError("duplicate-json-key")
        result[key] = value
    return result


def decode(raw):
    return json.loads(raw, object_pairs_hook=unique_object)


def validate_config(value):
    if (not isinstance(value, dict) or set(value) != {"version", "devices"}
            or type(value["version"]) is not int or value["version"] != 1
            or not isinstance(value["devices"], list)
            or any(type(u) is not str for u in value["devices"])
            or len(value["devices"]) != len(KNOWN)
            or set(value["devices"]) != set(KNOWN)):
        raise SafetyError("wrong-config-identity")
    return value


def check_meta(info, *, directory=False, private=False):
    kind = stat.S_ISDIR if directory else stat.S_ISREG
    if (not kind(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022
            or (not directory and info.st_nlink != 1)
            or (private and stat.S_IMODE(info.st_mode) != (0o700 if directory else 0o600))):
        raise SafetyError("unprotected-path")


def protected_dir(path):
    """Open anchored root-owned ancestry. No symlinks or writable ancestors."""
    p = Path(path)
    if not p.is_absolute() or ".." in p.parts:
        raise SafetyError("nonabsolute-path")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    fd = os.open("/", flags)
    try:
        check_meta(os.fstat(fd), directory=True)
        for name in p.parts[1:]:
            child = os.open(name, flags, dir_fd=fd)
            os.close(fd)
            fd = child
            check_meta(os.fstat(fd), directory=True)
        return fd
    except BaseException:
        os.close(fd)
        raise


def read_at(directory, name, *, private=False):
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    try:
        check_meta(os.fstat(fd), private=private)
        with os.fdopen(fd, "r", closefd=False) as stream:
            raw = stream.read(16385)
        if len(raw) > 16384:
            raise SafetyError("oversized-record")
        return decode(raw)
    finally:
        os.close(fd)


def read_config(path):
    p = Path(path)
    fd = protected_dir(p.parent)
    try:
        return validate_config(read_at(fd, p.name))
    finally:
        os.close(fd)


def validate_state(value):
    if (not isinstance(value, dict) or set(value) != {"version", "owner", "owned"}
            or type(value["version"]) is not int or value["version"] != 1
            or value["owner"] != OWNER or not isinstance(value["owned"], dict)
            or set(value["owned"]) != set(INTEGRATED)
            or any(type(v) is not bool for v in value["owned"].values())):
        raise SafetyError("wrong-state-identity")
    return dict(value["owned"])


class Store:
    """Protected atomic state and one cooperative controller lock, not lifecycle."""
    def __init__(self, path, writable):
        self.fd = protected_dir(path)
        self.lock = None
        self.writable = writable
        try:
            check_meta(os.fstat(self.fd), directory=True, private=True)
            if writable:
                self.lock = os.open("controller.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW,
                                    0o600, dir_fd=self.fd)
                check_meta(os.fstat(self.lock), private=True)
                try:
                    fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    raise SafetyError("controller-conflict-lock") from None
        except BaseException:
            self.close()
            raise

    def load(self):
        try:
            return validate_state(read_at(self.fd, "ownership.json", private=True))
        except FileNotFoundError:
            return dict.fromkeys(INTEGRATED, False)

    def save(self, owned):
        if not self.writable:
            raise SafetyError("readonly-state")
        # Validate lock's named identity before any new intent write.
        named = os.stat("controller.lock", dir_fd=self.fd, follow_symlinks=False)
        held = os.fstat(self.lock)
        check_meta(named, private=True)
        if (named.st_dev, named.st_ino) != (held.st_dev, held.st_ino):
            raise SafetyError("controller-lock-replaced")
        value = {"version": 1, "owner": OWNER, "owned": owned}
        validate_state(value)
        name = f".ownership-{os.getpid()}.tmp"
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600, dir_fd=self.fd)
        try:
            raw = (json.dumps(value, sort_keys=True) + "\n").encode()
            with os.fdopen(fd, "wb", closefd=False) as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(fd)
            os.rename(name, "ownership.json", src_dir_fd=self.fd, dst_dir_fd=self.fd)
            os.fsync(self.fd)
        finally:
            os.close(fd)
            try:
                os.unlink(name, dir_fd=self.fd)
            except FileNotFoundError:
                pass

    def close(self):
        if self.lock is not None:
            os.close(self.lock)
            self.lock = None
        if getattr(self, "fd", None) is not None:
            os.close(self.fd)
            self.fd = None


class NVML:
    """Minimal official C API bindings. Library loaded in bounded child only."""
    def __init__(self):
        self.lib = C.CDLL("libnvidia-ml.so.1")
        self.handle = C.c_void_p()
        self.call("nvmlInit_v2", [])

    def call(self, name, types, *args):
        try:
            fn = getattr(self.lib, name)
        except AttributeError:
            raise SafetyError("unsupported-symbol:" + name) from None
        fn.argtypes, fn.restype = types, C.c_int
        code = fn(*args)
        if code != 0:
            raise SafetyError(f"{name}:nvml-return-{code}")

    def bind(self, uuid):
        self.call("nvmlDeviceGetHandleByUUID", [C.c_char_p, C.POINTER(C.c_void_p)],
                  uuid.encode("ascii"), C.byref(self.handle))
        buf = C.create_string_buffer(96)
        self.call("nvmlDeviceGetUUID", [C.c_void_p, C.c_char_p, C.c_uint],
                  self.handle, buf, len(buf))
        if buf.value.decode("ascii") != uuid:
            raise SafetyError("device-uuid-mismatch")

    def uint(self, name, *indices):
        value = C.c_uint()
        self.call(name, [C.c_void_p] + [C.c_uint] * len(indices) + [C.POINTER(C.c_uint)],
                  self.handle, *indices, C.byref(value))
        return value.value

    def temperature(self):
        # nvmlTemperatureSensors_t is a C enum; GPU absolute Celsius, NOT T.Limit.
        value = C.c_uint()
        self.call("nvmlDeviceGetTemperature", [C.c_void_p, C.c_int, C.POINTER(C.c_uint)],
                  self.handle, 0, C.byref(value))
        return value.value

    def count(self):
        return self.uint("nvmlDeviceGetNumFans")

    def policy(self, fan):
        # Official header typedefs nvmlFanControlPolicy_t to unsigned int.
        value = C.c_uint()
        self.call("nvmlDeviceGetFanControlPolicy_v2", [C.c_void_p, C.c_uint, C.POINTER(C.c_uint)],
                  self.handle, fan, C.byref(value))
        return value.value

    def target(self, fan):
        return self.uint("nvmlDeviceGetTargetFanSpeed", fan)

    def boost(self, fan):
        self.call("nvmlDeviceSetFanSpeed_v2", [C.c_void_p, C.c_uint, C.c_uint],
                  self.handle, fan, 100)

    def default(self, fan):
        self.call("nvmlDeviceSetDefaultFanSpeed_v2", [C.c_void_p, C.c_uint], self.handle, fan)


def valid_temperature(value):
    return type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 125


def device_job(uuid, action, owned, api_factory=NVML, clock=time.monotonic):
    """One isolated device transaction. No setter is reachable from inspect."""
    if uuid not in INTEGRATED or action not in {"inspect", "boost", "default"}:
        raise SafetyError("wrong-job-identity")
    api = api_factory()
    api.bind(uuid)
    count = api.count()
    if type(count) is not int or count < 1 or count > 64:
        raise SafetyError("no-supported-enumerated-fans")
    fans = list(range(count))  # NVML documents indices 0 <= fan < numFans.
    temp, sampled, errors = None, clock(), []
    try:
        temp = api.temperature()
        sampled = clock()
        if not valid_temperature(temp):
            raise SafetyError("invalid-temperature")
    except Exception as exc:
        errors.append(str(exc))
        temp = None
    policies, targets = {}, {}
    for fan in fans:
        try:
            policies[fan] = api.policy(fan)
            targets[fan] = api.target(fan)
            if policies[fan] not in (0, 1) or not 0 <= targets[fan] <= 100:
                raise SafetyError("invalid-readback")
        except Exception as exc:
            errors.append(f"fan-{fan}:{exc}")
    # Another owner must never be silently overwritten. Missing policy is not proof.
    conflict = not owned and (len(policies) != count or any(p != 0 for p in policies.values()))
    if action == "inspect":
        return {"temperature": temp, "sampled": sampled, "fans": fans,
                "policies": policies, "targets": targets, "conflict": conflict,
                "errors": errors, "ok": not errors and not conflict}
    if not owned:
        raise SafetyError("missing-durable-owner-intent")
    # Parent only requests default after 30s fresh continuous cool observations.
    # Recheck temperature immediately before every potentially lowering operation.
    def boost_all():
        failures = []
        for fan in fans:
            try:
                api.boost(fan)
                if api.target(fan) != 100 or api.policy(fan) != 1:
                    raise SafetyError("boost-readback-mismatch")
            except Exception as exc:
                failures.append(f"fan-{fan}:{exc}")
        return failures

    if action == "boost":
        failures = boost_all()
        return {"ok": not failures, "errors": errors + failures, "fans": fans}
    if errors or temp is None or temp > COOL or clock() - sampled > MAX_GAP:
        failures = boost_all()
        return {"ok": False, "errors": errors + ["default-refused"] + failures}
    try:
        for fan in fans:
            before = clock()
            fresh = api.temperature()
            if (not valid_temperature(fresh) or fresh > COOL
                    or clock() - before > CALL_TIMEOUT):
                raise SafetyError("default-fresh-cool-check-failed")
            api.default(fan)
            if api.policy(fan) != 0:
                raise SafetyError("default-policy-readback-mismatch")
        return {"ok": True, "errors": [], "fans": fans}
    except Exception as exc:
        failures = boost_all()
        return {"ok": False, "errors": [str(exc)] + failures}


def child_job(connection, uuid, action, owned):
    # Do not inherit the supervisor's graceful-stop handler into driver jobs.
    signal.signal(signal.SIGTERM, signal.SIG_DFL)
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    try:
        connection.send(device_job(uuid, action, owned))
    except Exception as exc:
        connection.send({"ok": False, "errors": [str(exc)]})
    finally:
        connection.close()


class BoundedJobs:
    """Parallel device jobs, one outstanding child/device; no unbounded join."""
    def __init__(self):
        self.blocked = {}
        self.context = MP.get_context("fork")  # Linux service; parent never loads NVML.

    def batch(self, actions, owned):
        running, results = {}, {}
        for uuid, action in actions.items():
            if uuid in self.blocked:
                prior = self.blocked[uuid]
                prior.join(0)
                if prior.is_alive():
                    results[uuid] = {"ok": False, "errors": ["unreaped-driver-call-device-blocked"]}
                    continue
                prior.close()
                del self.blocked[uuid]
            read, write = self.context.Pipe(duplex=False)
            process = self.context.Process(target=child_job, args=(write, uuid, action, owned[uuid]))
            process.start()
            write.close()
            running[uuid] = (process, read, time.monotonic() + CALL_TIMEOUT)
        while running:
            for uuid, (process, read, deadline) in list(running.items()):
                result = None
                if read.poll():
                    try:
                        result = read.recv()
                    except EOFError:
                        result = {"ok": False, "errors": ["device-worker-exited"]}
                elif not process.is_alive():
                    result = {"ok": False, "errors": ["device-worker-exited"]}
                elif time.monotonic() >= deadline:
                    result = {"ok": False, "errors": ["driver-call-timeout"]}
                if result is not None:
                    process.join(0.01)
                    if process.is_alive():
                        process.kill()
                        process.join(0.05)
                    if process.is_alive():
                        self.blocked[uuid] = process
                        result = {"ok": False, "errors": ["unreaped-driver-call-device-blocked"]}
                    else:
                        process.close()
                    read.close()
                    results[uuid] = result
                    del running[uuid]
            if running:
                time.sleep(0.01)
        return results


class Controller:
    def __init__(self, store, jobs, *, readonly=False, clock=time.monotonic, stop_requested=lambda: False):
        self.store, self.jobs, self.readonly, self.clock = store, jobs, readonly, clock
        self.stop_requested = stop_requested
        self.owned = store.load()
        self.cool_since = dict.fromkeys(INTEGRATED)
        self.last_sample = dict.fromkeys(INTEGRATED)
        self.recover = set(u for u, v in self.owned.items() if v)

    def cycle(self, *, stopping=False):
        observations = self.jobs.batch(dict.fromkeys(INTEGRATED, "inspect"), self.owned)
        actions, status = {}, {EXTERNAL: {"status": "external-control-needed", "label": "Server"}}
        now = self.clock()
        for uuid in INTEGRATED:
            sample = observations[uuid]
            sampled = sample.get("sampled")
            temperature_fresh = (valid_temperature(sample.get("temperature"))
                                 and type(sampled) in (int, float) and 0 <= now - sampled <= MAX_GAP)
            fresh = sample.get("ok") is True and temperature_fresh
            previous = self.last_sample[uuid]
            contiguous = fresh and previous is not None and 0 < sampled - previous <= MAX_GAP
            self.last_sample[uuid] = sampled if fresh else None
            cool = fresh and sample["temperature"] <= COOL
            if not cool:
                self.cool_since[uuid] = None
            elif not contiguous or self.cool_since[uuid] is None:
                self.cool_since[uuid] = sampled
            if sample.get("conflict") and not self.owned[uuid]:
                self.cool_since[uuid] = None
                status[uuid] = {"status": "degraded-controller-conflict", "sample": sample}
                continue
            if self.owned[uuid]:
                # Stop/watchdog/restart always boost. Never lower on an error or gap.
                release = (not stopping and uuid not in self.recover and cool
                           and self.cool_since[uuid] is not None
                           and sampled - self.cool_since[uuid] >= COOL_SECONDS)
                actions[uuid] = "default" if release else "boost"
                if not fresh or uuid in self.recover:
                    self.cool_since[uuid] = None
            elif temperature_fresh and sample["temperature"] >= HOT:
                # Persist manual intent before the first setter, including failed attempts.
                self.owned[uuid] = True
                if not self.readonly:
                    try:
                        self.store.save(self.owned)
                    except BaseException:
                        self.owned[uuid] = False
                        raise
                actions[uuid] = "boost"
            status[uuid] = {"status": "degraded" if not fresh else "observed", "sample": sample}
        if self.readonly:
            for uuid, action in actions.items():
                status[uuid]["would_do"] = action
            return status
        if self.stop_requested():
            actions = {uuid: "boost" for uuid in actions}
        results = self.jobs.batch(actions, self.owned) if actions else {}
        for uuid, action in actions.items():
            result = results[uuid]
            status[uuid]["action"], status[uuid]["result"] = action, result
            if result.get("ok") is not True or result.get("errors"):
                self.cool_since[uuid] = None
                status[uuid]["status"] = "degraded"
            else:
                self.recover.discard(uuid)
                if status[uuid]["status"] != "degraded":
                    status[uuid]["status"] = "boosted-intended-100" if action == "boost" else "firmware-default"
                if action == "default":
                    self.owned[uuid] = False
                    # Failure here leaves persisted intent true; restart reboosts conservatively.
                    self.store.save(self.owned)
                    self.cool_since[uuid] = None
        return status


class TransitionLog:
    """Categorical changes immediately; changing sensor values at most every 60s."""
    def __init__(self, clock=time.monotonic, emit=print):
        self.clock, self.emit = clock, emit
        self.signature, self.last = None, None

    def write(self, status):
        signature = json.dumps({uuid: {
            "status": entry.get("status"), "action": entry.get("action"),
            "errors": sorted(set(entry.get("sample", {}).get("errors", [])
                                 + entry.get("result", {}).get("errors", []))),
        } for uuid, entry in status.items()}, sort_keys=True)
        now = self.clock()
        if signature != self.signature or self.last is None or now - self.last >= 60:
            self.emit(json.dumps(status), flush=True)
            self.signature, self.last = signature, now


def notify(message):
    address = os.environ.get("NOTIFY_SOCKET")
    if address:
        if address.startswith("@"):
            address = "\0" + address[1:]
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as sock:
            sock.sendto(message.encode(), address)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("run", "failsafe", "capabilities", "dry-run"))
    parser.add_argument("--config", default=CONFIG)
    parser.add_argument("--state-dir", default=STATE_DIR)
    args = parser.parse_args(argv)
    if os.geteuid() != 0:
        raise SafetyError("root-required")
    read_config(args.config)
    readonly = args.mode in {"capabilities", "dry-run"}
    store = Store(args.state_dir, writable=not readonly)
    try:
        stopping = False
        controller = Controller(store, BoundedJobs(), readonly=readonly,
                                stop_requested=lambda: stopping)
        def stop(_signum, _frame):
            nonlocal stopping
            stopping = True
        signal.signal(signal.SIGTERM, stop)
        signal.signal(signal.SIGINT, stop)
        if args.mode != "run":
            print(json.dumps(controller.cycle(stopping=args.mode == "failsafe")), flush=True)
            return 0
        logger = TransitionLog()
        notify("READY=1")
        while not stopping:
            result = controller.cycle()
            logger.write(result)
            notify("WATCHDOG=1")
            # Sleep in small increments so clean stop reaches conservative failsafe promptly.
            deadline = time.monotonic() + POLL
            while not stopping and time.monotonic() < deadline:
                time.sleep(0.1)
        print(json.dumps(controller.cycle(stopping=True)), flush=True)
        return 0
    finally:
        store.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(json.dumps({"status": "degraded-fatal", "error": str(error)}), flush=True)
        raise SystemExit(1)
