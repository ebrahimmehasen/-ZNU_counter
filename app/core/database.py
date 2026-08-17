"""SQLite connection management and schema.

SQLite is the operational source of truth for ticket numbering (Rule 3/4
in the project brief). It must keep working with no network, survive
application/Windows restarts, and never lose or duplicate a ticket
number even if the process dies mid-print.

Design choices that serve those goals:
  * WAL journal mode: readers (UI refresh) don't block the writer, and
    a crash mid-write leaves the DB recoverable rather than corrupted.
  * Every write that touches ticket numbering uses `BEGIN IMMEDIATE`
    to take the write lock up front, so two near-simultaneous prints
    (e.g. a stuck UI double-click) cannot compute the same "next number".
  * A UNIQUE(session_id, ticket_number) constraint is a hard backstop
    against duplicate numbers even if application logic has a bug.
  * Every ticket gets a stable `uuid` at creation time, independent of
    the local auto-increment id. That uuid is the idempotency key used
    when upserting into Supabase, so retried/duplicate sync attempts
    never create duplicate cloud rows.

Multi-building note: this file's own numbering scope (session_id, i.e.
one business day) never needed a `building` column to stay correct,
because each desktop install serves exactly one physical building (see
app/config.py's `building` setting) — its whole local database only
ever holds that one building's tickets, so MAX(ticket_number) WHERE
session_id=... is inherently building-scoped already. `building` is
still stored per-ticket (alongside `program`, which replaces the old
`certificate_type`) purely so every row carries everything it needs to
sync to Supabase correctly, without the sync code having to reach back
into config for it.
"""
from __future__ import annotations

import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS app_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS daily_sessions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    business_date TEXT NOT NULL UNIQUE,
    started_at    TEXT NOT NULL,
    ended_at      TEXT,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tickets (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    uuid           TEXT NOT NULL UNIQUE,
    session_id     INTEGER NOT NULL REFERENCES daily_sessions(id),
    ticket_number  INTEGER NOT NULL,
    status         TEXT NOT NULL DEFAULT 'RESERVED',
    print_attempts INTEGER NOT NULL DEFAULT 0,
    printed_at     TEXT,
    sync_status    TEXT NOT NULL DEFAULT 'PENDING_SYNC',
    synced_at      TEXT,
    device_id      TEXT,
    printer_name   TEXT,
    error_message  TEXT,
    certificate_type TEXT,
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL,
    UNIQUE(session_id, ticket_number)
);

CREATE INDEX IF NOT EXISTS idx_tickets_sync_status ON tickets(sync_status);
CREATE INDEX IF NOT EXISTS idx_tickets_session ON tickets(session_id);

CREATE TABLE IF NOT EXISTS counters (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    counter_number INTEGER NOT NULL UNIQUE,
    name           TEXT,
    active         INTEGER NOT NULL DEFAULT 1,
    created_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ticket_events (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id  INTEGER NOT NULL REFERENCES tickets(id),
    event_type TEXT NOT NULL,
    timestamp  TEXT NOT NULL,
    metadata   TEXT
);

CREATE INDEX IF NOT EXISTS idx_ticket_events_ticket ON ticket_events(ticket_id);
"""


class Database:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(
            str(self.db_path),
            timeout=30,          # wait for locks instead of failing immediately
            isolation_level=None,  # manual transaction control (BEGIN/COMMIT below)
            check_same_thread=False,
        )
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=FULL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(SCHEMA)
        self._migrate()
        self._ensure_device_id()

    def _migrate(self) -> None:
        """Additive, idempotent column migrations for databases created by
        an earlier version of the schema (e.g. Phase 1 installs upgrading
        to Phase 2's queue-calling columns, or single-building installs
        upgrading to the multi-building schema). Only ADD/RENAME COLUMN —
        never drops anything, so old data is never at risk."""
        existing = {row["name"] for row in self._conn.execute("PRAGMA table_info(tickets)")}
        if "counter_id" not in existing:
            self._conn.execute("ALTER TABLE tickets ADD COLUMN counter_id INTEGER REFERENCES counters(id)")
        if "called_at" not in existing:
            self._conn.execute("ALTER TABLE tickets ADD COLUMN called_at TEXT")

        # certificate_type -> program: this desktop install now stamps
        # every ticket with the academic program chosen at print time
        # (see ui/certificate_dialog.ask_for_program), not a certificate.
        # Rename rather than add-a-new-column so any tickets already
        # printed under the old column keep their value instead of
        # being orphaned. SQLite has supported RENAME COLUMN since
        # 3.25 (2018), well within PyInstaller's bundled sqlite3.
        if "certificate_type" in existing and "program" not in existing:
            self._conn.execute("ALTER TABLE tickets RENAME COLUMN certificate_type TO program")
            existing.discard("certificate_type")
            existing.add("program")
        if "program" not in existing:
            self._conn.execute("ALTER TABLE tickets ADD COLUMN program TEXT")

        # Which of the four buildings (B/C/E/F) this ticket was printed
        # under — see app/config.py's `building` setting and
        # app/core/certificates.py's BUILDINGS list. Nullable so any
        # tickets printed before this feature existed keep working.
        if "building" not in existing:
            self._conn.execute("ALTER TABLE tickets ADD COLUMN building TEXT")

    def _ensure_device_id(self) -> None:
        row = self._conn.execute(
            "SELECT value FROM app_meta WHERE key='device_id'"
        ).fetchone()
        if row is None:
            self._conn.execute(
                "INSERT INTO app_meta(key, value) VALUES ('device_id', ?)",
                (str(uuid.uuid4()),),
            )

    @property
    def device_id(self) -> str:
        row = self._conn.execute(
            "SELECT value FROM app_meta WHERE key='device_id'"
        ).fetchone()
        return row["value"]

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Take the write lock immediately, so concurrent callers serialize
        instead of racing to compute the same next-ticket-number."""
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            yield self._conn
            self._conn.execute("COMMIT")
        except Exception:
            self._conn.execute("ROLLBACK")
            raise

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        return self._conn.execute(sql, params)

    def close(self) -> None:
        self._conn.close()
