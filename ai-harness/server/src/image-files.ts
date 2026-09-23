import { constants } from "node:fs";
import { mkdir, open, chmod } from "node:fs/promises";
import path from "node:path";
import { randomUUID } from "node:crypto";
import type { Files } from "./files.js";
import { ApiError, requireId } from "./errors.js";
import { MAX_IMAGE_BYTES, normalize, sha256 } from "./image-codec.js";
import type {
  ImageJob,
  ImageSubmission,
  ImageReference,
  FrozenImageReference,
} from "./image-contracts.js";

export class ImageFiles {
  constructor(readonly files: Files) {}
  private directory(jobId: string) {
    return path.join(this.files.root, "image-jobs", requireId(jobId));
  }
  async snapshot(
    sessionId: string,
    workspaceId: string,
    jobId: string,
    references: NonNullable<ImageSubmission["references"]>,
  ): Promise<FrozenImageReference[]> {
    const dir = this.directory(jobId);
    await mkdir(dir, { recursive: true, mode: 0o700 });
    await this.files.assertNoLinks(dir);
    const result: FrozenImageReference[] = [];
    for (const [index, reference] of references.entries()) {
      let root: string, relative: string, name: string, id: string;
      if ("fileId" in reference) {
        const file = this.files.store.file(reference.fileId);
        if (file.sessionId !== sessionId)
          throw new ApiError(
            404,
            "not_found",
            "Reference not found in this session",
          );
        root = path.join(
          this.files.root,
          file.kind === "attachment" ? "uploads" : "artifacts",
        );
        relative = file.path;
        name = file.name;
        id = file.id;
      } else {
        root = this.files.workspace(workspaceId);
        relative = reference.workspacePath;
        name = path.basename(relative);
        id = `reference-${index + 1}`;
      }
      const { handle, stat } = await this.files.openGuarded(root, relative);
      let bytes: Buffer;
      try {
        if (stat.size > MAX_IMAGE_BYTES)
          throw new ApiError(
            413,
            "image_too_large",
            "Reference exceeds 50 MiB",
          );
        const chunks: Buffer[] = [];
        let length = 0;
        for await (const chunk of handle.createReadStream()) {
          length += chunk.length;
          if (length > MAX_IMAGE_BYTES)
            throw new ApiError(
              413,
              "image_too_large",
              "Reference exceeds 50 MiB",
            );
          chunks.push(chunk);
        }
        bytes = Buffer.concat(chunks);
      } finally {
        await handle.close().catch(() => {});
      }
      const normalized = await normalize(bytes);
      await this.write(path.join(dir, `${index}.original`), bytes);
      await this.write(path.join(dir, `${index}.png`), normalized.png);
      const { png: _png, ...dimensions } = normalized;
      result.push({
        referenceId: `reference-${index + 1}`,
        ...("fileId" in reference ? { fileId: id } : {}),
        name,
        sha256: sha256(bytes),
        normalizedSha256: sha256(normalized.png),
        ...dimensions,
      });
    }
    return result;
  }
  private async write(
    destination: string,
    bytes: Buffer,
    signal?: AbortSignal,
  ) {
    const handle = await open(
      destination,
      constants.O_CREAT |
        constants.O_EXCL |
        constants.O_WRONLY |
        constants.O_NOFOLLOW,
      0o600,
    );
    try {
      await handle.writeFile(bytes, { signal });
      await handle.sync();
    } finally {
      await handle.close();
    }
    await chmod(destination, 0o400);
  }
  async frozen(
    job: ImageJob,
    snapshots: FrozenImageReference[],
  ): Promise<Buffer[]> {
    const dir = this.directory(job.id),
      out = [];
    await this.files.assertNoLinks(dir);
    for (const [index, ref] of snapshots.entries()) {
      const read = async (suffix: string) => {
        const { handle, stat } = await this.files.openGuarded(
          dir,
          `${index}.${suffix}`,
        );
        try {
          if (stat.size > MAX_IMAGE_BYTES * 8) throw new Error("size");
          return await handle.readFile();
        } finally {
          await handle.close();
        }
      };
      const original = await read("original"),
        normalized = await read("png");
      if (
        sha256(original) !== ref.sha256 ||
        sha256(normalized) !== ref.normalizedSha256
      )
        throw new ApiError(
          409,
          "reference_changed",
          "Frozen reference integrity check failed",
        );
      out.push(normalized);
    }
    return out;
  }
  async save(
    job: ImageJob,
    workspaceId: string,
    bytes: Buffer,
    signal?: AbortSignal,
  ) {
    // Authoritative artifact is outside the engine mount, including cancelled late outputs.
    const id = randomUUID(),
      workspacePath = `image-${job.id}.png`;
    const artifact = path.join(this.files.root, "artifacts", id);
    await this.files.assertNoLinks(path.dirname(artifact));
    await this.write(artifact, bytes, signal);
    const store = this.files.store,
      run = store.runSnapshot(job.runId);
    const f = store.saveFile({
      id,
      sessionId: job.sessionId,
      kind: "artifact",
      path: id,
      name: workspacePath,
      mimeType: "image/png",
      size: bytes.length,
      runId: job.runId,
      messageId:
        !job.cancelRequested && run.status === "completed"
          ? run.finalMessageId
          : null,
      image: {
        jobId: job.id,
        actualSize: job.actualSize!,
        model: job.model,
        seed: job.seed,
        sha256: sha256(bytes),
      },
    });
    store.emit(
      job.sessionId,
      "artifact",
      { artifact: store.publicFile(f) },
      job.runId,
    );
    store.emitRun(job.runId);
    // Preserve the authoritative artifact/provenance even if an engine changed
    // the workspace or shutdown interrupts the non-authoritative workspace copy.
    try {
      const workspace = this.files.workspace(workspaceId);
      await this.files.assertNoLinks(workspace);
      store.db
        .prepare("INSERT INTO h003_image_outputs VALUES(?,?,?)")
        .run(workspaceId, workspacePath, job.id);
      await this.write(path.join(workspace, workspacePath), bytes, signal);
      return { artifactId: id, outputPath: workspacePath };
    } catch {
      return { artifactId: id };
    }
  }
}
