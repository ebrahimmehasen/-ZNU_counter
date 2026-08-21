"""The "which program?" step that precedes most printed numbers.

NOTE ON THE FILENAME: kept as `certificate_dialog.py` for now even
though it no longer asks about certificates — see the note at the top
of app/core/certificates.py for why the rename to program_dialog.py is
a manual follow-up rather than something this change could safely do.

Shown by both the real print button and the test-number button, so a
test ticket exercises exactly the same path a real one does (including
landing in an admission queue afterwards) rather than being a
different code path that can drift out of sync with production.

Multi-building behaviour (see PLAN_MULTI_BUILDING.md): each building
has its own fixed list of programs, and one of them (C — بشري) has
only a single possible program. Asking a one-button question would
just add a needless tap, so `ask_for_program` returns that program
immediately without ever opening a dialog when the configured building
has ask_on_print=False. Every other building still gets the same
picker UI as before, just scoped to its own program list.

Design constraints for the dialog itself, in priority order — this
screen sits between the employee and every single ticket they issue:
  * one tap, no scrolling: a building's whole program list fits on
    screen at once in a grid, so issuing a ticket stays a two-tap
    operation (three, on B, at most).
  * big targets: touch/mouse under time pressure with a queue waiting.
  * cancellable: closing without choosing must reserve no number at
    all, so an accidental click can't burn a ticket number. The caller
    only reserves *after* this returns a value (see main_window).
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QGridLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from app.core.certificates import get_building

COLUMNS = 2


class ProgramDialog(QDialog):
    """Modal program picker, scoped to one building. `selected_value`
    holds the chosen stable id (e.g. "dentistry") after exec() returns
    Accepted."""

    def __init__(self, parent=None, building_value: str = "", title: str = "اختر البرنامج"):
        super().__init__(parent)
        self.selected_value: Optional[str] = None
        building = get_building(building_value)
        programs = building.programs if building else ()

        self.setWindowTitle(title)
        self.setLayoutDirection(Qt.RightToLeft)
        self.setModal(True)
        self.setMinimumWidth(620)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(14)

        heading = QLabel(title)
        heading.setObjectName("certDialogTitle")
        heading.setAlignment(Qt.AlignCenter)
        layout.addWidget(heading)

        hint = QLabel("اضغط على البرنامج المطلوب — الرقم هيتطبع بعدها على طول.")
        hint.setObjectName("certDialogHint")
        hint.setAlignment(Qt.AlignCenter)
        hint.setWordWrap(True)
        layout.addWidget(hint)

        grid = QGridLayout()
        grid.setSpacing(10)
        # A trailing odd item would sit alone in the left column; span
        # it across the full width so the grid stays even. Decided
        # while adding rather than by rearranging the layout afterwards
        # — moving a widget between grid cells after the fact leaves a
        # stale layout item behind and crashes on show().
        last_index = len(programs) - 1
        last_is_orphan = len(programs) % COLUMNS != 0

        for index, (value, label) in enumerate(programs):
            button = QPushButton(label)
            button.setObjectName("certButton")
            button.setCursor(Qt.PointingHandCursor)
            button.setMinimumHeight(58)
            # Bind the value per-iteration; a bare closure over `value`
            # would hand every button the last program in the list.
            button.clicked.connect(lambda _checked=False, v=value: self._choose(v))

            row, column = index // COLUMNS, index % COLUMNS
            if index == last_index and last_is_orphan:
                grid.addWidget(button, row, 0, 1, COLUMNS)
            else:
                grid.addWidget(button, row, column)

        layout.addLayout(grid)

        cancel = QPushButton("إلغاء")
        cancel.setObjectName("certCancelButton")
        cancel.clicked.connect(self.reject)
        layout.addWidget(cancel)

    def _choose(self, value: str) -> None:
        self.selected_value = value
        self.accept()


def ask_for_program(parent=None, building_value: str = "", title: Optional[str] = None) -> Optional[str]:
    """Returns the chosen program id for `building_value`, or None if
    the employee cancelled/closed the dialog. None must be treated as
    "do nothing at all" by the caller — never as a default program.

    For a building whose only program is implicit (currently just C —
    بشري), no dialog is shown at all: the single program is returned
    immediately. This is a deliberate silent success, not a
    cancellation, so the caller must not mistake it for one — check
    `get_building(building_value).ask_on_print` yourself if you need to
    tell the two apart for some other reason."""
    building = get_building(building_value)
    if building is None:
        return None
    if not building.ask_on_print:
        # Exactly one program by construction (see
        # core/certificates.py's BUILDINGS) — no picker needed.
        return building.programs[0][0]

    dialog = ProgramDialog(parent, building_value, title or f"اختر البرنامج ({building.label})")
    if dialog.exec() == QDialog.Accepted:
        return dialog.selected_value
    return None
