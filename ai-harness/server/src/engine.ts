import { randomUUID } from "node:crypto";
import { spawn, type ChildProcessWithoutNullStreams } from "node:child_process";
import { constants, type WriteStream } from "node:fs";
import {
  lstat,
  mkdir,
  open,
  realpath,
  rename,
  rm,
  stat,
} from "node:fs/promises";
import { dirname, isAbsolute, join, relative, resolve, sep } from "node:path";
import { Readable, Writable } from "node:stream";
import { setTimeout as delay } from "node:timers/promises";
import * as acp from "@agentclientprotocol/sdk";
import type {
  Engine,
  EngineFactory,
  EngineOptions,
  EngineUpdate,
} from "./contracts.js";

const DELEGATION_GET = "mcode/session/delegation/get";
const DELEGATION_STOP = "mcode/session/delegation/stop";
const DELEGATION_UPDATE = "mcode/session/delegation_update";
export class EngineSettlementError extends Error {
  readonly code = "engine_settlement_unknown";
  constructor() {
    super(
      "Native background delivery settlement is unknown; workspace requires review",
    );
    this.name = "EngineSettlementError";
  }
}

const TERMINAL_CHILD = new Set(["completed", "failed", "stopped"]);
const CHILD_STATES = new Set([
  "queued",
  "running",
  "completed",
  "failed",
  "stopped",
  "unknown",
]);
const MAX_DETAIL = 2048;

function record(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}
function bounded(value: string, max = MAX_DETAIL): string {
  // Keep data plain text; the web client renders this as text, never markup.
  return value.replace(/[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]/g, "").slice(0, max);
}
function within(root: string, path: string): boolean {
  const rel = relative(root, path);
  return (
    rel === "" ||
    (!rel.startsWith(`..${sep}`) && rel !== ".." && !isAbsolute(rel))
  );
}

/** Lexical containment plus every existing component checked, including broken symlinks.
 * Native operations still require PREP's mount sandbox: this check is not a kernel sandbox.
 */
export async function scopedPath(
  workspace: string,
  candidate: string,
  allowMissing = false,
): Promise<string> {
  if (!candidate || candidate.includes("\0"))
    throw new Error("Invalid workspace path");
  const root = await realpath(workspace);
  const lexicalRoot = resolve(workspace);
  let target = resolve(lexicalRoot, candidate);
  if (!within(lexicalRoot, target) && !within(root, target))
    throw new Error("Path is outside workspace");
  if (within(lexicalRoot, target))
    target = resolve(root, relative(lexicalRoot, target));
  let cursor = root;
  const parts = relative(root, target).split(sep).filter(Boolean);
  for (let i = 0; i < parts.length; i++) {
    cursor = join(cursor, parts[i]!);
    try {
      const info = await lstat(cursor);
      if (info.isSymbolicLink())
        throw new Error("Symlink paths are not permitted");
      if (i < parts.length - 1 && !info.isDirectory())
        throw new Error("Invalid path ancestor");
      if (info.isFile() && info.nlink > 1)
        throw new Error("Hard-linked files are not permitted");
    } catch (error) {
      if (allowMissing && record(error) && error.code === "ENOENT") break;
      throw error;
    }
  }
  return target;
}

/** Recognized code actions run inside PREP's container. Parsing limits command
 * admission; it cannot prove the behavior of arbitrary Python/Node/package code.
 * PREP must constrain filesystem, egress, credentials and unreviewed tools.
 */
export function tokenizeWorkspaceShell(source: string): string[][] | null {
  if (!source.trim() || source.length > 32768 || source.includes("\0"))
    return null;
  const commands: string[][] = [];
  let words: string[] = [];
  let word = "";
  let started = false;
  let quote = "";
  const finishWord = () => {
    if (started) words.push(word);
    word = "";
    started = false;
  };
  const finishCommand = () => {
    finishWord();
    if (!words.length) return false;
    commands.push(words);
    words = [];
    return true;
  };
  for (let i = 0; i < source.length; i++) {
    const ch = source[i]!;
    if (quote) {
      if (ch === quote) {
        quote = "";
        continue;
      }
      if (quote === '"' && (ch === "$" || ch === "`")) return null;
      if (ch === "\\" && quote === '"') {
        const next = source[++i];
        if (next === undefined || next === "\n") return null;
        word += next;
      } else word += ch;
      continue;
    }
    if (ch === '"' || ch === "'") {
      quote = ch;
      started = true;
      continue;
    }
    if (ch === "\\") {
      const next = source[++i];
      if (next === undefined || next === "\n") return null;
      word += next;
      started = true;
      continue;
    }
    if (ch === ";" || ch === "\n" || (ch === "&" && source[i + 1] === "&")) {
      if (!finishCommand()) return null;
      if (ch === "&") i++;
      continue;
    }
    if ("|&<>$`(){}#".includes(ch)) return null;
    if (/\s/.test(ch)) {
      finishWord();
      continue;
    }
    word += ch;
    started = true;
  }
  if (quote) return null;
  finishWord();
  if (words.length) commands.push(words);
  return commands.length ? commands : null;
}

