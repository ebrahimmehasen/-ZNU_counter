"""Plain data containers for rows read out of SQLite."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


class TicketStatus:
    RESERVED = "RESERVED"          # number allocated, print not yet confirmed
    PRINTED = "PRINTED"            # printer confirmed success; implicitly "waiting"
                                    # until called_at is set (see queue_service.py —
                                    # there's no separate WAITING status: a PRINTED
                                    # ticket with called_at IS NULL *is* the waiting queue)
    PRINT_FAILED = "PRINT_FAILED"  # printer/template error, safe to retry
    CANCELLED = "CANCELLED"        # employee explicitly abandoned this number
    CALLED = "CALLED"              # picked from the waiting queue, assigned to a counter

    TERMINAL = (CANCELLED,)
    UNRESOLVED = (RESERVED, PRINT_FAILED)
    SYNCABLE = (PRINTED, CALLED)   # tickets confirmed printed — eligible to sync to Supabase


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
    counter_id: Optional[int] = None
    called_at: Optional[str] = None

    @classmethod
    def from_row(cls, row) -> "Ticket":
        return cls(**{k: row[k] for k in row.keys()})


@dataclass
class Counter:
    id: int
    counter_number: int
    name: Optional[str]
    active: bool
    created_at: str

    @classmethod
    def from_row(cls, row) -> "Counter":
        data = {k: row[k] for k in row.keys()}
        data["active"] = bool(data["active"])
        return cls(**data)
