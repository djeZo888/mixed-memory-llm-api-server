// Pinned-native fixture only: actual image MCP schemas, mock client, no gateway.
import { appendFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';
import { createImageServer } from '../../../tools/image/image-mcp.mjs';

const imageRequire = createRequire(new URL('../../../tools/image/package.json', import.meta.url));
const { StdioServerTransport } = await import(pathToFileURL(imageRequire.resolve('@modelcontextprotocol/sdk/server/stdio.js')).href);
const capture = process.argv[2];
if (!capture) throw Error('Fixture capture path required');
let pending = '';
process.stdin.on('data', chunk => {
  pending += chunk.toString();
  while (pending.includes('\n')) {
    const newline = pending.indexOf('\n');
    const line = pending.slice(0, newline); pending = pending.slice(newline + 1);
    const message = JSON.parse(line);
    if (message.method === 'tools/call') appendFileSync(capture, JSON.stringify({ kind: 'mcp_input', message }) + '\n');
  }
});
const server = createImageServer({
  async capabilities(input) {
    appendFileSync(capture, JSON.stringify({ kind: 'client_invocation', input }) + '\n');
    return { fixture: 'image_capabilities accepted empty input', generationEnabled: false, editEnabled: false };
  },
  async invoke() { throw Error('Image generation/edit forbidden in fixture'); },
});
await server.connect(new StdioServerTransport());
process.stdin.once('end', () => server.close());
process.once('SIGTERM', async () => { await server.close(); process.exit(0); });
