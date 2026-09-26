import { request } from "node:http";

export type BackendService = "qwen-gpu0" | "qwen-gpu1" | "image";
export type Readiness = { ready: boolean | null };
const targets = {
  "qwen-gpu0": {
    origin: "http://10.156.100.60:30002",
    route: "/v1/readiness",
    alias: "qwen3.8-27b-gpu0",
  },
  "qwen-gpu1": {
    origin: "http://10.156.100.60:30004",
    route: "/v1/readiness",
    alias: "qwen3.8-27b",
  },
  image: {
    origin: "http://10.156.100.60:30006",
    route: "/v1/image-capabilities",
    alias: "qwen-image-2.1",
  },
} as const;
const unavailable = () => Error("Passive backend readiness unavailable");
/** Root-approved passive endpoints, implemented separately by Worker1. Never
 * /health, never generation, never proof of idle. Caller carries no target URL. */
export function createBackendReadiness(
  key: string,
  options: { fixtureOrigins?: Partial<Record<BackendService, string>> } = {},
): Record<BackendService, (signal: AbortSignal) => Promise<Readiness>> {
  if (!key || !/^[\x21-\x7e]+$/.test(key)) throw unavailable();
  return Object.fromEntries(
    Object.entries(targets).map(([serviceId, target]) => {
      const override = options.fixtureOrigins?.[serviceId as BackendService];
      if (override) {
        const url = new URL(override);
        if (
          url.protocol !== "http:" ||
          url.hostname !== "127.0.0.1" ||
          url.username ||
          url.password ||
          url.pathname !== "/" ||
          url.search ||
          url.hash
        )
          throw Error("Readiness fixtures require IPv4 loopback origin");
      }
      const probe = (signal: AbortSignal) =>
        new Promise<Readiness>((resolve, reject) => {
          const bounded = AbortSignal.any([signal, AbortSignal.timeout(2000)]);
          const req = request(
            new URL(target.route, override ?? target.origin),
            {
              method: "GET",
              signal: bounded,
              agent: false,
              headers: {
                Authorization: `Bearer ${key}`,
                Accept: "application/json",
              },
            },
            (response) => {
              let length = 0;
              const chunks: Buffer[] = [];
              response.on("data", (chunk: Buffer) => {
                length += chunk.length;
                if (length > 128 * 1024) {
                  req.destroy();
                  reject(unavailable());
                } else chunks.push(chunk);
              });
              response.on("error", () => reject(unavailable()));
              response.on("end", () => {
                try {
                  if (
                    !response.complete ||
                    ![200, 503].includes(response.statusCode ?? 0)
                  )
                    throw unavailable();
                  const value: unknown = JSON.parse(
                    Buffer.concat(chunks).toString("utf8"),
                  );
                  if (
                    !value ||
                    typeof value !== "object" ||
                    Array.isArray(value)
                  )
                    throw unavailable();
                  const body = value as Record<string, unknown>;
                  if (serviceId === "image") {
                    if (
                      response.statusCode !== 200 ||
                      body.model !== target.alias ||
                      typeof body.ready !== "boolean" ||
                      typeof body.admitting !== "boolean" ||
                      typeof body.busy !== "boolean"
                    )
                      throw unavailable();
                    resolve({
                      ready: body.ready && (body.admitting || body.busy),
                    });
                  } else {
                    if (
                      body.schema_version !== 1 ||
                      body.model_alias !== target.alias ||
                      typeof body.ready !== "boolean" ||
                      body.admitting !== null ||
                      !["starting", "up", "unhealthy", "unknown"].includes(
                        String(body.state),
                      ) ||
                      body.ready !== (body.state === "up") ||
                      response.statusCode !== (body.ready ? 200 : 503)
                    )
                      throw unavailable();
                    resolve({
                      ready: body.state === "unknown" ? null : body.ready,
                    });
                  }
                } catch {
                  reject(unavailable());
                }
              });
            },
          );
          req.on("error", () => reject(unavailable()));
          req.end();
        });
      return [serviceId, probe];
    }),
  ) as Record<BackendService, (signal: AbortSignal) => Promise<Readiness>>;
}
