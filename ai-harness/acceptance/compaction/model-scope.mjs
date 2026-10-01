import {verifyChildLineage,childRequestMetadata} from './child-lineage.mjs';
import { createHash } from 'node:crypto';
import { isAbsolute, relative } from 'node:path';
const sha = text => createHash('sha256').update(text).digest('hex');
const same = (a, b) => JSON.stringify(sorted(a)) === JSON.stringify(sorted(b));
function sorted(v) { return Array.isArray(v) ? v.map(sorted) : v && typeof v === 'object' ? Object.fromEntries(Object.keys(v).sort().map(k => [k, sorted(v[k])])) : v; }
const within = (a, b) => { const d = relative(a, b); return d === '' || (!d.startsWith('../') && d !== '..' && !isAbsolute(d)); };
const hex = v => typeof v === 'string' && /^[a-f0-9]{64}$/.test(v);
export function verifyObservedModelScope(probe, expected) {
  if (typeof probe?.scopeReceiptUtf8 !== 'string' || !expected?.scopePolicy) return { status: 'NOT_TESTED', errors: ['observed-model-scope-or-independent-policy-absent'] };
  try {
    const s = JSON.parse(probe.scopeReceiptUtf8), policy = expected.scopePolicy;
    if (s.source !== 'h041-observed-model-scope' || s.scopePolicySha256 !== sha(JSON.stringify(sorted(policy))) ||
        probe.scopeReceiptSha256 !== sha(probe.scopeReceiptUtf8)) throw Error('scope receipt/policy');
    for (const [key, value] of Object.entries({ nativeThreadId: expected.probeThreadId, nativeTurnId: expected.probeTurnId, actionId: expected.actionId,
      runId: expected.runId, windowId: expected.windowId })) if (!value || s[key] !== value) throw Error('scope identity');
    for (const [bytes, digest] of [['parentLaunchReceiptUtf8','parentLaunchReceiptSha256'],['launchReceiptUtf8','launchReceiptSha256'],['prelaunchReceiptUtf8','prelaunchReceiptSha256'],['nativeFramesUtf8','nativeFramesSha256'],['firstRequestUtf8','firstRequestSha256'],['normalizedRequestUtf8','normalizedRequestSha256']])
      if (typeof s[bytes] !== 'string' || !hex(s[digest]) || sha(s[bytes]) !== s[digest]) throw Error('scope retained raw bytes');
    if (s.firstRequestUtf8 !== probe.firstRequestUtf8 || s.normalizedRequestUtf8 !== probe.normalizedRequestUtf8) throw Error('scope request substitution');
    const launch = JSON.parse(s.launchReceiptUtf8), fresh = JSON.parse(s.prelaunchReceiptUtf8), frames = JSON.parse(s.nativeFramesUtf8), raw = JSON.parse(s.firstRequestUtf8), normalized = JSON.parse(s.normalizedRequestUtf8);
    if (launch.schema !== 'codex-launch-v1' || launch.sessionId !== s.sessionId || !hex(launch.nonce) ||
        launch.container?.imageRevision !== policy.sourceRevision || launch.container?.imageId !== policy.imageId ||
        launch.container?.network !== 'slirp4netns:allow_host_loopback=true' || launch.container?.rootless !== true || launch.container?.readOnly !== true || launch.container?.privileged !== false ||
        !same(launch.sources, policy.receiptSources) || !hex(launch.egress?.receiptSha256) || launch.egress?.nftSha256 !== policy.nftSha256 ||
        launch.egress?.bootId !== launch.producer?.bootId || launch.egress?.uid !== launch.producer?.uid ||
        policy.gatewayUrl !== 'http://10.0.2.2:8081/v1' || policy.network !== 'gateway-only' ||
        !same(raw.tools, policy.rawTools) || !same(normalized.tools, policy.normalizedTools)) throw Error('actual launch/egress/tools policy');
    if (!Array.isArray(policy.forbiddenPaths) || policy.forbiddenPaths.length < 4 || !Array.isArray(policy.mounts) || !same(launch.container.mounts, policy.mounts.map(m => ({...m, source: m.source === '@profile' ? fresh.profile.path : m.source === '@workspace' ? fresh.workspace.path : m.source, destination: m.destination.replaceAll('@profile',fresh.profile.path).replaceAll('@workspace',fresh.workspace.path)})))) throw Error('frozen actual mounts');
    const parent = JSON.parse(s.parentLaunchReceiptUtf8);
    if (parent.schema !== 'codex-launch-v1' || parent.sessionId === s.sessionId || !parent.container?.profileDir || !parent.container?.workspace) throw Error('observed parent launch absent');
    if (!Array.isArray(launch.container.additionalMounts) || launch.container.additionalMounts.some(m => m.type !== 'tmpfs' || m.source !== '' || !['/tmp','/run','/var/tmp'].includes(m.destination))) throw Error('unexpected additional mount');
    if (policy.rawTools.some(t => (t.name ?? t.function?.name) !== 'read_original') || policy.rawTools.length > 1 || policy.normalizedTools.some(t => (t.name ?? t.function?.name) !== 'read_original')) throw Error('model file/exec tool exposed');
    const mounts = [...launch.container.mounts, ...launch.container.additionalMounts];
    for (const m of mounts) for (const forbidden of [parent.container.profileDir,parent.container.workspace]) if (m.source && (within(m.source, forbidden) || within(forbidden,m.source))) throw Error('actual parent mount exposed');
    for (const m of mounts) for (const forbidden of policy.forbiddenPaths) if (m.source && (within(m.source, forbidden) || within(forbidden, m.source))) throw Error('protected host tree mounted');
    if (fresh.source !== 'owned-prelaunch-filesystem-observation' || fresh.sessionId !== s.sessionId ||
        fresh.profile.path !== launch.container.profileDir || fresh.workspace.path !== launch.container.workspace ||
        !fresh.profile.empty || !fresh.workspace.empty || !Number.isSafeInteger(fresh.profile.ino) || !Number.isSafeInteger(fresh.workspace.ino) ||
        fresh.profile.ino !== fresh.postlaunch?.profile?.ino || fresh.profile.dev !== fresh.postlaunch?.profile?.dev || fresh.workspace.ino !== fresh.postlaunch?.workspace?.ino || fresh.workspace.dev !== fresh.postlaunch?.workspace?.dev ||
        fresh.observedAtMs > launch.checkedAtMs) throw Error('fresh model mounts');
    if (!Array.isArray(frames) || frames.some(f => typeof f.bytesUtf8 !== 'string' || sha(f.bytesUtf8) !== f.sha256 || !same(JSON.parse(f.bytesUtf8),f.value))) throw Error('actual native frame bytes');
    const starts = frames.filter(f => f.direction === 'to-native' && f.value.method === 'thread/start');
    const req = starts.at(-1), ack = req && frames.find(f => f.direction === 'from-native' && f.value.id === req.value.id && f.value.result);
    const initialize = frames.find(f => f.direction === 'to-native' && f.value.method === 'initialize');
    if (!req || !ack || !same(Object.fromEntries(Object.entries(ack.value.result).filter(([k]) => k !== 'thread')), policy.threadAck) || ack.value.result.thread?.id !== s.nativeThreadId || !same(ack.value.result.thread?.environments,policy.threadEnvironments) || !same(policy.threadEnvironments,[]) || req.value.params.cwd !== fresh.workspace.path ||
        !same(Object.fromEntries(Object.entries(req.value.params).filter(([k]) => k !== 'cwd')), policy.threadParams) ||
        initialize?.value.params.capabilities?.experimentalApi !== policy.experimentalApi ||
        raw.client_metadata?.thread_id !== s.nativeThreadId || raw.client_metadata?.turn_id !== s.nativeTurnId) throw Error('actual native scope policy/identity');
    return { status: 'PASS', errors: [], scopeReceiptSha256: sha(probe.scopeReceiptUtf8), observedModelScope: true,
      network: 'gateway-only', physicalMounts: mounts, modelFileTools: [], originalReader: policy.rawTools.length ? 'read_original' : null };
  } catch { return { status: 'FAIL', errors: ['observed-model-scope-raw-producer-native-policy-or-mount-binding'] }; }
}

