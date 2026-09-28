"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { ArrowRight, UserRoundPlus } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { api, ApiError } from "@/lib/api-client";
import type { RegisterResponse } from "@/lib/contracts";

const schema = z.object({
  full_name: z.string().trim().min(2, "Ingresa tu nombre completo").max(150),
  email: z.string().email("Ingresa un correo válido"),
  alias: z.string().regex(/^[a-z0-9_]{3,20}$/, "Usa 3 a 20 letras minúsculas, números o _"),
  password: z.string().min(12, "Usa al menos 12 caracteres").max(128),
});
type Values = z.infer<typeof schema>;

export default function RegisterPage() {
  const router = useRouter();
  const [error, setError] = useState("");
  const { register, handleSubmit, formState: { errors, isSubmitting } } = useForm<Values>({ resolver: zodResolver(schema) });

  async function submit(values: Values) {
    setError("");
    try {
      await api.post<RegisterResponse>("/auth/register", values);
      router.push("/login?registered=1");
    } catch (cause) {
      setError(cause instanceof ApiError && cause.code === "IDENTITY_CONFLICT"
        ? "Este correo o alias ya está en uso." : "No pudimos crear tu cuenta. Intenta de nuevo.");
    }
  }

  return <section>
    <div className="mb-7 flex size-12 items-center justify-center rounded-2xl bg-mint text-forest"><UserRoundPlus size={23} /></div>
    <p className="mb-2 text-sm font-semibold text-[#468d70]">EMPECEMOS</p>
    <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">Abre tu cuenta</h1>
    <p className="mt-3 text-[#667b70]">Solo necesitamos unos datos para comenzar.</p>
    <form onSubmit={handleSubmit(submit)} className="mt-8 space-y-4" noValidate>
      {([
        ["full_name", "Nombre completo", "Juan Esteban Gómez", "name", "text"],
        ["email", "Correo electrónico", "tu@correo.com", "email", "email"],
        ["alias", "Tu alias", "juan_p2p", "username", "text"],
        ["password", "Contraseña", "Mínimo 12 caracteres", "new-password", "password"],
      ] as const).map(([key, label, placeholder, complete, type]) => <div key={key}>
        <label htmlFor={key} className="mb-2 block text-sm font-semibold">{label}</label>
        <input id={key} type={type} autoComplete={complete} className="field" placeholder={placeholder} {...register(key)} aria-invalid={!!errors[key]} />
        {errors[key] && <p role="alert" className="mt-1 text-sm text-red-700">{errors[key]?.message}</p>}
      </div>)}
      {error && <p role="alert" className="rounded-xl bg-red-50 p-3 text-sm text-red-800">{error}</p>}
      <button type="submit" disabled={isSubmitting} className="btn-primary w-full">{isSubmitting ? "Creando cuenta..." : "Crear cuenta"}<ArrowRight size={18} /></button>
    </form>
    <p className="mt-7 text-center text-sm text-[#667b70]">¿Ya tienes cuenta? <Link href="/login" className="font-semibold text-forest underline underline-offset-4">Iniciar sesión</Link></p>
  </section>;
}
