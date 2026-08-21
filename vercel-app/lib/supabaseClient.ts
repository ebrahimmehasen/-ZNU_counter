import { createClient } from "@supabase/supabase-js";

// Safe to expose in the browser: RLS on `tickets` only grants public
// SELECT plus execute on the call_next_ticket() RPC (SECURITY
// DEFINER) — see supabase/schema.sql in the repo root. There is no
// direct write path from this key beyond that vetted function.
const url = process.env.NEXT_PUBLIC_SUPABASE_URL!;
const anonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!;

if (!url || !anonKey) {
  throw new Error(
    "Missing NEXT_PUBLIC_SUPABASE_URL / NEXT_PUBLIC_SUPABASE_ANON_KEY. " +
      "Copy .env.local.example to .env.local and fill in your Supabase project's values."
  );
}

export const supabase = createClient(url, anonKey);

/** Local calendar date as YYYY-MM-DD, matching the desktop app's
 * `business_date` (Python `date.today().isoformat()`), not UTC. */
export function todayBusinessDate(): string {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

type RpcResponse<T> = { data: T | null; error: { message?: string; code?: string } | null };

/** A weak-connection failure — the request never got a response back
 * (offline, DNS hiccup, dropped connection, timeout) — vs. an actual
 * error response FROM Postgres/PostgREST, which always carries a
 * `code` (e.g. a raised exception, a constraint violation). Only the
 * former is safe to blindly retry: if `code` is set, the server did
 * receive and process the request, so retrying could double-apply a
 * write (most importantly, double-claim a ticket in call_next_ticket /
 * admission_claim_next) instead of just resending a lost request. */
function isRetryableNetworkError(error: { message?: string; code?: string } | null): boolean {
  if (!error || error.code) return false;
  return /fetch|network|timeout|offline|load failed/i.test(error.message || "");
}

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/** Wraps a `supabase.rpc(...)` call with up to `attempts` tries on a
 * flaky connection — see isRetryableNetworkError for exactly what
 * qualifies for a retry (and why claim-type RPCs are still safe to
 * wrap with this). Short, fixed backoff between attempts (not
 * exponential): these are interactive, employee-facing actions, not
 * background jobs — a few hundred ms is the point, not minutes. */
export async function rpcWithRetry<T>(
  fn: () => PromiseLike<RpcResponse<T>>,
  attempts = 3
): Promise<RpcResponse<T>> {
  let last: RpcResponse<T> = { data: null, error: null };
  for (let i = 0; i < attempts; i++) {
    try {
      last = await fn();
    } catch (e) {
      last = { data: null, error: { message: e instanceof Error ? e.message : String(e) } };
    }
    if (!last.error || !isRetryableNetworkError(last.error)) return last;
    if (i < attempts - 1) await sleep(300 * (i + 1));
  }
  return last;
}
