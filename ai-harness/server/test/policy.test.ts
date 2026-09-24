import test from "node:test";
import assert from "node:assert/strict";
import { PassThrough, Readable, Writable } from "node:stream";
import { mkdtemp, mkdir, rm, symlink } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import * as acp from "@agentclientprotocol/sdk";
import {
  reviewedToolPermission,
  REVIEWED_SKILLS,
  REVIEWED_POLICY_ASK,
  REVIEWED_POLICY_DENY,
  TRUSTED_BROWSER_INSTRUCTION,
} from "../src/policy.js";
import { scopedPath } from "../src/engine.js";

const SEARCH = "mcp__searxng__searxng_search";
async function fixture(t: test.TestContext) {
  const root = await mkdtemp(join(tmpdir(), "h001-policy-"));
  const workspace = join(root, "workspace");
  await mkdir(workspace);
  await symlink(root, join(workspace, "outside"));
  const upstream = new PassThrough();
  const downstream = new PassThrough();
  const client = new acp.ClientSideConnection(
    () => ({
      async requestPermission(request) {
        const permitted = await reviewedToolPermission(
          workspace,
          request,
          scopedPath,
        );
        return {
          outcome: {
            outcome: "selected",
            optionId: permitted === true ? "yes" : "no",
          },
        };
      },
      async sessionUpdate() {},
    }),
    acp.ndJsonStream(
      Writable.toWeb(upstream),
      Readable.toWeb(downstream) as unknown as Parameters<
        typeof acp.ndJsonStream
      >[1],
    ),
  );
  const agent = new acp.AgentSideConnection(
    () => ({
      async initialize() {
        return { protocolVersion: acp.PROTOCOL_VERSION, agentCapabilities: {} };
      },
      async newSession() {
        return { sessionId: "fixture-native" };
      },
      async prompt() {
        return { stopReason: "end_turn" };
      },
      async cancel() {},
      async authenticate() {
        return {};
      },
    }),
    acp.ndJsonStream(
      Writable.toWeb(downstream),
      Readable.toWeb(upstream) as unknown as Parameters<
        typeof acp.ndJsonStream
      >[1],
    ),
  );
  await client.initialize({
    protocolVersion: acp.PROTOCOL_VERSION,
    clientCapabilities: {},
  });
  await client.newSession({ cwd: workspace, mcpServers: [] });
  t.after(async () => {
    upstream.end();
    downstream.end();
    await rm(root, { recursive: true, force: true });
  });
  let id = 0;
  const permit = async (name: string, rawInput: unknown) => {
    const response = await agent.requestPermission({
      sessionId: "fixture-native",
      toolCall: {
        toolCallId: `${++id}`,
        title: "Misleading safe title is not authority",
        name,
        rawInput,
      },
      options: [
        { optionId: "yes", kind: "allow_once", name: "Allow once" },
        { optionId: "no", kind: "reject_once", name: "Reject once" },
      ],
    });
    return (
      response.outcome.outcome === "selected" &&
      response.outcome.optionId === "yes"
    );
  };
  return { permit, workspace };
}

