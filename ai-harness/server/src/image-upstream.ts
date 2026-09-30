import { request } from "node:http";
import { randomBytes } from "node:crypto";
import type { ImageBackend, ImageProfile } from "./image-contracts.js";
import { geometry } from "./image-codec.js";
import { ApiError } from "./errors.js";

export const IMAGE_ORIGIN = "http://10.156.100.60:30006";
export interface ImageUpstreamOptions {
  /** Existing protected host credential, never engine/browser configuration. */
  key: string | (() => string | Promise<string>);
  /** Offline fixture only; production never exposes an upstream environment override. */
  fixtureOrigin?: string;
  requestMs?: number;
  responseMs?: number;
}
const unavailable = () =>
  new ApiError(
    503,
    "image_upstream_unavailable",
    "Image upstream is unavailable",
  );
export class ImageUpstream implements ImageBackend {
  private readonly origin: string;
  constructor(private readonly options: ImageUpstreamOptions) {
    this.origin = options.fixtureOrigin ?? IMAGE_ORIGIN;
    if (options.fixtureOrigin) {
      const u = new URL(options.fixtureOrigin);
      if (
        u.protocol !== "http:" ||
        u.hostname !== "127.0.0.1" ||
        u.username ||
        u.password ||
        u.pathname !== "/" ||
        u.search ||
        u.hash
      )
        throw new Error("Image fixture origin must be IPv4 loopback");
    }
  }
  private async call(
    route: string,
    signal: AbortSignal,
    body?: Buffer,
    contentType?: string,
  ) {
    let key: string;
    try {
      key =
        typeof this.options.key === "function"
          ? await this.options.key()
          : this.options.key;
      if (!key || !/^[\x21-\x7e]+$/.test(key)) throw new Error("key");
    } catch {
      throw unavailable();
    }
    signal.throwIfAborted();
    return new Promise<{
      status: number;
      headers: import("node:http").IncomingHttpHeaders;
      bytes: Buffer;
    }>((resolve, reject) => {
      let timer: NodeJS.Timeout;
      const limit = body ? 49 * 1024 * 1024 : 256 * 1024;
      const req = request(
        new URL(route, this.origin),
        {
          method: body ? "POST" : "GET",
          signal,
          agent: false,
          headers: {
            Authorization: `Bearer ${key}`,
            Accept: "application/json",
            ...(body
              ? {
                  "Content-Type": contentType!,
                  "Content-Length": String(body.length),
                }
              : {}),
          },
        },
        (response) => {
          clearTimeout(timer);
          timer = setTimeout(
            () => req.destroy(unavailable()),
            this.options.responseMs ?? 30000,
          );
          timer.unref();
          let length = 0;
          const chunks: Buffer[] = [];
          response.on("data", (chunk: Buffer) => {
            length += chunk.length;
            if (length > limit) {
              req.destroy(unavailable());
              return;
            }
            chunks.push(chunk);
          });
          response.on("error", () => reject(unavailable()));
          response.on("end", () => {
            clearTimeout(timer);
            if (!response.complete) {
              reject(unavailable());
              return;
            }
            resolve({
              status: response.statusCode ?? 0,
              headers: response.headers,
              bytes: Buffer.concat(chunks),
            });
          });
        },
      );
      timer = setTimeout(
        () => req.destroy(unavailable()),
        body ? (this.options.requestMs ?? 900000) : 10000,
      );
      timer.unref();
      req.on("error", () => {
        clearTimeout(timer);
        reject(unavailable());
      });
      req.end(body);
    });
  }
  async capabilities(signal: AbortSignal) {
    const response = await this.call("/v1/image-capabilities", signal);
    if (response.status !== 200) throw unavailable();
    try {
      const value: unknown = JSON.parse(response.bytes.toString("utf8"));
      this.profiles(value); // Validate the reviewed shape; return its JSON unchanged.
      return value;
    } catch {
      throw unavailable();
    }
  }
  profiles(value: unknown): ImageProfile[] {
    if (!value || typeof value !== "object") throw unavailable();
    const caps = value as Record<string, unknown>;
    if (caps.model !== "qwen-image-2.1" || !Array.isArray(caps.profiles))
      throw unavailable();
    const out: ImageProfile[] = [];
    for (const p of caps.profiles) {
      if (
        !p ||
        typeof p !== "object" ||
        !["generation", "edit"].includes(p.operation) ||
        typeof p.size !== "string" ||
        !Number.isInteger(p.references) ||
        typeof p.transparent !== "boolean" ||
        !/^[a-f0-9]{64}$/.test(p.evidence_sha256)
      )
        throw unavailable();
      geometry(p.size);
      if (p.transparent) continue;
      if (
        p.operation === "generation"
          ? p.references !== 0
          : ![1, 2].includes(p.references)
      )
        throw unavailable();
      out.push({
        operation: p.operation,
        referenceCount: p.references,
        size: p.size,
        model: String(caps.model),
      });
    }
    return out;
  }
  async readiness(signal: AbortSignal) {
    const response = await this.call("/health/ready", signal);
    if (response.status !== 200) return { ready: false, idle: false };
    try {
      const body = JSON.parse(response.bytes.toString("utf8"));
      return {
        ready: body.ready === true && body.admitting === true,
        idle: body.busy === false,
      };
    } catch {
      return { ready: false, idle: false };
    }
  }
  async execute(
    input: Parameters<ImageBackend["execute"]>[0],
    signal: AbortSignal,
  ): ReturnType<ImageBackend["execute"]> {
    const fields = {
      model: input.model,
      prompt: input.prompt,
      size: input.size,
      seed: input.seed,
      n: 1,
      response_format: "b64_json",
      background: "opaque",
    };
    let body: Buffer, contentType: string;
    if (input.operation === "generation") {
      body = Buffer.from(JSON.stringify(fields));
      contentType = "application/json";
    } else {
      const boundary = `image-${randomBytes(24).toString("hex")}`,
        parts: Buffer[] = [];
      if (
        input.references.some((b) => b.length > 32 * 1024 * 1024) ||
        input.references.reduce((n, b) => n + b.length, 0) > 64 * 1024 * 1024
      )
        throw new ApiError(
          413,
          "image_too_large",
          "Normalized references exceed upstream limits",
        );
      for (const [key, value] of Object.entries(fields))
        parts.push(
          Buffer.from(
            `--${boundary}\r\nContent-Disposition: form-data; name="${key}"\r\n\r\n${value}\r\n`,
          ),
        );
      for (const [i, bytes] of input.references.entries()) {
        parts.push(
          Buffer.from(
            `--${boundary}\r\nContent-Disposition: form-data; name="image[]"; filename="reference-${i + 1}.png"\r\nContent-Type: image/png\r\n\r\n`,
          ),
          bytes,
          Buffer.from("\r\n"),
        );
      }
      parts.push(Buffer.from(`--${boundary}--\r\n`));
      body = Buffer.concat(parts);
      contentType = `multipart/form-data; boundary=${boundary}`;
    }
    const response = await this.call(
      input.operation === "generation"
        ? "/v1/images/generations"
        : "/v1/images/edits",
      signal,
      body,
      contentType,
    );
    if (response.status === 429) {
      // The reviewed API's busy429 is the only automatic replay authority.
      let busy = false;
      try {
        busy =
          JSON.parse(response.bytes.toString("utf8")).error?.code === "busy";
      } catch {}
      const value = response.headers["retry-after"];
      let retryAfterMs = NaN;
      if (typeof value === "string")
        retryAfterMs = /^\d+$/.test(value)
          ? Number(value) * 1000
          : Math.max(0, Date.parse(value) - Date.now());
      if (busy && Number.isFinite(retryAfterMs))
        return { kind: "not_admitted", retryAfterMs };
      throw unavailable();
    }
    if (response.status !== 200) throw unavailable();
    try {
      const value = JSON.parse(response.bytes.toString("utf8"));
      if (!Array.isArray(value.data) || value.data.length !== 1)
        throw new Error("count");
      const encoded = value.data[0]?.b64_json;
      if (
        typeof encoded !== "string" ||
        encoded.length > 48 * 1024 * 1024 ||
        !encoded.length ||
        encoded.length % 4 ||
        !/^[A-Za-z0-9+/]*={0,2}$/.test(encoded)
      )
        throw new Error("encoding");
      const effectiveSeed = value.data[0].seed;
      if (
        effectiveSeed !== undefined &&
        (!Number.isSafeInteger(effectiveSeed) || effectiveSeed < 0)
      )
        throw new Error("seed");
      const png = Buffer.from(encoded, "base64");
      if (png.toString("base64") !== encoded) throw new Error("encoding");
      // Reviewed API strips native metadata; optional effective seed is checked by
      // the broker. Without it, these
      // describe the exact submitted model and persisted seed.
      return {
        kind: "output",
        png,
        model: input.model,
        seed: effectiveSeed ?? input.seed,
      };
    } catch {
      throw unavailable();
    }
  }
}
