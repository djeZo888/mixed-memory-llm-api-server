#!/usr/bin/env python3
"""Q38A-only pinned image pull. No container creation, runtime imports or services.

Run with /usr/bin/python3 -I -B after the acquisition plan and guard proof.
All persistent output is anchored below the existing task directory on /data.
Docker owns layer storage; cancellation stops this CLI and requests daemon pull
cancellation, but cannot attest instantaneous daemon cancellation.
"""
import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import selectors
import signal
import stat
import subprocess
import sys
import time
import uuid

sys.dont_write_bytecode = True
REPO = Path(__file__).resolve().parents[2]
TASK = Path('/data/build/q38a-20260915')
MODEL_UUID = 'a6d4ab58-84e1-4e48-9a67-13ad1c6f6e0a'
IMAGE = 'lmsysorg/sglang@sha256:37bbbd3444732a464bbc68dee4fb0164e0ce9e18e2f027f3fc967f1152d3c262'
CONFIG_ID = 'sha256:e6238090791a938ab86dd21a9a6394192dad15237e815df557cf83524d54b813'
MANIFEST_ID = IMAGE.split('@', 1)[1]
MANIFEST_BYTES = 13686
CONFIG_BYTES = 65818
SOURCE = '0bcd822377da7b5718e674eaf9c870d349424dd1'
MIN_DATA_FREE = 4 * 1024**3
MIN_START_FREE = 200 * 1024**3
PULL_TIMEOUT = 3 * 60 * 60
INSPECT_TEMPLATE = ('{"Id":{{json .Id}},"RepoDigests":{{json .RepoDigests}},'
                    '"Os":{{json .Os}},"Architecture":{{json .Architecture}},'
                    '"Size":{{json .Size}},"source_revision":'
                    '{{json (index .Config.Labels "org.opencontainers.image.revision")}}}')


class ImageStop(RuntimeError):
    """Static locally authored failure text, safe for the task status."""


def storage_module():
    spec = importlib.util.spec_from_file_location('q38a_d1_storage', REPO / 'scripts/d1/storage_guard.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def verify_provenance():
    runtime = json.loads((REPO / 'reports/q38s-provenance.json').read_text())['runtime']
    if (runtime['image_reference'] != IMAGE or runtime['config']['digest'] != CONFIG_ID
            or runtime['manifest']['digest'] != MANIFEST_ID
            or runtime['manifest']['size_bytes'] != MANIFEST_BYTES
            or runtime['config']['size_bytes'] != CONFIG_BYTES
            or runtime['platform'] != {'os': 'linux', 'architecture': 'amd64'}
            or runtime['source_commit'] != SOURCE):
        raise ImageStop('reviewed image provenance mismatch')


def open_directory(path):
    """Open every component without following links; return fd and path identities."""
    path = Path(path)
    if not path.is_absolute() or '..' in path.parts:
        raise ImageStop('absolute contained path required')
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    identities = {}
    current = Path('/')
    try:
        for part in path.parts[1:]:
            nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = nxt
            current /= part
            item = os.fstat(fd)
            identities[str(current)] = (item.st_dev, item.st_ino)
        return fd, identities
    except BaseException:
        os.close(fd)
        raise


def identities_unchanged(identities):
    for path, expected in identities.items():
        item = os.lstat(path)
        if not stat.S_ISDIR(item.st_mode) or (item.st_dev, item.st_ino) != expected:
            raise ImageStop('anchored directory changed')


def protected_subdir(parent, name):
    try:
        os.mkdir(name, 0o700, dir_fd=parent)
    except FileExistsError:
        pass
    fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
    item = os.fstat(fd)
    # /data/build inherits setgid. That bit changes group inheritance only;
    # neither accepted mode grants any group/other access to this root directory.
    if item.st_uid != 0 or stat.S_IMODE(item.st_mode) not in (0o700, 0o2700):
        os.close(fd)
        raise ImageStop('task image directory must be root-owned mode 0700 or 2700')
    return fd


def safe_regular(fd, expected_dev):
    item = os.fstat(fd)
    if (not stat.S_ISREG(item.st_mode) or item.st_nlink != 1 or item.st_uid != 0
            or item.st_mode & 0o077 or item.st_dev != expected_dev):
        raise ImageStop('unsafe task output file')


def previous_status(fd):
    try:
        previous = os.open('status.json', os.O_RDONLY | os.O_NOFOLLOW, dir_fd=fd)
    except FileNotFoundError:
        previous = None
    if previous is not None:
        with os.fdopen(previous, 'r') as stream:
            safe_regular(stream.fileno(), os.fstat(fd).st_dev)
            old = json.loads(stream.read(65537))
            if old.get('task') != 'Q38A' or old.get('image_reference') != IMAGE:
                raise ImageStop('foreign task image status')
            return old
    return None


def atomic_status(fd, record):
    previous_status(fd)
    name = '.image-status-' + uuid.uuid4().hex
    out = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd)
    with os.fdopen(out, 'w') as stream:
        json.dump(record, stream, sort_keys=True)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(name, 'status.json', src_dir_fd=fd, dst_dir_fd=fd)
    os.fsync(fd)


