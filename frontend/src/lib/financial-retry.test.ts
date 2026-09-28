import { beforeEach, describe, expect, it, vi } from "vitest";
import { clearTransferKey, stableTransferKey } from "./financial-retry";

const values = new Map<string, string>();
beforeEach(() => {
  values.clear();
  vi.stubGlobal("sessionStorage", {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => values.set(key, value),
    removeItem: (key: string) => values.delete(key),
  });
});

describe("financial retry keys", () => {
  it("reuses the key for the identical payload, and rotates for another payment", async () => {
    const payment = { recipient_id: "abc", amount: 50000, concept: "Cena" };
    const first = await stableTransferKey(payment);
    expect(await stableTransferKey(payment)).toBe(first);
    const second = await stableTransferKey({ ...payment, amount: 50001 });
    expect(second).not.toBe(first);
    clearTransferKey();
    expect(await stableTransferKey(payment)).not.toBe(first);
  });
});
