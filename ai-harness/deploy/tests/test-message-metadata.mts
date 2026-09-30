import assert from "node:assert/strict";
import test from "node:test";
import { pathToFileURL } from "node:url";
import { isAbsolute, join } from "node:path";
import { readFileSync } from "node:fs";
import { createHash } from "node:crypto";
const source = process.env.AI_HARNESS_MINIMAX_SOURCE;
assert.ok(
  source && isAbsolute(source),
  "Set AI_HARNESS_MINIMAX_SOURCE to ae65651 plus the reviewed 0001..0008 patches",
);
const identity = JSON.parse(
  readFileSync(new URL("../patches/identity.json", import.meta.url), "utf8"),
);
for (const rel of [
  "packages/tui/src/acp/agent.ts",
  "packages/tui/src/acp/updates.ts",
  "packages/tui/src/acp/extensions.ts",
  "packages/tui/src/runtime/adapters/delegation-access.ts",
  "packages/tui/src/runtime/port.ts",
]) {
  const pin = identity.files.find((f: { path: string }) => f.path === rel);
  assert.equal(
    createHash("sha256")
      .update(readFileSync(join(source, rel)))
      .digest("hex"),
    pin.patchedSha256,
    rel,
  );
}
const { TuiAcpUpdateProjector, tuiAcpMessageMetadata } = await import(
  pathToFileURL(join(source, "packages/tui/src/acp/updates.ts")).href
);
const { TuiDelegationAccess } = await import(
  pathToFileURL(
    join(source, "packages/tui/src/runtime/adapters/delegation-access.ts"),
  ).href
);

test("native metadata requires both identities; actual complete metadata survives prior streaming and is never synthesized from text", () => {
  const projector = new TuiAcpUpdateProjector();
  const delta = {
    type: "delta",
    messageId: "m",
    turnId: "t",
    content: "visible",
  } as const;
  assert.equal(tuiAcpMessageMetadata(delta, "s")!.kind, null);
  assert.equal(tuiAcpMessageMetadata(delta, "s")!.status, "streaming");
  assert.equal(projector.project(delta).length, 1);
  const complete = {
    type: "message",
    message: {
      id: "m",
      turnId: "t",
      role: "assistant",
      kind: "final",
      finishReason: "stop",
      content: "visible",
    },
  } as const;
  assert.deepEqual(projector.project(complete), []);
  assert.deepEqual(tuiAcpMessageMetadata(complete, "s"), {
    schemaVersion: 1,
    sessionId: "s",
    messageId: "m",
    turnId: "t",
    kind: "final",
    finishReason: "stop",
    status: "completed",
  });
  assert.equal(
    tuiAcpMessageMetadata(
      { type: "delta", content: "I am final" } as const,
      "s",
    ),
    undefined,
  );
});

test("native thought-only streaming followed by full visible answer retains all visible parts exactly once", () => {
  const p = new TuiAcpUpdateProjector();
  p.project({
    type: "delta",
    messageId: "m",
    turnId: "t",
    thinking: "actual thought",
  });
  const event = {
    type: "message",
    message: {
      id: "m",
      turnId: "t",
      role: "assistant",
      parts: [
        { type: "thinking", content: "actual thought" },
        { type: "text", content: "part one " },
        { type: "text", content: "part two" },
      ],
      finishReason: "stop",
    },
  } as const;
  const projected = p.project(event as any);
  assert.deepEqual(
    projected.map((u) => u.sessionUpdate),
    ["agent_message_chunk", "agent_message_chunk"],
  );
  assert.equal(
    projected.map((u: any) => u.content.text).join(""),
    "part one part two",
  );
  assert.deepEqual(p.project(event as any), []);
});

test("native snapshot completeness distinguishes complete pages from missing/repeated cursor and page limit", async () => {
  const session = (id: string, parent = "root") => ({
    sessionId: id,
    parentSessionId: parent,
    sessionType: "branch",
    sessionKind: "task",
    status: "running",
  });
  let pages = 0;
  const full = new TuiDelegationAccess({
    listSessionPage: async () =>
      ++pages === 1
        ? { sessions: [session("c")], hasMore: true, nextCursor: "next" }
        : { sessions: [session("grandchild", "c")], hasMore: false },
    abortSession: async () => false,
  } as any);
  assert.deepEqual(
    (await full.getSnapshot("root")).members.map((m) => m.sessionId),
    ["c", "grandchild"],
  );
  assert.equal(pages, 2);
  const done = await full.getSnapshot("root");
  assert.equal(done.complete, true);
  for (const mode of ["missing", "repeat", "limit"]) {
    let calls = 0;
    const cut = new TuiDelegationAccess({
      listSessionPage: async () => ({
        sessions: [session(`child-${calls++}`)],
        hasMore: true,
        ...(mode === "missing"
          ? {}
          : { nextCursor: mode === "repeat" ? "same" : String(calls) }),
      }),
      abortSession: async () => false,
    } as any);
    assert.equal((await cut.getSnapshot("root")).complete, false);
    assert.ok(calls <= 20);
  }
});
