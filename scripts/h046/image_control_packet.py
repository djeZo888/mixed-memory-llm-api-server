#!/usr/bin/env python3
"""Offline exact source/control builder. Output is a review request, never GO."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'h044'))
sys.path.insert(0,str(Path(__file__).resolve().parent))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import image_owner_successor as owner
from image_executor import LEAVES, canonical_storage_binding, storage_guard_argv


def signature(value):
    return [value[k] for k in ('dev','inode','mode','uid','gid','nlink','size','mtimeNs','ctimeNs')]


def build(graph, stage, source_root, canonical_packet=None, mutable_packet=None):
    stage = Path(stage)
    if str(stage.parent) != '/run/llmctl' or not stage.name.startswith('h046-image-stopped-cas-'):
        raise ValueError('new exact protected H046 stage required')
    core = owner.core; source_root = Path(source_root)
    if canonical_packet is None:raise ValueError('fresh actual canonical storage source/registration packet required')
    if canonical_packet['bootId'] != graph['bootId']:raise ValueError('canonical/owner boot join changed')
    storage_binding = canonical_storage_binding(canonical_packet)
    if mutable_packet is None or mutable_packet.get('bootId') != graph['bootId']:
        raise ValueError('fresh actual mutable writer/descriptor packet required')
    if {p:v['sha256'] for p,v in mutable_packet['sources'].items()} != owner.MUTABLE_SOURCE_SHA:
        raise ValueError('exact installed mutable writer source changed')
    for leaf in ('scripts/control/hardware_latch.py','scripts/lifecycle/hardware_policy.py'):
        if hashlib.sha256((source_root/leaf).read_bytes()).hexdigest() != owner.MUTABLE_SOURCE_SHA[owner.core.RELEASE+'/'+leaf]:
            raise ValueError('offline canonical schema source changed')
    if mutable_packet['guardTemperatureGPU'] != mutable_packet['descriptors'][owner.GUARD_PATH]['value']['sample']['gpus'][0]['uuid']:
        raise ValueError('guard thermal target changed')
    mutable = {}
    for p in owner.MUTABLE_PATHS:
        observed = mutable_packet['descriptors'][p]
        if observed['path'] != p: raise ValueError('fixed mutable descriptor path required')
        mutable[p] = {'path':p,'protectedMetadata':observed['identity'][2:6],'parentIdentity':observed['parentIdentity'],
            'temperatureLimitC':mutable_packet['guardTemperatureLimitC'] if p == owner.GUARD_PATH else None,
            'semantic':owner.mutable_semantic(p,owner.core.encode(observed['value']),temperature_limit=mutable_packet['guardTemperatureLimitC'])}
    peer_files = dict(graph['peerFileSha256'])
    if owner.GUARD_PATH not in peer_files:raise ValueError('exact previous guard peer set required')
    peer_files.pop(owner.GUARD_PATH)
    native = mutable[owner.GUARD_PATH]['semantic']['native']
    resident = graph['residentBindings']['MiMo']
    if native['image_id'] != resident['container']['image'] or native['container_id'] != resident['container']['id'] or native['pid'] != resident['container']['pid'] or str(native['pid_start_ticks']) != resident['birth']['startTicks']:
        raise ValueError('fresh MiMo guard/current resident owner join changed')
    sources = {name:source_root/('scripts/h044' if name == 'image_owner_reconcile.py' else 'scripts/h046')/name
               for name in LEAVES}
    helpers = {str(stage/name):hashlib.sha256(path.read_bytes()).hexdigest() for name,path in sources.items()}
    files = {v['path']:v['sha256'] for group in graph['sourceGraph'].values()
             for v in group.values() if type(v) is dict and 'path' in v and 'sha256' in v}
    if any(files.get(p) != digest for p,digest in storage_binding['sourceSha256'].items()):
        raise ValueError('owner/canonical frozen source closure join changed')
    value = owner.request() | {'status':'SOURCE_ONLY_REVIEW_REQUEST_NOT_GO','issuedBy':'UNISSUED',
        'bootId':graph['bootId'],'sourceSha256':helpers[str(stage/'image_owner_successor.py')],
        'ownerSourceSha256':core.OWNER_SOURCE_SHA,'rootStage':str(stage),'helperSha256':helpers,
        'notBeforeUtc':None,'expiresUtc':None,
        'apiCanonicalSourceSha256':{path:files[path] for path in core.API_FILES},
        'apiUnitRawSha256':files[owner.API_UNIT],
        'backendUnitRawSha256':files[owner.BACKEND_UNIT],
        'dockerBinarySha256':graph['dockerBinarySha256'],
        'pythonSha256':graph['pythonSha256'],'daemonId':graph['daemonId'],
        'residentBindings':graph['residentBindings'],'peerFileSha256':peer_files,
        'stoppedUnits':graph['stoppedUnits'],
        'expectedFileIdentity':graph['expectedFileIdentity'],
        'archiveFileIdentity':graph['archiveFileIdentity'],
        'archiveDirectoryIdentity':graph['archiveDirectoryIdentity'],
        'mutableDescriptorBinding':mutable,'mutableSourceSha256':owner.MUTABLE_SOURCE_SHA,
        'mutableSourceIdentity':{p:v['identity'] for p,v in mutable_packet['sources'].items()},
        'descriptorReadback':{'proofUtc':mutable_packet['proofUtc'],'status':'ACTUAL_READBACK_ONLY_NOT_HARDWARE_PROOF',
            'files':{p:{k:v[k] for k in ('path','sha256','identity')} for p,v in mutable_packet['descriptors'].items()}},
        'mutableReadContract':'Fixed canonical paths/writers/protected parent/metadata/semantics frozen; atomic replacement BETWEEN stable reads allowed; each read exact current FD/named9field+bytes join; each successful snapshot durably audited; no retry/descriptor writes/native admission.',
        'canonicalStorageBinding':storage_binding,
        'canonicalStorageReadUtc':canonical_packet['proofUtc'],
        'cachedPublicOCIPaths':{'manifest':'/data/containerd/root/io.containerd.content.v1.content/blobs/sha256/'+core.PLATFORM[7:],
            'config':'/data/containerd/root/io.containerd.content.v1.content/blobs/sha256/'+core.CONFIG[7:]},
        'readGraphUtc':graph['proofUtc'],'readGraphStatus':'ACTUAL_READBACK_ONLY; refresh changed identities before root GO',
        'fixedInvocation':['/usr/bin/python3.12','-I','-S','-B','-X',
            'pycache_prefix='+str(stage/'NO-PYC-CACHE'),str(stage/'image_executor.py'),str(stage/'ROOT-GO.json')],
        'stageSourceGraph':{str(stage/name):str(path.relative_to(source_root)) for name,path in sources.items()},
        'preflight':'Root-owned0700 exclusive new stage, five0600 helpers; NO-PYC-CACHE absent; ROOT-GO0600; current owner refresh',
        'storageTransport':'Unchanged canonical helper subprocess/Runner/Storage; exact -X child cache prefix added; original parent actual kernel wait and complete group absence; normal nested subprocess returns lack separate recorder receipts',
        'storageGuardInvocations':[storage_guard_argv(['/usr/bin/python3.12','-I','-B',
            core.RELEASE+'/scripts/common/registered-storage.py','--json',*extra],core,{'rootStage':str(stage)})
            for extra in ([],['--root-guard'])],
        'finitePlan':{'totalSeconds':180,'minimumInitialSettlementReserveSeconds':60,'invocations':1,
            'archiveWrites':0,'protectedSuccessorFiles':['config','state','operation','recovery','api'],
            'unchangedCheckpoint':core.PATHS['checkpoint'],
            'settlement':'Each helper actual kernel wait/reap + independent current birth/group absence; conditionally rollback own staged/original inodes only',
            'timingQualification':'NOT_TESTED; guard density may exhaust180s; no automatic retry'},
        'hardwareProof':'READ_ONLY_NO_PUBLISHED_HARDWARE_RECEIPT; native starts use normal unchanged persisted Runtime guard',
        'laterInferencePlan':{'authority':'SEPARATE_EXACT_ROOT_GO_REQUIRED',
            'preferredStart':['sudo','-n','/usr/bin/systemctl','start','llm-image-api.service'],
            'reason':'API lifespan fixed reconcile/recover starts backend and performs warm; starting backend first duplicates restart/warm',
            'warm':{'backendBoundSeconds':840,'monitorBoundSeconds':900,'settlementReserveSeconds':120,
                'width':1024,'height':1024,'steps':40,'seed':42,'paidCli':'CLOSED_DURING_LOADING'},
            'fullHD':{'nativeWidth':1920,'nativeHeight':1088,'publicWidth':1920,'publicHeight':1080,
                'format':'DECODED_PNG','request':'Genuine authenticated normal-live Sova image job, exact client/prompt/source/current-owner bound by root',
                'required':'Actual normal job/result/PNG hash+dimensions+current GPU/CID/native owner/settlement and no USB4/Xid/AER/OOM or margin failure'},
            'capacity':'Observe host15%/GPU5% margins, cgroup memory.current/peak/stat, PSI and OOM event deltas across concurrent six-instance operation; no cap/offload changes',
            'normalSova':'Chatlane owns compiled startup AI_HARNESS_CODEX_GENERATION_ONLY_FILE activation/current protected receipt closure',
            'advancedMCP':'OFF','editing':'NOT_TESTED; separate genuine edit/source/result/settlement checks required'},
        'qualification':'SOURCE_ONLY; actual readback separately recorded; native/lifecycle/generation NOT_TESTED'}
    # Exercise the exact captured map shapes, while keeping the returned control
    # unmistakably nonexecutable. This validation cannot mint live authority.
    now = datetime.datetime.now(datetime.timezone.utc)
    synthetic = dict(value,status='GO',issuedBy='root',notBeforeUtc=now.isoformat(),
                     expiresUtc=(now+datetime.timedelta(seconds=180)).isoformat())
    owner.validate_go(synthetic,value['sourceSha256'],now)
    return value


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('graph'); parser.add_argument('stage');parser.add_argument('canonical_packet');parser.add_argument('mutable_packet'); args = parser.parse_args()
    print(json.dumps(build(json.loads(Path(args.graph).read_text()),args.stage,
                           Path(__file__).resolve().parents[2],
                           json.loads(Path(args.canonical_packet).read_text()),
                           json.loads(Path(args.mutable_packet).read_text())),indent=2,sort_keys=True))
