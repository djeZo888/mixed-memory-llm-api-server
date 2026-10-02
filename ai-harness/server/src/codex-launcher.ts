import { codexTraceSchemaForMode, type CodexNativeTraceMode } from "./codex-receipts.js";
/** Host-only launcher adapter. It never invokes a host Codex executable. */
import { observeOwnedCodexProcess, type CodexHostObservations } from "./codex-host-observation.js";
import { createHash, randomUUID } from "node:crypto";
import { getCodexLaunchFailureDiagnostic, createCodexReceiptChannel, createCodexReceiptLifecycle, observeCodexProducer, validateCodexLaunchReceipt, validateCodexSettlementReceipt, validateCodexTraceReceipt, type CodexNativeTraceReceipt, type CodexReceiptPolicy, type CodexNativeLaunchReceipt, type CodexNativeSettlementReceipt } from "./codex-receipts.js";
import { spawn } from "node:child_process";
import { isAbsolute, join, resolve } from "node:path";
import type { Readable, Writable } from "node:stream";
export interface CodexLaunchInput {
    technicalVisionQualified?: boolean;
    /** Trusted private qualification only; public/native input never sets this. */
    nativeTraceMode?: CodexNativeTraceMode;
    sessionId: string;
    profileDir: string;
    workspace: string;
    codexHome: string;
    gatewayUrl: string;
    gatewayToken: string;
    modelPolicyVersion: string;
    /** Set only by trusted host composition, never chat input. */
    imageJobsQualified?: boolean;
    imageGenerationQualified?: boolean;
    /** Trusted isolated probe identity; never from the native request. */
    receiptRunId?: string;
}
export interface OwnedCodexProcess {
    observationFailure?: Promise<never>;
    stdin: Writable;
    stdout: Readable;
    exited: Promise<void>;
    /** Factual host child exit, never a native/cleanup qualification. */
    /** Host-only OOB location; never native authority or a model/tool path. */
    receiptChannelDirectory?: string;
    /** PRIVATE original redacted launcher pipe, armed before launch await; never authority. */
    launcherDiagnostics?:Promise<Readonly<{bytes:Buffer;sha256:string;truncated:boolean;complete:boolean}>>;
    launchFailureObservation?:Promise<Readonly<{value:unknown;rawUtf8:string|undefined;provenance:unknown;nativeQualified:false}>|undefined>;
    exitObservation?: Promise<Readonly<{code:number|null;signal:NodeJS.Signals|null;spawnFailed:boolean}>>;
    launchReceipt?: Promise<CodexNativeLaunchReceipt | undefined>;
    traceReceipt?: Promise<CodexNativeTraceReceipt | undefined>;
    settlementReceipt?: Promise<CodexNativeSettlementReceipt | undefined>;
    terminateAndConfirm(): Promise<boolean>;
}
export const CODEX_MODEL_POLICY = "sova-codex-0.158.0-qwen-text-v2";
/** Mounted tool/instruction policy is separate from the persisted model profile. */
export const CODEX_TOOL_POLICY_SHA256: string = "6d70b39cb33340f793fde3c46f18f8dbb703e4e65267e2c9e54c7fa984c2a3e7";
export const CODEX_GENERATION_POLICY_SHA256 = "3308a9550e5c2ab599489c3b7ba68df49bf4ae14d5195662f482c54f05699344";
/** Fixed reviewed script uses task-egress.py and redact-acp.py. Supervisor exit0
 * attests exact random container rm + explicit exists exit1, not mere PID exit.
 * Unclean exits/timeout stay uncertain. Gateway settlement is a separate proof.
 */
