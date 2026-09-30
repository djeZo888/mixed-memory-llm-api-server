#!/usr/bin/env node
// Future rollback only. No config.yaml/token, history, ledger or snapshot access.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {existsSync,lstatSync,readFileSync,readdirSync,realpathSync,writeFileSync,renameSync,unlinkSync} from 'node:fs';
import {join,resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
if(process.argv.includes('--help')) { console.log('Usage: rollback-profiles.mjs REVIEWED_H016_MODULE PROFILES_ROOT [--dry-run|--apply]\nRequires stopped app/settled task containers and W1 exact MiMo settlement plus explicit ready GLM selection before apply. Default dry-run.'); process.exit(0); }
const [modulePath,rootArg,mode='--dry-run']=process.argv.slice(2);
assert(['--dry-run','--apply'].includes(mode));
assert.equal(createHash('sha256').update(readFileSync(modulePath)).digest('hex'),'045d0ed290a4870182610745a5a51ba471d9797bf5aebffbb3148ca4d000e020');
const {frontierAgentMarkdown,frontierSlotPolicy,DEFAULT_FRONTIER_PROFILE,MIMO_MANAGED_CONTEXTS,seedFrontierAgent}=await import(pathToFileURL(resolve(modulePath)));
const root=resolve(rootArg); assert.equal(realpathSync(root),root);
const directory=p=>{const s=lstatSync(p); assert(s.isDirectory()&&!s.isSymbolicLink()&&s.uid===process.getuid()&&!(s.mode&0o022));};
const read=p=>{const s=lstatSync(p); assert(s.isFile()&&s.uid===process.getuid()&&s.nlink===1&&!(s.mode&0o077));return readFileSync(p);};
directory(root);
const glm=Buffer.from(frontierAgentMarkdown());
const mimos=MIMO_MANAGED_CONTEXTS.map(contextWindow=>Buffer.from(frontierAgentMarkdown({model:'mimo-v2.6-pro-rl',contextWindow,maxOutputTokens:65536})));
const oldPolicy=frontierSlotPolicy({model:'mimo-v2.6-pro-rl'}), newPolicy=frontierSlotPolicy();
const plans=[]; let untouched=0;
for(const entry of readdirSync(root)) {
  const profile=join(root,entry);directory(profile);
  const state=join(profile,'state');if(!existsSync(state))continue;directory(state);
  const agents=join(state,'agents');if(!existsSync(agents))continue;directory(agents);
  const frontier=join(agents,'frontier');if(!existsSync(frontier))continue;directory(frontier);
  assert.deepEqual(readdirSync(frontier),['agent.md'],'extra frontier content preserved; stop');
  const agent=join(frontier,'agent.md'),bytes=read(agent);
  const alreadyGLM=bytes.equals(glm);
  assert(alreadyGLM||mimos.some(m=>m.equals(bytes)),'custom frontier conflict preserved; stop before writes');
  const instructions=join(state,'AGENTS.md'),before=read(instructions),text=before.toString('utf8');
  assert.equal(Buffer.from(text).compare(before),0,'invalid UTF8');
  if(alreadyGLM&&!text.includes(oldPolicy)){untouched++;continue;}
  assert.equal(text.split(oldPolicy).length,2,'managed MiMo paragraph absent/duplicated; preserve and stop');
  plans.push({state,agent,bytes,instructions,before,after:text.replace(oldPolicy,newPolicy),alreadyGLM});
}
// All profiles validated before first write. No credentials/config regeneration.
if(mode==='--apply') for(const p of plans) {
  assert(read(p.agent).equals(p.bytes)&&read(p.instructions).equals(p.before),'profile changed');
  seedFrontierAgent(p.state,DEFAULT_FRONTIER_PROFILE);
  const tmp=join(p.state,`.h016-rollback-${process.pid}.tmp`);
  try { writeFileSync(tmp,p.after,{flag:'wx',mode:0o600});assert(read(p.instructions).equals(p.before));renameSync(tmp,p.instructions); }
  finally { if(existsSync(tmp))unlinkSync(tmp); }
}
console.log(JSON.stringify({mode,exactMiMoToGLM1M:plans.filter(p=>!p.alreadyGLM).length,managedPolicyRepairs:plans.length,alreadyGLM1M:untouched,customContentOverwritten:false,historyOrCredentialsRead:false}));
