const retryKey = "habicapital_pending_transfer";
const chargeRetryKey = "habicapital_pending_charge";

async function stableKey(storageKey: string, payload: object): Promise<string> {
  const bytes = new TextEncoder().encode(JSON.stringify(payload));
  const hash = Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", bytes)),
    (value) => value.toString(16).padStart(2, "0")).join("");
  let saved: { hash?: string; key?: string; at?: number } = {};
  try { saved = JSON.parse(sessionStorage.getItem(storageKey) ?? "{}"); } catch { /* Discard malformed local state. */ }
  if (saved.hash === hash && saved.key && Date.now() - (saved.at ?? 0) < 23 * 60 * 60 * 1000) return saved.key;
  const key = crypto.randomUUID();
  sessionStorage.setItem(storageKey, JSON.stringify({ hash, key, at: Date.now() }));
  return key;
}

export function stableTransferKey(payload: { recipient_id: string; amount: number; concept: string }): Promise<string> {
  return stableKey(retryKey, payload);
}

export function clearTransferKey() {
  sessionStorage.removeItem(retryKey);
}

export function stableChargeKey(payload: { payer_alias: string; amount: number; concept: string }): Promise<string> {
  return stableKey(chargeRetryKey, payload);
}

export function clearChargeKey() {
  sessionStorage.removeItem(chargeRetryKey);
}
