"use client";

import { useMemo, useState } from "react";
import { allocateCop, redistributeShares, type SplitRow } from "@/lib/split-math";

export function useSplitCalculator(total: number) {
  const [rows, setRows] = useState<SplitRow[]>([]);
  const points = rows.reduce((sum, row) => sum + row.points, 0);
  const amounts = useMemo(() => allocateCop(total, rows), [total, rows]);
  return {
    rows, points, amounts, valid: amounts !== null,
    add(recipient: Omit<SplitRow, "points" | "locked">) {
      setRows((existing) => redistributeShares([...existing, { ...recipient, points: 0, locked: false }]));
    },
    remove(id: string) {
      setRows((existing) => redistributeShares(existing.filter((row) => row.recipient_id !== id)));
    },
    edit(id: string, value: number) {
      setRows((existing) => {
        const index = existing.findIndex((row) => row.recipient_id === id);
        if (index < 0) return existing;
        return redistributeShares(existing.map((row, position) =>
          position === index ? { ...row, points: value } : row), index);
      });
    },
    toggle(id: string) {
      setRows((existing) => redistributeShares(existing.map((row) => row.recipient_id === id
        ? { ...row, locked: !row.locked } : row)));
    },
  };
}
