"""Exact H029 source-only install; run only after root's explicit deployment GO."""
import copy
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

STAGE = Path('/data/backups/H029-FINALCONTROL03-stage')
BACKUP = Path('/data/backups/H029-FINALCONTROL03-d111edb9')
CONTROL = Path('/usr/local/lib/llm-server/control-api')
BOOT = '992bf979-efae-495b-9ab2-26e75ed5c5d0'
sys.path.insert(0, str(CONTROL / 'scripts'))
from common.lifecycle_lease import acquire_lease
from control.adapter import ProductionBackend
from lifecycle.concurrent_profiles import receipt_sha256


def require(value, code):
    if not value: raise RuntimeError(code)


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic(path, data, mode=0o644):
    temporary = path.with_name(path.name + '.h029-tmp')
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data);stream.flush();os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists(): temporary.unlink()


def service(action):
    subprocess.run(['systemctl', action, 'llm-control.service', 'llm-node.service'],
                   check=True, timeout=20, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)



def canonical_mounts(mounts):
    require(isinstance(mounts, list), 'native_mounts_invalid_shape')
    for entry in mounts:
        require(isinstance(entry, dict) and all(isinstance(k, str) for k in entry)
                and isinstance(entry.get('Source'), str)
                and isinstance(entry.get('Destination'), str)
                and isinstance(entry.get('RW'), bool), 'native_mounts_invalid_shape')
    try:
        return sorted(mounts, key=lambda entry: json.dumps(entry, sort_keys=True, allow_nan=False))
    except (TypeError, ValueError):
        raise RuntimeError('native_mounts_invalid_shape')


def launch_components(actual):
    components = {k: actual[k] for k in ('Config', 'HostConfig', 'Mounts', 'Path', 'Args')}
    components['Mounts'] = canonical_mounts(components['Mounts'])
    hashes = {k: hashlib.sha256(json.dumps(v, sort_keys=True).encode()).hexdigest()
              for k, v in components.items()}
    return components, hashes


def require_native_equal(before, after):
    require(len(before) == len(after), 'native_identity_changed')
    for old, new in zip(before, after):
        for component in ('Config', 'HostConfig', 'Mounts', 'Path', 'Args'):
            require(old['componentSha256'][component] == new['componentSha256'][component],
                    'native_component_changed_' + component)
    require(before == after, 'native_identity_changed')


def native_identity(proposal):
    values = json.loads(subprocess.check_output(['docker','inspect', *[c['id'] for c in proposal['containers']]], timeout=10))
    result=[]
    for actual,pin in zip(values,proposal['containers']):
        value=dict(name=actual['Name'],id=actual['Id'],image=actual['Image'],running=actual['State']['Running'],startedAt=actual['State']['StartedAt'],gpuUuids=[g for r in actual['HostConfig']['DeviceRequests'] for g in r['DeviceIDs']])
        require(value == pin, 'native_pin_changed')
        value['pid']=actual['State']['Pid']
        components, value['componentSha256'] = launch_components(actual)
        value['launchSha256']=hashlib.sha256(json.dumps(components,sort_keys=True).encode()).hexdigest()
        result.append(value)
    return result


