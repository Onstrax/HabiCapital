"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, ArrowRight, CheckCircle2, Search, X } from "lucide-react";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { api, ApiError } from "@/lib/api-client";
import { formatCOP, type Recipient } from "@/lib/contracts";
import { clearTransferKey, stableTransferKey } from "@/lib/financial-retry";

const lookupSchema = z.object({ recipient_alias: z.string().regex(/^[a-z0-9_]{3,20}$/, "Ingresa el alias exacto (3 a 20 caracteres)") });
const transferSchema = z.object({
  amount: z.number({ invalid_type_error: "Ingresa un monto en pesos" }).int("Solo pesos enteros")
    .positive("El monto debe ser positivo").max(Number.MAX_SAFE_INTEGER, "Monto demasiado alto"),
  concept: z.string().trim().min(1, "Escribe un concepto").max(255, "Máximo 255 caracteres"),
});
type LookupValues = z.infer<typeof lookupSchema>;
type TransferValues = z.infer<typeof transferSchema>;

export function TransferModal({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient();
  const [recipient, setRecipient] = useState<Recipient | null>(null);
  const [reference, setReference] = useState("");
  const [error, setError] = useState("");
  const [uncertain, setUncertain] = useState(false);
  const lookupForm = useForm<LookupValues>({ resolver: zodResolver(lookupSchema) });
  const transferForm = useForm<TransferValues>({ resolver: zodResolver(transferSchema) });
  const lookup = useMutation({ mutationFn: (values: LookupValues) => api.post<Recipient>("/transfers/lookup", values),
    onSuccess: (value) => { setRecipient(value); setError(""); },
    onError: (cause) => setError(cause instanceof ApiError && cause.code === "RECIPIENT_NOT_FOUND"
      ? "No encontramos ese alias. Revísalo e intenta de nuevo." : "No pudimos buscar el destinatario."),
  });
  const transfer = useMutation({
    mutationFn: async (values: TransferValues) => {
      const payload = { recipient_id: recipient!.recipient_id,
        amount: api.assertAmount(values.amount), concept: values.concept.trim() };
      return api.post<{ reference_id: string }>("/transfers/execute", payload,
        { idempotencyKey: await stableTransferKey(payload) });
    },
    onSuccess: (value) => {
      clearTransferKey();
      setUncertain(false);
      setReference(value.reference_id);
      setError("");
      void queryClient.invalidateQueries({ queryKey: ["ledger"] });
    },
    onError: (cause) => {
      const ambiguous = !(cause instanceof ApiError) || cause.status >= 500 || cause.code === "IDEMPOTENCY_IN_PROGRESS";
      setUncertain(ambiguous);
      if (!ambiguous) clearTransferKey();
      setError(ambiguous ? "No pudimos confirmar el resultado. Revisa tus movimientos antes de volver a intentar. Si reintentas este mismo pago, conservaremos su llave de seguridad."
        : cause instanceof ApiError && cause.code === "INSUFFICIENT_FUNDS" ? "Saldo insuficiente para esta transferencia."
        : cause instanceof ApiError ? cause.message : "No pudimos completar la transferencia.");
    },
  });
  useEffect(() => {
    function handleKey(event: KeyboardEvent) { if (event.key === "Escape" && !transfer.isPending) onClose(); }
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [onClose, transfer.isPending]);

  return <div className="fixed inset-0 z-50 flex items-end justify-center bg-[#082a25]/60 p-0 sm:items-center sm:p-5" onMouseDown={(event) => { if (event.target === event.currentTarget && !transfer.isPending) onClose(); }}>
    <section role="dialog" aria-modal="true" aria-labelledby="transfer-title" className="w-full max-w-lg rounded-t-[28px] bg-white p-6 shadow-2xl sm:rounded-[28px] sm:p-8">
      <div className="mb-7 flex items-center justify-between"><div><p className="text-xs font-semibold uppercase tracking-widest text-[#5b997a]">Transferencia segura</p>
        <h2 id="transfer-title" className="mt-1 text-2xl font-semibold">{reference ? "¡Listo!" : "Enviar dinero"}</h2></div>
        <button type="button" onClick={onClose} aria-label="Cerrar" className="rounded-full p-2 hover:bg-cream"><X size={21} /></button></div>
      {reference ? <div className="space-y-5 text-center"><CheckCircle2 size={52} className="mx-auto text-[#419e71]" />
        <p className="font-semibold">Tu transferencia se completó.</p><p className="break-all text-sm text-[#6c8074]">Referencia: {reference}</p>
        <button type="button" onClick={onClose} className="btn-primary w-full">Volver al inicio</button></div> : !recipient ? <form onSubmit={lookupForm.handleSubmit((values) => { setError(""); lookup.mutate(values); })} className="space-y-5" noValidate>
        <div className="flex items-center gap-3 rounded-2xl bg-cream p-4 text-sm text-[#576f63]"><Search size={20} className="shrink-0" /><span>Busca a la persona por su alias antes de enviar.</span></div>
        <div><label htmlFor="recipient_alias" className="mb-2 block text-sm font-semibold">Alias del destinatario</label>
          <input id="recipient_alias" className="field" placeholder="ej. carlos_dev" autoComplete="off" {...lookupForm.register("recipient_alias")} aria-invalid={!!lookupForm.formState.errors.recipient_alias} />
          {lookupForm.formState.errors.recipient_alias && <p role="alert" className="mt-1 text-sm text-red-700">{lookupForm.formState.errors.recipient_alias.message}</p>}</div>
        {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
        <button type="submit" className="btn-primary w-full" disabled={lookup.isPending}>{lookup.isPending ? "Buscando..." : "Buscar destinatario"}<ArrowRight size={18} /></button>
      </form> : <form onSubmit={transferForm.handleSubmit((values) => { setError(""); transfer.mutate(values); })} className="space-y-5" noValidate>
        <div className="rounded-2xl bg-mint p-4"><p className="text-xs font-semibold uppercase tracking-wide text-[#4d8067]">Confirma el destinatario</p>
          <p className="mt-2 text-lg font-semibold">{recipient.masked_name}</p><p className="text-sm text-[#446a59]">@{recipient.recipient_alias}</p></div>
        <div><label htmlFor="amount" className="mb-2 block text-sm font-semibold">Monto en COP</label>
          <input id="amount" type="number" min="1" step="1" inputMode="numeric" disabled={uncertain} className="field" placeholder="50.000" {...transferForm.register("amount", { valueAsNumber: true })} aria-invalid={!!transferForm.formState.errors.amount} />
          {transferForm.formState.errors.amount && <p role="alert" className="mt-1 text-sm text-red-700">{transferForm.formState.errors.amount.message}</p>}</div>
        <div><label htmlFor="concept" className="mb-2 block text-sm font-semibold">Concepto</label>
          <input id="concept" disabled={uncertain} className="field" placeholder="¿Para qué es?" {...transferForm.register("concept")} aria-invalid={!!transferForm.formState.errors.concept} />
          {transferForm.formState.errors.concept && <p role="alert" className="mt-1 text-sm text-red-700">{transferForm.formState.errors.concept.message}</p>}</div>
        <p className="text-sm text-[#667c6f]">Enviarás {Number.isSafeInteger(transferForm.watch("amount")) && transferForm.watch("amount") > 0 ? formatCOP(transferForm.watch("amount")) : "—"} a @{recipient.recipient_alias}.</p>
        {error && <p role="alert" className="rounded-xl bg-red-50 p-3 text-sm text-red-800">{error}</p>}
        <div className="flex flex-col-reverse gap-3 sm:flex-row"><button type="button" disabled={transfer.isPending || uncertain} className="btn-subtle sm:flex-1" onClick={() => { setRecipient(null); setError(""); }}><ArrowLeft size={18} />Atrás</button>
          <button type="submit" disabled={transfer.isPending} className="btn-primary sm:flex-[2]">{transfer.isPending ? "Enviando..." : uncertain ? "Reintentar el mismo pago" : "Confirmar transferencia"}</button></div>
      </form>}
    </section>
  </div>;
}
