import { afterEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import { GET, POST } from "./route";

afterEach(() => vi.unstubAllGlobals());
const base = "http://localhost:3001/api/v1/";
const ctx = (path: string) => ({ params: { path: path.split("/") } });

describe("server-side session proxy", () => {
  it("sets an HttpOnly cookie and never returns the JWT to browser JavaScript", async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      access_token: "signed-secret", expires_in: 900, token_type: "bearer",
    }), { status: 200, headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetcher);
    const login = await POST(new NextRequest(base + "auth/login", {
      method: "POST", headers: { origin: "http://localhost:3001" }, body: "{}",
    }), ctx("auth/login"));
    expect((await login.json()).access_token).toBeUndefined();
    const cookie = login.headers.get("set-cookie") ?? "";
    expect(cookie).toContain("HttpOnly");
    expect(cookie).toContain("SameSite=strict");
    expect(cookie).toContain("signed-secret");

    await GET(new NextRequest(base + "ledger/balance", {
      headers: { cookie: cookie.split(";")[0], authorization: "Bearer forged" },
    }), ctx("ledger/balance"));
    expect(fetcher.mock.calls[1][1].headers.get("authorization")).toBe("Bearer signed-secret");
  });

  it("rejects cross-origin mutations before forwarding a session cookie", async () => {
    const fetcher = vi.fn();
    vi.stubGlobal("fetch", fetcher);
    const response = await POST(new NextRequest(base + "transfers/execute", {
      method: "POST", headers: { origin: "http://malicious.example", cookie: "habicapital_session=secret" },
      body: "{}",
    }), ctx("transfers/execute"));
    expect(response.status).toBe(403);
    expect(fetcher).not.toHaveBeenCalled();
  });
});
