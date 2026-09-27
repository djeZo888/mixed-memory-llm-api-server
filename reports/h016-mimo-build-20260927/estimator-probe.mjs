#!/usr/bin/env node
/** Actual-image compiled estimator probe and reachable release-chunk lineage; offline. */
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFileSync,existsSync} from 'node:fs';
import {dirname,resolve,relative} from 'node:path';
if(process.argv.includes('--help')){console.log('Run in H016 candidate image with node estimator-probe.mjs');process.exit(0);}
const n=await import('/opt/minimax/native-probes.mjs');
const model={provider:'custom_provider:frontier',id:'mimo-v2.6-pro-rl'};
const estimator=n.modelTokenEstimator(model),qwen=n.modelTokenEstimator({...model,id:'qwen3.8-27b'});
assert.notEqual(estimator,qwen);
assert.equal(estimator.estimateTextTokens('中文'),6);
assert.equal(n.modelTokenEstimator({...model,id:'glm-5.3-flash'}),estimator);
assert.equal(n.modelTokenEstimator({...model,provider:'other'}),qwen);
const visited=new Set(),hits=[];
function visit(p){
 if(visited.has(p))return;visited.add(p);const text=readFileSync(p,'utf8');
 if(text.includes('mimo-v2.6-pro-rl')){
  const pos=text.indexOf('mimo-v2.6-pro-rl');
  hits.push({path:p,sha256:createHash('sha256').update(text).digest('hex'),selectorSnippet:text.slice(Math.max(0,pos-200),pos+200)});
 }
 for(const match of text.matchAll(/(?:from\s*|import\s*\(\s*|import\s*)["'](\.[^"']+\.js)["']/g)){
  const target=resolve(dirname(p),match[1]);if(target.startsWith('/opt/minimax/')&&existsSync(target))visit(target);
 }
}
visit('/opt/minimax/cli.js');assert(hits.length>0,'new estimator not reachable from packaged cli');
assert(hits.some(x=>x.selectorSnippet.includes('glm-5.3-flash')&&x.selectorSnippet.includes('utf8')));
const meta=JSON.parse(readFileSync('/opt/minimax/native-probes.mjs.metafile.json','utf8'));
const input='packages/local-runtime-v2/src/service/model-system/resolution/model-token-estimator.ts';assert(meta.inputs[input]);
console.log(JSON.stringify({result:'PASS',probeSourceRevision:n.probeSourceRevision,packagedSourceRevision:readFileSync('/opt/minimax/patched-source-revision.txt','utf8').trim(),estimatorSourceInput:input,probeSourceBytes:meta.inputs[input].bytes,expectedSourceSha256:'649b21e84263c278c1a43d8cc17ab19fdbf08a5a4b95c666d9a914dd81abea68',mimoAndGlmUseSameUtf8Estimator:true,otherProviderUsesOriginalEstimator:true,utf8ExampleTokens:6,reachableJsFiles:visited.size,compiledSelectorHits:hits,cliSha256:createHash('sha256').update(readFileSync('/opt/minimax/cli.js')).digest('hex'),probeSha256:createHash('sha256').update(readFileSync('/opt/minimax/native-probes.mjs')).digest('hex')},null,2));
