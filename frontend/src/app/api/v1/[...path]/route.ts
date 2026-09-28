import { NextRequest } from "next/server";

export const dynamic = "force-dynamic";

async function forward(request: NextRequest, context: { params: { path: string[] } }) {
  const base = process.env.BACKEND_URL ?? "http://localhost:8000";
  const upstream = new URL(`/api/v1/${context.params.path.map(encodeURIComponent).join("/")}${request.nextUrl.search}`, base);
  const headers = new Headers();
  for (const header of ["authorization", "content-type", "x-idempotency-key"]) {
    const value = request.headers.get(header);
    if (value) headers.set(header, value);
  }
  try {
    const response = await fetch(upstream, {
      method: request.method,
      headers,
      body: request.method === "GET" ? undefined : await request.arrayBuffer(),
      redirect: "manual",
      cache: "no-store",
    });
    const outHeaders = new Headers({ "Cache-Control": "no-store" });
    for (const header of ["content-type", "x-cache"]) {
      const value = response.headers.get(header);
      if (value) outHeaders.set(header, value);
    }
    return new Response(response.body, { status: response.status, headers: outHeaders });
  } catch {
    return Response.json({ code: "API_UNAVAILABLE", message: "El servidor no está disponible. Intenta de nuevo." },
      { status: 503, headers: { "Cache-Control": "no-store" } });
  }
}

export const GET = forward;
export const POST = forward;
