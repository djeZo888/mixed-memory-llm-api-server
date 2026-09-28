import { randomUUID } from "node:crypto";
import type { DatabaseSync } from "node:sqlite";
export type RequestOwnershipState = "queued" | "counting" | "accepted" | "draining" | "uncertain" | "settled";
export interface RequestOwnership { id:string; sessionId:string; state:RequestOwnershipState; lane?:string; updatedAt:string; }
export interface SettlementQuery { sessionId:string; nativeThreadId?:string; activeTurnId?:string|null; }
export interface OwnershipOptions {
  /** True only after a durable ledger has been opened and all prior records loaded. */
  recoveryReady:boolean;
  initialRequests?:readonly RequestOwnership[];
  /** Synchronous durable commit. No token or credentials are recorded. */
  onRequestState:(record:RequestOwnership)=>void;
}
/** Session lineage outlives token revocation and socket/native lifetimes. */
export class GatewayOwnership {
  private records=new Map<string,RequestOwnership>(); private knownSessions=new Set<string>(); private failed=false;
  constructor(private options?:OwnershipOptions){for(const r of options?.initialRequests??[]){if(!r.id||!r.sessionId||!["queued","counting","accepted","draining","uncertain","settled"].includes(r.state))throw Error("Invalid ownership ledger");this.knownSessions.add(r.sessionId);if(r.state!=="settled")this.records.set(r.id,{...r,state:"uncertain"});}}
  registerSession(sessionId:string){this.knownSessions.add(sessionId);}
  begin(sessionId:string):RequestOwnership {this.registerSession(sessionId);const r:RequestOwnership={id:randomUUID(),sessionId,state:"queued",updatedAt:new Date().toISOString()};this.records.set(r.id,r);this.write(r);return r;}
  transition(r:RequestOwnership,state:RequestOwnershipState,lane?:string){r.state=state;if(lane)r.lane=lane;r.updatedAt=new Date().toISOString();this.write(r);if(state==="settled")this.records.delete(r.id);}
  private write(r:RequestOwnership){try{this.options?.onRequestState({...r});}catch{r.state="uncertain";this.failed=true;throw Error("Gateway ownership ledger unavailable");}}
  confirm(query:SettlementQuery):boolean{return this.options?.recoveryReady===true&&!this.failed&&this.knownSessions.has(query.sessionId)&&![...this.records.values()].some(r=>r.sessionId===query.sessionId);}
  snapshot(sessionId:string){return [...this.records.values()].filter(r=>r.sessionId===sessionId).map(r=>({...r}));}
}
/** Additive table; old releases and existing lane/frontier ledgers remain intact. */
export class GatewayOwnershipLedger {
  constructor(private db:DatabaseSync){db.exec("CREATE TABLE IF NOT EXISTS h021_gateway_requests(id TEXT PRIMARY KEY, session_id TEXT NOT NULL, state TEXT NOT NULL, record TEXT NOT NULL)");}
  options():OwnershipOptions{return {recoveryReady:true,initialRequests:this.db.prepare("SELECT record FROM h021_gateway_requests WHERE state != 'settled'").all().map(r=>JSON.parse(String(r.record))),onRequestState:(record)=>{this.db.prepare("INSERT OR REPLACE INTO h021_gateway_requests VALUES(?,?,?,?)").run(record.id,record.sessionId,record.state,JSON.stringify(record));}};}
}
