"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowDownLeft, ArrowRight, ArrowUpRight, Clock3, HandCoins, LogOut, RefreshCw, Send, ShieldCheck, Wallet } from "lucide-react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Brand } from "@/components/Brand";
import { PaymentRequestsList } from "@/components/charges/PaymentRequestsList";
import { CreateChargeModal } from "@/components/charges/CreateChargeModal";
import { TransferModal } from "@/components/transfer/TransferModal";
import { api } from "@/lib/api-client";
import { formatCOP, formatDate, type Balance, type Movement } from "@/lib/contracts";
import { clearChargeKey, clearGroupChargeKey, clearTransferKey } from "@/lib/financial-retry";

export default function Dashboard() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [ready, setReady] = useState(false);
  const [transferOpen, setTransferOpen] = useState(false);
  const [chargeOpen, setChargeOpen] = useState(false);
  const [waking, setWaking] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const signOut = useCallback(async () => {
    await api.post("/auth/logout").catch(() => {});
    clearTransferKey();
    clearChargeKey();
    clearGroupChargeKey();
    queryClient.clear();
    router.replace("/login");
  }, [queryClient, router]);

  useEffect(() => {
    void api.get<{ authenticated: boolean; role: "USER" | "ADMIN" }>("/auth/session")
      .then((session) => {
        if (session.role === "ADMIN") router.replace("/admin");
        else setReady(true);
      }).catch(() => router.replace("/login"));
    window.addEventListener("habicapital:unauthorized", signOut);
    return () => window.removeEventListener("habicapital:unauthorized", signOut);
  }, [router, signOut]);
  const balance = useQuery({ queryKey: ["ledger", "balance"], queryFn: () => api.get<Balance>("/ledger/balance"), enabled: ready, refetchInterval: 15_000 });
  const movements = useQuery({ queryKey: ["ledger", "movements"], queryFn: () => api.get<{ items: Movement[] }>("/ledger/movements"), enabled: ready, refetchInterval: 30_000 });
  useEffect(() => {
    if (!ready || !balance.isFetching) { setWaking(false); return; }
    const timer = setTimeout(() => setWaking(true), 3000);
    return () => clearTimeout(timer);
  }, [ready, balance.isFetching]);
  if (!ready) return <main className="flex min-h-screen items-center justify-center" role="status">Preparando tu espacio...</main>;

  return <div className="min-h-screen">
    <header className="border-b border-[#e5eae3] bg-white"><div className="mx-auto flex max-w-6xl items-center justify-between px-5 py-4 sm:px-8 lg:px-10">
      <Brand /><div className="flex items-center gap-3"><span className="hidden rounded-full bg-mint px-3 py-2 text-xs font-semibold text-forest sm:inline-flex"><ShieldCheck size={15} className="mr-1" /> Tu espacio seguro</span>
        <button type="button" onClick={() => void signOut()} className="inline-flex items-center gap-2 rounded-xl p-2 text-sm text-[#526c5e] hover:bg-cream sm:px-3" aria-label="Cerrar sesión"><LogOut size={18} /><span className="hidden sm:inline">Salir</span></button></div></div></header>
    <main className="mx-auto max-w-6xl px-5 pb-24 pt-9 sm:px-8 sm:pt-12 lg:px-10">
      <div className="mb-8 flex flex-col justify-between gap-5 sm:flex-row sm:items-end"><div><p className="text-sm font-semibold text-[#468d70]">TU ESPACIO FINANCIERO</p>
        <h1 className="mt-1 text-3xl font-semibold tracking-tight sm:text-4xl">Todo en un solo lugar.</h1><p className="mt-2 text-[#66796e]">Mueve tu dinero con tranquilidad.</p></div>
        <div className="flex w-full flex-col gap-3 sm:w-auto sm:flex-row">
          <Link href="/charges" className="btn-subtle w-full sm:w-auto"><HandCoins size={18} /> Mis cobros</Link>
          <button type="button" className="btn-subtle w-full sm:w-auto" onClick={() => setChargeOpen(true)}><HandCoins size={18} /> Solicitar cobro</button>
          <button type="button" className="btn-primary w-full sm:w-auto" onClick={() => setTransferOpen(true)}><Send size={18} /> Enviar dinero <ArrowRight size={18} /></button>
        </div></div>
      <div className="grid gap-5 lg:grid-cols-[minmax(0,1.35fr)_minmax(300px,1fr)]">
        <section aria-labelledby="balance-heading" className="relative overflow-hidden rounded-[28px] bg-forest p-6 text-white shadow-card sm:p-8">
          <div className="pointer-events-none absolute -right-12 -top-24 size-64 rounded-full border-[45px] border-[#6ba27f]/20" />
          <div className="relative flex items-start justify-between"><div className="flex size-11 items-center justify-center rounded-2xl bg-white/15"><Wallet size={23} /></div>
            <span className="flex items-center gap-2 rounded-full border border-white/20 px-3 py-1.5 text-xs text-mint"><span className={`size-2 rounded-full ${balance.isError ? "bg-red-300" : "bg-[#78d69f]"}`} />{balance.isError ? "Sin conexión" : balance.isFetching ? "Actualizando" : "Saldo en vivo"}</span></div>
          <h2 id="balance-heading" className="relative mt-10 text-sm text-[#c3ded0]">Saldo disponible</h2>
          <p aria-live="polite" className="relative mt-2 break-all text-4xl font-semibold tracking-tight sm:text-5xl">{balance.isLoading ? "Cargando..." : balance.data ? formatCOP(balance.data.balance) : "—"}</p>
          <div className="relative mt-8 flex flex-wrap items-center justify-between gap-3 border-t border-white/20 pt-5 text-sm text-[#c3ded0]"><span>Pesos colombianos · COP</span>
            <button type="button" aria-label="Actualizar saldo" onClick={() => void balance.refetch()} disabled={balance.isFetching} className="inline-flex items-center gap-2 hover:text-white"><RefreshCw size={15} className={balance.isFetching ? "animate-spin" : ""} />Actualizar</button></div>
          {waking && <p role="status" className="relative mt-4 text-sm text-mint">Despertando servidor seguro... Esto puede tardar un momento.</p>}
          {balance.isError && <p role="alert" className="relative mt-4 text-sm text-red-200">No se pudo consultar el saldo. Intenta actualizarlo.</p>}
        </section>
        <div className="surface flex flex-col justify-between p-6 sm:p-8"><div><div className="mb-5 flex size-11 items-center justify-center rounded-2xl bg-mint text-forest"><ArrowUpRight size={23} /></div>
          <h2 className="text-xl font-semibold">Tu dinero, a tu ritmo.</h2><p className="mt-2 max-w-sm text-sm leading-relaxed text-[#688073]">Envía a cualquier persona por su alias y confirma su identidad antes de transferir.</p></div>
          <button type="button" onClick={() => setTransferOpen(true)} className="mt-6 inline-flex items-center gap-2 font-semibold text-forest">Hacer una transferencia <ArrowRight size={17} /></button></div>
      </div>
      <div className="mt-5 grid items-start gap-5 lg:grid-cols-[minmax(0,1.35fr)_minmax(300px,1fr)]">
        <section className="surface p-5 sm:p-7" aria-labelledby="movements-heading"><div className="mb-6 flex items-center justify-between gap-2"><div><p className="text-xs font-semibold uppercase tracking-widest text-[#638c76]">TUS MOVIMIENTOS</p>
          <h2 id="movements-heading" className="mt-1 text-xl font-semibold">Actividad reciente</h2></div>
          <button type="button" aria-label="Actualizar movimientos" onClick={async () => { setRefreshing(true); try { await movements.refetch(); } finally { setRefreshing(false); } }} className="rounded-xl p-2 text-[#648273] hover:bg-cream"><RefreshCw size={18} className={refreshing ? "animate-spin" : ""} /></button></div>
          {movements.isLoading && <p role="status" className="text-sm text-[#6b7e71]">Cargando movimientos...</p>}
          {movements.isError && <p role="alert" className="text-sm text-red-700">No pudimos cargar el historial. <button onClick={() => void movements.refetch()} className="font-semibold underline">Reintentar</button></p>}
          {movements.data?.items.length === 0 && <div className="rounded-2xl bg-cream px-6 py-10 text-center"><Clock3 className="mx-auto mb-3 text-[#669b7f]" />
            <p className="font-medium">Aún no hay movimientos</p><p className="mt-1 text-sm text-[#728277]">Tus transferencias aparecerán aquí.</p></div>}
          <ul className="max-h-[26rem] divide-y divide-[#e9eee7] overflow-y-auto overscroll-contain pr-2" tabIndex={movements.data?.items.length ? 0 : -1} aria-label="Historial de movimientos recientes">{movements.data?.items.map((item) => <li key={item.reference_id} className="flex items-center gap-3 py-4 first:pt-0">
            <div className={`flex size-11 shrink-0 items-center justify-center rounded-2xl ${item.direction === "IN" ? "bg-mint text-forest" : "bg-[#f7ede2] text-[#a77845]"}`}>
              {item.direction === "IN" ? <ArrowDownLeft size={20} /> : <ArrowUpRight size={20} />}</div>
            <div className="min-w-0 flex-1"><p className="truncate font-semibold">{item.concept}</p><p className="mt-0.5 truncate text-xs text-[#748579]">{item.direction === "IN" ? "De" : "A"} @{item.counterparty_alias} · {formatDate(item.created_at)}</p></div>
            <p className={`shrink-0 font-semibold ${item.direction === "IN" ? "text-[#29845e]" : "text-ink"}`}>{item.direction === "IN" ? "+" : "−"}{formatCOP(item.amount)}</p></li>)}</ul>
        </section>
        <PaymentRequestsList />
      </div>
    </main>
    {transferOpen && <TransferModal onClose={() => setTransferOpen(false)} />}
    {chargeOpen && <CreateChargeModal onClose={() => setChargeOpen(false)} />}
  </div>;
}
