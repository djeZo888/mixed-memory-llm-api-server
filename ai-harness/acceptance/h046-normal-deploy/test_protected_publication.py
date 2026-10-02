import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('protected_publication',HERE/'protected_publication.py')
p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)

class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=HERE)
        self.root=Path(self.tmp.name).resolve()
        self.key=b'k'*32
        self.now=int(time.time()*1000)
        self.owner={'pid':12345,'startTicks':'6789','uid':os.getuid(),
                    'bootId':'12345678-1234-1234-1234-123456789abc','cgroupPath':'/test/app.service'}
    def tearDown(self): self.tmp.cleanup()
    def file(self,path,raw):
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(raw);path.chmod(0o600);return path
    def graph(self):
        server=self.root/'server';deploy=self.root/'deploy'
        self.file(server/'dist/main.js',b'import "./dep.js";\n')
        self.file(server/'dist/codex-preview-main.js',b'export {};\n')
        self.file(server/'dist/dep.js',b'export {};\n')
        for name in ('main','codex-preview-main','dep'):self.file(server/'src'/f'{name}.ts',b'export {};\n')
        self.file(server/'package-lock.json',b'{}\n')
        for name in p.receipt_names('generation'):
            self.file(Path(os.path.normpath(str(deploy/name))),b'# pinned source\n')
        self.file(deploy/'engine/validate-image-overlays.py',b'# validator\n')
        return server,deploy
    def go(self):
        body={'sourceCommit':'a'*40,'receiptSources':{'one':'b'*64}}
        target=self.root/'ticket.json';claims=self.root/'claims';claims.mkdir(mode=0o700)
        config=self.file(self.root/'config',b'current config')
        config_files={str(config):p.sha(config.read_bytes())}
        observation={'schema':'h046-root-app-observation-v1','owner':self.owner,'observedAtMs':self.now,
                     'unit':'ai-harness.service','invocationId':'c'*32,'sourceCommit':'d'*40,
                     'configSha256':p.sha(p.canonical(config_files)),'activeRuns':0,'activeImageJobs':0,
                     'activeVisionJobs':0,'originalLogSha256':'e'*64}
        obs=self.file(self.root/'owner.json',p.canonical(observation))
        g={'schema':'h046-protected-publication-go-v1','reviewedBy':'root',
           'id':'12345678-1234-1234-1234-123456789abc','operation':'ordinary-current-sources',
           'issuedAtMs':self.now-1,'expiresAtMs':self.now+60000,'maxInvocations':1,
           'sourceCommit':body['sourceCommit'],'bodySha256':p.sha(p.canonical(body)),
           'receiptSourcesSha256':p.sha(p.canonical(body['receiptSources'])),
           'helperSha256':p.sha(p.read_bytes(HERE/'protected_publication.py')),
           'baselinePath':str(self.root/'baseline'),'keyPath':str(self.root/'key'),
           'targetPath':str(target),'claimsDir':str(claims),'owner':self.owner,
           'ownerObservationPath':str(obs),'ownerObservationSha256':p.sha(obs.read_bytes()),'configFiles':config_files}
        return body,g,target,claims
    def validate(self,body,g,target,claims):
        with patch.object(p,'observe_owner',return_value=self.owner),patch.object(p,'observe_unit',return_value={
                'MainPID':'12345','InvocationID':'c'*32,'ControlGroup':self.owner['cgroupPath']}):
            return p.validate_go(p.seal(g,self.key),self.key,body,'ordinary-current-sources',
                                 g['baselinePath'],g['keyPath'],target,claims,self.now)
    def test_canonical_matches_js_utf16_order(self):
        v={'\ue000':1,'\U00010000':2,'z':[True,None,'\nλ']}
        script="let b='';for await(const c of process.stdin)b+=c;const v=JSON.parse(b);function f(x){if(Array.isArray(x))return '['+x.map(f).join(',')+']';if(x&&typeof x==='object')return '{'+Object.keys(x).sort().map(k=>JSON.stringify(k)+':'+f(x[k])).join(',')+'}';return JSON.stringify(x)}process.stdout.write(f(v));"
        r=subprocess.run(['node','--input-type=module','-e',script],input=json.dumps(v).encode(),capture_output=True,check=True)
        self.assertEqual(p.canonical(v),r.stdout)
    def test_signed_floats_forbidden(self):
        with self.assertRaises(p.Refused):p.canonical({'n':1.0})
    def test_wrong_key_and_unsigned_rejected(self):
        with self.assertRaises(p.Refused):p.verify_envelope(p.seal({'x':1},self.key),b'q'*32)
        with self.assertRaises(p.Refused):p.verify_envelope({'body':{}},self.key)
    def test_duplicate_json_rejected(self):
        path=self.file(self.root/'duplicate',b'{"x":1,"x":2}')
        with self.assertRaises(p.Refused):p.load_json(path,private=True)
    def test_private_file_mode_link_alias_rejected(self):
        path=self.file(self.root/'private',b'secret fixture')
        path.chmod(0o644)
        with self.assertRaises(p.Refused):p.read_bytes(path,private=True)
        path.chmod(0o600);os.link(path,self.root/'hardlink')
        with self.assertRaises(p.Refused):p.read_bytes(path,private=True)
        os.unlink(self.root/'hardlink');(self.root/'alias').symlink_to(path)
        with self.assertRaises(p.Refused):p.read_bytes(self.root/'alias',private=True)
    def test_exact_graph_does_not_include_unimported_startup_helper(self):
        server,deploy=self.graph();self.file(deploy/'run-server.sh',b'unimported helper')
        files,sources=p.current_graph(server,deploy,'generation')
        self.assertNotIn(str(deploy/'run-server.sh'),files)
        self.assertIn(str(server/'dist/dep.js'),files)
        self.assertIn(str(server/'src/dep.ts'),files)
        self.assertEqual(set(sources),set(p.BASE+p.GEN))
        self.assertEqual(len(sources),12)
    def test_import_escape_and_missing_source_rejected(self):
        server,deploy=self.graph();self.file(server/'dist/main.js',b'import "../../outside.js";')
        with self.assertRaises(p.Refused):p.current_graph(server,deploy,'generation')
        self.file(server/'dist/main.js',b'import "./dep.js";');(server/'src/dep.ts').unlink()
        with self.assertRaises(FileNotFoundError):p.current_graph(server,deploy,'generation')
    def test_missing_baseline_never_fabricated(self):
        with self.assertRaises(FileNotFoundError):p.validate_baseline(self.root/'absent',self.root/'key',self.root/'server')
    def test_final_release_metadata_and_sibling_paths_bind_commit(self):
        commit='a'*40
        root=self.root/'releases';release=root/(commit+'-h046-normal05')/'ai-harness'
        (release/'server').mkdir(parents=True);(release/'deploy').mkdir()
        self.file(release/'source-commit.txt',commit.encode()+b'\n')
        with patch.object(p,'RELEASES_ROOT',root):
            p.validate_release_paths(release/'server',release/'deploy',commit)
            for server,deploy,head in [(release/'server',release/'deploy','b'*40),
                                      (release/'server',self.root/'deploy',commit)]:
                with self.assertRaises(p.Refused):p.validate_release_paths(server,deploy,head)
            self.file(release/'source-commit.txt',b'b'*40+b'\n')
            with self.assertRaises(p.Refused):p.validate_release_paths(release/'server',release/'deploy',commit)
    def test_valid_root_go_scope(self):
        body,g,target,claims=self.go();self.assertEqual(self.validate(body,g,target,claims),g)
    def test_expired_repeated_or_scope_widened_go_rejected(self):
        body,g,target,claims=self.go()
        for field,value in [('expiresAtMs',self.now),('maxInvocations',2),('maxInvocations',True),('sourceCommit','f'*40),
                            ('bodySha256','0'*64),('helperSha256','0'*64),('targetPath',str(self.root/'other'))]:
            bad={**g,field:value}
            with self.assertRaises(p.Refused):self.validate(body,bad,target,claims)
        g['rawGenerationEnabled']=True
        with self.assertRaises(p.Refused):self.validate(body,g,target,claims)
    def test_busy_stale_config_or_owner_observation_rejected(self):
        body,g,target,claims=self.go();obs=Path(g['ownerObservationPath'])
        for field,value in [('activeRuns',1),('observedAtMs',self.now-15001),('configSha256','0'*64)]:
            original=json.loads(obs.read_bytes());changed={**original,field:value}
            obs.write_bytes(p.canonical(changed));bad={**g,'ownerObservationSha256':p.sha(obs.read_bytes())}
            with self.assertRaises(p.Refused):self.validate(body,bad,target,claims)
            obs.write_bytes(p.canonical(original))
        self.file(self.root/'config',b'changed')
        with self.assertRaises(p.Refused):self.validate(body,g,target,claims)
    def test_exclusive_claim_stays_spent(self):
        claim=self.root/'claim.json';p.exclusive(claim,b'one')
        with self.assertRaises(FileExistsError):p.exclusive(claim,b'two')
        self.assertEqual(claim.read_bytes(),b'one')
    def test_generation_exact_body_and_capacity(self):
        sidecar={'sourceCommit':'a'*40,'profile':'generation','receiptSources':{'x':'b'*64}}
        expected={'sourceCommit':sidecar['sourceCommit'],'profile':'generation',
                  'currentSourceSha256':p.sha(p.canonical(sidecar)),
                  'receiptSourcesSha256':p.sha(p.canonical(sidecar['receiptSources']))}
        with patch.object(p,'validate_sidecar',return_value=sidecar),patch.object(p,'observe_owner',return_value=self.owner),\
             patch.object(p,'actual_current_loader',return_value={'generationAuthority':expected}):
            body=p.prepare_generation('baseline.sources.json','baseline','key',
                '12345678-1234-1234-1234-123456789abc','22345678-1234-1234-1234-123456789abc',12345,self.now-10,self.now+60000)
            self.assertEqual(set(body),{'schema','reviewedBy','id','sessionId','issuedAtMs','expiresAtMs',
                'maxNativeRuns','maxImageJobs','operation','size','authority','owner'})
            self.assertEqual((body['maxNativeRuns'],body['maxImageJobs'],body['size']),(1,1,'1920x1080'))
            with self.assertRaises(p.Refused):p.prepare_generation('baseline.sources.json','baseline','key',
                body['id'],body['sessionId'],12345,self.now-10,self.now+1800001)

if __name__=='__main__':unittest.main()
