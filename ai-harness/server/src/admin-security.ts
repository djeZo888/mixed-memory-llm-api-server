import { createHmac, randomBytes, timingSafeEqual } from "node:crypto";
import type { FastifyReply, FastifyRequest } from "fastify";
import { ApiError } from "./errors.js";

/** One replaceable authority boundary; every reachable trusted LAN visitor has
 * identical authority. The URL path and CSRF capability are not authentication. */
export class AdminSecurity {
  private readonly key = randomBytes(32);
  private readonly origins: Set<string>;
  private readonly readOnlyOrigins: Set<string>;
  constructor(
    origins: readonly string[],
    readOnlyOrigins: readonly string[] = [],
    private readonly now = Date.now,
  ) {
    const validate = (input: string) => {
      const url = new URL(input);
      if (
        !["http:", "https:"].includes(url.protocol) ||
        url.origin !== input ||
        url.username ||
        url.password
      )
        throw Error("Invalid public origin");
      return input;
    };
    this.origins = new Set(origins.map(validate));
    this.readOnlyOrigins = new Set(readOnlyOrigins.map(validate));
    if (!this.origins.size)
      throw Error("At least one admin origin is required");
  }
  check(req: FastifyRequest, admin: boolean) {
    const host = req.headers.host;
    const all = [...this.origins, ...this.readOnlyOrigins];
    if (!host || !all.some((origin) => new URL(origin).host === host))
      this.deny();
    const origin = req.headers.origin;
    if (origin && (!all.includes(origin) || new URL(origin).host !== host))
      this.deny();
    if (req.headers.authorization) this.deny();
    if (
      req.headers["sec-fetch-site"] &&
      !["same-origin", "none"].includes(String(req.headers["sec-fetch-site"]))
    )
      this.deny();
    if (
      admin &&
      ![...this.origins].some((origin) => new URL(origin).host === host)
    )
      this.deny();
  }
  issue(req: FastifyRequest, reply: FastifyReply) {
    this.check(req, true);
    const origin = [...this.origins].find(
      (value) => new URL(value).host === req.headers.host,
    )!;
    const payload = `${this.now() + 30 * 60 * 1000}.${randomBytes(24).toString("hex")}`;
    const token = `${payload}.${this.sign(payload, origin)}`;
    reply.header(
      "Set-Cookie",
      `harness_admin_csrf=${token}; HttpOnly; SameSite=Strict; Path=/api/admin; Max-Age=1800${origin.startsWith("https:") ? "; Secure" : ""}`,
    );
    return {
      csrf: token,
      expiresInSeconds: 1800,
      authority: "anonymous_trusted_network",
    };
  }
  mutation(req: FastifyRequest) {
    this.check(req, true);
    const origin = req.headers.origin;
    if (
      !origin ||
      !this.origins.has(origin) ||
      new URL(origin).host !== req.headers.host
    )
      this.deny();
    if (
      req.headers["content-type"]?.split(";")[0]?.trim() !== "application/json"
    )
      this.deny();
    const token = req.headers["x-csrf-token"];
    const cookies = (req.headers.cookie ?? "")
      .split(";")
      .map((s) => s.trim())
      .filter((s) => s.startsWith("harness_admin_csrf="));
    if (
      typeof token !== "string" ||
      cookies.length !== 1 ||
      cookies[0] !== `harness_admin_csrf=${token}`
    )
      this.deny();
    const match = /^(\d{13})\.([0-9a-f]{48})\.([0-9a-f]{64})$/.exec(
      token as string,
    );
    if (
      !match ||
      Number(match[1]) <= this.now() ||
      Number(match[1]) > this.now() + 30 * 60 * 1000
    )
      this.deny();
    const signature = this.sign(`${match![1]}.${match![2]}`, origin!);
    if (!timingSafeEqual(Buffer.from(signature), Buffer.from(match![3]!)))
      this.deny();
  }
  private sign(payload: string, origin: string) {
    return createHmac("sha256", this.key)
      .update(`${origin}\n${payload}`)
      .digest("hex");
  }
  private deny(): never {
    throw new ApiError(
      403,
      "admin_origin_forbidden",
      "Trusted same-origin admin request required",
    );
  }
}
