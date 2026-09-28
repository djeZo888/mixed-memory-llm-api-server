#!/usr/bin/env node
// Bounded operator runner. No model access in prepare mode; one bounded batch, existing host settlement before each handoff.
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { readFile, writeFile, mkdir, open, copyFile } from 'node:fs/promises';
import { resolve, dirname, basename, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
const repo = resolve(dirname(fileURLToPath(import.meta.url)), '../../..');
const fixtureRoot = join(repo, 'ai-harness/server/test/fixtures/h021-matched');
const sha = data => createHash('sha256').update(data).digest('hex');
export const cases = JSON.parse(await readFile(join(fixtureRoot, 'CASES.json'), 'utf8')).cases.filter(c => c.id !== 'image-specialist');
const implementations = { 'python-boundary': 'bins.py', 'cpp-bounds': 'prefix.hpp', 'node-async-validation': 'load.mjs' };
const checks = {
  'python-boundary': [['python3', '-m', 'unittest', '-v', 'test_bins.py']],
  'cpp-bounds': [['c++', '-std=c++17', '-Wall', '-Wextra', '-Werror', 'test_prefix.cpp', '-o', 'test-prefix'], ['./test-prefix']],
  'node-async-validation': [['node', '--test', 'test_load.mjs']],
};
export function taskText(c) {
  if (c.id === 'pdf-units') return 'Read the attached source.pdf using the installed local PDF skill/helper. Extract and render page 1. State its supply voltage and current limit, convert the current to amperes, and cite page 1. Create a one-page summary PDF in artifacts/. Retain the source unchanged; report actual tool failures.';
  if (!c.files) return c.task;
  return `${c.task} Copy the attached implementation and independent test into a working directory using their original filenames; do not change the tests. Run the tests, save the repaired implementation as artifacts/${implementations[c.id]}, and report the actual result. Use no delegation, external dependencies, internet, image tools or frontier model.`;
}
export async function prepare(out, pdf) {
  await mkdir(out, {recursive: false});
  const plan = [];
  for (const c of cases) {
    const dir = join(out, c.id); await mkdir(dir);
    const inputs = [];
    for (const name of c.files ?? []) {
      const bytes = await readFile(join(fixtureRoot, name));
      await copyFile(join(fixtureRoot, name), join(dir, basename(name)));
      inputs.push({name: basename(name), sha256: sha(bytes), bytes: bytes.length});
    }
    if (c.id === 'pdf-units' && pdf) {
      const bytes = await readFile(pdf); assert(bytes.subarray(0, 5).toString() === '%PDF-');
      await writeFile(join(dir, 'source.pdf'), bytes, {flag: 'wx', mode: 0o600});
      inputs.push({name: 'source.pdf', sha256: sha(bytes), bytes: bytes.length});
    }
    plan.push({id: c.id, prompt: taskText(c), inputs, check: checks[c.id] ?? 'Manual independent tool/source/artifact review', status: c.id === 'pdf-units' && !pdf ? 'NEEDS_OWNED_PDF_INPUT' : 'PREPARED_NOT_RUN'});
  }
  // Operator material lives above case input directories and is never uploaded.
  await writeFile(join(out, 'PLAN.json'), JSON.stringify({schema: 'h021-matched-plan-v1', cases: plan}, null, 2)+'\n', {flag:'wx',mode:0o600});
  return plan;
}
export function validateGo(g, source, now = Date.now()) {
  assert.equal(g.schema, 'h021-matched-batch-go-v1');
  assert.equal(g.exactSource, source, 'GO candidate differs from this checkout');
  assert.match(source, /^[a-f0-9]{40}$/);
  const origin = new URL(g.origin); assert(['http:', 'https:'].includes(origin.protocol));
  assert.equal(origin.origin, g.origin); assert(!origin.username && !origin.password);
  assert.equal(g.scope, 'Sova API matched batch');
  assert.equal(g.model, 'qwen3.8-27b'); assert.equal(g.lane, 'Qwen0');
  assert.equal(g.context, 480000); assert.equal(g.outputCap, 1024);
  assert.equal(g.retryCount, 0); assert.equal(g.sharedAdmission, true);
  assert.equal(g.previousOwnerSettled, true); assert.equal(g.protocolQualified, true);
  assert.equal(g.nativeCli, '0.158.0');
  assert.match(g.imageDigest, /^(sha256:)?[a-f0-9]{64}$/);
  assert.match(g.profileSha256, /^[a-f0-9]{64}$/);
  assert.match(g.readbackSha256, /^[a-f0-9]{64}$/);
  for (const key of ['pilotId','laneOwner','coordinator','readbackPath']) assert(typeof g[key] === 'string' && g[key].length > 0);
  assert(Number.isFinite(Date.parse(g.expiresUtc)) && Date.parse(g.expiresUtc) > now && Date.parse(g.expiresUtc) <= now + 40*60_000, 'GO missing, expired or beyond bounded task');
  assert(Array.isArray(g.schedule) && g.schedule.length > 0 && g.schedule.length <= 10);
  const seen=new Set();
  for(const step of g.schedule) {
    assert(['minimax','codex'].includes(step.engine)); assert(cases.some(c=>c.id===step.caseId));
    const key=step.engine+':'+step.caseId;assert(!seen.has(key),'no automatic repair/repeat in batch');seen.add(key);
  }
  return g;
}
async function save(dir, name, data) {
  await writeFile(join(dir,name), JSON.stringify(data,null,2)+'\n', {flag:'wx',mode:0o600});
}
// Writes the no-replay marker durably BEFORE the one non-idempotent prompt POST.
async function intent(dir, data) {
  const f = await open(join(dir,'DISPATCH-INTENT.json'),'wx',0o600);
  try {await f.writeFile(JSON.stringify(data,null,2)+'\n'); await f.sync();} finally {await f.close();}
}
export async function runOne(g, inputsDir, out, {source, fetcher=fetch, wait=ms=>new Promise(r=>setTimeout(r,ms)), pollMs=1000, maxPolls=300} = {}) {
  validateGo(g, source);
  assert(g.schedule.some(step=>step.engine===g.engine && step.caseId===g.caseId),'case absent from reviewed batch');
  assert.equal(sha(await readFile(g.readbackPath)), g.readbackSha256, 'deployed owner readback differs');
  const c = cases.find(c => c.id === g.caseId);
  const files = (c.files ?? []).map(name => basename(name));
  if (c.id === 'pdf-units') files.push('source.pdf');
  // Only hard-coded input names; never upload PLAN, CASES, reference solutions or expected answers.
  const inputs = await Promise.all(files.map(async name=>({name,bytes:await readFile(join(inputsDir,c.id,name))})));
  for(const name of c.files ?? []) {
    const input=inputs.find(f=>f.name===basename(name));
    assert.equal(sha(input.bytes),sha(await readFile(join(fixtureRoot,name))),'staged buggy source/test changed; do not expose repaired answers');
  }
  await mkdir(out, {recursive:false});
  await save(out,'GO.json',g);
  let sessionId, runId; const startedUtc = new Date().toISOString(); const start = performance.now();
  const result = {engine:g.engine,caseId:g.caseId,exactSource:source,model:g.model,lane:g.lane,imageDigest:g.imageDigest,profileSha256:g.profileSha256,nativeCli:g.engine==='codex'?g.nativeCli:null,context:g.context,outputCap:g.outputCap,startedUtc,retryCount:0,inputTokens:null,outputTokens:null,tokenUsageReason:'Public Sova snapshot exposes occupied context, not billing input/output usage; request W1 gateway receipt',toolErrors:[],interventions:[],verdict:'NOT_TESTED',settlement:'REQUIRES_EXISTING_AUTHORITATIVE_HOST_SETTLEMENT'};
  async function request(path, options={}) {
    assert(Date.now() < Date.parse(g.expiresUtc),'GO expired; stop without retry');
    const r = await fetcher(g.origin+path,{...options,redirect:'error',headers:{Origin:g.origin,...options.headers},signal:AbortSignal.timeout(30_000)});
    if (!r.ok) throw Error(`Sova ${options.method ?? 'GET'} ${path} HTTP ${r.status}`);
    return r;
  }
  const post = async (path, value) => (await request(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(value)})).json();
  try {
    const health = await (await request('/api/health')).json(); await save(out,'health.json',health);
    assert.equal(health.engines?.default,'minimax');
    if(g.engine==='codex') assert(health.engines?.codex?.available && health.engines.codex.protocolQualified);
    const created = await post('/api/sessions',{engineKind:g.engine}); sessionId=created.session.id; result.sessionId=sessionId;
    await save(out,'created.json',created); assert.equal(created.session.engineKind,g.engine);
    result.engineVersion=created.session.engineVersion ?? null;
    if(g.engine==='minimax') result.nativeCli=created.session.engineVersion ?? null;
    const attachmentIds=[];
    for(const input of inputs) {
      const form=new FormData();form.append('file',new Blob([input.bytes]),input.name);
      const uploaded=await (await request(`/api/sessions/${sessionId}/uploads`,{method:'POST',body:form})).json();
      attachmentIds.push(uploaded.attachment.id);
      // Check upload/download bytes without consulting any existing chat.
      const download=await request(`/api/attachments/${uploaded.attachment.id}/download`);
      assert.equal(sha(Buffer.from(await download.arrayBuffer())),sha(input.bytes));
      await save(out,`upload-${input.name}.json`,{...uploaded,sha256:sha(input.bytes)});
    }
    const text=taskText(c); await intent(out,{sessionId,text,attachmentIds,startedUtc});
    ({runId}=await post(`/api/sessions/${sessionId}/messages`,{text,attachmentIds}));
    result.runId=runId; await save(out,'accepted.json',{runId,sessionId});
    let snapshot;
    for(let i=0;i<maxPolls;i++) {
      snapshot=await (await request(`/api/sessions/${sessionId}`)).json();
      assert.equal(snapshot.session.engineKind,g.engine,'engine changed');
      const run=snapshot.runs.find(r=>r.id===runId);
      if(run && ['completed','failed','cancelled','interrupted'].includes(run.status) && !['queued','running','compacting','cancelling'].includes(snapshot.session.status)) break;
      snapshot=undefined; await wait(pollMs);
    }
    if(!snapshot) throw Error('Bounded observation ended; ownership uncertain, no automatic cancel or replay');
    await save(out,'snapshot.json',snapshot);
    result.runStatus=snapshot.runs.find(r=>r.id===runId)?.status;
    result.toolErrors=snapshot.activities.filter(a=>a.status==='failed').map(a=>({id:a.id,name:a.name,summary:a.summary}));
    // Reconnect readback only: no prompt POST; preserve history/event identities.
    const reconnected=await (await request(`/api/sessions/${sessionId}`)).json();
    assert.deepEqual(reconnected.runs.map(r=>r.id),snapshot.runs.map(r=>r.id));
    assert(snapshot.messages.every(m=>reconnected.messages.some(n=>n.id===m.id && n.content===m.content)));
    await save(out,'reconnect.json',reconnected);
    result.artifacts=[];
    await mkdir(join(out,'downloads'));
    for(const a of snapshot.artifacts) {
      // Never trust arbitrary download URLs from model-produced text.
      const bytes=Buffer.from(await (await request(`/api/artifacts/${a.id}/download`)).arrayBuffer());
      const name=`${a.id}-${basename(a.name)}`;
      await writeFile(join(out,'downloads',name),bytes,{flag:'wx',mode:0o600});
      result.artifacts.push({id:a.id,name:a.name,local:name,sha256:sha(bytes),bytes:bytes.length});
    }
    result.verdict=result.runStatus==='completed'?'PENDING_INDEPENDENT_CHECK':'FAIL';
    result.independentCheck=checks[c.id] ?? 'Review actual tool calls/source URL/numeric units/PDF visual rendering';
    // Downloaded model code is never executed on the Mac operator host by this runner.
  } catch(e) {
    result.verdict=runId?'FAIL':'BLOCKED_OR_UNCERTAIN';
    result.error=String(e.message);result.sessionId=sessionId;result.runId=runId;
  } finally {
    result.elapsedMs=Math.round(performance.now()-start);
    await save(out,'RESULT.json',result);
  }
  return result;
}
/** Host hook is W1-owned and must combine gateway/native/children/image settlement.
 * Never infer it from public idle status, cancel ACK, or an empty local array.
 * No new observer/service is installed here. Missing hook fails before HTTP.
 */
