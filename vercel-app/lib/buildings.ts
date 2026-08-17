// The four physical buildings the system now serves, each with its own
// academic programs — the web app's copy of the canonical list.
//
// `value` is the stable internal identifier stored in `tickets.building`
// / `tickets.program`; `label` is Arabic display text only. Never key
// logic off the label — rewording it must not orphan tickets already
// issued under it.
//
// MIRROR OF app/core/certificates.py (Python, desktop app — see that
// file's docstring for why it's still named certificates.py despite
// holding building/program data now). The two MUST stay in sync: a
// test should parse this file the same way tests/test_certificates.py
// used to, and fail the suite if the values or labels drift apart —
// see the "known follow-up" note in the multi-building migration plan.

export type Program = {
  value: string;
  label: string;
};

export type Building = {
  value: "B" | "C" | "E" | "F";
  label: string;
  programs: Program[];
  // false means: this building has exactly one program, so nothing
  // ever needs to ask which one — see /admission's auto-selection for
  // building C, and app/ui/certificate_dialog.py's ask_for_program on
  // the desktop side for the same rule.
  askOnPrint: boolean;
};

export const BUILDINGS: Building[] = [
  {
    value: "B",
    label: "أسنان وصيدلة",
    programs: [
      { value: "dentistry", label: "أسنان" },
      { value: "pharmacy", label: "صيدلة" },
    ],
    askOnPrint: true,
  },
  {
    value: "C",
    label: "بشري",
    programs: [{ value: "humanMedicine", label: "بشري" }],
    askOnPrint: false,
  },
  {
    value: "E",
    label: "حسابات وتجارة",
    programs: [
      { value: "ai", label: "ذكاء اصطناعي" },
      { value: "medicalInformatics", label: "معلوماتية طبية" },
      { value: "aviationIS", label: "نظم معلومات طيران" },
      { value: "accounting", label: "محاسبة" },
      { value: "businessAdmin", label: "إدارة أعمال" },
    ],
    askOnPrint: true,
  },
  {
    value: "F",
    label: "هندسة وتمريض",
    programs: [
      { value: "mechatronics", label: "هندسة ميكاترونيكس" },
      { value: "constructionEng", label: "هندسة تشييد" },
      { value: "nursing", label: "تمريض" },
    ],
    askOnPrint: true,
  },
];

// Keyed by plain `string`, not the "B"|"C"|"E"|"F" literal union: every
// caller here is looking up a value that came from storage/the network
// (localStorage, a DB column, a URL) — genuinely just a string, not a
// value TypeScript can statically know is one of the four buildings.
// `Building.value` keeps the narrow literal type for authoring safety
// (BUILDINGS above is written by hand), it's only widened at lookup time.
const BUILDINGS_BY_VALUE = new Map<string, Building>(BUILDINGS.map((b) => [b.value, b]));
const BUILDING_LABELS = new Map<string, string>(BUILDINGS.map((b) => [b.value, b.label]));
const PROGRAM_LABELS = new Map<string, string>(
  BUILDINGS.flatMap((b) => b.programs.map((p) => [p.value, p.label] as const))
);
const PROGRAM_BUILDING = new Map<string, string>(
  BUILDINGS.flatMap((b) => b.programs.map((p) => [p.value, b.value] as const))
);

export function getBuilding(value?: string | null): Building | undefined {
  if (!value) return undefined;
  return BUILDINGS_BY_VALUE.get(value);
}

/** Display text for a stored building value. Unknown/missing values
 * render as a dash rather than throwing. */
export function buildingLabel(value?: string | null): string {
  if (!value) return "—";
  return BUILDING_LABELS.get(value) ?? value;
}

/** Display text for a stored program value. Unknown/missing values
 * render as a dash rather than throwing — tickets printed before this
 * feature existed (program is null) must still show up. */
export function programLabel(value?: string | null): string {
  if (!value) return "—";
  return PROGRAM_LABELS.get(value) ?? value;
}

/** Which building a program value belongs to, or undefined if it's not
 * a recognized program. Program values are unique across buildings by
 * construction, so this is unambiguous. */
export function buildingOfProgram(program?: string | null): string | undefined {
  if (!program) return undefined;
  return PROGRAM_BUILDING.get(program);
}

// --- per-browser building selection (localStorage) ------------------
//
// Every page that's scoped to one building (/, /call, /admission) uses
// the same key, so choosing a building on one of them is remembered
// for the others too if the same device is ever reused across pages —
// though in practice each device/browser only ever opens the one page
// it needs. /view is deliberately NOT gated by this: it's the one
// screen meant to show every building at once, for the main
// supervisor, with its own in-page building filter instead.

const BUILDING_STORAGE_KEY = "queue_building";

/** "" means no building has been chosen on this browser yet. Reading
 * localStorage must only ever happen after mount (see each page's
 * useEffect) — calling this during the initial render would break
 * server/client hydration. */
export function getSelectedBuilding(): string {
  if (typeof window === "undefined") return "";
  return localStorage.getItem(BUILDING_STORAGE_KEY) || "";
}

export function setSelectedBuilding(value: string) {
  if (typeof window === "undefined") return;
  localStorage.setItem(BUILDING_STORAGE_KEY, value);
}

export function clearSelectedBuilding() {
  if (typeof window === "undefined") return;
  localStorage.removeItem(BUILDING_STORAGE_KEY);
}
