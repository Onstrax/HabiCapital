export interface LoginResponse { expires_in: number; token_type: string; role: "USER" | "ADMIN" }
export interface RegisterResponse { id: string; email: string; alias: string; full_name: string }
export interface Balance { account_id: string; balance: number; currency: "COP" }
export interface Movement {
  reference_id: string; type: string; direction: "IN" | "OUT";
  amount: number; gmf_tax: number; total_debit: number; concept: string; counterparty_alias: string; created_at: string;
}
export interface Charge {
  id: string; requester_alias: string; payer_alias: string;
  amount: number; gmf_tax: number; total_debit: number; concept: string; status: "PENDING" | "COMPLETED" | "REJECTED" | "CANCELLED";
  created_at: string;
}
export interface CreatedCharge {
  id: string; group_id: string | null; payer_alias: string; masked_name: string;
  amount: number; gmf_tax: number; total_debit: number; percentage: number | null; concept: string;
  status: Charge["status"]; created_at: string; updated_at: string;
}
export interface Recipient { recipient_id: string; recipient_alias: string; masked_name: string; alias: string; amount: number | null; gmf_tax: number | null; total_debit: number | null }

export const formatCOP = (amount: number) => new Intl.NumberFormat("es-CO", {
  style: "currency", currency: "COP", maximumFractionDigits: 0,
}).format(amount);

export const formatDate = (value: string) => new Intl.DateTimeFormat("es-CO", {
  day: "numeric", month: "short", hour: "numeric", minute: "2-digit",
}).format(new Date(value));
