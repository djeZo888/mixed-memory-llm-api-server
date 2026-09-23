#!/usr/bin/env python3
"""Read-only Ada NVML/proc sampler; the guarded launcher owns output storage.

The launcher must verify registered storage, open a private regular output file,
keep its anchored guard alive, and pass that descriptor with subprocess pass_fds.
This program never opens its output path for writing. CLI paths are fixed launcher
configuration, never values from an HTTP request. No GPU configuration or inference
API is called. Device samples are observations, not allocator/process peaks.
"""
from __future__ import annotations

import argparse
import ctypes
import datetime
import fcntl
import json
import math
import os
from pathlib import Path
import signal
import stat
import sys
import threading
import time


GPU_UUID = "GPU-5d895991-b794-2b4c-b9c4-5f1b668afd23"
DEVICE_INTERVAL = 0.2
HOST_INTERVAL = 1.0
MAX_PROC_BYTES = 128 * 1024


class Memory(ctypes.Structure):
    _fields_ = [("total", ctypes.c_ulonglong), ("free", ctypes.c_ulonglong),
                ("used", ctypes.c_ulonglong)]


class Utilization(ctypes.Structure):
    _fields_ = [("gpu", ctypes.c_uint), ("memory", ctypes.c_uint)]


class NVML:
    """Small typed ABI; optional library injection is only for local fixtures."""

    def __init__(self, library=None):
        self.library = library if library is not None else ctypes.CDLL("libnvidia-ml.so.1")
        self.handle = ctypes.c_void_p()
        self.initialized = False
        self.functions = {}
        handle = ctypes.c_void_p
        uintp = ctypes.POINTER(ctypes.c_uint)
        signatures = {
            "nvmlInit_v2": [], "nvmlShutdown": [],
            "nvmlDeviceGetHandleByUUID": [ctypes.c_char_p, ctypes.POINTER(handle)],
            "nvmlDeviceGetUUID": [handle, ctypes.POINTER(ctypes.c_char), ctypes.c_uint],
            "nvmlDeviceGetMemoryInfo": [handle, ctypes.POINTER(Memory)],
            "nvmlDeviceGetUtilizationRates": [handle, ctypes.POINTER(Utilization)],
            "nvmlDeviceGetPcieThroughput": [handle, ctypes.c_int, uintp],
            "nvmlDeviceGetCurrPcieLinkGeneration": [handle, uintp],
            "nvmlDeviceGetCurrPcieLinkWidth": [handle, uintp],
        }
        for name, args in signatures.items():
            function = getattr(self.library, name, None)
            if function is not None:
                function.argtypes, function.restype = args, ctypes.c_int
            self.functions[name] = function

    def call(self, name, *args):
        function = self.functions[name]
        if function is None:
            return {"function": name, "code": None, "error": "symbol_unavailable"}
        try:
            return {"function": name, "code": int(function(*args))}
        except (OSError, ctypes.ArgumentError) as error:
            return {"function": name, "code": None, "error": type(error).__name__}

    def start(self):
        result = {"init": self.call("nvmlInit_v2")}
        if result["init"]["code"] != 0:
            return result
        self.initialized = True
        result["handle"] = self.call("nvmlDeviceGetHandleByUUID", GPU_UUID.encode("ascii"),
                                     ctypes.byref(self.handle))
        if result["handle"]["code"] != 0:
            return result
        uuid = ctypes.create_string_buffer(96)
        result["identity"] = self.call("nvmlDeviceGetUUID", self.handle, uuid, len(uuid))
        if result["identity"]["code"] == 0:
            observed = uuid.value.decode("ascii", errors="replace")
            result["identity"].update(value=observed, matches_required_uuid=observed == GPU_UUID)
        return result

    def memory(self):
        value = Memory()
        result = self.call("nvmlDeviceGetMemoryInfo", self.handle, ctypes.byref(value))
        if result["code"] == 0:
            result["value"] = {name: int(getattr(value, name)) for name in ("total", "used", "free")}
        return result

    def utilization(self):
        value = Utilization()
        result = self.call("nvmlDeviceGetUtilizationRates", self.handle, ctypes.byref(value))
        if result["code"] == 0:
            result["value"] = {"gpu": int(value.gpu), "memory": int(value.memory)}
        return result

    def scalar(self, name, *arguments):
        value = ctypes.c_uint()
        result = self.call(name, self.handle, *arguments, ctypes.byref(value))
        if result["code"] == 0:
            result["value"] = int(value.value)
        return result

    def sample(self, stop):
        queries = (
            ("memory_bytes", self.memory, ()),
            ("utilization_percent", self.utilization, ()),
            # NVML counter enum: TX=0, RX=1; returned units are KB/s.
            ("pcie_tx_kb_per_s", self.scalar, ("nvmlDeviceGetPcieThroughput", 0)),
            ("pcie_rx_kb_per_s", self.scalar, ("nvmlDeviceGetPcieThroughput", 1)),
            ("pcie_link_generation", self.scalar, ("nvmlDeviceGetCurrPcieLinkGeneration",)),
            ("pcie_link_width", self.scalar, ("nvmlDeviceGetCurrPcieLinkWidth",)),
        )
        result = {}
        for key, function, arguments in queries:
            if stop.is_set():
                break
            result[key] = function(*arguments)
        return result

    def close(self):
        if self.initialized:
            self.initialized = False
            return self.call("nvmlShutdown")
        return {"function": "nvmlShutdown", "code": None, "error": "not_initialized"}


