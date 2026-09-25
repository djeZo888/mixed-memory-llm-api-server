import { chmod, lstat, realpath } from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { readProtectedCredential } from "./protected-credential.js";
import { openDispatchFreeze } from "./dispatch-freeze.js";
import { AdminActions } from "./admin-actions.js";
import { nodeClient } from "./node-client.js";
import { createStatusService } from "./status-service.js";
/** Independent entry point: no chat/store/engine instance or native probes. */
export async function startStatus() {
  if (Number(process.versions.node.split(".")[0]) !== 24)
    throw Error("Node24 required");
  const socket = "/run/ai-harness-status/http.sock";
  if (
    process.env.AI_HARNESS_STATUS_SOCKET &&
    process.env.AI_HARNESS_STATUS_SOCKET !== socket
  )
    throw Error("Unexpected status socket");
  const directory = path.dirname(socket),
    stat = await lstat(directory);
  if (
    !stat.isDirectory() ||
    stat.isSymbolicLink() ||
    stat.mode & 0o002 ||
    (await realpath(directory)) !== directory
  )
    throw Error("Unsafe status socket directory");
  const keyFile = process.env.AI_HARNESS_CONTROL_KEY_FILE;
  if (!keyFile) throw Error("Protected control credential not configured");
  const key = await readProtectedCredential(keyFile);
  const freeze = openDispatchFreeze();
  const backends = {
    "ai-vm": nodeClient("ai-vm", key),
    "ai-harness": nodeClient("ai-harness"),
  };
  const actions = new AdminActions({ db: freeze.db, freeze, backends });
  const service = createStatusService({ backends, freeze, actions });
  service.app.addHook("onClose", async () => {
    freeze.close();
  });
  await service.app.listen({ path: socket });
  await chmod(socket, 0o660);
  for (const signal of ["SIGINT", "SIGTERM"] as const)
    process.once(signal, () => {
      void service.app.close();
    });
  return service;
}
if (
  process.argv[1] &&
  import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href
) {
  startStatus().catch(() => {
    process.stderr.write(
      "Independent status startup failed; inspect protected configuration\n",
    );
    process.exitCode = 1;
  });
}
