import { randomUUID } from "node:crypto";
import { execFileSync } from "node:child_process";
import {
  BUILD_NAMES, ORIGINAL_RELEASE, RECOVERY_ENDPOINT, RECOVERY_LANE, sha256,
  type CurrentFile, type EvidenceFile, type LocalBoundary, type RecoveryProof,
} from "../src/recovery-proof.js";

/** Synthetic source fixtures only: these bytes are not operational evidence. */
const originalSources = new Map<string, Buffer>();
export const fixtureEvidenceBytes = (filePath: string) => {
  const source = filePath === "/opt/h036-test/evidence/original/gateway.ts" ? "gateway" :
    filePath === "/opt/h036-test/evidence/original/main.ts" ? "main" : undefined;
  if (source) {
    if (!originalSources.has(source)) originalSources.set(source, execFileSync("git", ["show", `${ORIGINAL_RELEASE}:ai-harness/server/src/${source}.ts`]));
    return originalSources.get(source)!;
  }
  return Buffer.from(`SOURCE TEST FIXTURE, NOT A LIVE GRANT: ${filePath}\n`);
};
const evidence = (filePath: string): EvidenceFile => ({ path: filePath, sha256: sha256(fixtureEvidenceBytes(filePath)) });
const currentFile = (filePath: string): CurrentFile => ({ ...evidence(filePath), uid: 1001, mode: 0o644 });

export function fixtureProof(): RecoveryProof {
  const target = {
    sessionId: randomUUID(), runId: randomUUID(), workspaceId: randomUUID(),
    threadId: randomUUID(), turnId: randomUUID(), requestIds: [randomUUID()],
  };
  const containerId = "a".repeat(64);
  const releasePath = "/opt/h036-test/release";
  const newProviderBoot = randomUUID();
  return {
    schema: 1, operation: "release-one-interrupted-codex", recoveryId: randomUUID(),
    issuedAt: "2026-09-30T02:00:00.000Z", expiresAt: "2026-09-30T02:10:00.000Z", target,
    database: { path: "/opt/h036-test/data/app.sqlite", uid: 1001, dev: 2, ino: 100, snapshotSha256: "b".repeat(64) },
    deployment: {
      sourceCommit: "c".repeat(40), releasePath,
      config: currentFile("/opt/h036-test/current.env"), unit: currentFile("/opt/h036-test/harness.service"),
      build: Object.fromEntries(BUILD_NAMES.map(name => [name, currentFile(`${releasePath}/server/dist/${name}.js`)])),
    },
    maintenance: {
      config: { ...currentFile("/etc/nginx/sites-available/ai-harness"), uid: 0 }, responseStatus: 503,
      capture: evidence("/opt/h036-test/evidence/maintenance.json"),
      observedAt: "2026-09-30T01:59:00.000Z", workers: [{ pid: 1234, startTicks: "481516" }, { pid: 1235, startTicks: "481517" }],
    },
    harness: {
      oldBootId: randomUUID(), newBootId: randomUUID(), newBootStartedAt: "2026-09-30T01:30:49.000Z",
      capture: evidence("/opt/h036-test/evidence/harness-boots.json"),
    },
    native: {
      containerId, imageId: `sha256:${"d".repeat(64)}`, uid: 1001,
      workspaceMount: `/opt/h036-test/workspaces/${target.workspaceId}`, threadHomeMount: "/opt/h036-test/native-home",
      lineage: evidence("/opt/h036-test/evidence/native-lineage.json"), cleanup: evidence("/opt/h036-test/evidence/native-cleanup.json"),
      removedAt: "2026-09-30T01:50:00.000Z", absenceObservedAt: "2026-09-30T01:50:01.000Z",
      removeArgv: ["podman", "rm", "-f", containerId], removeExit: 0,
      absenceArgv: ["podman", "container", "exists", containerId], absenceExit: 1,
    },
    provider: {
      originalSourceCommit: ORIGINAL_RELEASE,
      originalGateway: evidence("/opt/h036-test/evidence/original/gateway.ts"),
      originalMain: evidence("/opt/h036-test/evidence/original/main.ts"),
      originalConfig: evidence("/opt/h036-test/evidence/original/config.env"),
      upstreamMode: "DEFAULT_UPSTREAMS", lane: RECOVERY_LANE, endpoint: RECOVERY_ENDPOINT, nodeAlias: "ai-vm",
      oldSshHostKeySha256: "e".repeat(64), newSshHostKeySha256: "e".repeat(64),
      nodeAttestation: evidence("/opt/h036-test/evidence/node-attestation.json"),
      oldCapture: evidence("/opt/h036-test/evidence/provider-old.json"), newCapture: evidence("/opt/h036-test/evidence/provider-new.json"),
      oldBootId: randomUUID(), newBootId: newProviderBoot, newBootStartedAt: "2026-09-30T01:35:00.000Z",
      runtimeBootId: newProviderBoot, runtimeStartedAt: "2026-09-30T01:36:00.000Z", runtimeInvocationId: randomUUID().replaceAll("-", ""),
      replayPolicy: "volatile-no-durable-request-replay", replayReview: evidence("/opt/h036-test/evidence/replay-review.txt"),
      requests: [{ id: target.requestIds[0]!, acceptedAt: "2026-09-29T23:31:10.733Z", lane: RECOVERY_LANE, endpoint: RECOVERY_ENDPOINT }],
    },
  };
}

export function fixtureBoundary(proof: RecoveryProof): LocalBoundary {
  return {
    uid: proof.database.uid, bootId: proof.harness.newBootId, now: Date.parse("2026-09-30T02:01:00.000Z"),
    database: { dev: proof.database.dev, ino: proof.database.ino, uid: proof.database.uid },
    service: { LoadState: "masked", ActiveState: "inactive", SubState: "dead", MainPID: "0" }, databaseUsers: [],
    maintenanceWorkers: structuredClone(proof.maintenance.workers),
  };
}
