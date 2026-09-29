"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft, LogOut, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { api, ApiError } from "@/lib/api-client";
import { Brand } from "@/components/Brand";
import { formatCOP } from "@/lib/contracts";

interface TopupResult {
  reference_id: string;
  target_alias: string;
  amount_credited: number;
  new_target_balance: number;
}

export default function AdminPage() {
  const router = useRouter();
  const [ready, setReady] = useState(false);
  const [alias, setAlias] = useState("");
  const [amount, setAmount] = useState("");
  const [concept, setConcept] = useState("Recarga administrativa");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    void api.get<{ authenticated: boolean; role: "USER" | "ADMIN" }>("/auth/session")
      .then((session) => {
        if (session.role !== "ADMIN") router.replace("/");
        else setReady(true);
      }).catch(() => router.replace("/login"));
  }, [router]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setMessage("");
    const numericAmount = Number(amount);
    try {
      api.assertAmount(numericAmount);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Monto inválido.");
      return;
    }
    setBusy(true);
    try {
      const result = await api.post<TopupResult>("/admin/topup", {
        target_user_alias: alias.trim().toLowerCase(), amount: numericAmount, concept: concept.trim(),
      });
      setMessage(`Se abonaron ${formatCOP(result.amount_credited)} a @${result.target_alias}. Saldo nuevo: ${formatCOP(result.new_target_balance)}.`);
      setAlias("");
      setAmount("");
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "No se pudo realizar la recarga.");
    } finally {
      setBusy(false);
    }
  }

  async function signOut() {
    await api.post("/auth/logout").catch(() => {});
    router.replace("/login");
  }

  if (!ready) return <main className="flex min-h-screen items-center justify-center" role="status">Verificando administrador...</main>;

  return <div className="min-h-screen">
    <header className="border-b border-[#e5eae3] bg-white">
      <div className="mx-auto flex max-w-5xl items-center justify-between px-5 py-4 sm:px-8">
        <Brand />
        <button type="button" onClick={() => void signOut()} className="inline-flex items-center gap-2 rounded-xl p-2 text-sm text-[#526c5e] hover:bg-cream" aria-label="Cerrar sesión">
          <LogOut size={18} /><span>Salir</span>
        </button>
      </div>
    </header>
    <main className="mx-auto max-w-5xl px-5 py-9 sm:px-8 sm:py-12">
      <Link href="/" className="inline-flex items-center gap-2 text-sm font-semibold text-forest"><ArrowLeft size={16} /> Ir al inicio</Link>
      <section className="surface mx-auto mt-6 max-w-xl p-6 sm:p-9">
        <div className="mb-5 flex size-12 items-center justify-center rounded-2xl bg-mint text-forest"><ShieldCheck size={24} /></div>
        <p className="text-sm font-semibold text-[#468d70]">ADMINISTRACIÓN</p>
        <h1 className="mt-1 text-3xl font-semibold tracking-tight">Cargar saldo</h1>
        <p className="mt-2 text-sm leading-relaxed text-[#667b70]">El abono se registra en el ledger desde la cuenta del sistema. Cada recarga requiere una cuenta de usuario activa.</p>
        <form onSubmit={submit} className="mt-7 space-y-5">
          <div>
            <label htmlFor="target-alias" className="mb-2 block text-sm font-semibold">Alias del usuario</label>
            <input id="target-alias" required minLength={3} maxLength={20} pattern="[a-z0-9_]{3,20}" value={alias} onChange={(event) => setAlias(event.target.value)} className="field" autoComplete="off" placeholder="juan_juan" />
          </div>
          <div>
            <label htmlFor="topup-amount" className="mb-2 block text-sm font-semibold">Monto en pesos (COP)</label>
            <input id="topup-amount" required type="number" min="1" step="1" value={amount} onChange={(event) => setAmount(event.target.value)} className="field" inputMode="numeric" placeholder="100000" />
          </div>
          <div>
            <label htmlFor="topup-concept" className="mb-2 block text-sm font-semibold">Concepto</label>
            <input id="topup-concept" required minLength={1} maxLength={255} value={concept} onChange={(event) => setConcept(event.target.value)} className="field" />
          </div>
          {error && <p role="alert" className="rounded-xl bg-red-50 p-3 text-sm text-red-800">{error}</p>}
          {message && <p role="status" className="rounded-xl bg-mint p-3 text-sm text-forest">{message}</p>}
          <button type="submit" disabled={busy} className="btn-primary w-full">{busy ? "Procesando..." : "Confirmar recarga"}</button>
        </form>
      </section>
    </main>
  </div>;
}
