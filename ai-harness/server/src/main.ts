import {loadCodexOrdinaryEntry,type CodexOrdinaryEntry} from "./codex-ordinary-entry.js";
import {CodexEngine} from "./codex-engine.js";
import type {CodexNativeObservation} from "./codex-observation.js";
import type {FreshParentRecoveryEvidence} from "./session-checkpoint.js";
import { readFileSync } from "node:fs";
import { loadCodexSpecialists } from "./codex-specialist-qualification.js";
import { createHostOwnedAcceptance } from "./owned-acceptance.js";
import { loadFrontierSelection, loadActiveFrontier } from "./active-frontier.js";
import { FRONTIER_MODEL } from "./frontier.js";
import { MIMO_MODEL } from "./mimo.js";
import { FrontierLedger } from "./frontier-ledger.js";
import { readProtectedCredential } from "./protected-credential.js";
export { readProtectedCredential } from "./protected-credential.js";
import path from "node:path";
import { fileURLToPath,pathToFileURL } from "node:url";
import { createApp } from "./app.js";
import { createGateway, type LaneState, type GatewayOptions } from "./gateway.js";
import { ImageUpstream } from "./image-upstream.js";
import { createEngine } from "./engine.js";
import { composeCodexHost, type CodexHostQualification } from "./codex-host.js";
import { GatewayOwnershipLedger } from "./gateway-ownership.js";
import { createProductionQwenVerifier, loadQwenReceipt } from "./codex-production.js";
import { createResponsesDiagnostics, createQwenAdmissionDiagnostics } from "./codex-diagnostics.js";
import { codexDeployment } from "./codex-deployment.js";
import {
  NodeAvailability,
  type HardwareLatchLedger,
} from "./node-availability.js";
import { nodeClient } from "./node-client.js";
import { openDispatchFreeze, serveDispatchFreeze } from "./dispatch-freeze.js";
import { serviceAvailability } from "./service-availability.js";
import { createBackendReadiness } from "./backend-readiness.js";
import { loadNewChatEngine } from "./system-registry.js";

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
/** Explicit reviewed release entrypoint. The trusted new-chat default must qualify.
 * The receipt is a protected host file outside task mounts and binds current instances. */
