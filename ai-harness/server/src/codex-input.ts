import { promises as fs } from "node:fs";
import path from "node:path";
import { CodexProtocolError } from "./codex-connection.js";
export const nativeMedia = (mime: string) =>
  /^(image|audio|video)\//i.test(mime);
/** App Server 0.158.0 has no generic file variant. Text references use mounted paths;
 * bytes remain in the original upload/artifact store and are read by workspace tools. */
export async function codexInput(
  text: string,
  workspace: string,
  attachments: { path: string; mimeType: string; name: string }[],
) {
  if (attachments.length > 20)
    throw new CodexProtocolError("Too many Codex file references");
  const references: { path: string; name: string; mimeType: string }[] = [];
  const root = path.resolve(workspace);
  for (const file of attachments) {
    if (nativeMedia(file.mimeType))
      throw new CodexProtocolError(
        "Codex native media is not qualified; use an available specialist tool",
      );
    if (
      !file.path ||
      /[\x00-\x1f\x7f\\]/.test(file.path) ||
      file.path.split("/").includes("..")
    )
      throw new CodexProtocolError("Invalid Codex file reference");
    const absolute = path.resolve(root, file.path),
      relative = path.relative(root, absolute);
    if (!relative || relative.startsWith("..") || path.isAbsolute(relative))
      throw new CodexProtocolError("Codex file reference outside workspace");
    let current = path.parse(absolute).root;
    for (const part of absolute.slice(current.length).split(path.sep)) {
      current = path.join(current, part);
      if ((await fs.lstat(current)).isSymbolicLink())
        throw new CodexProtocolError(
          "Codex file reference contains symbolic link",
        );
    }
    const stat = await fs.stat(absolute);
    if (!stat.isFile() || stat.nlink !== 1)
      throw new CodexProtocolError("Unsafe Codex file reference");
    references.push({
      path: relative,
      name: file.name,
      mimeType: file.mimeType,
    });
  }
  return [
    {
      type: "text",
      text:
        text +
        (references.length
          ? `\n\nUser-selected workspace files (path references; no native media recognition):\n${JSON.stringify(references)}`
          : ""),
      text_elements: [],
    },
  ];
}
