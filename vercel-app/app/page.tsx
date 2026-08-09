"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { supabase, todayBusinessDate } from "@/lib/supabaseClient";
import {
  announceTest,
  announceTicket,
  getArabicVoices,
  getSelectedVoice,
  onVoicesChanged,
  setSelectedVoiceURI,
  speechAvailable,
  unlockSpeech,
} from "@/lib/speech";

type Current = { ticket_number: number; counter_number: number } | null;

type DisplayData = {
  current: Current;
  nextNumbers: number[];
  stats: { totalToday: number; waiting: number; called: number };
};

const EMPTY: DisplayData = {
  current: null,
  nextNumbers: [],
  stats: { totalToday: 0, waiting: 0, called: 0 },
};

async function fetchDisplayData(businessDate: string): Promise<DisplayData> {
  const [{ data: currentRows }, { data: waitingRows }, { count: totalToday }, { count: waiting }, { count: called }] =
    await Promise.all([
      supabase
        .from("tickets")
        .select("ticket_number, counter_number")
        .eq("business_date", businessDate)
        .eq("status", "CALLED")
        .order("called_at", { ascending: false })
        .limit(1),
      supabase
        .from("tickets")
        .select("ticket_number")
        .eq("business_date", businessDate)
        .eq("status", "PRINTED")
        .is("called_at", null)
        .order("ticket_number", { ascending: true })
        .limit(5),
      supabase
        .from("tickets")
        .select("uuid", { count: "exact", head: true })
        .eq("business_date", businessDate)
        .in("status", ["PRINTED", "CALLED"]),
      supabase
        .from("tickets")
        .select("uuid", { count: "exact", head: true })
        .eq("business_date", businessDate)
        .eq("status", "PRINTED")
        .is("called_at", null),
      supabase
        .from("tickets")
        .select("uuid", { count: "exact", head: true })
        .eq("business_date", businessDate)
        .eq("status", "CALLED"),
    ]);

  return {
    current: (currentRows && currentRows[0]) || null,
    nextNumbers: (waitingRows || []).map((r) => r.ticket_number),
    stats: {
      totalToday: totalToday ?? 0,
      waiting: waiting ?? 0,
      called: called ?? 0,
    },
  };
}

