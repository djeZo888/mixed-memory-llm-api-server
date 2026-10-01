// SOURCE-only IPC peer. No Codex/native/container/provider operation exists.
import {readFile,writeFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
const path=process.argv[2],bytes=await readFile(path),config=JSON.parse(bytes),sha=b=>createHash('sha256').update(b).digest('hex');
process.on('message',async m=>{
 if(m.cancel)return;
 if(m.method==='stall')return;
 if(m.method==='shutdown'){await writeFile(config.marker,'actual owned SOURCE worker shutdown',{mode:0o600});process.send({id:m.id,result:{ack:true}},()=>{process.disconnect();process.exit(0);});return;}
 if(m.method==='prepareRestart'){const statePath=config.handoff,state='SOURCE-only handoff';await writeFile(statePath,state,{mode:0o600});process.send({id:m.id,result:{statePath,stateSha256:sha(state)}});return;}
 if(m.method==='close'){const closeReceiptUtf8='{"source":"SYNTHETIC_ONLY_CLOSE"}';process.send({id:m.id,result:{settlement:{state:'released'},closeReceiptUtf8,closeReceiptSha256:sha(closeReceiptUtf8)}});return;}
 if(m.method==='adoptRestart'){process.send({id:m.id,result:{nativeThreadId:m.args.checkpoint.nativeThreadId,afterStateUtf8:m.args.checkpoint.stateUtf8,replayedActionIds:[],observedSourcePid:process.pid}});return;}
 process.send({id:m.id,result:{source:'SYNTHETIC_ONLY',pid:process.pid,value:m.args.value}});
});
process.send({ready:true,protocol:'h041-owned-application-ipc-v1',configSha256:sha(bytes)});
