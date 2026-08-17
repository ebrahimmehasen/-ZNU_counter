"""Buildings and academic programs — the multi-building replacement for
the old single "certificate type" list.

NOTE ON THE FILENAME: this module is still called `certificates.py` for
now. It should really be `app/core/buildings.py` — the concept it holds
is buildings/programs, not certificates — but renaming it is a manual
step left for whoever next touches the repo directly (git mv +
update the ~6 imports below), since it wasn't safe to do as part of
this automated change. Every name exported from here uses the new
building/program vocabulary; only the filename is stale.

`BUILDINGS` is the four physical buildings the system now serves, each
with its own ticket sequence, its own first-review queue, and its own
fixed list of academic programs. `value` is the stable internal
identifier stored in `tickets.building` / `tickets.program` locally and
in Supabase (see supabase/schema.sql) — everything downstream keys off
it, never off the Arabic label, so relabeling a building/program can
never silently orphan tickets already issued under it.

This list is mirrored in TypeScript for the web app at
vercel-app/lib/buildings.ts. The two files MUST stay in sync (same
convention tests/test_certificates.py used to enforce for the old
certificate list — see tests/test_programs.py for the new version).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Building:
    value: str          # stable id: "B" / "C" / "E" / "F"
    label: str           # Arabic display name, e.g. "أسنان وصيدلة"
    programs: tuple[tuple[str, str], ...]  # (value, label) pairs, in display order
    ask_on_print: bool   # False means: never show a picker, silently stamp the one program


BUILDINGS: tuple[Building, ...] = (
    Building(
        value="B",
        label="أسنان وصيدلة",
        programs=(
            ("dentistry", "أسنان"),
            ("pharmacy", "صيدلة"),
        ),
        ask_on_print=True,
    ),
    Building(
        value="C",
        label="بشري",
        programs=(
            ("humanMedicine", "بشري"),
        ),
        # Only one possible program — the desktop app never asks, it
        # just stamps it. See ui/certificate_dialog.ask_for_program().
        ask_on_print=False,
    ),
    Building(
        value="E",
        label="حسابات وتجارة",
        programs=(
            ("ai", "ذكاء اصطناعي"),
            ("medicalInformatics", "معلوماتية طبية"),
            ("aviationIS", "نظم معلومات طيران"),
            ("accounting", "محاسبة"),
            ("businessAdmin", "إدارة أعمال"),
        ),
        ask_on_print=True,
    ),
    Building(
        value="F",
        label="هندسة وتمريض",
        programs=(
            ("mechatronics", "هندسة ميكاترونيكس"),
            ("constructionEng", "هندسة تشييد"),
            ("nursing", "تمريض"),
        ),
        ask_on_print=True,
    ),
)

BUILDING_VALUES: frozenset[str] = frozenset(b.value for b in BUILDINGS)

_BUILDINGS_BY_VALUE: dict[str, Building] = {b.value: b for b in BUILDINGS}
_BUILDING_LABELS: dict[str, str] = {b.value: b.label for b in BUILDINGS}
_PROGRAM_LABELS: dict[str, str] = {
    value: label for b in BUILDINGS for value, label in b.programs
}
_PROGRAM_VALUES: frozenset[str] = frozenset(_PROGRAM_LABELS.keys())
# Which building each program value belongs to — used to validate that
# a (building, program) pair printed on the desktop app is actually a
# legal combination before it ever reaches Supabase's own constraint.
_PROGRAM_BUILDING: dict[str, str] = {
    value: b.value for b in BUILDINGS for value, _ in b.programs
}


def get_building(value: str | None) -> Building | None:
    if not value:
        return None
    return _BUILDINGS_BY_VALUE.get(value)


def building_label(value: str | None) -> str:
    if not value:
        return "—"
    return _BUILDING_LABELS.get(value, value)


def program_label(value: str | None) -> str:
    """Display text for a stored program value. Unknown/missing values
    render as a dash rather than raising — a ticket printed before this
    feature existed (program IS NULL) must still be listable and
    callable, not crash a screen."""
    if not value:
        return "—"
    return _PROGRAM_LABELS.get(value, value)


def is_valid_building(value: str | None) -> bool:
    return value in BUILDING_VALUES


def is_valid_program(value: str | None) -> bool:
    return value in _PROGRAM_VALUES


def is_valid_building_program(building: str | None, program: str | None) -> bool:
    """True iff `program` is one of `building`'s own programs. A
    building with ask_on_print=False (currently just C) still has
    exactly one legal program, so this correctly rejects mismatches
    there too, not just for the multi-program buildings."""
    if not building or not program:
        return False
    return _PROGRAM_BUILDING.get(program) == building


# --- backward-compatible aliases -----------------------------------------
# The old single-building version of this module exported these three
# names for a flat list of 13 certificate types. Nothing in this
# codebase should still import them (every caller was updated alongside
# this change), but they're kept as a safety net for any external
# script/notebook that might still reference the old API — each now
# raises loudly instead of silently returning wrong data, since a flat
# "certificate list" no longer makes sense once programs are scoped per
# building.
def CERTIFICATE_TYPES(*_a, **_k):  # noqa: N802 - matches the old constant's name
    raise RuntimeError(
        "CERTIFICATE_TYPES was removed in the multi-building migration. "
        "Use BUILDINGS / get_building(building).programs instead."
    )