export default function DisplayPage() {
  const [data, setData] = useState<DisplayData>(EMPTY);
  const [offline, setOffline] = useState(false);
  const [flash, setFlash] = useState(false);
  const [soundAvailable, setSoundAvailable] = useState(false);
  // Both `todayBusinessDate()` (depends on the machine's local clock —
  // the build server and a visitor's browser can disagree, especially
  // near midnight) and `speechAvailable()` (reads `window`, absent
  // during the static server-rendered shell) must NOT be computed
  // during the initial render, or that render won't match what the
  // server already sent down — a React hydration error. Both start
  // blank/false and get filled in from an effect, which only runs
  // after hydration completes.
  const [businessDate, setBusinessDate] = useState("");
  const [voices, setVoices] = useState<SpeechSynthesisVoice[]>([]);
  const [selectedVoiceURI, setSelectedVoiceURIState] = useState("");
  const lastCalled = useRef<number | null>(null);

  useEffect(() => {
    setBusinessDate(todayBusinessDate());
    const available = speechAvailable();
    setSoundAvailable(available);
    if (!available) return;

    const syncVoices = () => {
      setVoices(getArabicVoices());
      setSelectedVoiceURIState(getSelectedVoice()?.voiceURI || "");
    };
    syncVoices();
    return onVoicesChanged(syncVoices);
  }, []);

  function chooseVoice(voiceURI: string) {
    setSelectedVoiceURI(voiceURI);
    setSelectedVoiceURIState(voiceURI);
    unlockSpeech();
    announceTest(); // preview immediately so it's obvious what changed
  }

  const refresh = useCallback(async () => {
    if (!businessDate) return;
    try {
      const next = await fetchDisplayData(businessDate);
      const changed = lastCalled.current !== null && next.current?.ticket_number !== lastCalled.current;
      if (changed) {
        setFlash(true);
        setTimeout(() => setFlash(false), 1200);
        if (next.current) {
          announceTicket(next.current.ticket_number, next.current.counter_number);
        }
      }
      lastCalled.current = next.current?.ticket_number ?? null;
      setData(next);
      setOffline(false);
    } catch {
      setOffline(true);
    }
  }, [businessDate]);

  useEffect(() => {
    if (!businessDate) return;
    refresh();

    // Realtime push (instant) — any change to today's tickets triggers
    // a fresh fetch of the computed display payload. A 5s poll is kept
    // as a safety net in case a realtime event is ever missed.
    const channel = supabase
      .channel("tickets-display")
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

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col items-center px-6 py-10 gap-8">
      <header className="flex flex-col items-center text-center gap-3">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src="/university-logo.png" alt="جامعة الزقازيق الأهلية" className="w-24 h-24 sm:w-32 sm:h-32" />
        <div>
          <h1 className="text-3xl sm:text-5xl font-extrabold tracking-wide text-blue-300">
            أهلاً بكم في جامعة الزقازيق الأهلية
          </h1>
          <div className="text-slate-500 mt-1 text-sm">{businessDate}</div>
        </div>
      </header>

      <main className="w-full max-w-5xl flex flex-col items-center gap-8">
        <div className="w-full grid grid-cols-1 md:grid-cols-2 gap-6">
          <section className="bg-slate-900 border-2 border-blue-900 rounded-3xl px-8 py-10 text-center flex flex-col items-center justify-center">
            <div className="text-blue-300 tracking-widest text-sm sm:text-lg font-bold">يتم خدمته الآن</div>
            <div
              className={`font-extrabold leading-none my-3 text-[90px] sm:text-[150px] transition-colors duration-700 ${
                flash ? "text-green-400" : "text-white"
              }`}
            >
              {data.current ? data.current.ticket_number : "—"}
            </div>
            {data.current && (
              <div className="text-2xl sm:text-3xl font-bold text-blue-300">
                مكتب رقم {data.current.counter_number}
              </div>
            )}
          </section>

          <section className="bg-slate-900 border-2 border-slate-800 rounded-3xl px-8 py-10 text-center flex flex-col items-center justify-center">
            <div className="text-slate-400 tracking-widest text-sm sm:text-lg font-bold mb-4">الانتظار</div>
            <div className="flex flex-wrap justify-center gap-3">
              {data.nextNumbers.length === 0 ? (
                <span className="text-slate-500">لا يوجد أحد في الانتظار</span>
              ) : (
                data.nextNumbers.map((n) => (
                  <span key={n} className="bg-slate-800 rounded-xl px-5 py-3 text-2xl sm:text-3xl font-bold">
                    {n}
                  </span>
                ))
              )}
            </div>
          </section>
        </div>

        <section className="flex flex-wrap justify-center gap-5 w-full">
          <Stat label="إجمالي اليوم" value={data.stats.totalToday} />
          <Stat label="في الانتظار" value={data.stats.waiting} />
          <Stat label="تم النداء" value={data.stats.called} />
        </section>
      </main>

      {offline && (
        <div className="fixed bottom-0 left-0 right-0 bg-orange-900 text-orange-200 text-center py-2">
          انقطع الاتصال — جاري إعادة المحاولة…
        </div>
      )}

      {soundAvailable && (
        <div className="fixed top-4 right-4 bg-slate-900 border border-slate-700 rounded-2xl shadow-lg p-3 flex flex-col gap-2 max-w-[240px]">
          {voices.length > 0 && (
            <select
              value={selectedVoiceURI}
              onChange={(e) => chooseVoice(e.target.value)}
              className="bg-slate-800 text-slate-100 text-xs rounded-lg px-2 py-2 border border-slate-700"
            >
              {voices.map((v) => (
                <option key={v.voiceURI} value={v.voiceURI}>
                  {v.name} ({v.lang}){v.localService ? "" : " ★"}
                </option>
              ))}
            </select>
          )}
          <button
            onClick={() => {
              unlockSpeech();
              announceTest();
            }}
            className="bg-blue-600 hover:bg-blue-700 text-white text-sm font-bold rounded-lg px-4 py-2"
          >
            🔊 تجربة الصوت
          </button>
        </div>
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="bg-slate-900 border border-slate-800 rounded-2xl px-8 py-5 text-center min-w-[140px]">
      <div className="text-slate-400 text-xs sm:text-sm tracking-widest">{label}</div>
      <div className="text-3xl sm:text-5xl font-extrabold mt-1">{value}</div>
    </div>
  );
}
