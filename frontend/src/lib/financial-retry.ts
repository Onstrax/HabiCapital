const retryKey = "habicapital_pending_transfer";

export async function stableTransferKey(payload: { recipient_id: string; amount: number; concept: string }): Promise<string> {
  const bytes = new TextEncoder().encode(JSON.stringify(payload));
  const hash = Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", bytes)),
    (value) => value.toString(16).padStart(2, "0")).join("");
  let saved: { hash?: string; key?: string; at?: number } = {};
  try { saved = JSON.parse(sessionStorage.getItem(retryKey) ?? "{}"); } catch { /* Discard malformed local state. */ }
  if (saved.hash === hash && saved.key && Date.now() - (saved.at ?? 0) < 23 * 60 * 60 * 1000) return saved.key;
  const key = crypto.randomUUID();
  sessionStorage.setItem(retryKey, JSON.stringify({ hash, key, at: Date.now() }));
  return key;
}

export function clearTransferKey() {
  sessionStorage.removeItem(retryKey);
}
