import {spawn} from 'node:child_process';
export async function confirmSettlement(query) {
 if (query.exactSource !== '5f95693e8c83bd40ca167b9b8fe2e1520ce51634' || query.pilotId !== 'H021-ACCEPT04') throw Error('Settlement source/pilot mismatch');
 return new Promise((resolve,reject)=>{
  const p=spawn('ssh',['-o','BatchMode=yes','-o','ConnectTimeout=5','ai-harness','python3 /home/user/.cache/h021-pilot03-preview/settlement-readback.py'],{stdio:['pipe','pipe','pipe']});let output='',bytes=0;
  const timer=setTimeout(()=>{p.kill();reject(Error('Host settlement readback timed out'));},15000);
  p.stdout.on('data',b=>{bytes+=b.length;if(bytes>1048576){p.kill();reject(Error('Host receipt exceeded bound'));}else output+=b;});p.stderr.resume();
  p.on('error',e=>{clearTimeout(timer);reject(e);});p.on('close',code=>{clearTimeout(timer);if(code!==0)return reject(Error('Host settlement unconfirmed'));try{const result=JSON.parse(output);if(result.sessionId!==query.sessionId||result.runId!==query.runId||result.evidence?.binding?.exactSource!==query.exactSource||result.evidence?.binding?.pilotId!==query.pilotId||typeof result.settled!=='boolean')throw Error('Receipt binding mismatch');resolve(result);}catch{reject(Error('Invalid host receipt'));}});p.stdin.end(JSON.stringify(query));
 });
}
