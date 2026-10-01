import test from "node:test";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { CODEX_SPECIALIST_PINS, loadCodexSpecialists, validateCodexSpecialists } from "../src/codex-specialist-qualification.js";
import { codexCapabilities } from "../src/codex-capabilities.js";
import { composeCodexHost } from "../src/codex-host.js";
import { createGateway } from "../src/gateway.js";
const now = Date.parse("2026-09-29T07:00:00Z");
const sha = (s: string) => createHash("sha256").update(s).digest("hex");
/** Synthetic only. No production receipt or real acceptance claim is generated. */
function fixture() {
  let run = 0;
  const evidence = Object.fromEntries(Object.entries({ image: ["generation", "followup_edit", "child"], frontier: ["tool_continuation", "codex_child", "minimax_delegation"] }).map(([capability, cases]) => {
    const value = { schema: 1, kind: "retained-live-specialist-acceptance", capability,
      pins: structuredClone(CODEX_SPECIALIST_PINS), reviewedAt: "2026-09-29T06:00:00Z", workflows: Object.fromEntries(cases.map(name => [name, {
        result: "PASS", sessionId: "00000000-0000-0000-0000-000000000001",
        runId: `00000000-0000-0000-0000-${String(++run).padStart(12, "0")}`,
        transcriptSha256: sha("synthetic transcript"), settlementSha256: sha("synthetic settlement"),
      }])) };
    return [`fixture-${capability}.json`, { value, text: JSON.stringify(value) }];
  }));
  const record: any = { schema: 1, kind: "reviewed-codex-specialists", pins: structuredClone(CODEX_SPECIALIST_PINS),
    image: { file: "fixture-image.json", sha256: sha(evidence["fixture-image.json"].text) },
    frontier: { file: "fixture-frontier.json", sha256: sha(evidence["fixture-frontier.json"].text) } };
  return { record, evidence, read: (name: string) => { if (!evidence[name]) throw Error("missing"); return evidence[name]; },
    refresh: (capability: string) => { const e = evidence[`fixture-${capability}.json`]; e.text = JSON.stringify(e.value); record[capability].sha256 = sha(e.text); } };
}
test("absent, task-owned, traversal, missing and malformed protected paths close both specialists", () => {
  for (const path of [undefined, "/tmp/fixture.json", "/etc/sova-qualification/../fixture.json", "/etc/sova-qualification/sub/fixture.json", "/etc/sova-qualification/missing.json"])
    assert.equal(loadCodexSpecialists(path).frontierResponsesQualified || loadCodexSpecialists(path).imageJobsQualified, false);
});
test("reviewed pins plus exact retained cases drive host gates and capability metadata together", () => {
  const f = fixture(), q = validateCodexSpecialists(f.record, f.read, now);
  const host = composeCodexHost("/trusted/run-codex.sh", () => undefined, {
    protocolQualified: true, rootlessQualified: true, verifyLane: async () => { throw Error("not observed"); },
    nativeDelegationQualified: true,
    imageJobsQualified: q.imageJobsQualified ? true : undefined,
    frontierResponsesQualified: q.frontierResponsesQualified ? true : undefined, capabilities: q.capabilities,
  });
  const caps = codexCapabilities(host.runtime.capabilities, host.runtime);
  assert.equal(host.responses?.frontierQualified, true);
  assert.equal(host.runtime.imageToolEnabled, true);
  assert.deepEqual(host.runtime.qualifiedChildModels, ["qwen3.8-27b", "mimo-v2.6-pro-rl"]);
  for (const capability of ["image", "frontier"] as const) {
    assert.equal(caps[capability].supported, true); assert.equal(caps[capability].qualification, "live");
    assert.match(caps[capability].reason, /current .*readiness is checked separately/);
    assert.doesNotMatch(caps[capability].reason, /acceptance pending/);
  }
});
test("partial qualification is independent; exact scoped acceptance remains separate", () => {
  const f = fixture(); f.record.image = null;
  const q = validateCodexSpecialists(f.record, f.read, now);
  assert.equal(q.imageJobsQualified, false); assert.equal(q.frontierResponsesQualified, true);
  const host = composeCodexHost("/trusted/run-codex.sh", () => undefined, {
    protocolQualified: true, rootlessQualified: true, verifyLane: async () => { throw Error("not observed"); },
    imageAcceptance: id => id === "owned", frontierAcceptance: id => id === "owned", capabilities: q.capabilities,
  });
  assert.equal(host.runtime.imageToolEnabled, false); assert.equal(host.responses?.frontierQualified, undefined);
  assert.equal(host.responses?.frontierAcceptance?.("unrelated"), false);
});
test("image qualification binds the installed OCI manifest/config, separately from its parent", () => {
  const binding = JSON.parse(readFileSync(new URL("../../../configs/runtimes/h005-runtime-binding.json", import.meta.url), "utf8")).image;
  assert.equal(CODEX_SPECIALIST_PINS.image.runtimeImage, binding.image_id);
  assert.equal(CODEX_SPECIALIST_PINS.image.runtimeImageIdDomain, binding.image_id_domain);
  assert.equal(CODEX_SPECIALIST_PINS.image.runtimeConfigDigest, binding.image_config_digest);
  assert.equal(CODEX_SPECIALIST_PINS.image.parentImageReference, binding.parent_image_reference);
  assert.equal(CODEX_SPECIALIST_PINS.image.runtimeRevision, binding.upstream_revision);
  assert.notEqual(CODEX_SPECIALIST_PINS.image.runtimeImage, binding.parent_image_reference);
});
for (const [name, mutate] of Object.entries<Record<string, (f: ReturnType<typeof fixture>) => void>[string]>({
  "foreign engine": f => f.record.pins.engine.sourceRevision = "0".repeat(40),
  "foreign policy": f => f.record.pins.policy = "foreign",
  "wrong Qwen profile": f => f.record.pins.qwen.profile.contextWindow = 200000,
  "wrong MiMo model": f => f.record.pins.frontier.profile.model = "glm-5.3-flash",
  "wrong MiMo template": f => f.record.pins.frontier.templateSha256 = "0".repeat(64),
  "wrong image revision": f => f.record.pins.image.modelRevision = "0".repeat(40),
  "parent image is not tested runtime": f => f.record.pins.image.runtimeImage = f.record.pins.image.parentImageReference,
  "wrong image identity domain": f => f.record.pins.image.runtimeImageIdDomain = "config_digest",
  "wrong image config": f => f.record.pins.image.runtimeConfigDigest = "sha256:" + "0".repeat(64),
  "wrong image parent": f => f.record.pins.image.parentImageReference = "sha256:" + "0".repeat(64),
  "stale tool policy": f => f.record.pins.toolPolicySha256 = "dd0ff12a651db4cc8521cddb8e5094c5a197ca87cef6b7ec797343da67d9f1ec",
  "missing tool policy": f => delete f.record.pins.toolPolicySha256,
  "parent-only retained evidence": f => { f.evidence["fixture-image.json"].value.pins.image.runtimeImage = f.evidence["fixture-image.json"].value.pins.image.parentImageReference; f.refresh("image"); },
  "changed output budget": f => f.record.pins.frontier.profile.maxOutputTokens = 512,
  "changed compaction": f => f.record.pins.frontier.profile.autoCompactTokenLimit = 880000,
  "changed thinking": f => f.record.pins.frontier.profile.reasoning = "none",
  "changed parallel policy": f => f.record.pins.frontier.profile.parallelToolCalls = true,
  "extra field": f => f.record.ready = true,
  "wrong digest": f => f.record.image.sha256 = "0".repeat(64),
  "unsafe evidence path": f => f.record.image.file = "../fixture-image.json",
  "missing evidence": f => f.record.image.file = "absent.json",
  "stale evidence pins": f => { (f.evidence["fixture-image.json"].value.pins.engine as any).version = "old"; f.refresh("image"); },
  "future evidence": f => { f.evidence["fixture-image.json"].value.reviewedAt = "2099-01-01T00:00:00Z"; f.refresh("image"); },
  "missing required workflow": f => { delete f.evidence["fixture-image.json"].value.workflows.child; f.refresh("image"); },
  "non-PASS result": f => { f.evidence["fixture-image.json"].value.workflows.child.result = "NOT_TESTED"; f.refresh("image"); },
  "missing settlement": f => { f.evidence["fixture-image.json"].value.workflows.child.settlementSha256 = ""; f.refresh("image"); },
})) test(`${name} fails closed`, () => { const f = fixture(); mutate(f); assert.throws(() => validateCodexSpecialists(f.record, f.read, now)); });
test("qualification cannot create or mark an unavailable frontier backend ready", async () => {
  const f = fixture(), q = validateCodexSpecialists(f.record, f.read, now);
  const host = composeCodexHost("/trusted/run-codex.sh", () => undefined, {
    protocolQualified: true, rootlessQualified: true, verifyLane: async () => { throw Error("not observed"); },
    frontierResponsesQualified: q.frontierResponsesQualified ? true : undefined, capabilities: q.capabilities,
  });
  const g = createGateway({ upstreamKey: "fixture-only", selectedFrontierModel: "mimo-v2.6-pro-rl", ownership: { recoveryReady: true, onRequestState: () => {} }, responses: host.responses });
  const token = g.issueToken("fixture-session", "codex");
  const response = await g.app.inject({ method: "POST", url: "/v1/responses", headers: { authorization: `Bearer ${token}` }, payload: { model: "mimo-v2.6-pro-rl", input: "fixture only" } });
  assert.equal(response.statusCode, 503);
  assert.equal(response.json().error.code, "codex_frontier_unqualified");
  assert.notEqual(g.frontierSnapshot().state, "active");
  await g.close();
});

test("one retained Codex child run can qualify its tool continuation and child workflow", () => {
 const f=fixture(),w=f.evidence["fixture-frontier.json"].value.workflows;
 w.tool_continuation.runId=w.codex_child.runId;f.refresh("frontier");
 assert.equal(validateCodexSpecialists(f.record,f.read,now).frontierResponsesQualified,true);
});
