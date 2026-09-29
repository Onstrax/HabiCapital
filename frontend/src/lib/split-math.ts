export interface SplitRow {
  recipient_id: string;
  alias: string;
  masked_name: string;
  points: number; // integer hundredths of a percent
  locked: boolean;
}

export function redistributeShares(rows: SplitRow[], editedIndex?: number): SplitRow[] {
  if (!rows.length) return [];
  const fixed = rows.map((row, index) => row.locked || index === editedIndex);
  const used = rows.reduce((sum, row, index) => sum + (fixed[index] ? row.points : 0), 0);
  const free = rows.map((_, index) => index).filter((index) => !fixed[index]);
  if (used > 10_000 || (!free.length && used !== 10_000)) return rows;
  const each = free.length ? Math.floor((10_000 - used) / free.length) : 0;
  return rows.map((row, index) => ({ ...row, points: fixed[index] ? row.points
    : each + (index === free[free.length - 1] ? 10_000 - used - each * free.length : 0) }));
}

export function allocateCop(total: number, rows: SplitRow[]): number[] | null {
  if (!Number.isSafeInteger(total) || total <= 0 || !rows.length ||
      rows.some((row) => !Number.isInteger(row.points) || row.points <= 0) ||
      rows.reduce((sum, row) => sum + row.points, 0) !== 10_000) return null;
  const amounts = rows.map((row) => Number(BigInt(total) * BigInt(row.points) / BigInt(10_000)));
  const remainder = total - amounts.reduce((sum, amount) => sum + amount, 0);
  let lastUnlocked = -1;
  for (let index = rows.length - 1; index >= 0; index--) {
    if (!rows[index].locked) { lastUnlocked = index; break; }
  }
  if (remainder && lastUnlocked < 0) return null;
  if (remainder) amounts[lastUnlocked] += remainder;
  return amounts.every((amount) => amount > 0) ? amounts : null;
}

export function parsePercent(text: string): number | null {
  if (!/^(?:\d{1,3})(?:\.\d{0,2})?$/.test(text)) return null;
  const [whole, fraction = ""] = text.split(".");
  const points = Number(whole) * 100 + Number(fraction.padEnd(2, "0"));
  return points <= 10_000 ? points : null;
}
