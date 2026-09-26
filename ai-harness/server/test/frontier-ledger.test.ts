import test from "node:test";
import assert from "node:assert/strict";
import { DatabaseSync } from "node:sqlite";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { FrontierLedger } from "../src/frontier-ledger.js";
import {
  FRONTIER_MODEL,
  FRONTIER_REVISION,
  frontierConfiguration,
  type FrontierRecord,
} from "../src/frontier.js";
test("actual SQLite restart retains owner identity, cancels queued work, quarantines active and preserves settled results", () => {
  const dir = mkdtempSync(join(tmpdir(), "frontier-ledger-"));
  let db = new DatabaseSync(join(dir, "journal.sqlite"));
  try {
    const first = new FrontierLedger(db);
    for (const state of ["queued", "active", "settled"] as const)
      first.record({
        id: state,
        sessionId: "owner",
        state,
        model: FRONTIER_MODEL,
        contextWindow: 480000,
        promptTokens: 123,
        reservedOutput: 65536,
        updatedAt: state,
      });
    first.record({
      id: "foreign",
      sessionId: "other",
      state: "active",
      model: FRONTIER_MODEL,
      contextWindow: 480000,
      updatedAt: "z",
    });
    db.close();
    db = new DatabaseSync(join(dir, "journal.sqlite"));
    const restored = new FrontierLedger(db);
    const records = restored.latest("owner");
    assert.equal(records.length, 3);
    assert.equal(records.find((r) => r.id === "queued")?.state, "cancelled");
    assert.equal(records.find((r) => r.id === "active")?.state, "quarantined");
    assert.equal(records.find((r) => r.id === "settled")?.state, "settled");
    assert(records.every((r) => r.sessionId === "owner"));
    assert.equal(records.find((r) => r.id === "active")?.promptTokens, 123);
  } finally {
    db.close();
    rmSync(dir, { recursive: true, force: true });
  }
});
test("missing, malformed, unsupported or unqualified frontier config cannot activate; exact frozen config can", () => {
  const valid = {
    model: FRONTIER_MODEL,
    qualified: true,
    contextWindow: 480000,
    maxOutputTokens: 65536,
    tokenizerRevision: FRONTIER_REVISION,
    templateRevision: FRONTIER_REVISION,
    maxPromptTokens: 16000,
  };
  assert.equal(frontierConfiguration(valid)?.contextWindow, 480000);
  for (const v of [
    null,
    {},
    [],
    { ...valid, qualified: false },
    { ...valid, contextWindow: "480000" },
    { ...valid, contextWindow: 1000000 },
    { ...valid, templateRevision: "e".repeat(40) },
    { ...valid, maxPromptTokens: 0 },
    { ...valid, maxPromptTokens: 480001 },
  ])
    assert.equal(frontierConfiguration(v), undefined);
});
