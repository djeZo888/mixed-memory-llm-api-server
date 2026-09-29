import test from "node:test";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import fs from "node:fs";
import { syncBuiltinESMExports } from "node:module";
import { CODEX_SPECIALIST_PINS, loadCodexSpecialists, validateCodexSpecialists } from "../src/codex-specialist-qualification.js";
const now = Date.parse("2026-09-29T15:25:00Z");
const sha = (s: string) => createHash("sha256").update(s).digest("hex");
const testedSource = "c863d4984f4a75c237b6de97b7ce40b8570fca81";
const targetSource = "ef3d863a6eb78918019a512fe2c5da6f61384882";
const testedPolicy = "aee39eea7f559a2f1c1b34c2d99818be1bc4e79ea6dba2ca7ec4075c8e34a956";
const root = "/etc/sova-qualification/";
/** Synthetic workflows only: no real acceptance receipt is generated/installed. */
function fixture() {
  const run = { result: "PASS", sessionId: "00000000-0000-0000-0000-000000000001", runId: "00000000-0000-0000-0000-000000000002",
    transcriptSha256: sha("synthetic transcript"), settlementSha256: sha("synthetic settlement") };
  const value: any = { schema: 2, kind: "retained-live-frontier-reviewed-compatibility", capability: "frontier",
    pins: { ...structuredClone(CODEX_SPECIALIST_PINS), toolPolicySha256: testedPolicy }, sourceRevision: testedSource,
    reviewedAt: "2026-09-29T15:05:00Z", workflows: { tool_continuation: { ...run }, codex_child: { ...run },
      minimax_delegation: { ...run, runId: "00000000-0000-0000-0000-000000000003" } }, review: { file: "review.json", sha256: "" } };
  const review: any = { schema: 1, kind: "reviewed-frontier-tool-policy-compatibility", testedSourceRevision: testedSource,
    testedPins: structuredClone(value.pins), targetSourceRevision: targetSource, targetPins: structuredClone(CODEX_SPECIALIST_PINS),
    workflowsSha256: sha(JSON.stringify(value.workflows)), reviewedAt: "2026-09-29T15:20:00Z", reviewedBy: "synthetic reviewer" };
  const record: any = { schema: 1, kind: "reviewed-codex-specialists", pins: structuredClone(CODEX_SPECIALIST_PINS), image: null,
    frontier: { file: "frontier.json", sha256: "" } };
  const documents: Record<string, { text: string; value: any }> = {};
  const refresh = () => {
    for (const [name, doc] of [["review.json", review], ["frontier.json", value], ["record.json", record]] as const) {
      const text = JSON.stringify(doc); documents[name] = { text, value: doc };
      if (name === "review.json" && value.review) value.review.sha256 = sha(text);
      if (name === "frontier.json") record.frontier.sha256 = sha(text);
    }
  };
  const bindWorkflows = () => { review.workflowsSha256 = sha(JSON.stringify(value.workflows)); refresh(); };
  const read = (name: string) => { if (!documents[name]) throw Error("missing"); return documents[name]; };
  refresh(); return { record, value, review, documents, refresh, bindWorkflows, read };
}
test("explicit frontier reuse preserves actual old pins and runs and reports distinct live/reviewed identity", () => {
  const f = fixture(), before = JSON.stringify(f.value), q = validateCodexSpecialists(f.record, f.read, now);
  assert.equal(q.frontierResponsesQualified, true); assert.equal(q.imageJobsQualified, false);
  assert.equal(JSON.stringify(f.value), before); assert.equal(f.value.pins.toolPolicySha256, testedPolicy);
  assert.deepEqual(f.value.workflows.tool_continuation, f.value.workflows.codex_child);
  for (const expected of [testedSource, targetSource, testedPolicy, CODEX_SPECIALIST_PINS.toolPolicySha256, f.value.review.sha256,
    f.record.frontier.sha256, "Reused live", "compatibility reviewed", "reviewed implementation basis", "no new target live execution", "current backend readiness is checked separately", "950000 is configured capacity"])
    assert.ok(q.capabilities.frontier.reason.includes(expected), expected);
});
test("schema1 current pins pass but original old tool policy cannot implicitly carry", () => {
  const f = fixture(); delete f.value.sourceRevision; delete f.value.review;
  f.value.schema = 1; f.value.kind = "retained-live-specialist-acceptance"; f.refresh();
  assert.throws(() => validateCodexSpecialists(f.record, f.read, now));
  f.value.pins = structuredClone(CODEX_SPECIALIST_PINS); f.refresh();
  assert.equal(validateCodexSpecialists(f.record, f.read, now).frontierResponsesQualified, true);
});
const invalid: Record<string, (f: ReturnType<typeof fixture>) => void> = {
  "unknown old policy": f => { f.value.pins.toolPolicySha256 = "0".repeat(64); f.review.testedPins = structuredClone(f.value.pins); },
  "relabelled old evidence": f => { f.value.pins.toolPolicySha256 = CODEX_SPECIALIST_PINS.toolPolicySha256; f.review.testedPins = structuredClone(f.value.pins); },
  "future target policy": f => f.review.targetPins.toolPolicySha256 = "0".repeat(64),
  "unknown tested source": f => { f.value.sourceRevision = "0".repeat(40); f.review.testedSourceRevision = f.value.sourceRevision; },
  "unknown target source": f => f.review.targetSourceRevision = "0".repeat(40),
  "mismatched source review": f => f.review.testedSourceRevision = targetSource,
  "mismatched pin review": f => f.review.testedPins.toolPolicySha256 = "0".repeat(64),
  "changed target logical policy": f => f.review.targetPins.policy = "other",
  "changed outer tool policy": f => f.record.pins.toolPolicySha256 = testedPolicy,
  "missing review": f => delete f.value.review,
  "missing reviewer": f => delete f.review.reviewedBy,
  "blank reviewer": f => f.review.reviewedBy = " ",
  "missing review time": f => delete f.review.reviewedAt,
  "invalid review time": f => f.review.reviewedAt = "invalid",
  "future review time": f => f.review.reviewedAt = "2099-01-01T00:00:00Z",
  "review predates evidence": f => f.review.reviewedAt = "2026-09-29T15:04:00Z",
  "future evidence time": f => f.value.reviewedAt = "2099-01-01T00:00:00Z",
  "invalid evidence time": f => f.value.reviewedAt = null,
  "wrong review kind": f => f.review.kind = "generic-approval",
  "wrong review schema": f => f.review.schema = 2,
  "wrong evidence kind": f => f.value.kind = "retained-live-specialist-acceptance",
  "wrong evidence schema": f => f.value.schema = 3,
  "missing source": f => delete f.value.sourceRevision,
  "extra evidence field": f => f.value.ready = true,
  "extra review field": f => f.review.allowFuture = true,
  "extra reference field": f => f.value.review.allowFuture = true,
  "extra tested pin": f => { f.value.pins.allowFuture = true; f.review.testedPins = structuredClone(f.value.pins); },
  "extra target pin": f => f.review.targetPins.allowFuture = true,
  "missing tested tool pin": f => delete f.value.pins.toolPolicySha256,
  "missing workflow": f => { delete f.value.workflows.minimax_delegation; f.bindWorkflows(); },
  "extra workflow": f => { f.value.workflows.image = f.value.workflows.codex_child; f.bindWorkflows(); },
  "failed workflow with reviewed digest": f => { f.value.workflows.codex_child.result = "FAIL"; f.bindWorkflows(); },
  "missing settlement with reviewed digest": f => { delete f.value.workflows.codex_child.settlementSha256; f.bindWorkflows(); },
  "extra workflow field": f => { f.value.workflows.codex_child.ready = true; f.bindWorkflows(); },
  "bad workflow identity": f => { f.value.workflows.codex_child.runId = "unknown"; f.bindWorkflows(); },
  "bad transcript digest": f => { f.value.workflows.codex_child.transcriptSha256 = "unknown"; f.bindWorkflows(); },
  "unreviewed run": f => f.value.workflows.codex_child.runId = "00000000-0000-0000-0000-000000000009",
  "corrupt workflow digest": f => f.review.workflowsSha256 = "0".repeat(64),
  "review traversal": f => f.value.review.file = "../review.json",
  "absolute review path": f => f.value.review.file = "/tmp/review.json",
  "missing review file": f => f.value.review.file = "absent.json",
};
for (const [name, mutate] of Object.entries(invalid)) test(`${name} rejects even with rehashed outer evidence`, () => {
  const f = fixture(); mutate(f); f.refresh(); assert.throws(() => validateCodexSpecialists(f.record, f.read, now));
});
test("every non-tool pin domain rejects changes including model/runtime/logical provider/source owner/image", () => {
  for (const path of [["engine", "sourceRevision"], ["policy"], ["frontier", "runtimeRevision"], ["frontier", "profile", "model"],
    ["frontier", "profile", "reasoning"], ["frontier", "profile", "parallelToolCalls"], ["qwen", "ownerPolicy", "controlAdapterSha256"],
    ["qwen", "modelRevision"], ["qwen", "profile", "contextWindow"], ["image", "runtimeImage"]]) {
    const f = fixture(); let p = f.value.pins;
    for (const key of path.slice(0, -1)) p = p[key]; p[path.at(-1)!] = "changed";
    f.review.testedPins = structuredClone(f.value.pins); f.refresh();
    assert.throws(() => validateCodexSpecialists(f.record, f.read, now), path.join("."));
  }
});
test("corrupt review bytes or reference hash rejects", () => {
  for (const kind of ["bytes", "hash"]) {
    const f = fixture();
    if (kind === "bytes") f.documents["review.json"].text += " ";
    else { f.value.review.sha256 = "0".repeat(64); f.documents["frontier.json"].text = JSON.stringify(f.value); f.record.frontier.sha256 = sha(f.documents["frontier.json"].text); }
    assert.throws(() => validateCodexSpecialists(f.record, f.read, now));
  }
});
test("frontier compatibility cannot qualify image even with relabelled capability", () => {
  for (const capability of ["frontier", "image"]) {
    const f = fixture(); f.value.capability = capability; f.refresh(); f.record.image = f.record.frontier; f.record.frontier = null;
    assert.throws(() => validateCodexSpecialists(f.record, f.read, now));
  }
});
test("protected loader enforces boundaries for record, evidence and review", t => {
  const f = fixture(); let unsafeFile = "", defect = "", current = ""; const opened: string[] = [];
  const textFor = (p: string) => f.documents[p.slice(root.length)]?.text ?? "";
  const fileStat = (p: string) => ({ uid: p === unsafeFile && defect === "owner" ? 1000 : 0,
    mode: p === unsafeFile && defect === "writable" ? 0o100666 : 0o100644,
    nlink: p === unsafeFile && defect === "hardlink" ? 2 : 1, ino: 7, dev: 1,
    size: p === unsafeFile && defect === "size" ? 65537 : Buffer.byteLength(textFor(p)), isFile: () => true });
  const mocks = [
    t.mock.method(fs, "realpathSync", (p: string) => p === unsafeFile && defect === "symlink" ? "/tmp/fixture.json" : p),
    t.mock.method(fs, "lstatSync", (p: string) => p.endsWith(".json") ? fileStat(p) : ({ uid: 0, mode: defect === "ancestry" ? 0o40777 : 0o40755, isDirectory: () => true })),
    t.mock.method(fs, "openSync", (p: string, flags: number) => { assert.equal(flags, fs.constants.O_RDONLY | fs.constants.O_NOFOLLOW); opened.push(p); current = p; return 123; }),
    t.mock.method(fs, "fstatSync", () => ({ ...fileStat(current), ino: current === unsafeFile && defect === "replaced" ? 8 : 7 })),
    t.mock.method(fs, "readFileSync", () => textFor(current)), t.mock.method(fs, "closeSync", () => {}),
  ];
  syncBuiltinESMExports(); t.after(() => { for (const m of mocks) m.mock.restore(); syncBuiltinESMExports(); });
  assert.equal(loadCodexSpecialists(root + "record.json").frontierResponsesQualified, true);
  assert.deepEqual(opened, [root + "record.json", root + "frontier.json", root + "review.json"]);
  for (const name of ["record.json", "frontier.json", "review.json"]) for (const bad of ["owner", "writable", "hardlink", "symlink", "size", "replaced", "ancestry"]) {
    unsafeFile = root + name; defect = bad; const q = loadCodexSpecialists(root + "record.json");
    assert.equal(q.frontierResponsesQualified || q.imageJobsQualified, false, `${name}: ${bad}`);
  }
  defect = ""; opened.length = 0;
  for (const p of [undefined, "/tmp/record.json", root + "../record.json", root + "sub/record.json"]) assert.equal(loadCodexSpecialists(p).frontierResponsesQualified, false);
  assert.deepEqual(opened, []);
});

test("historical H033 target source and policy reject after exact H034 replacement", () => {
  const f = fixture();
  f.review.targetSourceRevision = "eb8ed4283d83cfbdbcc97dfbeec7056d2538c05e";
  f.review.targetPins.toolPolicySha256 = "b71c0ab62310df062f9df2eba464ef1c0fffe1a108d07778b50d7f3ebb4653c5";
  f.refresh();
  assert.throws(() => validateCodexSpecialists(f.record, f.read, now));
});
