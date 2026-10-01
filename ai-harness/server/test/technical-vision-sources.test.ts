import assert from "node:assert/strict";
import test, { type TestContext } from "node:test";
import { mkdtemp, realpath, rm, writeFile, mkdir, symlink, link, readFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { Readable } from "node:stream";
import sharp from "sharp";
import { Store } from "../src/store.js";
import { Files } from "../src/files.js";
import { createTechnicalVisionSourceResolver, technicalVisionSha256, type TechnicalVisionPdfRenderer } from "../src/technical-vision-sources.js";
import { signal } from "./technical-vision-fixtures.js";

async function local(t: TestContext, renderPdf?: TechnicalVisionPdfRenderer) {
  const root = await realpath(await mkdtemp(path.join(tmpdir(), "h039-technical-vision-")));
  const store = new Store(path.join(root, "db.sqlite")), files = new Files(root, store);
  await files.init(); const session = store.createSession(); await files.prepare(session.id, session.workspaceId);
  const run = store.createRun(session, "message", "synthetic vision fixture", []); store.updateRun(run.id, "running");
  const owner = { sessionId: session.id, workspaceId: session.workspaceId, runId: run.id };
  t.after(async () => { store.close(); await rm(root, { recursive: true, force: true }); });
  return { root, store, files, session, run, owner, resolve: createTechnicalVisionSourceResolver({ files, renderPdf }), upload: (bytes: Buffer, name = "fixture.png") => files.upload(session.id, name, "application/octet-stream", Readable.from(bytes)) };
}
const png = (w = 120, h = 80) => sharp({ create: { width: w, height: h, channels: 3, background: "#fff" } }).png().toBuffer();
test("owned upload and workspace snapshots validate actual format, preserve original bytes, hash and geometry", async t => {
  const f = await local(t), bytes = await png(), file = await f.upload(bytes, "declared.jpg");
  const request = { requestId: "read1", source: { fileId: file.id }, crops: [{ id: "crop1", page: 1, x: 10, y: 10, width: 100, height: 60 }] };
  const p = await f.resolve(request, f.owner, signal());
  assert.equal(p.manifest.mediaType, "image/png"); assert.equal(p.manifest.sha256, technicalVisionSha256(bytes));
  assert.deepEqual(p.manifest.pages[0], { page: 1, width: 120, height: 80, originalWidth: 120, originalHeight: 80, orientation: 1 });
  assert.deepEqual(await readFile(path.join(f.root, "uploads", file.path)), bytes);
  const workspace = f.files.workspace(f.owner.workspaceId); await mkdir(path.join(workspace, "drawings")); await writeFile(path.join(workspace, "drawings/a.png"), bytes);
  const w = await f.resolve({ requestId: "read2", source: { workspacePath: "drawings/a.png" } }, f.owner, signal());
  assert.equal(w.manifest.sha256, p.manifest.sha256);
  assert.ok(!JSON.stringify(w.manifest).includes(f.root));
  const raster = await sharp(w.images[0].png).metadata(); assert.equal(raster.width, 120);
});
test("EXIF orientation maps crop coordinates to oriented pixels without resizing", async t => {
  const f = await local(t), bytes = await sharp({ create: { width: 120, height: 80, channels: 3, background: "#aaa" } }).jpeg().withMetadata({ orientation: 6 }).toBuffer();
  const file = await f.upload(bytes);
  const p = await f.resolve({ requestId: "rotate", source: { fileId: file.id }, crops: [{ id: "edge", page: 1, x: 60, y: 100, width: 20, height: 20 }] }, f.owner, signal());
  assert.deepEqual(p.manifest.pages[0], { page: 1, width: 80, height: 120, originalWidth: 120, originalHeight: 80, orientation: 6 });
  assert.equal(p.manifest.mediaType, "image/jpeg"); assert.equal((await sharp(p.images[0].png).metadata()).width, 80);
});
test("session/run/workspace ownership, traversal, symlink and hardlink guards reject without path leakage", async t => {
  const f = await local(t), other = f.store.createSession(), bytes = await png(), file = await f.upload(bytes);
  const request = { requestId: "scope", source: { fileId: file.id } };
  for (const owner of [{ ...f.owner, workspaceId: other.workspaceId }, { ...f.owner, sessionId: other.id }, { ...f.owner, runId: "absent" }]) await assert.rejects(f.resolve(request, owner, signal()), { code: "invalid_source" });
  const workspace = f.files.workspace(f.owner.workspaceId); await writeFile(path.join(workspace, "a.png"), bytes);
  await symlink(path.join(workspace, "a.png"), path.join(workspace, "symbolic.png")); await link(path.join(workspace, "a.png"), path.join(workspace, "hard.png"));
  for (const workspacePath of ["symbolic.png", "hard.png", "a.png"]) await assert.rejects(f.resolve({ requestId: "guard", source: { workspacePath } }, f.owner, signal()), (e: any) => e.code === "invalid_source" && !e.message.includes(f.root));
  await assert.rejects(f.resolve({ requestId: "guard", source: { workspacePath: "../secret" } }, f.owner, signal()), { code: "invalid_request" });
  f.store.updateRun(f.run.id, "completed"); await assert.rejects(f.resolve(request, f.owner, signal()), { code: "invalid_source" });
});
test("raw DWG, SVG, corrupt images, oversize pages and out-of-bounds crops cannot dispatch", async t => {
  const f = await local(t);
  for (const bytes of [Buffer.from("AC1032 raw DWG fixture"), Buffer.from('<svg xmlns="http://www.w3.org/2000/svg"/>'), Buffer.from([0x89, 0x50, 0x4e, 0x47]), Buffer.from("https://example.com/image.png")]) {
    const file = await f.upload(bytes); await assert.rejects(f.resolve({ requestId: "bad", source: { fileId: file.id } }, f.owner, signal()), { code: "invalid_source" });
  }
  const big = await f.upload(await png(4097, 1)); await assert.rejects(f.resolve({ requestId: "big", source: { fileId: big.id } }, f.owner, signal()), { code: "source_too_large" });
  const file = await f.upload(await png());
  await assert.rejects(f.resolve({ requestId: "crop", source: { fileId: file.id }, crops: [{ id: "crop1", page: 1, x: 119, y: 0, width: 2, height: 1 }] }, f.owner, signal()), { code: "invalid_source" });
  await assert.rejects(f.resolve({ requestId: "page", source: { fileId: file.id }, pages: [2] }, f.owner, signal()), { code: "invalid_request" });
});
test("explicit PDF pages use a trusted renderer seam with page units, source hash and bounded geometry", async t => {
  const rendered = await png(), bytes = Buffer.from("%PDF-1.7\nsynthetic renderer-seam fixture; not a valid PDF\n");
  let calls = 0;
  const f = await local(t, async (request, abort) => {
    calls++; assert.deepEqual(request.pdf, bytes); assert.equal(request.sha256, technicalVisionSha256(bytes)); assert.deepEqual(request.pages, [2]); assert.equal(request.maxEdge, 4096); assert.equal(abort.aborted, false);
    return { pageCount: 3, pages: [{ page: 2, png: rendered, pdf: { widthPoints: 720, heightPoints: 480, rotation: 0 } }] };
  });
  const file = await f.upload(bytes, "fixture.pdf"), request = { requestId: "pdf", source: { fileId: file.id }, pages: [2], crops: [{ id: "detail", page: 2, x: 0, y: 0, width: 120, height: 80 }] };
  const p = await f.resolve(request, f.owner, signal());
  assert.equal(p.manifest.mediaType, "application/pdf"); assert.equal(p.manifest.pages[0].page, 2); assert.equal(p.manifest.pages[0].pdf!.widthPoints, 720); assert.equal(p.manifest.sha256, technicalVisionSha256(bytes)); assert.equal(calls, 1);
  await assert.rejects(f.resolve({ requestId: "pdf-no-page", source: { fileId: file.id } }, f.owner, signal()), { code: "invalid_request" });
  const noRenderer = createTechnicalVisionSourceResolver({ files: f.files }); await assert.rejects(noRenderer(request, f.owner, signal()), { code: "unavailable" });
});
test("invalid PDF page mapping/rotation fails closed and pre-aborted preparation does no renderer work", async t => {
  const bytes = Buffer.from("%PDF-1.7\nfixture"), raster = await png(); let calls = 0;
  const f = await local(t, async () => { calls++; return { pageCount: 1, pages: [{ page: 2, png: raster, pdf: { widthPoints: 720, heightPoints: 480, rotation: 0 } }] }; });
  const file = await f.upload(bytes), request = { requestId: "pdf", source: { fileId: file.id }, pages: [2] };
  await assert.rejects(f.resolve(request, f.owner, signal()), { code: "invalid_source" });
  const abort = new AbortController(); abort.abort(); await assert.rejects(f.resolve(request, f.owner, abort.signal), { code: "observation_cancelled" }); assert.equal(calls, 1);
  const invalidRotation = createTechnicalVisionSourceResolver({ files: f.files, renderPdf: async () => ({ pageCount: 2, pages: [{ page: 2, png: raster, pdf: { widthPoints: 720, heightPoints: 480, rotation: 45 as any } }] }) });
  await assert.rejects(invalidRotation(request, f.owner, signal()), { code: "invalid_source" });
});
test("non-cooperative PDF adapter has a bounded preparation deadline and caller cancellation", async t => {
  const f = await local(t), file = await f.upload(Buffer.from("%PDF-1.7\nfixture"));
  let calls = 0;
  const resolve = createTechnicalVisionSourceResolver({ files: f.files, preparationMs: 30, renderPdf: async () => { calls++; return new Promise(() => {}); } });
  const request = { requestId: "deadline", source: { fileId: file.id }, pages: [1] };
  await assert.rejects(resolve(request, f.owner, signal()), { code: "timeout" }); assert.equal(calls, 1);
  const stop = new AbortController(), observing = resolve(request, f.owner, stop.signal); stop.abort();
  await assert.rejects(observing, { code: "observation_cancelled" });
});
