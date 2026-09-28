import assert from "node:assert/strict";
import test from "node:test";
import { chmodSync, existsSync, linkSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, realpathSync, rmSync, statSync, symlinkSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createResponsesDiagnostics } from "../src/codex-diagnostics.js";
import { responsesFailureCode } from "../src/codex-responses.js";

const event = {
  requestId: "1dd5841e-0e5b-4a72-9b6f-1a279ec50931",
  sessionId: "d367d797-774f-4733-8222-9fe40c0551e1",
  lane: "qwen3.8-27b-gpu0", phase: "stream" as const,
  code: responsesFailureCode(new Error("Unqualified reasoning field")),
};
function fixture(t: any) {
  const dir = mkdtempSync(join(realpathSync(tmpdir()), "h021-diagnostics-"));
  t.after(() => rmSync(dir, { recursive: true, force: true }));
  const path = join(dir, "failures.jsonl");
  return { dir, path, log: createResponsesDiagnostics(path) };
}

test("logs only reviewed metadata, never raw fields or secrets", t => {
  const f = fixture(t);
  const secret = "PRIVATE_MODEL_TEXT_TOKEN_PAYLOAD";
  f.log({ ...event, message: secret, chunk: Buffer.from(secret), token: secret, payload: { secret } } as any);
  const text = readFileSync(f.path, "utf8"), record = JSON.parse(text);
  assert.doesNotMatch(text, new RegExp(secret));
  assert.deepEqual(Object.keys(record).sort(), ["code", "lane", "phase", "requestId", "sessionId", "time"]);
  assert.deepEqual({ ...record, time: undefined }, { ...event, time: undefined });
  assert.match(record.time, /^\d{4}-\d{2}-\d{2}T/);
  assert.equal(statSync(f.path).mode & 0o777, 0o600);
});

test("unsafe codes, owner IDs and lanes are discarded; malformed input cannot throw", t => {
  const f = fixture(t), secret = "PRIVATE_SECRET\nINJECTED";
  f.log({ ...event, code: secret, requestId: secret, sessionId: "x".repeat(10000), lane: secret });
  const text = readFileSync(f.path, "utf8"), record = JSON.parse(text);
  assert.deepEqual({ ...record, time: undefined }, { requestId: null, sessionId: null, lane: null, phase: "stream", code: "unqualified_output", time: undefined });
  assert.doesNotMatch(text, /PRIVATE_SECRET|INJECTED/);
  assert.doesNotThrow(() => f.log(null as any));
  assert.doesNotThrow(() => f.log({ ...event, get code() { throw new Error(secret); } }));
  f.log({ ...event, phase: secret } as any);
  assert.equal(readFileSync(f.path, "utf8"), text);
});

test("both files remain private and bounded across repeated rotations", t => {
  const f = fixture(t);
  writeFileSync(f.path, "", { mode: 0o644 });
  for (let i = 0; i < 900; i++) f.log(event);
  assert.deepEqual(readdirSync(f.dir).sort(), ["failures.jsonl", "failures.jsonl.1"]);
  for (const path of [f.path, f.path + ".1"]) {
    assert.equal(statSync(path).mode & 0o777, 0o600);
    assert.ok(statSync(path).size > 0 && statSync(path).size <= 65536);
    for (const line of readFileSync(path, "utf8").trim().split("\n")) assert.equal(JSON.parse(line).code, event.code);
  }
  writeFileSync(f.path, "x".repeat(70000));
  f.log(event);
  assert.ok(statSync(f.path).size < 65536);
});

test("rejects file, parent and rotation symlinks without modifying their targets", t => {
  const f = fixture(t), target = join(f.dir, "protected-target");
  writeFileSync(target, "UNCHANGED");
  symlinkSync(target, f.path);
  assert.doesNotThrow(() => f.log(event));
  assert.equal(readFileSync(target, "utf8"), "UNCHANGED");
  rmSync(f.path);
  const realDir = join(f.dir, "real"), linkedDir = join(f.dir, "linked");
  mkdirSync(realDir, { mode: 0o700 }); symlinkSync(realDir, linkedDir);
  createResponsesDiagnostics(join(linkedDir, "log"))(event);
  assert.equal(existsSync(join(realDir, "log")), false);
  writeFileSync(f.path, "x".repeat(65535));
  symlinkSync(target, f.path + ".1");
  f.log(event);
  assert.equal(readFileSync(target, "utf8"), "UNCHANGED");
  assert.equal(statSync(f.path).size, 65535);
});

test("rejects hardlinks and writable host directory; I/O failure does not escape", t => {
  const f = fixture(t), target = join(f.dir, "target");
  writeFileSync(target, "UNCHANGED"); linkSync(target, f.path);
  assert.doesNotThrow(() => f.log(event));
  assert.equal(readFileSync(target, "utf8"), "UNCHANGED");
  rmSync(f.path); chmodSync(f.dir, 0o777);
  f.log(event); assert.equal(existsSync(f.path), false);
  assert.doesNotThrow(() => createResponsesDiagnostics(join(f.dir, "missing", "log"))(event));
});
