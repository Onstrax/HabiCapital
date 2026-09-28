"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { ArrowRight, Eye, EyeOff, LockKeyhole } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { api, ApiError, setAccessToken } from "@/lib/api-client";
import type { LoginResponse } from "@/lib/contracts";

const schema = z.object({ email: z.string().email("Ingresa un correo válido"), password: z.string().min(1, "Ingresa tu contraseña") });
type Values = z.infer<typeof schema>;

export default function LoginPage() {
  const router = useRouter();
  const [visible, setVisible] = useState(false);
  const [error, setError] = useState("");
  const { register, handleSubmit, formState: { errors, isSubmitting } } = useForm<Values>({ resolver: zodResolver(schema) });

  async function submit(values: Values) {
    setError("");
    try {
      const result = await api.post<LoginResponse>("/auth/login", values);
      setAccessToken(result.access_token);
      router.replace("/");
    } catch (cause) {
      setError(cause instanceof ApiError && cause.code === "INVALID_CREDENTIALS"
        ? "El correo o la contraseña no son correctos." : "No pudimos iniciar sesión. Intenta de nuevo.");
    }
  }

  return <section>
    <div className="mb-8 flex size-12 items-center justify-center rounded-2xl bg-mint text-forest"><LockKeyhole size={23} /></div>
    <p className="mb-2 text-sm font-semibold text-[#468d70]">QUÉ BUENO VERTE</p>
    <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">Bienvenido de nuevo</h1>
    <p className="mt-3 text-[#667b70]">Ingresa a tu espacio financiero.</p>
    <form onSubmit={handleSubmit(submit)} className="mt-9 space-y-5" noValidate>
      <div><label htmlFor="email" className="mb-2 block text-sm font-semibold">Correo electrónico</label>
        <input id="email" type="email" autoComplete="email" className="field" placeholder="tu@correo.com" {...register("email")} aria-invalid={!!errors.email} />
        {errors.email && <p role="alert" className="mt-1 text-sm text-red-700">{errors.email.message}</p>}</div>
      <div><label htmlFor="password" className="mb-2 block text-sm font-semibold">Contraseña</label>
        <div className="relative"><input id="password" type={visible ? "text" : "password"} autoComplete="current-password" className="field pr-14" placeholder="Tu contraseña" {...register("password")} aria-invalid={!!errors.password} />
          <button type="button" className="absolute inset-y-0 right-3 px-2 text-[#657b70]" aria-label={visible ? "Ocultar contraseña" : "Mostrar contraseña"} onClick={() => setVisible(!visible)}>{visible ? <EyeOff size={19} /> : <Eye size={19} />}</button></div>
        {errors.password && <p role="alert" className="mt-1 text-sm text-red-700">{errors.password.message}</p>}</div>
      {error && <p role="alert" className="rounded-xl bg-red-50 p-3 text-sm text-red-800">{error}</p>}
      <button type="submit" disabled={isSubmitting} className="btn-primary w-full">{isSubmitting ? "Entrando..." : "Iniciar sesión"}<ArrowRight size={18} /></button>
    </form>
    <p className="mt-8 text-center text-sm text-[#667b70]">¿Aún no tienes cuenta? <Link href="/register" className="font-semibold text-forest underline underline-offset-4">Crear cuenta</Link></p>
  </section>;
}
