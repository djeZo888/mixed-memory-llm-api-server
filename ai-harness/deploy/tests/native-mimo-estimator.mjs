#!/usr/bin/env node
/** Evaluate only the changed estimator source with retained real estimator classes. */
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {stripTypeScriptTypes} from 'node:module';
import {pathToFileURL} from 'node:url';
import {resolve} from 'node:path';
if(process.argv.includes('--help')) {console.log('Usage: native-mimo-estimator.mjs RETAINED_NATIVE_PROBES.mjs');process.exit(0);}
const native=await import(pathToFileURL(resolve(process.argv[2])));
const patch=readFileSync(new URL('../patches/0010-frontier-model-accounting.patch',import.meta.url),'utf8');
const source=patch.split('@@ -0,0 +1,21 @@\n')[1].split('diff --git')[0].split('\n').filter(s=>s.startsWith('+')).map(s=>s.slice(1)).join('\n');
const code=stripTypeScriptTypes(source.replace(/^import .*;\n/gm,''),{mode:'strip'}).replace('export function modelTokenEstimator','function modelTokenEstimator');
const qwenModel={provider:'custom_provider:harness',id:'qwen3.8-27b'};
const originalQwen=native.modelTokenEstimator(qwenModel);
const originalGlm=native.modelTokenEstimator({provider:'custom_provider:frontier',id:'glm-5.3-flash'});
const base=Object.getPrototypeOf(originalGlm.constructor);
const select=new Function('Buffer','BpeTokenEstimator','createDefaultTokenEstimator',code+'\nreturn modelTokenEstimator;')(Buffer,base,()=>originalQwen);
const mimo=select({provider:'custom_provider:frontier',id:'mimo-v2.6-pro-rl'});
assert.equal(mimo.estimateTextTokens('中文🙂'),Buffer.byteLength('中文🙂'));
assert.equal(mimo.estimateMessage({role:'user',content:'fixture'}),Buffer.byteLength(JSON.stringify({role:'user',content:'fixture'}))+256);
assert.equal(mimo,select({provider:'custom_provider:frontier',id:'glm-5.3-flash'}));
assert.equal(select(qwenModel),originalQwen);assert.equal(select({provider:'unrelated',id:'mimo-v2.6-pro-rl'}),originalQwen);
console.log(JSON.stringify({result:'PASS',scope:'Exact changed patch estimator source evaluated with retained native BPE base; no rebuilt/deployed engine claim',networkRequests:0}));
