/** Offline actual-capture audit. Emits hashes/counts/booleans only; no raw prompts,
 * model text, credentials or reasoning. Does not invoke native/model/network tools. */
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { resolve, join } from 'node:path';
import { execFileSync } from 'node:child_process';
import { translateResponses, ResponsesStream } from '../../ai-harness/server/src/codex-responses.ts';

const [first, retest, destination] = process.argv.slice(2);
assert.ok(first && retest && destination, 'Require first capture, retest capture, output JSON paths');
const sha = (value: string | Buffer) => createHash('sha256').update(value).digest('hex');
const json = (path: string) => JSON.parse(readFileSync(path, 'utf8'));
const catalog = json('ai-harness/deploy/codex/models.json');
const instructions = catalog.models.find((m: any) => m.slug === 'qwen3.8-27b').model_messages.instructions_template;
const config = readFileSync('ai-harness/deploy/codex/config-image-jobs.toml', 'utf8');
const completionContract = config.match(/^developer_instructions = "(.*)"$/m)![1];
const h034 = JSON.parse(execFileSync('git', ['show', '354a8d642e69e835d4f130fb2812a5f796d9e9d6:ai-harness/deploy/codex/models.json'], { encoding: 'utf8' }));
const oldInstructions = h034.models.find((m: any) => m.slug === 'qwen3.8-27b').model_messages.instructions_template;
const comparison = json('../input/W2-H035-RETAINED/EDIT-BOUNDARY-COMPARISON.json');
assert.ok(sha(oldInstructions) === comparison.successfulSpawnVersusRetest.instructionOldSha256, 'H034 source must match retained comparison instruction digest');
const text = (item: any): string => (item.content ?? []).filter((part: any) => ['input_text', 'output_text', 'text'].includes(part.type)).map((part: any) => part.text ?? '').join('\n');
const results = [];
for (const [label, directory, runId] of [
  ['H035_first', first, 'cfe55e79-cea8-4282-ae5b-d8543a8980ab'],
  ['H035_retest', retest, 'a2dbab1c-fca0-46e0-995d-726157a620af'],
]) {
  const root = resolve(directory);
  const manifest = json(join(root, 'manifest.json'));
  let verified = 0;
  for (const [name, digest] of Object.entries(manifest.files) as [string, any][]) {
    const file = resolve(root, name);
    assert.ok(file.startsWith(root + '/'), 'Capture member must stay below capture root');
    const bytes = readFileSync(file);
    assert.ok(bytes.length === digest.bytes && sha(bytes) === digest.sha256, 'Capture member digest/size mismatch');
    verified++;
  }
  const boundary = join(root, 'boundaries');
  const names = readdirSync(boundary).sort();
  const select = (phase: string) => names.filter(name => name.endsWith(`-${phase}.bin`));
  assert.equal(select('pre_normalization').length, 1, 'One retained provider request per failed turn');
  const original = json(join(boundary, select('pre_normalization')[0]));
  const before = JSON.stringify(original);
  assert.ok(original.input.every((item: any) => item.type !== 'reasoning'), 'Audit accepts only captures without reasoning items');
  const translated = translateResponses(original);
  assert.ok(JSON.stringify(original) === before, 'Translation must not mutate original history');
  const normalized = json(join(boundary, select('normalized_request')[0]));
  // Lane selection is gateway-owned; compare every other serialized field.
  const { model: capturedLane, ...capturedBody } = normalized;
  const { model: requestedModel, ...translatedBody } = translated.body;
  assert.ok(JSON.stringify(translatedBody) === JSON.stringify(capturedBody), 'Current translation must preserve all captured non-lane fields');
  const developer = original.input.filter((item: any) => item.role === 'developer').map(text).join('\n');
  assert.ok(original.instructions === instructions, 'Actual effective instructions must match current reviewed catalog');
  assert.ok(developer.includes(completionContract), 'Actual developer message must contain entire completion contract');
  const app = json(join(root, 'app-rows.json'));
  const run = app.runs.find((row: any) => row.id === runId);
  assert.ok(run, 'Retained failed run must exist');
  assert.ok(sha(run.text) === '37374b62c65ff3be70ead65b0a68e41148637cc95717b869a9afdc3fe79512c3', 'Strict original fixture must remain exact');
  const lastInput = text(original.input.at(-1));
  assert.ok(lastInput.includes(run.text), 'Exact original user request must survive assembly');
  const user = app.messages.find((row: any) => row.run_id === runId && row.role === 'user');
  assert.ok(user?.content === run.text, 'Saved user request remains original');
  const final = app.messages.filter((row: any) => row.run_id === runId && row.role === 'assistant');
  assert.equal(final.length, 1, 'One retained final per failed turn');
  const frames: any[] = [];
  const diagnostics: any[] = [];
  const stream = new ResponsesStream(translated, frame => frames.push(JSON.parse(frame.split('\ndata: ')[1])), event => diagnostics.push(event));
  for (const name of select('provider_sse')) stream.push(readFileSync(join(boundary, name)));
  stream.end();
  const terminal = frames.filter(frame => frame.type === 'response.completed');
  assert.equal(terminal.length, 1, 'One terminal response');
  const output = terminal[0].response.output;
  assert.ok(output.every((item: any) => item.type === 'message'), 'Replay must not synthesize tool calls or reasoning');
  const finalText = output.map(text).join('');
  assert.ok(finalText === final[0].content, 'Replay must deliver original promise unchanged');
  const finish = diagnostics.find(event => event.type === 'provider_finish');
  assert.ok(finish?.finishReason === 'stop', 'Original finish remains stop');
  const jobs = app.h003_image_jobs.map((row: any) => JSON.parse(row.data).job);
  assert.ok(jobs.every((job: any) => job && typeof job.id === 'string' && typeof job.runId === 'string' && typeof job.state === 'string'), 'Retained image records require their nested job envelope');
  assert.equal(jobs.filter((job: any) => job.runId === runId).length, 0, 'No new job attributed to failed turn');
  const historicalCalls = original.input.filter((item: any) => item.type === 'function_call');
  const historicalInvalidCapabilities = historicalCalls.filter((item: any) => item.namespace === 'mcp__image' && item.name === 'image_capabilities' && Object.hasOwn(JSON.parse(item.arguments), 'prompt'));
  const roles: Record<string, number> = {};
  for (const item of original.input) { const role = item.role ?? item.type; roles[role] = (roles[role] ?? 0) + 1; }
  results.push({ label, runId, verifiedCaptureFiles: verified,
    manifestSha256: sha(readFileSync(join(root, 'manifest.json'))),
    rawRequestSha256: sha(readFileSync(join(boundary, select('pre_normalization')[0]))),
    strictPromptSha256: sha(run.text), latestAssembledInputSha256: sha(lastInput),
    instructionsSha256: sha(original.instructions), developerMessageSha256: sha(developer),
    completionContractPresent: true, sameCurrentInstructions: true, historyInputRoles: roles,
    historicalInvalidPromptShapedCapabilitiesCalls: historicalInvalidCapabilities.length,
    explicitImageDisabledClauseInDeveloper: /image.{0,30}(disabled|unqualified|unavailable)|(disabled|unqualified|unavailable).{0,30}image/i.test(developer),
    publicImageGateFieldsInDeveloper: /imageToolEnabled|imageJobsQualified/.test(developer),
    exactRequestPreserved: true, completeTranslatedBodyMatchesApartFromSelectedLane: true,
    selectedLane: capturedLane, requestedModel,
    providerFinish: finish.finishReason, introducedCalls: 0, originalFinalPreserved: true,
    finalSha256: sha(finalText), finalBytes: Buffer.byteLength(finalText),
    newImageJobs: 0, savedJobStates: jobs.map((job: any) => ({ id: job.id, state: job.state, runId: job.runId, artifactId: job.artifactId })),
    strictWorkflowOutcome: 'FAIL_RETAINED_NOT_RETESTED',
  });
}
const report = { schema: 1, sourceBase: '7fe2bf0adde6ffdae1e5d7f04bd5d1c4c4cfeee8',
  scope: 'Offline current-source replay of retained actual input and provider output; no inference or native process.',
  auditedUtc: new Date().toISOString(),
  h034InstructionSourceMatchesRetainedComparison: true, h034InstructionsSha256: sha(oldInstructions),
  h034AndH035BothHavePersistence: [oldInstructions, instructions].every(s => s.includes('Please keep going until the query is completely resolved')),
  h034AndH035SameExplicitHostGateSentence: [oldInstructions, instructions].every(s => s.includes('Image generation/edit and delegation require explicit host capability enablement; image capabilities alone do not grant generation.')),
  h034ActualRawAvailableLocally: false,
  results, interpretation: 'No dropped tool call, missing generic completion instruction, or explicit false image gate instruction demonstrated. Behavioral causality remains unresolved. This verifies preservation, not completion of the requested workflow.' };
writeFileSync(destination, JSON.stringify(report, null, 2) + '\n');
console.log(JSON.stringify({ status: 'PASS_BOUNDARY_PRESERVATION_ONLY', captures: results.length, output: destination }));
