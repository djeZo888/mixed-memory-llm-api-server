"""Passive Linux /proc counters. Four fixed collectors; no app data or commands."""
from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
import re
import threading
import time

FIELDS = {
    "cpu": ("percent", "logical_count"),
    "memory": ("total_bytes", "available_bytes", "swap_total_bytes", "swap_free_bytes", "pressure_some_avg10", "pressure_full_avg10"),
    "disk": ("total_bytes", "available_bytes", "read_bytes_per_second", "write_bytes_per_second"),
    "network": ("rx_bytes_per_second", "tx_bytes_per_second"),
}


def read_proc(path):
    # All callers use fixed paths. Cap parsed source bytes; never read process argv.
    with open(path, encoding="ascii") as stream:
        value = stream.read(262145)
    if len(value) > 262144:
        raise ValueError("counter source too large")
    return value


class ProcResources:
    def __init__(self, read=read_proc, statvfs=os.statvfs, root_device=lambda: os.stat("/").st_dev,
                 monotonic=time.monotonic):
        self.read, self.statvfs, self.root_device, self.monotonic = read, statvfs, root_device, monotonic
        self.previous = {}

    def delta(self, component, values):
        now = self.monotonic()
        prior = self.previous.get(component)
        self.previous[component] = (now, values)
        if prior is None or now <= prior[0] or any(a < b for a, b in zip(values, prior[1])):
            return None
        return [(a - b) / (now - prior[0]) for a, b in zip(values, prior[1])]

    def observe(self, component):
        if component == "cpu":
            lines = self.read("/proc/stat").splitlines()
            fields = next(line for line in lines if line.startswith("cpu ")).split()[1:9]
            counters = list(map(int, fields))
            rates = self.delta(component, (sum(counters), counters[3] + counters[4]))
            percent = None if rates is None or rates[0] <= 0 else max(0, min(100, 100 * (rates[0] - rates[1]) / rates[0]))
            return {"percent": percent, "logical_count": sum(bool(re.match(r"cpu[0-9]+ ", line)) for line in lines)}
        if component == "memory":
            values = {}
            for line in self.read("/proc/meminfo").splitlines():
                key, value = line.split(":", 1)
                if key in {"MemTotal", "MemAvailable", "SwapTotal", "SwapFree"}:
                    fields = value.split()
                    if fields[1:] != ["kB"]:
                        raise ValueError("unknown memory units")
                    values[key] = int(fields[0]) * 1024
            pressure = {}
            try:
                for line in self.read("/proc/pressure/memory").splitlines():
                    fields = line.split()
                    pressure[fields[0]] = float(dict(field.split("=") for field in fields[1:])["avg10"])
            except (OSError, ValueError, KeyError):
                pass
            return {"total_bytes": values["MemTotal"], "available_bytes": values["MemAvailable"],
                    "swap_total_bytes": values["SwapTotal"], "swap_free_bytes": values["SwapFree"],
                    "pressure_some_avg10": pressure.get("some"), "pressure_full_avg10": pressure.get("full")}
        if component == "disk":
            capacity = self.statvfs("/")
            device = self.root_device()
            counters = None
            for line in self.read("/proc/diskstats").splitlines():
                fields = line.split()
                if len(fields) >= 14 and (int(fields[0]), int(fields[1])) == (os.major(device), os.minor(device)):
                    counters = (int(fields[5]) * 512, int(fields[9]) * 512)
                    break
            rates = self.delta(component, counters) if counters is not None else None
            return {"total_bytes": capacity.f_blocks * capacity.f_frsize,
                    "available_bytes": capacity.f_bavail * capacity.f_frsize,
                    "read_bytes_per_second": rates[0] if rates else None, "write_bytes_per_second": rates[1] if rates else None}
        if component == "network":
            rx, tx = 0, 0
            for line in self.read("/proc/net/dev").splitlines():
                if ":" not in line:
                    continue
                name, data = line.split(":", 1)
                if name.strip() == "lo":
                    continue
                fields = data.split()
                rx += int(fields[0])
                tx += int(fields[8])
            rates = self.delta(component, (rx, tx))
            return {"rx_bytes_per_second": rates[0] if rates else None, "tx_bytes_per_second": rates[1] if rates else None}
        raise ValueError("unknown component")


class ResourceCache:
    def __init__(self, observe, clock=time.time, monotonic=time.monotonic):
        self.observe, self.clock, self.monotonic = observe, clock, monotonic
        self.values, self.started = {}, {}
        self.lock = threading.Lock()

    def refresh(self, component):
        with self.lock:
            if component in self.started:
                return False
            self.started[component] = self.monotonic()
        try:
            values = self.observe(component)
            if set(values) != set(FIELDS[component]):
                raise ValueError("invalid fields")
            self.values[component] = {"values": values, "at": self.clock(), "monotonic": self.monotonic(), "state": "ok", "reason": None}
            return True
        except Exception:
            prior = self.values.get(component)
            if prior:
                self.values[component] = {**prior, "state": "error", "reason": "resource_observation_unavailable"}
            return False
        finally:
            with self.lock:
                self.started.pop(component, None)

    def snapshot(self):
        result = {}
        for component, fields in FIELDS.items():
            value = self.values.get(component)
            age = max(0, round((self.monotonic() - value["monotonic"]) * 1000)) if value else None
            item = {"state": value["state"] if value else "unknown",
                    "observed_at": datetime.fromtimestamp(value["at"], timezone.utc).isoformat().replace("+00:00", "Z") if value else None,
                    "age_ms": age, "freshness": "unknown" if age is None else "fresh" if age <= 15000 else "stale",
                    "reason": value["reason"] if value else "not_observed", **{field: None for field in fields}}
            if value:
                item.update(value["values"])
            started = self.started.get(component)
            if started is not None and self.monotonic() - started > 2:
                item.update(state="timeout", reason="resource_observation_timeout")
            result[component] = item
        return result

    def start(self):
        def poll(component):
            while True:
                started = self.monotonic()
                self.refresh(component)
                time.sleep(max(0, 5 - (self.monotonic() - started)))
        for component in FIELDS:
            threading.Thread(target=poll, args=(component,), daemon=True).start()
