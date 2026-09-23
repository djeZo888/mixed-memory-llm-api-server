#!/usr/bin/env node
// SPDX-License-Identifier: MIT
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import { capabilitiesInput, configuredToken, createImageClient, editInput, generateInput, ImageError, LIMITS } from './image.mjs';

export function createImageServer(client, lifetime = new AbortController()) {
  const server = new McpServer({ name: 'ai-harness-image', version: '0.0.3' });
  const invoke = (operation, input, extra) => run(async () => {
    let lastProgress = -1;
    return client.invoke(operation, input, {
      signal: AbortSignal.any([extra.signal, lifetime.signal]),
      onProgress: extra._meta?.progressToken === undefined ? undefined : async job => {
        if (job.elapsedMs < lastProgress) return;
        lastProgress = job.elapsedMs;
        await extra.sendNotification({ method: 'notifications/progress', params: {
          progressToken: extra._meta.progressToken, progress: job.elapsedMs,
          message: `Image job ${job.state}${job.queuePosition === undefined ? '' : `; queue position ${job.queuePosition}`}${job.cancelRequested ? '; cancellation requested, draining' : ''}`,
        } });
      },
    });
  });
  server.registerTool('image_capabilities', {
    title: 'Local image capabilities',
    description: 'Read the resident Qwen-Image-2.1 service operation, size and reference-count capabilities. Only advertised qualified edit profiles are available; no creative fallback.',
    inputSchema: capabilitiesInput,
    annotations: { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: false },
  }, (input, extra) => run(() => client.capabilities(input, { signal: AbortSignal.any([extra.signal, lifetime.signal]) })));
  server.registerTool('image_generate', {
    title: 'Generate an image locally',
    description: 'Create one opaque image using resident Qwen-Image-2.1. Default size 1920x1080. Current generation profiles accept zero references; reference-based creation uses image_edit with references. Do not automatically convert operations; unqualified inputs may fail. Submit once; the stored job survives tool/turn ending. If awaiting approval, ask the user to use the image approval card; never resubmit or approve by tool.',
    inputSchema: generateInput,
    annotations: { readOnlyHint: false, destructiveHint: false, idempotentHint: false, openWorldHint: false },
  }, (input, extra) => invoke('generation', input, extra));
  server.registerTool('image_edit', {
    title: 'Edit an image locally',
    description: 'Use for reference-based creation or a new opaque edited version using resident Qwen-Image-2.1, with references containing explicit current-session file IDs or anchored relative workspace paths. Read image_capabilities for enabled sizes/reference counts first. Preserve originals and source geometry; any required resize/canvas change needs the user approval card. Unavailable edits cannot fall back to generation or another creative service.',
    inputSchema: editInput,
    annotations: { readOnlyHint: false, destructiveHint: false, idempotentHint: false, openWorldHint: false },
  }, (input, extra) => invoke('edit', input, extra));
  async function run(action) {
    try {
      const result = await action();
      const failed = result.error || ['failed', 'interrupted'].includes(result.job?.state);
      return { ...(failed ? { isError: true } : {}), content: [{ type: 'text', text: JSON.stringify(result) }] };
    } catch (error) {
      const safe = error instanceof ImageError ? { code: error.code, message: error.message } : { code: 'IMAGE_TOOL_FAILED', message: 'The image tool failed. Check the existing job card before submitting again.' };
      return { isError: true, content: [{ type: 'text', text: JSON.stringify({ error: safe }) }] };
    }
  }
  return server;
}

async function main() {
  if (process.argv.includes('--help')) {
    process.stdout.write('Usage: node image-mcp.mjs\nMCP stdio server for image_capabilities, image_generate and image_edit.\nUses only the existing AI_HARNESS_GATEWAY_TOKEN at fixed http://10.0.2.2:8081/v1.\nNo endpoint, identity, approval or backend arguments. Submitted jobs survive disconnection.\n');
    return;
  }
  if (process.argv.length !== 2) { process.stderr.write('Unsupported arguments. Use --help.\n'); process.exitCode = 1; return; }
  let token;
  try { token = configuredToken(process.env); }
  catch { process.stderr.write('Image MCP rejected: invalid session gateway configuration.\n'); process.exitCode = 1; return; }
  const lifetime = new AbortController();
  const server = createImageServer(createImageClient({ token }), lifetime);
  const transport = new StdioServerTransport(process.stdin, process.stdout, { maxBufferSize: LIMITS.stdioBytes });
  server.server.onerror = () => process.stderr.write('Image MCP transport or protocol error.\n');
  server.server.onclose = () => lifetime.abort();
  let closing = false;
  async function close() {
    if (closing) return;
    closing = true; lifetime.abort();
    // Ending observation never sends /cancel or replays a submitted image job.
    await server.close();
  }
  process.stdin.once('end', close);
  process.once('SIGTERM', close);
  process.once('SIGINT', close);
  await server.connect(transport);
}
if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  await main().catch(() => { process.stderr.write('Image MCP stopped after a transport failure.\n'); process.exitCode = 1; });
}