test("official SDK permission transport admits reviewed skills/direct search and denies all wrappers", async (t) => {
  const { permit } = await fixture(t);
  for (const name of REVIEWED_SKILLS)
    assert.equal(await permit("skill", { name }), true, name);
  for (const name of [
    "unknown",
    "pdf/../../secret",
    "/pdf",
    "code_review",
    "plugin:pdf",
  ])
    assert.equal(await permit("skill", { name }), false, name);
  assert.equal(await permit("skill", { name: "pdf", path: "/etc" }), false);
  assert.equal(await permit(SEARCH, { query: "datasheet" }), true);
  assert.equal(await permit("mcp__searxng__admin", {}), false);
  assert.equal(await permit("mcp__foreign__send", {}), false);
  assert.equal(
    await permit("mcp_invoke", {
      tool_name: SEARCH,
      arguments: { query: "datasheet" },
    }),
    false,
  );
  assert.equal(await permit("mcp_invoke", { tool_name: SEARCH }), false);
  for (const input of [
    { tool_name: "mcp__foreign__send", arguments: {} },
    { tool_ref: SEARCH, arguments: {} },
    { tool_name: SEARCH, tool_ref: "opaque", arguments: {} },
    { tool_name: SEARCH, arguments_json: "{}" },
    { tool_name: SEARCH, arguments: [] },
    { target: SEARCH, arguments: {} },
  ])
    assert.equal(
      await permit("mcp_invoke", input),
      false,
      JSON.stringify(input),
    );
  assert.equal(await permit("tool_search", { query: SEARCH }), false);
  assert.equal(
    await permit("tool_search", { regex: `^${SEARCH}$`, top_k: 1 }),
    false,
  );
  for (const input of [
    { query: "foreign" },
    { regex: ".*" },
    { query: SEARCH, regex: ".*" },
    { query: SEARCH, top_k: -1 },
    { tool_name: SEARCH },
    {},
  ])
    assert.equal(await permit("tool_search", input), false);
});

test("official SDK compact browser admits reviewed public research actions and actual query kinds", async (t) => {
  const { permit } = await fixture(t);
  const allowed: [string, Record<string, unknown> | undefined][] = [
    ["inspect", undefined],
    [
      "inspect",
      { includeDom: true, snapshotId: "snapshot-1", offset: 1, limit: 10 },
    ],
    ["navigate", { url: "https://example.com/docs", replaceCurrentTab: true }],
    ["open_tab", { url: "http://example.com/" }],
    ["navigate", { url: "https://[2606:4700:4700::1111]/" }],
    ["return_to_previous_tab", undefined],
    ["back", {}],
    ["forward", {}],
    ["reload", {}],
    ["click", { ref: "ref-1", button: "left", delay: 50 }],
    ["click_and_wait_for_navigation", { ref: "ref-2", timeout: 1000 }],
    ["hover", { position: { x: 100, y: 40 } }],
    ["scroll", { direction: "down", distance: 400 }],
    ["wait", { kind: "timeout", timeout: 0 }],
    ["wait", { kind: "selector", selector: "main", state: "visible" }],
    ["wait", { kind: "text", text: "Research" }],
    ["wait", { kind: "url", url: "https://example.com/" }],
    ["wait", { kind: "load" }],
    ["screenshot", undefined],
    [
      "screenshot",
      { scope: "clip", clip: { x: 0, y: 0, width: 10, height: 10 } },
    ],
    ["query", { kind: "text", selector: "main", maxChars: 1000 }],
    ["query", { kind: "dom" }],
    ["query", { kind: "semantic", text: "Download PDF" }],
    ["query", { kind: "editable" }],
    ["query", { kind: "snapshot" }],
    ["query", { kind: "console", levels: ["error"], limit: 5 }],
    [
      "query",
      {
        kind: "network",
        status: ["failed"],
        resourceTypes: ["document"],
        afterSequence: 1,
      },
    ],
  ];
  for (const [action, input] of allowed)
    assert.equal(
      await permit("browser", { action, ...(input ? { input } : {}) }),
      true,
      action + JSON.stringify(input),
    );
});

test("official SDK detailed browser aliases use native fields and reject mutation aliases", async (t) => {
  const { permit } = await fixture(t);
  const allowed: [string, Record<string, unknown>][] = [
    ["browser_inspect", { includeDom: true }],
    ["browser_navigate", { url: "https://example.com/" }],
    ["browser_click", { index: 0, click_count: 1 }],
    ["browser_scroll", { direction: "down", distance: 20 }],
    ["browser_hover", { normalized_position: { x: 0.5, y: 0.5 } }],
    ["browser_wait_for", { text: "Ready", timeout: 1000 }],
    ["browser_get_dom", { selector: "main" }],
    ["browser_screenshot", { scope: "fullPage" }],
    ["browser_verify_text", { texts: ["Ready"], exact: true }],
    ["browser_inspect_editable_targets", { limit: 10 }],
  ];
  for (const [name, input] of allowed)
    assert.equal(await permit(name, input), true, name);
  for (const name of [
    "browser_type",
    "browser_paste",
    "browser_press_key",
    "browser_evaluate",
    "website_deploy",
    "code_review",
  ])
    assert.equal(await permit(name, {}), false, name);
  assert.equal(
    await permit("browser_click", { ref: "ref-1", click_count: 2 }),
    false,
  );
});

