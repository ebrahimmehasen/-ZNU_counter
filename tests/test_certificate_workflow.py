"""Local (SQLite) half of the building/program workflow.

Stages after the first reviewer live in Supabase, so what's testable
here is the part the desktop app owns: that the building/program
chosen at print time is attached to the ticket, survives the
failure/retry path, and doesn't disturb existing numbering or
counters.

(Kept as test_certificate_workflow.py: it exercises the same
ticket_service surface the old single-certificate tests did, just
against the building/program fields that replaced certificate_type.)
"""
from __future__ import annotations

import sqlite3

from app.core.database import Database
from app.core.models import TicketStatus
from app.core.session_service import SessionService
from app.core.ticket_service import TicketService


def make_services(tmp_path):
    db = Database(tmp_path / "queue.db")
    return db, SessionService(db), TicketService(db)


def test_building_and_program_are_stored_with_the_reserved_ticket(tmp_path):
    db, sessions, tickets = make_services(tmp_path)
    session = sessions.get_or_create_today()

    ticket = tickets.reserve_next_ticket(session.id, "E", "accounting")
    tickets.mark_printed(ticket.id, "PrinterA")

    assert ticket.building == "E"
    assert ticket.program == "accounting"
    stored = tickets.get_ticket(ticket.id)
    assert stored.building == "E"
    assert stored.program == "accounting"


def test_building_and_program_survive_print_failure_and_retry(tmp_path):
    """A failed print keeps the same number AND the same building/program
    — the employee must not be asked to pick again, and the reprinted
    ticket must not silently land in a different queue."""
    db, sessions, tickets = make_services(tmp_path)
    session = sessions.get_or_create_today()

    ticket = tickets.reserve_next_ticket(session.id, "F", "nursing")
    tickets.mark_print_failed(ticket.id, "paper jam")

    unresolved = tickets.get_unresolved_ticket(session.id)
    assert unresolved is not None
    assert unresolved.ticket_number == ticket.ticket_number
    assert unresolved.building == "F"
    assert unresolved.program == "nursing"

    tickets.mark_printed(unresolved.id, "PrinterA")
    stored = tickets.get_ticket(ticket.id)
    assert stored.building == "F"
    assert stored.program == "nursing"


def test_each_ticket_keeps_its_own_building_and_program(tmp_path):
    db, sessions, tickets = make_services(tmp_path)
    session = sessions.get_or_create_today()

    chosen = [("B", "dentistry"), ("C", "humanMedicine"), ("E", "ai"), ("F", "mechatronics")]
    created = []
    for building, program in chosen:
        t = tickets.reserve_next_ticket(session.id, building, program)
        tickets.mark_printed(t.id, "PrinterA")
        created.append(t)

    stored = [(tickets.get_ticket(t.id).building, tickets.get_ticket(t.id).program) for t in created]
    assert stored == chosen
    assert [t.ticket_number for t in created] == [1, 2, 3, 4]


def test_stats_expose_the_latest_ticket_program(tmp_path):
    db, sessions, tickets = make_services(tmp_path)
    session = sessions.get_or_create_today()

    first = tickets.reserve_next_ticket(session.id, "E", "accounting")
    tickets.mark_printed(first.id, "PrinterA")
    second = tickets.reserve_next_ticket(session.id, "B", "pharmacy")
    tickets.mark_printed(second.id, "PrinterA")

    stats = tickets.get_today_stats(session.id)
    assert stats["current_number"] == 2
    assert stats["current_program"] == "pharmacy"