def read_bounded(path, maximum=MAX_PROC_BYTES):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        chunks, length = [], 0
        while length <= maximum:
            chunk = os.read(fd, min(16384, maximum + 1 - length))
            if not chunk:
                break
            chunks.append(chunk)
            length += len(chunk)
        if length > maximum:
            raise ValueError("read_limit_exceeded")
        return b"".join(chunks).decode("ascii")
    finally:
        os.close(fd)


def observed_read(function):
    try:
        return {"status": "ok", "value": function()}
    except (OSError, ValueError, UnicodeError) as error:
        result = {"status": "unavailable", "error": type(error).__name__}
        if isinstance(error, OSError):
            result["errno"] = error.errno
        return result


def proc_values(path, fields, *, kib=False):
    values = {}
    for line in read_bounded(path).splitlines():
        parts = line.split()
        if not parts or parts[0].rstrip(":") not in fields:
            continue
        key = parts[0].rstrip(":")
        if (len(parts) != (3 if kib else 2) or not parts[1].isdigit()
                or kib and parts[2] != "kB" or key in values):
            raise ValueError("invalid_proc_value")
        values[key] = int(parts[1]) * (1024 if kib else 1)
    return {"values": values, "missing": sorted(set(fields) - values.keys())}


def host_sample(cgroup, stop):
    result = {}
    queries = (
        ("meminfo_bytes", lambda: proc_values("/proc/meminfo",
            {"MemTotal", "MemAvailable", "SwapTotal", "SwapFree"}, kib=True)),
        ("vmstat_counters", lambda: proc_values("/proc/vmstat",
            {"pswpin", "pswpout", "pgmajfault", "oom_kill"})),
    )
    for key, query in queries:
        if stop.is_set():
            return result
        result[key] = observed_read(query)
    if cgroup is not None:
        result["cgroup_bytes"] = {}
        for name in ("memory.current", "memory.peak", "memory.swap.current"):
            if stop.is_set():
                break
            def read_number(name=name):
                value = read_bounded(cgroup / name, 128).strip()
                if not value.isdigit():
                    raise ValueError("invalid_cgroup_value")
                return int(value)
            result["cgroup_bytes"][name] = observed_read(read_number)
    return result


def timestamp():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="microseconds")


def output_stream(fd, path):
    """Validate the launcher's existing file, then duplicate only its descriptor."""
    target = Path(path)
    if not target.is_absolute() or str(target) != path or ".." in target.parts:
        raise ValueError("invalid_output_path")
    info, named = os.fstat(fd), target.stat(follow_symlinks=False)
    access = fcntl.fcntl(fd, fcntl.F_GETFL) & os.O_ACCMODE
    if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.geteuid()
            or info.st_mode & 0o077 or (info.st_dev, info.st_ino) != (named.st_dev, named.st_ino)
            or not stat.S_ISREG(named.st_mode) or access not in (os.O_WRONLY, os.O_RDWR)
            or target.resolve(strict=True) != target):
        raise ValueError("output_descriptor_identity_invalid")
    return os.fdopen(os.dup(fd), "w", buffering=65536, encoding="utf-8")


