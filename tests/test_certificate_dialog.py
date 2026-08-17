"""The program picker sits in front of every printed ticket (for
buildings with more than one program), so a fault here stops the
counter working entirely for those buildings.

These run against a real Qt widget on the "offscreen" platform plugin
(no visible window, no display needed). That matters: an earlier
version of this dialog constructed fine and only crashed when actually
shown, so a test that merely instantiated it would have passed while
every print in production died.
"""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QPushButton  # noqa: E402

from app.core.certificates import BUILDINGS, get_building  # noqa: E402
from app.ui.building_dialog import BuildingDialog, ask_for_building  # noqa: E402
from app.ui.certificate_dialog import ProgramDialog, ask_for_program  # noqa: E402


@pytest.fixture(scope="module")
def qt_app():
    # One QApplication per process is a Qt hard requirement; reuse it if
    # another test module already created one.
    yield QApplication.instance() or QApplication([])


# ---- program dialog (per-building) --------------------------------------


def test_program_dialog_can_actually_be_shown(qt_app):
    """Regression: an earlier version of this dialog rearranged its grid
    after populating it, left a stale layout item, and segfaulted on
    show(). Building E has 5 programs (odd count, same shape as the
    original crash)."""
    dialog = ProgramDialog(building_value="E")
    dialog.show()
    qt_app.processEvents()
    assert dialog.isVisible()
    dialog.close()


def test_every_program_in_a_building_gets_a_button(qt_app):
    building = get_building("F")
    dialog = ProgramDialog(building_value="F")
    dialog.show()
    qt_app.processEvents()

    labels = {b.text() for b in dialog.findChildren(QPushButton) if b.objectName() == "certButton"}
    assert labels == {label for _, label in building.programs}
    dialog.close()


def test_clicking_a_program_button_selects_that_programs_value(qt_app):
    """Each button must carry its own value — a closure bug here would
    silently file every student under the last program in the list."""
    building = get_building("E")
    for value, label in building.programs:
        dialog = ProgramDialog(building_value="E")
        dialog.show()
        qt_app.processEvents()

        button = next(
            b
            for b in dialog.findChildren(QPushButton)
            if b.objectName() == "certButton" and b.text() == label
        )
        button.click()

        assert dialog.selected_value == value
        assert dialog.result() == ProgramDialog.Accepted


def test_cancelling_the_program_dialog_selects_nothing(qt_app):
    """Cancel must yield None so the caller reserves no ticket number —
    a mis-click on "print" must never burn a number."""
    dialog = ProgramDialog(building_value="B")
    dialog.show()
    qt_app.processEvents()
    dialog.reject()

    assert dialog.selected_value is None


def test_ask_for_program_skips_the_dialog_for_a_single_program_building(qt_app, monkeypatch):
    """Building C has exactly one program — ask_for_program must return
    it immediately without ever constructing a dialog (an accidental
    QDialog().exec() here would block the test forever waiting for a
    click that never comes)."""

    def fail_if_constructed(*a, **k):
        raise AssertionError("ProgramDialog should not be constructed for a single-program building")

    monkeypatch.setattr("app.ui.certificate_dialog.ProgramDialog", fail_if_constructed)

    result = ask_for_program(building_value="C")
    assert result == "humanMedicine"


def test_ask_for_program_returns_none_for_an_unknown_building(qt_app):
    assert ask_for_program(building_value="not-a-real-building") is None


# ---- building dialog (device setup / "تغيير المبنى") ---------------------


def test_building_dialog_can_actually_be_shown(qt_app):
    dialog = BuildingDialog()
    dialog.show()
    qt_app.processEvents()
    assert dialog.isVisible()
    dialog.close()


def test_every_building_gets_a_button(qt_app):
    dialog = BuildingDialog()
    dialog.show()
    qt_app.processEvents()

    labels = {b.text() for b in dialog.findChildren(QPushButton) if b.objectName() == "certButton"}
    assert labels == {f"مبنى {b.value}\n{b.label}" for b in BUILDINGS}
    dialog.close()


def test_clicking_a_building_button_selects_that_buildings_value(qt_app):
    for building in BUILDINGS:
        dialog = BuildingDialog()
        dialog.show()
        qt_app.processEvents()

        button = next(
            b
            for b in dialog.findChildren(QPushButton)
            if b.objectName() == "certButton" and b.text() == f"مبنى {building.value}\n{building.label}"
        )
        button.click()

        assert dialog.selected_value == building.value


def test_cancelling_the_building_dialog_selects_nothing_when_allowed(qt_app):
    dialog = BuildingDialog(allow_cancel=True)
    dialog.show()
    qt_app.processEvents()
    dialog.reject()
    assert dialog.selected_value is None


def test_mandatory_first_run_dialog_has_no_close_button(qt_app):
    """A device with no building configured can't print at all, so the
    first-run prompt must not be trivially dismissible."""
    from PySide6.QtCore import Qt

    dialog = BuildingDialog(allow_cancel=False)
    assert not (dialog.windowFlags() & Qt.WindowCloseButtonHint)
    dialog.close()
