"use client";

import { FormEvent, useEffect, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, LockKeyhole, Plus, Trash2, UnlockKeyhole, X } from "lucide-react";
import { api, ApiError } from "@/lib/api-client";
import { formatCOP, type CreatedCharge, type Recipient } from "@/lib/contracts";
import { FinancialBreakdown } from "@/components/FinancialBreakdown";
import { tryGmfBreakdown } from "@/lib/gmf-math";
import { parsePercent } from "@/lib/split-math";
import { clearGroupChargeKey, stableGroupChargeKey } from "@/lib/financial-retry";
import { useSplitCalculator } from "./useSplitCalculator";

type GroupResult = { group_id: string; total_amount: number; items: CreatedCharge[] };

export function SplitPaymentModal({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient();
  const [totalText, setTotalText] = useState("");
  const [concept, setConcept] = useState("");
  const [alias, setAlias] = useState("");
  const [match, setMatch] = useState<Recipient | null>(null);
  const [looking, setLooking] = useState(false);
  const [lookupError, setLookupError] = useState("");
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [error, setError] = useState("");
  const [uncertain, setUncertain] = useState(false);
  const [created, setCreated] = useState<GroupResult | null>(null);
  const total = Number(totalText);
  const split = useSplitCalculator(total);
  const validAmount = Number.isSafeInteger(total) && total > 0;
  const validTaxTotals = split.amounts?.every((amount) => tryGmfBreakdown(amount) !== null) ?? false;
  const validConcept = concept.trim().length > 0 && concept.trim().length <= 255;
  const badDraft = Object.values(drafts).some((value) => parsePercent(value) === null);

  useEffect(() => {
    setMatch(null);
    setLookupError("");
    if (!/^[a-z0-9_]{3,20}$/.test(alias) || uncertain || created) return;
    let active = true;
    const timer = setTimeout(() => {
      setLooking(true);
      void api.post<Recipient>("/transfers/lookup", { recipient_alias: alias }).then((found) => {
        if (active) setMatch(found);
      }).catch((cause) => {
        if (active) setLookupError(cause instanceof ApiError && cause.code === "RECIPIENT_NOT_FOUND"
          ? "Alias no encontrado" : "No pudimos validar el alias. Intenta de nuevo.");
      }).finally(() => { if (active) setLooking(false); });
    }, 350);
    return () => { active = false; clearTimeout(timer); };
  }, [alias, uncertain, created]);

  async function addRecipient() {
    if (!/^[a-z0-9_]{3,20}$/.test(alias) || uncertain) return;
    setError("");
    try {
      const found = match?.recipient_alias === alias ? match
        : await api.post<Recipient>("/transfers/lookup", { recipient_alias: alias });
      if (split.rows.some((row) => row.recipient_id === found.recipient_id)) {
        setLookupError("Este alias ya está en el grupo.");
        return;
      }
      split.add({ recipient_id: found.recipient_id, alias: found.recipient_alias,
                  masked_name: found.masked_name });
      setDrafts({});
      setAlias("");
      setMatch(null);
    } catch (cause) {
      setLookupError(cause instanceof ApiError ? cause.message : "No pudimos validar el alias.");
    }
  }

  const mutation = useMutation({
    mutationFn: async () => {
      const payload = { total_amount: api.assertAmount(total), concept: concept.trim(),
        recipients: split.rows.map((row) => ({ recipient_alias: row.alias,
          percentage: row.points / 100, is_locked: row.locked })) };
      return api.post<GroupResult>("/charges/group", payload,
        { idempotencyKey: await stableGroupChargeKey(payload) });
    },
    onSuccess: (result) => {
      clearGroupChargeKey();
      setUncertain(false);
      setCreated(result);
      setError("");
      void queryClient.invalidateQueries({ queryKey: ["charges"] });
    },
    onError: (cause) => {
      const ambiguous = !(cause instanceof ApiError) || cause.status >= 500 || cause.code === "IDEMPOTENCY_IN_PROGRESS";
      setUncertain(ambiguous);
      if (!ambiguous) clearGroupChargeKey();
      setError(ambiguous ? "No pudimos confirmar si se creó el grupo. Reintenta sin modificar los datos para recuperar el resultado."
        : cause instanceof ApiError ? cause.message : "No pudimos crear el cobro grupal.");
    },
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!validAmount || !validConcept || !split.valid || !validTaxTotals || badDraft || mutation.isPending) return;
    setError("");
    mutation.mutate();
  }

  const busy = mutation.isPending;
  return <div className="fixed inset-0 z-50 flex items-end justify-center bg-[#082a25]/60 sm:items-center sm:p-5"
    onMouseDown={(event) => { if (event.target === event.currentTarget && !busy) onClose(); }}>
    <section role="dialog" aria-modal="true" aria-labelledby="split-title"
      className="max-h-[100dvh] w-full max-w-2xl overflow-y-auto rounded-t-[28px] bg-white p-5 shadow-2xl sm:max-h-[90dvh] sm:rounded-[28px] sm:p-8">
      <div className="mb-5 flex items-start justify-between gap-3">
        <div><p className="text-xs font-semibold uppercase tracking-widest text-[#5b997a]">Cobro grupal</p>
          <h2 id="split-title" className="mt-1 text-2xl font-semibold">{created ? "Solicitudes enviadas" : "Dividir un cobro"}</h2></div>
        <button type="button" onClick={onClose} aria-label="Cerrar" className="rounded-full p-2 hover:bg-cream"><X size={20} /></button>
      </div>
      {created ? <div className="space-y-4 text-center"><CheckCircle2 className="mx-auto text-[#419e71]" size={48} />
        <p>Se enviaron {created.items.length} cobros por un total de {formatCOP(created.total_amount)}.</p>
        <button onClick={onClose} className="btn-primary w-full">Ver mis cobros</button></div> :
        <form onSubmit={submit} className="space-y-5">
          <div className="grid gap-4 sm:grid-cols-2"><div><label htmlFor="split-total" className="mb-2 block text-sm font-semibold">Monto total (COP)</label>
            <input id="split-total" className="field" type="number" min="1" step="1" required disabled={uncertain}
              value={totalText} onChange={(event) => setTotalText(event.target.value)} inputMode="numeric" /></div>
            <div><label htmlFor="split-concept" className="mb-2 block text-sm font-semibold">Concepto</label>
              <input id="split-concept" className="field" required maxLength={255} disabled={uncertain}
                value={concept} onChange={(event) => setConcept(event.target.value)} placeholder="Almuerzo de equipo" /></div></div>
          <div><label htmlFor="split-alias" className="mb-2 block text-sm font-semibold">Añadir destinatario por alias</label>
            <div className="flex gap-2"><input id="split-alias" className="field min-w-0 flex-1" maxLength={20}
              value={alias} disabled={uncertain} autoComplete="off" placeholder="alias exacto"
              onChange={(event) => setAlias(event.target.value.toLowerCase())} />
              <button type="button" className="btn-subtle shrink-0 !px-3" disabled={uncertain || looking || !/^[a-z0-9_]{3,20}$/.test(alias)}
                onClick={() => void addRecipient()}><Plus size={18} /> Añadir</button></div>
            {looking && <p role="status" className="mt-1 text-xs text-[#667b70]">Verificando alias...</p>}
            {match?.recipient_alias === alias && <p className="mt-1 text-sm text-forest">Identidad confirmada: {match.masked_name}</p>}
            {lookupError && <p role="alert" className="mt-1 text-sm text-red-700">{lookupError}</p>}
          </div>
          <p className="rounded-xl bg-mint p-3 text-sm">Cada pagador cubre su parte más GMF al pagar. Crear este grupo no debita tu cuenta; recibirás el monto solicitado.</p>
          <div><h3 className="text-sm font-semibold">Personas en el grupo</h3>
            <div className="mt-2 max-h-64 space-y-2 overflow-y-auto overscroll-contain">
              {split.rows.length === 0 && <p className="rounded-xl bg-cream p-4 text-sm">Añade al menos una persona.</p>}
              {split.rows.map((row, index) => <div key={row.recipient_id} className="grid grid-cols-[minmax(0,1fr)_6rem_auto] items-center gap-2 rounded-xl border border-[#e5eae3] p-3 sm:grid-cols-[minmax(0,1fr)_7rem_6rem_auto]">
                <div className="min-w-0"><p className="truncate text-sm font-semibold">@{row.alias}</p><p className="truncate text-xs text-[#667b70]">{row.masked_name}</p></div>
                <label className="text-xs"><span className="sr-only">Porcentaje de @{row.alias}</span>
                  <input aria-label={`Porcentaje de @${row.alias}`} type="text" inputMode="decimal" disabled={uncertain}
                    className="field !p-2 text-right text-sm" value={drafts[row.recipient_id] ?? (row.points / 100).toFixed(2)}
                    onChange={(event) => {
                      const value = event.target.value;
                      setDrafts((old) => ({ ...old, [row.recipient_id]: value }));
                      const points = parsePercent(value);
                      if (points !== null) split.edit(row.recipient_id, points);
                    }} />%</label>
                <p className="col-start-1 text-xs font-semibold text-forest sm:col-auto sm:text-right">{split.amounts ? formatCOP(split.amounts[index]) : "—"}</p>
                <div className="flex gap-1"><button type="button" aria-label={`${row.locked ? "Desbloquear" : "Bloquear"} @${row.alias}`}
                  title={row.locked ? "Desbloquear" : "Bloquear"} disabled={uncertain}
                  className="rounded-lg p-2 hover:bg-cream" onClick={() => { setDrafts({}); split.toggle(row.recipient_id); }}>
                  {row.locked ? <LockKeyhole size={17} /> : <UnlockKeyhole size={17} />}</button>
                  <button type="button" aria-label={`Quitar @${row.alias}`} disabled={uncertain}
                    className="rounded-lg p-2 hover:bg-cream" onClick={() => { setDrafts({}); split.remove(row.recipient_id); }}><Trash2 size={17} /></button></div>
                {split.amounts && <div className="col-span-full"><FinancialBreakdown amount={split.amounts[index]} payer={"@" + row.alias} /></div>}
              </div>)}
            </div>
            <p className={`mt-3 text-sm font-semibold ${split.points === 10_000 ? "text-forest" : "text-red-700"}`}>
              Total: {(split.points / 100).toFixed(2)}% / 100.00%</p>
            {split.rows.length > 0 && !split.valid && <p role="status" className="mt-1 text-xs text-red-700">Revisa los candados, porcentajes y montos: cada persona debe recibir al menos $1 COP.</p>}
          </div>
          {error && <p role="alert" className="rounded-xl bg-red-50 p-3 text-sm text-red-800">{error}</p>}
          <button type="submit" className="btn-primary w-full" disabled={busy || !validAmount || !validConcept || !split.valid || !validTaxTotals || badDraft}>
            {busy ? "Enviando..." : uncertain ? "Reintentar el mismo cobro" : "Enviar cobros grupales"}</button>
        </form>}
    </section>
  </div>;
}
