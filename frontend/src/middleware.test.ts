import { describe, expect, it } from "vitest";
import { NextRequest } from "next/server";
import { middleware } from "./middleware";

describe("Content Security Policy", () => {
  it("gives each HTML response a different script nonce and denies inline injection", () => {
    const request = new NextRequest("http://localhost:3001/login");
    const first = middleware(request);
    const second = middleware(request);
    const policy = first.headers.get("content-security-policy") ?? "";
    const nextPolicy = second.headers.get("content-security-policy") ?? "";
    expect(policy).toMatch(/script-src 'self' 'nonce-[A-Za-z0-9+/=]+' 'strict-dynamic'/);
    const scriptPolicy = policy.split("; ").find((directive) => directive.startsWith("script-src"));
    expect(scriptPolicy).not.toContain("'unsafe-inline'");
    expect(scriptPolicy).not.toContain("'unsafe-eval'");
    expect(policy).toContain("connect-src 'self'");
    expect(policy).toContain("object-src 'none'");
    expect(policy).toContain("frame-ancestors 'none'");
    expect(nextPolicy).not.toBe(policy);
  });
});
