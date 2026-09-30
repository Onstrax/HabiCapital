import { formatCOP } from "@/lib/contracts";
import { tryGmfBreakdown } from "@/lib/gmf-math";

export function FinancialBreakdown({ amount, payer = "tu cuenta" }: { amount: number; payer?: string }) {
  const quote = tryGmfBreakdown(amount);
  if (!quote || amount <= 0) return null;
  return <div className="rounded-xl bg-cream p-3 text-sm" aria-live="polite">
    <span className="rounded-full bg-mint px-2 py-1 text-xs font-semibold">Incluye retención 4x1000</span>
    <dl className="mt-3 space-y-1">
      <div className="flex flex-wrap justify-between gap-2"><dt>Monto al destinatario</dt><dd>{formatCOP(amount)} COP</dd></div>
      <div className="flex flex-wrap justify-between gap-2"><dt>Impuesto 4x1000 (GMF)</dt><dd>{formatCOP(quote.gmf_tax)} COP</dd></div>
      <div className="flex flex-wrap justify-between gap-2 font-semibold"><dt>Total a debitar de {payer}</dt><dd>{formatCOP(quote.total_debit)} COP</dd></div>
    </dl>
  </div>;
}
