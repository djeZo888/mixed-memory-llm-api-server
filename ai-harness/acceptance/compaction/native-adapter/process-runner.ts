import { fork, execFile, type ChildProcess } from 'node:child_process';
import { promisify } from 'node:util';
import { readFile } from 'node:fs/promises';
import { join } from 'node:path';
import { reviewedAuthorization } from '../authorization.mjs';
import { privateFile, durableFile } from './checkpoint.js';
import { sha256, stableJson } from './projection.js';
export interface RunnerInput { workerPath:string; workerSha256:string; configPath:string; configSha256:string; hostPrivate:string; review:Parameters<typeof reviewedAuthorization>[0]; operationTimeoutMs?:number }
export interface ApplicationIdentity {pid:number;startTicks:string;bootId:string;source:string}
const exec = promisify(execFile);
export async function observeApplicationIdentity(pid:number):Promise<ApplicationIdentity> {
  if(!Number.isSafeInteger(pid)||pid<1)throw Error('actual_application_pid_required');
  if(process.platform==='linux') {
    const stat=await readFile(`/proc/${pid}/stat`,'utf8'),fields=stat.slice(stat.lastIndexOf(')')+2).split(' ');
    return {pid,startTicks:fields[19]!,bootId:(await readFile('/proc/sys/kernel/random/boot_id','utf8')).trim(),source:'linux-proc'};
  }
  // Actual Mac process identity supports SOURCE IPC regression only. Entry
  // qualification still requires Linux; this cannot qualify native transport.
  if(process.platform==='darwin') {
    const observed=await exec('/bin/ps',['-p',String(pid),'-o','lstart=']);
    if(!observed.stdout.trim())throw Error('owned_process_absent');
    const boot=await exec('/usr/sbin/sysctl',['-n','kern.boottime']);
    return {pid,startTicks:observed.stdout.trim(),bootId:boot.stdout.trim(),source:'darwin-ps-source-only'};
  }
  throw Error('application_process_identity_unavailable');
}
const id = (p:ApplicationIdentity) => `${p.bootId}:${p.pid}:${p.startTicks}`;
export async function bounded<T>(operation:Promise<T>,milliseconds:number,code:string):Promise<T> {
  let timer:ReturnType<typeof setTimeout>|undefined;
  try{return await Promise.race([operation,new Promise<T>((_,reject)=>{timer=setTimeout(()=>reject(Error(code)),Math.max(1,milliseconds));})]);}
  finally{if(timer)clearTimeout(timer);}
}
/** Exact acquired process owner. Failure closes dispatch, never cleanup. */
export class OwnedApplicationRunner {
  private child?:ChildProcess; private identity?:ApplicationIdentity; private sequence=0;
  private pending=new Map<number,{resolve(value:any):void;reject(error:Error):void}>(); private failed=false;
  private exits=new Map<ChildProcess,Promise<{code:number|null;signal:NodeJS.Signals|null}>>();
  constructor(private input:RunnerInput) {
    if(input.operationTimeoutMs!==undefined&&(!Number.isInteger(input.operationTimeoutMs)||input.operationTimeoutMs<1||input.operationTimeoutMs>120000))throw Error('bounded_reviewed_runner_timeout_required');
  }
  identitySnapshot(){if(!this.identity)throw Error('actual_application_identity_absent');return {...this.identity,applicationProcessId:id(this.identity)};}
  private cutoff(cleanup=false){const a=reviewedAuthorization(this.input.review);return cleanup?a.expiresAt:a.dispatchCutoffAt;}
  async start(signal?:AbortSignal) {
    if(signal?.aborted)throw Error('owned_application_start_cancelled');
    if(this.child||this.failed)throw Error('runner_duplicate_or_failed_no_retry');
    const cutoff=this.cutoff();
    if(Date.now()>=cutoff||sha256(await readFile(this.input.workerPath))!==this.input.workerSha256||sha256(await privateFile(this.input.configPath))!==this.input.configSha256)throw Error('reviewed_worker_config_window_required');
    if(signal?.aborted)throw Error('owned_application_start_cancelled');
    const child=fork(this.input.workerPath,[this.input.configPath],{execArgv:[],stdio:['ignore','ignore','ignore','ipc'],env:{PATH:'/usr/bin:/bin',HOME:process.env.HOME,USER:process.env.USER,LOGNAME:process.env.LOGNAME}});
    this.child=child; // Ownership before all awaits.
    this.exits.set(child,new Promise(resolve=>child.once('exit',(code,signal)=>{for(const p of this.pending.values())p.reject(Error('owned_application_exited_no_replay'));this.pending.clear();resolve({code,signal});})));
    let readyResolve!:(v:any)=>void,readyReject!:(e:Error)=>void;
    const ready=new Promise<any>((r,j)=>{readyResolve=r;readyReject=j;});void ready.catch(()=>undefined);
    child.on('message',(message:any)=>{
      if(message?.ready){readyResolve(message);return;}
      const p=this.pending.get(message?.id);if(!p)return;this.pending.delete(message.id);message.error?p.reject(Error('owned_worker_operation_failed_preserved')):p.resolve(message.result);
    });
    child.on('error',()=>{this.failed=true;readyReject(Error('owned_application_transport_failed'));for(const p of this.pending.values())p.reject(Error('owned_application_transport_failed'));this.pending.clear();});
    child.once('exit',()=>readyReject(Error('owned_application_exited_before_ready')));
    try {
      if(!child.pid)throw Error('owned_application_pid_absent');this.identity=await observeApplicationIdentity(child.pid);
      const ack=await bounded(ready,Math.min(this.input.operationTimeoutMs??120000,cutoff-Date.now()),'owned_worker_start_deadline');
      if(ack.protocol!=='h041-owned-application-ipc-v1'||ack.configSha256!==this.input.configSha256)throw Error('actual_worker_ready_config_mismatch');
      if(signal?.aborted)throw Error('owned_application_ready_cancelled');
      await durableFile(join(this.input.hostPrivate,`${child.pid}-${sha256(id(this.identity))}-runner-start.json`),stableJson({...this.identity,source:'owned-application-os-identity',identitySource:this.identity.source,workerSha256:this.input.workerSha256,configSha256:this.input.configSha256,ready:ack}));
    } catch(error){this.failed=true;await this.shutdownAndConfirm().catch(()=>undefined);throw error;}
  }
  async call(method:string,args:any={},signal?:AbortSignal) {
    const cleanup=['close','shutdown'].includes(method);
    if(!this.child||(!cleanup&&this.failed))throw Error('owned_runner_unavailable');
    const cutoff=this.cutoff(cleanup);if(Date.now()>=cutoff)throw Error('owned_runner_dispatch_cutoff');
    const current=++this.sequence,child=this.child;
    return await new Promise<any>((resolve,reject)=>{
      const abandon=()=>{this.pending.delete(current);if(!cleanup)this.failed=true;if(child.connected)child.send({cancel:current},()=>undefined);reject(Error('owned_runner_deadline_no_replay'));};
      const timer=setTimeout(abandon,Math.min(this.input.operationTimeoutMs??120000,cutoff-Date.now()));
      const done=()=>{clearTimeout(timer);signal?.removeEventListener('abort',abandon);};
      this.pending.set(current,{resolve:v=>{done();resolve(v);},reject:e=>{done();reject(e);}});
      signal?.addEventListener('abort',abandon,{once:true});
      if(signal?.aborted){done();abandon();return;}
      child.send({id:current,method,args},error=>{if(error){this.pending.delete(current);done();if(!cleanup)this.failed=true;reject(Error('owned_runner_send_failed'));}});
    });
  }
  async shutdownAndConfirm() {
    const child=this.child;if(!child)throw Error('actual_owned_application_exit_absent');
    const identity=this.identity;
    // Shutdown remains reachable after an operation timeout or transport fault.
    try{await this.call('shutdown');}catch{/* explicit quarantine below */}
    try{return await bounded(this.exits.get(child)!,Math.min(15000,Math.max(1,this.cutoff(true)-Date.now())),'owned_application_exit_timeout');}
    catch(error){
      this.failed=true;
      let exact=false;
      if(child.pid&&identity)exact=id(await observeApplicationIdentity(child.pid).catch(()=>({pid:0,startTicks:'',bootId:'',source:''})))===id(identity);
      if(exact)child.kill('SIGTERM');
      const exit=await bounded(this.exits.get(child)!,2000,'owned_application_quarantined_still_present').catch(()=>null);
      await durableFile(join(this.input.hostPrivate,`runner-${child.pid}-quarantine-${this.sequence}.json`),stableJson({source:'owned-application-failed-settlement',identity,exactOwnedSignal:exact,exit,nativeSettlement:'unconfirmed',automaticReplay:false})).catch(()=>undefined);
      throw error;
    }
  }
  async restart(input:{checkpoint:any;acceptedContinuation?:any;runId:string;actionId:string;windowId:string;observedSettlements:any[]},signal?:AbortSignal) {
    if(signal?.aborted)throw Error('owned_restart_cancelled_before_prepare');
    if(!this.child||!this.identity||this.failed)throw Error('actual_old_application_required');
    const old=this.child,before=this.identity;
    let handoff:any;
    try{handoff=await this.call('prepareRestart',input,signal);}catch(error){if(signal?.aborted){await this.call('close',{runId:input.runId,observedSettlements:input.observedSettlements}).catch(()=>undefined);await this.shutdownAndConfirm().catch(()=>undefined);}throw error;}
    if(typeof handoff?.statePath!=='string'||!handoff.stateSha256||sha256(await privateFile(handoff.statePath))!==handoff.stateSha256)throw Error('owned_persisted_restart_handoff_required');
    const closed=await this.call('close',{runId:input.runId,observedSettlements:input.observedSettlements});
    if(closed?.settlement?.state!=='released'||typeof closed.closeReceiptUtf8!=='string'||sha256(closed.closeReceiptUtf8)!==closed.closeReceiptSha256)throw Error('actual_owned_close_required_before_process_restart');
    const exited=await this.shutdownAndConfirm();
    if(exited.code!==0||exited.signal!==null)throw Error('old_application_exit_unconfirmed_no_restart');
    this.child=undefined;this.identity=undefined;if(signal?.aborted)throw Error('owned_restart_cancelled_after_old_exit');await this.start(signal);
    const after=this.identity!;if(id(before)===id(after))throw Error('application_process_identity_not_replaced');
    if(signal?.aborted){await this.shutdownAndConfirm();throw Error('owned_restart_cancelled_before_adoption');}
    const resumed=await this.call('adoptRestart',{...handoff,checkpoint:input.checkpoint,acceptedContinuation:input.acceptedContinuation,closed,beforeProcess:before,afterProcess:after,oldExit:exited,runId:input.runId,actionId:input.actionId,windowId:input.windowId},signal);
    if(resumed.nativeThreadId!==input.checkpoint.nativeThreadId||resumed.afterStateUtf8!==input.checkpoint.stateUtf8||resumed.replayedActionIds?.length!==0)throw Error('accepted_parent_changed_or_replayed');
    const receiptUtf8=stableJson({source:'owned-application-process-restart',runId:input.runId,actionId:input.actionId,windowId:input.windowId,before,after,oldExit:exited,oldCloseReceiptUtf8:closed.closeReceiptUtf8,stateSha256:handoff.stateSha256,nativeThreadId:resumed.nativeThreadId,checkpointStateSha256:input.checkpoint.stateSha256});
    await durableFile(join(this.input.hostPrivate,`${after.pid}-${sha256(id(after))}-cold-restart.json`),receiptUtf8);
    return {...resumed,beforeProcessId:id(before),afterProcessId:id(after),processRestartReceiptUtf8:receiptUtf8,processRestartReceiptSha256:sha256(receiptUtf8)};
  }
}
