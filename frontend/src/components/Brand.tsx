import Link from "next/link";
import { Landmark } from "lucide-react";

export function Brand({ href = "/" }: { href?: string }) {
  return <Link href={href} className="inline-flex items-center gap-3 font-bold tracking-tight text-ink" aria-label="HabiCapital, inicio">
    <span className="flex size-10 items-center justify-center rounded-xl bg-forest text-mint"><Landmark size={21} strokeWidth={2.2} /></span>
    <span className="text-xl">Habi<span className="text-[#449879]">Capital</span></span>
  </Link>;
}
