import assert from 'node:assert/strict';
import {mkdtempSync,mkdirSync,writeFileSync,readFileSync,realpathSync} from 'node:fs';
import {resolve,join} from 'node:path';
import {spawnSync} from 'node:child_process';
import {frontierAgentMarkdown,frontierSlotPolicy} from '../../ai-harness/deploy/engine/configure-profile.mjs';
const helper=resolve('reports/h016-activation-prep-20260927/rollback-profiles.mjs');
const module=resolve('ai-harness/deploy/engine/configure-profile.mjs');
const root=realpathSync(mkdtempSync(resolve('../private/rollback-fixture-')));
const create=(id,context)=>{const state=join(root,id,'state');mkdirSync(join(state,'agents/frontier'),{recursive:true,mode:0o700});const spec={model:'mimo-v2.6-pro-rl',contextWindow:context,maxOutputTokens:65536};writeFileSync(join(state,'agents/frontier/agent.md'),frontierAgentMarkdown(spec),{mode:0o600});writeFileSync(join(state,'AGENTS.md'),'user prefix\n'+frontierSlotPolicy(spec)+'user suffix\n',{mode:0o600});writeFileSync(join(state,'history.txt'),'retained history',{mode:0o600});return state;};
const a=create('a',131072),b=create('b',1048576);
const run=mode=>spawnSync(process.execPath,[helper,module,root,mode],{encoding:'utf8'});
let r=run('--dry-run');assert.equal(r.status,0,r.stderr);assert.equal(JSON.parse(r.stdout).exactMiMoToGLM1M,2);assert(readFileSync(join(a,'agents/frontier/agent.md'),'utf8').includes('mimo-v2.6'));
r=run('--apply');assert.equal(r.status,0,r.stderr);
for(const state of [a,b]){assert.equal(readFileSync(join(state,'agents/frontier/agent.md'),'utf8'),frontierAgentMarkdown());assert.equal(readFileSync(join(state,'AGENTS.md'),'utf8'),'user prefix\n'+frontierSlotPolicy()+'user suffix\n');assert.equal(readFileSync(join(state,'history.txt'),'utf8'),'retained history');}
assert.equal(run('--apply').status,0);
const c=create('c',131072),d=create('d',131072);writeFileSync(join(d,'agents/frontier/agent.md'),'custom text',{mode:0o600});const before=readFileSync(join(c,'agents/frontier/agent.md'));r=run('--apply');assert.notEqual(r.status,0);assert(readFileSync(join(c,'agents/frontier/agent.md')).equals(before));assert.equal(readFileSync(join(d,'agents/frontier/agent.md'),'utf8'),'custom text');
console.log('PASS two exact tuples, dry-run without writes, GLM1M output65536, managed paragraph only, custom instructions/history preserved, repeat apply, all-profile conflict before writes. Isolated local fixtures only.');
