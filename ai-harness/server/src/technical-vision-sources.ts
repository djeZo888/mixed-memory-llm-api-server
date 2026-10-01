import path from "node:path";
import { createHash } from "node:crypto";
import sharp from "sharp";
import type { Files } from "./files.js";
import {
  TECHNICAL_VISION_LIMITS as L, TechnicalVisionError,
  type TechnicalVisionInput, type TechnicalVisionOwner, type TechnicalVisionPrepared,
  type TechnicalVisionPage,
} from "./technical-vision-contracts.js";
import { validateTechnicalVisionInput, validateTechnicalVisionOwner, validateTechnicalVisionManifest } from "./technical-vision-validation.js";
import { technicalVisionWithinSignal } from "./technical-vision-lifecycle.js";

export const technicalVisionSha256 = (v: Buffer | string) => createHash("sha256").update(v).digest("hex");
/** Trusted host adapter only. Sandbox/bound the renderer; never pass it an agent-supplied URL/path. */
export type TechnicalVisionPdfRenderer = (input: {
  pdf: Buffer; sha256: string; pages: number[]; maxEdge: number; maxPixels: number;
}, signal: AbortSignal) => Promise<{
  pageCount: number;
  pages: { page: number; png: Buffer; pdf: NonNullable<TechnicalVisionPage["pdf"]> }[];
}>;
export interface TechnicalVisionSourceOptions { files: Files; renderPdf?: TechnicalVisionPdfRenderer; preparationMs?: number }

async function image(bytes: Buffer, page: number) {
  if (!bytes.length || bytes.length > L.sourceBytes) throw new TechnicalVisionError("source_too_large");
  try {
    const options = { limitInputPixels: L.pagePixels, failOn: "warning" as const };
    const m = await sharp(bytes, options).metadata();
    if (!["png", "jpeg"].includes(m.format ?? "") || (m.pages ?? 1) !== 1 || !m.width || !m.height) throw new TechnicalVisionError("invalid_source");
    if (m.width > L.edge || m.height > L.edge || m.width * m.height > L.pagePixels) throw new TechnicalVisionError("source_too_large");
    const { data: png, info } = await sharp(bytes, options).timeout({ seconds: 15 }).autoOrient().toColourspace("srgb").flatten({ background: "#ffffff" }).removeAlpha().png().toBuffer({ resolveWithObject: true });
    if (png.length > L.sourceBytes) throw new TechnicalVisionError("source_too_large");
    return {
      png, format: m.format,
      geometry: { page, width: info.width, height: info.height, originalWidth: m.width, originalHeight: m.height, orientation: m.orientation ?? 1 } satisfies TechnicalVisionPage,
    };
  } catch (e) { if (e instanceof TechnicalVisionError) throw e; throw new TechnicalVisionError("invalid_source"); }
}

