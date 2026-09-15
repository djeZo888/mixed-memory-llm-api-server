"""Explicit U1 port for independent tests, NOT an extracted Manager API.

Only a reviewed production adapter may translate this port into the frozen L1
loader/prepare_start/dispatch calls. No command-line fixture or injection seam
is provided. Implementations must bound each call by the supplied deadline;
preflight and transitions run in the canonical lease-owning executor thread.
"""
from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Protocol


class ControlError(Exception):
    def __init__(self, code: str, status: int = 503):
        self.code, self.status = code, status
        super().__init__(code)


class StorageUnavailable(ControlError):
    def __init__(self):
        super().__init__("storage_unavailable")


class PackageBlocked(ControlError):
    def __init__(self):
        super().__init__("package_admission_unavailable")


@dataclass(frozen=True)
class Deadline:
    end: float

    @classmethod
    def after(cls, seconds: float) -> "Deadline":
        return cls(time.monotonic() + seconds)

    def remaining(self) -> float:
        remaining = self.end - time.monotonic()
        if remaining <= 0:
            raise ControlError("deadline_exceeded")
        return remaining


class Session(Protocol):
    """In-process trusted port, never populated by HTTP input.

    observe supplies fresh trusted L1-style state plus four explicit ready_proof
    booleans. Recovery sessions additionally attest recovery_trusted=True only
    after exact protected /run immutable journal validation. catalog supplies
    small registered-profile/acquisition DTOs, never a weight walk/hash.
    """
    def observe(self, deadline: Deadline) -> dict: ...
    def catalog(self, deadline: Deadline) -> list[dict]: ...
    def check_admission(self, lease, deadline: Deadline) -> None: ...
    def preflight(self, target: str, lease, deadline: Deadline) -> None: ...
    def stop(self, lease, deadline: Deadline) -> None: ...
    def select(self, target: str, lease, deadline: Deadline) -> None: ...
    def start(self, lease, deadline: Deadline) -> None: ...


class Backend(Protocol):
    def open(self, *, recovery: bool = False) -> Session: ...
