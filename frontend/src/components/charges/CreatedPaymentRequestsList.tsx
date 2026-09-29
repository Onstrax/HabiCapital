"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "@/lib/api-client";
import { formatCOP, formatDate, type CreatedCharge } from "@/lib/contracts";

type Page = { items: CreatedCharge[]; next_offset: number | null };

const statusStyles: Record<CreatedCharge["status"], string> = {
  PENDING: "bg-amber-100 text-amber-800",
  COMPLETED: "bg-emerald-100 text-emerald-800",
  REJECTED: "bg-red-100 text-red-800",
  CANCELLED: "bg-slate-100 text-slate-700",
};
const statusLabels: Record<CreatedCharge["status"], string> = {
  PENDING: "Pendiente", COMPLETED: "Pagado", REJECTED: "Rechazado", CANCELLED: "Cancelado",
};

export function CreatedPaymentRequestsList() {
  const queryClient = useQueryClient();
  const [offset, setOffset] = useState(0);
  const [error, setError] = useState("");
  const created = useQuery({
    queryKey: ["charges", "created", offset],
    queryFn: () => api.get<Page>(`/charges/created?limit=20&offset=${offset}`),
    refetchInterval: 30_000,
    retry: false,
  });
  const cancel = useMutation({
    mutationFn: (id: string) => api.post(`/charges/${encodeURIComponent(id)}/cancel`),
    onSuccess: () => {
      setError("");
      void queryClient.invalidateQueries({ queryKey: ["charges"] });
    },
    onError: (cause) => {
      setError(cause instanceof ApiError ? cause.message : "No se pudo cancelar el cobro.");
      void queryClient.invalidateQueries({ queryKey: ["charges", "created"] });
    },
  });

  return <section className="surface p-5 sm:p-7" aria-labelledby="created-charges-heading">
    <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
      <div><p className="text-xs font-semibold uppercase tracking-widest text-[#638c76]">SOLICITUDES ENVIADAS</p>
        <h2 id="created-charges-heading" className="mt-1 text-xl font-semibold">Cobros emitidos por mí</h2></div>
      <button type="button" onClick={() => void created.refetch()} disabled={created.isFetching}
        className="text-sm font-semibold text-forest disabled:opacity-50">Actualizar</button>
    </div>
    {error && <p role="alert" className="mb-3 text-sm text-red-700">{error}</p>}
    {created.isPending && <p role="status" className="text-sm">Cargando solicitudes...</p>}
    {created.isError && <p role="alert" className="text-sm text-red-700">No se pudieron cargar tus cobros.
      <button type="button" onClick={() => void created.refetch()} className="ml-2 font-semibold underline">Reintentar</button></p>}
    {created.data && <>
      <div className="max-h-[26rem] space-y-3 overflow-y-auto overscroll-contain pr-2" tabIndex={created.data.items.length ? 0 : -1}
        role="region" aria-label="Cobros emitidos y sus estados">
        {created.data.items.length === 0 && <p className="rounded-xl bg-cream p-5 text-sm">Aún no has emitido cobros.</p>}
        {created.data.items.map((item) => <article key={item.id} className="rounded-2xl border border-[#e7ece5] p-4">
          <div className="flex flex-wrap items-start justify-between gap-2">
            <div className="min-w-0"><p className="font-semibold">@{item.payer_alias} · {item.masked_name}</p>
              <p className="mt-1 break-words text-sm text-[#718276]">{item.concept}</p></div>
            <span className={`rounded-full px-3 py-1 text-xs font-semibold ${statusStyles[item.status]}`}>{statusLabels[item.status]}</span>
          </div>
          <p className="mt-3 text-sm font-semibold text-forest">{formatCOP(item.amount)}
            {item.percentage !== null && <span className="ml-2 text-xs text-[#667b70]">{item.percentage.toFixed(2)}%</span>}</p>
          <p className="mt-1 text-xs text-[#667b70]">Creado: {formatDate(item.created_at)} · Actualizado: {formatDate(item.updated_at)}</p>
          {item.status === "PENDING" && <button type="button" className="mt-3 text-sm font-semibold text-red-700"
            disabled={cancel.isPending} onClick={() => cancel.mutate(item.id)}>
            {cancel.isPending && cancel.variables === item.id ? "Cancelando..." : "Cancelar cobro"}
          </button>}
        </article>)}
      </div>
      <div className="mt-4 flex items-center justify-between text-sm">
        <button type="button" className="font-semibold text-forest disabled:opacity-40" disabled={offset === 0 || created.isFetching}
          onClick={() => setOffset(Math.max(0, offset - 20))}>Anterior</button>
        <span>Página {Math.floor(offset / 20) + 1}</span>
        <button type="button" className="font-semibold text-forest disabled:opacity-40" disabled={created.data.next_offset === null || created.isFetching}
          onClick={() => setOffset(created.data.next_offset!)}>Siguiente</button>
      </div>
    </>}
  </section>;
}