export async function startCodexPreview(receiptPath: string, outputLimit = 65536, imageJobsQualified = false, frontierResponsesQualified = false, acceptance?: { frontier: (sessionId: string) => boolean; image?: (sessionId: string) => boolean; diagnostics?: GatewayOptions["diagnostics"] }, ownedAcceptancePath?: string, specialistQualificationPath?: string) {
  let qualification: CodexHostQualification | undefined;
  try {
    const receipt = await loadQwenReceipt(receiptPath);
    const inferenceKey = await readProtectedCredential(required("AI_HARNESS_INFERENCE_KEY_FILE"));
    const controlKey = await readProtectedCredential(required("AI_HARNESS_NODE_CONTROL_KEY_FILE"));
    const onAdmissionDiagnostic = createQwenAdmissionDiagnostics(path.join(required("AI_HARNESS_DATA_DIR"), "codex-qwen-admission.jsonl"));
    const verifyLane = createProductionQwenVerifier(receipt, { inferenceKey, controlKey }, undefined, undefined, onAdmissionDiagnostic);
    // This list pins reviewed lane policy, not ephemeral startup readiness.
    // Host composition revalidates current owner identity for every admission;
    // counter revalidates again before/after counting on the selected lane.
    const qualifiedAliases = Object.keys(receipt.lanes);
    // Legacy positional flags remain accepted, but cannot substitute for live evidence.
    const specialists = loadCodexSpecialists(specialistQualificationPath);
    qualification = { protocolQualified: true, rootlessQualified: true, verifyLane, onAdmissionDiagnostic, outputLimit, qualifiedAliases, nativeDelegationQualified: true,
      ...(acceptance ? { frontierAcceptance: acceptance.frontier, imageAcceptance: acceptance.image } : {}),
      ...(specialists.frontierResponsesQualified ? { frontierResponsesQualified: true as const } : {}),
      ...(specialists.imageJobsQualified ? { imageJobsQualified: true as const } : {}),
      capabilities: specialists.capabilities,
      onResponsesError: createResponsesDiagnostics(path.join(required("AI_HARNESS_DATA_DIR"), "codex-responses-errors.jsonl")) };
  } catch { /* A failed optional preview must not remove MiniMax or stored histories. */ }
  const ordinary=qualification?loadCodexOrdinaryEntry(process.env.AI_HARNESS_CODEX_ORDINARY_ENTRY_FILE||undefined,process.env.AI_HARNESS_CODEX_ORDINARY_ENTRY_KEY_FILE||undefined,{serverDir:path.dirname(path.dirname(fileURLToPath(import.meta.url))),deploymentDir:path.dirname(required("AI_HARNESS_ENGINE_LAUNCHER"))}):undefined;
  if(ordinary&&qualification)qualification={...qualification,nativeReceiptPolicy:ordinary.nativeReceiptPolicy,...ordinary.hooks};
  if (!qualification) process.stderr.write("Codex preview unavailable: deployment identity/allocation unqualified\n");
  return start({ enablePreview: !!qualification, qualification, pilotOutputLimit: outputLimit, providerDiagnostics: acceptance?.diagnostics, ownedAcceptancePath,ordinary });
}
export async function start(codex: { enablePreview?: boolean; qualification?: CodexHostQualification; pilotOutputLimit?: number; providerDiagnostics?: GatewayOptions["diagnostics"]; ownedAcceptancePath?: string;ordinary?:CodexOrdinaryEntry } = {}) {
  const newChatEngine = loadNewChatEngine();
  if (Number(process.versions.node.split(".")[0]) !== 24)
    throw new Error("Node 24 is required");
  const dataDir = required("AI_HARNESS_DATA_DIR"),
    launcher = required("AI_HARNESS_ENGINE_LAUNCHER"),
    keyFile = required("AI_HARNESS_INFERENCE_KEY_FILE");
  const freeze = openDispatchFreeze();
  const key = await readProtectedCredential(keyFile);
  const approvalKeyFile = process.env.AI_HARNESS_BROWSER_APPROVAL_KEY_FILE;
  const approvalProxyKey = approvalKeyFile
    ? await readProtectedCredential(approvalKeyFile)
    : undefined;
  const gatewayPort = port("AI_HARNESS_GATEWAY_PORT", 8081);
  let frontierLedger: FrontierLedger | undefined;
  let gateway: ReturnType<typeof createGateway> | undefined;
  let nodeAvailability: NodeAvailability | undefined;
  let freezeServer: Awaited<ReturnType<typeof serveDispatchFreeze>> | undefined;
  let freezeTimer: NodeJS.Timeout | undefined;
  if (codex.qualification && gatewayPort !== 8081) throw Error("Codex requires the shared gateway owner on port 8081");
  let activeRunId = (_sessionId: string): string | undefined => undefined;
  const owned = codex.ownedAcceptancePath ? createHostOwnedAcceptance(codex.ownedAcceptancePath, id => activeRunId(id)) : undefined;
  if (owned && codex.qualification) codex.qualification = { ...codex.qualification, frontierAcceptance: owned.frontier, imageAcceptance: owned.image, onResponsesDiagnostic: owned.onDiagnostic };
  const codexHost = composeCodexHost(path.join(path.dirname(launcher), "run-codex.sh"), () => gateway, codex.qualification);
  const codexOptions = codexDeployment({ enablePreview: codex.enablePreview, runtime: codexHost.runtime });
  const availability = (id: string) => {
    const observed = serviceAvailability(
      nodeAvailability
        ? (name) => nodeAvailability!.get(name)
        : [FRONTIER_MODEL, MIMO_MODEL].includes(id)
          ? () => ({ state: "unknown", dispatch: "hold" })
          : undefined,
      id,
    );
    return freeze.held(id) && observed.dispatch !== "reject"
      ? {
          ...observed,
          dispatch: "hold" as const,
          reason: "admin_dispatch_frozen",
        }
      : observed;
  };
  const application = await createApp({
    newChatEngine,
    dataDir,
    launcher,
    engineFactory: createEngine,
    ...codexOptions,
    memoryRecoveryHost:codex.ordinary?async input=>{
      const session=application.store.getSession(input.sessionId),g=gateway;if(!g?.observeNoGeneration||session.engineKind!=="codex"||session.nativeState.ownership!=="idle"||session.nativeState.activeTurnId!==null||application.store.isQuarantined(session.workspaceId)||freeze.held("harness"))throw Error("Ordinary recovery owner is unavailable");
      const row=application.store.db.prepare("SELECT id FROM h041_session_checkpoints WHERE session_id=? AND id=? AND status='recovery_required'").get(input.sessionId,input.checkpointId);if(!row||!application.store.db.prepare("SELECT id FROM h041_checkpoint_recoveries WHERE session_id=? AND checkpoint_id=?").get(input.sessionId,input.checkpointId))throw Error("Exact human-acknowledged recovery required");
      if(application.store.db.prepare("SELECT id FROM runs WHERE workspace_id=? AND status IN ('queued','running','cancelling') LIMIT 1").get(session.workspaceId))throw Error("Workspace still has queued/active owner");
      await application.files.prepare(input.sessionId,session.workspaceId);const observed:Partial<FreshParentRecoveryEvidence>={};const token=g.issueToken(input.sessionId,"codex");
      const result=await g.observeNoGeneration(input.sessionId,async()=>{const engine=new CodexEngine({sessionId:input.sessionId,profileDir:application.files.profile(input.sessionId),workspace:application.files.workspace(session.workspaceId),launcher,gatewayUrl:codexHost.runtime.gatewayUrl,gatewayToken:token,stderrPath:application.files.log(input.sessionId),sessionMemory:input.memory,onNativeSessionId:()=>{},onNativeState:state=>application.store.setNativeState(input.sessionId,"codex",state),onUpdate:()=>{},onNativeLifecycle:event=>{if(["launch","thread","settlement","gateway_settled"].includes(event.kind))Object.assign(observed,{[event.kind==="gateway_settled"?"gateway":event.kind]:event});}},codexHost.runtime);try{await engine.start();await engine.close();}catch(error){try{await engine.close();}catch{application.store.quarantine(session.workspaceId,"Fresh recovery cleanup unknown");}throw error;}finally{g.revokeToken(token);}return observed;});
      if(!result.value.launch||!result.value.thread||!result.value.settlement||!result.value.gateway)throw Error("Fresh recovery lifecycle observations incomplete");return {...result.value,noGeneration:result.proof} as FreshParentRecoveryEvidence;
    }:undefined,
    imageAcceptance: codex.qualification?.imageAcceptance,
    imageReferenceAcceptance: owned?.imageReference,
    onRunAccepted: owned?.onRunAccepted,
    onRunFinished: owned?.onRunFinished,
    imageBackend: new ImageUpstream({ key }),
    frontierStatus: (sessionId) => ({
      ...gateway?.frontierSnapshot(),
      requests: frontierLedger?.latest(sessionId) ?? [],
    }),
    approvalProxyKey,
    availability,
    dispatchHeld: () => freeze.held("harness"),
    availabilitySummary: () =>
      nodeAvailability?.states() ?? {
        qwenGpu0: "unknown",
        qwenGpu1: "unknown",
        image: "unknown",
      },
    gatewayUrl:
      process.env.AI_HARNESS_GATEWAY_URL ??
      `http://127.0.0.1:${gatewayPort}/v1`,
    issueToken: (id) => gateway!.issueToken(id, application.store.getSession(id).engineKind === "codex" ? "codex" : "minimax"),
    revokeToken: (token) => gateway!.revokeToken(token),
    allowedOrigins: process.env.AI_HARNESS_ALLOWED_ORIGINS?.split(",").map(
      (s) => s.trim(),
    ),
    webDist: process.env.AI_HARNESS_WEB_DIST,
    visionAvailable: process.env.AI_HARNESS_VISION_AVAILABLE !== "false", // fixed deployment capability approved by root probe; UI path remains untested
  });
  activeRunId = id => {
    const rows = application.store.db.prepare("SELECT id FROM runs WHERE session_id=? AND status='running'").all(id) as {id:string}[];
    return rows.length === 1 ? rows[0].id : undefined;
  };
  try {
    application.store.db.exec(
      "CREATE TABLE IF NOT EXISTS gateway_lanes(alias TEXT PRIMARY KEY,state TEXT NOT NULL); CREATE TABLE IF NOT EXISTS gateway_usage(session_id TEXT PRIMARY KEY,prompt_tokens INTEGER NOT NULL,completion_tokens INTEGER,source TEXT NOT NULL,observed_at TEXT NOT NULL)",
    );
    application.store.db.exec(
      "CREATE TABLE IF NOT EXISTS node_hardware_latches(id INTEGER PRIMARY KEY CHECK(id=1), value TEXT NOT NULL)",
    );
    const latchRow = application.store.db
      .prepare("SELECT value FROM node_hardware_latches WHERE id=1")
      .get() as { value: string } | undefined;
    const controlKeyFile = process.env.AI_HARNESS_NODE_CONTROL_KEY_FILE;
    // Optional H005 source wiring. The status daemon is never a chat startup
    // dependency. Once a durable latch exists, disabling config cannot erase it.
    if (controlKeyFile || latchRow) {
      const controlKey = controlKeyFile
        ? await readProtectedCredential(controlKeyFile)
        : undefined;
      nodeAvailability = new NodeAvailability({
        readiness: createBackendReadiness(key),
        backend: controlKey
          ? nodeClient("ai-vm", controlKey)
          : {
              status: async () => {
                throw Error("Passive node not configured");
              },
            },
        initialLatches: latchRow
          ? (JSON.parse(latchRow.value) as HardwareLatchLedger)
          : {},
        onLatch: (ledger) => {
          application.store.db
            .prepare("INSERT OR REPLACE INTO node_hardware_latches VALUES(1,?)")
            .run(JSON.stringify(ledger));
        },
        changed: () => {
          gateway?.notifyAvailabilityChanged();
          application.images?.notifyAvailabilityChanged();
        },
      });
    }
    frontierLedger = new FrontierLedger(application.store.db);
    let selectedFrontierModel: typeof FRONTIER_MODEL | typeof MIMO_MODEL = FRONTIER_MODEL;
    let frontier: import("./gateway.js").GatewayOptions["frontier"];
    try {
      // Read selected model before qualification: never disguise a rejected
      // MiMo selection as an available GLM fallback.
      const rawSelection = JSON.parse(readFileSync(new URL("../../config/active-frontier.json", import.meta.url), "utf8"));
      if (rawSelection?.model === MIMO_MODEL) selectedFrontierModel = MIMO_MODEL;
      const selection = loadFrontierSelection();
      frontier = loadActiveFrontier(selection,
        () => readProtectedCredential(required("AI_HARNESS_FRONTIER_KEY_FILE")),
        (record) => frontierLedger!.record(record),
        () => readProtectedCredential(required("AI_HARNESS_NODE_CONTROL_KEY_FILE")));
    } catch { /* Only the selected frontier is disabled. Qwen startup survives. */ }
    const states = Object.fromEntries(
      (
        application.store.db
          .prepare("SELECT alias,state FROM gateway_lanes")
          .all() as { alias: string; state: LaneState }[]
      ).map((r) => [r.alias, r.state]),
    );
    const ownership = new GatewayOwnershipLedger(application.store.db).options();
    // A recovered request cannot be erased by an idle lane row from an older owner.
    for (const record of ownership.initialRequests ?? []) {
      if (record.lane) states[record.lane] = "quarantined";
      else for (const alias of ["qwen3.8-27b-gpu0", "qwen3.8-27b"]) states[alias] = "quarantined";
    }
    gateway = createGateway({
      ownership,
      responses: codexHost.responses,
      nativeMetadataAuthority: codex.qualification?.nativeMetadataAuthority,
      onNativeOperation: receipt => {
        const row=application.store.db.prepare("SELECT id FROM runs WHERE session_id=? AND status='running' ORDER BY rowid DESC LIMIT 1").get(receipt.sessionId);
        if(row){application.store.checkpoints.recordNativeEvidence(receipt.sessionId,String(row.id),"native_operation",receipt);
          if(receipt.metadata.request_kind==="compaction")application.store.checkpoints.observeCompaction(receipt.sessionId,String(row.id),"gateway:"+receipt.requestId,receipt.phase==="uncertain"?"failed":receipt.phase==="settled"?"completed":"start");}
        codex.qualification?.onNativeOperation?.(receipt);
      },
      diagnostics: owned ? { capture: owned.capture, onFailure: owned.onFailure } : codex.providerDiagnostics,
      imageAcceptance: codex.qualification?.imageAcceptance,
      qwenOutputLimit: codex.pilotOutputLimit ?? codex.qualification?.outputLimit,
      frontier,
      selectedFrontierModel,
      initialFrontierOwnerModel: (application.store.db.prepare("SELECT json_extract(value,'$.model') AS model FROM frontier_requests WHERE state IN ('active','quarantined') ORDER BY updated_at DESC LIMIT 1").get() as {model?: string} | undefined)?.model,
      upstreamKey: key,
      images: application.images,
      codexImageJobsQualified: codex.qualification?.imageJobsQualified === true,
      availability,
      dispatchHeld: (alias) => freeze.held(alias),
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
    const changed = () => {
      application.broker.notifyDispatchChanged();
      gateway?.notifyAvailabilityChanged();
      application.images?.notifyAvailabilityChanged();
    };
    let previousHolds = JSON.stringify(
      freeze.db.prepare("SELECT key FROM dispatch_holds ORDER BY key").all(),
    );
    freezeTimer = setInterval(() => {
      try {
        const holds = JSON.stringify(
          freeze.db
            .prepare("SELECT key FROM dispatch_holds ORDER BY key")
            .all(),
        );
        if (holds !== previousHolds) {
          previousHolds = holds;
          changed();
        }
      } catch {
        changed();
      } // Dispatch gates independently fail closed on read error.
    }, 250);
    freezeTimer.unref();
    nodeAvailability?.start();
    await gateway.app.listen({ host: "127.0.0.1", port: gatewayPort });
    await application.app.listen({
      host: "127.0.0.1",
      port: port("AI_HARNESS_PORT", 8080),
    });
    freezeServer = await serveDispatchFreeze(
      freeze,
      () => {
        const broker = application.broker.dispatchImpact(),
          lanes = gateway!.snapshot(),
          image = application.images?.dispatchImpact();
        const active =
          (gateway!.frontierSnapshot().state === "active" ? 1 : 0) +
          broker.active +
          lanes.lanes.filter((lane) => lane.state === "active").length +
          (image?.lane === "active" ? 1 : 0);
        const queued =
          gateway!.frontierSnapshot().queued +
          broker.queued +
          lanes.queued +
          (image?.queued ?? 0) +
          (image?.awaitingApproval ?? 0);
        // Counts are component reservations, not distinct user requests. Quarantine
        // and native activity cannot be inferred idle from passive readiness.
        return {
          frozen: freeze.held(),
          ready: true,
          activity: active ? "busy" : "unknown",
          active_requests: active,
          queue_depth: queued,
        };
      },
      changed,
      (scope) => {
        const aliases = [
          scope.includes("qwen-gpu0") ? "qwen3.8-27b-gpu0" : null,
          scope.includes("qwen-gpu1") ? "qwen3.8-27b" : null,
          scope.includes("glm-5.3-flash") ? "glm-5.3-flash" : null,
        ].filter((id): id is string => !!id);
        if (!gateway!.reconcileAfterOwnerSettlement(aliases)) return false;
        if (
          scope.includes("image") &&
          application.images &&
          !application.images.reconcileAfterOwnerSettlement()
        )
          return false;
        return true;
      },
    );
  } catch (error) {
    owned?.close();
    codexHost.stopSettlementObservation();
    nodeAvailability?.stop();
    clearInterval(freezeTimer);
    await freezeServer?.close();
    freeze.close();
    await gateway?.close();
    await application.app.close();
    throw error;
  }
  let stopping = false;
  const close = async () => {
    if (stopping) return;
    stopping = true;
    nodeAvailability?.stop();
    clearInterval(freezeTimer);
    await freezeServer?.close();
    owned?.close();
    codexHost.stopSettlementObservation();
    await Promise.all([
      application.broker.close(),
      application.images?.close(),
    ]);
    await gateway!.close();
    await application.app.close();
    freeze.close();
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
