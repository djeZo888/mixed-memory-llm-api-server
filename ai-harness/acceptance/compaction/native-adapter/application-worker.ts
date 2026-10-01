/** Actual private Node application process. No network/launch occurs until an
 * owned IPC method loads the reviewed entry. Never a public HTTP dispatcher. */
import { privateFile } from './checkpoint.js';
import { sha256 } from './projection.js';
import { loadReviewedLocalEntry } from './entry.js';
import { qualifyRestart } from './restart.js';
const configPath=process.argv[2];
if(!configPath||!process.send||!process.connected)throw Error('owned_private_ipc_worker_only');
const configBytes=await privateFile(configPath),config=JSON.parse(configBytes.toString('utf8'));
let adapter:Awaited<ReturnType<typeof loadReviewedLocalEntry>>|undefined,closed=false,shuttingDown=false;
const operations=new Map<number,{abort:AbortController;done:Promise<void>}>();
const allowed=new Set(['qualification','runtime','open','append','originals','compact','probe','continue','childContext','freshBriefControl','prepareRestart','captureAcceptedArtifacts','adoptRestart','close','shutdown']);
process.on('message',(message:any)=>{
  if(Number.isSafeInteger(message?.cancel)){operations.get(message.cancel)?.abort.abort();return;}
  if(!Number.isSafeInteger(message?.id)||!allowed.has(message.method)||shuttingDown)return;
  const abort=new AbortController(),send=(payload:any)=>new Promise<void>(resolve=>process.send!({id:message.id,...payload},()=>resolve()));
  const operation=(async()=>{
    try {
      if(message.method==='shutdown') {
        shuttingDown=true;for(const op of operations.values())op.abort.abort();
        // Shutdown cannot manufacture an exit if owned close never confirmed.
        await Promise.all([...operations.values()].map(op=>op.done));
        if(adapter&&!closed){await adapter.close({runId:message.args?.runId,observedSettlements:message.args?.observedSettlements??[]});closed=true;}
        await send({result:{shutdownAcknowledged:true}});process.disconnect();process.exit(0);
      }
      if(message.method==='close'){for(const [id,op]of operations)if(id!==message.id)op.abort.abort();await Promise.all([...operations.entries()].filter(([id])=>id!==message.id).map(([,op])=>op.done));}
      if(message.method==='adoptRestart') {
        if(adapter)throw Error('restart_worker_not_fresh');
        const ticket=await qualifyRestart(message.args,config);abort.signal.throwIfAborted();adapter=await loadReviewedLocalEntry(configPath,ticket,abort.signal);
        const result=await adapter.adoptRestart({ticket,signal:abort.signal});await send({result});return;
      }
      if(!adapter)adapter=await loadReviewedLocalEntry(configPath);
      if(message.method==='qualification'){await send({result:{enabled:adapter.enabled,capabilities:adapter.capabilities,profile:config.profile,qualificationSha256:config.qualificationSha256}});return;}
      const method=(adapter as any)[message.method];if(typeof method!=='function')throw Error('unsupported_owned_worker_method');
      const result=await method({...message.args,signal:abort.signal});if(message.method==='close')closed=true;
      await send({result});
    } catch {await send({error:'owned_operation_failed_output_preserved_no_replay'});}
  })();
  if(message.method!=='shutdown')operations.set(message.id,{abort,done:operation});
  void operation.finally(()=>operations.delete(message.id));
});
process.send({ready:true,protocol:'h041-owned-application-ipc-v1',configSha256:sha256(configBytes)});
