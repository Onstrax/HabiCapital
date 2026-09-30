export function gmfBreakdown(amount: number): { gmf_tax: number; total_debit: number } {
  if (!Number.isSafeInteger(amount) || amount < 0) throw new Error("Monto COP inválido");
  const cop = BigInt(amount);
  const raw = cop * BigInt(4) / BigInt(1000);
  const tax = cop === BigInt(0) ? BigInt(0) : raw > BigInt(0) ? raw : BigInt(1);
  const total = cop + tax;
  if (total > BigInt(Number.MAX_SAFE_INTEGER)) throw new Error("Monto más GMF demasiado alto");
  return { gmf_tax: Number(tax), total_debit: Number(total) };
}
export function tryGmfBreakdown(amount: number) {
  try { return gmfBreakdown(amount); } catch { return null; }
}
