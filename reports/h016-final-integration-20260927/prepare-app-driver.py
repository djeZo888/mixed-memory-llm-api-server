#!/usr/bin/env python3
"""Derive the thin H016 proposal from H009 hooks; no host, service or inference calls."""
import pathlib,sys
if '--help' in sys.argv: print(__doc__);sys.exit(0)
here=pathlib.Path(__file__).resolve().parent
old=here.parent/'h009-frontier-20260926/driver';out=here/'driver';out.mkdir(exist_ok=True)
for name in ['edge.mjs','check.mjs','policy-a.txt','policy-b.txt','prompts.json','preflight-cli.mjs']:(out/name).write_bytes((old/name).read_bytes())
s=(old/'live.mjs').read_text()
s=s.replace('started+1140000','started+480000')
s=s.replace('{frontierBody},{NodeAvailability}', '{prepareMimo},{NodeAvailability}')
s=s.replace("'protected-credential','frontier','node-availability'", "'protected-credential','mimo','node-availability'")
s=s.replace("let mode='full-count-only',phase='full-roster'", "let mode='full-live',phase='code'")
s=s.replace('frontierBody(effective)', 'prepareMimo(effective).json')
a=s.index('  onActive:r=>{');b=s.index('\n});',a);s=s[:a]+s[b:]
a=s.index('async function overlapQwen()');b=s.index("let status='FAILED'",a);s=s[:a]+s[b:]
s=s.replace("    frontier:{contextWindow:480000,tokenizerRevision:REV,templateRevision:REV,upstreamKey:key,onRequestState:guards.onRequestState}});", "    frontier:(await load('active-frontier')).loadActiveFrontier((await load('active-frontier')).loadFrontierSelection(),key,guards.onRequestState)});")
a=s.index("  const fullId=await newSession(");b=s.index("  const call=calls(codeId,'task')",a)
s=s[:a]+"  const codeId=await newSession('h016-foreground-edge-code');const code=await run(codeId,prompts.code);\n"+s[b:]
s=s.replace("childModel:'custom_provider:frontier/glm-5.3-flash'", "childModel:'custom_provider:frontier/mimo-v2.6-pro-rl'")
s=s.replace("summary={codeSessionId:codeId,fullRosterSessionId:fullId,", "summary={codeSessionId:codeId,")
s=s.replace("scope:'one native code task; full real child roster if initial full count fits, else explicit reduced actual schemas; no overflow replay'", "scope:'one Qwen parent and MiMo foreground child; full production tools; no projection, count-only replay or overlap test'")
s=s.replace("const here=dirname(fileURLToPath(import.meta.url));", "const here=dirname(fileURLToPath(import.meta.url));")
s=s.replace("const guards=createGuards({record,capture,getMode:()=>mode,", "const guards=createGuards({record,capture,getMode:()=>mode,toolsSha256:gate.toolsSha256,")
s=s.replace('FLASH,RETAIN_FLASH', 'FLASH').replace('KEY,REV,IMAGE', 'KEY,IMAGE')
s=s.replace(',probePromise,probeStarted=false', '')
s=s.replace("const independentId='h009-independent-qwen';\n", '')
s=s.replace('actual Flash', 'actual MiMo').replace('Flash bash','MiMo bash').replace('its Flash wire','its MiMo wire').replace('flashRequests:states','mimoRequests:states')
s=s.replace("execFileSync(process.execPath,['check.mjs']", "assert.equal(sha(readFileSync(join(workspace,'check.mjs'))),sha(readFileSync(join(here,'check.mjs'))),'verification file changed');assert.notEqual(sha(readFileSync(join(workspace,'edge.mjs'))),sha(readFileSync(join(here,'edge.mjs'))),'child made no change');execFileSync(process.execPath,['check.mjs']")
s=s.replace("  summary={codeSessionId", "  assert.equal(gateway.frontierSnapshot().state,'idle');const finals=new Map();for(const r of states)finals.set(r.id,r);assert(finals.size>1&&[...finals.values()].every(r=>r.state==='settled'),'native requests not serially settled');\n  summary={codeSessionId")
s=s.replace('status:u.status},u.type', 'status:u.status,update:u},u.type')
(out/'live.mjs').write_text(s)
s=(old/'supervise.py').read_text().replace('H009-FRONTIER-20260926/live-acceptance-01','H016-FINAL-INTEGRATION-20260927/live-acceptance-01')
s=s.replace('min(1200,','min(600,')
(out/'supervise.py').write_text(s)
