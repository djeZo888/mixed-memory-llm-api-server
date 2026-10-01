/** Host-private adapter for A's actual root-carrier challenge. No serialized
 * object can replace A's process-local admission brand. Never releases a hold. */
import {isQualificationTaskAdmission,loadQualificationTaskAdmission,type QualificationTaskAdmission} from '../../../server/src/qualification-task-admission.js';
import {actionFingerprint,freezeKey} from '../../../server/src/dispatch-freeze.js';
import {reviewedAuthorization} from '../authorization.mjs';
import {privateFile,durableFile} from './checkpoint.js';
import {sha256,stableJson,reviewSnapshot} from './projection.js';
import {join} from 'node:path';
export interface CarrierBinding { admissionPath:string; transactionId:string; sessionId:string; ownHold:{key:string;fingerprint:string;action:string;scope:string}; }
export function validateCarrierBinding(config:any):CarrierBinding {
 const binding=config.carrier,review=config.bootstrap?.review;
 if(!binding||stableJson(binding)!==stableJson(review?.carrier)||!/^\/run\/ai-harness-qualification\/[a-z0-9-]{8,128}\/admission.json$/.test(binding.admissionPath)||typeof binding.transactionId!=='string'||!binding.transactionId||typeof binding.sessionId!=='string'||!binding.sessionId)throw Error('exact_root_reviewed_carrier_binding_required');
 const hold=binding.ownHold,action=JSON.parse(hold?.action??'null'),scope=JSON.parse(hold?.scope??'null');
 if(!action||action.node_id!=='ai-harness'||action.service_id!=='harness'||action.action!=='service.stop'||hold.key!==freezeKey(action)||hold.fingerprint!==actionFingerprint(action)||stableJson(scope)!==stableJson(['harness']))throw Error('exact_canonical_owned_harness_STOP_required');
 reviewedAuthorization(review);return reviewSnapshot(binding);
}
/** Independent read-only row check. Even a valid task challenge does not confer
 * authority over a foreign hold, a modified STOP, or unreadable gate state. */
export function carrierRowsHeld(rows:any[],binding:CarrierBinding,serviceId='harness') {
 const service=({'qwen3.8-27b':'qwen-gpu1','qwen3.8-27b-gpu0':'qwen-gpu0'} as Record<string,string>)[serviceId]??serviceId;
 let own=0;for(const row of rows){
  const scope=JSON.parse(String(row.scope)),action=JSON.parse(String(row.action));
  if(!Array.isArray(scope)||scope.some(s=>typeof s!=='string')||!action||typeof action!=='object')throw Error('unreadable_shared_hold');
  if(row.key===binding.ownHold.key){if(++own!==1||row.fingerprint!==binding.ownHold.fingerprint||row.action!==binding.ownHold.action||row.scope!==binding.ownHold.scope||row.acknowledged!==1)throw Error('owned_carrier_STOP_changed');continue;}
  if(scope.includes('harness')||scope.includes(service)||(service==='glm-5.3-flash'&&action.node_id==='ai-vm'&&action.action==='node.reboot'))return true;
 }if(own!==1)throw Error('owned_carrier_STOP_missing');return false;
}
export class CarrierAdmission {
 private latest:any;
 constructor(private admission:QualificationTaskAdmission,private binding:CarrierBinding,private review:any){if(!isQualificationTaskAdmission(admission))throw Error('actual_A_task_admission_brand_required');}
 async verify(sessionId:string,requestId:string,signal?:AbortSignal,directory?:string){
  this.latest=undefined;
  const authority=reviewedAuthorization(this.review);if(Date.now()>=authority.dispatchCutoffAt)throw Error('carrier_dispatch_cutoff');
  const received=await this.admission.verify({sessionId,requestId,lane:'qwen3.8-27b'},signal);
  // Actual received producer fields, never filled from expected IDs.
  if(received.transactionId!==this.binding.transactionId||received.ownHoldKey!==this.binding.ownHold.key||!Number.isFinite(received.observedAtMs)||Date.now()-received.observedAtMs<0||Date.now()-received.observedAtMs>1500||Date.now()>=authority.dispatchCutoffAt||signal?.aborted)throw Error('current_exact_carrier_challenge_required');
  const utf8=JSON.stringify(received);if(directory)await durableFile(join(directory,`carrier-${sha256(requestId)}-${received.challenge}.json`),utf8);
  if(Date.now()>=authority.dispatchCutoffAt||signal?.aborted)throw Error('carrier_dispatch_cutoff_after_capture');this.latest=received;return received;
 }
 held(rows:any[],serviceId:string){try{const at=this.latest?.observedAtMs,now=Date.now();if(!Number.isFinite(at)||now<at||now-at>1500||now>=reviewedAuthorization(this.review).dispatchCutoffAt)return true;return carrierRowsHeld(rows,this.binding,serviceId);}catch{return true;}}
}
export async function carrierForConfig(configPath:string,provided?:QualificationTaskAdmission,signal?:AbortSignal){
 signal?.throwIfAborted();
 const config=JSON.parse((await privateFile(configPath)).toString('utf8')),binding=validateCarrierBinding(config);
 const admission=provided??loadQualificationTaskAdmission(binding.admissionPath);
 const gate=new CarrierAdmission(admission,binding,config.bootstrap.review);
 await gate.verify(binding.sessionId,'carrier-entry',signal);signal?.throwIfAborted();return gate;
}
