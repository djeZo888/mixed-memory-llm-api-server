import { useEffect, useState } from 'react';
interface Draft { objective: string; constraints: unknown[]; decisions: unknown[]; pending: unknown[]; checks: unknown[] }
interface View { current: {id:string;state:Draft;trustedChecks:unknown[]} | null; proposals:{id:string;state:Draft}[]; references:{id:string;sha256:string|null;availability:string}[]; recovery:{id:string;status:string}[]; authority:string }
async function memoryRequest<T>(path:string,body?:unknown):Promise<T> {
  const response=await fetch(path,{cache:'no-store',...(body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})});
  const result=await response.json(); if(!response.ok)throw Error(result?.error?.message??'Memory operation failed'); return result;
}
/** Existing-session controls. Human authority comes from the protected browser proxy. */
export function MemoryPanel({sessionId,onClose}:{sessionId:string;onClose:()=>void}) {
 const base=`/api/sessions/${encodeURIComponent(sessionId)}/memory`,[view,setView]=useState<View|null>(null),[draft,setDraft]=useState(''),[note,setNote]=useState(''),[error,setError]=useState(''),[busy,setBusy]=useState(false),[original,setOriginal]=useState('');
 async function refresh(){const next=await memoryRequest<View>(base);setView(next);setDraft(JSON.stringify(next.current?.state??{objective:'',constraints:[],decisions:[],pending:[],checks:[]},null,2));}
 useEffect(()=>{let active=true;memoryRequest<View>(base).then(next=>{if(active){setView(next);setDraft(JSON.stringify(next.current?.state??{objective:'',constraints:[],decisions:[],pending:[],checks:[]},null,2));}}).catch(e=>{if(active)setError(String(e.message));});return()=>{active=false;};},[base]);
 async function act(operation:()=>Promise<unknown>){setBusy(true);setError('');try{await operation();await refresh();}catch(e){setError(e instanceof Error?e.message:String(e));}finally{setBusy(false);}}
 return <section aria-label="Conversation memory">
  <button onClick={onClose}>Close memory</button><h2>Conversation memory</h2>
  {error&&<p role="alert">{error}</p>}{!view?<p>Loading memory…</p>:<>
  <p>{view.authority}</p><h3>Accepted state</h3><pre>{JSON.stringify(view.current,null,2)}</pre>
  <label>Proposed correction (objective, constraints, decisions, pending work and check claims)<textarea aria-label="Proposed correction" value={draft} onChange={e=>setDraft(e.target.value)} /></label>
  <button disabled={busy} onClick={()=>void act(()=>memoryRequest(base+'/proposals',{state:JSON.parse(draft)}))}>Save proposal for review</button>
  <h3>Proposals</h3>{view.proposals.map(p=><article key={p.id}><pre>{JSON.stringify(p.state,null,2)}</pre><button disabled={busy} onClick={()=>void act(()=>memoryRequest(base+'/accept',{proposalId:p.id,expectedVersion:view.current?.id??null}))}>Accept reviewed proposal</button></article>)}
  <h3>Original references</h3>{view.references.map(r=><p key={r.id}>{r.id} · {r.sha256??'hash unavailable'} · {r.availability} <button disabled={busy||r.availability!=='complete'} onClick={()=>void act(async()=>{const read=await memoryRequest<{text:string}>(base+'/originals/'+encodeURIComponent(r.id)+'?offset=0&limit=8192');setOriginal(read.text);})}>Read first 8192 bytes</button></p>)}<pre>{original}</pre>
  <h3>Recovery checkpoints</h3><label>Review note<input aria-label="Recovery review note" value={note} onChange={e=>setNote(e.target.value)} /></label>
  {view.recovery.filter(c=>c.status==='recovery_required').map(c=><p key={c.id}>{c.id} · {c.status} <button disabled={busy||!note.trim()} onClick={()=>void act(()=>memoryRequest(base+'/recovery/'+encodeURIComponent(c.id)+'/acknowledge',{note}))}>Acknowledge preserved checkpoint</button> <button disabled={busy} onClick={()=>void act(()=>memoryRequest(base+'/recovery/'+encodeURIComponent(c.id)+'/recover',{}))}>Recover without replay</button></p>)}
  </>}
 </section>;
}