export function createRootlessCodexLauncher(launcherPath: string, receiptPolicy?: CodexReceiptPolicy, observations?: CodexHostObservations): (input: CodexLaunchInput) => Promise<OwnedCodexProcess> {
    if (!isAbsolute(launcherPath) || !launcherPath.endsWith("/deploy/run-codex.sh"))
        throw Error("Trusted Codex launcher path required");
    return async (input) => {
        if (process.platform !== "linux" || process.getuid?.() === 0 || input.modelPolicyVersion !== CODEX_MODEL_POLICY || input.gatewayUrl !== "http://10.0.2.2:8081/v1" || input.codexHome !== join(resolve(input.profileDir), "codex-home"))
            throw Error("Unqualified Codex rootless policy");
        if(input.imageJobsQualified && input.imageGenerationQualified)throw Error("Ambiguous full/generation-only profile");
        const traceSchema=codexTraceSchemaForMode(input.nativeTraceMode);
        if((traceSchema || input.technicalVisionQualified === true || input.imageGenerationQualified === true)&&!receiptPolicy)throw Error("Trusted trace receipt policy required");
        const channel = receiptPolicy ? createCodexReceiptChannel({ ...input, launcherPath, runId: input.receiptRunId ?? randomUUID() }, receiptPolicy) : undefined;
        const env: NodeJS.ProcessEnv = { PATH: "/usr/bin:/bin", HOME: process.env.HOME, USER: process.env.USER, LOGNAME: process.env.LOGNAME,
            AI_HARNESS_SESSION_ID: input.sessionId, AI_HARNESS_GATEWAY_URL: input.gatewayUrl, AI_HARNESS_GATEWAY_TOKEN: input.gatewayToken };
        if(traceSchema)env.AI_HARNESS_CODEX_TRACE_MODE=input.nativeTraceMode;
        if (channel) { env.AI_HARNESS_CODEX_RECEIPT_DIR = channel.directory; env.AI_HARNESS_CODEX_RECEIPT_NONCE = channel.binding.nonce; }
        const child = spawn(launcherPath, ["--profile-dir", input.profileDir, "--workspace", input.workspace, ...(input.imageJobsQualified === true ? ["--image-jobs-qualified"] : []), ...(input.imageGenerationQualified === true ? ["--image-generation-qualified"] : []), ...(input.technicalVisionQualified === true ? ["--technical-vision-qualified"] : [])], { env, stdio: ["pipe", "pipe", "pipe"] });
        // Qualification-only private bounded diagnostic capture is armed BEFORE
        // any launch await. Ordinary unqualified stderr stays discarded. It is
        // untrusted diagnostic text and can NEVER promote native authority.
        const launcherDiagnostics=channel?captureCodexLauncherDiagnostics(child.stderr):undefined;
        if(!channel)child.stderr.resume();
        let status: number | null | undefined;
        let spawnFailed = false;
        const exitObservation=new Promise<Readonly<{code:number|null;signal:NodeJS.Signals|null;spawnFailed:boolean}>>(resolve=>{child.once("error",()=>{spawnFailed=true;resolve(Object.freeze({code:null,signal:null,spawnFailed:true}));});child.once("exit",(code,signal)=>{status=code;resolve(Object.freeze({code,signal,spawnFailed:false}));});});
        const exited=exitObservation.then(()=>undefined);
        const ended = () => status !== undefined || spawnFailed;
        const launchReceipt = channel ? (async () => {
            try { const value: any = await channel.wait("launch", 15000, ended); if (!value || !child.pid) return undefined;
                return validateCodexLaunchReceipt(value, channel.binding, observeCodexProducer(value.producer?.pid, child.pid, channel.binding.uid));
            } catch { return undefined; }
        })() : undefined;
        const lifecycle = channel && launchReceipt ? createCodexReceiptLifecycle({
            launchReceipt, exited, hasExited: ended, cleanupBudgetMs: 120000,
            terminate: () => { child.kill("SIGTERM"); },
            async lookup(launch) { const value = await channel.wait("settlement", 500, () => false); return validateCodexSettlementReceipt(value, channel.binding, launch); },
        }) : undefined;
        const settlementReceipt = lifecycle?.settlementReceipt;
        const launchFailureObservation=channel&&launchReceipt?(async()=>{if(await launchReceipt)return undefined;const value=await channel.wait('failure',500,()=>false);if(!value)return undefined;const v=value as Record<string,unknown>;if(v.schema!=='codex-launch-failure-v1'||v.nonce!==channel.binding.nonce||v.sessionId!==channel.binding.sessionId||v.runId!==channel.binding.runId)return undefined;return getCodexLaunchFailureDiagnostic(value);})():undefined;
        void launchFailureObservation?.catch(()=>undefined);
        let cleanup: Promise<boolean> | undefined;
        const owned: OwnedCodexProcess = { stdin: child.stdin, stdout: child.stdout, exited, receiptChannelDirectory:channel?.directory, launcherDiagnostics, launchFailureObservation, exitObservation, launchReceipt, settlementReceipt, terminateAndConfirm() {
                if (lifecycle) return lifecycle.confirm();
                return cleanup ??= new Promise<boolean>(resolve => {
                    const timer = setTimeout(() => resolve(false), 45000);
                    if (status === undefined && !spawnFailed)
                        child.kill("SIGTERM");
                    void exited.then(() => { clearTimeout(timer); resolve(!spawnFailed && status === 0); });
                });
            } };
        if(traceSchema && channel){owned.traceReceipt=(async()=>{const settlement=await owned.settlementReceipt,launch=await launchReceipt;if(!settlement||!launch)return undefined;const value=await channel.wait("trace",500,()=>false);return validateCodexTraceReceipt(value,channel.binding,launch,settlement);})();void owned.traceReceipt.catch(()=>undefined);}
        if (observations) { try { return observeOwnedCodexProcess(owned,input,observations); } catch { await owned.terminateAndConfirm().catch(()=>false); throw Error("Trusted native observation failed"); } }
        return owned;
    };
}

/** This is selected by trusted receipt-policy host composition, never chat/env.
 * Raw bytes remain PRIVATE; bounded capture loss remains explicit. */
export function captureCodexLauncherDiagnostics(stream:Readable):Promise<Readonly<{bytes:Buffer;sha256:string;truncated:boolean;complete:boolean}>>{
 const chunks:Buffer[]=[];let bytes=0,truncated=false,complete=false;
 return new Promise(resolve=>{let done=false;const finish=()=>{if(done)return;done=true;const raw=Buffer.concat(chunks);resolve(Object.freeze({bytes:raw,sha256:createHash('sha256').update(raw).digest('hex'),truncated,complete}));};
 stream.on('data',chunk=>{if(!Buffer.isBuffer(chunk)){truncated=true;return;}const remaining=65536-bytes;if(chunk.length>remaining)truncated=true;if(remaining>0){const part=Buffer.from(chunk.subarray(0,remaining));chunks.push(part);bytes+=part.length;}});stream.once('end',()=>{complete=true;finish();});stream.once('error',finish);stream.once('close',finish);});
}
