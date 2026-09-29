import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import Ajv from 'ajv';
import { CODEX_MODEL_POLICY, CODEX_TOOL_POLICY_SHA256 } from '../src/codex-launcher.js';
const profile = (name: string) => readFileSync(new URL(`../../deploy/codex/${name}`, import.meta.url), 'utf8');
test('mounted ordinary image guidance invokes the actual explicit capability query contract', () => {
  const skill = profile('skills/sova-local-tools/SKILL.md');
  const models = JSON.parse(profile('models.json')).models;
  const overlay = profile('sova-overlay.md');
  assert.ok(skill.includes('Invoke the `image_capabilities` tool with exactly `{"query":"capabilities"}`'));
  assert.match(skill, /not a resource URI or a skill lookup/);
  assert.match(skill, /Native vision remains unavailable/);
  for (const guidance of [skill, overlay, ...models.map((m: any) => m.model_messages.instructions_template)]) {
    assert.match(guidance, /Frontier\/MiMo availability comes from the enabled model\/tool catalog/);
    assert.doesNotMatch(guidance, /Native vision and frontier\/MiMo remain unavailable|Read `image_capabilities`/);
    assert.match(guidance, /canvas/); assert.match(guidance, /settlement/);
  }
  for (const m of models) assert.ok(m.model_messages.instructions_template.includes('Invoke image_capabilities with exactly {"query":"capabilities"}'));
  const ordinarySkill = readFileSync(new URL('../../skills/image/SKILL.md', import.meta.url), 'utf8');
  assert.ok(ordinarySkill.includes('{"query":"capabilities"}'));
  const tools = JSON.parse(readFileSync(new URL('./fixtures/codex/image-mcp-tools.json', import.meta.url), 'utf8'));
  const schema = tools.find((t: any) => t.name === 'image_capabilities').inputSchema;
  const validate = new Ajv({ strict: false }).compile(schema);
  assert.equal(schema.additionalProperties, false); assert.deepEqual(schema.properties.query, { type: 'string', enum: ['capabilities'] });
  assert.deepEqual(schema.required, ['query']); assert.equal(validate({query: 'capabilities'}), true);
  for (const args of [{}, {query: 'other'}, {query: 'capabilities', prompt: '1024x576'}]) assert.equal(validate(args), false);
  for (const args of [{references:'[]'}, {skill:'sova-local-tools'}, {ref:'x'}, {uri:'x'}, {__ns:'10'}, {ns:'10'}, {__v:1}]) assert.equal(validate(args), false);
});
test('mounted guidance changes only separate tool identity and retains old chat model policy', () => {
  const names = ['config.toml', 'config-image-jobs.toml', 'requirements.toml', 'models.json', 'browser-mcp.mjs', 'skills/sova-local-tools/SKILL.md'];
  const digest = createHash('sha256').update(names.map(profile).join('')).digest('hex');
  assert.equal(digest, CODEX_TOOL_POLICY_SHA256);
  const launcher = readFileSync(new URL('../../deploy/run-codex.sh', import.meta.url), 'utf8');
  assert.ok(launcher.includes(digest));
  assert.equal(CODEX_MODEL_POLICY, 'sova-codex-0.158.0-qwen-text-v2');
  assert.match(launcher, /d8841743002e16de1f9269a850a2f06a73055688befec4c309778ca8a4c11aad/);
});

test('both installed instruction surfaces select dimensions per operation before creation and follow the existing status ID', () => {
  const ordinary = readFileSync(new URL('../../skills/image/SKILL.md', import.meta.url), 'utf8');
  const models = JSON.parse(profile('models.json')).models;
  for (const guidance of [ordinary, profile('skills/sova-local-tools/SKILL.md'), profile('sova-overlay.md'), ...models.map((m: any) => m.model_messages.instructions_template)]) {
    assert.match(guidance, /1536x864/);
    assert.match(guidance, /1024x1024/);
    assert.match(guidance, /BEFORE.*creative call/);
    assert.match(guidance, /generation.*(?:not qualify FullHD|not edit sizes)/i);
    assert.match(guidance, /image_status/);
    assert.match(guidance, /"jobId":"<existing job.id>"/);
    assert.match(guidance, /read-only lookup/);
    assert.match(guidance, /Only `?completed`?.*(?:successful|delivery)/);
    assert.match(guidance, /image_completion_unknown/);
  }
});

test('restricted Codex catalog offers only capability and owned status lookup; creative catalog retains explicit gated tools', () => {
  const enabled = (name: string) => JSON.parse(profile(name).match(/^enabled_tools = (.+)$/m)![1]!);
  assert.deepEqual(enabled('config.toml'), ['image_capabilities', 'image_status']);
  assert.deepEqual(enabled('config-image-jobs.toml'), ['image_capabilities', 'image_status', 'image_generate', 'image_edit']);
});
