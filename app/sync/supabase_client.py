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
            # Which of the four buildings this ticket belongs to — every
            # queue lookup and RPC on the Supabase side is scoped by
            # this (see supabase/schema.sql), so it must always be set
            # for a ticket printed under the multi-building system.
            "building": ticket.building,
            # Drives which admission queue this ticket lands in after
            # the first reviewer finishes with it (see the
            # finish_first_review_and_call_next / admission_call_next
            # RPCs in supabase/schema.sql). Replaces the old
            # certificate_type name/concept.
            "program": ticket.program,
            "created_at": ticket.created_at,
            "updated_at": ticket.updated_at,
        }
        try:
            client.table("tickets").upsert(payload, on_conflict="uuid").execute()
        except Exception as e:
            raise SupabaseUnavailable(str(e)) from e

    def get_max_ticket_number(self, building: str, business_date: str) -> Optional[int]:
        """Highest ticket_number Supabase has for this building/business
        date, or None if it has none / is unreachable. Used at startup
        to catch the local sequence up if it was ever reset while the
        cloud mirror already had newer tickets (see
        `reconcile_sequence_floor` in ticket_service.py) — never
        required for printing to work, only for choosing a better
        starting number when possible. Scoped by building because each
        building runs its own independent sequence."""
        client = self._get_client()
        try:
            res = (
                client.table("tickets")
                .select("ticket_number")
                .eq("building", building)
                .eq("business_date", business_date)
                .order("ticket_number", desc=True)
                .limit(1)
                .execute()
            )
        except Exception as e:
            raise SupabaseUnavailable(str(e)) from e
        return res.data[0]["ticket_number"] if res.data else None

    def admin_reset_business_date(self, building: str, business_date: str, password: str) -> None:
        """Wipes every cloud ticket for a (building, business_date) pair
        via the password-gated `admin_reset_business_date` RPC (see
        supabase/schema.sql) — the password check happens server-side,
        not just in this client, since the anon key is also embedded
        in the public web app. Scoped to `building` so resetting one
        building's day never touches the other three."""
        client = self._get_client()
        try:
            client.rpc(
                "admin_reset_business_date",
                {
                    "p_building": building,
                    "p_business_date": business_date,
                    "p_password": password,
                },
            ).execute()
        except Exception as e:
            raise SupabaseUnavailable(str(e)) from e