def mount_ids():
    result = []
    for path in ('/data', '/data/models-large'):
        value = subprocess.check_output(
            ['/usr/bin/findmnt', '-n', '-M', path, '-o', 'ID'],
            text=True, stderr=subprocess.DEVNULL, timeout=15).strip()
        if not value.isdigit():
            raise ImageStop('ambiguous mount identity')
        result.append(value)
    return result


def command_environment(fd):
    anchor = '/proc/self/fd/' + str(fd)
    env = {'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LANG': 'C.UTF-8',
           'DOCKER_CONFIG': anchor + '/docker-config', 'TMPDIR': anchor + '/tmp',
           'XDG_CACHE_HOME': anchor + '/cache'}
    if 'HOME' in os.environ:
        env['HOME'] = os.environ['HOME']
    return env


def docker_command(fd, *args):
    return ['/usr/bin/docker', '--config', '/proc/self/fd/' + str(fd) + '/docker-config',
            '--host', 'unix:///run/docker.sock', *args]


def narrow_image(raw, content_proof):
    item = json.loads(raw)
    keys = {'Id', 'RepoDigests', 'Os', 'Architecture', 'Size', 'source_revision'}
    if (set(item) != keys or item['Id'] not in (CONFIG_ID, MANIFEST_ID)
            or (item['Os'], item['Architecture'], item['source_revision']) != ('linux', 'amd64', SOURCE)
            or content_proof != expected_content_proof()):
        raise ImageStop('installed identity/platform/source or stored content proof mismatch')
    if not isinstance(item['RepoDigests'], list) or IMAGE not in item['RepoDigests']:
        raise ImageStop('installed RepoDigests lacks exact distribution manifest')
    if type(item['Size']) is not int or item['Size'] <= 0:
        raise ImageStop('invalid installed image size')
    # Emit only the approved RepoDigest, never unrelated locally attached names.
    item['RepoDigests'] = [IMAGE]
    item['Id_kind'] = 'config_digest' if item['Id'] == CONFIG_ID else 'platform_manifest_digest'
    return item


def expected_content_proof():
    return {'manifest_sha256': MANIFEST_ID, 'manifest_bytes': MANIFEST_BYTES,
            'config_sha256': CONFIG_ID, 'config_bytes': CONFIG_BYTES,
            'platform': 'linux/amd64', 'source_revision': SOURCE,
            'verification': 'STORED_PAYLOAD_BYTES_SHA256_MATCH'}


def verify_stored_metadata(manifest_raw, config_raw):
    for payload, size, digest in ((manifest_raw, MANIFEST_BYTES, MANIFEST_ID),
                                  (config_raw, CONFIG_BYTES, CONFIG_ID)):
        if len(payload) != size or 'sha256:' + hashlib.sha256(payload).hexdigest() != digest:
            raise ImageStop('stored OCI metadata length or computed SHA256 mismatch')
    manifest, config = json.loads(manifest_raw), json.loads(config_raw)
    if (manifest.get('schemaVersion') != 2 or manifest.get('config', {}).get('digest') != CONFIG_ID
            or manifest['config'].get('size') != CONFIG_BYTES
            or (config.get('os'), config.get('architecture')) != ('linux', 'amd64')
            or config.get('config', {}).get('Labels', {}).get('org.opencontainers.image.revision') != SOURCE):
        raise ImageStop('stored OCI descriptor/platform/source mismatch')
    # Full public config is never returned or logged; only these approved fields.
    return expected_content_proof()


def content_command(digest):
    if digest not in (MANIFEST_ID, CONFIG_ID):
        raise ImageStop('unapproved metadata digest')
    return ['/usr/bin/ctr', '--address', '/run/containerd/containerd.sock',
            '--namespace', 'moby', 'content', 'get', digest]


