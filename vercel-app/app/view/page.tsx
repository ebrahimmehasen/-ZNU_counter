"use client";

import { useCallback, useEffect, useState } from "react";
import { supabase, todayBusinessDate } from "@/lib/supabaseClient";

type CalledTicket = { ticket_number: number; called_at: string };
type CounterStats = { counterNumber: number; tickets: CalledTicket[] };

async function fetchCounterStats(businessDate: string): Promise<CounterStats[]> {
  const { data } = await supabase
    .from("tickets")
    .select("ticket_number, counter_number, called_at")
    .eq("business_date", businessDate)
    .eq("status", "CALLED")
    .order("called_at", { ascending: true });

  const byCounter = new Map<number, CalledTicket[]>();
  for (const row of data || []) {
    const list = byCounter.get(row.counter_number) || [];
    list.push({ ticket_number: row.ticket_number, called_at: row.called_at });
    byCounter.set(row.counter_number, list);
  }

  return [...byCounter.entries()]
    .map(([counterNumber, tickets]) => ({ counterNumber, tickets }))
    .sort((a, b) => a.counterNumber - b.counterNumber);
}

export default function ViewPage() {
  const [stats, setStats] = useState<CounterStats[]>([]);
  const [businessDate, setBusinessDate] = useState("");
  const [openCounter, setOpenCounter] = useState<number | null>(null);
  const [offline, setOffline] = useState(false);

  useEffect(() => {
    setBusinessDate(todayBusinessDate());
  }, []);

  const refresh = useCallback(async () => {
    if (!businessDate) return;
    try {
      setStats(await fetchCounterStats(businessDate));
      setOffline(false);
    } catch {
      setOffline(true);
    }
  }, [businessDate]);

  useEffect(() => {
    if (!businessDate) return;
    refresh();

    const channel = supabase
      .channel("counter-view")
      .on(
        "postgres_changes",
        { event: "*", schema: "public", table: "tickets", filter: `business_date=eq.${businessDate}` },
        () => refresh()
      )
      .subscribe();

    const interval = setInterval(refresh, 5000);
    return () => {
      supabase.removeChannel(channel);
      clearInterval(interval);
    };
  }, [refresh, businessDate]);

  const total = stats.reduce((sum, c) => sum + c.tickets.length, 0);

  return (
    <div className="min-h-screen bg-slate-100 text-slate-800 flex flex-col items-center px-4 py-8 gap-5">
      <header className="text-center">
        <h1 className="text-xl font-extrabold text-blue-900">إحصائية المكاتب</h1>
        <div className="text-xs text-slate-500 mt-1">{businessDate}</div>
      </header>

      <div className="bg-white border border-slate-200 rounded-2xl shadow-sm px-6 py-4 text-center w-full max-w-sm">
        <div className="text-xs text-slate-500">إجمالي الأرقام المستقبلة</div>
        <div className="text-3xl font-extrabold text-blue-900 mt-1">{total}</div>
      </div>

      <main className="w-full max-w-sm flex flex-col gap-3">
        {stats.length === 0 ? (
          <div className="text-center text-slate-500 text-sm py-10">لسه مفيش أرقام اتنادى عليها النهارده</div>
        ) : (
          stats.map((counter) => {
            const isOpen = openCounter === counter.counterNumber;
            return (
              <div key={counter.counterNumber} className="bg-white border border-slate-200 rounded-2xl shadow-sm overflow-hidden">
                <button
                  onClick={() => setOpenCounter(isOpen ? null : counter.counterNumber)}
                  className="w-full flex items-center justify-between px-5 py-4"
                >
                  <span className="font-bold text-blue-900">مكتب رقم {counter.counterNumber}</span>
                  <span className="flex items-center gap-2">
                    <span className="text-2xl font-extrabold text-slate-800">{counter.tickets.length}</span>
                    <span className={`text-slate-400 transition-transform ${isOpen ? "rotate-180" : ""}`}>▾</span>
                  </span>
                </button>
                {isOpen && (
                  <div className="border-t border-slate-100 px-5 py-4 flex flex-wrap gap-2 bg-slate-50">
                    {counter.tickets.map((t) => (
                      <span
                        key={t.called_at}
                        className="bg-slate-200 rounded-lg px-3 py-1.5 text-sm font-bold text-slate-700"
                      >
                        {t.ticket_number}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            );
          })
        )}
      </main>

      {offline && (
        <div className="fixed bottom-0 left-0 right-0 bg-orange-100 text-orange-800 text-center py-2 text-sm">
          انقطع الاتصال — جاري إعادة المحاولة…
        </div>
      )}
    </div>
  );
}
