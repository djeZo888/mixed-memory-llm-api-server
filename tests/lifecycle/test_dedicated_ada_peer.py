"""Exact existing H028 pure owner proof; no native requests or model operations."""
import copy
import runpy
from unittest.mock import patch
from tests.lifecycle import test_dedicated_image_peer as image
ROOT, change = image.ROOT, image.change
from control.node_observation import ADA_BASE, ADA_SOURCES, ADA_AUTH_PATH
from lifecycle.runtime_io import LifecycleError

# Reuse only fixture construction, not the image-specific test methods.
class DedicatedAdaPeerTests(__import__('unittest').TestCase):
    def setUp(self):
        image.DedicatedImagePeerTests.setUp(self)
        self.binding.roots.update(data="/data", services="/data/services")
        self.owner = runpy.run_path(str(ROOT / 'scripts/h028/ada_owner.py'))
        self.config = {'owner':self.owner['OWNER'],'image_id':self.owner['IMAGE'],
                       'source_sha256':ADA_SOURCES, 'image_env':[]}
        self.state = {'schema_version':1,'owner':self.owner['OWNER'],'desired':'running',
                      'container':{'id':'a'*64,'name':self.owner['NAME'],'image_id':self.owner['IMAGE']}}
        self.source_bytes = {ADA_BASE+'/source/'+name:(ROOT/'scripts/h028'/name).read_bytes() for name in ADA_SOURCES}
        self.source_bytes[ADA_AUTH_PATH]=(ROOT/'scripts/runtime/sglang38_file_auth.py').read_bytes()
        self.docs={ADA_BASE+'/config.json':self.config,ADA_BASE+'/state.json':self.state}
        self.candidate={'Id':'a'*64,'Name':'/'+self.owner['NAME'],'Image':self.owner['IMAGE'],
          'HostConfig':{'DeviceRequests':[{'DeviceIDs':[self.owner['GPU']],'Count':0,'Capabilities':[['gpu']]}],
            'ReadonlyRootfs':True,'NetworkMode':'bridge','PortBindings':{'30014/tcp':[{'HostIp':'127.0.0.1','HostPort':'30014'}]},
            'RestartPolicy':{'Name':'no','MaximumRetryCount':0},'Memory':self.owner['MEMORY'],'MemorySwap':self.owner['MEMORY'],
            'CpusetCpus':'0-71','CapDrop':['ALL'],'SecurityOpt':['no-new-privileges'],'LogConfig':{'Type':'local'}},
          'Config':{'Entrypoint':['/opt/sglang/bin/python'],'Cmd':['-I','-B','/runtime/ada_launcher.py','--slot','ada200k'],
            'Env':[k+'='+v for k,v in self.owner['environment']().items()],
            'Labels':{'io.llm-ada200k.owner':self.owner['OWNER'],'io.llm-ada200k.gpu':self.owner['GPU']}},
          'State':{'Running':True,'Pid':1234,'StartedAt':'current-start'},'NetworkSettings':{},
          'Mounts':[{'Type':'bind','Source':v[0],'Destination':k,'RW':v[1]} for k,v in self.owner['mounts']().items()]}
        self.fresh=copy.deepcopy(self.candidate)
        self.boot=patch('lifecycle.hardware_policy.boot_identity',return_value={'boot_id':'current-boot'})
        self.boot_mock=self.boot.start();self.addCleanup(self.boot.stop)

    def validate(self):return self.manager.validate_dedicated_ada_peer(self.candidate,self.deployment)

    def test_exact_current_ada_passes_without_write_or_readiness(self):
        self.fresh['Mounts'].reverse();self.validate()
        self.manager.persistent_json.assert_not_called();self.manager.sglang_probe.assert_not_called()

    def test_unknown_or_changed_native_peer_fails_closed(self):
        baseline=copy.deepcopy(self.fresh)
        for path,value in [(('Id',),'b'*64),(('HostConfig','DeviceRequests',0,'DeviceIDs'),['foreign']),
           (('State','Pid'),4321),(('State','StartedAt'),'restart'),(('State','Running'),False),
           (('Mounts',0,'RW'),True),(('Config','Labels','io.llm-ada200k.owner'),'foreign')]:
            with self.subTest(path=path):
                self.fresh=copy.deepcopy(baseline);change(self.fresh,path,value)
                with self.assertRaisesRegex(LifecycleError,'untrusted_concurrent_peer'):self.validate()
        self.fresh=baseline;self.candidate['Name']='/unknown'
        with self.assertRaises(LifecycleError):self.validate()

    def test_source_and_config_state_boot_drift_fail_closed(self):
        for name in ADA_SOURCES:
            key=ADA_BASE+'/source/'+name;old=self.source_bytes[key];self.source_bytes[key]+=b'\n'
            with self.assertRaises(LifecycleError):self.validate()
            self.source_bytes[key]=old
        original=self.manager.docker.inspect.side_effect
        for name in ['state','config','boot']:
            with self.subTest(name=name):
                def inspect(cid):
                    if name=='state':self.state['pending_create']={'unknown':True}
                    elif name=='config':self.config['new']='changed'
                    else:self.boot_mock.return_value={'boot_id':'changed-boot'}
                    return original(cid)
                self.manager.docker.inspect.side_effect=inspect
                with self.assertRaises(LifecycleError):self.validate()
                self.state.pop('pending_create',None);self.config.pop('new',None)
                self.boot_mock.return_value={'boot_id':'current-boot'}
        self.manager.docker.inspect.side_effect=original

    def test_conflict_router_accepts_only_named_proven_ada(self):
        self.manager._slots_envelope = {'slots': {'qwen': {'selected': None}, 'glm': {'selected': None}}}
        self.manager._slot_target = 'glm'
        self.manager.docker.inventory.return_value = [self.candidate]
        self.manager.conflict_check(deployment=self.deployment)
        self.candidate['Name'] = '/foreign-gpu-user'
        with self.assertRaises(LifecycleError):
            self.manager.conflict_check(deployment=self.deployment)

    def test_overlap_gpu_is_rejected(self):
        self.deployment=copy.deepcopy(self.deployment)
        self.deployment['launch']['gpus']=[self.owner['GPU']]
        with self.assertRaises(LifecycleError):self.validate()
