import { Brand } from "@/components/Brand";

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return <main className="min-h-screen lg:grid lg:grid-cols-2">
    <div className="flex min-h-screen flex-col px-5 py-7 sm:px-10 lg:px-16 lg:py-10">
      <Brand href="/login" />
      <div className="mx-auto flex w-full max-w-[430px] flex-1 flex-col justify-center py-12">{children}</div>
      <p className="text-xs text-[#82928c]">© HabiCapital · Hecho para mover tu dinero con confianza.</p>
    </div>
    <aside className="relative hidden overflow-hidden bg-forest p-16 text-white lg:flex lg:flex-col lg:justify-end">
      <div className="pointer-events-none absolute -right-36 -top-32 size-[580px] rounded-full border-[84px] border-[#356b58]/50" />
      <div className="pointer-events-none absolute right-12 top-40 size-48 rounded-full bg-[#548e72]/25 blur-3xl" />
      <div className="relative max-w-md">
        <div className="mb-9 inline-flex rounded-full border border-[#9dccb1]/40 px-4 py-2 text-sm text-[#c0e6cd]">Una forma más simple de estar al día</div>
        <h2 className="text-5xl font-semibold leading-tight tracking-tight">Tu dinero, siempre en movimiento.</h2>
        <p className="mt-5 text-lg leading-relaxed text-[#c5ded2]">Envía, recibe y organiza tus cobros desde un solo lugar.</p>
      </div>
    </aside>
  </main>;
}
