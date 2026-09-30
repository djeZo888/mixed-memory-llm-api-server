/** Protected offline operator entry point. Never imported by main or exposed over HTTP. */
import { execFileSync } from "node:child_process";
import { lstatSync, readFileSync, readdirSync, realpathSync, statSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { DatabaseSync } from "node:sqlite";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { Store } from "./store.js";
import { recoverySnapshot } from "./recovery-snapshot.js";
import { parseRecoveryProof, readRootProtected, sha256, verifyEvidenceFiles, verifyLocalBoundary, verifyRequestBinding, type LocalBoundary, type RecoveryProof } from "./recovery-proof.js";

/** Check local descriptors only. No sockets, HTTP, SSH, probes or service mutations. */
export function localBoundary(proof: RecoveryProof): LocalBoundary {
  if (process.platform !== "linux" || !process.getuid) throw Error("Recovery requires the Linux app host");
  const uid = process.getuid();
  if (uid === 0 || uid !== proof.database.uid) throw Error("Recovery must run as the existing non-root app user");
  const db = lstatSync(proof.database.path);
  if (!db.isFile() || db.isSymbolicLink() || realpathSync(proof.database.path) !== proof.database.path) throw Error("Unsafe database path");
  const output = execFileSync("/usr/bin/systemctl", ["--user", "show", "ai-harness.service", "--property=LoadState,ActiveState,SubState,MainPID"], { encoding: "utf8", timeout: 5000, maxBuffer: 8192, env: { ...process.env, SYSTEMD_PAGER: "cat" } });
  const properties = Object.fromEntries(output.trim().split("\n").map(line => line.split("=")));
  const service = { LoadState: properties.LoadState!, ActiveState: properties.ActiveState!, SubState: properties.SubState!, MainPID: properties.MainPID! };
  const databaseUsers: number[] = [];
  const maintenanceWorkers: LocalBoundary["maintenanceWorkers"] = [];
  // A stopped/masked service plus no app-UID database handles is required. Unknown
  // same-UID process access fails closed, not silently treated as absent.
  for (const entry of readdirSync("/proc")) {
    if (!/^\d+$/.test(entry) || Number(entry) === process.pid) continue;
    try {
      const command = readFileSync(`/proc/${entry}/cmdline`, "utf8").replaceAll("\0", " ").trim();
      if (command.startsWith("nginx: worker process")) {
        const stat = readFileSync(`/proc/${entry}/stat`, "utf8");
        const fields = stat.slice(stat.lastIndexOf(")") + 2).split(" ");
        maintenanceWorkers.push({ pid: Number(entry), startTicks: fields[19]! });
      }
      if (statSync(`/proc/${entry}`).uid !== uid) continue;
      for (const descriptor of readdirSync(`/proc/${entry}/fd`)) {
        try {
          const st = statSync(`/proc/${entry}/fd/${descriptor}`);
          if (st.dev === db.dev && st.ino === db.ino) databaseUsers.push(Number(entry));
        } catch (error) { if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error; }
      }
    } catch (error) { if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error; }
  }
  return { uid, bootId: readFileSync("/proc/sys/kernel/random/boot_id", "utf8").trim(), now: Date.now(), database: { dev: db.dev, ino: db.ino, uid: db.uid }, service, databaseUsers, maintenanceWorkers };
}

/** Read-only snapshot never instantiates Store, changes journal mode or migrates. */
export function readOnlyPreflight(proof: RecoveryProof) {
  // SQLite READONLY still creates shared-memory/WAL files on a clean WAL-mode
  // source. Inspect a private byte-for-byte DB+WAL copy instead. Never use
  // immutable=1 on the source: that would silently ignore an uncheckpointed WAL.
  const directory = mkdtempSync(path.join(tmpdir(), "h036-readonly-"));
  const sources = [proof.database.path, `${proof.database.path}-wal`];
  const capture = () => sources.map(source => {
    try {
      const st = lstatSync(source);
      if (!st.isFile() || st.isSymbolicLink()) throw Error("Unsafe recovery database/WAL");
      return readFileSync(source);
    } catch (error) { if ((error as NodeJS.ErrnoException).code === "ENOENT" && source.endsWith("-wal")) return undefined; throw error; }
  });
  let db: DatabaseSync | undefined;
  try {
    const bytes = capture();
    for (const [i, buffer] of bytes.entries()) if (buffer) writeFileSync(path.join(directory, i === 0 ? "snapshot.sqlite" : "snapshot.sqlite-wal"), buffer, { mode: 0o600 });
    const after = capture();
    if (bytes.some((buffer, i) => buffer ? !after[i]?.equals(buffer) : after[i] !== undefined)) throw Error("Recovery refused: database changed while taking snapshot");
    db = new DatabaseSync(path.join(directory, "snapshot.sqlite"), { readOnly: true });
    db.exec("BEGIN");
    verifyRequestBinding(db, proof);
    const snapshot = recoverySnapshot(db, proof.target);
    if (snapshot.sha256 !== proof.database.snapshotSha256) throw Error("Recovery refused: snapshot changed");
    return { snapshotSha256: snapshot.sha256 };
  } finally { if (db) { if (db.isTransaction) db.exec("ROLLBACK"); db.close(); } rmSync(directory, { recursive: true, force: true }); }
}

export function runRecovery(argv: string[]) {
  if (argv.length !== 5 || !["preflight", "apply"].includes(argv[0]!) || argv[1] !== "--proof" || argv[3] !== "--session")
    throw Error("Usage: interrupted-recovery.js preflight|apply --proof /root-protected/proof.json --session EXACT_UUID");
  const [action, , proofPath, , sessionId] = argv;
  const bytes = readRootProtected(proofPath!);
  const proof = parseRecoveryProof(JSON.parse(bytes.toString("utf8")));
  if (sessionId !== proof.target.sessionId) throw Error("Explicit session differs from protected assignment");
  // The executing CLI and all reviewed semantics must be the exact deployed build.
  if (realpathSync(fileURLToPath(import.meta.url)) !== proof.deployment.build["interrupted-recovery"]!.path)
    throw Error("Recovery must execute the exact protected deployed build");
  const verify = () => {
    if (sha256(readRootProtected(proofPath!)) !== sha256(bytes)) throw Error("Recovery proof changed");
    verifyEvidenceFiles(proof);
    verifyLocalBoundary(proof, localBoundary(proof));
  };
  verify();
  const before = readOnlyPreflight(proof);
  verify();
  if (action === "preflight") return { operation: "preflight", eligible: true, sessionId, ...before, outcome: "interrupted_unknown", applied: false };
  // Offline mode does not run migrations or generic restart recovery. BEGIN
  // IMMEDIATE inside apply performs the snapshot CAS before any durable mutation.
  const store = new Store(proof.database.path, undefined, { mode: "offline-recovery" });
  try {
    verify();
    verifyRequestBinding(store.db, proof);
    store.applyPhysicalRelease({
      target: proof.target, snapshotSha256: before.snapshotSha256, proofSha256: sha256(bytes), recoveryId: proof.recoveryId,
      evidence: { schema: 1, proofPath, sourceCommit: proof.deployment.sourceCommit, nativeContainerId: proof.native.containerId,
        harnessOldBootId: proof.harness.oldBootId, harnessNewBootId: proof.harness.newBootId,
        providerOldBootId: proof.provider.oldBootId, providerNewBootId: proof.provider.newBootId,
        providerEndpoint: proof.provider.endpoint, providerLane: proof.provider.lane },
    });
    return { operation: "apply", sessionId, recoveryId: proof.recoveryId, outcome: "interrupted_unknown", physicalRelease: true, proofSha256: sha256(bytes), snapshotSha256: before.snapshotSha256 };
  } finally { store.close(); }
}

if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) {
  try { process.stdout.write(JSON.stringify(runRecovery(process.argv.slice(2))) + "\n"); }
  catch (error) { process.stderr.write(JSON.stringify({ applied: false, error: error instanceof Error ? error.message : "Recovery refused" }) + "\n"); process.exitCode = 1; }
}
