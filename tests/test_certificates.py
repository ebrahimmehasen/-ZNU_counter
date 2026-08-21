"""Guards the one rule the two building/program lists depend on: the
Python list (desktop app, app/core/certificates.py) and the TypeScript
list (web app, vercel-app/lib/buildings.ts) describe the same
buildings and programs, in the same order, with the same stable
`value` ids.

They can't literally share a file across the two languages, so this
test parses the .ts source and compares. If someone adds a
building/program to one side only, tickets printed under it would be
unlabelable (or uncallable) on the other side — that's the failure
this catches.

(Kept as test_certificates.py — mirrors the source module's own name,
app/core/certificates.py, which is still called that pending the
building.py rename noted in its docstring.)
"""
from __future__ import annotations

import re
from pathlib import Path

from app.core.certificates import (
    BUILDINGS,
    building_label,
    get_building,
    is_valid_building,
    is_valid_building_program,
    is_valid_program,
    program_label,
)

TS_FILE = Path(__file__).resolve().parent.parent / "vercel-app" / "lib" / "buildings.ts"

PROGRAM_ENTRY_RE = re.compile(r'\{\s*value:\s*"(?P<value>[^"]+)"\s*,\s*label:\s*"(?P<label>[^"]+)"\s*\}')
BUILDING_BLOCK_RE = re.compile(
    r'\{\s*value:\s*"(?P<value>[^"]+)"\s*,\s*label:\s*"(?P<label>[^"]+)"\s*,'
    r'\s*programs:\s*\[(?P<programs>.*?)\]\s*,'
    r'\s*askOnPrint:\s*(?P<ask>true|false)\s*,?\s*\}',
    re.DOTALL,
)


def parse_ts_buildings() -> list[tuple[str, str, tuple[tuple[str, str], ...], bool]]:
    source = TS_FILE.read_text(encoding="utf-8")
    array_body = source.split("export const BUILDINGS: Building[] = [", 1)[1].rsplit("];", 1)[0]
    result = []
    for m in BUILDING_BLOCK_RE.finditer(array_body):
        programs = tuple(
            (p.group("value"), p.group("label")) for p in PROGRAM_ENTRY_RE.finditer(m.group("programs"))
        )
        result.append((m.group("value"), m.group("label"), programs, m.group("ask") == "true"))
    return result


def python_buildings() -> list[tuple[str, str, tuple[tuple[str, str], ...], bool]]:
    return [(b.value, b.label, b.programs, b.ask_on_print) for b in BUILDINGS]


def test_python_and_typescript_building_lists_match():
    ts = parse_ts_buildings()
    assert len(ts) == 4, "sanity check that the .ts parser actually matched something"
    assert ts == python_buildings()


def test_building_values_are_unique():
    values = [b.value for b in BUILDINGS]
    assert len(values) == len(set(values))


def test_program_values_are_unique_across_all_buildings():
    all_programs = [value for b in BUILDINGS for value, _ in b.programs]
    assert len(all_programs) == len(set(all_programs))


def test_the_four_expected_buildings_are_present():
    assert [b.value for b in BUILDINGS] == ["B", "C", "E", "F"]


def test_building_c_is_the_only_single_program_building():
    single_program = [b.value for b in BUILDINGS if not b.ask_on_print]
    assert single_program == ["C"]
    assert len(get_building("C").programs) == 1


def test_get_building_and_labels():
    assert get_building("E").label == "حسابات وتجارة"
    assert get_building("not-a-real-building") is None
    assert get_building(None) is None

    assert building_label("B") == "أسنان وصيدلة"
    assert program_label("dentistry") == "أسنان"

    # A ticket printed before this feature existed has neither — every
    # screen must still render it instead of blowing up.
    assert building_label(None) == "—"
    assert program_label(None) == "—"


def test_validity_checks():
    assert is_valid_building("F")
    assert not is_valid_building("Z")
    assert not is_valid_building(None)

    assert is_valid_program("nursing")
    assert not is_valid_program("not-a-real-program")

    assert is_valid_building_program("F", "nursing")
    assert not is_valid_building_program("F", "dentistry")  # dentistry belongs to B
    assert not is_valid_building_program("F", None)
    assert not is_valid_building_program(None, "nursing")
