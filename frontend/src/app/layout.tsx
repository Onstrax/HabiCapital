import type { Metadata } from "next";
import { Providers } from "@/components/Providers";
import "./globals.css";

export const metadata: Metadata = {
  title: "HabiCapital | Tu dinero, en buenas manos",
  description: "Gestiona tus transferencias y cobros de forma segura.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return <html lang="es"><body><Providers>{children}</Providers></body></html>;
}