def test_tickets_advanced_past_the_first_reviewer_still_count_for_today(tmp_path):
    """The cloud moves tickets to WAITING_FOR_ADMISSION / COMPLETED as
    they progress. Should those statuses ever reach the local mirror,
    the day's count must not shrink — the numbers were still issued."""
    db, sessions, tickets = make_services(tmp_path)
    session = sessions.get_or_create_today()

    for status in (
        TicketStatus.PRINTED,
        TicketStatus.CALLED,
        TicketStatus.WAITING_FOR_ADMISSION,
        TicketStatus.CALLED_BY_ADMISSION,
        TicketStatus.COMPLETED,
    ):
        t = tickets.reserve_next_ticket(session.id, "E", "accounting")
        db.execute("UPDATE tickets SET status=?, printed_at=? WHERE id=?", (status, "2026-01-01T00:00:00", t.id))

    stats = tickets.get_today_stats(session.id)
    assert stats["today_count"] == 5
    assert stats["current_number"] == 5


def test_building_and_program_are_optional_so_pre_existing_callers_still_work(tmp_path):
    """Reserving without a building/program must stay legal: it's what
    every pre-multi-building caller and test in this suite does."""
    db, sessions, tickets = make_services(tmp_path)
    session = sessions.get_or_create_today()

    ticket = tickets.reserve_next_ticket(session.id)
    tickets.mark_printed(ticket.id, "PrinterA")

    assert ticket.building is None
    assert ticket.program is None
    assert tickets.get_today_stats(session.id)["current_program"] is None


def test_database_created_before_multi_building_migrates_without_data_loss(tmp_path):
    """A queue.db from the single-certificate release must gain
    `building` and have `certificate_type` renamed to `program` on
    first open, keeping every ticket it already had."""
    db_path = tmp_path / "queue.db"

    # Build a "previous release" database: the single-certificate schema
    # (certificate_type, no building), holding one already-printed
    # ticket with a certificate value from that era.
    legacy = sqlite3.connect(str(db_path))
    legacy.executescript(
        """
        CREATE TABLE daily_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT, business_date TEXT NOT NULL UNIQUE,
            started_at TEXT NOT NULL, ended_at TEXT, created_at TEXT NOT NULL);
        CREATE TABLE tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT, uuid TEXT NOT NULL UNIQUE,
            session_id INTEGER NOT NULL REFERENCES daily_sessions(id),
            ticket_number INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'RESERVED',
            print_attempts INTEGER NOT NULL DEFAULT 0, printed_at TEXT,
            sync_status TEXT NOT NULL DEFAULT 'PENDING_SYNC', synced_at TEXT,
            device_id TEXT, printer_name TEXT, error_message TEXT,
            certificate_type TEXT,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            UNIQUE(session_id, ticket_number));
        INSERT INTO daily_sessions(business_date, started_at, created_at)
            VALUES ('2026-01-01', '2026-01-01T09:00:00', '2026-01-01T09:00:00');
        INSERT INTO tickets(uuid, session_id, ticket_number, status, printed_at,
                             certificate_type, created_at, updated_at)
            VALUES ('legacy-uuid', 1, 7, 'PRINTED', '2026-01-01T09:05:00',
                    'egyptian', '2026-01-01T09:05:00', '2026-01-01T09:05:00');
        """
    )
    legacy.commit()
    legacy.close()

    db = Database(db_path)
    tickets = TicketService(db)

    columns = {row["name"] for row in db.execute("PRAGMA table_info(tickets)")}
    assert "program" in columns
    assert "building" in columns
    assert "certificate_type" not in columns  # renamed away, not duplicated

    row = db.execute("SELECT * FROM tickets WHERE uuid='legacy-uuid'").fetchone()
    assert row["ticket_number"] == 7
    # The old certificate value survives the rename verbatim — it's now
    # a stale/unrecognized program value, which certificates.program_label
    # renders as-is rather than crashing on, but the data itself is kept.
    assert row["program"] == "egyptian"
    assert row["building"] is None  # single-building installs never had one

    # Numbering continues from the legacy data, and new tickets can
    # carry a building/program alongside the old ones.
    fresh = tickets.reserve_next_ticket(1, "C", "humanMedicine")
    assert fresh.ticket_number == 8
    assert fresh.building == "C"
    assert fresh.program == "humanMedicine"