export async function runBatch(g, inputsDir, out, options={}) {
  validateGo(g, options.source);
  assert.equal(typeof options.confirmSettlement,'function','W1 existing authoritative host settlement hook required; no dispatch');
  await mkdir(out,{recursive:false});await save(out,'BATCH-GO.json',g);
  const results=[];let blocked;
  for(const [index,step] of g.schedule.entries()) {
    const result=await runOne({...g,...step},inputsDir,join(out,`${String(index+1).padStart(2,'0')}-${step.engine}-${step.caseId}`),options);
    results.push(result);
    if(!result.sessionId || !result.runId) {blocked='Dispatch/session outcome uncertain; stop without replay';break;}
    try {
      const settled=await options.confirmSettlement({sessionId:result.sessionId,runId:result.runId,exactSource:g.exactSource,pilotId:g.pilotId});
      await save(out,`settlement-${index+1}.json`,settled ?? null);
      assert.equal(settled?.sessionId,result.sessionId);
      assert.equal(settled?.settled,true,'Existing host could not prove all owned work settled');
      result.settlement='CONFIRMED_BY_EXISTING_HOST_HOOK';
    } catch(e) {blocked=String(e.message);break;}
  }
  const summary={schema:'h021-matched-batch-result-v1',status:blocked?'BLOCKED':'PENDING_INDEPENDENT_CHECKS',blocked,results,dispatchRetries:0};
  await save(out,'BATCH-RESULT.json',summary);return summary;
}
if (process.argv[1] && resolve(process.argv[1])===fileURLToPath(import.meta.url)) {
  const [mode,a,b,c,hookPath]=process.argv.slice(2);
  if(mode==='--prepare' && a) console.log(JSON.stringify(await prepare(resolve(a),b && resolve(b))));
  else if(mode==='--run' && a && b && c && hookPath) {
    const source=execFileSync('git',['rev-parse','HEAD'],{cwd:repo,encoding:'utf8'}).trim();
    const g=JSON.parse(await readFile(a,'utf8'));validateGo(g,source);
    // Trusted operator-provided W1 adapter to EXISTING host ownership interface.
    const hook=await import(pathToFileURL(resolve(hookPath)).href);
    const result=await runBatch(g,resolve(b),resolve(c),{source,confirmSettlement:hook.confirmSettlement});
    console.log(JSON.stringify(result));process.exitCode=result.status==='BLOCKED'?1:0;
  } else {console.error('Prepare only: --prepare OUT [OWNED_PDF]\nExact batch GO only: --run GO.json PREPARED_INPUTS NEW_EVIDENCE_DIR W1_EXISTING_HOST_HOOK.mjs');process.exitCode=2;}
}
