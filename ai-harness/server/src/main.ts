import { constants } from "node:fs";
import { open, lstat, realpath } from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { createApp } from "./app.js";
import { createGateway, type LaneState } from "./gateway.js";
import { ImageUpstream } from "./image-upstream.js";
import { createEngine } from "./engine.js";

function required(name: string): string {
  const value = process.env[name];
  if (!value || !path.isAbsolute(value))
    throw new Error(`${name} must be an absolute path`);
  return value;
}
function port(name: string, fallback: number) {
  const value = process.env[name];
  if (!value) return fallback;
  if (!/^\d+$/.test(value) || +value < 1 || +value > 65535)
    throw new Error(`${name} must be a TCP port`);
  return +value;
}
/** Called only by explicit production startup. Fixtures inject synthetic credentials. */
export async function readProtectedCredential(file: string): Promise<string> {
  if (!path.isAbsolute(file) || (await realpath(file)) !== file)
    throw new Error("Unsafe inference credential path");
  const before = await lstat(file);
  if (
    !before.isFile() ||
    before.isSymbolicLink() ||
    before.nlink !== 1 ||
    (before.mode & 0o077) !== 0 ||
    ![0, process.getuid?.()].includes(before.uid)
  )
    throw new Error(
      "Inference credential must be a protected owner-only regular file",
    );
  const handle = await open(file, constants.O_RDONLY | constants.O_NOFOLLOW);
  try {
    const info = await handle.stat();
    if (info.ino !== before.ino || info.dev !== before.dev || info.size > 8192)
      throw new Error("Unsafe inference credential identity");
    const value = (await handle.readFile("utf8")).trim();
    if (!value || !/^[\x21-\x7e]+$/.test(value))
      throw new Error("Invalid inference credential");
    return value;
  } finally {
    await handle.close();
  }
}
export async function start() {
  if (Number(process.versions.node.split(".")[0]) !== 24)
    throw new Error("Node 24 is required");
  const dataDir = required("AI_HARNESS_DATA_DIR"),
    launcher = required("AI_HARNESS_ENGINE_LAUNCHER"),
    keyFile = required("AI_HARNESS_INFERENCE_KEY_FILE");
  const key = await readProtectedCredential(keyFile);
  const approvalKeyFile = process.env.AI_HARNESS_BROWSER_APPROVAL_KEY_FILE;
  const approvalProxyKey = approvalKeyFile
    ? await readProtectedCredential(approvalKeyFile)
    : undefined;
  const gatewayPort = port("AI_HARNESS_GATEWAY_PORT", 8081);
  let gateway: ReturnType<typeof createGateway> | undefined;
  const application = await createApp({
    dataDir,
    launcher,
    engineFactory: createEngine,
    imageBackend: new ImageUpstream({ key }),
    approvalProxyKey,
    gatewayUrl:
      process.env.AI_HARNESS_GATEWAY_URL ??
      `http://127.0.0.1:${gatewayPort}/v1`,
    issueToken: (id) => gateway!.issueToken(id),
    revokeToken: (token) => gateway!.revokeToken(token),
    allowedOrigins: process.env.AI_HARNESS_ALLOWED_ORIGINS?.split(",").map(
      (s) => s.trim(),
    ),
    webDist: process.env.AI_HARNESS_WEB_DIST,
    visionAvailable: process.env.AI_HARNESS_VISION_AVAILABLE !== "false", // fixed deployment capability approved by root probe; UI path remains untested
  });
  try {
    application.store.db.exec(
      "CREATE TABLE IF NOT EXISTS gateway_lanes(alias TEXT PRIMARY KEY,state TEXT NOT NULL); CREATE TABLE IF NOT EXISTS gateway_usage(session_id TEXT PRIMARY KEY,prompt_tokens INTEGER NOT NULL,completion_tokens INTEGER,source TEXT NOT NULL,observed_at TEXT NOT NULL)",
    );
    const states = Object.fromEntries(
      (
        application.store.db
          .prepare("SELECT alias,state FROM gateway_lanes")
          .all() as { alias: string; state: LaneState }[]
      ).map((r) => [r.alias, r.state]),
    );
    gateway = createGateway({
      upstreamKey: key,
      images: application.images,
      initialLaneStates: states,
      onLaneState: (alias, state) => {
        application.store.db
          .prepare("INSERT OR REPLACE INTO gateway_lanes VALUES(?,?)")
          .run(alias, state);
      },
      onUsage: (usage) => {
        // Native children/compression share a token. Retain real request evidence but
        // never overwrite main-chat context with a request of unknown attribution.
        application.store.db
          .prepare("INSERT OR REPLACE INTO gateway_usage VALUES(?,?,?,?,?)")
          .run(
            usage.sessionId,
            usage.promptTokens,
            usage.completionTokens ?? null,
            usage.source,
            new Date().toISOString(),
          );
      },
    });
    await gateway.app.listen({ host: "127.0.0.1", port: gatewayPort });
    await application.app.listen({
      host: "127.0.0.1",
      port: port("AI_HARNESS_PORT", 8080),
    });
  } catch (error) {
    await gateway?.close();
    await application.app.close();
    throw error;
  }
  let stopping = false;
  const close = async () => {
    if (stopping) return;
    stopping = true;
    await Promise.all([
      application.broker.close(),
      application.images?.close(),
    ]);
    await gateway!.close();
    await application.app.close();
  };
  for (const signal of ["SIGINT", "SIGTERM"] as const)
    process.once(signal, () => {
      const timer = setTimeout(() => process.exit(1), 70000);
      timer.unref();
      void close().then(
        () => {
          clearTimeout(timer);
          process.exitCode = 0;
        },
        () => {
          clearTimeout(timer);
          process.exitCode = 1;
        },
      );
    });
  process.stdout.write("ai-harness 0.0.3 listening on IPv4 loopback\n");
  return { ...application, gateway, close };
}
if (
  process.argv[1] &&
  import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href
) {
  start().catch(() => {
    process.stderr.write(
      "ai-harness startup failed; check protected configuration and local ports\n",
    );
    process.exitCode = 1;
  });
}
