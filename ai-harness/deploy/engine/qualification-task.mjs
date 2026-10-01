/** Fixed qualification entry, no action on import and no public authority. */
import {readFile,lstat,realpath,writeFile} from 'node:fs/promises';import {resolve} from 'node:path';import {pathToFileURL,fileURLToPath} from 'node:url';import {createHash} from 'node:crypto';
export async function runCarrierTask(configPath,admissionPath){
 if(process.platform!=='linux'||!process.getuid?.()||process.env.NODE_OPTIONS||process.env.NODE_PATH)throw Error('isolated_owned_linux_task_only');
 const s=await lstat(configPath);if(!s.isFile()||s.nlink!==1||(s.mode&0o777)!==0o600||s.uid!==process.getuid()||await realpath(configPath)!==configPath||s.size>1024*1024)throw Error('protected_task_config');const raw=await readFile(configPath),config=JSON.parse(raw);
 // Guardian READY must precede the first imported executable acceptance graph.
 const until=Date.now()+5000;let ready=false;
 while(Date.now()<until){try{const f=await lstat(config.guardianReady);if(f.uid===0&&f.isFile()&&f.nlink===1&&(f.mode&0o777)===0o600){ready=true;break;}}catch{}await new Promise(r=>setTimeout(r,20));}if(!ready)throw Error('guardian_not_ready_no_dispatch');
 for(const [path,sha]of Object.entries(config.executedHashes)){if(await realpath(path)!==path||createHash('sha256').update(await readFile(path)).digest('hex')!==sha)throw Error('task_executed_source_changed');}
 const admissionApi=await import(pathToFileURL(config.admissionModule).href),admission=admissionApi.loadQualificationTaskAdmission(admissionPath);
 await admission.verify({sessionId:config.sessionId,requestId:'task-bootstrap',lane:'qwen3.8-27b'});
 const entry=await import(pathToFileURL(config.entryModule).href);
 // E must explicitly consume the genuine object in its qualified bootstrap;
 // absence is an integration failure, never an ignored option or boolean grant.
 if(typeof entry.loadReviewedCarrierEntry!=='function')throw Error('carrier_aware_qualified_E_entry_required');
 const adapter=await entry.loadReviewedCarrierEntry(config.entryConfig,admission),controller=await import(pathToFileURL(config.controllerModule).href);
 const packet=JSON.parse(await readFile(config.controllerPacket,'utf8'));const sinkRoot=config.sinkDirectory,info=await lstat(sinkRoot);if(await realpath(sinkRoot)!==sinkRoot||info.uid!==process.getuid()||(info.mode&0o777)!==0o700||!info.isDirectory())throw Error('private_sink_required');
 const put=async(name,value)=>{if(!/^[A-Za-z0-9._-]{1,128}$/.test(name))throw Error('private_sink_name');const raw=JSON.stringify(value);if(Buffer.byteLength(raw)>64*1024*1024)throw Error('private_sink_bound');await writeFile(sinkRoot+'/'+name+'.json',raw,{mode:0o600,flag:'wx'});};const sink={private:(name,value)=>put('private-'+name,value),record:value=>put('evidence-'+crypto.randomUUID(),value)};let closed=false;
 const stop=async()=>{if(!closed){closed=true;await adapter.close?.();}};process.once('SIGTERM',()=>void stop().catch(()=>{process.exitCode=1;}));process.once('SIGINT',()=>void stop().catch(()=>{process.exitCode=1;}));
 try{const result=await controller.runAcceptance({packet,adapter,sink});if(result.status!=='PASS')throw Error('actual_manual_acceptance_failed');return result;}finally{await stop();}
}
if(process.argv[1]&&resolve(process.argv[1])===fileURLToPath(import.meta.url)){if(process.argv.length!==4)throw Error('fixed_carrier_arguments');runCarrierTask(process.argv[2],process.argv[3]).catch(()=>{process.stderr.write('Owned qualification task failed; no replay.\n');process.exitCode=1;});}
