"use client";

import { useCallback, useEffect, useState } from "react";
import { supabase, todayBusinessDate } from "@/lib/supabaseClient";
import { buildingLabel, clearSelectedBuilding, getSelectedBuilding, programLabel, setSelectedBuilding } from "@/lib/buildings";
import BuildingPicker from "@/components/BuildingPicker";

const STORAGE_KEY = "queue_counter_number";

type CurrentTicket = { ticketNumber: number; program: string | null } | null;

type Message =
  | { kind: "empty" }
  | { kind: "finished"; ticketNumber: number }
  | { kind: "error"; text: string }
  | null;

// No sound on this page on purpose — this is the employee's own
// screen. The announcement plays on the public display page instead
// (see app/page.tsx), which is what the waiting room actually hears.
//
// This is a deliberate two-step flow, not one "next" button:
// 1. "اطلب رقم جديد" claims the next waiting ticket (call_next_ticket).
// 2. While serving it, the SAME button becomes "تمت المراجعة" —
//    pressing it only files the current student into their program
//    queue (finish_first_review); it does NOT also call a new one.
//    The button then reverts to step 1.
// A reviewer finishing with a student doesn't mean they're ready for
// the next one immediately (paperwork, a break) — collapsing both into
// one click was the bug this two-step shape exists to avoid. See
// finish_first_review() / call_next_ticket() in supabase/schema.sql.
//
// Multi-building: this whole page is scoped to one building, chosen
// once (BuildingPicker below) and remembered per browser, same pattern
// as the counter number. Every RPC call is scoped to it server-side —
// see p_building in supabase/schema.sql — so a mis-set counter number
// can never call a ticket from the wrong building.
export default function CallPage() {
  // null = still reading localStorage; "" = read, nothing chosen yet.
  const [building, setBuilding] = useState<string | null>(null);
  const [counterNumber, setCounterNumber] = useState<number | null>(null);
  const [setupValue, setSetupValue] = useState("1");
  const [servedCount, setServedCount] = useState(0);
  const [current, setCurrent] = useState<CurrentTicket>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<Message>(null);

  // Remembered per-device, so the employee at this counter only sets
  // it up once — reopening the page later goes straight to the call
  // screen, not back through setup.
  useEffect(() => {
    setBuilding(getSelectedBuilding());
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved) setCounterNumber(parseInt(saved, 10));
  }, []);

  function chooseBuilding(value: string) {
    setSelectedBuilding(value);
    setBuilding(value);
  }

  function changeBuilding() {
    clearSelectedBuilding();
    setBuilding("");
  }

  // Re-derived from the server, not just kept in React state — a page
  // refresh while mid-review must land back on "تمت المراجعة" for the
  // same student, not silently forget they're being served and offer
  // "اطلب رقم جديد" again (which would double-claim a new ticket while
  // the old one is still sitting there uncompleted).
  const refreshCurrent = useCallback(async (b: string, counter: number) => {
    const { data } = await supabase
      .from("tickets")
      .select("ticket_number, program")
      .eq("building", b)
      .eq("business_date", todayBusinessDate())
      .eq("status", "CALLED")
      .eq("counter_number", counter)
      .order("called_at", { ascending: false })
      .limit(1);
    const row = data?.[0];
    setCurrent(row ? { ticketNumber: row.ticket_number, program: row.program } : null);
  }, []);

  // Counted by counter_number, not by status='CALLED': a finished
  // student moves on to WAITING_FOR_ADMISSION/etc. but this counter
  // should still get credit for having served them (matches /view).
  const refreshServedCount = useCallback(async (b: string, counter: number) => {
    const { count } = await supabase
      .from("tickets")
      .select("uuid", { count: "exact", head: true })
      .eq("building", b)
      .eq("business_date", todayBusinessDate())
      .eq("counter_number", counter);
    setServedCount(count ?? 0);
  }, []);

  useEffect(() => {
    if (building && counterNumber !== null) {
      refreshCurrent(building, counterNumber);
      refreshServedCount(building, counterNumber);
    }
  }, [building, counterNumber, refreshCurrent, refreshServedCount]);

  function confirmSetup() {
    const n = parseInt(setupValue, 10);
    if (!Number.isInteger(n) || n < 1) return;
    localStorage.setItem(STORAGE_KEY, String(n));
    setCounterNumber(n);
  }

  function changeCounter() {
    localStorage.removeItem(STORAGE_KEY);
    setCounterNumber(null);
    setCurrent(null);
    setMessage(null);
  }

  async function requestNext() {
    if (!building || counterNumber === null) return;
    setBusy(true);
    setMessage(null);
    try {
      const { data, error } = await supabase.rpc("call_next_ticket", {
        p_building: building,
        p_business_date: todayBusinessDate(),
        p_counter_number: counterNumber,
      });
      if (error) throw error;

      const row = data?.[0];
      if (!row || row.out_ticket_number === null) {
        setMessage({ kind: "empty" });
        setCurrent(null);
      } else {
        // call_next_ticket() (unlike finish_first_review_and_call_next)
        // doesn't return the program in its result columns — it's the
        // older, untouched function other callers still rely on, so
        // its signature isn't changed here. One extra small lookup
        // instead.
        const { data: ticketRow } = await supabase
          .from("tickets")
          .select("program")
          .eq("building", building)
          .eq("business_date", todayBusinessDate())
          .eq("ticket_number", row.out_ticket_number)
          .single();
        setCurrent({
          ticketNumber: row.out_ticket_number,
          program: ticketRow?.program ?? null,
        });
        refreshServedCount(building, counterNumber);
      }
    } catch (e) {
      setMessage({ kind: "error", text: e instanceof Error ? e.message : "خطأ في الشبكة — حاول تاني." });
    } finally {
      setBusy(false);
    }
  }

  async function finishReview() {
    if (!building || counterNumber === null || !current) return;
    setBusy(true);
    setMessage(null);
    try {
      const { data, error } = await supabase.rpc("finish_first_review", {
        p_building: building,
        p_business_date: todayBusinessDate(),
        p_counter_number: counterNumber,
      });
      if (error) throw error;

      const finishedNumber = data?.[0]?.out_finished_ticket_number ?? current.ticketNumber;
      setMessage({ kind: "finished", ticketNumber: finishedNumber });
      setCurrent(null);
    } catch (e) {
      setMessage({ kind: "error", text: e instanceof Error ? e.message : "خطأ في الشبكة — حاول تاني." });
    } finally {
      setBusy(false);
    }
  }

  if (building === null) {
    return <div className="min-h-screen bg-slate-100" />; // pre-hydration blank, no flash
  }

  if (!building) {
    return <BuildingPicker onSelect={chooseBuilding} />;
  }

  if (counterNumber === null) {
    return (
      <div className="min-h-screen bg-slate-100 text-slate-800 flex items-center justify-center p-6">
        <div className="bg-white border border-slate-200 rounded-2xl shadow-sm px-10 py-9 w-full max-w-sm text-center">
          <div className="text-xs text-slate-500 mb-3">
            مبنى {building} — {buildingLabel(building)}{" "}
            <button onClick={changeBuilding} className="underline hover:text-blue-700 ms-1">
              (تغيير)
            </button>
          </div>
          <h1 className="text-xl font-bold text-blue-900 mb-1">رقم الشباك؟</h1>
          <p className="text-xs text-slate-500 mb-6">
            هيتحفظ على الجهاز ده — مش هيطلب منك تاني كل مرة تفتح الصفحة.
          </p>
          <input
            type="number"
            min={1}
            inputMode="numeric"
            value={setupValue}
            onChange={(e) => setSetupValue(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && confirmSetup()}
            className="w-full text-center text-2xl border border-slate-300 rounded-lg px-3 py-3 mb-5"
            autoFocus
          />
          <button
            onClick={confirmSetup}
            className="w-full bg-blue-600 hover:bg-blue-700 text-white font-extrabold text-lg rounded-lg py-4"
          >
            تأكيد
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-100 text-slate-800 flex items-center justify-center p-6">
      <div className="bg-white border border-slate-200 rounded-2xl shadow-sm px-10 py-9 w-full max-w-sm text-center">
        <div className="text-xs text-slate-500 mb-1">
          مبنى {building} — {buildingLabel(building)}{" "}
          <button onClick={changeBuilding} className="underline hover:text-blue-700 ms-1">
            (تغيير)
          </button>
        </div>
        <div className="text-xs text-slate-500 mb-1">
          شباك رقم <span className="font-bold text-slate-700">{counterNumber}</span>{" "}
          <button onClick={changeCounter} className="underline hover:text-blue-700 ms-1">
            (تغيير)
          </button>
        </div>
        <h1 className="text-xl font-bold text-blue-900 mb-4">استدعاء الأرقام</h1>

        <div className="bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 mb-6">
          <div className="text-xs text-slate-500">عدد الأرقام اللي خلّصتها النهارده</div>
          <div className="text-3xl font-extrabold text-slate-800">{servedCount}</div>
        </div>

        {current && (
          <div className="bg-blue-50 border border-blue-200 rounded-xl px-4 py-3 mb-4 text-center">
            <div className="text-xs text-blue-600 font-bold">بتراجع دلوقتي الرقم</div>
            <div className="text-3xl font-extrabold text-blue-900">{current.ticketNumber}</div>
            <div className="text-sm font-bold text-blue-700 mt-1">{programLabel(current.program)}</div>
          </div>
        )}

        {current ? (
          <button
            onClick={finishReview}
            disabled={busy}
            className="w-full bg-amber-600 hover:bg-amber-700 disabled:bg-slate-400 text-white font-extrabold text-lg rounded-lg py-5"
          >
            {busy ? "جاري الحفظ…" : "تمت المراجعة"}
          </button>
        ) : (
          <button
            onClick={requestNext}
            disabled={busy}
            className="w-full bg-blue-600 hover:bg-blue-700 disabled:bg-slate-400 text-white font-extrabold text-lg rounded-lg py-5"
          >
            {busy ? "جاري النداء…" : "اطلب رقم جديد"}
          </button>
        )}

        <div className="mt-5 min-h-[24px] text-sm flex flex-col gap-2">
          {message?.kind === "finished" && (
            <span className="text-slate-500 text-xs">
              الرقم #{message.ticketNumber} اتحوّل لشؤون الطلاب. اضغط &quot;اطلب رقم جديد&quot; لما تكون جاهز.
            </span>
          )}
          {message?.kind === "empty" && <span className="text-amber-700 font-bold">مفيش حد مستنّي دلوقتي.</span>}
          {message?.kind === "error" && <span className="text-red-700 font-bold">{message.text}</span>}
        </div>
      </div>
    </div>
  );
}
