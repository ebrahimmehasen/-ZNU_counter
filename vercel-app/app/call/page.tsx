"use client";

import { useCallback, useEffect, useState } from "react";
import { supabase, todayBusinessDate } from "@/lib/supabaseClient";

const STORAGE_KEY = "queue_counter_number";

type Result =
  | { kind: "success"; ticketNumber: number }
  | { kind: "empty" }
  | { kind: "error"; message: string }
  | null;

// No sound on this page on purpose — this is the employee's own
// screen. The announcement plays on the public display page instead
// (see app/page.tsx), which is what the waiting room actually hears.
export default function CallPage() {
  const [counterNumber, setCounterNumber] = useState<number | null>(null);
  const [setupValue, setSetupValue] = useState("1");
  const [servedCount, setServedCount] = useState(0);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<Result>(null);

  // Remembered per-device, so the employee at this counter only sets
  // it up once — reopening the page later goes straight to the call
  // screen, not back through setup.
  useEffect(() => {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved) setCounterNumber(parseInt(saved, 10));
  }, []);

  const refreshServedCount = useCallback(async (counter: number) => {
    const { count } = await supabase
      .from("tickets")
      .select("uuid", { count: "exact", head: true })
      .eq("business_date", todayBusinessDate())
      .eq("status", "CALLED")
      .eq("counter_number", counter);
    setServedCount(count ?? 0);
  }, []);

  useEffect(() => {
    if (counterNumber !== null) refreshServedCount(counterNumber);
  }, [counterNumber, refreshServedCount]);

  function confirmSetup() {
    const n = parseInt(setupValue, 10);
    if (!Number.isInteger(n) || n < 1) return;
    localStorage.setItem(STORAGE_KEY, String(n));
    setCounterNumber(n);
  }

  function changeCounter() {
    localStorage.removeItem(STORAGE_KEY);
    setCounterNumber(null);
    setResult(null);
  }

  async function requestNext() {
    if (counterNumber === null) return;
    setBusy(true);
    setResult(null);
    try {
      const { data, error } = await supabase.rpc("call_next_ticket", {
        p_business_date: todayBusinessDate(),
        p_counter_number: counterNumber,
      });
      if (error) throw error;

      if (!data || data.length === 0) {
        setResult({ kind: "empty" });
      } else {
        const ticketNumber = data[0].out_ticket_number;
        setResult({ kind: "success", ticketNumber });
        refreshServedCount(counterNumber);
      }
    } catch (e) {
      setResult({ kind: "error", message: e instanceof Error ? e.message : "خطأ في الشبكة — حاول تاني." });
    } finally {
      setBusy(false);
    }
  }

  if (counterNumber === null) {
    return (
      <div className="min-h-screen bg-slate-100 text-slate-800 flex items-center justify-center p-6">
        <div className="bg-white border border-slate-200 rounded-2xl shadow-sm px-10 py-9 w-full max-w-sm text-center">
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

        <button
          onClick={requestNext}
          disabled={busy}
          className="w-full bg-blue-600 hover:bg-blue-700 disabled:bg-slate-400 text-white font-extrabold text-lg rounded-lg py-5"
        >
          {busy ? "جاري النداء…" : "اطلب رقم جديد"}
        </button>

        <div className="mt-5 min-h-[24px] text-sm">
          {result?.kind === "success" && (
            <span className="text-green-700 font-bold">تم نداء الرقم #{result.ticketNumber}</span>
          )}
          {result?.kind === "empty" && <span className="text-amber-700 font-bold">مفيش حد مستنّي دلوقتي.</span>}
          {result?.kind === "error" && <span className="text-red-700 font-bold">{result.message}</span>}
        </div>
      </div>
    </div>
  );
}