def main():
    require(os.geteuid() == 0 and sys.argv[1:] == ['apply'], 'explicit_root_apply_required')
    require(datetime.datetime.now(datetime.timezone.utc) < datetime.datetime(2026,9,29,3,8,0,tzinfo=datetime.timezone.utc), 'checkpoint_cutoff')
    proposal = json.loads((STAGE / 'CONTROL-DEPLOY-PROPOSAL.json').read_text())
    expected = proposal['successorSourceSha256']
    for root, files in proposal['changesBySourceRoot'].items():
        for name, pins in files.items():
            require(sha(STAGE / name) == pins['after'], 'stage_source_mismatch')
            require(sha(Path(root) / name) == pins['before'], 'installed_source_mismatch')
    require(not BACKUP.exists(), 'backup_already_exists')
    manager = ProductionBackend(CONTROL / 'configs').open().manager
    instance_path = Path(manager.binding.path('data', 'services/llm-manager/deployment-instance.json'))
    receipt_path = Path(proposal['receiptPath'])
    with acquire_lease(blocking=False):
        require(Path('/proc/sys/kernel/random/boot_id').read_text().strip() == BOOT, 'boot_changed')
        state = manager.read_state()
        require(state.get('schema_version') == 3, 'owner_state_unqualified')
        for slot in ('glm', 'qwen'):
            require(state['slots'][slot].get('pending_create') is None, 'pending_create')
            require(manager.running(manager.trusted_container(state['slots'][slot]['container'])) is True, 'model_state_changed')
        native_before = native_identity(proposal)
        journal = manager.binding.read_json('data',manager.binding.path('data','services/llm-control/operations.json'))
        require(not any(e['status'] in {'pending','running'} for e in journal['entries'].values()), 'owned_operation_pending')
        instance = manager.binding.read_json('data', str(instance_path))
        require(instance == manager.instance, 'instance_changed')
        prior = manager.binding.read_json('data', str(receipt_path))
        require(receipt_sha256(prior) == proposal['predecessorReceiptSha256'] == instance['concurrent_pair_acceptance']['sha256'], 'receipt_changed')
        require(sha(receipt_path) == proposal['predecessorRawSha256'], 'receipt_raw_changed')
        require(prior['source_sha256'] == proposal['predecessorSourceSha256'] and len(prior['source_sha256']) == 82, 'closure_pin_changed')
        for root in proposal['changesBySourceRoot']:
            require(all(sha(Path(root) / name) == digest for name,digest in prior['source_sha256'].items()), 'predecessor_closure_mismatch')
        successor = copy.deepcopy(prior)
        successor.update(source_sha256=expected, reviewed_source_commit=proposal['commit'])
        updated = copy.deepcopy(instance)
        updated['concurrent_pair_acceptance'].update(sha256=receipt_sha256(successor), reviewed_source_commit=proposal['commit'])
        BACKUP.mkdir(mode=0o700)
        shutil.copy2(instance_path, BACKUP / 'deployment-instance.json')
        shutil.copy2(receipt_path, BACKUP / 'dualq-480k.accepted.json')
        for root, files in proposal['changesBySourceRoot'].items():
            for name in files:
                target = BACKUP / root.lstrip('/') / name
                target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                shutil.copy2(Path(root) / name, target)
        transition = {'schema':1,'task':'H029-FINALCONTROL03','sourceCommit':proposal['commit'],'bootId':BOOT,
          'predecessorReceiptSha256':receipt_sha256(prior),'successorReceiptSha256':receipt_sha256(successor),
          'changesBySourceRoot':proposal['changesBySourceRoot'],'receiptMutation':['source_sha256','reviewed_source_commit'],
          'modelsStarted':False,'modelsStopped':False,'inferenceSubmitted':0,'applied':False,
          'predecessorRawSha256':sha(receipt_path),'allClosureFiles':82,'containersBefore':native_before,
          'backupPath':str(BACKUP)}
        atomic(BACKUP / 'TRANSITION.json', (json.dumps(transition,indent=2)+'\n').encode(), 0o600)
        stopped = False
        try:
            stopped = True;service('stop')
            for root, files in proposal['changesBySourceRoot'].items():
                for name in files:
                    atomic(Path(root) / name, (STAGE / name).read_bytes())
            for root in proposal['changesBySourceRoot']:
                require(all(sha(Path(root) / name) == digest for name,digest in expected.items()), 'installed_closure_mismatch')
            manager.persistent_json(str(receipt_path), successor)
            manager.persistent_json(str(instance_path), updated)
            transition['containersAfter'] = native_identity(proposal)
            atomic(BACKUP / 'TRANSITION.json', (json.dumps(transition,indent=2)+'\n').encode(), 0o600)
            require_native_equal(native_before, transition['containersAfter'])
            require(manager.binding.read_json('data',str(receipt_path)) == successor, 'receipt_readback_mismatch')
            require(manager.binding.read_json('data',str(instance_path)) == updated, 'instance_readback_mismatch')
            transition['successorRawSha256'] = sha(receipt_path)
            transition['closuresMatch'] = {root:True for root in proposal['changesBySourceRoot']}
            transition['preservation'] = {'receiptExceptSourceRevision': True, 'instanceExceptReceiptReference': True}
            transition['applied'] = True
            transition['utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
            atomic(BACKUP / 'TRANSITION.json', (json.dumps(transition,indent=2)+'\n').encode(), 0o600)
        except Exception as error:
            transition['failureCode'] = str(error) if isinstance(error, RuntimeError) else type(error).__name__
            try:
                atomic(BACKUP / 'TRANSITION.json', (json.dumps(transition,indent=2)+'\n').encode(), 0o600)
            except OSError:
                pass  # Diagnostic persistence must never prevent original rollback.
            if stopped:
                for root,files in proposal['changesBySourceRoot'].items():
                    for name in files: atomic(Path(root) / name, (BACKUP / root.lstrip('/') / name).read_bytes())
                manager.persistent_json(str(receipt_path), prior)
                manager.persistent_json(str(instance_path), instance)
            raise
        finally:
            if stopped: service('start')
    print(json.dumps(transition,sort_keys=True))

if __name__ == '__main__':
    try: main()
    except Exception as error:
        print(json.dumps({'status':'FAIL','type':type(error).__name__,'code':getattr(error,'code',str(error) if isinstance(error, RuntimeError) else None)}))
        raise SystemExit(1)
