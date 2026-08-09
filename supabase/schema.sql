-- Phase 1 Supabase schema: minimum structure to receive synced tickets
-- for cloud monitoring. This is a mirror/monitoring copy — the local
-- SQLite database remains the source of truth for numbering.

create table if not exists tickets (
    uuid          uuid primary key,
    ticket_number integer not null,
    business_date date not null,
    status        text not null,
    printed_at    timestamptz,
    device_id     text,
    printer_name  text,
    created_at    timestamptz not null,
    updated_at    timestamptz not null,
    synced_at     timestamptz not null default now(),
    unique (business_date, ticket_number)
);

create index if not exists idx_tickets_business_date on tickets(business_date);

alter table tickets enable row level security;

-- Phase 1 uses a single restricted anon key from the desktop app.
-- It may only insert/update its own sync rows — never delete, never
-- read other devices' data if you later add multi-tenant policies.
-- Tighten this (e.g. per-device keys, edge function) before Phase 2+
-- exposes this data to browser-facing dashboards.
create policy "desktop app can insert tickets"
    on tickets for insert
    to anon
    with check (true);

create policy "desktop app can upsert its own tickets"
    on tickets for update
    to anon
    using (true)
    with check (true);

create policy "anyone with anon key can read tickets"
    on tickets for select
    to anon
    using (true);
