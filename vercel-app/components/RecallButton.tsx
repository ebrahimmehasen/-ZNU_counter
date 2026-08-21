"use client";

// "المناداة مرة أخرى" — lets /call and /admission replay the
// announcement for whoever they're currently serving (e.g. the student
// didn't hear their number) without re-claiming anyone or touching the
// queue. The actual re-announcement happens server-side: the RPC this
// button triggers (recall_ticket / admission_recall_ticket, see
// supabase/schema.sql) just re-stamps called_at/admission_called_at,
// which /view's display page treats as "new" and announces again.
//
// Two limits, both enforced here (client-side only — see the RPCs'
// comments for why that's an acceptable trust level for this feature):
// - a 60s cooldown before the button can be pressed at all (right after
//   the initial call) and again between each recall;
// - a hard cap of 2 recalls per served ticket. Past that, the button
//   locks with `lockedMessage` instead of a countdown, on the theory
//   that a student who didn't answer three calls probably isn't
//   there — the employee should move on rather than keep trying.
//
// Resets whenever the caller passes a new `lastCallAt` for a genuinely
// new ticket (a fresh call, not a recall) — see the calledAt-tracking
// in call/page.tsx and admission/page.tsx.

import { useEffect, useState } from "react";

const COOLDOWN_MS = 60_000;
const MAX_RECALLS = 2;

export default function RecallButton({
  lastCallAt,
  recallCount,
  onRecall,
  busy,
  lockedMessage,
}: {
  lastCallAt: number | null;
  recallCount: number;
  onRecall: () => void;
  busy: boolean;
  lockedMessage: string;
}) {
  // Re-render every second so the cooldown countdown/enable state keeps
  // up — lastCallAt/recallCount alone don't change while just waiting.
  const [, setTick] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), 1000);
    return () => clearInterval(id);
  }, []);

  if (lastCallAt === null) return null;

  if (recallCount >= MAX_RECALLS) {
    return (
      <button
        disabled
        className="w-full bg-slate-100 text-slate-400 font-bold text-sm rounded-lg py-3 cursor-not-allowed"
      >
        {lockedMessage}
      </button>
    );
  }

  const remainingMs = COOLDOWN_MS - (Date.now() - lastCallAt);
  const onCooldown = remainingMs > 0;

  return (
    <button
      onClick={onRecall}
      disabled={busy || onCooldown}
      className="w-full bg-slate-200 hover:bg-slate-300 disabled:bg-slate-100 disabled:text-slate-400 text-slate-700 font-bold text-sm rounded-lg py-3"
    >
      {onCooldown ? `المناداة مرة أخرى (${Math.ceil(remainingMs / 1000)})` : "المناداة مرة أخرى"}
    </button>
  );
}
