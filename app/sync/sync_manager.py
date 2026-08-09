"""Background synchronization loop.

Runs on its own QThread so a slow/unreachable network never blocks the
print button or the rest of the UI (Supabase must never be a printing
dependency). Every `interval_seconds` it looks for PRINTED tickets that
are still PENDING_SYNC/SYNC_FAILED and upserts them one at a time,
marking each SYNCED as it succeeds. A failed batch simply leaves the
remaining tickets PENDING_SYNC/SYNC_FAILED for the next tick — nothing
about a failed sync ever touches the printing/numbering tables.
"""
from __future__ import annotations

import time

from PySide6.QtCore import QThread, Signal

from app.core.session_service import SessionService
from app.core.ticket_service import TicketService
from app.logging_config import get_logger
from app.sync.supabase_client import SupabaseSyncClient, SupabaseUnavailable

logger = get_logger("sync")


class SyncManager(QThread):
    status_changed = Signal(dict)  # {"online": bool, "pending": int, "last_sync": str|None, "last_error": str|None}

    def __init__(
        self,
        ticket_service: TicketService,
        session_service: SessionService,
        supabase_client: SupabaseSyncClient,
        interval_seconds: int = 15,
        batch_size: int = 25,
        parent=None,
    ):
        super().__init__(parent)
        self.ticket_service = ticket_service
        self.session_service = session_service
        self.supabase_client = supabase_client
        self.interval_seconds = interval_seconds
        self.batch_size = batch_size
        self._stop_requested = False
        self._last_sync = None
        self._last_error = None

    def stop(self) -> None:
        self._stop_requested = True

    def run(self) -> None:
        logger.info("Sync manager started (interval=%ss)", self.interval_seconds)
        while not self._stop_requested:
            self._sync_once()
            for _ in range(self.interval_seconds * 10):
                if self._stop_requested:
                    break
                time.sleep(0.1)
        logger.info("Sync manager stopped")

    def sync_now(self) -> None:
        """Trigger an out-of-band sync attempt (e.g. right after printing)
        without waiting for the next timer tick."""
        self._sync_once()

    def _sync_once(self) -> None:
        pending = self.ticket_service.get_pending_sync_tickets(self.batch_size)
        if not pending:
            self._emit_status(online=True)
            return

        today = self.session_service.get_or_create_today()
        synced_count = 0
        error = None
        for ticket in pending:
            try:
                self.supabase_client.upsert_ticket(ticket, today.business_date)
                self.ticket_service.mark_synced(ticket.id)
                synced_count += 1
                logger.info("Ticket #%s synchronized", ticket.ticket_number)
            except SupabaseUnavailable as e:
                error = str(e)
                self.ticket_service.mark_sync_failed(ticket.id)
                logger.warning("Sync failed for ticket #%s: %s", ticket.ticket_number, e)
                break  # network is likely down; stop hammering it this tick

        if synced_count:
            self._last_sync = time.strftime("%Y-%m-%d %H:%M:%S")
        self._last_error = error
        self._emit_status(online=error is None)

    def _emit_status(self, online: bool) -> None:
        remaining = self.ticket_service.get_pending_sync_tickets(9999)
        self.status_changed.emit(
            {
                "online": online,
                "pending": len(remaining),
                "last_sync": self._last_sync,
                "last_error": self._last_error,
            }
        )
