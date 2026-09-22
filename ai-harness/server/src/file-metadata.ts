import path from "node:path";
/** Display name only: paths are always separately generated/guarded. */
export function displayName(input: string): string {
  const value = path
    .basename(input.replaceAll("\\", "/"))
    .normalize("NFC")
    .replace(/[\x00-\x1f\x7f"<>:|?*\u202a-\u202e\u2066-\u2069]/g, "_")
    .replace(/^\.+/, "")
    .trim();
  return Array.from(value).slice(0, 150).join("") || "file";
}
export function contentDisposition(name: string, inline = false): string {
  const safe = displayName(name);
  const ascii = safe.replace(/[^\x20-\x7e]/g, "_");
  const encoded = encodeURIComponent(safe).replace(
    /[!'()*]/g,
    (c) => `%${c.charCodeAt(0).toString(16).toUpperCase()}`,
  );
  return `${inline ? "inline" : "attachment"}; filename="${ascii}"; filename*=UTF-8''${encoded}`;
}
export function imageMime(name: string): string | null {
  const types: Record<string, string> = {
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".avif": "image/avif",
  };
  return types[path.extname(name).toLowerCase()] ?? null;
}

/** ASCII-only compatibility value for old releases' literal filename headers. */
export function safeStorageName(name: string): string {
  const value = path
    .basename(name.replaceAll("\\", "/"))
    .normalize("NFKC")
    .replace(/[^a-zA-Z0-9._ -]/g, "_")
    .replace(/^\.+/, "")
    .slice(0, 150);
  return value || "file";
}
