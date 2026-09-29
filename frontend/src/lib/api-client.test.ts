import { afterEach, describe, expect, it, vi } from "vitest";
import { api, ApiError } from "./api-client";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("api client", () => {
  it("never exposes a JWT to browser code and uses a distinct UUIDv4 for each POST", async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", fetcher);
    await api.post("/transfers/lookup", { recipient_alias: "carlos_dev" });
    await api.post("/transfers/execute", { recipient_id: "123", amount: 100, concept: "Pago" });
    const first = fetcher.mock.calls[0][1];
    const second = fetcher.mock.calls[1][1];
    expect(first.headers.Authorization).toBeUndefined();
    expect(first.headers["X-Idempotency-Key"]).toMatch(/^[\da-f]{8}-[\da-f]{4}-4[\da-f]{3}-[89ab][\da-f]{3}-[\da-f]{12}$/i);
    expect(first.headers["X-Idempotency-Key"]).not.toBe(second.headers["X-Idempotency-Key"]);
  });

  it("keeps the bank error code and rejects unsafe amounts", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ code: "INSUFFICIENT_FUNDS_FOR_PAYMENT_REQUEST", message: "Sin saldo" }),
      { status: 400, headers: { "Content-Type": "application/json" } },
    )));
    await expect(api.post("/charges/123/pay", {})).rejects.toMatchObject({
      code: "INSUFFICIENT_FUNDS_FOR_PAYMENT_REQUEST", status: 400,
    } satisfies Partial<ApiError>);
    expect(() => api.assertAmount(Number.MAX_SAFE_INTEGER + 1)).toThrow();
    expect(() => api.assertAmount(0)).toThrow();
  });

  it("reuses an explicit key when retrying the same financial payload", async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", fetcher);
    const key = crypto.randomUUID();
    const payload = { recipient_id: "123", amount: 50000, concept: "Cena" };
    await api.post("/transfers/execute", payload, { idempotencyKey: key });
    await api.post("/transfers/execute", payload, { idempotencyKey: key });
    expect(fetcher.mock.calls[0][1].headers["X-Idempotency-Key"]).toBe(key);
    expect(fetcher.mock.calls[1][1].headers["X-Idempotency-Key"]).toBe(key);
  });
});
