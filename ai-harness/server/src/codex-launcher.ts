/** Host-only launcher adapter. It never invokes a host Codex executable. */
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
}
export interface OwnedCodexProcess {
    stdin: Writable;
    stdout: Readable;
    exited: Promise<void>;
    terminateAndConfirm(): Promise<boolean>;
}
export const CODEX_MODEL_POLICY = "sova-codex-0.158.0-qwen-text-v2";
/** Mounted tool/instruction policy is separate from the persisted model profile. */
export const CODEX_TOOL_POLICY_SHA256 = "aee39eea7f559a2f1c1b34c2d99818be1bc4e79ea6dba2ca7ec4075c8e34a956";
/** Fixed reviewed script uses task-egress.py and redact-acp.py. Supervisor exit0
 * attests exact random container rm + explicit exists exit1, not mere PID exit.
 * Unclean exits/timeout stay uncertain. Gateway settlement is a separate proof.
 */
export function createRootlessCodexLauncher(launcherPath: string): (input: CodexLaunchInput) => Promise<OwnedCodexProcess> {
    if (!isAbsolute(launcherPath) || !launcherPath.endsWith("/deploy/run-codex.sh"))
        throw Error("Trusted Codex launcher path required");
    return async (input) => {
        if (process.platform !== "linux" || process.getuid?.() === 0 || input.modelPolicyVersion !== CODEX_MODEL_POLICY || input.gatewayUrl !== "http://10.0.2.2:8081/v1" || input.codexHome !== join(resolve(input.profileDir), "codex-home"))
            throw Error("Unqualified Codex rootless policy");
        const env: NodeJS.ProcessEnv = { PATH: "/usr/bin:/bin", HOME: process.env.HOME, USER: process.env.USER, LOGNAME: process.env.LOGNAME,
            AI_HARNESS_SESSION_ID: input.sessionId, AI_HARNESS_GATEWAY_URL: input.gatewayUrl, AI_HARNESS_GATEWAY_TOKEN: input.gatewayToken };
        const child = spawn(launcherPath, ["--profile-dir", input.profileDir, "--workspace", input.workspace, ...(input.imageJobsQualified === true ? ["--image-jobs-qualified"] : [])], { env, stdio: ["pipe", "pipe", "pipe"] });
        // The supervisor redacts; discard all stderr here (no credential/error echo).
        child.stderr.resume();
        let status: number | null | undefined;
        let spawnFailed = false;
        const exited = new Promise<void>(resolve => { child.once("error", () => { spawnFailed = true; resolve(); }); child.once("exit", code => { status = code; resolve(); }); });
        let cleanup: Promise<boolean> | undefined;
        return { stdin: child.stdin, stdout: child.stdout, exited, terminateAndConfirm() {
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