/** A delegated child shares native housekeeping with its parent. Physical mounts
 * are observed, never described as empty; model input/tools are checked separately. */
export function verifyObservedDelegatedScope(probe,expected){
 if(typeof probe?.scopeReceiptUtf8!=='string'||!expected?.scopePolicy)return {status:'NOT_TESTED',errors:['delegated-scope-policy-or-actual-bytes-absent']};
 try{
  const s=JSON.parse(probe.scopeReceiptUtf8),p=expected.scopePolicy,l=JSON.parse(s.launchReceiptUtf8),frames=JSON.parse(s.nativeFramesUtf8),raw=JSON.parse(s.firstRequestUtf8),normalized=JSON.parse(s.normalizedRequestUtf8);
  if(s.source!=='h041-observed-delegated-model-scope'||probe.scopeReceiptSha256!==sha(probe.scopeReceiptUtf8)||s.scopePolicySha256!==sha(JSON.stringify(sorted(p)))||s.launchReceiptSha256!==sha(s.launchReceiptUtf8)||s.nativeFramesSha256!==sha(s.nativeFramesUtf8)||s.firstRequestUtf8!==probe.firstRequestUtf8||s.normalizedRequestUtf8!==probe.normalizedRequestUtf8)throw Error();
  for(const [k,v]of Object.entries({nativeThreadId:expected.probeThreadId,nativeTurnId:expected.probeTurnId,actionId:expected.actionId,runId:expected.runId,windowId:expected.windowId}))if(!v||s[k]!==v)throw Error();
  if(l.schema!=='codex-launch-v1'||l.sessionId!==s.authenticationSessionId||!hex(l.nonce)||l.container?.imageRevision!==p.sourceRevision||l.container?.imageId!==p.imageId||!same(l.sources,p.receiptSources)||l.container?.rootless!==true||l.container?.readOnly!==true||l.container?.privileged!==false||l.container?.network!=='slirp4netns:allow_host_loopback=true'||l.egress?.nftSha256!==p.nftSha256||!hex(l.egress?.receiptSha256)||l.egress.bootId!==l.producer.bootId||l.egress.uid!==l.producer.uid||p.network!=='gateway-only'||p.gatewayUrl!=='http://10.0.2.2:8081/v1'||p.parentHousekeeping!=='native-only-no-model-tools')throw Error();
  if(!Array.isArray(p.mounts)||!same(l.container.mounts,p.mounts.map(m=>({...m,source:m.source==='@profile'?l.container.profileDir:m.source==='@workspace'?l.container.workspace:m.source,destination:m.destination.replaceAll('@profile',l.container.profileDir).replaceAll('@workspace',l.container.workspace)})))||!Array.isArray(l.container.additionalMounts)||l.container.additionalMounts.some(m=>m.type!=='tmpfs'||m.source!==''||!['/tmp','/run','/var/tmp'].includes(m.destination)))throw Error();
  const mounts=[...l.container.mounts,...l.container.additionalMounts];if(!Array.isArray(p.forbiddenPaths)||p.forbiddenPaths.length<4)throw Error();for(const m of mounts)for(const path of p.forbiddenPaths)if(m.source&&(within(m.source,path)||within(path,m.source)))throw Error();
  if(!same(raw.tools,[])||!same(normalized.tools,[])||raw.model!=='qwen3.8-27b'||normalized.model!=='qwen3.8-27b'||!same(p.rawTools,[])||!same(p.normalizedTools,[]))throw Error();
  if(!Array.isArray(frames)||frames.some(f=>sha(f.bytesUtf8)!==f.sha256||!same(JSON.parse(f.bytesUtf8),f.value)))throw Error();
  const proof=s.proof,t=JSON.parse(proof.lineage.responseUtf8).result.thread,metadata=childRequestMetadata(raw,t.parentThreadId,proof.parentTurnId);if(metadata.thread_id!==s.nativeThreadId||metadata.turn_id!==s.nativeTurnId||verifyChildLineage(proof.lineage,{parentId:t.parentThreadId,childId:s.nativeThreadId,firstDispatchAt:proof.firstDispatchAt,providerModel:raw.model}).status!=='PASS')throw Error();
  const spawn=frames.filter(f=>f.direction==='from-native'&&f.value.method==='item/started'&&f.value.params?.threadId===t.parentThreadId&&f.value.params?.turnId===proof.parentTurnId&&f.value.params?.item?.id===proof.spawnCallId&&f.value.params.item.type==='collabAgentToolCall'&&f.value.params.item.tool==='spawnAgent'&&f.value.params.item.prompt===proof.brief),started=frames.filter(f=>f.direction==='from-native'&&f.value.method==='turn/started'&&f.value.params?.threadId===s.nativeThreadId&&f.value.params.turn?.id===s.nativeTurnId);
  if(spawn.length!==1||started.length!==1||Date.parse(started[0].observedAt)>Date.parse(proof.firstDispatchAt))throw Error();
  const parent=frames.find(f=>f.direction==='to-native'&&['thread/start','thread/resume'].includes(f.value.method)),ack=parent&&frames.find(f=>f.direction==='from-native'&&f.value.id===parent.value.id&&f.value.result?.thread?.id===t.parentThreadId);
  if(!parent||!ack||!same(Object.fromEntries(Object.entries(parent.value.params).filter(([k])=>!['threadId','cwd'].includes(k))),p.parentThreadParams)||!same(Object.fromEntries(Object.entries(ack.value.result).filter(([k])=>k!=='thread')),p.parentThreadAck)||ack.value.result.sandbox?.type!=='readOnly'||!same(t.environments,[]))throw Error();
  return {status:'PASS',errors:[],scopeReceiptSha256:sha(probe.scopeReceiptUtf8),observedModelScope:true,physicalMounts:mounts,modelFileTools:[],network:'gateway-only'};
 }catch{return {status:'FAIL',errors:['actual-delegated-native-policy-lineage-mount-or-tool-binding']};}
}
