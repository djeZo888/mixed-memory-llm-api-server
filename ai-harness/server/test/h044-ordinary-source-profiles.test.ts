/** Protected SOURCE fixtures only. No startup or model qualification is issued. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {chmodSync,mkdtempSync,realpathSync,mkdirSync,writeFileSync,readFileSync,rmSync} from 'node:fs';
import {homedir} from 'node:os';
import {join,dirname} from 'node:path';
import {createHash,createHmac,randomBytes} from 'node:crypto';
import {canonicalJson} from '../src/codex-canonical.js';
import {loadCodexOrdinaryEntry,type CodexOrdinarySourceProfile} from '../src/codex-ordinary-entry.js';
import {codexReceiptSourceProfile} from '../src/codex-receipts.js';
import {receiptFixture} from './helpers/codex-receipt-fixture.js';
const sha=(b:string|Buffer)=>createHash('sha256').update(b).digest('hex');
function fixture(t:test.TestContext,profile:CodexOrdinarySourceProfile='technical-generation'){
 const root=realpathSync(mkdtempSync(join(homedir(),'h044-source-profiles-'))),key=randomBytes(32),keyPath=join(root,'key'),path=join(root,'entry'),sourcePath=path+'.sources.json';
 chmodSync(root,0o700);writeFileSync(keyPath,key,{mode:0o600});t.after(()=>rmSync(root,{recursive:true,force:true}));
 const put=(p:string,s:string)=>{mkdirSync(dirname(p),{recursive:true,mode:0o700});writeFileSync(p,s,{mode:0o600});return sha(s);};
 const oldServer=join(root,'original/server'),oldDeploy=join(root,'original/deploy'),serverDir=join(root,'current/server'),deploymentDir=join(root,'current/deploy');
 const originalFiles:Record<string,string>={},files:Record<string,string>={};
 for(const [dir,closure,current] of [[oldServer,originalFiles,false],[serverDir,files,true]] as const){
  for(const name of current?['main','codex-preview-main','codex-instructions']:['main','codex-preview-main']){
   closure[join(dir,'dist',name+'.js')]=put(join(dir,'dist',name+'.js'),name==='main'&&current?'import "./codex-instructions.js";':'export {};');
   closure[join(dir,'src',name+'.ts')]=put(join(dir,'src',name+'.ts'),'export {};');
  }
  closure[join(dir,'package-lock.json')]=put(join(dir,'package-lock.json'),'{}');
 }
 const f=receiptFixture();for(const name of Object.keys(f.binding.sources)){const hash=put(join(oldDeploy,name),'original-helper');originalFiles[join(oldDeploy,name)]=hash;f.binding.sources[name]=hash;f.rawLaunch.sources[name]=hash;}
 const launchPath=join(root,'launch.json'),settlementPath=join(root,'settlement.json'),protocolAckPath=join(root,'acks.json'),binaryPath=join(root,'binary');
 const qualification={launchPath,settlementPath,protocolAckPath,binaryPath,launchSha256:put(launchPath,JSON.stringify(f.rawLaunch)),settlementSha256:put(settlementPath,JSON.stringify(f.rawSettlement)),protocolAckSha256:put(protocolAckPath,JSON.stringify({schema:'codex-zero-generation-acks-v1',launchNonce:f.rawLaunch.nonce,initialize:{codexHome:f.binding.profileDir+'/codex-home',platformOs:'linux',userAgent:'codex/0.158.0'},threadStart:{thread:{id:'synthetic'},model:'qwen3.8-27b',modelProvider:'sova',cwd:f.binding.workspace},providerRequests:0})),binarySha256:put(binaryPath,'synthetic native binary'),binaryVersion:'0.158.0',upstream:'064c6b8c737f5b41d171fdda80bd9ef10ad06eb3',binding:f.binding,observedProducer:f.producer,validatedAtMs:f.now};
 const baseline={schema:'codex-ordinary-entry-v1',approvalId:'original-baseline',sourceCommit:'a'.repeat(40),files:originalFiles,receiptSources:f.binding.sources,qualification};
 const seal=(body:unknown)=>JSON.stringify({body,seal:createHmac('sha256',key).update(canonicalJson(body)).digest('hex')});put(path,seal(baseline));const original=readFileSync(path);
 const technical=profile==='technical'||profile==='technical-generation',generation=profile==='generation'||profile==='technical-generation';
 const receiptSources=Object.fromEntries(codexReceiptSourceProfile(technical,generation).map(name=>{const hash=put(join(deploymentDir,name),'current-helper:'+name);files[join(deploymentDir,name)]=hash;return [name,hash];}));
 files[join(deploymentDir,'engine/validate-image-overlays.py')]=put(join(deploymentDir,'engine/validate-image-overlays.py'),'reviewed-validator');
 const body:any={schema:'codex-ordinary-current-sources-v1',reviewedBy:'root',reviewedAt:'2026-10-01T00:00:00Z',baselineApprovalSha256:sha(original),baselineApprovalId:baseline.approvalId,sourceCommit:'b'.repeat(40),serverDir,deploymentDir,profile,files,receiptSources};
 const reseal=()=>put(sourcePath,seal(body));reseal();
 return {root,path,keyPath,sourcePath,body,baseline,original,reseal,serverDir,deploymentDir,f,load:()=>loadCodexOrdinaryEntry(path,keyPath,{serverDir,deploymentDir})!};
}
for(const profile of ['ordinary','technical','generation','technical-generation'] as const)test(`independent authenticated ${profile} current closure preserves original baseline and grants no feature`,t=>{
 const f=fixture(t,profile),entry=f.load();assert.deepEqual(entry.nativeReceiptPolicy.sourceSha256,f.body.receiptSources);assert.deepEqual(readFileSync(f.path),f.original);
 assert.equal((entry as any).imageGenerationQualified,undefined);assert.equal((entry as any).technicalVisionQualified,undefined);
 assert.throws(()=>entry.assertCurrent(f.f.launch),/genuinely qualified/);
});
for(const mutation of ['forged-seal','wrong-baseline','missing-instructions','changed-instructions','missing-helper','extra-source','stale-hash','profile-mismatch','boolean-grant','source-name-grant','wrong-runtime','writable-source','original-ack','original-body','arbitrary-file'] as const)test(`current source approval rejects ${mutation} independently`,t=>{
 const f=fixture(t);
 switch(mutation){
  case 'forged-seal':writeFileSync(f.sourcePath,JSON.stringify({body:f.body,seal:'0'.repeat(64)}));break;
  case 'wrong-baseline':f.body.baselineApprovalSha256='0'.repeat(64);f.reseal();break;
  case 'missing-instructions':delete f.body.files[join(f.serverDir,'dist/codex-instructions.js')];f.reseal();break;
  case 'changed-instructions':writeFileSync(join(f.serverDir,'dist/codex-instructions.js'),'changed operative instruction');break;
  case 'missing-helper':delete f.body.receiptSources['../tools/image/image.mjs'];f.reseal();break;
  case 'extra-source':f.body.receiptSources['../arbitrary.mjs']='a'.repeat(64);f.reseal();break;
  case 'stale-hash':f.body.receiptSources['run-codex.sh']='a'.repeat(64);f.reseal();break;
  case 'profile-mismatch':f.body.profile='technical';f.reseal();break;
  case 'boolean-grant':f.body.generationQualified=true;f.reseal();break;
  case 'source-name-grant':f.body.profile='root-reviewed-PASS';f.reseal();break;
  case 'wrong-runtime':f.body.serverDir=f.root;f.reseal();break;
  case 'writable-source':chmodSync(join(f.serverDir,'dist/codex-instructions.js'),0o666);break;
  case 'original-ack':writeFileSync(f.baseline.qualification.protocolAckPath,'{}');break;
  case 'original-body':writeFileSync(f.path,JSON.stringify({...JSON.parse(f.original.toString()),body:{...f.baseline,sourceCommit:'c'.repeat(40)}}));break;
  case 'arbitrary-file':{const p=join(f.root,'extra');writeFileSync(p,'x',{mode:0o600});f.body.files[p]=sha('x');f.reseal();break;}
 }
 assert.throws(f.load);
});
test('baseline without a current source approval cannot silently admit a different release',t=>{const f=fixture(t);rmSync(f.sourcePath);assert.throws(f.load,/omits actual executing/);assert.deepEqual(readFileSync(f.path),f.original);});
