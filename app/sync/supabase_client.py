"""Thin wrapper around the Supabase client.

Kept separate from sync_manager so the upsert/idempotency contract is
in one obvious place: every push is an upsert keyed on the ticket's
stable `uuid`, so re-sending the same ticket (e.g. after a retry
following a network blip) can never create a duplicate cloud row.
"""
from __future__ import annotations

from typing import Optional

from app.config import SupabaseConfig
from app.core.models import Ticket
from app.logging_config import get_logger

logger = get_logger("supabase")


class SupabaseUnavailable(Exception):
    pass


class SupabaseSyncClient:
    def __init__(self, config: SupabaseConfig):
        self.config = config
        self._client = None

    def _get_client(self):
        if not self.config.configured:
            raise SupabaseUnavailable("Supabase URL/key not configured.")
        if self._client is None:
            from supabase import create_client
            self._client = create_client(self.config.url, self.config.key)
        return self._client

    def upsert_ticket(self, ticket: Ticket, business_date: str) -> None:
        client = self._get_client()
        payload = {
            "uuid": ticket.uuid,
            "ticket_number": ticket.ticket_number,
            "business_date": business_date,
            "status": ticket.status,
            "printed_at": ticket.printed_at,
            "device_id": ticket.device_id,
            "printer_name": ticket.printer_name,
            "created_at": ticket.created_at,
            "updated_at": ticket.updated_at,
        }
        try:
            client.table("tickets").upsert(payload, on_conflict="uuid").execute()
        except Exception as e:
            raise SupabaseUnavailable(str(e)) from e
