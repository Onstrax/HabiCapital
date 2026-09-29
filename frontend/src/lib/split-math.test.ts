import { describe, expect, it } from "vitest";
import { allocateCop, redistributeShares, type SplitRow } from "./split-math";

const make = (points: number, locked = false): SplitRow => ({
  recipient_id: crypto.randomUUID(), alias: crypto.randomUUID(), masked_name: "P***", points, locked,
});

describe("group split without fractional pesos", () => {
  it("distributes hundredths of a percent evenly, giving the last row the fractional point", () => {
    expect(redistributeShares([make(0), make(0), make(0)]).map((row) => row.points))
      .toEqual([3333, 3333, 3334]);
  });

  it("keeps locked percentages and a manual edit, redistributing only other unlocked rows", () => {
    const rows = redistributeShares([make(5000, true), make(3000), make(2500)], 1);
    expect(rows.map((row) => row.points)).toEqual([5000, 3000, 2000]);
  });

  it("assigns COP remainder to the last unlocked recipient without moving a lock", () => {
    const shares = [make(3333, true), make(3333), make(3334)];
    expect(allocateCop(101, shares)).toEqual([33, 33, 35]);
  });

  it("refuses zero-weight rows and a remainder when all recipients are locked", () => {
    expect(allocateCop(1, [make(5000), make(5000)])).toBeNull();
    expect(allocateCop(101, [make(3333, true), make(3333, true), make(3334, true)])).toBeNull();
  });
});
