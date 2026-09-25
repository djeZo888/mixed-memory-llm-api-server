import { constants, type Stats } from "node:fs";
import fs from "node:fs/promises";

const directory = "/run/credentials/ai-harness-status.service";
const registeredFile = `${directory}/control-api-key`;
const ancestry = ["/", "/run", "/run/credentials", directory];
const unsafe = () => new Error("Unsafe status credential provenance");

function same(a: Stats, b: Stats): boolean {
  return ["dev", "ino", "uid", "gid", "mode", "nlink", "size"]
    .every((key) => a[key as keyof Stats] === b[key as keyof Stats]);
}

function sameParent(a: Stats, b: Stats): boolean {
  return ["dev", "ino", "uid", "gid", "mode"]
    .every((key) => a[key as keyof Stats] === b[key as keyof Stats]);
}

function protectedFile(info: Stats): boolean {
  return info.isFile() && !info.isSymbolicLink() &&
    info.uid === 0 && info.gid === 0 && (info.mode & 0o7777) === 0o440 &&
    info.nlink === 1 && info.size > 0 && info.size <= 8192;
}

async function boundary() {
  const parents: Stats[] = [];
  for (const parent of ancestry) {
    const info = await fs.lstat(parent);
    if (!info.isDirectory() || info.isSymbolicLink() ||
        info.uid !== 0 || info.gid !== 0 || (info.mode & 0o022) !== 0 ||
        (await fs.realpath(parent)) !== parent ||
        (parent === directory && (info.mode & 0o7777) !== 0o550))
      throw unsafe();
    parents.push(info);
  }
  const mounts = (await fs.readFile("/proc/self/mountinfo", "utf8"))
    .trim().split("\n").map((line) => ({ line, fields: line.split(" ") }))
    .filter(({ fields }) => fields[4] === directory ||
      fields[4]?.startsWith(`${directory}/`));
  if (mounts.length !== 1) throw unsafe();
  const { line, fields } = mounts[0];
  const separator = fields.indexOf("-");
  const options = fields[5]?.split(",") ?? [];
  const device = /^(\d+):(\d+)$/.exec(fields[2] ?? "");
  if (!device) throw unsafe();
  const major = BigInt(device[1]), minor = BigInt(device[2]);
  const dev = ((major & 0xfffn) << 8n) | (minor & 0xffn) |
    ((minor & ~0xffn) << 12n) | ((major & ~0xfffn) << 32n);
  // systemd's credential bind mount is read-only; its tmpfs superblock may be rw.
  if (BigInt(parents[parents.length - 1].dev) !== dev ||
      fields[4] !== directory || fields[3] !== "/" || separator < 6 ||
      fields[separator + 1] !== "tmpfs" || fields[separator + 2] !== "tmpfs" ||
      !["ro", "nosuid", "nodev", "noexec", "nosymfollow"].every((x) => options.includes(x)) ||
      ["rw", "suid", "dev", "exec", "symfollow"].some((x) => options.includes(x)))
    throw unsafe();
  return { parents, mount: line };
}

/** Status-only registration. Never use this exception for inference credentials.
 * The exact root-managed immutable systemd mount establishes provenance. The
 * deployment checks its numeric ACL: named service UID r/rx, group/other none;
 * 0440/0550 group bits are the ACL mask, not an owning-group access grant.
 */
export async function readStatusControlCredential(file: string): Promise<string> {
  if (file !== registeredFile || process.env.CREDENTIALS_DIRECTORY !== directory)
    throw unsafe();
  const initial = await boundary();
  if ((await fs.realpath(file)) !== file) throw unsafe();
  const before = await fs.lstat(file);
  if (!protectedFile(before) || before.dev !== initial.parents[ancestry.length - 1].dev)
    throw unsafe();
  const handle = await fs.open(file, constants.O_RDONLY | constants.O_NOFOLLOW);
  try {
    const opened = await handle.stat();
    if (!protectedFile(opened) || !same(before, opened)) throw unsafe();
    const value = (await handle.readFile("utf8")).trim();
    const after = await handle.stat();
    const current = await fs.lstat(file);
    const final = await boundary();
    if (!protectedFile(after) || !same(opened, after) || !same(after, current) ||
        (await fs.realpath(file)) !== file || initial.mount !== final.mount ||
        !initial.parents.every((parent, i) => sameParent(parent, final.parents[i])))
      throw unsafe();
    if (!value || !/^[\x21-\x7e]+$/.test(value))
      throw new Error("Invalid status credential");
    return value;
  } finally {
    await handle.close();
  }
}
