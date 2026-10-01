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
