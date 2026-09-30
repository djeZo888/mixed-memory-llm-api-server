import { TIME_ZONE, clockInstruction } from "./locale.js";
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
import { userInfo } from "node:os";
import { Readable, Writable } from "node:stream";
import { setTimeout as delay } from "node:timers/promises";
import * as acp from "@agentclientprotocol/sdk";
import {
  TRUSTED_BROWSER_INSTRUCTION,
  reviewedToolPermission,
  REVIEWED_POLICY_ASK,
  REVIEWED_POLICY_DENY,
} from "./policy.js";
import type {
  Engine,
  EngineFactory,
  EngineOptions,
  EngineUpdate,
  MessageChannel,
  SubagentSummary,
} from "./contracts.js";

const DELEGATION_GET = "mcode/session/delegation/get";
const DELEGATION_STOP = "mcode/session/delegation/stop";
const DELEGATION_UPDATE = "mcode/session/delegation_update";
export class EngineSettlementError extends Error {
  readonly code = "engine_settlement_unknown";
  constructor() {
    super("Native completion settlement is unknown; workspace requires review");
    this.name = "EngineSettlementError";
  }
}

const MESSAGE_BOUNDARY = "mcode/session/message_update";
const SETTLEMENT_GET = "mcode/session/settlement/get";
const SETTLEMENT_META = "minimax-code/settlement";
interface SettlementReceipt {
  schemaVersion: 1;
  instanceId: string;
  rootSessionId: string;
  runId: string | null;
  exhaustive: boolean;
  state: "running" | "settled" | "cancelled" | "unknown";
  rootTurnIds: string[];
  reasons: string[];
}
export class EngineCleanupError extends Error {
  readonly code = "engine_cleanup_unknown";
  constructor() {
    super(
      "Engine launcher cleanup is unconfirmed; workspace settlement is unknown",
    );
    this.name = "EngineCleanupError";
  }
}
function nativeId(value: unknown): value is string {
  return (
    typeof value === "string" &&
    value.length > 0 &&
    value.length <= 512 &&
    !/[\x00-\x20\x7f]/.test(value)
  );
}
function parseSettlement(value: unknown): SettlementReceipt {
  if (
    !record(value) ||
    Object.keys(value).some(
      (key) =>
        ![
          "schemaVersion",
          "instanceId",
          "rootSessionId",
          "runId",
          "exhaustive",
          "state",
          "rootTurnIds",
          "reasons",
        ].includes(key),
    ) ||
    value.schemaVersion !== 1 ||
    typeof value.instanceId !== "string" ||
    !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(
      value.instanceId,
    ) ||
    !nativeId(value.rootSessionId) ||
    !(value.runId === null || nativeId(value.runId)) ||
    typeof value.exhaustive !== "boolean" ||
    !["running", "settled", "cancelled", "unknown"].includes(
      String(value.state),
    ) ||
    !Array.isArray(value.rootTurnIds) ||
    value.rootTurnIds.length > 10000 ||
    !value.rootTurnIds.every(nativeId) ||
    new Set(value.rootTurnIds).size !== value.rootTurnIds.length ||
    !Array.isArray(value.reasons) ||
    value.reasons.length > 1000 ||
    !value.reasons.every(
      (reason) =>
        typeof reason === "string" && reason.length > 0 && reason.length <= 512,
    ) ||
    // Stop can exhaustively cancel an allocated run before its first root turn
    // is admitted. Successful settlement still requires the real initial turn.
    (value.runId === null
      ? value.rootTurnIds.length !== 0
      : value.rootTurnIds.length === 0
        ? value.state !== "cancelled" || !value.exhaustive
        : value.rootTurnIds[0] !== value.runId)
  )
    throw new EngineSettlementError();
  return value as unknown as SettlementReceipt;
}
function idleReceipt(receipt: SettlementReceipt): boolean {
  return (
    receipt.runId !== null &&
    receipt.exhaustive &&
    receipt.reasons.length === 0 &&
    ["settled", "cancelled"].includes(receipt.state)
  );
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

/** Pinned ae65651 builtin-defs.ts LocalBashToolDef has no selectable cwd.
 * local-pi-tools.ts binds it to workspaceRoot. This is schema admission, not a
 * script sandbox: shell programs run within PREP's reviewed container boundary.
 */
export function nativeShellInput(input: unknown): boolean {
  return (
    record(input) &&
    Object.keys(input).every((key) =>
      ["command", "timeout", "run_in_background"].includes(key),
    ) &&
    typeof input.command === "string" &&
    !input.command.includes("\0") &&
    (input.timeout === undefined ||
      (typeof input.timeout === "number" &&
        Number.isFinite(input.timeout) &&
        input.timeout <= 2_147_483)) &&
    (input.run_in_background === undefined ||
      typeof input.run_in_background === "boolean")
  );
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

/** Scoped native tool admission; arbitrary shell source is contained by PREP, not classified here. */
export async function workspacePermission(
  workspace: string,
  request: acp.RequestPermissionRequest,
): Promise<boolean> {
  const reviewed = await reviewedToolPermission(workspace, request, scopedPath);
  if (reviewed !== undefined) return reviewed;
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
    if (name === "bash") return nativeShellInput(input);

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
  ask: [
    "read",
    "write",
    "edit",
    "grep",
    "glob",
    "bash",
    ...REVIEWED_POLICY_ASK,
  ],
  deny: [...REVIEWED_POLICY_DENY],
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
  complete?: boolean;
  rootSessionId: string;
  members: {
    sessionId: string;
    parentSessionId: string;
    status: string;
    task?: string;
    agentName?: string;
    backgroundTaskId?: string;
    createdAtMs?: number;
    updatedAtMs?: number;
  }[];
}
function snapshot(value: unknown, rootId: string): ChildSnapshot {
  if (
    !record(value) ||
    value.schemaVersion !== 1 ||
    value.rootSessionId !== rootId ||
    !Array.isArray(value.members) ||
    value.members.length > 10000 ||
    (value.complete !== undefined && typeof value.complete !== "boolean")
  ) {
    throw new Error("Engine delegation settlement is unknown");
  }
  for (const member of value.members) {
    if (
      !record(member) ||
      !nativeId(member.sessionId) ||
      !nativeId(member.parentSessionId) ||
      typeof member.status !== "string" ||
      !CHILD_STATES.has(member.status)
    ) {
      throw new Error("Engine delegation settlement is unknown");
    }
  }
  const members = value.members as ChildSnapshot["members"];
  const identities = new Set(members.map((m) => m.sessionId));
  if (identities.size !== members.length || identities.has(rootId))
    throw new Error("Invalid child identities");
  const parents = new Map(members.map((m) => [m.sessionId, m.parentSessionId]));
  const rooted = new Set([rootId]);
  for (const member of members) {
    const seen = new Set<string>();
    let cursor = member.sessionId;
    while (!rooted.has(cursor)) {
      if (seen.has(cursor) || !parents.has(cursor))
        throw new Error("Incomplete child tree");
      seen.add(cursor);
      cursor = parents.get(cursor)!;
    }
    for (const id of seen) rooted.add(id);
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
  private childBaseline?: Map<string, string>;
  private childRunMembers = new Set<string>();
  private childBaselineComplete = false;
  private tools = new Map<
    string,
    Extract<EngineUpdate, { type: "progress" }>
  >();
  private textTails = new Map<
    string,
    {
      text: string;
      nativeMessageId?: string;
      channel: MessageChannel;
      phaseSource: string;
    }
  >();
  private visibleMessages = new Set<string>();
  private boundaries = new Map<
    string,
    {
      turnId: string;
      kind: string | null;
      finishReason: string | null;
      status: "streaming" | "completed";
    }
  >();
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
  private backgroundObserved = false;
  private receipt?: SettlementReceipt;
  private rootIdentity?: string;
  private instanceIdentity?: string;
  private newSession = false;
  private requestedTermination = false;
  private seenRuns = new Set<string>();

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
    // The host launcher/Podman needs the service account home. Only the launcher
    // sets the container's private HOME; ambient HOME is not account authority.
    const account = userInfo();
    const uid = process.getuid?.();
    if (
      uid === undefined ||
      uid === 0 ||
      account.uid !== uid ||
      process.geteuid?.() !== uid ||
      !isAbsolute(account.homedir)
    )
      throw new Error("Engine launcher requires an ordinary service account");
    const hostHome = await realpath(account.homedir);
    const hostHomeInfo = await stat(hostHome);
    if (!hostHomeInfo.isDirectory() || hostHomeInfo.uid !== uid)
      throw new Error(
        "Engine launcher home must be an owned existing directory",
      );
    await mkdir(o.profileDir, { recursive: true, mode: 0o700 });
    const profileInfo = await lstat(o.profileDir);
    if (!profileInfo.isDirectory() || profileInfo.isSymbolicLink())
      throw new Error("Unsafe engine profile directory");
    const nativeState = join(o.profileDir, "state");
    await mkdir(nativeState, { recursive: true, mode: 0o700 });
    await seedNativePermissionPolicy(nativeState);
    const nativeHome = join(nativeState, "home");
    await mkdir(nativeHome, { recursive: true, mode: 0o700 });
    const homeInfo = await lstat(nativeHome);
    if (
      !homeInfo.isDirectory() ||
      homeInfo.isSymbolicLink() ||
      (process.getuid && homeInfo.uid !== process.getuid())
    )
      throw new Error("Unsafe engine home directory");
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
      TZ: TIME_ZONE,
      HOME: hostHome,
      AI_HARNESS_GATEWAY_URL: o.gatewayUrl,
      AI_HARNESS_GATEWAY_TOKEN: o.gatewayToken,
      AI_HARNESS_SESSION_ID: o.sessionId,
    };
    // Rootless Podman needs its ordinary user runtime directory; this is not a secret.
    if (process.env.XDG_RUNTIME_DIR)
      env.XDG_RUNTIME_DIR = process.env.XDG_RUNTIME_DIR;
    while (o.dispatchHeld?.() && !this.closing && !this.cancelled)
      await new Promise<void>(resolve => setTimeout(resolve, 50));
    if (this.closing || this.cancelled) throw new Error("Engine launch cancelled while frozen");
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
          clientInfo: { name: "ai-harness", version: "0.0.2" },
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
        !methods.includes(DELEGATION_STOP) ||
        !methods.includes(SETTLEMENT_GET)
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
        this.newSession = true;
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
      const initial = await this.readSettlement(connection);
      this.instanceIdentity = initial.instanceId;
      this.rootIdentity = initial.rootSessionId;
      if (
        !idleReceipt(initial) &&
        !(
          this.newSession &&
          !this.startedWork &&
          initial.state === "unknown" &&
          !initial.exhaustive &&
          initial.runId === null &&
          initial.rootTurnIds.length === 0
        )
      )
        throw new EngineSettlementError();
      this.receipt = initial;
      if (initial.runId) this.seenRuns.add(initial.runId);
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

  private projectText(
    text: string,
    nativeMessageId: string | undefined,
    channel: MessageChannel,
  ): void {
    if (nativeMessageId && channel !== "thought" && text.trim())
      this.visibleMessages.add(nativeMessageId);
    const key = JSON.stringify([nativeMessageId ?? null, channel]);
    const previous = this.textTails.get(key);
    const safe = ((previous?.text ?? "") + text).replaceAll(
      this.options.gatewayToken,
      "[REDACTED]",
    );
    const cutoff = Math.max(
      0,
      safe.length - this.options.gatewayToken.length + 1,
    );
    const metadata = {
      nativeMessageId,
      channel,
      phaseSource:
        channel === "thought"
          ? "acp:agent_thought_chunk"
          : "acp:agent_message_chunk",
    };
    if (cutoff)
      this.emit({ type: "text", text: safe.slice(0, cutoff), ...metadata });
    this.textTails.set(key, { text: safe.slice(cutoff), ...metadata });
  }

  private flushText(nativeMessageId?: string): void {
    for (const [key, tail] of this.textTails) {
      if (
        nativeMessageId !== undefined &&
        tail.nativeMessageId !== nativeMessageId
      )
        continue;
      if (tail.text) this.emit({ type: "text", ...tail });
      this.textTails.delete(key);
    }
  }

  private safeDetail(text: string, max = MAX_DETAIL): string {
    return bounded(
      text
        .replaceAll(this.options.gatewayToken, "[REDACTED]")
        .replace(/(Bearer\s+)[A-Za-z0-9._~+/=-]+/gi, "$1[REDACTED]")
        .replace(
          /((?:api[_-]?key|token|password|secret|authorization)\s*[=:]\s*)[^\s&]+/gi,
          "$1[REDACTED]",
        )
        .replace(/(https?:\/\/)[^/@\s]+:[^/@\s]+@/gi, "$1[REDACTED]@"),
      max,
    );
  }

  private inputSummary(input: unknown): {
    command?: string;
    url?: string;
    detail?: string;
  } {
    if (!record(input)) return {};
    const result: { command?: string; url?: string; detail?: string } = {};
    const details: string[] = [];
    if (typeof input.action === "string")
      details.push(`action: ${this.safeDetail(input.action, 120)}`);
    // Native browser's reviewed schema nests parameters under input; inspect only
    // known fields, never serialize arbitrary objects or credentials.
    if (typeof input.action === "string" && record(input.input)) {
      for (const key of ["url", "query", "path"]) {
        if (typeof input.input[key] !== "string") continue;
        const safe = this.safeDetail(input.input[key] as string);
        if (key === "url") result.url = safe;
        details.push(`${key}: ${safe}`);
      }
    }
    // Explicit actual input fields only: no raw arbitrary serialization or credential fields.
    for (const key of [
      "command",
      "url",
      "query",
      "path",
      "file_path",
      "filePath",
      "pattern",
      "description",
    ]) {
      const value = input[key];
      if (typeof value !== "string") continue;
      const safe = this.safeDetail(value);
      if (key === "command" || key === "url") result[key] = safe;
      details.push(`${key}: ${safe}`);
    }
    if (details.length) result.detail = this.safeDetail(details.join("\n"));
    return result;
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
    if (
      update.sessionUpdate === "agent_message_chunk" ||
      update.sessionUpdate === "agent_thought_chunk"
    ) {
      if (!this.active) return;
      if (update.content.type === "text")
        this.projectText(
          update.content.text,
          nativeId(update.messageId) &&
            !update.messageId.includes(this.options.gatewayToken)
            ? update.messageId
            : undefined,
          update.sessionUpdate === "agent_thought_chunk"
            ? "thought"
            : "unknown",
        );
    } else if (
      update.sessionUpdate === "tool_call" ||
      update.sessionUpdate === "tool_call_update"
    ) {
      const known = this.tools.get(update.toolCallId);
      if (
        !this.active ||
        !nativeId(update.toolCallId) ||
        update.toolCallId.includes(this.options.gatewayToken)
      )
        return;
      const label = this.safeDetail(update.title ?? known?.name ?? "Tool", 160);
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
      const input = this.inputSummary(update.rawInput);
      const detail = (update.content ?? [])
        .flatMap((part) =>
          part.type === "content" && part.content.type === "text"
            ? [part.content.text]
            : [],
        )
        .join("\n");
      const observed = new Date().toISOString();
      const status = update.status ?? known?.status ?? "unknown";
      const projected: Extract<EngineUpdate, { type: "progress" }> = {
        ...known,
        type: "progress",
        kind: "tool",
        label: `${label}: ${status}`,
        taskId: update.toolCallId,
        toolCallId: update.toolCallId,
        toolActivityId: update.toolCallId,
        name: this.safeDetail(
          typeof update.name === "string"
            ? update.name
            : (known?.name ?? label),
          160,
        ),
        status,
        ...(known?.startedAt
          ? { startedAt: known.startedAt }
          : ["pending", "in_progress"].includes(status)
            ? { startedAt: observed }
            : {}),
        updatedAt: observed,
        ...input,
        ...(detail ? { detail: this.safeDetail(detail) } : {}),
        ...(["completed", "failed"].includes(status)
          ? { completedAt: known?.completedAt ?? observed }
          : {}),
      };
      this.tools.set(update.toolCallId, projected);
      this.emit(projected);
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
    // Only actual emitted thought chunks are projected; no inferred hidden reasoning.
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
    if (method === MESSAGE_BOUNDARY) {
      if (
        !this.active ||
        params.schemaVersion !== 1 ||
        !nativeId(params.messageId) ||
        !nativeId(params.turnId) ||
        params.messageId.includes(this.options.gatewayToken) ||
        params.turnId.includes(this.options.gatewayToken) ||
        !["streaming", "completed"].includes(String(params.status)) ||
        ![null, "preamble", "final"].includes(params.kind as string | null) ||
        !(
          params.finishReason === undefined ||
          (typeof params.finishReason === "string" &&
            params.finishReason.length <= 100)
        ) ||
        Object.keys(params).some(
          (k) =>
            ![
              "schemaVersion",
              "sessionId",
              "messageId",
              "turnId",
              "kind",
              "finishReason",
              "status",
            ].includes(k),
        )
      )
        return;
      const previous = this.boundaries.get(params.messageId);
      if (
        previous &&
        (previous.turnId !== params.turnId || previous.status === "completed")
      )
        return;
      if (params.status === "completed") this.flushText(params.messageId);
      this.boundaries.set(params.messageId, {
        turnId: params.turnId,
        kind: params.kind as string | null,
        finishReason: (params.finishReason as string | undefined) ?? null,
        status: params.status as "streaming" | "completed",
      });
      this.emit({
        type: "phase",
        nativeMessageId: params.messageId,
        nativeTurnId: params.turnId,
        channel:
          params.kind === "preamble" ||
          ["tool_calls", "toolUse"].includes(String(params.finishReason))
            ? "commentary"
            : "unknown",
        phaseSource: "native:message_update",
        streamState: params.status as "streaming" | "completed",
      });
      return;
    }
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
      this.unknownChildren();
      /* A fresh required get decides settlement; malformed notifications cannot settle it. */
    }
  }

  private unknownChildren(): void {
    this.emit({
      type: "progress",
      kind: "subagent_summary",
      label: "Subagent counts unknown",
      subagents: {
        known: false,
        active: null,
        completed: null,
        failed: null,
        cancelled: null,
        updatedAt: new Date().toISOString(),
      },
    });
  }

  private async baselineChildren(
    connection: acp.ClientSideConnection,
  ): Promise<void> {
    try {
      const result = await deadline(
        connection.request<unknown>(DELEGATION_GET, {
          sessionId: this.nativeId,
        }),
        5000,
        "Child snapshot unavailable",
      );
      const state = snapshot(
        record(result) ? result.snapshot : undefined,
        this.nativeId!,
      );
      this.childBaseline = new Map(
        state.members.map((m) => [m.sessionId, m.status]),
      );
      this.childBaselineComplete = state.complete === true;
      this.projectChildren(state);
    } catch {
      this.childBaseline = undefined;
      this.childBaselineComplete = false;
      this.unknownChildren();
    }
  }

  private projectChildren(state: ChildSnapshot): void {
    if (!this.active || !this.childBaseline) return;
    const observed = new Date().toISOString();
    for (const child of state.members) {
      if (
        typeof child.backgroundTaskId === "string" &&
        child.backgroundTaskId.length > 0
      )
        this.backgroundObserved = true;
      if (this.childBaseline.get(child.sessionId) !== child.status)
        this.childRunMembers.add(child.sessionId);
      if (
        !this.childRunMembers.has(child.sessionId) ||
        this.childStates.get(child.sessionId) === child.status
      )
        continue;
      this.childStates.set(child.sessionId, child.status);
      const timestamp = (ms: unknown) =>
        typeof ms === "number" &&
        Number.isFinite(ms) &&
        ms >= 0 &&
        ms <= 8.64e15
          ? new Date(ms).toISOString()
          : undefined;
      this.emit({
        type: "progress",
        kind: "subagent",
        label: `${this.safeDetail(child.agentName ?? "Subagent", 120)}: ${child.status}`,
        name: this.safeDetail(child.agentName ?? "Subagent", 120),
        taskId: child.sessionId,
        subagentId: child.sessionId,
        parentSessionId: child.parentSessionId,
        status: child.status,
        updatedAt: timestamp(child.updatedAtMs) ?? observed,
        ...(timestamp(child.createdAtMs)
          ? { startedAt: timestamp(child.createdAtMs) }
          : {}),
        ...(TERMINAL_CHILD.has(child.status)
          ? { completedAt: timestamp(child.updatedAtMs) ?? observed }
          : {}),
        ...(typeof child.backgroundTaskId === "string"
          ? { backgroundTaskId: this.safeDetail(child.backgroundTaskId, 512) }
          : {}),
        ...(typeof child.task === "string"
          ? { detail: this.safeDetail(child.task) }
          : {}),
      });
    }
    const members = state.members.filter((m) =>
      this.childRunMembers.has(m.sessionId),
    );
    if (
      !this.childBaselineComplete ||
      state.complete !== true ||
      members.length !== this.childRunMembers.size ||
      members.some((m) => m.status === "unknown")
    ) {
      this.unknownChildren();
      return;
    }
    const summary: SubagentSummary = {
      known: true,
      active: 0,
      completed: 0,
      failed: 0,
      cancelled: 0,
      updatedAt: observed,
    };
    for (const child of members) {
      if (child.status === "running" || child.status === "queued")
        summary.active!++;
      else if (child.status === "completed") summary.completed!++;
      else if (child.status === "failed") summary.failed!++;
      else if (child.status === "stopped") summary.cancelled!++;
    }
    this.emit({
      type: "progress",
      kind: "subagent_summary",
      label: "Native subagent snapshot",
      subagents: summary,
    });
  }

  private async readSettlement(
    connection = this.requireConnection(),
    expected?: SettlementReceipt,
  ): Promise<SettlementReceipt> {
    const result = await deadline(
      connection.request<unknown>(SETTLEMENT_GET, {
        sessionId: this.nativeId,
        ...(expected
          ? {
              instanceId: expected.instanceId,
              ...(expected.runId ? { runId: expected.runId } : {}),
            }
          : {}),
      }),
      30_000,
      "Engine settlement query timed out",
    );
    const receipt = parseSettlement(
      record(result) ? result.receipt : undefined,
    );
    if (
      (this.instanceIdentity && receipt.instanceId !== this.instanceIdentity) ||
      (this.rootIdentity && receipt.rootSessionId !== this.rootIdentity) ||
      (expected &&
        (receipt.instanceId !== expected.instanceId ||
          receipt.rootSessionId !== expected.rootSessionId ||
          receipt.runId !== expected.runId))
    )
      throw new EngineSettlementError();
    return receipt;
  }

  private async preflight(connection: acp.ClientSideConnection): Promise<void> {
    const current = await this.readSettlement(connection, this.receipt);
    if (
      !idleReceipt(current) &&
      !(
        this.newSession &&
        !this.startedWork &&
        current.state === "unknown" &&
        !current.exhaustive &&
        current.runId === null &&
        current.rootTurnIds.length === 0
      )
    )
      throw new EngineSettlementError();
    this.receipt = current;
  }

  async prompt(
    text: string,
    attachments: { path: string; mimeType: string; name: string }[] = [],
  ): Promise<void | "completed" | "cancelled"> {
    if (this.active) throw new Error("An engine prompt is already active");
    this.active = true;
    this.cancelled = false;
    this.tools.clear();
    this.textTails.clear();
    this.boundaries.clear();
    this.childStates.clear();
    this.visibleMessages.clear();
    this.childBaseline = undefined;
    this.childBaselineComplete = false;
    this.childRunMembers.clear();
    this.emit({
      type: "progress",
      kind: "subagent_summary",
      label: "Subagent counts unknown",
      subagents: {
        known: false,
        active: null,
        completed: null,
        failed: null,
        cancelled: null,
      },
    });
    try {
      await this.start();
      if (this.cancelled) return;
      const connection = this.requireConnection();
      await this.preflight(connection);
      await this.baselineChildren(connection);
      if (this.cancelled) return "cancelled";
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
      while (this.options.dispatchHeld?.() && !this.closing && !this.cancelled)
        await new Promise<void>(resolve => setTimeout(resolve, 50));
      if (this.closing || this.cancelled) return "cancelled";
      this.startedWork = true;
      this.settled = false;
      const result = await connection.prompt({
        sessionId: this.nativeId!,
        prompt: [
          { type: "text", text: TRUSTED_BROWSER_INSTRUCTION },
          { type: "text", text: clockInstruction() },
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
      const receipt = parseSettlement(result._meta?.[SETTLEMENT_META]);
      if (
        !idleReceipt(receipt) ||
        receipt.instanceId !== this.instanceIdentity ||
        receipt.rootSessionId !== this.rootIdentity ||
        this.seenRuns.has(receipt.runId!) ||
        (result.stopReason === "end_turn"
          ? receipt.state !== "settled"
          : result.stopReason === "cancelled"
            ? receipt.state !== "cancelled"
            : true)
      )
        throw new EngineSettlementError();
      const fresh = await this.readSettlement(connection, receipt);
      if (
        !idleReceipt(fresh) ||
        fresh.state !== receipt.state ||
        JSON.stringify(fresh.rootTurnIds) !==
          JSON.stringify(receipt.rootTurnIds)
      )
        throw new EngineSettlementError();
      this.receipt = fresh;
      this.seenRuns.add(fresh.runId!);
      this.settled = true;
      this.flushText();
      // A stopped preamble can precede a background continuation. Only the last
      // real root turn in the verified exhaustive receipt can supply run-final.
      if (fresh.state === "settled") {
        const finalTurn = fresh.rootTurnIds.at(-1);
        const candidates = [...this.boundaries].filter(
          ([, b]) =>
            b.turnId === finalTurn &&
            b.status === "completed" &&
            b.kind !== "preamble" &&
            (b.kind === "final" ||
              ["stop", "end_turn", "stop_sequence"].includes(
                b.finishReason ?? "",
              )),
        );
        const lastCandidate = candidates.at(-1)?.[0];
        const finalId =
          lastCandidate && this.visibleMessages.has(lastCandidate)
            ? lastCandidate
            : undefined;
        for (const [id, b] of this.boundaries) {
          if (!fresh.rootTurnIds.includes(b.turnId)) continue;
          if (
            id === finalId ||
            ["tool_calls", "toolUse"].includes(b.finishReason ?? "") ||
            b.kind === "preamble" ||
            (finalId &&
              b.status === "completed" &&
              (b.kind === "final" ||
                ["stop", "end_turn", "stop_sequence"].includes(
                  b.finishReason ?? "",
                )))
          )
            this.emit({
              type: "phase",
              nativeMessageId: id,
              channel: id === finalId ? "final" : "commentary",
              nativeTurnId: b.turnId,
              streamState: "completed",
              phaseSource: "native:message_update+settled_root_turn",
            });
        }
      }
      return fresh.state === "cancelled" ? "cancelled" : "completed";
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
      this.flushText();
      this.active = false;
    }
  }

  async cancel(): Promise<void> {
    this.cancelled = true;
    const connection = this.connection;
    if (!connection || !this.nativeId || connection.signal.aborted) {
      if (this.startedWork && !this.settled) throw new EngineSettlementError();
      return;
    }
    await connection.cancel({ sessionId: this.nativeId });
    if (!this.startedWork) return;
    await deadline(
      (async () => {
        let expected: SettlementReceipt | undefined;
        for (;;) {
          const receipt = await this.readSettlement(connection, expected);
          if (!expected && receipt.runId !== null) expected = receipt;
          if (idleReceipt(receipt) && receipt.state === "cancelled") return;
          if (receipt.state !== "running") throw new EngineSettlementError();
          await delay(20, undefined, { signal: connection.signal });
        }
      })(),
      30_000,
      "Engine cancellation settlement timed out",
    );
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
    if (connection && !connection.signal.aborted && this.nativeId) {
      await deadline(
        (async () => {
          await connection.cancel({ sessionId: this.nativeId! });
          if (this.startedWork) await this.readSettlement(connection);
          if (this.supportsClose)
            await connection.closeSession({ sessionId: this.nativeId! });
        })(),
        this.options.shutdownTimeouts?.acpMs ?? 5_000,
        "Engine native shutdown timed out",
      ).catch(() => undefined);
    }
    if (child.exitCode === null && child.signalCode === null) {
      this.requestedTermination = child.kill("SIGTERM");
    }
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
      !this.requestedTermination ||
      !this.exitStatus ||
      this.exitStatus.code !== 0 ||
      this.exitStatus.signal !== null ||
      this.exitStatus.spawnError
    ) {
      throw new EngineCleanupError();
    }
    // A killed ACP pipe is not evidence that container grandchildren stopped.
    // Verified owned-container cleanup releases process ownership only; prompt failures remain failures.
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
