/** Real normal application subprocess. No temporary composition or history replay. */
import {startNormalProduct,kernelProcessReceipt} from './normal-product.js';
import {privateFile,durableFile} from './checkpoint.js';
import {sha256,stableJson} from './projection.js';
import {readFile} from 'node:fs/promises';import {join} from 'node:path';import {fileURLToPath} from 'node:url';
const path=process.argv[2];if(!path||!process.send)throw Error('owned_normal_private_ipc_only');
const configBytes=await privateFile(path),config=JSON.parse(configBytes.toString('utf8'));
const allowedEnvironment=new Set(['AI_HARNESS_DATA_DIR','AI_HARNESS_ENGINE_LAUNCHER','AI_HARNESS_INFERENCE_KEY_FILE','AI_HARNESS_NODE_CONTROL_KEY_FILE','AI_HARNESS_BROWSER_APPROVAL_KEY_FILE','AI_HARNESS_ALLOWED_ORIGINS','AI_HARNESS_WEB_DIST','AI_HARNESS_PORT','AI_HARNESS_GATEWAY_PORT','AI_HARNESS_GATEWAY_URL']);
if(!config.normalEnvironment||config.normalEnvironment.AI_HARNESS_DATA_DIR!==config.dataDir||config.normalEnvironment.AI_HARNESS_GATEWAY_PORT!=='8081')throw Error('root_frozen_normal_environment_required');for(const [key,value]of Object.entries(config.normalEnvironment)){if(!allowedEnvironment.has(key)||typeof value!=='string'||value.includes('\0'))throw Error('unreviewed_normal_environment_input');process.env[key]=value;}
let product:Awaited<ReturnType<typeof startNormalProduct>>|undefined,closed=false,stopping=false;
const operations=new Map<number,{abort:AbortController;done:Promise<void>}>();
const pair=(key:string,value:any)=>{const text=stableJson(value);return {[key+'Utf8']:text,[key+'Sha256']:sha256(text)};};
const allowed=new Set(['readyReceipt','baseline','settleRun','closeReceipt','recoveryRows','reopenBaseline','close','shutdown']);
process.on('message',(message:any)=>{
 if(Number.isSafeInteger(message?.cancel)){operations.get(message.cancel)?.abort.abort();return;}
 if(!Number.isSafeInteger(message?.id)||!allowed.has(message.method)||stopping)return;
 const abort=new AbortController(),send=(payload:any)=>new Promise<void>(resolve=>process.send!({id:message.id,...payload},()=>resolve()));
 const work=(async()=>{try{
  if(message.method==='shutdown'||message.method==='close'){stopping=true;for(const op of operations.values())op.abort.abort();await Promise.all([...operations.values()].map(op=>op.done));if(product&&!closed){await product.application.close();closed=true;}await send({result:{applicationClosed:closed}});if(message.method==='shutdown'){process.disconnect();process.exit(0);}return;}
  if(!product)product=await startNormalProduct(path);
  const {producer,application}=product,sessionId=config.sessionId;
  if(message.method==='readyReceipt'){const kernel=await kernelProcessReceipt();await send({result:{source:'normal-product-process-ready',dataDir:config.dataDir,configSha256:sha256(configBytes),workerSha256:sha256(await readFile(fileURLToPath(import.meta.url))),...pair('kernel',kernel)}});return;}
  if(message.method==='reopenBaseline'){producer.active(abort.signal);await producer.reopenBaseline(message.args.baseline);producer.active(abort.signal);await send({result:{reopened:true}});return;}
  if(message.method==='baseline'){await send({result:await producer.settled(sessionId,abort.signal)});return;}
  if(message.method==='settleRun'){await send({result:await producer.settleRun(sessionId,message.args.runId,abort.signal)});return;}
  if(message.method==='closeReceipt'){await send({result:await producer.closeReceipt(sessionId)});return;}
  if(message.method==='recoveryRows'){const id=message.args.checkpointId,checkpoint=application.store.checkpoints.status(sessionId).find((r:any)=>r.id===id);if(!checkpoint)throw Error('exact_normal_checkpoint_missing');const rows=application.store.db.prepare('SELECT body FROM h041_checkpoint_transitions WHERE session_id=? AND run_id=?').all(sessionId,checkpoint.runId);await send({result:{...pair('checkpoint',checkpoint),transitionRows:rows.map((r:any)=>String(r.body)),...pair('failedRun',application.store.runs(sessionId).find((r:any)=>r.id===checkpoint.runId))}});return;}
 }catch{await send({error:'owned_normal_operation_failed_preserved_no_replay'});}})();
 if(!['shutdown','close'].includes(message.method))operations.set(message.id,{abort,done:work});void work.finally(()=>operations.delete(message.id));
});
process.send({ready:true,protocol:'h041-owned-application-ipc-v1',configSha256:sha256(configBytes)});
