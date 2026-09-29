"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, ApiError } from "@/lib/api-client";
import { formatDate } from "@/lib/contracts";

type AuditItem = {
  id: string;
  user_id: string | null;
  action: string;
  payload: Record<string, unknown>;
  created_at: string;
};
type AuditPage = { items: AuditItem[]; next_offset: number | null };

export function AuditLogList() {
  const [offset, setOffset] = useState(0);
  const { data, isPending, isError, error, refetch, isFetching } = useQuery({
    queryKey: ["admin-audit", offset],
    queryFn: () => api.get<AuditPage>(`/admin/audit?limit=20&offset=${offset}`),
    staleTime: 15_000,
    retry: false,
  });

  return <section className="surface mt-8 p-5 sm:p-8" aria-label="Consulta de auditoría">
    <h2 className="text-xl font-semibold">Auditoría</h2>
    <p className="mt-1 text-sm text-[#667b70]">Eventos recientes; solo visibles para el administrador.</p>
    {isPending && <p role="status" className="mt-5 text-sm">Cargando eventos...</p>}
    {isError && <div className="mt-5" role="alert">
      <p className="text-sm text-red-800">{error instanceof ApiError ? error.message : "No se pudo consultar la auditoría."}</p>
      <button type="button" onClick={() => void refetch()} className="mt-2 text-sm font-semibold text-forest">Reintentar</button>
    </div>}
    {data && <>
      <div className="mt-5 max-h-96 space-y-3 overflow-y-auto pr-1">
        {data.items.length === 0 && <p className="text-sm text-[#667b70]">Sin eventos en esta página.</p>}
        {data.items.map((event) => <article key={event.id} className="rounded-xl border border-[#e5eae3] p-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <strong className="break-all text-sm">{event.action}</strong>
            <time className="text-xs text-[#667b70]" dateTime={event.created_at}>{formatDate(event.created_at)}</time>
          </div>
          <p className="mt-2 break-all text-xs text-[#667b70]">Actor: {event.user_id ?? "Sistema"}</p>
          <pre className="mt-2 max-h-28 overflow-auto whitespace-pre-wrap break-all rounded-lg bg-cream p-2 text-xs">{JSON.stringify(event.payload, null, 2)}</pre>
        </article>)}
      </div>
      <div className="mt-4 flex items-center justify-between gap-4 text-sm">
        <button type="button" disabled={offset === 0 || isFetching} onClick={() => setOffset(Math.max(0, offset - 20))} className="font-semibold text-forest disabled:opacity-40">Anterior</button>
        <span>Página {Math.floor(offset / 20) + 1}</span>
        <button type="button" disabled={data.next_offset === null || isFetching} onClick={() => setOffset(data.next_offset!)} className="font-semibold text-forest disabled:opacity-40">Siguiente</button>
      </div>
    </>}
  </section>;
}
