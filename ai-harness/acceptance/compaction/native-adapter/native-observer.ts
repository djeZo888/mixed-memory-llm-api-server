import { Transform, Writable } from 'node:stream';
import { closeSync, constants, fsyncSync, openSync, writeSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { randomUUID } from 'node:crypto';
import type { RootlessCodexProcess } from '../../../server/src/codex-engine.js';
import { isRecord } from '../../../server/src/codex-connection.js';
import { sha256, stableJson } from './projection.js';

export interface NativeFrame {
  direction: 'to-native' | 'from-native'; bytesUtf8: string; sha256: string;
  observedAt: string; sequence: number; value: Record<string, unknown>;
}
interface NativeHandle {
  handleId: string; sessionId: string; frames: NativeFrame[]; failed: boolean;
  cleanup?: { confirmed: boolean; observedAt: string };
  gateway?: { nativeThreadId?: string; nativeTurnId: string | null; confirmed: boolean; observedAt: string };
}
export interface ObservedOperation {
  handleId: string; sessionId: string; nativeThreadId: string; nativeTurnId: string;
  method: 'turn/start' | 'thread/compact/start'; request: NativeFrame; ack: NativeFrame;
  started: NativeFrame; completed: NativeFrame; compactionId?: string; compactionStarted?: NativeFrame; compactionCompleted?: NativeFrame;
  cleanup: NonNullable<NativeHandle['cleanup']>; gateway: NonNullable<NativeHandle['gateway']>;
  traceReceiptSha256: string;
}
function writePrivate(path: string, bytes: string) {
  const fd = openSync(path, constants.O_WRONLY | constants.O_CREAT | constants.O_EXCL | constants.O_NOFOLLOW, 0o600);
  try { const b = Buffer.from(bytes); for (let p = 0; p < b.length;) { const n = writeSync(fd, b, p, b.length - p); if (!n) throw Error('native_capture_incomplete'); p += n; } fsyncSync(fd); }
  finally { closeSync(fd); }
  const dir = openSync(dirname(path), constants.O_RDONLY);
  try { fsyncSync(dir); } finally { closeSync(dir); }
}

/** A byte-preserving tap on the temporary composition's actual private stdio.
 * Handles are host capture identities, never invented native process IDs.
 * Runtime policy/launcher remain unchanged; no server calls are answered here.
 */
export class NativeObserver {
  private handles: NativeHandle[] = [];
  private observed=new WeakMap<object,{handle:NativeHandle;buffers:Record<string,Buffer>;rawSequence:number}>();
  registerObserved(sessionId:string,process:object){if(this.observed.has(process))throw Error('actual_native_process_already_observed');const handle:NativeHandle={handleId:randomUUID(),sessionId,frames:[],failed:false};this.handles.push(handle);this.observed.set(process,{handle,buffers:{input:Buffer.alloc(0),output:Buffer.alloc(0)},rawSequence:0});}
  ingestObserved(event:{sessionId:string;process:object;direction:'input'|'output';sequence:number;bytes:Buffer;sha256:string}){const state=this.observed.get(event.process);if(!state||state.handle.sessionId!==event.sessionId||event.sequence!==state.rawSequence+1||sha256(event.bytes)!==event.sha256||this.totalBytes+event.bytes.length>this.maxBytes)throw Error('actual_native_raw_process_sequence');state.rawSequence=event.sequence;this.totalBytes+=event.bytes.length;const buffer=Buffer.concat([state.buffers[event.direction],event.bytes]);let begin=0,end:number;while((end=buffer.indexOf(10,begin))!==-1){const raw=buffer.subarray(begin,end+1);begin=end+1;if(raw.length>4*1024*1024||!Buffer.from(raw.toString('utf8')).equals(raw))throw Error('actual_native_raw_frame_bound');const value=JSON.parse(raw.toString('utf8'));if(!isRecord(value))throw Error('actual_native_raw_frame_invalid');const direction=event.direction==='input'?'to-native':'from-native',frame:NativeFrame={direction,value,bytesUtf8:raw.toString('utf8'),sha256:sha256(raw),sequence:state.handle.frames.length,observedAt:new Date().toISOString()};writePrivate(join(this.directory,`${state.handle.handleId}-${frame.sequence}-${direction}.jsonl`),frame.bytesUtf8);state.handle.frames.push(frame);for(const notify of [...this.listeners])notify();}state.buffers[event.direction]=buffer.subarray(begin);}
  cleanupObserved(process:object){const state=this.observed.get(process);if(!state||Object.values(state.buffers).some(b=>b.length))throw Error('actual_native_raw_cleanup_incomplete');state.handle.cleanup={confirmed:true,observedAt:new Date().toISOString()};}
  private totalBytes = 0;
  private listeners=new Set<()=>void>();
  constructor(private directory: string, private maxBytes = 64 * 1024 * 1024) {}
  wrap(sessionId: string, child: RootlessCodexProcess): RootlessCodexProcess {
    const handle: NativeHandle = { handleId: randomUUID(), sessionId, frames: [], failed: false };
    this.handles.push(handle);
    const buffers = { 'to-native': Buffer.alloc(0), 'from-native': Buffer.alloc(0) };
    const record = (direction: NativeFrame['direction'], bytes: Buffer) => {
      if (this.totalBytes + bytes.length > this.maxBytes) throw Error('native_total_capture_bound');
      this.totalBytes += bytes.length;
      const buffer = Buffer.concat([buffers[direction], bytes]);
      let begin = 0, end: number;
      while ((end = buffer.indexOf(10, begin)) !== -1) {
        const raw = buffer.subarray(begin, end + 1); begin = end + 1;
        if (raw.length > 4 * 1024 * 1024 || handle.frames.length >= 8192 || !Buffer.from(raw.toString('utf8')).equals(raw)) throw Error('native_capture_bound_or_utf8');
        const value: unknown = JSON.parse(raw.toString('utf8'));
        if (!isRecord(value)) throw Error('native_capture_frame_invalid');
        const frame: NativeFrame = { direction, bytesUtf8: raw.toString('utf8'), sha256: sha256(raw), observedAt: new Date().toISOString(), sequence: handle.frames.length, value };
        writePrivate(join(this.directory, `${handle.handleId}-${frame.sequence}-${direction}.jsonl`), frame.bytesUtf8);
        handle.frames.push(frame);for(const notify of [...this.listeners])notify();
      }
      buffers[direction] = buffer.subarray(begin);
      if (buffers[direction].length > 4 * 1024 * 1024) throw Error('native_capture_frame_bound');
    };
    const output = new Transform({ transform(chunk, _encoding, callback) {
      try { record('from-native', Buffer.from(chunk)); callback(null, chunk); }
      catch { handle.failed = true; callback(Error('native_observation_failed')); }
    } });
    child.stdout.on('error', () => { handle.failed = true; output.destroy(Error('native_transport_failed')); });
    child.stdout.pipe(output);
    const input = new Writable({ write(chunk, _encoding, callback) {
      try { record('to-native', Buffer.from(chunk)); child.stdin.write(chunk, callback); }
      catch { handle.failed = true; callback(Error('native_observation_failed')); }
    } });
    child.stdin.on('error', () => { handle.failed = true; input.destroy(Error('native_transport_failed')); });
    let cleanup: Promise<boolean> | undefined;
    // Preserve actual successor receipt promises without minting or qualifying them.
    return { ...child, stdin: input, stdout: output, exited: child.exited,
      terminateAndConfirm: () => cleanup ??= (async () => {
        const confirmed = await child.terminateAndConfirm().catch(() => false);
        handle.cleanup = { confirmed, observedAt: new Date().toISOString() };
        if (buffers['from-native'].length || buffers['to-native'].length) handle.failed = true;
        try { writePrivate(join(this.directory, `${handle.handleId}-cleanup.json`), stableJson(handle.cleanup)); } catch (error) { handle.failed = true; throw error; }
        return confirmed;
      })() };
  }
  gateway(sessionId: string, nativeThreadId: string | undefined, nativeTurnId: string | null, confirmed: boolean) {
    const handle = this.handles.findLast(h => h.sessionId === sessionId);
    if (!handle) throw Error('gateway_native_handle_missing');
    if (!handle.cleanup || Date.now() < Date.parse(handle.cleanup.observedAt)) throw Error('gateway_before_native_cleanup');
    handle.gateway = { nativeThreadId, nativeTurnId, confirmed, observedAt: new Date().toISOString() };
    try { writePrivate(join(this.directory, `${handle.handleId}-gateway-${randomUUID()}.json`), stableJson(handle.gateway)); } catch (error) { handle.failed = true; throw error; }
  }
  frames(sessionId: string) {
    const handle = this.handles.findLast(h => h.sessionId === sessionId);
    if (!handle || handle.failed) throw Error('native_frames_missing_or_failed');
    return structuredClone(handle.frames);
  }
  /** Await actual stdio observation while admission stays held. No synthetic
   * event or second native connection; cancellation/deadline remain bounded. */
  async waitFrames(sessionId:string,predicate:(frames:NativeFrame[])=>boolean,signal:AbortSignal,expiresAt:number):Promise<NativeFrame[]>{
    return new Promise((resolve,reject)=>{
      let timer:ReturnType<typeof setTimeout>|undefined;
      const finish=(error?:Error,frames?:NativeFrame[])=>{this.listeners.delete(check);signal.removeEventListener('abort',abort);if(timer)clearTimeout(timer);if(error)reject(error);else resolve(frames!);};
      const abort=()=>finish(Error('owned_native_observation_cancelled'));
      const check=()=>{try{if(signal.aborted||Date.now()>=expiresAt)return abort();const frames=this.frames(sessionId);if(predicate(frames))finish(undefined,frames);}catch{finish(Error('owned_native_observation_failed'));}};
      this.listeners.add(check);signal.addEventListener('abort',abort,{once:true});timer=setTimeout(()=>finish(Error('owned_native_observation_deadline')),Math.max(1,Math.min(120000,expiresAt-Date.now())));check();
    });
  }
  sessions() { return [...new Set(this.handles.map(h => h.sessionId))]; }
  settled(sessionId: string) { return this.handles.some(h => h.sessionId === sessionId) && this.handles.filter(h => h.sessionId === sessionId).every(h => !h.failed && h.cleanup?.confirmed && h.gateway?.confirmed); }
  operation(sessionId: string): ObservedOperation {
    const handle = this.handles.findLast(h => h.sessionId === sessionId);
    if (!handle || handle.failed || !handle.cleanup?.confirmed || !handle.gateway?.confirmed) throw Error('native_operation_cleanup_or_capture_unconfirmed');
    const outgoing = handle.frames.filter(f => f.direction === 'to-native' && ['turn/start', 'thread/compact/start'].includes(String(f.value.method)));
    if (outgoing.length !== 1) throw Error('native_operation_missing_or_ambiguous');
    const request = outgoing[0], params = request.value.params;
    if (!Number.isSafeInteger(request.value.id)) throw Error('native_operation_rpc_identity_invalid');
    if (!isRecord(params) || typeof params.threadId !== 'string') throw Error('native_operation_thread_unavailable');
    const acks = handle.frames.filter(f => f.direction === 'from-native' && f.value.id === request.value.id && 'result' in f.value && !('error' in f.value));
    const started = handle.frames.filter(f => f.direction === 'from-native' && f.value.method === 'turn/started' && isRecord(f.value.params) && f.value.params.threadId===params.threadId);
    const completed = handle.frames.filter(f => f.direction === 'from-native' && f.value.method === 'turn/completed' && isRecord(f.value.params) && f.value.params.threadId===params.threadId);
    if (acks.length !== 1 || !isRecord(acks[0].value.result) || started.length !== 1 || !completed.length) throw Error('native_ack_or_terminal_absent');
    const first = started[0].value.params, last = completed[0].value.params;
    if (!isRecord(first) || !isRecord(last) || !isRecord(first.turn) || !isRecord(last.turn) ||
        first.threadId !== params.threadId || last.threadId !== params.threadId || typeof first.turn.id !== 'string' || last.turn.id !== first.turn.id ||
        last.turn.status !== 'completed' || last.turn.error != null || completed.some(f => stableJson(f.value.params) !== stableJson(last)) ||
        handle.gateway.nativeThreadId !== params.threadId || handle.gateway.nativeTurnId !== first.turn.id) throw Error('native_terminal_or_settlement_identity_mismatch');
    if (request.sequence >= acks[0].sequence || request.sequence >= started[0].sequence || started[0].sequence >= completed[0].sequence ||
        Date.parse(completed.at(-1)!.observedAt) > Date.parse(handle.cleanup.observedAt) || Date.parse(acks[0].observedAt) > Date.parse(handle.cleanup.observedAt)) throw Error('native_operation_order_mismatch');
    if (request.value.method === 'turn/start') {
      const result = acks[0].value.result as Record<string, unknown>;
      if (!isRecord(result.turn) || result.turn.id !== first.turn.id) throw Error('native_turn_ack_identity_mismatch');
    }
    const compacted = handle.frames.filter(f => f.direction === 'from-native' && f.value.method === 'item/completed' &&
      isRecord(f.value.params) && isRecord(f.value.params.item) && f.value.params.item.type === 'contextCompaction');
    let compactionId: string | undefined, compactionStarted: NativeFrame | undefined, compactionCompleted: NativeFrame | undefined;
    if (request.value.method === 'thread/compact/start') {
      if (compacted.length !== 1) throw Error('canonical_compaction_item_absent_or_ambiguous');
      const p = compacted[0].value.params as Record<string, unknown>, item = p.item as Record<string, unknown>;
      if (p.threadId !== params.threadId || p.turnId !== first.turn.id || typeof item.id !== 'string') throw Error('canonical_compaction_item_identity_mismatch');
      const starts = handle.frames.filter(f => f.direction === 'from-native' && f.value.method === 'item/started' &&
        isRecord(f.value.params) && isRecord(f.value.params.item) && f.value.params.item.id === item.id && f.value.params.item.type === 'contextCompaction');
      if (starts.length !== 1 || !isRecord(starts[0].value.params) || starts[0].value.params.threadId !== params.threadId ||
          starts[0].value.params.turnId !== first.turn.id || starts[0].sequence <= started[0].sequence || starts[0].sequence >= compacted[0].sequence || compacted[0].sequence >= completed[0].sequence) throw Error('compaction_item_lifecycle_mismatch');
      compactionId = item.id; compactionStarted = starts[0]; compactionCompleted = compacted[0];
    }
    const proof = { handleId: handle.handleId, request: request.sha256, ack: acks[0].sha256,
      started: started[0].sha256, completed: completed[0].sha256, compactionStarted: compactionStarted?.sha256 ?? null,
      compactionCompleted: compactionCompleted?.sha256 ?? null, cleanup: handle.cleanup, gateway: handle.gateway };
    return { handleId: handle.handleId, sessionId, nativeThreadId: params.threadId, nativeTurnId: first.turn.id,
      method: request.value.method as ObservedOperation['method'], request, ack: acks[0], started: started[0], completed: completed[0],
      compactionId, compactionStarted, compactionCompleted, cleanup: handle.cleanup, gateway: handle.gateway, traceReceiptSha256: sha256(stableJson(proof)) };
  }
}
