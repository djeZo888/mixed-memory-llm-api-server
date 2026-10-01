import assert from "node:assert/strict";
import test from "node:test";
import vm from "node:vm";
import { statusJs } from "../src/status-ui.js";

test("status and admin display current native readiness separately from unknown native capacity and configured policy", () => {
  // Both pages use this script. Execute its display functions without polling or actions.
  const source = statusJs.slice(statusJs.indexOf("function numeric("), statusJs.indexOf("function renderEngines("));
  const context = vm.createContext({}); vm.runInContext(source, context);
  const modelDetails = vm.runInContext("modelDetails", context);
  const row = { configured_model: { display_name: "Qwen", instance_name: "Qwen0", expected_alias: "qwen3.8-27b" },
    observed_model: { state: "ok", freshness: "fresh", ready: true }, configured_context_tokens: 480000, max_output_tokens: null,
    configured_profile: { contextWindow: 480000, maxOutputTokens: 65536, autoCompactTokenLimit: 400000 },
    capacity_status: "unknown", capacity_reason: "native_output_ceiling_not_observed" };
  let text = modelDetails(row).join("\n");
  assert.match(text, /Native model readiness: ready · fresh/);
  assert.match(text, /Observed native output ceiling: unknown/);
  assert.match(text, /Configured Sova policy: 480000 context \/ 65536 output ceiling/);
  assert.match(text, /capacity comparison: unknown · native_output_ceiling_not_observed/);
  row.observed_model.freshness = "stale";
  text = modelDetails(row).join("\n"); assert.match(text, /Native model readiness: Unknown · stale/);
  assert.doesNotMatch(text, /Native model readiness: ready/);
  row.observed_model.freshness = "fresh"; row.observed_model.ready = false;
  assert.match(modelDetails(row).join("\n"), /Native model readiness: not ready · fresh/);
});
