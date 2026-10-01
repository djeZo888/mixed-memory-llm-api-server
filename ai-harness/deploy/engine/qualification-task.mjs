/** Fixed qualification entry; no action on import/public activation. */
import {readFile,lstat,realpath,writeFile} from 'node:fs/promises';import {resolve} from 'node:path';import {pathToFileURL,fileURLToPath} from 'node:url';import {createHash,randomUUID} from 'node:crypto';
/** Source fixture seam: ownership is joined for EVERY failure after acquisition. */
export async function withOwnedQualification(acquire,work,signal){
 let adapter,result,workError,cleanupError;
 try{signal.throwIfAborted();adapter=await acquire(signal);if(typeof adapter.close!=='function')throw Error('owned_adapter_close_required');const original=adapter.close.bind(adapter);let closing;adapter.close=(...args)=>closing??=(async()=>original(...args))();signal.throwIfAborted();result=await work(adapter,signal);}catch(error){workError=error;}
 finally{if(adapter){try{await adapter.close({});}catch(error){cleanupError=error;}}}
 if(workError&&cleanupError)throw new AggregateError([workError,cleanupError],'qualification_work_and_owned_cleanup_failed');if(workError)throw workError;if(cleanupError)throw cleanupError;return result;
}
export async function runCarrierTask(configPath,admissionPath){
 const abort=new AbortController(),stop=()=>abort.abort();process.once('SIGTERM',stop);process.once('SIGINT',stop);
 try{
 if(process.platform!=='linux'||!process.getuid?.()||process.env.NODE_OPTIONS||process.env.NODE_PATH)throw Error('isolated_owned_linux_task_only');
 const s=await lstat(configPath);if(!s.isFile()||s.nlink!==1||(s.mode&0o777)!==0o600||s.uid!==process.getuid()||await realpath(configPath)!==configPath||s.size>1024*1024)throw Error('protected_task_config');const config=JSON.parse(await readFile(configPath));
 const until=performance.now()+5000;let ready=false;
 while(performance.now()<until){abort.signal.throwIfAborted();try{const f=await lstat(config.guardianReady);if(f.uid===0&&f.isFile()&&f.nlink===1&&(f.mode&0o777)===0o600){ready=true;break;}}catch{}await new Promise(r=>setTimeout(r,20));}if(!ready)throw Error('guardian_task_registration_not_ready');
 for(const [path,sha]of Object.entries(config.executedHashes)){if(await realpath(path)!==path||createHash('sha256').update(await readFile(path)).digest('hex')!==sha)throw Error('task_executed_source_changed');}
 const admissionApi=await import(pathToFileURL(config.admissionModule).href),admission=admissionApi.loadQualificationTaskAdmission(admissionPath);await admission.verify({sessionId:config.sessionId,requestId:'task-bootstrap',lane:'qwen3.8-27b'},abort.signal);
 const entry=await import(pathToFileURL(config.entryModule).href);if(typeof entry.loadReviewedCarrierEntry!=='function')throw Error('carrier_aware_qualified_E_entry_required');
 return await withOwnedQualification(signal=>entry.loadReviewedCarrierEntry(config.entryConfig,admission,signal),async(adapter,signal)=>{
  const controller=await import(pathToFileURL(config.controllerModule).href),translator=await import(pathToFileURL(config.translatorModule).href);if(typeof translator.translateResponses!=='function')throw Error('actual_pinned_translator_required');
  const packet=JSON.parse(await readFile(config.controllerPacket,'utf8'));const root=config.sinkDirectory,info=await lstat(root);if(await realpath(root)!==root||info.uid!==process.getuid()||(info.mode&0o777)!==0o700||!info.isDirectory())throw Error('private_sink_required');
  const put=async(name,value)=>{if(!/^[A-Za-z0-9._-]{1,128}$/.test(name))throw Error('private_sink_name');const raw=JSON.stringify(value);if(Buffer.byteLength(raw)>64*1024*1024)throw Error('private_sink_bound');await writeFile(root+'/'+name+'.json',raw,{mode:0o600,flag:'wx'});};const sink={private:(name,value)=>put('private-'+name,value),record:value=>put('evidence-'+randomUUID(),value)};
  const result=await controller.runAcceptance({packet,adapter,qualification:'native',signal,normalizeResponses:translator.translateResponses,sink});
  if(config.phase==='stage'?result.observedStatus!=='PASS'||result.actionCount!==9:config.phase!=='full'||result.status!=='PASS'||result.actionCount!==39)throw Error('actual_scoped_manual_acceptance_failed');return result;
 },abort.signal);
 }finally{process.removeListener('SIGTERM',stop);process.removeListener('SIGINT',stop);}
}
if(process.argv[1]&&resolve(process.argv[1])===fileURLToPath(import.meta.url)){if(process.argv.length!==4)throw Error('fixed_carrier_arguments');runCarrierTask(process.argv[2],process.argv[3]).catch(()=>{process.stderr.write('Owned qualification task failed; no replay.\n');process.exitCode=1;});}
