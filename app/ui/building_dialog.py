"""The "which building?" step — shown once on first run (and again any
time the employee taps "تغيير المبنى") to pin this desktop install to
one of the four physical buildings the system now serves.

One install serves exactly one building for its whole lifetime in
practice (see PLAN_MULTI_BUILDING.md — "جهاز طباعة واحد لكل مبنى"), so
this dialog is deliberately rare: it's not part of the per-ticket
print flow the way the program picker (certificate_dialog.py) is. The
choice is persisted to config.yaml (see app/config.py's `building`
field) and survives restarts; changing it is an explicit, occasional
action an employee takes when a machine is being repurposed or
initially set up, not something asked before every ticket.
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

from app.core.certificates import BUILDINGS

COLUMNS = 2


class BuildingDialog(QDialog):
    """Modal building picker. `selected_value` holds the chosen stable
    id ("B"/"C"/"E"/"F") after exec() returns Accepted."""

    def __init__(self, parent=None, allow_cancel: bool = True):
        super().__init__(parent)
        self.selected_value: Optional[str] = None

        self.setWindowTitle("اختر المبنى")
        self.setLayoutDirection(Qt.RightToLeft)
        self.setModal(True)
        self.setMinimumWidth(560)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(14)

        heading = QLabel("اختر المبنى")
        heading.setObjectName("certDialogTitle")
        heading.setAlignment(Qt.AlignCenter)
        layout.addWidget(heading)

        hint = QLabel("الجهاز ده هيفضل مربوط بالمبنى اللي هتختاره — تقدر تغيّره بعدين من الزرار في الشاشة الرئيسية.")
        hint.setObjectName("certDialogHint")
        hint.setAlignment(Qt.AlignCenter)
        hint.setWordWrap(True)
        layout.addWidget(hint)

        grid = QGridLayout()
        grid.setSpacing(10)
        for index, building in enumerate(BUILDINGS):
            button = QPushButton(f"مبنى {building.value}\n{building.label}")
            button.setObjectName("certButton")
            button.setCursor(Qt.PointingHandCursor)
            button.setMinimumHeight(74)
            button.clicked.connect(lambda _checked=False, v=building.value: self._choose(v))
            row, column = index // COLUMNS, index % COLUMNS
            grid.addWidget(button, row, column)
        layout.addLayout(grid)

        if allow_cancel:
            cancel = QPushButton("إلغاء")
            cancel.setObjectName("certCancelButton")
            cancel.clicked.connect(self.reject)
            layout.addWidget(cancel)

        # No first-run building means this device can't print at all
        # (every ticket needs one), so the dialog shouldn't be
        # trivially dismissible with Escape on that first run — only
        # when it's opened later as a deliberate "change building"
        # action (allow_cancel=True, the default) does Escape make
        # sense.
        if not allow_cancel:
            self.setWindowFlag(Qt.WindowCloseButtonHint, False)

    def _choose(self, value: str) -> None:
        self.selected_value = value
        self.accept()


def ask_for_building(parent=None, allow_cancel: bool = True) -> Optional[str]:
    """Returns the chosen building id, or None if the employee
    cancelled/closed the dialog (only possible when allow_cancel=True —
    pass allow_cancel=False for the mandatory first-run prompt)."""
    dialog = BuildingDialog(parent, allow_cancel=allow_cancel)
    if not allow_cancel:
        # Belt-and-suspenders: even if something tries to close the
        # dialog via Esc/Alt+F4, keep re-showing it until a building is
        # actually chosen — a printer PC configured with no building at
        # all cannot correctly print or sync a single ticket.
        while dialog.exec() != QDialog.Accepted:
            dialog = BuildingDialog(parent, allow_cancel=allow_cancel)
        return dialog.selected_value
    if dialog.exec() == QDialog.Accepted:
        return dialog.selected_value
    return None
