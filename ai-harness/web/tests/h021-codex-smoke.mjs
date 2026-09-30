// Offline browser smoke; creates only an owned temporary fixture app and browser profile.
import { chromium } from '@playwright/test';
import assert from 'node:assert/strict';
import { mkdtemp,realpath,rm,writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join,resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createApp } from '../../server/dist/app.js';
const dataDir=await realpath(await mkdtemp(join(tmpdir(),'h021-ui-')));
const inert=()=>({async start(){},async prompt(){throw Error('No fixture prompt permitted')},async cancel(){},async close(){}});
let browser,instance;
try {
 instance=await createApp({dataDir,webDist:resolve('dist'),allowedOrigins:['http://127.0.0.1:4197'],engineFactory:inert,codexEngineFactory:inert,enginePolicy:{codex:{enabled:false,protocolQualified:true,engineVersion:'0.158.0',modelPolicyVersion:'fixture'}},launcher:'/unused',gatewayUrl:'http://fixture.invalid',issueToken:()=> 'fixture',revokeToken(){}});
 const chat=instance.store.createSession(undefined,'codex',{engineVersion:'0.158.0',modelPolicyVersion:'fixture'});instance.store.setTitle(chat.id,'Codex offline fixture');await instance.files.prepare(chat.id,chat.workspaceId);instance.store.addMessage(chat.id,'user','Preserve the original attachment and conversation through compaction.');await writeFile(join(instance.files.workspace(chat.workspaceId),'result.txt'),'immutable fixture result');await instance.files.registerArtifact(chat.id,'result.txt','result.txt','text/plain');
 await instance.app.listen({host:'127.0.0.1',port:4197});
 browser=await chromium.launch({executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true,args:['--disable-background-networking','--disable-component-update','--disable-sync','--no-first-run']});const page=await browser.newPage({viewport:{width:1440,height:1000}});
 await page.route('**/*',route=>route.request().url().startsWith('http://127.0.0.1:4197/')?route.continue():route.abort());
 await page.goto('http://127.0.0.1:4197/');await page.getByText('Codex preview is disabled.',{exact:false}).waitFor();
 assert.equal(await page.getByRole('combobox',{name:'Harness for new chat'}).inputValue(),'minimax');assert.equal(await page.getByRole('option',{name:/Codex/}).evaluate(option=>option.disabled),true);assert.equal(await page.getByRole('button',{name:'Send message'}).isDisabled(),true);await page.getByText('Preserve the original attachment and conversation through compaction.').waitFor();
 await page.getByText('Codex preview capabilities',{exact:true}).click();await page.screenshot({path:fileURLToPath(new URL('../../../reports/h021-codex-adapter02-20260928/ui-offline.png',import.meta.url)),fullPage:true});
 console.log(JSON.stringify({status:'PASS',scope:'owned localhost UI fixture, no native/model requests',checks:['MiniMax default','Codex preview disabled','original history visible','composer read-only','capability details render']}));
} finally {await browser?.close();await instance?.app.close();await rm(dataDir,{recursive:true,force:true});}
