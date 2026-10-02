#!/usr/bin/env python3
"""Synthetic offline preparation guards; no socket, model or runtime imports."""
import copy
import importlib.util
import json
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('preparation', Path(__file__).with_name('image_backend_preparation.py'))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class PreparationTests(unittest.TestCase):
    def setUp(self):
        self.graph = m.source_graph()
        self.candidate = m.strict_json((m.ROOT/m.CANDIDATE).read_bytes())
        runtime, release = m.source_maps(self.graph)
        self.runtime = {'schema_version':1,'owner':m.OWNER,'source_commit':m.SGLANG,
            'checkpoint_revision':m.REVISION,'checkpoint_path':m.MODEL,
            'checkpoint_receipt_sha256':'a'*64,'gpu_uuid':m.READING_GPU,'image_id':m.PARENT,
            'network_id':'b'*64,'source_sha256':runtime,'release_source_sha256':release,
            'untouched':{'marker':'preserve'}}
        self.api = {'schema_version':1,'runtime_revision':m.SGLANG,'model_id':'Qwen/Qwen-Image-2.1',
            'model_revision':m.REVISION,'runtime_image_digest':m.PARENT,'profiles':[],
            'untouched':['retained']}
        self.args = {'prompt':'A red sailboat on an alpine lake.','size':'1920x1080','seed':43001}
        self.profile = {'operation':'generation','size':'1920x1080','references':0,
            'transparent':False,'native_size':'1920x1088','crop_bottom':8,'evidence_sha256':'c'*64}

    def plan(self):
        a,b = json.dumps(self.runtime).encode(),json.dumps(self.api).encode()
        return m.plan_config_migration(a,b,m.sha(a),m.sha(b),self.graph)

    def test_candidate_closed(self):
        self.assertIs(m.validate_candidate(self.candidate),self.candidate)
        self.assertFalse(m.packet()['generation']['executable'])

    def test_uuid_no_ordinal_or_reading_fallback(self):
        for gpu in (m.READING_GPU,'0','GPU-5d895991','all',None):
            with self.subTest(gpu=gpu):
                c=copy.deepcopy(self.candidate); c['placement']['gpu_uuid']=gpu
                with self.assertRaises(m.Refused): m.validate_candidate(c)

    def test_manifest_config_parent_domains(self):
        self.assertNotEqual(m.MANIFEST,m.OCI_CONFIG)
        for field in ('platformManifest','configDigest'):
            c=copy.deepcopy(self.candidate); c['runtime'][field]=m.PARENT
            with self.assertRaises(m.Refused): m.validate_candidate(c)

    def test_no_fake_live_or_install_authority(self):
        for field in ('installable','liveQualified'):
            c=copy.deepcopy(self.candidate); c[field]=True
            with self.assertRaises(m.Refused): m.validate_candidate(c)

    def test_resources_cannot_relax(self):
        for field,value in (('gpuReservePercent',4),('hostReservePercent',14),('outputs',2),
                            ('active',2),('steps',20),('cfg',2),('offload',True)):
            c=copy.deepcopy(self.candidate); c['resources'][field]=value
            with self.assertRaises(m.Refused): m.validate_candidate(c)
        for field in ('active','outputs','cfg'):
            c=copy.deepcopy(self.candidate); c['resources'][field]=True
            with self.assertRaises(m.Refused): m.validate_candidate(c)

    def test_cas_changed_or_missing(self):
        a,b=json.dumps(self.runtime).encode(),json.dumps(self.api).encode()
        for ea,eb in (('d'*64,m.sha(b)),(m.sha(a),'e'*64),(None,m.sha(b))):
            with self.assertRaises(m.Refused): m.plan_config_migration(a,b,ea,eb,self.graph)

    def test_migration_preserves_every_unowned_field(self):
        old=copy.deepcopy(self.runtime); oldapi=copy.deepcopy(self.api); plan=self.plan()
        expected=copy.deepcopy(old); expected.update(gpu_uuid=m.GPU,image_id=m.MANIFEST)
        api=copy.deepcopy(oldapi); api['runtime_image_digest']=m.MANIFEST
        self.assertEqual(plan['runtimeSuccessor'],expected)
        self.assertEqual(plan['apiSuccessor'],api)
        self.assertEqual(self.runtime,old); self.assertEqual(self.api,oldapi)
        self.assertFalse(plan['executable']); self.assertEqual(plan['qualification'],'NOT_TESTED')

    def test_delivery_mismatch_does_not_overwrite_source(self):
        for field in ('source_sha256','release_source_sha256'):
            prior=copy.deepcopy(self.runtime); self.runtime[field]={}
            with self.assertRaises(m.Refused): self.plan()
            self.runtime=prior
        a,b=json.dumps(self.runtime).encode(),json.dumps(self.api).encode()
        with self.assertRaises(m.Refused):
            m.plan_config_migration(a,b,m.sha(a),m.sha(b),[])

    def test_runtime_pin_owner_model_network_rejected(self):
        for field in ('owner','source_commit','checkpoint_revision','checkpoint_path','network_id','gpu_uuid','image_id'):
            prior=copy.deepcopy(self.runtime); self.runtime[field]='wrong'
            with self.assertRaises(m.Refused): self.plan()
            self.runtime=prior

    def test_api_pin_and_parent_cas(self):
        for field in ('runtime_revision','model_revision','model_id','runtime_image_digest'):
            prior=copy.deepcopy(self.api); self.api[field]='wrong'
            with self.assertRaises(m.Refused): self.plan()
            self.api=prior

    def test_exact_margin_boundaries(self):
        self.assertTrue(m.resource_guard(100,5,100,15,0))
        for values in ((100,4,100,15,0),(100,5,100,14,0),(100,5,100,15,1),
                       (0,0,100,15,0),(100,101,100,15,0),(100,5,100,101,0),
                       (True,5,100,15,0),(100,5.0,100,15,0)):
            with self.assertRaises(m.Refused): m.resource_guard(*values)

    def test_fullhd_exact_profile(self):
        value=m.validate_generation(self.args,[self.profile]); self.assertEqual(value['references'],0)
        for key,value in (('native_size','1920x1080'),('crop_bottom',0),('references',1),
                           ('transparent',True),('evidence_sha256','fake')):
            p=copy.deepcopy(self.profile); p[key]=value
            with self.assertRaises(m.Refused): m.validate_generation(self.args,[p])

    def test_no_profile_no_generation(self):
        with self.assertRaises(m.Refused): m.validate_generation(self.args,[])

    def test_seed_integer_and_mandatory(self):
        for seed in (True,-1,2**53,1.2,None):
            a=copy.deepcopy(self.args); a['seed']=seed
            with self.assertRaises(m.Refused): m.validate_generation(a,[self.profile])
        a=copy.deepcopy(self.args); del a['seed']
        with self.assertRaises(m.Refused): m.validate_generation(a,[self.profile])

    def test_references_overrides_and_edits_not_allowed(self):
        for field in ('references','steps','cfg','n','endpoint','model'):
            a=copy.deepcopy(self.args); a[field]=1
            with self.assertRaises(m.Refused): m.validate_generation(a,[self.profile])

    def test_json_duplicate_nonfinite_size_depth(self):
        for raw in (b'{"a":1,"a":2}',b'{"a":NaN}',b'x'*262145,
                    b'['*20+b'0'+b']'*20):
            with self.assertRaises(m.Refused): m.strict_json(raw)

    def test_readonly_finite_no_health_or_secrets(self):
        r=m.readonly_request(self.graph)
        self.assertEqual(r['caps']['transportInvocations'],1)
        self.assertEqual(r['authorization'],'REQUEST_ONLY_NO_GO')
        for cmd in r['commands']:
            self.assertNotIn('pull',cmd); self.assertNotIn('start',cmd)
            self.assertNotIn('stop',cmd); self.assertNotIn('restart',cmd)
        for f in r['files']:
            if 'key' in f['path']: self.assertEqual(f['projection'],'stat_only_no_content_no_hash')
        self.assertNotIn('http://',json.dumps(r['commands']))

    def test_retained_global_gate_not_unlockable(self):
        p=m.packet(); self.assertIn('followup_edit',p['generation']['gate'])
        self.assertFalse(p['runtimeProposal']['authorizedEdits'])
        self.assertEqual(p['generation']['rawPrecropArtifact'],'NOT_CAPTURED')
        self.assertIn('normal native generation',p['notTested'])
        bindings=p['generation']['reviewBindings']
        self.assertEqual(bindings['preparationSourceSha256'],m.sha(Path(m.__file__).read_bytes()))
        self.assertEqual(bindings['candidateConfigSha256'],p['candidateSha256'])
        self.assertEqual(bindings['sourceBase'],m.BASE_COMMIT)

    def test_reader_syntax_and_secret_projection(self):
        import ast
        request=m.readonly_request(self.graph); program=m.readonly_program(request)
        ast.parse(program)
        scope={'__name__':'offline_fixture'}
        exec(compile(program,'<fixed-review-reader>','exec'),scope)
        raw=json.dumps({'owner':m.OWNER,'gpu_uuid':m.GPU,'token':'SECRET-SYNTHETIC',
                        'api_key':'SECRET-SYNTHETIC','unknown':'SECRET-SYNTHETIC'}).encode()
        self.assertNotIn('SECRET-SYNTHETIC',json.dumps(scope['safe_project'](m.BASE+'/config.json',raw)))
        template=request['commands'][3][4]
        self.assertIn('gpuEnvironment',template)
        self.assertIn('false',template)

    def observation(self):
        records={}
        for i,key in enumerate(('config','state','operation','recovery','api_config','checkpoint')):
            path=m.API_CONFIG if key=='api_config' else m.MODEL+'/CHECKPOINT-RECEIPT.json' if key=='checkpoint' else m.BASE+'/'+key+'.json'
            records[key]={'fields':{},'receipt':{'outcome':'READBACK','path':path,'sha256':str(i+1)*64}}
        records['config']['fields']=copy.deepcopy(self.runtime)
        records['config']['fields'].update(image_id=m.MANIFEST,checkpointPathMatchesFixed=True)
        records['config']['fields']['checkpoint_receipt_sha256']=records['checkpoint']['receipt']['sha256']
        cid='c'*64; invocation='d'*32
        records['state']['fields']={'container':{'id':cid},'run_id':invocation}
        for key in ('operation','recovery'):
            records[key]['fields']={'status':'active','boot':'old-boot'}
        records['api_config']['fields']=copy.deepcopy(self.api)
        records['checkpoint']['fields']={'file_count':26,'revision':m.REVISION,
            'status':'COMPLETE_VERIFIED','total_bytes':33131614782}
        native={'name':'/'+m.CONTAINER,'owner':m.OWNER,'id':cid,'invocation':invocation,
            'gpu':m.READING_GPU,'image':m.MANIFEST,'configImage':m.MANIFEST,
            'running':False,'pid':0,'status':'exited','exitCode':255}
        image={'id':m.MANIFEST,'os':'linux','architecture':'amd64'}
        commands=[{'name':name,'exitCode':0,'capturedBytesComplete':True,'stdoutLog':json.dumps(value)}
            for name,value in (('gpu_inventory',{}),('gpu_processes',{}),('image_link',{}),
               ('systemd_owner',{}),('native_container',native),('native_image',image),('image_ports',{}))]
        graph=[{'path':r['installedPath'],'scope':'source_sha256' if r['installedPath'].startswith(m.BASE+'/source/') else 'release_source_sha256',
                'receipt':{'sha256':r['sha256'],'outcome':'READBACK'}} for r in self.graph
                if r['installedPath'].startswith(m.BASE+'/source/') or r['installedPath'].startswith(m.RELEASE+'/')]
        return {'origin':'LIVE_PASSIVE_READBACK','bootStable':True,'bootId':'new-boot',
            'finishedUtc':'2026-10-01T23:32:23+00:00','commands':commands,'records':records,'sourceGraph':graph}

    def test_current_reconcile_is_plan_only(self):
        value=m.reconcile_plan(self.observation(),'a'*64,self.graph)
        self.assertFalse(value['executable'])
        self.assertFalse(value['daemonIdentity']['configDomainProven'])
        self.assertEqual(value['protectedClosure']['count'],37)
        self.assertEqual(value['deltas']['runtime'],{'gpu_uuid':m.GPU})
        self.assertIn('old',value['staleRecords']['priorBoot'])

    def test_current_reconcile_rejects_fake_source_or_partial_evidence(self):
        for mutate in (
            lambda o:o.update(origin='SYNTHETIC'),
            lambda o:o.update(bootStable=False),
            lambda o:o['commands'][0].update(exitCode=True),
            lambda o:o['records']['state']['receipt'].update(outcome='FAILED'),
            lambda o:o['sourceGraph'][0]['receipt'].update(sha256='f'*64),
            lambda o:o['records']['operation']['fields'].update(boot='new-boot'),
        ):
            o=self.observation(); mutate(o)
            with self.assertRaises(m.Refused): m.reconcile_plan(o,'a'*64,self.graph)

    def test_registry_placement_only(self):
        import subprocess
        base=subprocess.run(['/usr/bin/git','show',m.BASE_COMMIT+':ai-harness/config/system-registry.json'],
                            cwd=m.ROOT,capture_output=True,check=True).stdout
        before=json.loads(base); after=json.loads((m.ROOT/'ai-harness/config/system-registry.json').read_bytes())
        entry=next(v for v in before['services'] if v['id']=='image')
        entry['placement']['gpu_uuid']=m.GPU
        self.assertEqual(before,after)


if __name__ == '__main__':
    unittest.main(verbosity=2)
