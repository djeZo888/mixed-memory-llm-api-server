/** Selected explicitly by the reviewed host service launcher; no browser enable flag. */
import { isAbsolute } from "node:path";
import { startCodexPreview } from "./main.js";
const receipt = process.argv[2], output = Number(process.argv[3] ?? "65536");
if (!receipt || !isAbsolute(receipt) || !Number.isSafeInteger(output) || output < 1 || output > 65536) {
  process.stderr.write("Invalid reviewed Codex deployment arguments\n"); process.exitCode = 1;
} else {
  startCodexPreview(receipt, output).catch(() => {
    process.stderr.write("Sova startup failed; check protected configuration and local ports\n"); process.exitCode = 1;
  });
}
