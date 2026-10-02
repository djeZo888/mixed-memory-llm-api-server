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
import image_owner_successor as owner
from image_executor import LEAVES


def signature(value):
    return [value[k] for k in ('dev','inode','mode','uid','gid','nlink','size','mtimeNs','ctimeNs')]


def build(graph, stage, source_root):
    stage = Path(stage)
    if str(stage.parent) != '/run/llmctl' or not stage.name.startswith('h046-image-stopped-cas-'):
        raise ValueError('new exact protected H046 stage required')
    core = owner.core; source_root = Path(source_root)
    sources = {name:source_root/('scripts/h044' if name == 'image_owner_reconcile.py' else 'scripts/h046')/name
               for name in LEAVES}
    helpers = {str(stage/name):hashlib.sha256(path.read_bytes()).hexdigest() for name,path in sources.items()}
    files = {v['path']:v['sha256'] for group in graph['sourceGraph'].values()
             for v in group.values() if type(v) is dict and 'path' in v and 'sha256' in v}
    value = owner.request() | {'status':'SOURCE_ONLY_REVIEW_REQUEST_NOT_GO','issuedBy':'UNISSUED',
        'bootId':graph['bootId'],'sourceSha256':helpers[str(stage/'image_owner_successor.py')],
        'ownerSourceSha256':core.OWNER_SOURCE_SHA,'rootStage':str(stage),'helperSha256':helpers,
        'notBeforeUtc':None,'expiresUtc':None,
        'apiCanonicalSourceSha256':{path:files[path] for path in core.API_FILES},
        'apiUnitRawSha256':files[owner.API_UNIT],
        'backendUnitRawSha256':files[owner.BACKEND_UNIT],
        'dockerBinarySha256':graph['dockerBinarySha256'],
        'pythonSha256':graph['pythonSha256'],'daemonId':graph['daemonId'],
        'residentBindings':graph['residentBindings'],'peerFileSha256':graph['peerFileSha256'],
        'stoppedUnits':graph['stoppedUnits'],
        'expectedFileIdentity':graph['expectedFileIdentity'],
        'archiveFileIdentity':graph['archiveFileIdentity'],
        'archiveDirectoryIdentity':graph['archiveDirectoryIdentity'],
        'hardwareLatchSha256':graph['hardwareLatchSha256'],'hardwareLatchIdentity':graph['hardwareLatchIdentity'],
        'cachedPublicOCIPaths':{'manifest':'/data/containerd/root/io.containerd.content.v1.content/blobs/sha256/'+core.PLATFORM[7:],
            'config':'/data/containerd/root/io.containerd.content.v1.content/blobs/sha256/'+core.CONFIG[7:]},
        'readGraphUtc':graph['proofUtc'],'readGraphStatus':'ACTUAL_READBACK_ONLY; refresh changed identities before root GO',
        'fixedInvocation':['/usr/bin/python3.12','-I','-S','-B',str(stage/'image_executor.py'),str(stage/'ROOT-GO.json')],
        'stageSourceGraph':{str(stage/name):str(path.relative_to(source_root)) for name,path in sources.items()},
        'preflight':'Root-owned0700 exclusive new stage, five0600 helpers; NO-PYC-CACHE absent; ROOT-GO0600; current owner refresh',
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
    parser.add_argument('graph'); parser.add_argument('stage'); args = parser.parse_args()
    print(json.dumps(build(json.loads(Path(args.graph).read_text()),args.stage,
                           Path(__file__).resolve().parents[2]),indent=2,sort_keys=True))
