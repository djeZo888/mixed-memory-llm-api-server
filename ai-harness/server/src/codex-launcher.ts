/** Host-only launcher adapter. It never invokes a host Codex executable. */
import { randomUUID } from "node:crypto";
import { createCodexReceiptChannel, createCodexReceiptLifecycle, observeCodexProducer, validateCodexLaunchReceipt, validateCodexSettlementReceipt, type CodexReceiptPolicy, type CodexNativeLaunchReceipt, type CodexNativeSettlementReceipt } from "./codex-receipts.js";
import { spawn } from "node:child_process";
import { isAbsolute, join, resolve } from "node:path";
import type { Readable, Writable } from "node:stream";
export interface CodexLaunchInput {
    sessionId: string;
    profileDir: string;
    workspace: string;
    codexHome: string;
    gatewayUrl: string;
    gatewayToken: string;
    modelPolicyVersion: string;
    /** Set only by trusted host composition, never chat input. */
    imageJobsQualified?: boolean;
    /** Trusted isolated probe identity; never from the native request. */
    receiptRunId?: string;
}
export interface OwnedCodexProcess {
    stdin: Writable;
    stdout: Readable;
    exited: Promise<void>;
    launchReceipt?: Promise<CodexNativeLaunchReceipt | undefined>;
    settlementReceipt?: Promise<CodexNativeSettlementReceipt | undefined>;
    terminateAndConfirm(): Promise<boolean>;
}
export const CODEX_MODEL_POLICY = "sova-codex-0.158.0-qwen-text-v2";
/** Mounted tool/instruction policy is separate from the persisted model profile. */
export const CODEX_TOOL_POLICY_SHA256: string = "38789bd752463b0a34beacb3849ea544ae5fc6fc4e6ea79204180ec229e5af59";
/** Fixed reviewed script uses task-egress.py and redact-acp.py. Supervisor exit0
 * attests exact random container rm + explicit exists exit1, not mere PID exit.
 * Unclean exits/timeout stay uncertain. Gateway settlement is a separate proof.
 */
export function createRootlessCodexLauncher(launcherPath: string, receiptPolicy?: CodexReceiptPolicy): (input: CodexLaunchInput) => Promise<OwnedCodexProcess> {
    if (!isAbsolute(launcherPath) || !launcherPath.endsWith("/deploy/run-codex.sh"))
        throw Error("Trusted Codex launcher path required");
    return async (input) => {
        if (process.platform !== "linux" || process.getuid?.() === 0 || input.modelPolicyVersion !== CODEX_MODEL_POLICY || input.gatewayUrl !== "http://10.0.2.2:8081/v1" || input.codexHome !== join(resolve(input.profileDir), "codex-home"))
            throw Error("Unqualified Codex rootless policy");
        const channel = receiptPolicy ? createCodexReceiptChannel({ ...input, launcherPath, runId: input.receiptRunId ?? randomUUID() }, receiptPolicy) : undefined;
        const env: NodeJS.ProcessEnv = { PATH: "/usr/bin:/bin", HOME: process.env.HOME, USER: process.env.USER, LOGNAME: process.env.LOGNAME,
            AI_HARNESS_SESSION_ID: input.sessionId, AI_HARNESS_GATEWAY_URL: input.gatewayUrl, AI_HARNESS_GATEWAY_TOKEN: input.gatewayToken };
        if (channel) { env.AI_HARNESS_CODEX_RECEIPT_DIR = channel.directory; env.AI_HARNESS_CODEX_RECEIPT_NONCE = channel.binding.nonce; }
        const child = spawn(launcherPath, ["--profile-dir", input.profileDir, "--workspace", input.workspace, ...(input.imageJobsQualified === true ? ["--image-jobs-qualified"] : [])], { env, stdio: ["pipe", "pipe", "pipe"] });
        // The supervisor redacts; discard all stderr here (no credential/error echo).
        child.stderr.resume();
        let status: number | null | undefined;
        let spawnFailed = false;
        const exited = new Promise<void>(resolve => { child.once("error", () => { spawnFailed = true; resolve(); }); child.once("exit", code => { status = code; resolve(); }); });
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
        let cleanup: Promise<boolean> | undefined;
        return { stdin: child.stdin, stdout: child.stdout, exited, launchReceipt, settlementReceipt, terminateAndConfirm() {
                if (lifecycle) return lifecycle.confirm();
                return cleanup ??= new Promise<boolean>(resolve => {
                    const timer = setTimeout(() => resolve(false), 45000);
                    timer.unref();
                    if (status === undefined && !spawnFailed)
                        child.kill("SIGTERM");
                    void exited.then(() => { clearTimeout(timer); resolve(!spawnFailed && status === 0); });
                });
            } };
    };
}
