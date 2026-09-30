import { describe, expect, it } from "vitest";
import { gmfBreakdown } from "./gmf-math";
describe("GMF integer preview", () => {
  it("keeps principal, tax and total exact", () => {
    expect(gmfBreakdown(100000)).toEqual({ gmf_tax: 400, total_debit: 100400 });
    expect(gmfBreakdown(100)).toEqual({ gmf_tax: 1, total_debit: 101 });
    expect(gmfBreakdown(0)).toEqual({ gmf_tax: 0, total_debit: 0 });
  });
  it("rejects unsafe money and total overflow", () => {
    for (const amount of [NaN, -1, 1.5, Number.MAX_SAFE_INTEGER]) {
      expect(() => gmfBreakdown(amount)).toThrow();
    }
  });
});
