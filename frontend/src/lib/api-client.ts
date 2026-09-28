export interface BankErrorBody {
  code?: string;
  message?: string;
  details?: Record<string, unknown>;
}

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string, public details: Record<string, unknown> = {}) {
    super(message);
    this.name = "ApiError";
  }
}

const tokenKey = "habicapital_access_token";
let tokenInMemory: string | null = null;

export function setAccessToken(token: string | null) {
  tokenInMemory = token;
  if (typeof window !== "undefined") {
    if (token) window.sessionStorage.setItem(tokenKey, token);
    else window.sessionStorage.removeItem(tokenKey);
  }
}

export function getAccessToken(): string | null {
  if (typeof window === "undefined") return tokenInMemory;
  return tokenInMemory ?? window.sessionStorage.getItem(tokenKey);
}

async function request<T>(method: "GET" | "POST", path: string, body?: unknown,
  options?: { idempotencyKey?: string }): Promise<T> {
  const headers: Record<string, string> = {};
  const token = getAccessToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  if (method === "POST") {
    headers["Content-Type"] = "application/json";
    headers["X-Idempotency-Key"] = options?.idempotencyKey ?? crypto.randomUUID();
  }
  const response = await fetch(`/api/v1${path}`, {
    method, headers, body: method === "POST" ? JSON.stringify(body ?? {}) : undefined,
    cache: "no-store",
  });
  const data: unknown = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = (data && typeof data === "object" ? data : {}) as BankErrorBody;
    if (response.status === 401 && token) {
      setAccessToken(null);
      if (typeof window !== "undefined") window.dispatchEvent(new Event("habicapital:unauthorized"));
    }
    throw new ApiError(response.status, error.code ?? "REQUEST_FAILED",
      error.message ?? "No pudimos completar la solicitud.", error.details);
  }
  return data as T;
}

export const api = {
  get: <T>(path: string) => request<T>("GET", path),
  post: <T>(path: string, body?: unknown, options?: { idempotencyKey?: string }) => request<T>("POST", path, body, options),
  assertAmount(amount: number) {
    if (!Number.isSafeInteger(amount) || amount <= 0) throw new Error("Ingresa un monto entero válido en pesos.");
    return amount;
  },
};
