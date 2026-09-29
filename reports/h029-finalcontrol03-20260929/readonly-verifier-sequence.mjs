import { readFileSync, readlinkSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { createHash, randomUUID } from 'node:crypto';
import { pathToFileURL } from 'node:url';
const emit=value=>process.stdout.write(JSON.stringify({time:new Date().toISOString(),...value})+'\n');
const cutoff=Date.parse('2026-09-29T03:07:20Z');
if(Date.now()>=cutoff)throw Error('task_cutoff');
const timer=setTimeout(()=>{emit({kind:'terminal',outcome:'stop',code:'task_cutoff',generationRequests:0});process.exit(2);},cutoff-Date.now());
const pid=Number(execFileSync('systemctl',['--user','show','ai-harness.service','-p','MainPID','--value']).toString().trim());
const cwd=readlinkSync(`/proc/${pid}/cwd`);
const env=Object.fromEntries(readFileSync(`/proc/${pid}/environ`,'utf8').split('\0').filter(x=>x.includes('=')).map(x=>[x.slice(0,x.indexOf('=')),x.slice(x.indexOf('=')+1)]));
const argv=readFileSync(`/proc/${pid}/cmdline`,'utf8').split('\0');
if(!cwd.includes('/h029-accept02-2662bd08e65c3fca5ce399761f4e672fb5d8f824/'))throw Error('current_release_mismatch');
const {createProductionQwenVerifier,loadQwenReceipt,boundedControlGet}=await import(pathToFileURL(cwd+'/dist/codex-production.js').href);
const {QWEN_ADMISSION_REASONS,QWEN_CONTROL_ERROR_CODES,admissionTransport}=await import(pathToFileURL(cwd+'/dist/codex-admission.js').href);
const receipt=await loadQwenReceipt(argv[2]);
const credentials={controlKey:readFileSync(env.AI_HARNESS_NODE_CONTROL_KEY_FILE,'utf8').trim(),inferenceKey:readFileSync(env.AI_HARNESS_INFERENCE_KEY_FILE,'utf8').trim()};
const requestId=randomUUID();const reasons=new Set(QWEN_ADMISSION_REASONS);
const hashes=Object.fromEntries(['codex-production.js','codex-admission.js','codex-qwen.js'].map(name=>[name,createHash('sha256').update(readFileSync(cwd+'/dist/'+name)).digest('hex')]));
const qualify=async(lane,phase,bracket)=>{
  let ordinal=0;
  const get=async(url,key)=>{
    const started=performance.now();const step=['control_before','node_before','native','control_after','node_after'][ordinal++];
    try{
      const value=await boundedControlGet(url,key);
      emit({kind:'getter',requestId,lane,phase,bracket,step,outcome:'pass',httpStatus:200,...(QWEN_CONTROL_ERROR_CODES.has(value?.failure_code)?{controlFailureCode:value.failure_code}:{}),elapsedMs:Math.round(performance.now()-started)});return value;
    }catch(error){emit({kind:'getter',requestId,lane,phase,bracket,step,outcome:'reject',transport:admissionTransport(error),elapsedMs:Math.round(performance.now()-started)});throw error;}
  };
  const verify=createProductionQwenVerifier(receipt,credentials,get,Date.now,event=>emit({kind:'verifier',bracket,...event,elapsedMs:Math.round(event.elapsedMs)}));
  try{await verify(lane,{requestId,phase});emit({kind:'qualification',requestId,lane,phase,bracket,outcome:'pass'});return true;}
  catch(error){emit({kind:'qualification',requestId,lane,phase,bracket,outcome:'reject',reason:reasons.has(error.reason)?error.reason:'unexpected',transport:admissionTransport(error)});return false;}
};
emit({kind:'start',requestId,origin:'ai-harness',mode:'read_only_diagnostic_no_acceptance',sourceRoot:cwd,distSha256:hashes,receiptPath:argv[2],receiptSha256:createHash('sha256').update(readFileSync(argv[2])).digest('hex'),sequence:'parallel_both_admission_then_qwen0_count_verifier_before_and_after_brackets',tokenizerExercised:false,generationRequests:0,tokenizeRequests:0});
const admitted=await Promise.all(['qwen3.8-27b-gpu0','qwen3.8-27b'].map(lane=>qualify(lane,'admission','admission')));
const first=admitted.every(Boolean)?await qualify('qwen3.8-27b-gpu0','count','before_tokenization_not_exercised'):null;
const second=first===true?await qualify('qwen3.8-27b-gpu0','count','after_tokenization_not_exercised'):null;
emit({kind:'complete',requestId,admitted,countVerifierFirst:first,countVerifierSecond:second,tokenizerExercised:false,generationRequests:0,tokenizeRequests:0,retries:0});
clearTimeout(timer);
