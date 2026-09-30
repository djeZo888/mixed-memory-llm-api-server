"""Offline test-only file sink. Never imported by driver/source package."""
import os,json,threading
from pathlib import Path
from contract import canonical,require
class Journal:
    """Exclusive namespace consumed forever; fsync each ownership boundary, not each token."""
    def __init__(self, path, intent, **_fixture_only):
        self.path = Path(path)
        self.path.mkdir(mode=0o700)  # existing directory, including failed intent, rejects replay
        self.lock = threading.RLock()
        self.write('INTENT', intent, exclusive=True)
        self.sync_dir(self.path.parent)

    @staticmethod
    def sync_dir(path):
        fd = os.open(path, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    def write(self, name, value, exclusive=False):
        require(name and all(c.isalnum() or c in '-_' for c in name), 'invalid journal name')
        with self.lock:
            target = self.path/(name+'.json')
            temp = target if exclusive else self.path/(name+'.tmp')
            fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, 'wb') as f:
                f.write(canonical(value)+b'\n')
                f.flush()
                os.fsync(f.fileno())
            if not exclusive:
                os.replace(temp, target)
            self.sync_dir(self.path)


    def append(self, name, value):
        require(name and all(c.isalnum() or c in '-_' for c in name), 'invalid journal name')
        with self.lock:
            fd=os.open(self.path/(name+'.jsonl'),os.O_WRONLY|os.O_CREAT|os.O_APPEND|os.O_NOFOLLOW,0o600)
            with os.fdopen(fd,'wb') as f:
                f.write(canonical(value)+b'\n');f.flush();os.fsync(f.fileno())
