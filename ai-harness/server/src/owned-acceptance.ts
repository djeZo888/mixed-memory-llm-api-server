/** Temporary operator-owned one-shot permissions. No task/API can create a grant. */
import { createHash } from "node:crypto";
import { appendFileSync, lstatSync, readFileSync, realpathSync, writeFileSync } from "node:fs";
import { dirname, isAbsolute, join } from "node:path";
import type { GatewayOptions } from "./gateway.js";
import { createOwnedProviderAcceptance, createOwnedProviderCapture, type ProviderBoundaryCapture } from "./provider-diagnostics.js";

interface Ticket { id: string; sessionId: string; expiresAt: number; image: boolean; frontier: boolean }
const uuid = (v: unknown): v is string => typeof v === "string" && /^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/.test(v);
export function createHostOwnedAcceptance(policy: string, activeRunId: (sessionId: string) => string | undefined, now: () => number = Date.now) {
  if (!isAbsolute(policy) || realpathSync(dirname(policy)) !== dirname(policy)) throw Error("Unsafe acceptance path");
  const uid = process.getuid?.(), directory = dirname(policy);
  for (let p = directory;; p = dirname(p)) {
    const s = lstatSync(p);
    if (!s.isDirectory() || s.isSymbolicLink() || (s.mode & (p === directory ? 0o077 : 0o022)) || ![0, uid].includes(s.uid)) throw Error("Unsafe acceptance ancestry");
    if (p === dirname(p)) break;
  }
  const grants = () => {
    const s = lstatSync(policy);
    if (!s.isFile() || s.isSymbolicLink() || s.nlink !== 1 || s.uid !== uid || (s.mode & 0o077) || s.size > 16384) throw Error("Unsafe acceptance policy");
    const v = JSON.parse(readFileSync(policy, "utf8"));
    if (v.schema !== 1 || !Array.isArray(v.tickets) || v.tickets.length > 8) throw Error("Invalid acceptance policy");
    const ids = new Set<string>(), sessions = new Set<string>();
    for (const t of v.tickets) {
      if (Object.keys(t).sort().join() !== "expiresAt,frontier,id,image,sessionId" || !uuid(t.id) || !uuid(t.sessionId) || ids.has(t.id) || sessions.has(t.sessionId) ||
          !Number.isSafeInteger(t.expiresAt) || typeof t.image !== "boolean" || typeof t.frontier !== "boolean") throw Error("Invalid acceptance ticket");
      ids.add(t.id); sessions.add(t.sessionId);
    }
    return v.tickets as Ticket[];
  };
  grants(); // Invalid explicitly selected startup policy fails closed.
  const bound = new Map<string, { ticket: Ticket; runId: string; requestIds: Set<string>; revoked: boolean; scope: ReturnType<typeof createOwnedProviderAcceptance>; sink: ReturnType<typeof createOwnedProviderCapture> }>();
  const consumedTickets = new Set<string>();
  const close = (sessionId: string, runId?: string) => {
    const b = bound.get(sessionId); if (!b || (runId !== undefined && b.runId !== runId)) return;
    b.scope.close(); b.sink.close(); bound.delete(sessionId);
    try { writeFileSync(join(directory, b.ticket.id, "closed.json"), JSON.stringify({sessionId, runId:b.runId, closedAt:now(), settlementClaim:false})+"\n", {flag:"wx",mode:0o600}); } catch { /* Closure itself does not depend on receipt I/O. */ }
  };
  const eligible = (sessionId: string) => {
    const b = bound.get(sessionId); if (!b || b.revoked) return undefined;
    try {
      if (!grants().some(t => JSON.stringify(t) === JSON.stringify(b.ticket)) || now() >= b.ticket.expiresAt) { b.scope.close(); b.revoked = true; return undefined; }
      return b.scope.allow(sessionId) ? b : undefined;
    } catch { b.scope.close(); b.revoked = true; return undefined; }
  };
  const metadata = (event: {sessionId:string;requestId:string}) => {
    const b = bound.get(event.sessionId); if (!b?.requestIds.has(event.requestId)) return;
    const file = join(directory,b.ticket.id,"diagnostics.jsonl"), line=JSON.stringify(event)+"\n";
    if (Buffer.byteLength(line) <= 65536 && lstatSync(file).size + Buffer.byteLength(line) <= 2*1024*1024)
      appendFileSync(file,line);
  };
  return {
    onRunAccepted(sessionId: string, runId: string) {
      if (bound.has(sessionId) || !uuid(runId)) return;
      let sink: ReturnType<typeof createOwnedProviderCapture> | undefined;
      try {
        const ticket = grants().find(t => t.sessionId === sessionId);
        if (!ticket || consumedTickets.has(ticket.id) || ticket.expiresAt <= now() || ticket.expiresAt - now() > 30*60*1000) return;
        consumedTickets.add(ticket.id);
        const scope = createOwnedProviderAcceptance({sessionId,runId,expiresAt:ticket.expiresAt,activeRunId},now);
        // The operator precreates this private directory. Exclusive receipt also
        // makes restart/repeated delivery fail closed without a second binding.
        const target = join(directory,ticket.id), st = lstatSync(target);
        if (!st.isDirectory() || st.isSymbolicLink() || st.uid !== uid || (st.mode & 0o077)) return;
        writeFileSync(join(target,"binding.json"),JSON.stringify({schema:1,ticket,sessionId,runId,boundAt:now(),policySha256:createHash("sha256").update(readFileSync(policy)).digest("hex")})+"\n",{flag:"wx",mode:0o600});
        writeFileSync(join(target,"diagnostics.jsonl"),"",{flag:"wx",mode:0o600});
        sink=createOwnedProviderCapture(target,sessionId);
        bound.set(sessionId,{ticket,runId,scope,sink,requestIds:new Set(),revoked:false});
      } catch { sink?.close(); /* No grant is installed on failure. */ }
    },
    onRunFinished: close,
    onDiagnostic: (event: Parameters<NonNullable<NonNullable<GatewayOptions["responses"]>["onDiagnostic"]>>[0]) => metadata(event),
    onFailure: (event: Parameters<NonNullable<NonNullable<GatewayOptions["diagnostics"]>["onFailure"]>>[0]) => metadata(event),
    image: (sessionId: string) => eligible(sessionId)?.ticket.image === true,
    frontier: (sessionId: string) => eligible(sessionId)?.ticket.frontier === true,
    capture(event: ProviderBoundaryCapture) {
      // Revocation stops NEW captured requests. Already accepted exact request
      // IDs keep bounded terminal/drain capture until the owned run finishes.
      if (event.phase === "pre_normalization") eligible(event.sessionId)?.requestIds.add(event.requestId);
      const b = bound.get(event.sessionId);
      if (b?.requestIds.has(event.requestId)) b.sink.capture(event);
    },
    close() { for (const session of [...bound.keys()]) close(session); },
  };
}
