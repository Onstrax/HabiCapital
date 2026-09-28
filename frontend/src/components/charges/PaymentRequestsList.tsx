"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowDownLeft, Check, X } from "lucide-react";
import { useState } from "react";
import { api, ApiError } from "@/lib/api-client";
import { formatCOP, formatDate, type Charge } from "@/lib/contracts";

export function PaymentRequestsList() {
  const queryClient = useQueryClient();
  const [message, setMessage] = useState("");
  const charges = useQuery({ queryKey: ["charges", "pending"], queryFn: () => api.get<{ items: Charge[] }>("/charges?status=PENDING"), refetchInterval: 30_000 });
  const action = useMutation({
    mutationFn: ({ id, action }: { id: string; action: "pay" | "reject" }) => api.post(`/charges/${encodeURIComponent(id)}/${action}`),
    onSuccess: () => {
      setMessage("");
      void queryClient.invalidateQueries({ queryKey: ["charges"] });
      void queryClient.invalidateQueries({ queryKey: ["ledger"] });
    },
    onError: (error) => {
      setMessage(error instanceof ApiError && error.code === "INSUFFICIENT_FUNDS_FOR_PAYMENT_REQUEST"
        ? "Saldo insuficiente. Tu cobro se mantendrá pendiente hasta que recargues saldo"
        : error instanceof ApiError ? error.message : "No pudimos procesar el cobro. Intenta de nuevo.");
      void queryClient.invalidateQueries({ queryKey: ["charges"] });
    },
  });

  return <section className="surface p-5 sm:p-7" aria-labelledby="charges-heading">
    <div className="mb-6 flex items-center justify-between gap-3"><div><p className="text-xs font-semibold uppercase tracking-widest text-[#638c76]">POR RESOLVER</p>
      <h2 id="charges-heading" className="mt-1 text-xl font-semibold">Cobros pendientes</h2></div>
      <span className="rounded-full bg-mint px-3 py-1 text-sm font-semibold text-forest">{charges.data?.items.length ?? 0}</span></div>
    {message && <p role="alert" className="mb-4 rounded-xl bg-[#fff0df] p-3 text-sm text-[#795327]">{message}</p>}
    {charges.isLoading && <p role="status" className="text-sm text-[#687d70]">Cargando cobros...</p>}
    {charges.isError && <p role="alert" className="text-sm text-red-700">No pudimos cargar tus cobros. <button onClick={() => void charges.refetch()} className="font-semibold underline">Reintentar</button></p>}
    {charges.data?.items.length === 0 && <div className="rounded-2xl bg-cream px-5 py-8 text-center"><ArrowDownLeft className="mx-auto mb-3 text-[#5c967a]" />
      <p className="font-medium">Estás al día con tus cobros</p><p className="mt-1 text-sm text-[#728277]">Aquí aparecerán cuando alguien te solicite un pago.</p></div>}
    <div className="space-y-3">{charges.data?.items.map((charge) => <article key={charge.id} className="rounded-2xl border border-[#e7ece5] p-4">
      <div className="flex items-start justify-between gap-3"><div className="min-w-0"><p className="font-semibold">@{charge.requester_alias}</p><p className="mt-1 break-words text-sm text-[#718276]">{charge.concept}</p>
        <p className="mt-2 text-xs text-[#8a988d]">{formatDate(charge.created_at)}</p></div>
        <p className="shrink-0 font-bold text-forest">{formatCOP(charge.amount)}</p></div>
      <div className="mt-4 grid grid-cols-2 gap-2"><button disabled={action.isPending} onClick={() => { setMessage(""); action.mutate({ id: charge.id, action: "reject" }); }} className="btn-subtle !min-h-10 !px-2 !py-2 text-sm"><X size={16} />Rechazar</button>
        <button disabled={action.isPending} onClick={() => { setMessage(""); action.mutate({ id: charge.id, action: "pay" }); }} className="btn-primary !min-h-10 !px-2 !py-2 text-sm"><Check size={16} />Pagar</button></div>
    </article>)}</div>
  </section>;
}
