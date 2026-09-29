import assert from "node:assert/strict";
import test, { type TestContext } from "node:test";
import { mkdtemp, realpath, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { Readable } from "node:stream";
import sharp from "sharp";
import { createApp } from "../src/app.js";
import type { ImageBackend } from "../src/image-contracts.js";

const png = (width: number, height: number) => sharp({
  create: { width, height, channels: 3, background: "#728344" },
}).png().toBuffer();
async function until(check: () => boolean) {
  const deadline = Date.now() + 4000;
  while (!check()) {
    assert.ok(Date.now() < deadline, "offline fixture timed out");
    await new Promise(resolve => setTimeout(resolve, 5));
  }
}

// In-process app + fake engine/backend only: no listener, HTTP request or model.
async function fixture(t: TestContext) {
  const dir = await realpath(await mkdtemp(path.join(tmpdir(), "image-intent-")));
  const turns: { text: string; finish(): void }[] = [];
  const executions: (() => Promise<void>)[] = [];
  const backend: ImageBackend = {
    async capabilities() { return {}; },
    profiles() { return [{ operation: "edit", referenceCount: 1, size: "64x64", model: "fixture" }]; },
    async readiness() { return { ready: true, idle: true }; },
    execute(input) {
      return new Promise(resolve => executions.push(async () => {
        resolve({ kind: "output", png: await png(64, 64), model: input.model, seed: input.seed });
      }));
    },
  };
  const f = await createApp({
    dataDir: dir,
    launcher: "/offline/not-launched",
    gatewayUrl: "http://127.0.0.1:1/v1",
    issueToken: () => "offline-token",
    revokeToken: () => {},
    imageBackend: backend,
    engineFactory: options => {
      let settle = () => {};
      return {
        async start() {},
        async prompt(text) {
          await new Promise<void>(resolve => {
            settle = resolve;
            turns.push({ text, finish() {
              options.onUpdate({ type: "text", text: "Historical fixture final", nativeMessageId: "reply", channel: "final" });
              options.onUpdate({ type: "phase", nativeMessageId: "reply", channel: "final", phaseSource: "offline_fixture", streamState: "completed" });
              resolve();
            } });
          });
        },
        async cancel() { settle(); },
        async close() { settle(); },
      };
    },
  });
  t.after(async () => { await f.app.close(); await rm(dir, { recursive: true, force: true }); });
  const session = await f.broker.createSession();
  const runId = f.broker.enqueue(session.id, "message", "Previous edit request");
  await until(() => turns.length === 1);
  const reference = await f.files.upload(session.id, "reference.png", "image/png", Readable.from(await png(120, 60)));
  const job = await f.images!.submit(session.id, {
    requestId: "saved-edit", operation: "edit", prompt: "private previous image prompt",
    references: [{ fileId: reference.id }],
  });
  assert.equal(job.state, "awaiting_approval");
  return { ...f, session, runId, reference, job, turns, executions };
}
function statuses(context: string): { id: string; runId: string; state: string; relationToCurrentRun: string; artifactId?: string }[] {
  return JSON.parse(context.split("\n")[1]);
}

test("image intent: new request follows prior completed status with exact text, references and immutable late result", async t => {
  const f = await fixture(t);
  assert.equal(f.turns[0].text, "Previous edit request", "no-image-context prompt stays byte-identical");
  f.turns[0].finish();
  await f.broker.idle();
  const oldFinal = f.store.messages(f.session.id).find(m => m.role === "assistant")!;
  const { approvalToken } = await f.images!.issueApprovalToken(f.session.id, f.job.id);
  await f.images!.approve(f.session.id, f.job.id, "approve", approvalToken);
  await until(() => f.executions.length === 1);
  await f.executions[0]();
  await until(() => f.store.messages(f.session.id).some(m => m.imageJobId === f.job.id));
  const completed = f.images!.get(f.session.id, f.job.id);
  assert.equal(completed.state, "completed");
  assert.equal(completed.runId, f.runId);
  assert.deepEqual(f.store.message(oldFinal.id), oldFinal);
  const historical = f.store.messages(f.session.id);
  const result = historical.find(m => m.imageJobId === f.job.id)!;
  assert.equal(result.origin, "image_service");
  assert.equal(result.runId, f.runId);
  assert.ok(result.content.includes(completed.artifactId!));
  assert.equal(f.turns.length, 1, "late result does not start an automatic turn");

  const request = "  Delegate to one fresh child to change the sail to blue.\nPreserve the original; show the actual edit inline and its download link.  ";
  const stageReferences = f.files.imageReferences.bind(f.files);
  let paths: string[] = [];
  f.files.imageReferences = async (sessionId, ids, allowUploads) => {
    assert.deepEqual([sessionId, ids, allowUploads], [f.session.id, [completed.artifactId!], false]);
    paths = await stageReferences(sessionId, ids, allowUploads);
    return paths;
  };
  const runId = f.broker.enqueue(f.session.id, "message", request, [], [completed.artifactId!]);
  await until(() => f.turns.length === 2);
  const context = f.images!.context(f.session.id, runId);
  assert.equal(paths.length, 1);
  f.files.imageReferences = stageReferences;
  const references = `\n\nUser-selected image references (workspace-relative paths):\n${paths.map(p => JSON.stringify(p)).join("\n")}\nUse these owned files for image tools when requested.`;
  assert.equal(f.turns[1].text, `${context}\n\nCurrent user request (run ${runId}):\n${request}${references}`);
  assert.equal(statuses(context).length, 1);
  assert.equal(statuses(context)[0].id, f.job.id);
  assert.equal(statuses(context)[0].runId, f.runId);
  assert.equal(statuses(context)[0].state, "completed");
  assert.equal(statuses(context)[0].relationToCurrentRun, "prior_run");
  assert.ok(context.includes(`current request run ${runId}`));
  assert.ok(context.includes(completed.artifactId!));
  assert.match(context, /does not by itself satisfy a different newly requested transformation or delegation/);
  assert.ok(!context.includes("private previous image prompt"));
  assert.equal(f.store.messages(f.session.id).find(m => m.runId === runId && m.role === "user")!.content, request);
  assert.deepEqual(f.store.messages(f.session.id).filter(m => historical.some(h => h.id === m.id)), historical);
  f.turns[1].finish();
  await f.broker.idle();
  assert.equal(f.executions.length, 1, "context never creates an edit on behalf of the model");
  assert.equal(f.images!.list(f.session.id).length, 1);
  assert.deepEqual(f.images!.get(f.session.id, f.job.id), completed);
  assert.equal(f.store.messages(f.session.id).filter(m => m.imageJobId === f.job.id).length, 1);
  const statusRequest = `What is the status of the saved job ${f.job.id}?`;
  const statusRunId = f.broker.enqueue(f.session.id, "message", statusRequest);
  await until(() => f.turns.length === 3);
  const statusContext = f.images!.context(f.session.id, statusRunId);
  assert.equal(f.turns[2].text, `${statusContext}\n\nCurrent user request (run ${statusRunId}):\n${statusRequest}`);
  assert.deepEqual(statuses(statusContext), statuses(context), "status follow-up retains exact old job and artifact provenance");
  f.turns[2].finish();
  await f.broker.idle();
  assert.equal(f.executions.length, 1);
  assert.deepEqual(f.images!.get(f.session.id, f.job.id), completed);
});

test("image intent: pending approval, status and continuation retain exact ID without inference or a held turn", async t => {
  const f = await fixture(t);
  const sameRun = f.images!.context(f.session.id, f.runId);
  assert.equal(statuses(sameRun)[0].relationToCurrentRun, "current_run");
  f.turns[0].finish();
  await f.broker.idle();
  const saved = f.images!.get(f.session.id, f.job.id);
  for (const request of [
    `What is the status of ${f.job.id}?`,
    `Continue the existing job ${f.job.id}; keep its identity and respect approval.`,
    "Delegate to a fresh child to edit the reference; keep the existing job identity.",
  ]) {
    const turnIndex = f.turns.length;
    const runId = f.broker.enqueue(f.session.id, "message", request);
    await until(() => f.turns.length === turnIndex + 1);
    const context = f.images!.context(f.session.id, runId);
    assert.equal(f.turns[turnIndex].text, `${context}\n\nCurrent user request (run ${runId}):\n${request}`);
    assert.equal(statuses(context)[0].id, f.job.id);
    assert.equal(statuses(context)[0].runId, f.runId);
    assert.equal(statuses(context)[0].state, "awaiting_approval");
    assert.equal(statuses(context)[0].relationToCurrentRun, "prior_run");
    assert.match(context, /new run ID alone does not require a new image job/);
    assert.match(context, /keep its exact ID and use image_status/);
    assert.match(context, /never resubmit to obtain status or resume approval/);
    f.turns[turnIndex].finish();
    await f.broker.idle();
    assert.equal(f.broker.currentImageRun(f.session.id), undefined);
    assert.deepEqual(f.images!.get(f.session.id, f.job.id), saved);
    assert.equal(f.executions.length, 0);
    assert.equal(f.images!.list(f.session.id).length, 1);
  }
});

test("image intent: owned-session boundary and prior handoff ordering preserve history without importing another session's jobs", async t => {
  const f = await fixture(t);
  f.turns[0].finish();
  await f.broker.idle();
  const other = await f.broker.createSession();
  assert.equal(f.images!.context(other.id, f.runId), "", "even another run ID cannot import jobs across sessions");
  assert.throws(() => f.images!.context("missing", f.runId), /not found/i);
  const summary = "Original handoff text\nwith its exact whitespace.  ";
  f.store.db.prepare("INSERT INTO handoffs(session_id,summary) VALUES(?,?)").run(f.session.id, summary);
  const request = "Check the saved image status.\n";
  const runId = f.broker.enqueue(f.session.id, "message", request);
  await until(() => f.turns.length === 2);
  assert.equal(f.turns[1].text, `Context from the prior chat (same workspace):\n${summary}\n\n${f.images!.context(f.session.id, runId)}\n\nCurrent user request (run ${runId}):\n${request}`);
  f.turns[1].finish();
  await f.broker.idle();
  const row = f.store.db.prepare("SELECT summary,delivered FROM handoffs WHERE session_id=?").get(f.session.id)!;
  assert.equal(row.summary, summary);
  assert.equal(row.delivered, 1);
  assert.equal(f.executions.length, 0);
  const otherRequest = "Original non-image request\n  unchanged";
  f.broker.enqueue(other.id, "message", otherRequest);
  await until(() => f.turns.length === 3);
  assert.equal(f.turns[2].text, otherRequest);
  f.turns[2].finish();
  await f.broker.idle();
});
