#!/usr/bin/env python3
"""Stopped-only narrow transaction; never stop/start/reset/warm either service.

--check-payload is entirely local and reads JSON from stdin. --install reads the
same payload only AFTER the separate capacity handoff and root exact transaction
GO. A matching supplied hash is integrity evidence, never approval by itself.
--rollback restores three files from the private receipt and remains stopped.
No automatic retry. A partial rollback failure leaves the API stopped for review.
installed.json is provisional: retain successful helper stdout as completion
evidence before startup. Compensation may restore files after that file is saved.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import stat
import subprocess
import sys

COMMIT = '9de9ecf701bedd0bcb337d9dcb49a4aca1c3fa27'
BASE = Path('/data/services/h003-image-api-activate-20260923')
SOURCE = Path('/usr/local/lib/llm-server/image-api/scripts/image_api')
CONFIG = Path('/etc/llm-server/image-api.json')
KEY = Path('/data/services/secrets/llm-api-key')
RUNTIME = Path('/data/services/image21-runtime-20260923')
RUNTIME_CONFIG = '4ded6e9261b512d952c5033b0634d4eaba79fa115685635c6307defe78c11d76'
RUNTIME_SERVICE = '0edadcb43ec83d369d7bdb66dddc7035962d620475314b0142cb9f047b197586'
OLD_CONFIG = '12969d9966f222217891791f0a2d6f4202ee2b0a7f83ef36f18d734a96721b07'
EXPECTED = {
    '__init__.py': '9f66047f4c2cde6ab4cb85b47c97a6274903fb560b96ef1f49fd42c1e67c751c',
    'app.py': '45abd74890af3a9d8045aeec6de56d773266e31f8e098ece5084d1f0fe7cb897',
    'backend.py': '64a5ceccb247e7c7ed646cc3ae9af89aeffb7aebd862c11604786a2041db9485',
    'protection.py': '9c8e5fad91717fa8e7665475e9cc49bb2092955439aaf3febeaf203cc7da6269',
    'protocol.py': '257df8ac052af14cd44aabb0daf30fa333132d9a4be8074ccab8d9e571de3b1b',
    'serve.py': '0d19743ab91ea4f8cafe2bf6d7ddd9d56d2248604da23c711a19f825ba4b6d2e',
    'uploads.py': '23903630b94c020af05988dfc13b0f1e650b431ca9f276485873234997e3ce93',
}
PREVIOUS = {**EXPECTED,
    'app.py': '4cad82ce35d4650c7f3242bd6816769010c6a52510fae1c3c26b8789acdc0d22',
    'protocol.py': '35653fa23fa883f20da9c869e75e7fd613008f23fe9793f16e240852b3e40243'}
TEXT_IDS = ('a2afad49380a592739944f2766f5547687a5cf302badd375bda14fffdb09f75c',
            'a71924b9e7fa4f72c6eeefc243731f59bdc0d951b817de1d32f32dbfd67f450e')
GENERATION = [
    ('1024x1024', '29250a7887d4bd9688a4ebd2c3f0720db1960116012f31fa553dddf37656aad4'),
    ('1024x576', 'f4c2f070cb44477dcacd671f46646cfa39e0374e859c808ec7c78c9cc3a35af1'),
    ('1216x704', '0c5536fb0a6ec34bb972e84ae05a1d01bcf8a96281220f3f31c9c08ddbda16ef'),
    ('1472x832', 'f017918f5885133522197bb5765201788e66a1423c4303992a65887eabd520e3'),
    ('1760x992', 'f91eaca9a0d8583081ccaa9d62d48bd7511bd5b99b8193a26abd7106f27e3c83'),
    ('1920x1080', 'b33ceb2e05638c3342581b964b21ae2c201e0748ac4331a15ac13ffa992786eb')]
TARGETS = (SOURCE / 'app.py', SOURCE / 'protocol.py', CONFIG)


def require(ok, code):
    if not ok:
        raise RuntimeError(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def strict(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'duplicate_json_key')
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=pairs,
                      parse_constant=lambda _: require(False, 'invalid_json_constant'))


def check_payload(payload):
    require(payload['source_commit'] == COMMIT, 'source_commit_mismatch')
    require(set(payload['source']) == set(EXPECTED), 'api_source_set_mismatch')
    source = {name: value.encode('utf-8') for name, value in payload['source'].items()}
    require({name: sha(raw) for name, raw in source.items()} == EXPECTED, 'reviewed_source_mismatch')
    raw = payload['qualification'].encode('utf-8')
    require(len(raw) <= 131072 and sha(raw) == payload['manifest_sha256'], 'exact_manifest_hash_mismatch')
    q = strict(raw)
    require(set(q) == {'schema_version', 'runtime_revision', 'model_id', 'model_revision',
                       'runtime_image_digest', 'profiles', 'limits'}, 'manifest_keys_mismatch')
    require(type(q['schema_version']) is int and q['schema_version'] == 1 and
            q['runtime_revision'] == '0cd8be351d0825488f4b81c8931167bbab618eca' and
            q['model_id'] == 'Qwen/Qwen-Image-2.1' and
            q['model_revision'] == '790c92633540aa0cb11d9abf19eb46d861714758' and
            q['runtime_image_digest'] == 'sha256:dafbccb763cff6a6aa3777c7c0a8cc185d838bd4b9f61bec8007f57f2c7233f8',
            'manifest_pins_mismatch')
    require(q['limits'] == {'max_width': 1920, 'max_height': 1080, 'max_pixels': 2073600,
                             'native_max_pixels': 2088960} and
            all(type(value) is int for value in q['limits'].values()), 'manifest_limits_mismatch')
    expected_gen = [{'operation': 'generation', 'references': 0, 'size': size,
                     'native_size': '1920x1088' if size == '1920x1080' else size,
                     'crop_bottom': 8 if size == '1920x1080' else 0,
                     'transparent': False, 'conditioning': '', 'evidence_sha256': digest}
                    for size, digest in GENERATION]
    require(isinstance(q['profiles'], list) and len(q['profiles']) <= 100, 'invalid_profiles')
    require([p for p in q['profiles'] if p.get('operation') == 'generation'] == expected_gen,
            'generation_records_changed')
    seen = set()
    for p in q['profiles']:
        required = {'operation', 'references', 'size', 'transparent', 'conditioning', 'evidence_sha256'}
        require(required <= set(p) and not set(p) - required - {'native_size', 'crop_bottom'},
                'profile_fields_mismatch')
        require(p['operation'] in ('generation', 'edit') and type(p['references']) is int and
                p['references'] in ((0,) if p['operation'] == 'generation' else (1, 2)) and
                p['transparent'] is False and p['conditioning'] == '' and
                isinstance(p['evidence_sha256'], str) and re.fullmatch('[0-9a-f]{64}', p['evidence_sha256']),
                'invalid_profile')
        require(isinstance(p['size'], str) and re.fullmatch('[1-9][0-9]{0,3}x[1-9][0-9]{0,3}', p['size']),
                'invalid_profile_size')
        width, height = map(int, p['size'].split('x'))
        require(width <= 1920 and height <= 1080 and width * height <= 2073600, 'profile_size_over_limit')
        native, crop = p.get('native_size', p['size']), p.get('crop_bottom', 0)
        geometry = ((p['size'] == '1920x1080' and native == '1920x1088' and crop == 8 and
                     (p['operation'], p['references']) in (('generation', 0), ('edit', 1))) or
                    (p['size'] != '1920x1080' and native == p['size'] and crop == 0))
        require(type(crop) is int and geometry, 'profile_geometry_mismatch')
        signature = (p['operation'], p['references'], p['size'])
        require(signature not in seen, 'duplicate_profile')
        seen.add(signature)
    return source, raw, q


def command(args):
    p = subprocess.run(args, capture_output=True, text=True, timeout=30,
                       env={'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LANG': 'C'})
    require(p.returncode == 0, 'transaction_command_failed')
    return p.stdout


def unit():
    keys = ('MainPID', 'ControlPID', 'ActiveState', 'SubState', 'Result', 'ExecMainCode',
            'ExecMainStatus', 'Restart', 'FragmentPath', 'DropInPaths')
    return dict(line.split('=', 1) for line in command(['systemctl', 'show', 'llm-image-api.service',
                *[arg for key in keys for arg in ('-p', key)]]).splitlines())


def stopped():
    value = unit()
    require(value['MainPID'] == '0' and value['ControlPID'] == '0' and
            value['ActiveState'] in ('inactive', 'failed') and value['SubState'] in ('dead', 'failed') and
            value['Restart'] == 'no' and value['DropInPaths'] == '', 'api_not_stopped')
    # This does not assert ASGI cleanup or reinterpret historical code2/status15.
    with socket.socket() as sock:
        sock.settimeout(1)
        require(sock.connect_ex(('127.0.0.1', 30006)) != 0, 'api_listener_present')
    return value


def texts():
    result = []
    for identity in TEXT_IDS:
        c = strict(command(['docker', 'inspect', identity]))[0]
        require(c['Id'] == identity and c['State']['Running'], 'original_text_not_running')
        result.append({'id': identity, 'image': c['Image'], 'pid': c['State']['Pid'],
                       'started_at': c['State']['StartedAt'], 'argv': c['Config']['Cmd'],
                       'settings': {k: c['HostConfig'][k] for k in
                                    ('CpusetCpus', 'Memory', 'MemorySwap', 'DeviceRequests', 'RestartPolicy')}})
    return result


def atomic(path, raw, metadata, protected_file):
    for parent in path.parents:
        st = parent.lstat()
        require(stat.S_ISDIR(st.st_mode) and st.st_uid == 0 and not st.st_mode & 0o022,
                'unprotected_target_parent')
    protected_file(path, maximum=1048576)
    temp = path.with_name('.h003-activate-' + path.name)
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        try:
            os.fchown(fd, metadata['uid'], metadata['gid'])
            os.fchmod(fd, metadata['mode'])
            with os.fdopen(fd, 'wb', closefd=False) as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(temp, path)
        fd = os.open(path.parent, os.O_DIRECTORY | os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    finally:
        if temp.exists():
            temp.unlink()
    st = path.lstat()
    require(protected_file(path, modes={metadata['mode']}, maximum=1048576) == raw and
            (st.st_uid, st.st_gid) == (metadata['uid'], metadata['gid']), 'installed_bytes_or_metadata_mismatch')


def host_tools():
    require(os.geteuid() == 0, 'root_required')
    # Pin the existing owner before importing it; its Runtime verifies registered
    # storage, runtime source pins, model receipt and current installed guards.
    require(sha((RUNTIME / 'source/service.py').read_bytes()) == RUNTIME_SERVICE, 'runtime_owner_changed')
    sys.path.insert(0, str(RUNTIME / 'source'))
    import service
    require(sha(service.protected_file(RUNTIME / 'source/service.py')) == RUNTIME_SERVICE,
            'runtime_owner_changed')
    r = service.Runtime()
    require(sha(service.protected_file(RUNTIME / 'config.json')) == RUNTIME_CONFIG, 'runtime_config_changed')
    return service, r


def install(payload):
    source, raw, q = check_payload(payload)
    m, r = host_tools()
    with m.acquire_lease(blocking=False):
        r.guards()
        api, text_before, state = stopped(), texts(), r.state()
        r.verify_resident(state)
        r.check_network(state)
        paths = {str(SOURCE / name): name for name in EXPECTED}
        paths.update({str(CONFIG): 'config.json', api['FragmentPath']: 'api-unit',
                      str(KEY): 'inference-key', str(RUNTIME / 'config.json'): 'runtime-config.json'})
        previous, metadata = {}, {}
        for name, backup in paths.items():
            path = Path(name)
            previous[name] = m.protected_file(path, maximum=1048576)
            st = path.lstat()
            metadata[name] = {'sha256': sha(previous[name]), 'mode': stat.S_IMODE(st.st_mode),
                              'uid': st.st_uid, 'gid': st.st_gid, 'backup': backup}
        require({name: sha(previous[str(SOURCE / name)]) for name in EXPECTED} == PREVIOUS,
                'prior_source_changed')
        require(sha(previous[str(CONFIG)]) == OLD_CONFIG, 'prior_manifest_changed')
        require([p for p in strict(previous[str(CONFIG)])['profiles'] if p['operation'] == 'generation'] ==
                [p for p in q['profiles'] if p['operation'] == 'generation'], 'prior_generation_changed')
        preflight = {'source_commit': COMMIT, 'api': api, 'texts': text_before,
                     'backend_container': state['container'], 'backend_run_id': state['run_id'],
                     'historical_exit_classification': 'ASGI-cleanup-unproven; no reclassification',
                     'files': metadata}
        files = {str(SOURCE / 'app.py'): source['app.py'], str(SOURCE / 'protocol.py'): source['protocol.py'],
                 str(CONFIG): raw}
        require(not BASE.exists() and not BASE.is_symlink(), 'transaction_already_present_no_repeat')
        with r.binding.mounted_guard(m.storage_io) as guard:
            with m.storage_io.AnchoredRoot(r.binding.path('services'), guard) as a:
                a.mkdir(BASE.name, mode=0o700)
            with m.storage_io.AnchoredRoot(str(BASE), guard) as a:
                a.mkdir('rollback', mode=0o700)
                for name, value in previous.items():
                    with a.open('rollback/' + metadata[name]['backup'], os.O_WRONLY | os.O_CREAT | os.O_EXCL) as f:
                        f.write(value)
                        f.fsync()
                a.atomic_json('preflight.json', preflight)
        # Revalidate every identity after durable snapshot and before any replace.
        require(stopped() == api and texts() == text_before and r.state() == state, 'snapshot_state_changed')
        for name, value in previous.items():
            st = Path(name).lstat()
            meta = metadata[name]
            require(m.protected_file(Path(name)) == value and
                    (stat.S_IMODE(st.st_mode), st.st_uid, st.st_gid) == (meta['mode'], meta['uid'], meta['gid']),
                    'snapshot_file_changed')
        r.guards()
        attempted = []
        try:
            for name, value in files.items():
                # Append BEFORE atomic: readback/fsync can fail after os.replace.
                attempted.append(name)
                atomic(Path(name), value, metadata[name], m.protected_file)
            command(['/data/services/image-api/venv/bin/python', '-I', '-B', '-c',
                     "import sys;sys.path.insert(0,'/usr/local/lib/llm-server/image-api/scripts');"
                     "from image_api.protocol import qualification,strict_json;"
                     "from image_api.protection import protected,CONFIG;"
                     "qualification(strict_json(protected(CONFIG,modes={0o644},maximum=131072)))"])
            require(stopped() == api and texts() == text_before and r.state() == state, 'post_install_state_changed')
            for name, value in previous.items():
                if name not in files:
                    require(m.protected_file(Path(name)) == value, 'preserved_file_changed')
            r.guards()
            receipt = {'status': 'PROVISIONAL_FILES_INSTALLED_API_STOPPED', 'source_commit': COMMIT,
                       'files': {name: sha(value) for name, value in files.items()},
                       'all_source_sha256': EXPECTED, 'manifest_sha256': sha(raw),
                       'profiles': q['profiles'], 'preflight_sha256': sha(m.protected_file(BASE / 'preflight.json')),
                       'startup_count': 0, 'warmup_count': 0}
            with r.binding.mounted_guard(m.storage_io) as guard:
                with m.storage_io.AnchoredRoot(str(BASE), guard) as a:
                    a.atomic_json('installed.json', receipt)
            r.guards()
        except BaseException:
            failures = []
            for name in reversed(attempted):
                try:
                    atomic(Path(name), previous[name], metadata[name], m.protected_file)
                except BaseException:
                    failures.append(name)
            result = {'status': 'COMPENSATION_FAILED' if failures else 'COMPENSATED_API_STOPPED',
                      'failed_paths': failures, 'startup_authorized': False, 'automatic_retry': False}
            try:
                r.guards()
                with r.binding.mounted_guard(m.storage_io) as guard:
                    with m.storage_io.AnchoredRoot(str(BASE), guard) as a:
                        a.atomic_json('compensation.json', result)
            except BaseException:
                result['durable_compensation_receipt'] = 'unavailable; preserve stderr and inspect before any action'
            print(json.dumps(result), file=sys.stderr)
            require(not failures, 'partial_install_compensation_failed_keep_api_stopped')
            raise
    print(json.dumps({'status': 'INSTALLED_API_STOPPED', 'manifest_sha256': sha(raw),
                      'rollback': str(BASE / 'rollback'), 'lease': 'released', 'warmups': 0}))


def rollback():
    m, r = host_tools()
    with m.acquire_lease(blocking=False):
        r.guards()
        api = stopped()
        before_raw = m.protected_file(BASE / 'preflight.json')
        before = strict(before_raw)
        receipt = strict(m.protected_file(BASE / 'installed.json'))
        require(receipt['source_commit'] == COMMIT and receipt['preflight_sha256'] == sha(before_raw) and
                set(receipt['files']) == {str(p) for p in TARGETS}, 'rollback_receipt_mismatch')
        require(api['FragmentPath'] == before['api']['FragmentPath'] and texts() == before['texts'],
                'rollback_preserved_identity_changed')
        backups = {}
        for name, meta in before['files'].items():
            require(Path(meta['backup']).name == meta['backup'] and meta['uid'] == 0 and
                    type(meta['mode']) is int and not meta['mode'] & 0o022, 'rollback_metadata_invalid')
            raw = m.protected_file(BASE / 'rollback' / meta['backup'])
            require(sha(raw) == meta['sha256'], 'rollback_backup_changed')
            backups[name] = raw
            current = m.protected_file(Path(name))
            st = Path(name).lstat()
            require((stat.S_IMODE(st.st_mode), st.st_uid, st.st_gid) == (meta['mode'], meta['uid'], meta['gid']),
                    'rollback_file_metadata_changed')
            require(sha(current) == receipt['files'].get(name, meta['sha256']), 'rollback_current_file_changed')
        require({name: sha(backups[str(SOURCE / name)]) for name in EXPECTED} == PREVIOUS and
                sha(backups[str(CONFIG)]) == OLD_CONFIG, 'rollback_prior_hashes_mismatch')
        r.guards()
        restored = []
        try:
            for path in reversed(TARGETS):
                atomic(path, backups[str(path)], before['files'][str(path)], m.protected_file)
                restored.append(str(path))
        except BaseException:
            print(json.dumps({'status': 'ROLLBACK_PARTIAL_OR_READBACK_FAILED_API_STOPPED',
                              'verified_restored': restored, 'automatic_retry': False}), file=sys.stderr)
            raise
        require(stopped() == api and texts() == before['texts'], 'rollback_state_changed')
        r.guards()
        with r.binding.mounted_guard(m.storage_io) as guard:
            with m.storage_io.AnchoredRoot(str(BASE), guard) as a:
                a.atomic_json('rollback-result.json', {'status': 'RESTORED_API_STOPPED', 'warmups': 0,
                              'restored': {str(p): sha(backups[str(p)]) for p in TARGETS}})
        r.guards()
    print(json.dumps({'status': 'RESTORED_API_STOPPED', 'lease': 'released', 'warmups': 0}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--check-payload', action='store_true', help='offline stdin payload integrity/schema check; no approval claim')
    mode.add_argument('--install', action='store_true', help='root-approved stopped-only install from stdin; never starts services')
    mode.add_argument('--rollback', action='store_true', help='restore exact three private backups; requires stopped API; never starts services')
    args = parser.parse_args()
    if args.rollback:
        rollback()
    else:
        raw = sys.stdin.buffer.read(1048577)
        require(len(raw) <= 1048576, 'payload_too_large')
        payload = strict(raw)
        if args.check_payload:
            _, raw, q = check_payload(payload)
            print(json.dumps({'status': 'PAYLOAD_INTEGRITY_ONLY_NO_ACTIVATION_AUTHORITY',
                              'source_commit': COMMIT, 'manifest_sha256': sha(raw), 'profiles': q['profiles']}))
        else:
            install(payload)


if __name__ == '__main__':
    main()
