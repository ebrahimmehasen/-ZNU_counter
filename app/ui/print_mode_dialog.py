"""The "how do numbers get to the student?" step — shown once on first
run (and again via "تغيير طريقة الطباعة") to pin this desktop install
to one of two workflows:

- "printer": every ticket is rendered to an image and sent to a real
  printer (the original workflow — see printing/printer_service.py).
- "preprinted": the employee already has a stack of pre-printed
  numbered tickets and just needs the on-screen counter to track which
  number is next; no printer is touched at all. See main_window.py's
  preprinted-mode handling in _print_next for the 5-second undo window
  that goes with this mode (a wrong tap can't be caught by a failed
  print the way it can in printer mode, so it needs its own safety net).

Persisted to config.yaml (see app/config.py's `print_mode` field), same
pattern as the building choice in building_dialog.py.
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

PRINTER = "printer"
PREPRINTED = "preprinted"


class PrintModeDialog(QDialog):
    """Modal print-mode picker. `selected_value` holds PRINTER or
    PREPRINTED after exec() returns Accepted."""

    def __init__(self, parent=None, allow_cancel: bool = True):
        super().__init__(parent)
        self.selected_value: Optional[str] = None

        self.setWindowTitle("طريقة الطباعة")
        self.setLayoutDirection(Qt.RightToLeft)
        self.setModal(True)
        self.setMinimumWidth(560)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(14)

        heading = QLabel("طريقة الطباعة")
        heading.setObjectName("certDialogTitle")
        heading.setAlignment(Qt.AlignCenter)
        layout.addWidget(heading)

        hint = QLabel("هل الجهاز ده متوصل بطابعة هتطبع الأرقام، ولا عندك أرقام مطبوعة جاهزة مسبقًا؟")
        hint.setObjectName("certDialogHint")
        hint.setAlignment(Qt.AlignCenter)
        hint.setWordWrap(True)
        layout.addWidget(hint)

        printer_button = QPushButton("عندي طابعة هتطبع الأرقام")
        printer_button.setObjectName("certButton")
        printer_button.setCursor(Qt.PointingHandCursor)
        printer_button.setMinimumHeight(74)
        printer_button.clicked.connect(lambda: self._choose(PRINTER))
        layout.addWidget(printer_button)

        preprinted_button = QPushButton("الأرقام مطبوعة جاهزة معايا")
        preprinted_button.setObjectName("certButton")
        preprinted_button.setCursor(Qt.PointingHandCursor)
        preprinted_button.setMinimumHeight(74)
        preprinted_button.clicked.connect(lambda: self._choose(PREPRINTED))
        layout.addWidget(preprinted_button)

        if allow_cancel:
            cancel = QPushButton("إلغاء")
            cancel.setObjectName("certCancelButton")
            cancel.clicked.connect(self.reject)
            layout.addWidget(cancel)

        # Same reasoning as BuildingDialog: no print mode means the
        # main window doesn't know how to handle "print next", so the
        # first-run prompt shouldn't be dismissible with Escape.
        if not allow_cancel:
            self.setWindowFlag(Qt.WindowCloseButtonHint, False)

    def _choose(self, value: str) -> None:
        self.selected_value = value
        self.accept()


def ask_for_print_mode(parent=None, allow_cancel: bool = True) -> Optional[str]:
    """Returns PRINTER or PREPRINTED, or None if the employee
    cancelled/closed the dialog (only possible when allow_cancel=True —
    pass allow_cancel=False for the mandatory first-run prompt)."""
    dialog = PrintModeDialog(parent, allow_cancel=allow_cancel)
    if not allow_cancel:
        while dialog.exec() != QDialog.Accepted:
            dialog = PrintModeDialog(parent, allow_cancel=allow_cancel)
        return dialog.selected_value
    if dialog.exec() == QDialog.Accepted:
        return dialog.selected_value
    return None
