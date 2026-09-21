"""I1 stage-record API with I1b descriptor-anchored persistence.

State.run and its identity/record validation remain the I1 implementation.
This adapter only replaces path-based state I/O, independently of I1R Runner.
"""
from pathlib import Path
import uuid

from .core import State, InstallError, digest


class AnchoredState(State):
    def __init__(self, anchor, name, config, lock_hash, input_hash, guard, *, uid=0):
        self.anchor, self.name = anchor, name
        self.path, self.guard, self.uid = Path(anchor.path) / name, guard, uid
        self.identity = {"schema_version": 1, "config_hash": digest(config),
                         "lock_hash": lock_hash, "input_hash": input_hash}
        self.guard()
        if anchor.stat(name, missing_ok=True) is not None:
            self.value = anchor.read_json(name)
            if any(self.value.get(k) != v for k, v in self.identity.items()):
                raise InstallError("state_config_lock_or_source_changed")
            self._validate_records()
        else:
            self.value = {**self.identity, "installation_id": str(uuid.uuid4()), "stages": {}}

    def save(self):
        self.guard()
        self.anchor.atomic_json(self.name, self.value)
