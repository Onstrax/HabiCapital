"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, X } from "lucide-react";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { api, ApiError } from "@/lib/api-client";
import { type Charge, formatCOP } from "@/lib/contracts";
import { clearChargeKey, stableChargeKey } from "@/lib/financial-retry";

const schema = z.object({
  payer_alias: z.string().regex(/^[a-z0-9_]{3,20}$/, "Ingresa el alias exacto (3 a 20 caracteres)"),
  amount: z.number({ invalid_type_error: "Ingresa un monto en pesos" }).int("Solo pesos enteros")
    .positive("El monto debe ser positivo").max(Number.MAX_SAFE_INTEGER, "Monto demasiado alto"),
  concept: z.string().trim().min(1, "Escribe un concepto").max(255, "Máximo 255 caracteres"),
});
type ChargeValues = z.infer<typeof schema>;

export function CreateChargeModal({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient();
  const [created, setCreated] = useState<Charge | null>(null);
  const [error, setError] = useState("");
  const [uncertain, setUncertain] = useState(false);
  const form = useForm<ChargeValues>({ resolver: zodResolver(schema) });
  const mutation = useMutation({
    mutationFn: async (values: ChargeValues) => {
      const payload = { payer_alias: values.payer_alias, amount: api.assertAmount(values.amount),
        concept: values.concept.trim() };
      return api.post<Charge>("/charges", payload, { idempotencyKey: await stableChargeKey(payload) });
    },
    onSuccess: (charge) => {
      clearChargeKey();
      setUncertain(false);
      setCreated(charge);
      setError("");
      void queryClient.invalidateQueries({ queryKey: ["charges"] });
    },
    onError: (cause) => {
      const ambiguous = !(cause instanceof ApiError) || cause.status >= 500 || cause.code === "IDEMPOTENCY_IN_PROGRESS";
      setUncertain(ambiguous);
      if (!ambiguous) clearChargeKey();
      setError(ambiguous ? "No pudimos confirmar si se creó el cobro. Reintenta con los mismos datos para consultar el resultado, o compruébalo con la otra persona."
        : cause instanceof ApiError && cause.code === "PAYER_NOT_FOUND" ? "No encontramos ese alias. Revísalo e intenta de nuevo."
        : cause instanceof ApiError && cause.code === "SELF_CHARGE_FORBIDDEN" ? "No puedes solicitarte un cobro a ti mismo."
        : cause instanceof ApiError ? cause.message : "No pudimos crear el cobro.");
    },
  });

  useEffect(() => {
    function handleKey(event: KeyboardEvent) { if (event.key === "Escape" && !mutation.isPending) onClose(); }
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [onClose, mutation.isPending]);

  return <div className="fixed inset-0 z-50 flex items-end justify-center bg-[#082a25]/60 p-0 sm:items-center sm:p-5"
    onMouseDown={(event) => { if (event.target === event.currentTarget && !mutation.isPending) onClose(); }}>
    <section role="dialog" aria-modal="true" aria-labelledby="charge-title"
      className="max-h-[100dvh] w-full max-w-lg overflow-y-auto rounded-t-[28px] bg-white p-6 shadow-2xl sm:max-h-[90dvh] sm:rounded-[28px] sm:p-8">
      <div className="mb-7 flex items-center justify-between gap-3"><div><p className="text-xs font-semibold uppercase tracking-widest text-[#5b997a]">Cobro P2P</p>
        <h2 id="charge-title" className="mt-1 text-2xl font-semibold">{created ? "Cobro solicitado" : "Solicitar un cobro"}</h2></div>
        <button type="button" onClick={onClose} aria-label="Cerrar" className="rounded-full p-2 hover:bg-cream"><X size={21} /></button></div>
      {created ? <div className="space-y-5 text-center"><CheckCircle2 size={52} className="mx-auto text-[#419e71]" />
        <p className="font-semibold">Solicitaste {formatCOP(created.amount)} a @{created.payer_alias}.</p>
        <p className="text-sm text-[#6c8074]">El cobro quedará pendiente hasta que esa persona lo pague o rechace.</p>
        <button type="button" onClick={onClose} className="btn-primary w-full">Volver al inicio</button></div>
        : <form onSubmit={form.handleSubmit((values) => { setError(""); mutation.mutate(values); })} className="space-y-5" noValidate>
          <p className="rounded-2xl bg-cream p-4 text-sm text-[#576f63]">La otra persona verá tu solicitud y decidirá si pagarla o rechazarla.</p>
          <div><label htmlFor="charge-payer" className="mb-2 block text-sm font-semibold">Alias de quien pagará</label>
            <input id="charge-payer" className="field" placeholder="ej. carlos_dev" autoComplete="off" disabled={uncertain}
              {...form.register("payer_alias")} aria-invalid={!!form.formState.errors.payer_alias} />
            {form.formState.errors.payer_alias && <p role="alert" className="mt-1 text-sm text-red-700">{form.formState.errors.payer_alias.message}</p>}</div>
          <div><label htmlFor="charge-amount" className="mb-2 block text-sm font-semibold">Monto en COP</label>
            <input id="charge-amount" className="field" type="number" min="1" step="1" inputMode="numeric" disabled={uncertain}
              {...form.register("amount", { valueAsNumber: true })} aria-invalid={!!form.formState.errors.amount} />
            {form.formState.errors.amount && <p role="alert" className="mt-1 text-sm text-red-700">{form.formState.errors.amount.message}</p>}</div>
          <div><label htmlFor="charge-concept" className="mb-2 block text-sm font-semibold">Concepto</label>
            <input id="charge-concept" className="field" placeholder="¿Qué necesitas cobrar?" disabled={uncertain}
              {...form.register("concept")} aria-invalid={!!form.formState.errors.concept} />
            {form.formState.errors.concept && <p role="alert" className="mt-1 text-sm text-red-700">{form.formState.errors.concept.message}</p>}</div>
          {error && <p role="alert" className="rounded-xl bg-red-50 p-3 text-sm text-red-800">{error}</p>}
          <button type="submit" disabled={mutation.isPending} className="btn-primary w-full">
            {mutation.isPending ? "Solicitando..." : uncertain ? "Reintentar el mismo cobro" : "Enviar solicitud"}
          </button>
        </form>}
    </section>
  </div>;
}
