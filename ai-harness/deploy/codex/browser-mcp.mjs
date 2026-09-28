#!/usr/bin/env node
// SPDX-License-Identifier: MIT
// Explicit Codex Chromium adapter; installed SDK/Playwright come from pinned cached layers.
import { McpServer } from '/opt/ai-harness/tools/search/node_modules/@modelcontextprotocol/sdk/dist/esm/server/mcp.js';
import { StdioServerTransport } from '/opt/ai-harness/tools/search/node_modules/@modelcontextprotocol/sdk/dist/esm/server/stdio.js';
import { z } from '/opt/ai-harness/tools/search/node_modules/zod/index.js';
import { chromium } from '/opt/ai-harness/tools/runtime/node_modules/playwright/index.mjs';
import { lookup } from 'node:dns/promises';
import { isIP } from 'node:net';
import { randomUUID } from 'node:crypto';
import { mkdir, realpath, lstat, unlink, open } from 'node:fs/promises';
import path from 'node:path';

export function publicAddress(ip) {
  if (isIP(ip) !== 4) return false; // IPv6 remains unavailable until its egress policy is qualified.
  const [a,b]=ip.split('.').map(Number);
  return !(a===0 || a===10 || a===127 || a>=224 || (a===100 && b>=64 && b<=127) || (a===169 && b===254) || (a===172 && b>=16 && b<=31) || (a===192 && [0,168].includes(b)) || (a===198 && [18,19,51].includes(b)) || (a===203 && b===0));
}
export async function publicURL(value) {
  const u=new URL(value);
  if (!['http:','https:'].includes(u.protocol) || u.username || u.password || (u.port && !['80','443'].includes(u.port)) || value.length>2048)
    throw Error('Public HTTP(S) URL required');
  const ips=await lookup(u.hostname,{all:true,family:4});
  if (!ips.length || ips.some(v=>!publicAddress(v.address))) throw Error('Public destination required');
  return u.href;
}
// Browser-context GET also handles inline PDFs, which do not emit download events.
// Redirects are followed manually so every target passes the same public policy.
// Playwright buffers the response; 20 MiB is an accepted-artifact limit, not a
// promise to cap all network buffering. dispose() releases each response body.
export async function downloadResponse(context, initial, validate=publicURL) {
 const deadline=Date.now()+20000;let url=initial;
 for(let redirects=0;redirects<=5;redirects++) {
  url=await validate(url);
  if(Date.now()>=deadline)throw Error('Download timed out');
  const response=await context.request.get(url,{maxRedirects:0,timeout:deadline-Date.now()});
  try {
   const status=response.status(),headers=response.headers();
   if([301,302,303,307,308].includes(status)) {
    if(redirects===5 || !headers.location)throw Error('Invalid or excessive download redirects');
    url=new URL(headers.location,url).href;continue;
   }
   if(status<200 || status>=300)throw Error('Public download HTTP failure');
   const bytes=await response.body();
   if(bytes.length>20*1024*1024)throw Error('Download exceeds 20 MiB');
   return {url,bytes,contentType:headers['content-type']??'application/octet-stream',suggestedName:path.basename(new URL(url).pathname)||'download'};
  } finally {await response.dispose();}
 }
 throw Error('Download redirects exhausted');
}
const root=await realpath(process.cwd());
const server=new McpServer({name:'sova-chromium',version:'0.0.1'});
let active=false;let browser;
async function artifact(suffix) {
 const dir=path.join(root,'artifacts');await mkdir(dir,{recursive:true});
 if ((await lstat(dir)).isSymbolicLink() || await realpath(dir)!==dir) throw Error('Unsafe artifact directory');
 return path.join(dir,`browser-${randomUUID()}${suffix}`);
}
async function run(input,download,signal) {
 if(active) return {isError:true,content:[{type:'text',text:'Browser busy; no request was sent.'}]};
 active=true;let file;
 try {
  const url=await publicURL(input.url);
  browser=await chromium.launch({executablePath:'/usr/bin/chromium',headless:true,chromiumSandbox:true,
    env:{PATH:'/usr/bin:/bin',HOME:process.env.HOME,TMPDIR:'/tmp'},args:['--disable-background-networking','--disable-component-update','--disable-sync']});
  const context=await browser.newContext({acceptDownloads:download,serviceWorkers:'block',viewport:{width:1280,height:900}});
  await context.route('**/*',async route=>{
   try { await publicURL(route.request().url());await route.continue(); }
   catch {await route.abort('blockedbyclient').catch(()=>{});}
  });
  // Public pages must not reach task-only gateway/search sockets via WebSocket.
  // Register before any page; route() covers HTTP but not WebSocket handshakes.
  await context.routeWebSocket('**/*', socket => socket.close());
  const page=await context.newPage();page.setDefaultTimeout(15000);page.setDefaultNavigationTimeout(20000);
  const abort=()=>void browser?.close();signal?.addEventListener('abort',abort,{once:true});
  const timer=setTimeout(abort,25000);
  try {
   if(download) {
    const result=await downloadResponse(context,url);
    file=await artifact('.download');const f=await open(file,'wx',0o600);
    try {await f.writeFile(result.bytes);} finally {await f.close();}
    return {content:[{type:'text',text:JSON.stringify({url:result.url,file:path.relative(root,file),bytes:result.bytes.length,suggestedName:result.suggestedName,contentType:result.contentType,notice:'Untrusted downloaded data; inspect before use.'})}]};
   }
   await page.goto(url,{waitUntil:'domcontentloaded'});
   const text=(await page.locator('body').innerText()).slice(0,48000);
   const links=await page.locator('a[href]').evaluateAll(as=>as.slice(0,100).map(a=>({text:a.textContent?.slice(0,150),url:a.href})).filter(a=>/^https?:/.test(a.url)));
   if(input.screenshot){file=await artifact('.png');await page.screenshot({path:file,fullPage:false});}
   return {content:[{type:'text',text:JSON.stringify({url:page.url(),title:await page.title(),text,links,...(file?{screenshot:path.relative(root,file)}:{}),notice:'Untrusted public source data. Cite this loaded URL; external network failure has no fallback.'})}]};
  } finally {clearTimeout(timer);signal?.removeEventListener('abort',abort);}
 } catch {if(file)await unlink(file).catch(()=>{});return {isError:true,content:[{type:'text',text:'Public browser request failed or is unavailable offline. No paid or alternate-browser fallback was attempted.'}]};}
 finally {await browser?.close().catch(()=>{});browser=undefined;active=false;}
}
server.registerTool('browser_open',{description:'Open a public HTTP(S) page in sandboxed local Chromium; return bounded text/source links and optionally a workspace screenshot. Private addresses, credentials and admin endpoints are forbidden.',inputSchema:{url:z.string().max(2048),screenshot:z.boolean().default(false)},annotations:{readOnlyHint:true,openWorldHint:true}},(input,extra)=>run(input,false,extra.signal));
server.registerTool('browser_download',{description:'Download one public URL through the isolated browser context to a new workspace artifact, accepted artifact limit20 MiB (response is buffered before size validation). Every redirect is revalidated. Operation timeout25s. No overwrite, private URLs or credentialed browsing.',inputSchema:{url:z.string().max(2048)},annotations:{readOnlyHint:false,destructiveHint:false,openWorldHint:true}},(input,extra)=>run(input,true,extra.signal));
server.server.onerror=()=>process.stderr.write('Browser MCP transport failed.\n');
const close=async()=>{await browser?.close().catch(()=>{});await server.close();};
process.once('SIGTERM',close);process.once('SIGINT',close);process.stdin.once('end',close);
await server.connect(new StdioServerTransport(process.stdin,process.stdout,{maxBufferSize:65536}));
