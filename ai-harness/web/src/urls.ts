// Tool output is untrusted text. Only explicit public HTTP(S) destinations become
// links; this is a navigation guard, not DNS verification or an automatic fetch.
export function safePublicUrl(value: string): string | undefined {
  if (/[\u0000-\u0020\u007f]/.test(value) || !/^https?:\/\//i.test(value)) return undefined;
  try {
    const url = new URL(value);
    if (url.username || url.password) return undefined;
    const host = url.hostname.toLowerCase().replace(/\.$/, '');
    if (
      !host.includes('.') ||
      host.includes(':') ||
      /(^|\.)(localhost|local|internal|intranet|lan|home|test|invalid)$/.test(host)
    )
      return undefined;
    // Block address literals: avoids obfuscated and IPv4-mapped local addresses.
    if (/^[\d.]+$/.test(host)) return undefined;
    return url.href;
  } catch {
    return undefined;
  }
}

// Add reviewed same-origin file routes here only when their exact contract is
// delivered. Callers must not accept arbitrary artifact URLs or raw markup.
const segment = (id: string): string | undefined =>
  id && id !== '.' && id !== '..' && !/[\u0000-\u001f\u007f]/.test(id)
    ? encodeURIComponent(id)
    : undefined;
const exact = (supplied: string | undefined, expected: string | undefined) =>
  expected && supplied === expected ? expected : undefined;
export function artifactDownloadUrl(id: string): string | undefined {
  const value = segment(id);
  return value ? `/api/artifacts/${value}/download` : undefined;
}
export function previewUrl(id: string, supplied?: string): string | undefined {
  const value = segment(id);
  return exact(supplied, value ? `/api/files/${value}/preview` : undefined);
}
export function attachmentDownloadUrl(id: string, supplied?: string): string | undefined {
  const value = segment(id);
  return exact(supplied, value ? `/api/attachments/${value}/download` : undefined);
}
export function runZipUrl(sessionId: string, runId: string, supplied?: string): string | undefined {
  const session = segment(sessionId),
    run = segment(runId);
  return exact(
    supplied,
    session && run ? `/api/sessions/${session}/runs/${run}/artifacts.zip` : undefined,
  );
}