def read_content(fd, digest, size, guard):
    """Read at most the exact expected metadata size plus one byte, within 60s."""
    process = subprocess.Popen(content_command(digest), env=command_environment(fd),
                               pass_fds=(fd,), stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    payload = bytearray()
    deadline = time.monotonic() + 60
    try:
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            while True:
                guard()
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise ImageStop('stored OCI metadata read timeout')
                if not selector.select(min(5, remaining)):
                    continue
                chunk = os.read(process.stdout.fileno(), min(65536, size + 1 - len(payload)))
                if not chunk:
                    break
                payload.extend(chunk)
                if len(payload) > size:
                    raise ImageStop('stored OCI metadata oversized')
        if process.wait(timeout=max(0.1, deadline - time.monotonic())) != 0:
            raise ImageStop('stored OCI metadata read failed')
        return bytes(payload)
    finally:
        stop_child(process)
        process.stdout.close()


def stop_child(child):
    if child is None or child.poll() is not None:
        return
    child.terminate()
    try:
        child.wait(timeout=10)
    except subprocess.TimeoutExpired:
        child.kill()
        child.wait(timeout=10)


def monitor_pull(child, guard, heartbeat, timeout=PULL_TIMEOUT):
    started = time.monotonic()
    next_log = started + 30
    try:
        while child.poll() is None:
            guard()
            elapsed = time.monotonic() - started
            if elapsed > timeout:
                raise ImageStop('bounded pull timeout')
            if time.monotonic() >= next_log:
                heartbeat(int(elapsed))
                next_log = time.monotonic() + 30
            time.sleep(5)
    except BaseException:
        stop_child(child)
        raise


def run(verify_only=False):
    if os.geteuid() != 0:
        raise ImageStop('root execution required')
    os.umask(0o077)
    verify_provenance()
    storage = storage_module()
    storage.check(MODEL_UUID)
    initial_mounts = mount_ids()
    taskfd, identities = open_directory(TASK)
    imagefd = protected_subdir(taskfd, 'image')
    identities[str(TASK / 'image')] = (os.fstat(imagefd).st_dev, os.fstat(imagefd).st_ino)
    if os.fstat(imagefd).st_dev != os.stat('/data').st_dev:
        raise ImageStop('task image directory not on /data')
    child = None
    record = {'schema_version': 1, 'task': 'Q38A', 'pid': os.getpid(), 'state': 'PREFLIGHT',
              'image_reference': IMAGE, 'expected_config_id': CONFIG_ID, 'platform': 'linux/amd64',
              'Q38B_auth': 'NOT_TESTED', 'inference': 'NOT_TESTED', 'mount_ids': initial_mounts}
    record['verification_mode'] = 'read_only' if verify_only else 'pull_and_verify'
    lock = os.open('pull.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600, dir_fd=imagefd)
    safe_regular(lock, os.fstat(imagefd).st_dev)
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    log = os.open('events.jsonl', os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW, 0o600, dir_fd=imagefd)
    safe_regular(log, os.fstat(imagefd).st_dev)

    def publish():
        record['updated_unix'] = int(time.time())
        atomic_status(imagefd, record)
        os.write(log, (json.dumps(record, sort_keys=True) + '\n').encode())
        os.fsync(log)

    def guard():
        storage.check(MODEL_UUID)
        if mount_ids() != initial_mounts:
            raise ImageStop('mount identity changed')
        identities_unchanged(identities)
        usage = os.statvfs(imagefd)
        if usage.f_bavail * usage.f_frsize < MIN_DATA_FREE:
            raise ImageStop('/data free space below 4 GiB reserve')

    def common(phase):
        guard()
        env = command_environment(imagefd)
        for args in ([str(REPO / 'scripts/common/require-data-mounted.sh')],
                     [str(REPO / 'scripts/common/root-disk-guard.sh'), '--report',
                      '/proc/self/fd/' + str(imagefd) + '/' + phase + '-root-guard.md']):
            subprocess.run(args, check=True, timeout=300, env=env, pass_fds=(imagefd,),
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        guard()

    def capture(*args):
        return subprocess.check_output(docker_command(imagefd, *args), text=True,
                                       env=command_environment(imagefd), pass_fds=(imagefd,),
                                       stderr=subprocess.DEVNULL, timeout=60)

    try:
        guard()
        old = previous_status(imagefd)
        if verify_only:
            lineage = old if old and old.get('pull_exit_code') == 0 else (old or {}).get('prior_attempt', {})
            if lineage.get('pull_exit_code') != 0:
                raise ImageStop('verify-only requires recorded successful task pull')
            record['prior_attempt'] = {key: lineage[key] for key in (
                'pid', 'pull_pid', 'pull_exit_code', 'state', 'updated_unix', 'failure_class', 'failure_reason')
                if key in lineage}
        for name in ('docker-config', 'tmp', 'cache'):
            subfd = protected_subdir(imagefd, name)
            if name == 'docker-config' and os.listdir(subfd):
                raise ImageStop('Docker config must remain empty')
            os.close(subfd)
        common('verify-pre' if verify_only else 'pre')
        publish()  # Validate existing task state before any Docker pull is started.
        socket = os.lstat('/run/docker.sock')
        if not stat.S_ISSOCK(socket.st_mode) or socket.st_uid != 0:
            raise ImageStop('trusted local Docker socket required')
        data_root = Path(capture('info', '--format', '{{.DockerRootDir}}').strip())
        if not data_root.is_absolute() or '/data' not in [str(p) for p in data_root.parents]:
            raise ImageStop('Docker data-root must be below /data')
        dockerfd, docker_identities = open_directory(data_root)
        try:
            if os.fstat(dockerfd).st_dev != os.stat('/data').st_dev:
                raise ImageStop('Docker data-root not on the exact /data filesystem')
        finally:
            os.close(dockerfd)
        identities.update(docker_identities)
        guard()
        capacity = os.statvfs(imagefd)
        record['data_free_bytes_at_check'] = capacity.f_bavail * capacity.f_frsize
        if not verify_only and record['data_free_bytes_at_check'] < MIN_START_FREE:
            raise ImageStop('/data startup capacity below approved 200 GiB allowance')
        record['docker_data_root'] = str(data_root)
        if not verify_only:
            record['state'] = 'PULLING'
            child = subprocess.Popen(docker_command(imagefd, 'pull', '--platform', 'linux/amd64', IMAGE),
                                     env=command_environment(imagefd), pass_fds=(imagefd,),
                                     cwd='/proc/self/fd/' + str(imagefd),
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            record['pull_pid'] = child.pid
            publish()

            def heartbeat(elapsed):
                record['elapsed_seconds'] = elapsed
                publish()

            monitor_pull(child, guard, heartbeat)
            record['pull_exit_code'] = child.returncode
            if child.returncode != 0:
                raise ImageStop('Docker pull failed; raw output suppressed')
        guard()
        socket = os.lstat('/run/containerd/containerd.sock')
        if not stat.S_ISSOCK(socket.st_mode) or socket.st_uid != 0:
            raise ImageStop('trusted local containerd socket required')
        record['state'] = 'VERIFYING_STORED_METADATA'
        publish()
        proof = verify_stored_metadata(read_content(imagefd, MANIFEST_ID, MANIFEST_BYTES, guard),
                                       read_content(imagefd, CONFIG_ID, CONFIG_BYTES, guard))
        record['stored_content_proof'] = proof
        record['actual_image'] = narrow_image(capture('image', 'inspect', '--format', INSPECT_TEMPLATE, IMAGE), proof)
        common('verify-post' if verify_only else 'post')
        record['state'] = 'COMPLETE'
        publish()
        return record
    except BaseException as exc:
        stop_child(child)
        record['state'] = 'STOP'
        # Never stringify tool exceptions: they can include credential-bearing output.
        record['failure_class'] = type(exc).__name__
        if isinstance(exc, ImageStop):
            record['failure_reason'] = str(exc)
        record['daemon_cancellation'] = ('NO_PULL_STARTED' if child is None else
                                         'CLI_STOPPED; DAEMON_CANCELLATION_NOT_INDEPENDENTLY_ATTESTED')
        try:
            common('stop')
            record['post_stop_guards'] = 'PASS'
        except BaseException:
            record['post_stop_guards'] = 'STOP'
        publish()  # Still anchored to the original filesystem, including after mount loss.
        raise
    finally:
        for fd in (log, lock, imagefd, taskfd):
            os.close(fd)


def interrupted(_signum, _frame):
    raise InterruptedError('task interrupted')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify-only', action='store_true', help='Verify stored metadata after recorded pull exit 0; never pull or launch a container.')
    args = parser.parse_args()
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    try:
        print(json.dumps(run(verify_only=args.verify_only), sort_keys=True))
    except BaseException as exc:
        result = {'state': 'STOP', 'failure_class': type(exc).__name__}
        if isinstance(exc, ImageStop):
            result['failure_reason'] = str(exc)
        print(json.dumps(result), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
