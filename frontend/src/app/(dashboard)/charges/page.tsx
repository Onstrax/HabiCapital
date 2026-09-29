"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowLeft, HandCoins, Users } from "lucide-react";
import { api } from "@/lib/api-client";
import { Brand } from "@/components/Brand";
import { PaymentRequestsList } from "@/components/charges/PaymentRequestsList";
import { CreatedPaymentRequestsList } from "@/components/charges/CreatedPaymentRequestsList";
import { CreateChargeModal } from "@/components/charges/CreateChargeModal";
import { SplitPaymentModal } from "@/components/charges/SplitPaymentModal";

export default function ChargesPage() {
  const router = useRouter();
  const [ready, setReady] = useState(false);
  const [singleOpen, setSingleOpen] = useState(false);
  const [groupOpen, setGroupOpen] = useState(false);

  useEffect(() => {
    void api.get<{ authenticated: boolean; role: "USER" | "ADMIN" }>("/auth/session")
      .then((session) => { if (session.role !== "USER") router.replace("/admin"); else setReady(true); })
      .catch(() => router.replace("/login"));
  }, [router]);

  if (!ready) return <main role="status" className="flex min-h-screen items-center justify-center">Verificando tu sesión...</main>;
  return <div className="min-h-screen">
    <header className="border-b border-[#e5eae3] bg-white"><div className="mx-auto max-w-6xl px-5 py-4 sm:px-8"><Brand /></div></header>
    <main className="mx-auto max-w-6xl px-5 pb-20 pt-8 sm:px-8">
      <Link href="/" className="inline-flex items-center gap-2 text-sm font-semibold text-forest"><ArrowLeft size={16} /> Volver al inicio</Link>
      <div className="mt-6 flex flex-col gap-5 sm:flex-row sm:items-end sm:justify-between">
        <div><p className="text-sm font-semibold text-[#468d70]">TUS COBROS</p>
          <h1 className="mt-1 text-3xl font-semibold">Solicitudes y seguimiento</h1>
          <p className="mt-2 text-sm text-[#667b70]">Revisa lo que debes responder y el estado de cada cobro que has creado.</p></div>
        <div className="flex flex-col gap-2 sm:flex-row">
          <button type="button" className="btn-subtle" onClick={() => setSingleOpen(true)}><HandCoins size={17} /> Cobro individual</button>
          <button type="button" className="btn-primary" onClick={() => setGroupOpen(true)}><Users size={17} /> Dividir un cobro</button>
        </div>
      </div>
      <div className="mt-6 grid items-start gap-5 lg:grid-cols-2">
        <div><h2 className="mb-3 text-sm font-semibold text-[#468d70]">COBROS RECIBIDOS</h2><PaymentRequestsList /></div>
        <CreatedPaymentRequestsList />
      </div>
    </main>
    {singleOpen && <CreateChargeModal onClose={() => setSingleOpen(false)} />}
    {groupOpen && <SplitPaymentModal onClose={() => setGroupOpen(false)} />}
  </div>;
}
