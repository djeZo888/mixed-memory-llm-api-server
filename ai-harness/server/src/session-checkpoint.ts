/** Recovery journal, not a native rollback transaction. Original rows/versions are never overwritten. */
import { randomUUID, createHash, createHmac, randomBytes, timingSafeEqual } from "node:crypto";
import {lstatSync,readFileSync,writeFileSync,realpathSync} from "node:fs";
import {dirname,sep} from "node:path";
import {validateCodexObservation,type CodexNativeObservation} from "./codex-observation.js";
import {codexReceiptProvenance,codexReceiptValidation,getCodexReceiptUtf8} from "./codex-receipts.js";
import {canonicalJson} from "./codex-canonical.js";
import type {CodexPolicyOwner} from "./codex-probe.js";
import type { Store } from "./store.js";
import { requireId } from "./errors.js";
export interface SessionCheckpointRecord {
  id: string; sessionId: string; runId: string; kind: string; nativeThreadId: string | null;
  acceptedVersionId: string | null; references: { id: string; sha256: string | null }[];
  acceptedStateSha256: string | null; originalInventory: {through:number;count:number;sha256:string};
  nativeState: import("./contracts.js").NativeEngineState;
  preparedAt: string; status: "prepared" | "replacement_observed" | "settled" | "recovery_required" | "recovered";
  compactions: { id: string; status: "start" | "completed" | "failed" }[];
  outcome?: "completed" | "cancelled" | "failed" | "process_restart";
}
export interface SessionRestartOwnershipProof { readonly sessionId:string;readonly runId:string;readonly checkpointId:string;readonly threadId:string;readonly purpose?:"accepted-continuation"|"settled-compaction" }
export interface FreshParentRecoveryEvidence {launch:CodexNativeObservation;thread:CodexNativeObservation;settlement:CodexNativeObservation;gateway:CodexNativeObservation}
const restartProofs=new WeakMap<SessionRestartOwnershipProof,{store:Store;snapshot:string}>();
function evidenceKey(store:Store,create=false) {
  const path=store.databasePath+".h041-native-evidence.key",directory=dirname(path),dir=lstatSync(directory);
  if(realpathSync(directory)!==directory||!dir.isDirectory()||dir.uid!==process.getuid?.()||(dir.mode&0o077)!==0)throw Error("Native evidence requires protected durable Store");
  if(create)try{writeFileSync(path,randomBytes(32),{mode:0o600,flag:"wx"});}catch(e){if((e as NodeJS.ErrnoException).code!=="EEXIST")throw e;}
  const info=lstatSync(path);if(realpathSync(path)!==path||!info.isFile()||info.nlink!==1||info.uid!==process.getuid?.()||(info.mode&0o777)!==0o600||info.size!==32)throw Error("Unsafe private native evidence key");return readFileSync(path);
}
function verifiedEvidence(store:Store,input:SessionRestartOwnershipProof) {
  const key=evidenceKey(store);
  return store.db.prepare("SELECT kind,body FROM h041_checkpoint_native_evidence WHERE session_id=? AND run_id=? AND kind!='native_operation'").all(input.sessionId,input.runId).map(row=>{
    const value=JSON.parse(String(row.body));if(typeof value.seal!=="string"||!/^[a-f0-9]{64}$/.test(value.seal)||!timingSafeEqual(Buffer.from(value.seal,"hex"),createHmac("sha256",key).update(JSON.stringify(value.payload)).digest())||value.payload.sessionId!==input.sessionId||value.payload.runId!==input.runId||value.payload.event.kind!==row.kind)throw Error("Untrusted protected native evidence");return value.payload;
  });
}
function restartSnapshot(store:Store,input:SessionRestartOwnershipProof) {
  const session=store.getSession(requireId(input.sessionId));
  const run=store.db.prepare("SELECT id,status FROM runs WHERE session_id=? AND id=?").get(input.sessionId,input.runId);
  const checkpoint=store.db.prepare("SELECT id,status,body FROM h041_session_checkpoints WHERE session_id=? AND run_id=?").get(input.sessionId,input.runId);
  if(session.nativeSessionId!==input.threadId||session.nativeState.ownership!=="idle"||session.nativeState.activeTurnId!==null||store.isQuarantined(session.workspaceId)||run?.status!=="completed"||checkpoint?.status!=="settled"||store.checkpoints.status(input.sessionId).some(c=>c.status==="recovery_required"))throw Error("Unsettled/uncertain Store parent cannot be adopted");
  const observed=verifiedEvidence(store,input),launch=observed.find(r=>r.event.kind==="launch"),settlement=observed.find(r=>r.event.kind==="settlement"),thread=observed.find(r=>r.event.kind==="thread"),gateway=observed.find(r=>r.event.kind==="gateway_settled");
  if(!launch||!settlement||!settlement.event.receipt?.cleanupOk||settlement.event.receipt.nonce!==launch.event.receipt?.nonce||settlement.event.receipt.containerId!==launch.event.receipt?.container?.id||thread?.event.threadId!==input.threadId||!thread.event.rolloutPath||gateway?.event.threadId!==input.threadId)throw Error("Store parent lacks genuine receipt/thread/rollout/gateway lineage");
  const evidence=observed.filter(r=>r.event.kind==="checkpoint_artifact").map(r=>r.event).filter(c=>c.checkpointId===input.checkpointId&&c.threadId===input.threadId);
  if(input.purpose==="settled-compaction"){
    if(checkpoint.id!==input.checkpointId||!observed.some(r=>r.event.kind==="compaction"&&r.event.threadId===input.threadId&&r.event.status==="completed"))throw Error("Store lacks actual settled compaction checkpoint");
  }else if(evidence.length!==2||new Set(evidence.map(c=>c.callId)).size!==2)throw Error("Store lacks consumed owned checkpoint lineage");
  for(const e of evidence){if(!store.db.prepare("SELECT f.id FROM files f JOIN h002_file_refs r ON r.file_id=f.id WHERE f.session_id=? AND f.id=? AND f.kind='artifact' AND r.run_id=?").get(input.sessionId,e.artifactId,input.runId)||!store.db.prepare("SELECT id FROM h041_originals WHERE session_id=? AND kind='file' AND source_key=? AND sha256=? AND availability='complete'").get(input.sessionId,e.artifactId,e.sha256))throw Error("Checkpoint artifact originals unavailable");}
  return JSON.stringify({databasePath:store.databasePath,...input,workspaceId:session.workspaceId,nativeState:session.nativeState,checkpoint,observed,consumed:evidence});
}
/** Revalidates the live reopened Store, never rebrands serialized proof JSON. */
export function validateSessionRestartOwnership(proof:SessionRestartOwnershipProof) {
  const authority=restartProofs.get(proof);if(!authority||restartSnapshot(authority.store,proof)!==authority.snapshot)throw Error("Missing/changed protected Store restart authority");return authority.snapshot;
}
export function claimSessionRestartOwnership(proof:SessionRestartOwnershipProof,newRunId:string,handoffSha256:string){const authority=restartProofs.get(proof);validateSessionRestartOwnership(proof);if(!authority)throw Error("Missing restart authority");requireId(newRunId);authority.store.db.prepare("INSERT INTO h041_restart_claims VALUES(?,?,?,?,?,?)").run(proof.sessionId,proof.threadId,proof.checkpointId,newRunId,"claimed_no_replay",handoffSha256);}
export function correlateSessionRestartOwnership(proof:SessionRestartOwnershipProof,owner:CodexPolicyOwner) {
 const snapshot=JSON.parse(validateSessionRestartOwnership(proof)),launch=snapshot.observed.find((r:any)=>r.event.kind==="launch"),settlement=snapshot.observed.find((r:any)=>r.event.kind==="settlement"),thread=snapshot.observed.find((r:any)=>r.event.kind==="thread");
 if(owner.threadId!==proof.threadId||thread.event.rolloutPath!==owner.rolloutPath||launch.receiptRawSha256!==codexReceiptProvenance(owner.launch)?.rawSha256||settlement.receiptRawSha256!==codexReceiptProvenance(owner.settlement!)?.rawSha256||launch.event.receipt.nonce!==owner.launch.nonce||settlement.event.receipt.nonce!==owner.settlement?.nonce||canonicalJson(launch.launchValidation)!==canonicalJson(codexReceiptValidation(owner.launch)))throw Error("Store proof does not match ORIGINAL policy receipts/rollout");
 if(proof.purpose==="settled-compaction"){
   if(!owner.settledCompaction||!snapshot.observed.some((r:any)=>r.event.kind==="compaction"&&r.event.turnId===owner.settledCompaction!.turnId&&r.event.status==="completed"&&owner.settledCompaction!.compactionIds.includes(r.event.compactionId)))throw Error("Compaction handoff lacks actual native replacement lineage");
 }else{
   const actual=snapshot.consumed.map(({threadId,kind,observation,...c}:any)=>c);
   if(canonicalJson(actual)!==canonicalJson(owner.checkpoints.filter(c=>c.checkpointId===proof.checkpointId))||actual.some((c:any)=>c.turnId!==owner.settledTurnId))throw Error("Consumed checkpoint differs from actual policy handoff");
 }
}
export class SessionCheckpoint {
  constructor(private readonly store: Store) {
    store.db.exec(`CREATE TABLE IF NOT EXISTS h041_session_checkpoints(id TEXT PRIMARY KEY,session_id TEXT NOT NULL REFERENCES sessions(id),run_id TEXT NOT NULL UNIQUE REFERENCES runs(id),status TEXT NOT NULL,body TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS h041_checkpoint_recoveries(id TEXT PRIMARY KEY,session_id TEXT NOT NULL REFERENCES sessions(id),checkpoint_id TEXT NOT NULL UNIQUE,body TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS h041_checkpoint_transitions(session_id TEXT NOT NULL,run_id TEXT NOT NULL,body TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS h041_checkpoint_native_evidence(session_id TEXT NOT NULL,run_id TEXT NOT NULL,kind TEXT NOT NULL,body TEXT NOT NULL);`);
    store.db.exec("CREATE TABLE IF NOT EXISTS h041_restart_claims(session_id TEXT NOT NULL,thread_id TEXT NOT NULL,checkpoint_id TEXT NOT NULL,new_run_id TEXT NOT NULL,status TEXT NOT NULL,handoff_sha256 TEXT NOT NULL,PRIMARY KEY(session_id,thread_id,checkpoint_id))");
  }
  prepare(sessionId: string, runId: string, kind: string, nativeThreadId?: string) {
    this.store.memory.bridge(sessionId).assertContinuationAllowed();
    if (!this.store.db.prepare("SELECT id FROM runs WHERE session_id=? AND id=?").get(sessionId,requireId(runId))) throw Error("Unowned checkpoint run");
    this.store.memory.indexHistory(sessionId);
    const view = this.store.memory.view(sessionId);
    const record: SessionCheckpointRecord = { id: randomUUID(), sessionId, runId, kind, nativeThreadId: nativeThreadId ?? null, acceptedVersionId: view.current?.id ?? null, acceptedStateSha256:view.current?createHash("sha256").update(JSON.stringify(view.current)).digest("hex"):null, originalInventory:this.store.memory.inventory(sessionId),nativeState:structuredClone(this.store.getSession(sessionId).nativeState),references: view.references.map(r => ({ id: r.id, sha256: r.sha256 })), preparedAt: new Date().toISOString(), status: "prepared", compactions: [] };
    this.store.db.prepare("INSERT INTO h041_session_checkpoints VALUES(?,?,?,?,?)").run(record.id,sessionId,runId,record.status,JSON.stringify(record));
    this.store.db.prepare("INSERT INTO h041_checkpoint_transitions VALUES(?,?,?)").run(sessionId,runId,JSON.stringify(record));return record;
  }
  private update(sessionId: string, runId: string, change: (r: SessionCheckpointRecord) => void) {
    const row = this.store.db.prepare("SELECT body FROM h041_session_checkpoints WHERE session_id=? AND run_id=?").get(sessionId,runId);
    if (!row) throw Error("Missing owned before-dispatch checkpoint");
    const record = JSON.parse(String(row.body)) as SessionCheckpointRecord; change(record);
    this.store.db.prepare("INSERT INTO h041_checkpoint_transitions VALUES(?,?,?)").run(sessionId,runId,JSON.stringify(record));
    this.store.db.prepare("UPDATE h041_session_checkpoints SET status=?,body=? WHERE session_id=? AND run_id=?").run(record.status,JSON.stringify(record),sessionId,runId); return record;
  }
  observeCompaction(sessionId: string, runId: string, compactionId: string, status: "start" | "completed" | "failed") {
    return this.update(sessionId,runId,r => {
      const prior = r.compactions.find(c => c.id === compactionId);
      if (prior) { if (prior.status === "failed" && status !== "failed") throw Error("Failed replacement cannot become completion"); prior.status = status; }
      else r.compactions.push({ id: compactionId, status });
      r.status = status === "failed" ? "recovery_required" : r.status === "recovery_required" ? r.status : "replacement_observed";
    });
  }
  finish(sessionId: string, runId: string, outcome: "completed" | "cancelled" | "failed") {
    return this.update(sessionId,runId,r => { r.outcome = outcome;
      // Cleanup only releases physical ownership. Cancellation/error after a replacement
      // or a manual compaction attempt cannot establish semantic continuity.
      const prior=this.store.db.prepare("SELECT body FROM h041_memory_versions WHERE session_id=? AND id=?").get(sessionId,r.acceptedVersionId);
      const retainedState=r.acceptedVersionId===null||!!prior&&createHash("sha256").update(String(prior.body)).digest("hex")===r.acceptedStateSha256;
      const retainedInventory=JSON.stringify(this.store.memory.inventory(sessionId,r.originalInventory.through))===JSON.stringify(r.originalInventory);
      r.status = r.status === "recovery_required" || outcome !== "completed" || !retainedState || !retainedInventory ? "recovery_required" : "settled";
    });
  }
  recordNativeEvidence(sessionId:string,runId:string,kind:string,body:unknown) {
    if(kind!=="native_operation")throw Error("Native evidence requires opaque genuine host observation");
    if(!this.store.db.prepare("SELECT id FROM h041_session_checkpoints WHERE session_id=? AND run_id=?").get(sessionId,runId))throw Error("Unowned native evidence");
    this.store.db.prepare("INSERT INTO h041_checkpoint_native_evidence VALUES(?,?,?,?)").run(sessionId,runId,kind,JSON.stringify(body));
  }
  recordNativeObservation(sessionId:string,runId:string,event:CodexNativeObservation) {
    const launch=validateCodexObservation(event,sessionId),keyPath=this.store.databasePath+".h041-native-evidence.key";
    for(const m of launch.container.mounts)if(keyPath===m.source||keyPath.startsWith(m.source+sep))throw Error("Native evidence key overlaps model mount");
    if(!this.store.db.prepare("SELECT id FROM h041_session_checkpoints WHERE session_id=? AND run_id=?").get(sessionId,runId))throw Error("Unowned native evidence run");
    const key=evidenceKey(this.store,true),payload={sessionId,runId,event,launchRawSha256:codexReceiptProvenance(launch)!.rawSha256,launchValidation:codexReceiptValidation(launch),...(event.kind==="launch"||event.kind==="settlement"?{receiptRawSha256:codexReceiptProvenance(event.receipt)!.rawSha256,receiptUtf8:getCodexReceiptUtf8(event.receipt)}:{})};
    this.store.db.prepare("INSERT INTO h041_checkpoint_native_evidence VALUES(?,?,?,?)").run(sessionId,runId,event.kind,JSON.stringify({payload,seal:createHmac("sha256",key).update(JSON.stringify(payload)).digest("hex")}));
  }
  issueRestartOwnership(input:SessionRestartOwnershipProof):SessionRestartOwnershipProof {
    const proof=Object.freeze({...input}),snapshot=restartSnapshot(this.store,proof);restartProofs.set(proof,{store:this.store,snapshot});return proof;
  }
  recoverInterrupted() {
    for (const row of this.store.db.prepare("SELECT session_id,run_id FROM h041_session_checkpoints WHERE status IN ('prepared','replacement_observed')").all())
      this.update(String(row.session_id),String(row.run_id),r => { r.outcome = "process_restart"; r.status = "recovery_required"; });
  }
  status(sessionId: string) {
    this.store.getSession(requireId(sessionId));
    return this.store.db.prepare("SELECT body FROM h041_session_checkpoints WHERE session_id=? ORDER BY rowid DESC LIMIT 64").all(sessionId).map(r => JSON.parse(String(r.body)) as SessionCheckpointRecord);
  }
  /** Acknowledgement retains a reviewed recovery plan; it cannot clear the gate or replay anything. */
  acknowledge(sessionId: string, checkpointId: string, note: string) {
    this.store.getSession(requireId(sessionId)); requireId(checkpointId);
    if (typeof note !== "string" || !note.trim() || Buffer.byteLength(note) > 4096 || !this.store.db.prepare("SELECT id FROM h041_session_checkpoints WHERE session_id=? AND id=? AND status='recovery_required'").get(sessionId,checkpointId)) throw Error("Unowned recovery acknowledgement");
    const id = randomUUID(); this.store.db.prepare("INSERT INTO h041_checkpoint_recoveries VALUES(?,?,?,?)").run(id,sessionId,checkpointId,JSON.stringify({id,note,acknowledgedAt:new Date().toISOString(),nativeRecovery:"NOT_TESTED",continuationBlocked:true})); return { id, continuationBlocked: true };
  }
  /** Explicit host-qualified fresh no-generation parent; never overwrites originals or replays failed work. */
  recoverWithFreshParent(sessionId:string,checkpointId:string,evidence:FreshParentRecoveryEvidence) {
    const session=this.store.getSession(requireId(sessionId));requireId(checkpointId);
    if(session.nativeState.ownership!=="idle"||session.nativeState.activeTurnId!==null||this.store.isQuarantined(session.workspaceId))throw Error("Physical native ownership remains uncertain");
    const row=this.store.db.prepare("SELECT run_id,body FROM h041_session_checkpoints WHERE session_id=? AND id=? AND status='recovery_required'").get(sessionId,checkpointId);
    if(!row||!this.store.db.prepare("SELECT id FROM h041_checkpoint_recoveries WHERE session_id=? AND checkpoint_id=?").get(sessionId,checkpointId))throw Error("Human acknowledged exact-session recovery required");
    const launch=validateCodexObservation(evidence.launch,sessionId);
    for(const observation of [evidence.thread,evidence.settlement,evidence.gateway])if(validateCodexObservation(observation,sessionId)!==launch)throw Error("Recovery observations have different owned launches");
    if(evidence.launch.kind!=="launch"||evidence.thread.kind!=="thread"||evidence.thread.method!=="thread/start"||evidence.thread.threadId===session.nativeSessionId||evidence.settlement.kind!=="settlement"||!evidence.settlement.receipt.cleanupOk||evidence.gateway.kind!=="gateway_settled"||evidence.gateway.threadId!==evidence.thread.threadId||evidence.gateway.activeTurnId!==null)throw Error("Recovery requires actual fresh no-generation ACK and native/gateway settlement");
    const prior=JSON.parse(String(row.body)) as SessionCheckpointRecord;
    if(JSON.stringify(this.store.memory.inventory(sessionId,prior.originalInventory.through))!==JSON.stringify(prior.originalInventory))throw Error("Recovery original inventory changed");
    if(prior.acceptedVersionId){const accepted=this.store.db.prepare("SELECT body FROM h041_memory_versions WHERE session_id=? AND id=?").get(sessionId,prior.acceptedVersionId);if(!accepted||createHash("sha256").update(String(accepted.body)).digest("hex")!==prior.acceptedStateSha256)throw Error("Recovery accepted state changed");}
    this.store.db.exec("SAVEPOINT fresh_parent_recovery");
    try {
      if(Number(this.store.db.prepare("UPDATE sessions SET native_session_id=? WHERE id=? AND native_session_id IS ?").run(evidence.thread.threadId,sessionId,session.nativeSessionId??null).changes)!==1)throw Error("Recovery parent CAS failed");
      this.update(sessionId,String(row.run_id),r=>{r.status="recovered";});
      this.store.db.prepare("INSERT INTO h041_checkpoint_transitions VALUES(?,?,?)").run(sessionId,String(row.run_id),JSON.stringify({kind:"fresh_parent_no_replay",oldNativeThreadId:session.nativeSessionId,newNativeThreadId:evidence.thread.threadId,launchRawSha256:codexReceiptProvenance(launch)!.rawSha256,nativeSemanticAcceptance:"NOT_TESTED"}));
      this.store.db.exec("RELEASE fresh_parent_recovery");return {nativeThreadId:evidence.thread.threadId,failedRunReplayed:false,originalsRetained:true};
    } catch(e){this.store.db.exec("ROLLBACK TO fresh_parent_recovery; RELEASE fresh_parent_recovery");throw e;}
  }
}