export function createTechnicalVisionSourceResolver(options: TechnicalVisionSourceOptions) {
  const preparationMs = options.preparationMs ?? 30000;
  if (!Number.isSafeInteger(preparationMs) || preparationMs < 1 || preparationMs > 120000) throw new TechnicalVisionError("invalid_request");
  const prepare = async (raw: TechnicalVisionInput, owner: TechnicalVisionOwner, signal: AbortSignal): Promise<TechnicalVisionPrepared> => {
    const input = validateTechnicalVisionInput(raw);
    validateTechnicalVisionOwner(owner);
    try {
      signal.throwIfAborted();
      const { files } = options, session = files.store.getSession(owner.sessionId);
      if (session.workspaceId !== owner.workspaceId || session.deleteRequested) throw new TechnicalVisionError("invalid_source");
      const run = files.store.db.prepare("SELECT session_id,workspace_id,status FROM runs WHERE id=?").get(owner.runId);
      if (run?.session_id !== owner.sessionId || run.workspace_id !== owner.workspaceId || run.status !== "running") throw new TechnicalVisionError("invalid_source");
      let root: string, relative: string;
      if ("fileId" in input.source) {
        const file = files.store.file(input.source.fileId);
        if (file.sessionId !== owner.sessionId || !["attachment", "artifact"].includes(file.kind)) throw new TechnicalVisionError("invalid_source");
        root = path.join(files.root, file.kind === "attachment" ? "uploads" : "artifacts"); relative = file.path;
      } else { root = files.workspace(owner.workspaceId); relative = input.source.workspacePath; }
      const { handle, stat } = await files.openGuarded(root, relative);
      let bytes: Buffer;
      try {
        if (!stat.size || stat.size > L.sourceBytes) throw new TechnicalVisionError("source_too_large");
        const chunks: Buffer[] = []; let length = 0;
        // Keep FD open for stable identity, bound growth, then verify metadata before accepting the snapshot.
        for await (const chunk of handle.createReadStream({ autoClose: false })) {
          signal.throwIfAborted(); length += chunk.length;
          if (length > L.sourceBytes) throw new TechnicalVisionError("source_too_large"); chunks.push(chunk);
        }
        const after = await handle.stat();
        if (after.size !== stat.size || length !== stat.size || after.mtimeMs !== stat.mtimeMs || after.ctimeMs !== stat.ctimeMs) throw new TechnicalVisionError("source_changed");
        bytes = Buffer.concat(chunks);
      } finally { await handle.close(); }
      signal.throwIfAborted();
      const hash = technicalVisionSha256(bytes), pages: TechnicalVisionPage[] = [], images: TechnicalVisionPrepared["images"] = [];
      let mediaType: TechnicalVisionPrepared["manifest"]["mediaType"];
      if (bytes.subarray(0, 5).toString("ascii") === "%PDF-") {
        if (!input.pages?.length) throw new TechnicalVisionError("invalid_request");
        if (!options.renderPdf) throw new TechnicalVisionError("unavailable");
        const rendered = await options.renderPdf({ pdf: bytes, sha256: hash, pages: input.pages, maxEdge: L.edge, maxPixels: L.pagePixels }, signal);
        signal.throwIfAborted();
        if (!Number.isSafeInteger(rendered.pageCount) || rendered.pageCount < 1 || input.pages.some(p => p > rendered.pageCount) || !Array.isArray(rendered.pages) || rendered.pages.length !== input.pages.length) throw new TechnicalVisionError("invalid_source");
        for (const page of input.pages) {
          const candidates = rendered.pages.filter(p => p.page === page);
          if (candidates.length !== 1 || !Buffer.isBuffer(candidates[0].png)) throw new TechnicalVisionError("invalid_source");
          const parsed = await image(candidates[0].png, page);
          if (parsed.format !== "png" || parsed.geometry.orientation !== 1) throw new TechnicalVisionError("invalid_source");
          pages.push({ ...parsed.geometry, pdf: candidates[0].pdf }); images.push({ page, png: parsed.png, sha256: technicalVisionSha256(parsed.png) });
        }
        mediaType = "application/pdf";
      } else {
        if (input.pages && (input.pages.length !== 1 || input.pages[0] !== 1)) throw new TechnicalVisionError("invalid_request");
        const parsed = await image(bytes, 1);
        pages.push(parsed.geometry); images.push({ page: 1, png: parsed.png, sha256: technicalVisionSha256(parsed.png) });
        mediaType = parsed.format === "png" ? "image/png" : "image/jpeg";
      }
      const manifest = { reference: input.source, sha256: hash, mediaType, coordinateSpace: "oriented_page_pixels" as const, pages, crops: input.crops ?? [] };
      try { validateTechnicalVisionManifest(manifest); } catch { throw new TechnicalVisionError("invalid_source"); }
      signal.throwIfAborted();
      return { manifest, images };
    } catch (e) {
      if (signal.aborted) throw new TechnicalVisionError("observation_cancelled");
      if (e instanceof TechnicalVisionError) throw e;
      // Guard/store/sharp/renderer diagnostics may contain absolute paths. Never expose them.
      throw new TechnicalVisionError("invalid_source");
    }
  };
  return async (raw: TechnicalVisionInput, owner: TechnicalVisionOwner, signal: AbortSignal): Promise<TechnicalVisionPrepared> => {
    const bounded = AbortSignal.any([signal, AbortSignal.timeout(preparationMs)]);
    try { return await technicalVisionWithinSignal(prepare(raw, owner, bounded), bounded); }
    catch (e) {
      if (signal.aborted) throw new TechnicalVisionError("observation_cancelled");
      if (bounded.aborted) throw new TechnicalVisionError("timeout");
      throw e;
    }
  };
}
