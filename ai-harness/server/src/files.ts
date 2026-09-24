import { constants } from "node:fs";
import { promises as fs } from "node:fs";
import path from "node:path";
import { createHash, randomUUID } from "node:crypto";
import { pipeline } from "node:stream/promises";
import { Transform, type Readable } from "node:stream";
import { ApiError, requireId } from "./errors.js";
import { displayName, imageMime, safeStorageName } from "./file-metadata.js";
import {
  zipStream,
  MAX_ZIP_FILES,
  MAX_ZIP_BYTES,
  type ZipEntry,
} from "./zip.js";
import type { FileRecord, Store } from "./store.js";
import type { Artifact, Attachment } from "./contracts.js";
export const MAX_UPLOAD = 50 * 1024 * 1024;
const MAX_ARTIFACT = 64 * 1024 * 1024;
export const safeName = safeStorageName;
export class Files {
  readonly root: string;
  constructor(
    root: string,
    readonly store: Store,
  ) {
    this.root = path.resolve(root);
  }
  async init() {
    await fs.mkdir(this.root, { recursive: true, mode: 0o700 });
    await this.assertNoLinks(this.root);
    for (const name of [
      "workspaces",
      "profiles",
      "logs",
      "uploads",
      "artifacts",
    ]) {
      const dir = path.join(this.root, name);
      await fs.mkdir(dir, { recursive: true, mode: 0o700 });
      await this.assertNoLinks(dir);
    }
  }
  async assertNoLinks(target: string) {
    const absolute = path.resolve(target);
    let current = path.parse(absolute).root;
    for (const segment of absolute
      .slice(current.length)
      .split(path.sep)
      .filter(Boolean)) {
      current = path.join(current, segment);
      if ((await fs.lstat(current)).isSymbolicLink())
        throw new ApiError(
          400,
          "unsafe_path",
          "Symbolic links are not allowed",
        );
    }
  }
  workspace(id: string) {
    return path.join(this.root, "workspaces", requireId(id));
  }
  profile(id: string) {
    return path.join(this.root, "profiles", requireId(id));
  }
  log(id: string) {
    return path.join(this.root, "logs", `${requireId(id)}.stderr.log`);
  }
  async prepare(sessionId: string, workspaceId: string) {
    for (const dir of [this.workspace(workspaceId), this.profile(sessionId)]) {
      await fs.mkdir(dir, { recursive: true, mode: 0o700 });
      await this.assertNoLinks(dir);
    }
  }
  async openGuarded(root: string, relative: string) {
    if (
      path.isAbsolute(relative) ||
      !relative ||
      relative.includes("\0") ||
      relative.split(/[\\/]/).some((p) => p === "..")
    )
      throw new ApiError(400, "unsafe_path", "Invalid file path");
    const canonicalRoot = await fs.realpath(root);
    const candidate = path.resolve(root, relative);
    if (!candidate.startsWith(path.resolve(root) + path.sep))
      throw new ApiError(400, "unsafe_path", "File is outside workspace");
    await this.assertNoLinks(candidate);
    if ((await fs.realpath(candidate)) !== path.join(canonicalRoot, relative))
      throw new ApiError(400, "unsafe_path", "Noncanonical file path");
    const handle = await fs.open(
      candidate,
      constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_NONBLOCK,
    );
    try {
      const stat = await handle.stat();
      const check = await fs.stat(candidate);
      await this.assertNoLinks(candidate);
      if (
        !stat.isFile() ||
        stat.nlink !== 1 ||
        stat.ino !== check.ino ||
        stat.dev !== check.dev ||
        (await fs.realpath(candidate)) !== path.join(canonicalRoot, relative)
      )
        throw new ApiError(400, "unsafe_path", "Unsafe file identity");
      if (process.platform === "linux") {
        const fdPath = await fs.readlink(`/proc/self/fd/${handle.fd}`);
        if (fdPath !== path.join(canonicalRoot, relative))
          throw new ApiError(400, "unsafe_path", "File escaped workspace");
      }
      return { handle, stat };
    } catch (e) {
      await handle.close();
      throw e;
    }
  }
  async upload(
    sessionId: string,
    filename: string,
    mimeType: string,
    input: Readable,
  ): Promise<FileRecord> {
    const s = this.store.getSession(sessionId);
    if (s.deleteRequested)
      throw new ApiError(409, "deleting", "Session is deleting");
    const id = randomUUID(),
      name = displayName(filename),
      relative = `${id}-${safeName(filename)}`;
    const root = path.join(this.root, "uploads");
    const dest = path.join(root, relative);
    let size = 0;
    const limit = new Transform({
      transform(chunk, _encoding, callback) {
        size += chunk.length;
        callback(
          size > MAX_UPLOAD
            ? new ApiError(413, "upload_too_large", "Upload exceeds 50 MiB")
            : null,
          chunk,
        );
      },
    });
    const handle = await fs.open(dest, "wx", 0o600);
    try {
      if (input.destroyed && !input.readableEnded)
        throw new ApiError(
          400,
          "invalid_upload",
          "Multipart file stream ended prematurely",
        );
      await pipeline(input, limit, handle.createWriteStream());
      if ((input as Readable & { truncated?: boolean }).truncated)
        throw new ApiError(413, "upload_too_large", "Upload exceeds 50 MiB");
      return this.store.saveFile({
        id,
        sessionId,
        kind: "attachment",
        path: relative,
        name,
        mimeType: mimeType.slice(0, 200),
        size,
      });
    } catch (e) {
      await handle.close().catch(() => {});
      await fs.rm(dest, { force: true });
      throw e;
    }
  }
  async discardAttachment(f: FileRecord) {
    if (f.kind !== "attachment") return;
    await fs.rm(path.join(this.root, "uploads", f.path), { force: true });
    this.store.db.prepare("DELETE FROM files WHERE id=?").run(f.id);
  }
  async attachments(sessionId: string, ids: string[]) {
    const s = this.store.getSession(sessionId);
    await this.prepare(s.id, s.workspaceId);
    const workspace = this.workspace(s.workspaceId);
    const folder = path.join(workspace, ".uploads");
    await fs.mkdir(folder, { recursive: true, mode: 0o700 });
    await this.assertNoLinks(folder);
    const out = [];
    for (const id of ids) {
      const f = this.store.file(requireId(id));
      if (f.kind !== "attachment" || f.sessionId !== sessionId)
        throw new ApiError(
          400,
          "invalid_attachment",
          "Attachment does not belong to this chat",
        );
      const { handle } = await this.openGuarded(
        path.join(this.root, "uploads"),
        f.path,
      );
      const destination = path.join(
        folder,
        `${randomUUID()}-${safeName(f.name)}`,
      );
      const target = await fs.open(
        destination,
        constants.O_CREAT |
          constants.O_EXCL |
          constants.O_WRONLY |
          constants.O_NOFOLLOW,
        0o600,
      );
      try {
        await pipeline(handle.createReadStream(), target.createWriteStream());
      } finally {
        await handle.close().catch(() => {});
        await target.close().catch(() => {});
      }
      out.push({ path: destination, name: f.name, mimeType: f.mimeType });
    }
    return out;
  }
  async imageReferences(sessionId: string, ids: string[]): Promise<string[]> {
    if (!ids.length) return [];
    const s = this.store.getSession(sessionId);
    await this.prepare(sessionId, s.workspaceId);
    const root = this.workspace(s.workspaceId),
      folder = path.join(root, ".image-references");
    await fs.mkdir(folder, { recursive: true, mode: 0o700 });
    await this.assertNoLinks(folder);
    const result: string[] = [];
    for (const id of ids) {
      const f = this.store.file(requireId(id));
      if (
        f.kind !== "artifact" ||
        f.sessionId !== sessionId ||
        !["image/png", "image/jpeg"].includes(f.mimeType)
      )
        throw new ApiError(
          400,
          "invalid_image_reference",
          "Image artifact does not belong to this chat",
        );
      const { handle, stat } = await this.openGuarded(
        path.join(this.root, "artifacts"),
        f.path,
      );
      if (stat.size > MAX_ARTIFACT) {
        await handle.close();
        throw new ApiError(413, "image_too_large", "Reference exceeds limit");
      }
      const relative = `.image-references/${randomUUID()}-${safeName(f.name)}`;
      const target = await fs.open(path.join(root, relative), "wx", 0o600);
      try {
        let bytes = 0;
        const limit = new Transform({
          transform(chunk, _encoding, callback) {
            bytes += chunk.length;
            callback(
              bytes > MAX_ARTIFACT
                ? new ApiError(
                    413,
                    "image_too_large",
                    "Reference exceeds limit",
                  )
                : null,
              chunk,
            );
          },
        });
        await pipeline(
          handle.createReadStream(),
          limit,
          target.createWriteStream(),
        );
        result.push(relative);
      } finally {
        await handle.close().catch(() => {});
        await target.close().catch(() => {});
      }
    }
    return result;
  }
  async registerArtifact(
    sessionId: string,
    filePath: string,
    name?: string,
    mimeType = "application/octet-stream",
    runId?: string,
    messageId?: string,
  ) {
    if (
      runId &&
      !this.store.db
        .prepare("SELECT id FROM runs WHERE id=? AND session_id=?")
        .get(runId, sessionId)
    )
      throw new ApiError(404, "not_found", "Run not found");
    if (
      messageId &&
      !this.store.db
        .prepare(
          "SELECT id FROM messages WHERE id=? AND session_id=? AND run_id=? AND role='assistant'",
        )
        .get(messageId, sessionId, runId ?? null)
    )
      throw new ApiError(404, "not_found", "Message not found");
    const s = this.store.getSession(sessionId);
    const workspace = this.workspace(s.workspaceId);
    const relative = path.isAbsolute(filePath)
      ? path.relative(workspace, filePath)
      : filePath;
    if (relative.split(path.sep).some((p) => p.startsWith(".")))
      throw new ApiError(
        400,
        "unsafe_path",
        "Hidden files cannot be published as artifacts",
      );
    if (
      this.store.db
        .prepare(
          "SELECT job_id FROM h003_image_outputs WHERE workspace_id=? AND path=?",
        )
        .get(s.workspaceId, relative)
    )
      throw new ApiError(
        409,
        "managed_image",
        "Image broker owns this artifact and its original reply provenance",
      );
    const { handle, stat } = await this.openGuarded(workspace, relative);
    if (stat.size > MAX_ARTIFACT) {
      await handle.close();
      throw new ApiError(413, "artifact_too_large", "Artifact exceeds 64 MiB");
    }
    const id = randomUUID(),
      dest = path.join(this.root, "artifacts", id);
    const target = await fs.open(dest, "wx", 0o600);
    try {
      let bytes = 0;
      const bounded = new Transform({
        transform(chunk, _e, cb) {
          bytes += chunk.length;
          cb(
            bytes > MAX_ARTIFACT
              ? new ApiError(
                  413,
                  "artifact_too_large",
                  "Artifact grew beyond limit",
                )
              : null,
            chunk,
          );
        },
      });
      await pipeline(
        handle.createReadStream(),
        bounded,
        target.createWriteStream(),
      );
      return this.store.saveFile({
        id,
        sessionId,
        kind: "artifact",
        path: id,
        name: displayName(name ?? path.basename(relative)),
        mimeType: imageMime(name ?? relative) ?? mimeType,
        runId: runId ?? null,
        messageId: messageId ?? null,
        sourcePath: relative,
        size: bytes,
      });
    } catch (e) {
      await fs.rm(dest, { force: true });
      throw e;
    } finally {
      await handle.close().catch(() => {});
      await target.close().catch(() => {});
    }
  }
  async discover(sessionId: string) {
    const s = this.store.getSession(sessionId),
      root = this.workspace(s.workspaceId);
    let visited = 0;
    const candidates: { path: string; size: number; mtime: number }[] = [];
    const walk = async (dir: string, depth: number): Promise<void> => {
      if (depth > 8) return;
      for (const item of await fs.readdir(path.join(root, dir), {
        withFileTypes: true,
      })) {
        if (++visited > 1000) return;
        if (
          item.name.startsWith(".") ||
          ["node_modules", "dist", "__pycache__"].includes(item.name)
        )
          continue;
        const rel = path.join(dir, item.name);
        if (item.isDirectory()) await walk(rel, depth + 1);
        else if (item.isFile()) {
          if (
            this.store.db
              .prepare(
                "SELECT job_id FROM h003_image_outputs WHERE workspace_id=? AND path=?",
              )
              .get(s.workspaceId, rel)
          )
            continue;
          const st = await fs.stat(path.join(root, rel));
          if (st.size <= MAX_ARTIFACT)
            candidates.push({ path: rel, size: st.size, mtime: st.mtimeMs });
        }
      }
    };
    await walk("", 0);
    return candidates;
  }
  /** Legacy recovery is a read-only projection. No original row or event is rewritten. */
  async withLegacyReferences(
    sessionId: string,
    artifacts: (Attachment | Artifact)[],
  ) {
    const session = this.store.getSession(sessionId);
    const workspace = this.workspace(session.workspaceId);
    let budget = MAX_ZIP_BYTES,
      candidates = 0;
    const result: (Attachment | Artifact)[] = [];
    for (const artifact of artifacts) {
      result.push(artifact);
      if (!("runId" in artifact)) continue;
      const file = this.store.file(artifact.id);
      if (
        file.sessionId !== sessionId ||
        file.runId !== artifact.runId ||
        file.messageId !== artifact.messageId
      )
        continue;
      const aliases = this.store.legacyReferencePaths(file);
      if (!aliases.length || ++candidates > MAX_ZIP_FILES ||
        file.size > MAX_ARTIFACT || file.size * 2 > budget)
        continue;
      // Read only a server-composed direct child, never the model's link target.
      let source: Awaited<ReturnType<Files["openGuarded"]>> | undefined;
      let snapshot: Awaited<ReturnType<Files["openGuarded"]>> | undefined;
      try {
        source = await this.openGuarded(workspace, file.name);
        snapshot = await this.openGuarded(
          path.join(this.root, "artifacts"),
          file.path,
        );
        if (source.stat.size !== file.size || snapshot.stat.size !== file.size)
          continue;
        budget -= file.size * 2;
        const digest = async (opened: NonNullable<typeof source>) => {
          const hash = createHash("sha256");
          let position = 0;
          while (position < opened.stat.size) {
            const buffer = Buffer.allocUnsafe(
              Math.min(64 * 1024, opened.stat.size - position),
            );
            const { bytesRead } = await opened.handle.read(
              buffer,
              0,
              buffer.length,
              position,
            );
            if (!bytesRead) throw new Error("Legacy source changed");
            hash.update(buffer.subarray(0, bytesRead));
            position += bytesRead;
          }
          const after = await opened.handle.stat();
          if (
            after.size !== opened.stat.size ||
            after.mtimeMs !== opened.stat.mtimeMs ||
            after.ctimeMs !== opened.stat.ctimeMs
          )
            throw new Error("Legacy source changed");
          return hash.digest("hex");
        };
        if ((await digest(source)) === (await digest(snapshot)))
          result[result.length - 1] = { ...artifact, referencePaths: aliases };
      } catch {
        /* Missing, changed or unsafe legacy sources retain the conservative UI fallback. */
      } finally {
        await source?.handle.close().catch(() => {});
        await snapshot?.handle.close().catch(() => {});
      }
    }
    return result;
  }
  async zip(sessionId: string, runId: string, includeAttachments = false) {
    this.store.getSession(requireId(sessionId));
    requireId(runId);
    const run = this.store.db
      .prepare("SELECT attachment_ids FROM runs WHERE id=? AND session_id=?")
      .get(runId, sessionId);
    if (!run) throw new ApiError(404, "not_found", "Run not found");
    const files = this.store
      .files(sessionId, "artifact")
      .filter((f) => f.runId === runId);
    for (const file of files) {
      if (
        file.messageId &&
        !this.store.db
          .prepare(
            "SELECT id FROM messages WHERE id=? AND session_id=? AND run_id=? AND role='assistant'",
          )
          .get(file.messageId, sessionId, runId)
      )
        throw new ApiError(
          404,
          "not_found",
          "Artifact not found in this reply",
        );
    }
    if (includeAttachments)
      files.push(
        ...this.store.ownedAttachments(
          sessionId,
          this.attachmentIds(run.attachment_ids),
          true,
        ),
      );
    return this.zipFiles(files);
  }
  async messageZip(sessionId: string, messageId: string) {
    this.store.getSession(requireId(sessionId));
    const message = this.store.db
      .prepare(
        "SELECT attachment_ids FROM messages WHERE id=? AND session_id=? AND role='user'",
      )
      .get(requireId(messageId), sessionId);
    if (!message) throw new ApiError(404, "not_found", "Message not found");
    return this.zipFiles(
      this.store.ownedAttachments(
        sessionId,
        this.attachmentIds(message.attachment_ids),
        true,
      ),
    );
  }
  private attachmentIds(value: unknown): string[] {
    let ids: unknown;
    try {
      ids = JSON.parse(String(value));
    } catch {
      /* Invalid stored references fail closed. */
    }
    if (!Array.isArray(ids) || ids.some((id) => typeof id !== "string"))
      throw new ApiError(404, "not_found", "Invalid reply file references");
    return ids.map(requireId);
  }
  private async zipFiles(files: FileRecord[]) {
    if (!files.length)
      throw new ApiError(404, "not_found", "No files for this reply");
    if (
      files.length > MAX_ZIP_FILES ||
      files.reduce((n, f) => n + f.size, 0) > MAX_ZIP_BYTES
    )
      throw new ApiError(
        413,
        "zip_too_large",
        "ZIP exceeds 100 files or 256 MiB",
      );
    const entries: ZipEntry[] = [];
    try {
      let bytes = 0;
      for (const file of files) {
        const { handle, stat } = await this.openGuarded(
          path.join(
            this.root,
            file.kind === "artifact" ? "artifacts" : "uploads",
          ),
          file.path,
        );
        entries.push({ handle, size: stat.size, name: file.name });
        bytes += stat.size;
        if (
          stat.size > (file.kind === "artifact" ? MAX_ARTIFACT : MAX_UPLOAD) ||
          bytes > MAX_ZIP_BYTES
        )
          throw new ApiError(413, "zip_too_large", "ZIP exceeds size limit");
      }
      return zipStream(entries);
    } catch (error) {
      await Promise.all(entries.map((e) => e.handle.close().catch(() => {})));
      throw error;
    }
  }
  async download(id: string, kind: FileRecord["kind"] = "artifact") {
    const f = this.store.file(requireId(id));
    if (f.kind !== kind)
      throw new ApiError(404, "not_found", "Artifact not found");
    this.store.getSession(f.sessionId);
    const { handle, stat } = await this.openGuarded(
      path.join(this.root, kind === "artifact" ? "artifacts" : "uploads"),
      f.path,
    );
    return { file: f, size: stat.size, stream: handle.createReadStream() };
  }
}
