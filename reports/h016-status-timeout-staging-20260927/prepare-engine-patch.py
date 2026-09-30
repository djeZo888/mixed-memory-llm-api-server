"""Offline exact-source patch preparation; never modifies the retained cache."""
from pathlib import Path
import hashlib,json,difflib
root=Path(__file__).resolve().parents[2]
cache=root.parents[1]/'H008-FRONTIER-20260926/native-source'
out=Path(__file__).resolve().parent
private=root.parent/'private/native-timeout-source'
files={
'packages/agent-core/src/pi-turn-runner/llm.ts':'80f43b4e02d1084739ad23d963e50ac0e303d89ef041b65f2d313d122c668e16',
'packages/agent-core/src/pi-turn-runner/llm-retry.ts':'91550d853a2050e588c8ea084e5abd8ee4775236df97ac0683a02b5aa5225396',
'third_party/pi-mono/packages/ai/src/providers/openai-completions.ts':'ac725f4baa2a923a704b0250165b389f7745139231bf108f3ac3df3a0541e35a'}
patch='';closure=[]
for name,expected in files.items():
 old=(cache/name).read_text();assert hashlib.sha256(old.encode()).hexdigest()==expected
 new=old
 if name.endswith('/llm.ts'):
  new=new.replace('timeoutMs: options?.timeoutMs ?? timeoutMs,', "timeoutMs: options?.timeoutMs ?? (model.id === 'mimo-v2.6-pro-rl' ? 511 * 60 * 1000 : timeoutMs),")
 elif name.endswith('/llm-retry.ts'):
  new=new.replace('const policy = resolvePolicy(input.policy);','const basePolicy = resolvePolicy(input.policy);')
  new=new.replace('return (async (model, context, options) => {', "return (async (model, context, options) => {\n    // MiMo ownership is never replayed after a transport/timeout ambiguity.\n    const policy = model.id === 'mimo-v2.6-pro-rl' ? { ...basePolicy, maxRetries: 0 } : basePolicy;",1)
 else:
  new=new.replace('const GATEWAY_TRANSPORT_TIMEOUT_MS = 151 * 60_000;', 'const GATEWAY_TRANSPORT_TIMEOUT_MS = 511 * 60_000;')
  new=new.replace('''\t\t\tconst requestOptions = {
\t\t\t\t...(options?.signal ? { signal: options.signal } : {}),
\t\t\t\t// Direct streamSimple auxiliaries also need the full local gateway budget.
\t\t\t\ttimeout: options?.timeoutMs ?? 151 * 60 * 1000,
\t\t\t\tmaxRetries: options?.maxRetries ?? 0,
\t\t\t};''','''\t\t\tconst mimo = model.id === "mimo-v2.6-pro-rl";
\t\t\tconst requestTimeoutMs = options?.timeoutMs ?? (mimo ? 511 : 151) * 60 * 1000;
\t\t\t// SDK timeout ends at headers; keep MiMo's deadline through stream drain.
\t\t\tconst requestSignal = mimo
\t\t\t\t? AbortSignal.any([...(options?.signal ? [options.signal] : []), AbortSignal.timeout(requestTimeoutMs)])
\t\t\t\t: options?.signal;
\t\t\tconst requestOptions = {
\t\t\t\t...(requestSignal ? { signal: requestSignal } : {}),
\t\t\t\ttimeout: requestTimeoutMs,
\t\t\t\tmaxRetries: mimo ? 0 : options?.maxRetries ?? 0,
\t\t\t};''')
 assert new!=old
 p=private/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(new)
 patch+=''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='a/'+name,tofile='b/'+name,n=0))
 closure.append({'path':name,'originalSha256':expected,'patchedSha256':hashlib.sha256(new.encode()).hexdigest()})
(out/'0011-mimo-request-budget.patch').write_text(patch)
(out/'ENGINE-PATCH-CLOSURE.json').write_text(json.dumps({'upstream':'ae65651df5f97ae1085ab4e19964f4b78c769a4e','baseImage':'sha256:6641df04cf4e8375029639a67c22da7c3ff4719d2b8e58748572f049de8fb022','sourceProvenance':'llm and llm-retry equal retained pinned pristine; provider equals current patched identity','patchSha256':hashlib.sha256(patch.encode()).hexdigest(),'files':closure,'compiledStatus':'NOT_BUILT','requiredCompiledClosure':['CLI entrypoint and all changed imported chunks from bundler metafile','native-probes.mjs and metafile if they include affected modules','packaged release and source identity manifests'],'untouched':['compiled estimator source','tools','dependencies','native llama runtime'],'activation':'HELD; old6641 does not implement this patch'},indent=2)+'\n')
print('Prepared three-file exact source patch; compiled engine closure remains HELD/NOT_BUILT')
