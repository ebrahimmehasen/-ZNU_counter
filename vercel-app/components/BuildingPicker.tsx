"use client";

// The "which building?" screen — shown by /, /call, and /admission
// whenever this browser hasn't chosen a building yet (see
// lib/buildings.ts's getSelectedBuilding/setSelectedBuilding). Each of
// those three pages is scoped to exactly one building once chosen; the
// choice is remembered in localStorage so a screen that's reloaded (or
// a browser that's reopened) goes straight back to its normal view,
// not through this picker again. /view is the one exception — it shows
// every building at once with its own in-page filter, so it never uses
// this component.

import { BUILDINGS } from "@/lib/buildings";

export default function BuildingPicker({
  onSelect,
  title = "اختر المبنى",
  hint = "هيتحفظ على الجهاز/المتصفح ده — تقدر تغيّره بعدين من الزرار في الشاشة.",
}: {
  onSelect: (value: string) => void;
  title?: string;
  hint?: string;
}) {
  return (
    <div className="min-h-screen bg-slate-100 text-slate-800 flex items-center justify-center p-6">
      <div className="bg-white border border-slate-200 rounded-2xl shadow-sm px-8 py-9 w-full max-w-md text-center">
        <h1 className="text-xl font-extrabold text-blue-900 mb-1">{title}</h1>
        <p className="text-xs text-slate-500 mb-6">{hint}</p>
        <div className="grid grid-cols-2 gap-3">
          {BUILDINGS.map((b) => (
            <button
              key={b.value}
              onClick={() => onSelect(b.value)}
              className="rounded-xl border-2 border-slate-200 hover:border-blue-500 hover:bg-blue-50 px-4 py-6 text-center transition-colors"
            >
              <div className="text-lg font-extrabold text-blue-900">مبنى {b.value}</div>
              <div className="text-sm text-slate-600 mt-1">{b.label}</div>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