def run(stream, cgroup, stop, *, library=None):
    """Return a status code; startup/query errors remain explicit in JSONL."""
    def emit(value):
        stream.write(json.dumps(value, separators=(",", ":"), allow_nan=False) + "\n")
    started = time.monotonic()
    nvml = None
    count = 0
    summary = {"sampled_max_used_bytes": None, "sampled_min_free_bytes": None,
               "max_sample_interval_s": None, "max_query_duration_s": 0.0,
               "skipped_schedule_slots": 0}
    try:
        if stop.is_set():
            return 0
        try:
            nvml = NVML(library)
        except OSError as error:
            emit({"event": "startup_failed", "utc": timestamp(), "monotonic_s": time.monotonic(),
                  "error": "nvml_library_unavailable", "errno": error.errno})
            return 2
        startup = nvml.start()
        emit({"event": "start", "utc": timestamp(), "monotonic_s": started,
              "gpu_uuid": GPU_UUID, "device_interval_s": DEVICE_INTERVAL,
              "host_interval_s": HOST_INTERVAL, "cgroup": str(cgroup) if cgroup else None,
              "nvml": startup, "scope": "sampled_device_totals_not_process_or_allocator_peaks",
              "pcie_counter_window_ms": 20,
              "utilization_window": "NVML product-dependent sample period, not necessarily 200ms",
              "cgroup_peak_scope": "Observed cgroup lifetime peak; sampler does not reset it",
              "peak_limit": "Peaks between samples or during driver stalls are unobserved."})
        stream.flush()
        if startup.get("identity", {}).get("matches_required_uuid") is not True:
            return 2
        due = host_due = flush_due = time.monotonic()
        previous = None
        while not stop.is_set():
            if stop.wait(max(0.0, due - time.monotonic())):
                break
            now = time.monotonic()
            interval = None if previous is None else now - previous
            record = {"event": "sample", "sequence": count, "utc": timestamp(),
                      "monotonic_s": now, "scheduled_monotonic_s": due,
                      "lateness_s": max(0.0, now - due), "interval_s": interval,
                      "excess_interval_s": None if interval is None else max(0.0, interval - DEVICE_INTERVAL),
                      "device": nvml.sample(stop)}
            if now >= host_due and not stop.is_set():
                record["host"] = host_sample(cgroup, stop)
                host_due += (math.floor((time.monotonic() - host_due) / HOST_INTERVAL) + 1) * HOST_INTERVAL
            finished = time.monotonic()
            record["query_finished_monotonic_s"] = finished
            record["query_duration_s"] = finished - now
            record["interrupted"] = stop.is_set()
            emit(record)
            count += 1
            previous = now
            memory = record["device"].get("memory_bytes", {})
            if memory.get("code") == 0:
                for key, field, aggregate in (("sampled_max_used_bytes", "used", max),
                                               ("sampled_min_free_bytes", "free", min)):
                    value = memory["value"][field]
                    summary[key] = value if summary[key] is None else aggregate(summary[key], value)
            if interval is not None:
                summary["max_sample_interval_s"] = max(summary["max_sample_interval_s"] or 0, interval)
            summary["max_query_duration_s"] = max(summary["max_query_duration_s"], finished - now)
            if finished >= flush_due:
                stream.flush()
                flush_due += (math.floor((finished - flush_due) / HOST_INTERVAL) + 1) * HOST_INTERVAL
            due += DEVICE_INTERVAL
            if due <= finished:
                skipped = math.floor((finished - due) / DEVICE_INTERVAL) + 1
                due += skipped * DEVICE_INTERVAL
                summary["skipped_schedule_slots"] += skipped
        return 0
    finally:
        shutdown = nvml.close() if nvml is not None else None
        emit({"event": "stop", "utc": timestamp(), "monotonic_s": time.monotonic(),
              "elapsed_s": time.monotonic() - started, "samples": count,
              "signal_stop_requested": stop.is_set(), "nvml_shutdown": shutdown, **summary})
        stream.flush()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-fd", type=int, required=True)
    parser.add_argument("--output-path", required=True)
    parser.add_argument("--cgroup", help="fixed launcher-owned cgroup v2 directory under /sys/fs/cgroup")
    args = parser.parse_args(argv)
    cgroup = Path(args.cgroup) if args.cgroup else None
    if cgroup is not None and (not cgroup.is_absolute() or ".." in cgroup.parts
            or str(cgroup) != args.cgroup or not cgroup.is_relative_to("/sys/fs/cgroup")
            or cgroup == Path("/sys/fs/cgroup") or cgroup.resolve() != cgroup):
        parser.error("invalid cgroup path")
    stop = threading.Event()
    def interrupted(_signum, _frame):
        stop.set()
    handlers = {number: signal.signal(number, interrupted) for number in (signal.SIGTERM, signal.SIGINT)}
    try:
        with output_stream(args.output_fd, args.output_path) as stream:
            return run(stream, cgroup, stop)
    except (OSError, ValueError) as error:
        print(json.dumps({"event": "sampler_failed", "error": type(error).__name__}), file=sys.stderr)
        return 2
    finally:
        for number, handler in handlers.items():
            signal.signal(number, handler)


if __name__ == "__main__":
    raise SystemExit(main())