export async function workspaceShellPermission(
  workspace: string,
  source: string,
): Promise<boolean> {
  const commands = tokenizeWorkspaceShell(source);
  if (!commands) return false;
  let cwd = resolve(workspace);
  const builtOutputs = new Set<string>();
  for (const words of commands) {
    const executable = words[0]!;
    const args = words.slice(1);
    // Do not accept executable paths outside the reviewed PATH or workspace.
    const command = executable.startsWith("./") ? "./program" : executable;
    if (
      /\b(?:publish|unpublish|push|deploy|send|upload|login|logout|token|auth)\b/i.test(
        args[0] ?? "",
      )
    )
      return false;
    if (command === "cd") {
      if (args.length !== 1 || args[0]!.startsWith("-")) return false;
      cwd = await scopedPath(workspace, resolve(cwd, args[0]!));
      if (!(await stat(cwd)).isDirectory()) return false;
      continue;
    }
    if (command === "pwd") {
      if (args.length) return false;
      continue;
    }
    let inlineIndex = -1;
    if (/^python(?:3(?:\.\d+)?)?$/.test(command)) {
      if (!args.length) return false;
      if (args[0] === "-c") {
        if (args.length < 2) return false;
        inlineIndex = 1;
      } else if (args[0] === "-m") {
        if (
          ![
            "pytest",
            "unittest",
            "compileall",
            "py_compile",
            "pip",
            "build",
          ].includes(args[1] ?? "")
        )
          return false;
        if (
          args[1] === "pip" &&
          !["install", "check", "list", "show"].includes(args[2] ?? "")
        )
          return false;
      } else if (args[0]!.startsWith("-")) return false;
    } else if (
      [
        "node",
        "tsx",
        "tsc",
        "pytest",
        "c++",
        "g++",
        "gcc",
        "clang",
        "clang++",
        "cc",
        "make",
        "cmake",
        "ctest",
        "ninja",
      ].includes(command)
    ) {
      if (["node", "tsx"].includes(command)) {
        if (!args.length) return false;
        if (args[0] === "-e" || args[0] === "--eval") {
          if (args.length < 2) return false;
          inlineIndex = 1;
        } else if (args[0]!.startsWith("-") && args[0] !== "--test")
          return false;
      }
      if (
        command === "cmake" &&
        args.some((arg) =>
          ["-P", "--install", "--workflow", "--open"].includes(arg),
        )
      )
        return false;
      if (
        ["make", "ninja"].includes(command) &&
        args.some((arg) =>
          /^(?:install|uninstall|publish|deploy|push|upload|send)$/.test(arg),
        )
      )
        return false;
    } else if (["npm", "pnpm", "yarn"].includes(command)) {
      if (
        !["test", "build", "install", "ci", "run", "exec"].includes(
          args[0] ?? "",
        ) ||
        args[0] === "exec"
      )
        return false;
      if (
        args[0] === "run" &&
        !/^(?:test|build|check|lint|format|typecheck)(?::[a-zA-Z0-9:_-]+)?$/.test(
          args[1] ?? "",
        )
      )
        return false;
    } else if (["pip", "pip3"].includes(command)) {
      if (!["install", "check", "list", "show"].includes(args[0] ?? ""))
        return false;
    } else if (command === "./program") {
      const program = await scopedPath(
        workspace,
        resolve(cwd, executable),
        true,
      );
      try {
        if (!(await stat(program)).isFile()) return false;
      } catch {
        if (!builtOutputs.has(program)) return false;
      }
    } else return false;
    if (["c++", "g++", "gcc", "clang", "clang++", "cc"].includes(command)) {
      const output = args.indexOf("-o");
      if (output >= 0 && args[output + 1])
        builtOutputs.add(
          await scopedPath(workspace, resolve(cwd, args[output + 1]!), true),
        );
    }
    if (inlineIndex >= 0) {
      // Reject obvious external-write/escape primitives. This is deliberately not
      // claimed to sandbox language execution; the container is that boundary.
      const code = args[inlineIndex]!;
      if (
        /(?:https?:|ssh:|curl\b|wget\b|\b(?:fetch|socket|requests|urllib|subprocess|child_process|env|environ|eval|exec|publish|upload|send|connect)\b|(?:^|["'])\.\.[/\\]|["']\/(?:etc|proc|sys|dev|home|root|tmp)\b)/i.test(
          code,
        )
      )
        return false;
    }
    for (let index = 0; index < args.length; index++) {
      if (index === inlineIndex) continue;
      const arg = args[index]!;
      if (
        arg.includes("\0") ||
        /^~/.test(arg) ||
        /(?:^|[/\\])\.\.(?:[/\\]|$)/.test(arg)
      )
        return false;
      if (
        /^(?:--prefix|--cache|--global|-g|--user|--target|--root|--userconfig|--globalconfig|--registry|--index-url|--extra-index-url|--trusted-host|--exec|--require|--import|--loader)(?:=|$)/.test(
          arg,
        )
      )
        return false;
      if (/^[A-Za-z_][A-Za-z0-9_]*=/.test(arg)) return false;
      if (/^[a-zA-Z][a-zA-Z0-9+.-]*:\/\//.test(arg) || arg.startsWith("git@"))
        return false;
      let pathArg = arg;
      const equal = arg.indexOf("=");
      if (equal >= 0) pathArg = arg.slice(equal + 1);
      if (/^-[ILo]/.test(pathArg) && pathArg.length > 2)
        pathArg = pathArg.slice(2);
      if (
        isAbsolute(pathArg) ||
        (!pathArg.startsWith("-") && !/^[0-9]+$/.test(pathArg))
      ) {
        await scopedPath(workspace, resolve(cwd, pathArg), true);
      }
    }
  }
  return true;
}

/** Reviewed image assets are container-only paths. PREP mounts these roots
 * read-only and excludes host links; the server never opens them on its host. */
export const READ_ONLY_ASSET_ROOTS = [
  "/opt/ai-harness/skills",
  "/opt/ai-harness/tools",
] as const;
export function isReviewedAssetPath(candidate: string): boolean {
  if (
    !isAbsolute(candidate) ||
    candidate.includes("\0") ||
    candidate.split("/").includes("..")
  )
    return false;
  const path = resolve(candidate);
  return READ_ONLY_ASSET_ROOTS.some((root) => within(root, path));
}

/** A narrow autonomous policy, not an attempt to classify arbitrary shell source.
 * Unknown tools/commands, background shell, external writes and publication fail closed.
 */
export async function workspacePermission(
  workspace: string,
  request: acp.RequestPermissionRequest,
): Promise<boolean> {
  const tool = request.toolCall;
  // name is supplied by pinned MiniMax; title is descriptive prose and is not authority.
  const name = tool.name;
  const input = tool.rawInput;
  if (typeof name !== "string" || !record(input)) return false;
  try {
    const readOnly = ["read", "grep", "glob"].includes(name);
    for (const location of tool.locations ?? []) {
      if (readOnly && isReviewedAssetPath(location.path)) continue;
      await scopedPath(workspace, location.path, true);
    }
    if (["read", "write", "edit", "grep", "glob"].includes(name)) {
      const expected = name === "edit" ? input.file_path : input.path;
      if (expected === undefined && (name === "grep" || name === "glob"))
        return true;
      if (typeof expected !== "string") return false;
      if (readOnly && isReviewedAssetPath(expected)) return true;
      await scopedPath(workspace, expected, name === "write");
      return true;
    }
    if (name === "bash") {
      if (input.run_in_background === true || typeof input.command !== "string")
        return false;
      // Admit recognized workspace code/build actions; PREP enforces process/network isolation.
      return await workspaceShellPermission(workspace, input.command);
    }
    return false;
  } catch {
    return false;
  }
}

/** Pinned MiniMax ae65651: local-runtime/src/permissions/rules.ts writes this
 * v1 format to MINIMAX_DATA_DIR/permission.json; native local tools are untagged
 * and pass the permission gate (agent-core/src/tools/bind.ts). Explicit ask rules
 * precede native bash fast-allow. This is NOT a sandbox: PREP must disable all
 * unreviewed MCP/Matrix/plugin tools, whose built-in provenance may skip this gate.
 */
export const NATIVE_PERMISSION_POLICY = {
  allow: [],
  ask: ["read", "write", "edit", "grep", "glob", "bash"],
  deny: [
    "website_deploy",
    "mavis",
    "request_feature_enable",
    "code_review",
    "memory",
    "browser",
    "browser_inspect",
    "browser_navigate",
    "browser_click",
    "browser_type",
    "browser_press_key",
    "browser_scroll",
    "browser_hover",
    "browser_wait_for",
    "browser_get_dom",
    "browser_screenshot",
    "browser_paste",
    "browser_verify_text",
    "browser_inspect_editable_targets",
  ],
} as const;

export async function seedNativePermissionPolicy(
  profileDir: string,
): Promise<void> {
  const profile = await lstat(profileDir);
  if (
    !profile.isDirectory() ||
    profile.isSymbolicLink() ||
    (process.getuid && profile.uid !== process.getuid())
  ) {
    throw new Error("Engine profile must be an owned real directory");
  }
  const destination = join(profileDir, "permission.json");
  try {
    const existing = await lstat(destination);
    if (
      !existing.isFile() ||
      existing.isSymbolicLink() ||
      existing.nlink !== 1 ||
      (process.getuid && existing.uid !== process.getuid())
    ) {
      throw new Error("Unsafe native permission policy path");
    }
  } catch (error) {
    if (!record(error) || error.code !== "ENOENT") throw error;
  }
  const temporary = join(profileDir, `.permission-${randomUUID()}.tmp`);
  const handle = await open(
    temporary,
    constants.O_CREAT |
      constants.O_EXCL |
      constants.O_WRONLY |
      constants.O_NOFOLLOW,
    0o600,
  );
  try {
    await handle.writeFile(JSON.stringify(NATIVE_PERMISSION_POLICY) + "\n");
    await handle.sync();
    await handle.close();
    await rename(temporary, destination);
  } catch (error) {
    await handle.close().catch(() => undefined);
    await rm(temporary, { force: true });
    throw error;
  }
}

interface ChildSnapshot {
  schemaVersion: 1;
  rootSessionId: string;
  members: {
    sessionId: string;
    parentSessionId: string;
    status: string;
    task?: string;
    agentName?: string;
    backgroundTaskId?: string;
  }[];
}
function snapshot(value: unknown, nativeId: string): ChildSnapshot {
  if (
    !record(value) ||
    value.schemaVersion !== 1 ||
    value.rootSessionId !== nativeId ||
    !Array.isArray(value.members)
  ) {
    throw new Error("Engine delegation settlement is unknown");
  }
  for (const member of value.members) {
    if (
      !record(member) ||
      typeof member.sessionId !== "string" ||
      typeof member.parentSessionId !== "string" ||
      typeof member.status !== "string" ||
      !CHILD_STATES.has(member.status)
    ) {
      throw new Error("Engine delegation settlement is unknown");
    }
  }
  return value as unknown as ChildSnapshot;
}

class AcpEngine implements Engine {
  private child?: ChildProcessWithoutNullStreams;
  private connection?: acp.ClientSideConnection;
  private stderr?: WriteStream;
  private nativeId?: string;
  private initialized = false;
  private restoring = true;
  private cancelled = false;
  private closing = false;
  private active = false;
  private supportsClose = false;
  private compactions = new Set<string>();
  private childStates = new Map<string, string>();
  private tools = new Map<string, { label: string; kind: string }>();
  private exitPromise?: Promise<void>;
  private exitStatus?: {
    code: number | null;
    signal: NodeJS.Signals | null;
    spawnError?: boolean;
  };
  private startPromise?: Promise<void>;
  private closePromise?: Promise<void>;
  private startedWork = false;
  private settled = true;
  private textTail = "";
  private backgroundObserved = false;

  constructor(private readonly options: EngineOptions) {
    this.nativeId = options.nativeSessionId;
  }

  start(): Promise<void> {
    if (this.closing) return Promise.reject(new Error("Engine is closed"));
    this.startPromise ??= this.initialize();
    return this.startPromise;
  }

  private async initialize(): Promise<void> {
    const o = this.options;
    for (const path of [o.launcher, o.profileDir, o.workspace, o.stderrPath]) {
      if (!isAbsolute(path))
        throw new Error("Engine launcher and storage paths must be absolute");
    }
    if (!/^[A-Za-z0-9_-]{32,256}$/.test(o.gatewayToken))
      throw new Error("Invalid runner gateway token");
    const gateway = new URL(o.gatewayUrl);
    if (
      !["http:", "https:"].includes(gateway.protocol) ||
      gateway.username ||
      gateway.password ||
      gateway.search ||
      gateway.hash ||
      !gateway.pathname.endsWith("/v1")
    ) {
      throw new Error("Invalid engine gateway URL");
    }
    await mkdir(o.profileDir, { recursive: true, mode: 0o700 });
    await seedNativePermissionPolicy(o.profileDir);
    await mkdir(dirname(o.stderrPath), { recursive: true, mode: 0o700 });
    await realpath(o.workspace);
    const logHandle = await open(
      o.stderrPath,
      constants.O_WRONLY |
        constants.O_APPEND |
        constants.O_CREAT |
        constants.O_NOFOLLOW,
      0o600,
    );
    if (this.closing) {
      await logHandle.close();
      throw new Error("Engine closed during startup");
    }
    this.stderr = logHandle.createWriteStream({ autoClose: true });
    // Do not inherit credentials, proxies, NODE_OPTIONS, auth sockets or the upstream key path.
    const env: NodeJS.ProcessEnv = {
      PATH: `${dirname(process.execPath)}:/usr/local/bin:/usr/bin:/bin`,
      LANG: "C.UTF-8",
      HOME: process.env.HOME ?? o.profileDir,
      AI_HARNESS_GATEWAY_URL: o.gatewayUrl,
      AI_HARNESS_GATEWAY_TOKEN: o.gatewayToken,
      AI_HARNESS_SESSION_ID: o.sessionId,
    };
    // Rootless Podman needs its ordinary user runtime directory; this is not a secret.
    if (process.env.XDG_RUNTIME_DIR)
      env.XDG_RUNTIME_DIR = process.env.XDG_RUNTIME_DIR;
    this.child = spawn(
      o.launcher,
      ["--profile-dir", o.profileDir, "--workspace", o.workspace],
      {
        cwd: o.workspace,
        env,
        stdio: ["pipe", "pipe", "pipe"],
        shell: false,
      },
    );
    const child = this.child;
    // Redact the one secret deliberately sent to the launcher, including across stderr chunks.
    let tail = "";
    child.stderr.setEncoding("utf8");
    child.stderr.on("data", (part: string) => {
      const data = tail + part;
      const keep = Math.max(0, o.gatewayToken.length - 1);
      // Replace before splitting so occurrences across chunks are retained and redacted.
      const safe = data.replaceAll(o.gatewayToken, "[REDACTED]");
      const cutoff = Math.max(0, safe.length - keep);
      this.stderr?.write(safe.slice(0, cutoff));
      tail = safe.slice(cutoff);
    });
    child.stderr.on("end", () => {
      this.stderr?.end(tail.replaceAll(o.gatewayToken, "[REDACTED]"));
      tail = "";
    });
    this.stderr.on("error", () => {
      child.kill("SIGTERM");
    });
    // Attach rejection handlers immediately; launch failure must not be an unhandled rejection.
    this.exitPromise = new Promise<void>((resolveExit) => {
      let done = false;
      const exited = () => {
        if (done) return;
        done = true;
        o.onExit?.();
        resolveExit();
      };
      child.once("close", (code, signal) => {
        this.exitStatus = { code, signal };
        exited();
      });
      child.once("error", () => {
        this.exitStatus = { code: null, signal: null, spawnError: true };
        exited();
      });
    });
    await new Promise<void>((resolveSpawn, reject) => {
      child.once("spawn", resolveSpawn);
      child.once("error", () =>
        reject(new Error("Engine launcher could not start")),
      );
    });
    const connection = new acp.ClientSideConnection(
      () => ({
        requestPermission: (params) => this.permission(params),
        sessionUpdate: (params) => this.update(params),
        extNotification: (method, params) => this.extension(method, params),
      }),
      acp.ndJsonStream(
        Writable.toWeb(child.stdin),
        Readable.toWeb(child.stdout) as unknown as Parameters<
          typeof acp.ndJsonStream
        >[1],
      ),
    );
    this.connection = connection;
    try {
      const init = await deadline(
        connection.initialize({
          protocolVersion: acp.PROTOCOL_VERSION,
          clientInfo: { name: "ai-harness", version: "0.0.1" },
          clientCapabilities: {
            fs: { readTextFile: false, writeTextFile: false },
            terminal: false,
            _meta: {
              "minimax-code/extensions": { version: 1, notifications: true },
            },
          },
        }),
        30_000,
        "Engine initialization timed out",
      );
      if (init.protocolVersion !== acp.PROTOCOL_VERSION)
        throw new Error("Unsupported ACP protocol version");
      const extensions = init._meta?.["minimax-code/extensions"];
      const methods =
        record(extensions) && Array.isArray(extensions.methods)
          ? extensions.methods
          : [];
      if (
        !methods.includes(DELEGATION_GET) ||
        !methods.includes(DELEGATION_STOP)
      ) {
        throw new Error(
          "Engine lacks required background delegation settlement capabilities",
        );
      }
      this.supportsClose =
        init.agentCapabilities?.sessionCapabilities?.close !== undefined;
      const params = { cwd: o.workspace, mcpServers: [] };
      if (this.nativeId) {
        if (init.agentCapabilities?.sessionCapabilities?.resume !== undefined) {
          await deadline(
            connection.resumeSession({ ...params, sessionId: this.nativeId }),
            30_000,
            "Engine resume timed out",
          );
        } else if (init.agentCapabilities?.loadSession) {
          await deadline(
            connection.loadSession({ ...params, sessionId: this.nativeId }),
            30_000,
            "Engine load timed out",
          );
        } else {
          throw new Error(
            "Engine cannot safely restore the saved native session",
          );
        }
      } else {
        const session = await deadline(
          connection.newSession(params),
          30_000,
          "Engine session creation timed out",
        );
        if (
          !session.sessionId ||
          session.sessionId.length > 512 ||
          session.sessionId.includes(o.gatewayToken)
        )
          throw new Error("Invalid native session ID");
        this.nativeId = session.sessionId;
        o.onNativeSessionId(session.sessionId);
      }
      // This setting is process-wide in pinned MiniMax; each chat has its own process.
      // Never allow a saved profile's auto/bypass mode to bypass the scoped permission client.
      const policy = await deadline(
        connection.setSessionConfigOption({
          sessionId: this.nativeId!,
          configId: "permissionMode",
          value: "default",
        }),
        30_000,
        "Engine permission policy configuration timed out",
      );
      if (
        !policy.configOptions.some(
          (option) =>
            option.id === "permissionMode" &&
            option.type === "select" &&
            option.currentValue === "default",
        )
      ) {
        throw new Error("Engine did not confirm default permission mode");
      }
      this.restoring = false;
      this.initialized = true;
    } catch (error) {
      await this.close().catch(() => undefined);
      throw error;
    }
  }

  private emit(update: EngineUpdate): void {
    // Ephemeral runner credentials are never durable event/message content.
    this.options.onUpdate(
      JSON.parse(
        JSON.stringify(update).replaceAll(
          this.options.gatewayToken,
          "[REDACTED]",
        ),
      ) as EngineUpdate,
    );
  }

  private projectText(text: string): void {
    const safe = (this.textTail + text).replaceAll(
      this.options.gatewayToken,
      "[REDACTED]",
    );
    const cutoff = Math.max(
      0,
      safe.length - this.options.gatewayToken.length + 1,
    );
    if (cutoff) this.emit({ type: "text", text: safe.slice(0, cutoff) });
    this.textTail = safe.slice(cutoff);
  }

  private async permission(
    params: acp.RequestPermissionRequest,
  ): Promise<acp.RequestPermissionResponse> {
    if (
      this.cancelled ||
      this.closing ||
      this.restoring ||
      params.sessionId !== this.nativeId
    ) {
      return { outcome: { outcome: "cancelled" } };
    }
    const allowed = await workspacePermission(this.options.workspace, params);
    const option = params.options.find(
      (candidate) =>
        candidate.kind === (allowed ? "allow_once" : "reject_once"),
    );
    this.emit({
      type: "progress",
      kind: "permission",
      label: allowed
        ? "Workspace operation authorized"
        : "Operation denied by workspace policy",
    });
    if (!option || this.cancelled || this.closing)
      return { outcome: { outcome: "cancelled" } };
    return { outcome: { outcome: "selected", optionId: option.optionId } };
  }

  private update(params: acp.SessionNotification): void {
    // session/load replays history; our durable original visible history already owns it.
    if (this.restoring || params.sessionId !== this.nativeId || this.closing)
      return;
    const update = params.update;
    if (update.sessionUpdate === "agent_message_chunk") {
      if (update.content.type === "text") this.projectText(update.content.text);
    } else if (
      update.sessionUpdate === "tool_call" ||
      update.sessionUpdate === "tool_call_update"
    ) {
      const known = this.tools.get(update.toolCallId);
      const label = bounded(update.title ?? known?.label ?? "Tool", 160);
      const kind = update.kind ?? known?.kind ?? "other";
      if (label === "bash") {
        const raw = update.rawOutput;
        const rendered =
          typeof raw === "string"
            ? raw
            : record(raw)
              ? JSON.stringify(raw)
              : "";
        if (
          rendered.includes("<bash_background") ||
          (record(raw) &&
            record(raw.details) &&
            typeof raw.details.task_id === "string")
        )
          this.backgroundObserved = true;
      }
      if (update.status !== "completed" && update.status !== "failed")
        this.tools.set(update.toolCallId, { label, kind });
      else this.tools.delete(update.toolCallId);
      const detail = (update.content ?? [])
        .flatMap((part) =>
          part.type === "content" && part.content.type === "text"
            ? [part.content.text]
            : [],
        )
        .join("\n");
      this.emit({
        type: "progress",
        kind: "tool",
        label: `${label}: ${update.status ?? "pending"}`,
        taskId: bounded(update.toolCallId, 200),
        ...(detail ? { detail: bounded(detail) } : {}),
      });
    } else if (update.sessionUpdate === "usage_update") {
      if (
        Number.isSafeInteger(update.used) &&
        update.used >= 0 &&
        update.size === 480000
      ) {
        this.emit({
          type: "context",
          used: update.used,
          estimated: true,
          source: "acp:usage_update:context_snapshot",
        });
      } else {
        this.emit({
          type: "context",
          used: null,
          estimated: true,
          source: "acp:usage_update:unverified_capacity",
        });
      }
    } else if (update.sessionUpdate === "plan") {
      this.emit({
        type: "progress",
        kind: "plan",
        label: "Plan updated",
        detail: bounded(
          update.entries
            .map((entry) => `${entry.status}: ${entry.content}`)
            .join("\n"),
        ),
      });
    }
    // agent_thought_chunk is deliberately not exposed as inferred work/progress.
    // Explicit compaction lifecycle comes only from PREP reviewed custom notifications.
  }

  private extension(method: string, params: Record<string, unknown>): void {
    if (
      params.sessionId !== this.nativeId ||
      this.restoring ||
      this.closing ||
      !this.nativeId
    )
      return;
    if (method === "mcode/session/compaction_update") {
      const id = params.compactionId;
      const status = params.status;
      if (
        params.schemaVersion !== 1 ||
        params.estimated !== true ||
        typeof id !== "string" ||
        !/^[A-Za-z0-9][A-Za-z0-9_.:-]{0,199}$/.test(id) ||
        !["start", "completed", "failed"].includes(String(status))
      )
        return;
      for (const field of ["tokensBefore", "tokensAfter"]) {
        const value = params[field];
        if (
          value !== undefined &&
          (typeof value !== "number" ||
            !Number.isSafeInteger(value) ||
            value < 0)
        )
          return;
      }
      if (
        Object.keys(params).some(
          (key) =>
            ![
              "schemaVersion",
              "sessionId",
              "compactionId",
              "status",
              "estimated",
              "tokensBefore",
              "tokensAfter",
            ].includes(key),
        )
      )
        return;
      const key = `${id}:${status}`;
      if (this.compactions.has(key)) return;
      this.compactions.add(key);
      this.emit({
        type: "compaction",
        compactionId: id,
        status: status as "start" | "completed" | "failed",
        ...(params.tokensBefore === undefined
          ? {}
          : { tokensBefore: params.tokensBefore as number }),
        ...(params.tokensAfter === undefined
          ? {}
          : { tokensAfter: params.tokensAfter as number }),
      });
      return;
    }
    if (method !== DELEGATION_UPDATE) return;
    try {
      this.projectChildren(snapshot(params.snapshot, this.nativeId));
    } catch {
      /* A fresh required get decides settlement; malformed notifications cannot settle it. */
    }
  }

  private projectChildren(state: ChildSnapshot): void {
    for (const child of state.members) {
      if (
        typeof child.backgroundTaskId === "string" &&
        child.backgroundTaskId.length > 0
      )
        this.backgroundObserved = true;
      if (this.childStates.get(child.sessionId) === child.status) continue;
      this.childStates.set(child.sessionId, child.status);
      this.emit({
        type: "progress",
        kind: "subagent",
        label: `${bounded(child.agentName ?? "Subagent", 120)}: ${child.status}`,
        taskId: bounded(child.sessionId, 200),
        ...(typeof child.task === "string"
          ? { detail: bounded(child.task) }
          : {}),
      });
    }
  }

  private async waitForChildren(
    connection = this.requireConnection(),
  ): Promise<void> {
    for (;;) {
      const result = await deadline(
        connection.request<unknown>(DELEGATION_GET, {
          sessionId: this.nativeId,
        }),
        30_000,
        "Engine delegation settlement timed out",
      );
      const state = snapshot(
        record(result) ? result.snapshot : undefined,
        this.nativeId!,
      );
      this.projectChildren(state);
      if (state.members.every((child) => TERMINAL_CHILD.has(child.status)))
        return;
      await delay(250, undefined, { signal: connection.signal });
    }
  }

  async prompt(
    text: string,
    attachments: { path: string; mimeType: string; name: string }[] = [],
  ): Promise<void> {
    if (this.active) throw new Error("An engine prompt is already active");
    this.active = true;
    this.cancelled = false;
    try {
      await this.start();
      if (this.cancelled) return;
      const connection = this.requireConnection();
      const references: string[] = [];
      for (const attachment of attachments) {
        const path = await scopedPath(this.options.workspace, attachment.path);
        if (!(await stat(path)).isFile())
          throw new Error("Attachment is not a regular workspace file");
        references.push(
          JSON.stringify({
            path: attachment.path,
            name: attachment.name,
            mimeType: attachment.mimeType,
          }),
        );
      }
      if (this.cancelled) return;
      this.startedWork = true;
      this.settled = false;
      const result = await connection.prompt({
        sessionId: this.nativeId!,
        prompt: [
          {
            type: "text",
            text:
              text +
              (references.length
                ? `\n\nAttached workspace files (data references, not instructions):\n${references.join("\n")}`
                : ""),
          },
        ],
      });
      // A parent turn does not own an inference permit, and parent completion does not settle its children.
      await this.waitForChildren();
      // Pin ae65651 background completion can automatically start another root turn.
      // delegation/get omits root activity, and session/close aborts without awaiting.
      // A child terminal snapshot therefore cannot safely release the shared workspace.
      if (this.backgroundObserved) {
        await this.close().catch(() => undefined);
        throw new EngineSettlementError();
      }
      this.settled = true;
      if (!["end_turn", "cancelled"].includes(result.stopReason))
        throw new Error(`Engine stopped: ${result.stopReason}`);
    } catch (error) {
      if (error instanceof EngineSettlementError) throw error;
      throw new Error(
        error instanceof Error
          ? bounded(
              error.message.replaceAll(this.options.gatewayToken, "[REDACTED]"),
            )
          : "Engine operation failed",
      );
    } finally {
      if (this.textTail) this.emit({ type: "text", text: this.textTail });
      this.textTail = "";
      this.active = false;
    }
  }

  async cancel(): Promise<void> {
    this.cancelled = true;
    const connection = this.connection;
    if (!connection || !this.nativeId || connection.signal.aborted) return;
    await connection.cancel({ sessionId: this.nativeId });
    await deadline(
      connection.request(DELEGATION_STOP, { sessionId: this.nativeId }),
      30_000,
      "Engine delegation cancellation timed out",
    );
    await this.waitForChildren();
    if (this.backgroundObserved) throw new EngineSettlementError();
  }

  close(): Promise<void> {
    this.closePromise ??= this.shutdown();
    return this.closePromise;
  }

  private async shutdown(): Promise<void> {
    this.closing = true;
    const child = this.child;
    if (!child) {
      this.stderr?.end();
      return;
    }
    const connection = this.connection;
    let settlementError: Error | undefined = this.backgroundObserved
      ? new EngineSettlementError()
      : undefined;
    if (
      this.startedWork &&
      !this.settled &&
      (!connection || connection.signal.aborted)
    ) {
      settlementError = new Error(
        "Engine workspace settlement is unknown after transport loss",
      );
    }
    if (connection && !connection.signal.aborted && this.nativeId) {
      try {
        await deadline(
          (async () => {
            await connection.cancel({ sessionId: this.nativeId! });
            await connection.request(DELEGATION_STOP, {
              sessionId: this.nativeId,
            });
            if (this.startedWork) {
              await this.waitForChildren(connection);
              if (this.backgroundObserved)
                settlementError = new EngineSettlementError();
              else this.settled = true;
            }
            if (this.supportsClose)
              await connection.closeSession({ sessionId: this.nativeId! });
          })(),
          this.options.shutdownTimeouts?.acpMs ?? 5_000,
          "Engine shutdown settlement timed out",
        );
      } catch {
        if (this.startedWork && !this.settled)
          settlementError = new Error(
            "Engine workspace settlement is unknown after cancellation",
          );
      }
    }
    if (child.exitCode === null && child.signalCode === null)
      child.kill("SIGTERM");
    child.stdin.end();
    try {
      await deadline(
        this.exitPromise!,
        this.options.shutdownTimeouts?.launcherMs ?? 45_000,
        "Engine launcher cleanup did not finish",
      );
    } catch {
      child.kill("SIGKILL");
      await deadline(
        this.exitPromise!,
        this.options.shutdownTimeouts?.killMs ?? 5_000,
        "Engine process settlement unknown",
      );
    }
    this.stderr?.end();
    this.initialized = false;
    // PREP's launcher contract reserves exit 0 for verified exact-container cleanup.
    // A socket close, nonzero status or signal exit provides no such evidence.
    if (
      !this.exitStatus ||
      this.exitStatus.code !== 0 ||
      this.exitStatus.signal !== null ||
      this.exitStatus.spawnError
    ) {
      throw new Error(
        "Engine launcher cleanup is unconfirmed; workspace settlement is unknown",
      );
    }
    // A killed ACP pipe is not evidence that container grandchildren stopped.
    if (settlementError) throw settlementError;
  }

  private requireConnection(): acp.ClientSideConnection {
    if (
      !this.connection ||
      !this.initialized ||
      this.connection.signal.aborted ||
      this.closing
    )
      throw new Error("Engine is not connected");
    return this.connection;
  }
}

async function deadline<T>(
  operation: Promise<T>,
  ms: number,
  message: string,
): Promise<T> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  try {
    return await Promise.race([
      operation,
      new Promise<never>((_, reject) => {
        timer = setTimeout(() => reject(new Error(message)), ms);
        timer.unref();
      }),
    ]);
  } finally {
    if (timer) clearTimeout(timer);
  }
}
export const createEngine: EngineFactory = (options) => new AcpEngine(options);
