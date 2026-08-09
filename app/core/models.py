"""Plain data containers for rows read out of SQLite."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


class TicketStatus:
    RESERVED = "RESERVED"          # number allocated, print not yet confirmed
    PRINTED = "PRINTED"            # printer confirmed success
    PRINT_FAILED = "PRINT_FAILED"  # printer/template error, safe to retry
    CANCELLED = "CANCELLED"        # employee explicitly abandoned this number

    TERMINAL = (PRINTED, CANCELLED)
    UNRESOLVED = (RESERVED, PRINT_FAILED)


class SyncStatus:
    PENDING_SYNC = "PENDING_SYNC"
    SYNCED = "SYNCED"
    SYNC_FAILED = "SYNC_FAILED"


@dataclass
class DailySession:
    id: int
    business_date: str
    started_at: str
    ended_at: Optional[str]
    created_at: str


@dataclass
class Ticket:
    id: int
    uuid: str
    session_id: int
    ticket_number: int
    status: str
    print_attempts: int
    printed_at: Optional[str]
    sync_status: str
    synced_at: Optional[str]
    device_id: Optional[str]
    printer_name: Optional[str]
    error_message: Optional[str]
    created_at: str
    updated_at: str

    @classmethod
    def from_row(cls, row) -> "Ticket":
        return cls(**{k: row[k] for k in row.keys()})
