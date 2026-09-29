import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";
const cookieName = "habicapital_session";
const cookieOptions = { httpOnly: true, secure: process.env.SESSION_COOKIE_SECURE === "true",
  sameSite: "strict" as const, path: "/" };

async function forward(request: NextRequest, context: { params: { path: string[] } }) {
  const path = context.params.path.join("/");
  const base = process.env.BACKEND_URL ?? "http://localhost:8000";
  if (path === "auth/session" && request.method === "GET") {
    const session = request.cookies.get(cookieName)?.value;
    if (!session) {
      return NextResponse.json({ authenticated: false },
        { status: 401, headers: { "Cache-Control": "no-store" } });
    }
    try {
      const response = await fetch(new URL("/api/v1/auth/me", base), {
        headers: { authorization: `Bearer ${session}` }, cache: "no-store",
      });
      if (!response.ok) {
        const result = NextResponse.json({ authenticated: false },
          { status: 401, headers: { "Cache-Control": "no-store" } });
        result.cookies.set(cookieName, "", { ...cookieOptions, maxAge: 0 });
        return result;
      }
      const body = await response.json() as { role: "USER" | "ADMIN" };
      return NextResponse.json({ authenticated: true, role: body.role },
        { headers: { "Cache-Control": "no-store" } });
    } catch {
      return Response.json({ code: "API_UNAVAILABLE", message: "El servidor no está disponible. Intenta de nuevo." },
        { status: 503, headers: { "Cache-Control": "no-store" } });
    }
  }
  const origin = request.headers.get("origin");
  const configuredOrigin = process.env.APP_ORIGIN ?? request.nextUrl.origin;

  if (
    request.method !== "GET" &&
    origin !== request.nextUrl.origin &&
    origin !== configuredOrigin
  ) {
    return NextResponse.json(
      { code: "INVALID_ORIGIN", message: "Origen no autorizado" },
      { status: 403 },
    );
  }
  if (path === "auth/logout" && request.method === "POST") {
    const result = NextResponse.json({ ok: true }, { headers: { "Cache-Control": "no-store" } });
    result.cookies.set(cookieName, "", { ...cookieOptions, maxAge: 0 });
    return result;
  }
  const upstream = new URL(`/api/v1/${context.params.path.map(encodeURIComponent).join("/")}${request.nextUrl.search}`, base);
  const headers = new Headers();
  for (const header of ["content-type", "x-idempotency-key"]) {
    const value = request.headers.get(header);
    if (value) headers.set(header, value);
  }
  const session = request.cookies.get(cookieName)?.value;
  if (session) headers.set("authorization", `Bearer ${session}`);
  try {
    const response = await fetch(upstream, {
      method: request.method,
      headers,
      body: request.method === "GET" ? undefined : await request.arrayBuffer(),
      redirect: "manual",
      cache: "no-store",
    });
    const outHeaders = new Headers({ "Cache-Control": "no-store" });
    if (path === "auth/login" && response.ok) {
      const body = await response.json() as { access_token: string; expires_in: number; token_type: string; role: "USER" | "ADMIN" };
      const result = NextResponse.json({ expires_in: body.expires_in, token_type: body.token_type, role: body.role },
        { headers: outHeaders });
      result.cookies.set(cookieName, body.access_token,
        { ...cookieOptions, maxAge: Math.min(body.expires_in, 900) });
      return result;
    }
    for (const header of ["content-type", "x-cache"]) {
      const value = response.headers.get(header);
      if (value) outHeaders.set(header, value);
    }
    const result = new NextResponse(response.body, { status: response.status, headers: outHeaders });
    if (response.status === 401 && session) {
      result.cookies.set(cookieName, "", { ...cookieOptions, maxAge: 0 });
    }
    return result;
  } catch {
    return Response.json({ code: "API_UNAVAILABLE", message: "El servidor no está disponible. Intenta de nuevo." },
      { status: 503, headers: { "Cache-Control": "no-store" } });
  }
}

export const GET = forward;
export const POST = forward;
