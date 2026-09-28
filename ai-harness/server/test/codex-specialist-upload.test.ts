import assert from 'node:assert/strict';
import test from 'node:test';
import {mkdtemp,realpath,rm,readFile,symlink,rename} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import sharp from 'sharp';
import {createApp, type AppOptions} from '../src/app.js';
import type {EngineFactory} from '../src/contracts.js';
async function setup(t:any, enabled=true, edits=true, trusted: Partial<AppOptions> = {}) {
 const root=await realpath(await mkdtemp(join(tmpdir(),'h021-specialist-')));const prompts:any[]=[];
 const engine:EngineFactory=()=>({async start(){},async prompt(text,attachments){prompts.push({text,attachments});},async cancel(){},async close(){}});
 const policy={codex:{enabled:true,protocolQualified:true,imageToolEnabled:enabled,engineVersion:'fixture',modelPolicyVersion:'fixture'}};
 const backend={async capabilities(){return {};},profiles(){return edits?[{operation:'edit' as const,referenceCount:1,size:'64x64',model:'fixture'}]:[];},async readiness(){return {ready:true,idle:true};},async execute(){throw Error('No image job permitted');}};
 const a=await createApp({dataDir:root,allowedOrigins:['http://localhost'],launcher:'/unused',gatewayUrl:'http://fixture.invalid',issueToken:()=> 'fixture',revokeToken(){},engineFactory:engine,codexEngineFactory:engine,enginePolicy:policy,imageBackend:backend,visionAvailable:false,...trusted});
 t.after(async()=>{await a.app.close();await rm(root,{recursive:true,force:true});});
 const session=await a.broker.createSession(undefined,'codex');
 const request=(path:string,payload?:any)=>a.app.inject({method:payload?'POST':'GET',url:path,headers:{host:'localhost'},payload});
 const upload=async(bytes:Buffer,mime='image/png')=>a.app.inject({method:'POST',url:`/api/sessions/${session.id}/uploads`,headers:{host:'localhost','content-type':'multipart/form-data; boundary=fixture'},payload:Buffer.concat([Buffer.from(`--fixture\r\nContent-Disposition: form-data; name="file"; filename="input.png"\r\nContent-Type: ${mime}\r\n\r\n`),bytes,Buffer.from('\r\n--fixture--\r\n')])});
 return {...a,root,prompts,session,request,upload,policy};
}
const png=()=>sharp({create:{width:8,height:8,channels:3,background:'#123456'}}).png().toBuffer();
test('qualified Codex upload becomes guarded specialist text reference; native attachments stay empty and original survives',async t=>{
 const f=await setup(t),bytes=await png();const health=(await f.request('/api/health')).json();assert.equal(health.engines.codex.imageToolEnabled,true);assert.equal(health.engines.codex.capabilities.media,false);
 const uploaded=await f.upload(bytes);assert.equal(uploaded.statusCode,201,uploaded.body);const id=uploaded.json().attachment.id;const stored=f.store.file(id),original=join(f.files.root,'uploads',stored.path);
 const reject=await f.request(`/api/sessions/${f.session.id}/messages`,{text:'read pixels',attachmentIds:[id]});assert.equal(reject.statusCode,400);assert.equal(reject.json().error.code,'codex_media_unsupported');
 const sent=await f.request(`/api/sessions/${f.session.id}/messages`,{text:'Use image specialist to edit',attachmentIds:[],imageReferences:[id]});assert.equal(sent.statusCode,202,sent.body);
 for(let i=0;i<100&&!f.prompts.length;i++)await new Promise(r=>setTimeout(r,5));assert.equal(f.prompts.length,1);assert.deepEqual(f.prompts[0].attachments,[]);assert.match(f.prompts[0].text,/\.image-references\//);assert.doesNotMatch(f.prompts[0].text,/localImage|data:image/);
 const reference=JSON.parse(f.prompts[0].text.split('\n').find((s:string)=>s.startsWith('".image-references/'))!);assert.deepEqual(await readFile(join(f.files.workspace(f.store.getSession(f.session.id).workspaceId),reference)),bytes);assert.deepEqual(await readFile(original),bytes);
 const other=await f.broker.createSession(undefined,'codex');const cross=await f.request(`/api/sessions/${other.id}/messages`,{text:'edit',imageReferences:[id]});assert.equal(cross.statusCode,400);
 await rename(original,original+'.preserved');await symlink(original+'.preserved',original);await assert.rejects(f.files.imageReferences(f.session.id,[id],true));
});
test('disabled or unqualified specialist and invalid image bytes reject upload with no native call',async t=>{
 for(const [enabled,edits] of [[false,true],[true,false]]){const f=await setup(t,enabled,edits);const r=await f.upload(await png());assert.equal(r.statusCode,400);assert.equal(r.json().error.code,'codex_image_tool_unavailable');assert.equal(f.prompts.length,0);}
 const f=await setup(t);const r=await f.upload(Buffer.from('not a PNG'));assert.equal(r.statusCode,400);assert.equal(r.json().error.code,'invalid_image');assert.equal(f.store.files(f.session.id,'attachment').length,0);assert.equal(f.prompts.length,0);
});
test('preview disable blocks specialist even with operational image flag and edit profile',async t=>{const f=await setup(t);f.policy.codex.enabled=false;assert.equal((await f.request('/api/health')).json().engines.codex.imageToolEnabled,false);const r=await f.upload(await png());assert.equal(r.statusCode,400);assert.equal(f.prompts.length,0);});
test('dispatch requires exact qualified edit reference count',async t=>{const f=await setup(t);const one=await f.upload(await png());const two=await f.upload(await png());assert.equal(one.statusCode,201);assert.equal(two.statusCode,201);const r=await f.request(`/api/sessions/${f.session.id}/messages`,{text:'edit two',imageReferences:[one.json().attachment.id,two.json().attachment.id]});assert.equal(r.statusCode,400);assert.equal(r.json().error.code,'codex_image_tool_unavailable');assert.equal(f.prompts.length,0);});

test('private image acceptance preserves global disabled capability and closes reference gates',async t=>{
 let allowed:string|undefined;const f=await setup(t,false,true,{imageAcceptance:id=>id===allowed});
 assert.equal((await f.upload(await png())).statusCode,400);allowed=f.session.id;
 assert.equal((await f.request('/api/health')).json().engines.codex.imageToolEnabled,false);
 const uploaded=await f.upload(await png());assert.equal(uploaded.statusCode,201,uploaded.body);
 const other=await f.broker.createSession(undefined,'codex');
 assert.equal((await f.request(`/api/sessions/${other.id}/messages`,{text:'edit',imageReferences:[uploaded.json().attachment.id]})).statusCode,400);
 allowed=undefined;
 assert.equal((await f.request(`/api/sessions/${f.session.id}/messages`,{text:'edit',imageReferences:[uploaded.json().attachment.id]})).statusCode,400);
 assert.equal((await f.upload(await png())).statusCode,400);assert.equal(f.prompts.length,0);
});

test('trusted run acceptance precedes dispatch and final callback preserves ordinary completion',async t=>{
 const accepted:any[]=[],finished:any[]=[];let f:Awaited<ReturnType<typeof setup>>;
 f=await setup(t,false,true,{onRunAccepted:(sessionId,runId)=>{assert.equal(f.prompts.length,0);assert.equal(f.store.getSession(sessionId).status,'queued');accepted.push({sessionId,runId});throw Error('optional scope unavailable');},onRunFinished:(sessionId,runId)=>finished.push({sessionId,runId})});
 const runId=f.broker.enqueue(f.session.id,'message','ordinary text');
 assert.deepEqual(accepted,[{sessionId:f.session.id,runId}]);
 for(let i=0;i<100&&!finished.length;i++)await new Promise(r=>setTimeout(r,5));
 assert.equal(f.prompts.length,1);assert.deepEqual(finished,accepted);
});

test('unbound reference staging preserves strict ownership and requires running permission at dispatch',async t=>{
 let staged:string|undefined,run:string|undefined;let f:Awaited<ReturnType<typeof setup>>;
 f=await setup(t,false,true,{imageReferenceAcceptance:id=>id===staged,imageAcceptance:id=>id===staged&&f.broker.currentImageRun(id)?.runId===run&&run!==undefined,onRunAccepted:(_id,rid)=>{run=rid;}});
 staged=f.session.id;
 assert.equal((await f.request('/api/health')).json().engines.codex.imageToolEnabled,false);
 const invalid=await f.upload(Buffer.from('not an image'));assert.equal(invalid.statusCode,400);assert.equal(invalid.json().error.code,'invalid_image');
 const uploaded=await f.upload(await png());assert.equal(uploaded.statusCode,201,uploaded.body);assert.equal(run,undefined);
 const fileId=uploaded.json().attachment.id,other=await f.broker.createSession(undefined,'codex');
 staged=other.id;
 const foreign=await f.request(`/api/sessions/${other.id}/messages`,{text:'edit',imageReferences:[fileId]});assert.equal(foreign.statusCode,400);assert.equal(foreign.json().error.code,'invalid_image_reference');assert.equal(run,undefined);
 staged=f.session.id;
 const invalidId=await f.request(`/api/sessions/${f.session.id}/messages`,{text:'edit',imageReferences:['../foreign']});assert.equal(invalidId.statusCode,400);
 const accepted=await f.request(`/api/sessions/${f.session.id}/messages`,{text:'edit owned reference',imageReferences:[fileId]});assert.equal(accepted.statusCode,202,accepted.body);
 for(let i=0;i<100&&!f.prompts.length;i++)await new Promise(r=>setTimeout(r,5));
 assert.equal(f.prompts.length,1);assert.match(f.prompts[0].text,/\.image-references\//);assert.deepEqual(f.prompts[0].attachments,[]);
 assert.equal((await f.request('/api/health')).json().engines.codex.imageToolEnabled,false);
});

test('reference staging alone never qualifies dispatch',async t=>{
 let staged:string|undefined;const finished:string[]=[];const f=await setup(t,false,true,{imageReferenceAcceptance:id=>id===staged,onRunFinished:(_sid,rid)=>finished.push(rid)});staged=f.session.id;
 const uploaded=await f.upload(await png());assert.equal(uploaded.statusCode,201);
 const accepted=await f.request(`/api/sessions/${f.session.id}/messages`,{text:'edit',imageReferences:[uploaded.json().attachment.id]});assert.equal(accepted.statusCode,202);
 for(let i=0;i<100&&!finished.length;i++)await new Promise(r=>setTimeout(r,5));
 assert.equal(finished.length,1);assert.equal(f.prompts.length,0);assert.equal(f.store.getSession(f.session.id).status,'failed');
});
