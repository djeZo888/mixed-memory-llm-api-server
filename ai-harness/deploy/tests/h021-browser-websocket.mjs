#!/usr/bin/env node
// Actual installed Playwright/Chromium API test of the exact production guard.
// No model/MCP/VM claim. One owned local HTTP server and fresh browser profile.
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {readFile} from 'node:fs/promises';
import {pathToFileURL} from 'node:url';
const [playwrightPath, chromePath]=process.argv.slice(2);
assert(playwrightPath && chromePath, 'Pass installed pinned playwright index.mjs and Chrome executable; no downloads');
const {chromium}=await import(pathToFileURL(playwrightPath));
const source=await readFile(new URL('../codex/browser-mcp.mjs',import.meta.url),'utf8');
const guard=source.match(/^  await context\.routeWebSocket\([^\n]+\);$/m)?.[0];
assert(guard,'exact source WebSocket guard absent');
assert(source.indexOf(guard)<source.indexOf('const page=await context.newPage()'),'guard installed after page');
let handshakes=0,browser;
const server=createServer((req,res)=>res.end('<!doctype html><title>Owned WebSocket fixture</title>'));
server.on('upgrade',(_request,socket)=>{handshakes++;socket.destroy();});
await new Promise(done=>server.listen(0,'127.0.0.1',done));
const origin=`http://127.0.0.1:${server.address().port}`;
try {
 browser=await chromium.launch({executablePath:chromePath,headless:true,chromiumSandbox:true,args:['--disable-background-networking','--disable-component-update','--disable-sync','--no-first-run']});
 // Sensitivity check: same installed browser can reach this listener without guard.
 const control=await browser.newContext();const controlPage=await control.newPage();await controlPage.goto(origin);
 await controlPage.evaluate(url=>new Promise(resolve=>{const ws=new WebSocket(url);ws.onclose=()=>resolve('closed');ws.onerror=()=>resolve('error');}),origin.replace('http:','ws:')+'/control');
 assert.equal(handshakes,1,'unprotected control did not reach owned listener');await control.close();
 const context=await browser.newContext({serviceWorkers:'block'});
 await new (Object.getPrototypeOf(async function(){}).constructor)('context',guard)(context);
 const page=await context.newPage();await page.goto(origin);
 const closed=await page.evaluate(url=>Promise.all(['/same-origin','/task-port-simulation'].map(path=>new Promise(resolve=>{const ws=new WebSocket(url+path);ws.onclose=()=>resolve('closed');ws.onerror=()=>resolve('error');}))),origin.replace('http:','ws:'));
 assert.deepEqual(closed,['closed','closed']);assert.equal(handshakes,1,'guard allowed upstream handshake');
 console.log(JSON.stringify({status:'PASS',scope:'Mac installed Chromium + exact production route guard; not Linux MCP acceptance',controlHandshakes:1,guardedAttempts:2,guardedHandshakes:0,chromium:browser.version(),sandboxDisablingFlags:[]}));
 await context.close();
} finally {await browser?.close();await new Promise(done=>server.close(done));}
