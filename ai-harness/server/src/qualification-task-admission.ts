/** Host-only root carrier challenge. Import grants no admission. No public/env
 * activation. The normal freeze DB is unchanged and every foreign hold wins. */
import {readFileSync,lstatSync,realpathSync} from 'node:fs';import {createHmac,randomBytes,timingSafeEqual} from 'node:crypto';import {connect} from 'node:net';import {DatabaseSync} from 'node:sqlite';import {DISPATCH_STATE} from './dispatch-freeze.js';
export interface TaskAdmissionContext {sessionId:string;requestId:string;lane:string}
const brands=new WeakSet<object>();
export class QualificationTaskAdmission {
 private readonly sessions=new Set<string>();private lastVerifiedAt=0;
 private constructor(private readonly packet:any,private readonly key:Buffer) {brands.add(this);}
 static load(path:string){
  if(process.platform!=='linux'||!process.getuid?.()||!/^\/run\/ai-harness-qualification\/[a-z0-9-]{8,128}\/admission.json$/.test(path))throw Error('protected_task_admission_only');
  const s=lstatSync(path);if(s.uid!==0||(s.mode&0o777)!==0o640||!s.isFile()||s.nlink!==1||s.size>8192||realpathSync(path)!==path)throw Error('untrusted_task_admission_packet');
  const p=JSON.parse(readFileSync(path,'utf8'));if(Object.keys(p).sort().join()!=='carrier,dispatchCutoffMs,expiresAtMs,key,lane,maxOwnedSessions,ownHoldKey,schema,sessionId,socketPath,transactionId'||p.schema!=='qualification-task-admission-v1'||p.lane!=='qwen3.8-27b'||p.socketPath!==path.replace('admission.json','admission.sock')||typeof p.key!=='string'||!/^[0-9a-f]{64}$/.test(p.key)||!Number.isSafeInteger(p.dispatchCutoffMs)||!Number.isSafeInteger(p.expiresAtMs)||p.expiresAtMs-p.dispatchCutoffMs<120000||p.maxOwnedSessions!==64)throw Error('invalid_task_admission_scope');
  const socket=lstatSync(p.socketPath);if(socket.uid!==0||!socket.isSocket()||(socket.mode&0o777)!==0o660)throw Error('untrusted_carrier_socket');
  const result=new QualificationTaskAdmission(Object.freeze(p),Buffer.from(p.key,'hex'));result.owner();return result;
 }
 private owner(){const p=this.packet.carrier,base=`/proc/${p.pid}`;const raw=readFileSync(base+'/stat','utf8'),ticks=raw.slice(raw.lastIndexOf(')')+2).split(/\s+/)[19];if(ticks!==p.startTicks||!/^Uid:\s+0\s+0\s/m.test(readFileSync(base+'/status','utf8'))||readFileSync('/proc/sys/kernel/random/boot_id','utf8').trim()!==p.bootId)throw Error('carrier_owner_lost');}
 async registerSession(input:{sessionId:string;role:'parent'|'probe'|'child';parentSessionId?:string},signal?:AbortSignal){
  if(!/^[A-Za-z0-9._:-]{1,128}$/.test(input.sessionId)||!['parent','probe','child'].includes(input.role)||this.sessions.size>=64)throw Error('invalid_owned_session_registration');
  if(input.role!=='parent'&&(!input.parentSessionId||!this.sessions.has(input.parentSessionId)))throw Error('unregistered_parent_session');
  const result=await this.exchange({...input,operation:'register',requestId:'register:'+input.sessionId,lane:this.packet.lane},signal);this.sessions.add(input.sessionId);return result;
 }
 held(alias:string,sessionId?:string):boolean{
  try{if(!brands.has(this)||!['harness','qwen3.8-27b','qwen-gpu1'].includes(alias)||Date.now()>=this.packet.dispatchCutoffMs||Date.now()-this.lastVerifiedAt>1500||(sessionId&&!this.sessions.has(sessionId)&&sessionId!==this.packet.sessionId))return true;this.owner();
   const db=new DatabaseSync(DISPATCH_STATE,{readOnly:true});try{const rows=db.prepare('SELECT key,scope FROM dispatch_holds').all();if(!rows.some(r=>r.key===this.packet.ownHoldKey))return true;return rows.some(r=>r.key!==this.packet.ownHoldKey&&(JSON.parse(String(r.scope)).includes('harness')||JSON.parse(String(r.scope)).includes('qwen-gpu1')));}finally{db.close();}
  }catch{return true;}
 }
 async verify(context:TaskAdmissionContext,signal?:AbortSignal){
  if(context.sessionId!==this.packet.sessionId&&!this.sessions.has(context.sessionId))throw Error('unregistered_owned_task_session');
  const result=await this.exchange({...context,operation:'admit'},signal);this.lastVerifiedAt=Date.now();return result;
 }
 private async exchange(context:TaskAdmissionContext&{operation:'register'|'admit';role?:string;parentSessionId?:string},signal?:AbortSignal){
  if(!brands.has(this)||context.lane!==this.packet.lane||typeof context.requestId!=='string'||!context.requestId||Date.now()>=this.packet.dispatchCutoffMs||signal?.aborted)throw Error('foreign_or_expired_task_admission');this.owner();
  const challenge=randomBytes(32).toString('hex'),body=JSON.stringify({challenge,transactionId:this.packet.transactionId,...context}),mac=createHmac('sha256',this.key).update(body).digest('hex');
  const response=await new Promise<string>((resolve,reject)=>{const socket=connect(this.packet.socketPath);let raw='';const timer=setTimeout(()=>{socket.destroy();reject(Error('carrier_challenge_timeout'));},1500);const stop=()=>socket.destroy(Error('carrier_challenge_cancelled'));signal?.addEventListener('abort',stop,{once:true});const finish=()=>{clearTimeout(timer);signal?.removeEventListener('abort',stop);};socket.once('error',e=>{finish();reject(e);});socket.on('data',b=>{raw+=b.toString('utf8');if(raw.length>8192){socket.destroy(Error('carrier_challenge_bound'));return;}if(raw.endsWith('\n')){finish();socket.end();resolve(raw.trim());}});socket.once('connect',()=>socket.write(JSON.stringify({body,mac})+'\n'));});
  const envelope=JSON.parse(response);if(typeof envelope.body!=='string'||typeof envelope.mac!=='string'||!/^[0-9a-f]{64}$/.test(envelope.mac)||!timingSafeEqual(Buffer.from(envelope.mac,'hex'),createHmac('sha256',this.key).update(envelope.body).digest()))throw Error('carrier_challenge_authentication');const v=JSON.parse(envelope.body);if(v.challenge!==challenge||v.transactionId!==this.packet.transactionId||v.sessionId!==context.sessionId||v.requestId!==context.requestId||v.lane!==context.lane||v.ownerStartTicks!==this.packet.carrier.startTicks||v.operation!==context.operation||v.ownHoldKey!==this.packet.ownHoldKey||v.status!==(context.operation==='register'?'registered':'admit')||Math.abs(Date.now()-v.observedAtMs)>1500||Date.now()>=this.packet.dispatchCutoffMs)throw Error('carrier_challenge_scope');this.owner();return Object.freeze(v);
 }
}
export const loadQualificationTaskAdmission=(path:string)=>QualificationTaskAdmission.load(path);
export const isQualificationTaskAdmission=(value:unknown):value is QualificationTaskAdmission=>!!value&&typeof value==='object'&&brands.has(value);
