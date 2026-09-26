import { constants } from "node:fs";
import { open, lstat, realpath } from "node:fs/promises";
import path from "node:path";
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
