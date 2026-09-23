"""No-follow protected config, source, credential and singleton descriptors."""
import fcntl
import os
from pathlib import Path
import re
import stat

CONFIG = Path('/etc/llm-server/image-api.json')
CREDENTIAL = Path('/run/credentials/llm-image-api.service/inference-key')
SOURCE = Path('/usr/local/lib/llm-server/image-api/scripts/image_api')
LOCK = Path('/run/llm-image-api/owner.lock')


class ProtectionError(Exception):
    pass


def protected(path, *, modes, maximum, credential=False):
    """Anchored descent rejects symlinks, mutable ancestry and read-time races."""
    if not path.is_absolute() or '..' in path.parts:
        raise ProtectionError()
    directory = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for index, part in enumerate(path.parts[1:-1], 1):
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            os.close(directory)
            directory = child
            meta = os.fstat(directory)
            owners = {0, os.geteuid()} if credential and index == len(path.parts) - 2 else {0}
            if meta.st_uid not in owners or meta.st_mode & 0o022:
                raise ProtectionError()
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        try:
            before = os.fstat(fd)
            owners = {0, os.geteuid()} if credential else {0}
            if (not stat.S_ISREG(before.st_mode) or before.st_uid not in owners or before.st_nlink != 1
                    or stat.S_IMODE(before.st_mode) not in modes or before.st_size > maximum
                    or credential and stat.S_IMODE(before.st_mode) == 0o440
                    and (before.st_uid != 0 or before.st_gid != 0)):
                raise ProtectionError()
            raw = os.read(fd, maximum + 1)
            signature = lambda s: (s.st_dev, s.st_ino, s.st_mode, s.st_uid, s.st_gid, s.st_nlink,
                                   s.st_size, s.st_mtime_ns, s.st_ctime_ns)
            if (len(raw) != before.st_size or signature(before) != signature(os.fstat(fd))
                    or signature(before) != signature(os.stat(path.name, dir_fd=directory, follow_symlinks=False))):
                raise ProtectionError()
            return raw
        finally:
            os.close(fd)
    except OSError:
        raise ProtectionError() from None
    finally:
        os.close(directory)


def key():
    raw = protected(CREDENTIAL, modes={0o400, 0o440, 0o600}, maximum=257, credential=True)
    value = raw[:-1] if raw.endswith(b'\n') else raw
    if not re.fullmatch(rb'[A-Za-z0-9._~+/=-]{32,256}', value):
        raise ProtectionError()
    return value


def installation():
    if os.geteuid() == 0 or Path(__file__).absolute().parent != SOURCE:
        raise ProtectionError()
    for name in ('__init__.py', 'serve.py', 'protection.py', 'protocol.py', 'uploads.py', 'backend.py', 'app.py'):
        protected(SOURCE / name, modes={0o644}, maximum=131072)
    protected(Path('/usr/local/libexec/llm-image-backend-recover'), modes={0o755}, maximum=1048576)
    return protected(CONFIG, modes={0o644}, maximum=131072), key()


def singleton():
    # systemd RuntimeDirectory, transient state only, no data/spool writes.
    directory = os.open(LOCK.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        parent = os.fstat(directory)
        if parent.st_uid != os.geteuid() or stat.S_IMODE(parent.st_mode) != 0o700:
            raise ProtectionError()
        fd = os.open(LOCK.name, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK,
                     0o600, dir_fd=directory)
        meta = os.fstat(fd)
        try:
            if (not stat.S_ISREG(meta.st_mode) or meta.st_uid != os.geteuid() or meta.st_nlink != 1
                    or stat.S_IMODE(meta.st_mode) != 0o600):
                raise ProtectionError()
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return fd
        except BaseException:
            os.close(fd)
            raise
    finally:
        os.close(directory)