test("browser malformed actions, private navigation and unsupported screenshot paths fail closed", async (t) => {
  const { permit, workspace } = await fixture(t);
  for (const action of [
    "fill",
    "type",
    "paste",
    "press_key",
    "upload_files",
    "drag",
    "check",
    "uncheck",
    "select_option",
    "double_click",
    "evaluate",
    "unknown",
  ])
    assert.equal(await permit("browser", { action, input: {} }), false, action);
  for (const input of [
    null,
    [],
    {},
    { action: "navigate" },
    { action: "query" },
    { action: "query", input: { kind: "javascript" } },
    { action: "inspect", input: [] },
    { action: "inspect", input: { script: "alert(1)" } },
    { action: "click", input: { target: { ref: "x" } } },
    { action: "screenshot", input: { scope: "clip" } },
  ])
    assert.equal(await permit("browser", input), false, JSON.stringify(input));
  for (const url of [
    "file:///etc/passwd",
    "javascript:alert(1)",
    "https://user:pass@example.com/",
    "http://localhost/",
    "http://127.0.0.1/",
    "http://2130706433/",
    "http://10.1.2.3/",
    "http://172.16.1.1/",
    "http://192.168.1.1/",
    "http://169.254.169.254/",
    "http://100.64.0.1/",
    "http://[::1]/",
    "http://host.internal/",
  ])
    assert.equal(
      await permit("browser", { action: "navigate", input: { url } }),
      false,
      url,
    );
  for (const file_path of [
    join(workspace, "capture.png"),
    "../escape.png",
    join(workspace, "outside", "escape.png"),
  ]) {
    assert.equal(
      await permit("browser", { action: "screenshot", input: { file_path } }),
      false,
    );
    assert.equal(await permit("browser_screenshot", { file_path }), false);
  }
});

test("policy exports ask gates without blanket browser denial and delegates only fs/bash", async () => {
  assert.ok(REVIEWED_POLICY_ASK.includes("browser"));
  assert.ok(REVIEWED_POLICY_ASK.includes("skill"));
  assert.ok(!REVIEWED_POLICY_DENY.includes("browser"));
  assert.match(TRUSTED_BROWSER_INSTRUCTION, /control-in-app-browser/);
  assert.match(
    TRUSTED_BROWSER_INSTRUCTION,
    /directly exposed mcp__searxng__searxng_search/,
  );
  for (const name of ["tool_search", "mcp_invoke"]) {
    assert.ok(REVIEWED_POLICY_DENY.includes(name));
    assert.ok(!REVIEWED_POLICY_ASK.includes(name));
  }
  for (const name of ["read", "write", "edit", "grep", "glob", "bash"])
    assert.equal(
      await reviewedToolPermission(
        "/workspace",
        {
          sessionId: "s",
          toolCall: { toolCallId: "t", name, rawInput: {} },
          options: [],
        },
        async (_w, p) => p,
      ),
      undefined,
    );
});

test("only exact reviewed image MCP tools and image skill supplement native role ceilings", async (t) => {
  const { permit } = await fixture(t);
  for (const name of [
    "mcp__image__image_capabilities",
    "mcp__image__image_generate",
    "mcp__image__image_edit",
  ])
    assert.equal(await permit(name, {}), true);
  assert.equal(await permit("skill", { name: "image" }), true);
  for (const name of [
    "mcp__image__approve",
    "mcp__image__admin",
    "mcp__foreign__image_edit",
    "mcp_invoke",
    "tool_search",
  ])
    assert.equal(await permit(name, {}), false);
});
