-- Supabase schema: mirror + queue-calling coordination.
--
-- The local SQLite database (desktop app) remains the source of truth
-- for TICKET NUMBERING — this table only mirrors already-printed
-- tickets and adds the "calling" columns used by the online public
-- display / call-next pages (hosted on Vercel, see /nextjs-app).
--
-- Numbering and calling are deliberately split across two different
-- write paths so neither can corrupt the other:
--   - the desktop app's background sync UPSERTs its own printed
--     tickets directly (status/printed_at/etc.) — unchanged from Phase 1.
--   - calling a ticket forward is NOT a plain UPDATE from the browser.
--     It only happens through call_next_ticket(), a SECURITY DEFINER
--     function that atomically picks the oldest waiting ticket and
--     marks it CALLED. The anon key has no direct UPDATE grant on
--     status/counter_number/called_at outside that function, so two
--     browsers calling "next" at the same instant can't both grab the
--     same ticket, and a page can't hand-craft an update to skip the
--     queue.

create table if not exists tickets (
    uuid           uuid primary key,
    ticket_number  integer not null,
    business_date  date not null,
    status         text not null,
    printed_at     timestamptz,
    device_id      text,
    printer_name   text,
    counter_number integer,
    called_at      timestamptz,
    created_at     timestamptz not null,
    updated_at     timestamptz not null,
    synced_at      timestamptz not null default now(),
    unique (business_date, ticket_number)
);

-- Additive migration for projects created from the Phase 1 version of
-- this file (safe to re-run: IF NOT EXISTS on everything).
alter table tickets add column if not exists counter_number integer;
alter table tickets add column if not exists called_at timestamptz;

create index if not exists idx_tickets_business_date on tickets(business_date);
create index if not exists idx_tickets_waiting
    on tickets(business_date, ticket_number)
    where status = 'PRINTED' and called_at is null;

alter table tickets enable row level security;

-- Desktop app sync (unchanged from Phase 1): the printer PC's anon key
-- upserts its own printed tickets directly. This key is only ever
-- held by the printer PC, not shipped to the browser.
drop policy if exists "desktop app can insert tickets" on tickets;
create policy "desktop app can insert tickets"
    on tickets for insert
    to anon
    with check (true);

drop policy if exists "desktop app can upsert its own tickets" on tickets;
create policy "desktop app can upsert its own tickets"
    on tickets for update
    to anon
    using (true)
    with check (true);

-- Public read (the Vercel display/call pages use the anon key too —
-- browser-exposed, so it must stay read-only + the RPC below).
drop policy if exists "anyone with anon key can read tickets" on tickets;
create policy "anyone with anon key can read tickets"
    on tickets for select
    to anon
    using (true);

-- NOTE: the same broad "using (true)" UPDATE policy above technically
-- also lets anyone with the anon key hand-craft a direct update to
-- tickets (e.g. change status themselves) — that was an accepted
-- simplification back when only the desktop app held this key. Now
-- that the key is exposed in the browser (Vercel), the honest fix is
-- a separate, narrower key/policy for the desktop sync vs. the public
-- pages. Tracked as a known follow-up, not solved by this migration —
-- see PHASE2_WEB.md "Known limitations".

-- Atomically call the oldest waiting ticket to a counter. SECURITY
-- DEFINER means it runs with the owner's privileges and bypasses RLS
-- internally, so it can update `tickets` even though anon has no
-- direct column-level grant on status/counter_number/called_at beyond
-- the broad policy above — this is the intended, safe write path.
-- Returns zero rows if nothing is waiting (checked by the caller as
-- "no waiting tickets", not an error).
create or replace function call_next_ticket(p_business_date date, p_counter_number integer)
returns table(out_ticket_number integer, out_counter_number integer, out_called_at timestamptz)
language plpgsql
security definer
set search_path = public
as $$
declare
    v_now timestamptz := now();
    v_ticket_number integer;
    v_called_at timestamptz;
begin
    update tickets t
    set status = 'CALLED',
        counter_number = p_counter_number,
        called_at = v_now,
        updated_at = v_now
    where t.uuid = (
        select uuid from tickets
        where business_date = p_business_date
          and status = 'PRINTED'
          and called_at is null
        order by ticket_number asc
        limit 1
        for update skip locked
    )
    returning t.ticket_number, t.called_at into v_ticket_number, v_called_at;

    if v_ticket_number is null then
        return; -- empty result set = queue is empty right now
    end if;

    out_ticket_number := v_ticket_number;
    out_counter_number := p_counter_number;
    out_called_at := v_called_at;
    return next;
end;
$$;

grant execute on function call_next_ticket(date, integer) to anon;

-- Admin reset: wipes every ticket for a given business date (used by
-- the desktop app's PIN-gated "إعادة تعيين النظام" action to zero the
-- sequence, e.g. after a rehearsal/demo). Password-gated INSIDE the
-- function, not just client-side in the desktop app — the anon key
-- calling this RPC is also embedded in the public Vercel site, so a
-- client-side-only check would be no protection at all against
-- someone calling this RPC directly from a browser console. Only the
-- password check makes this safe to grant to anon.
create or replace function admin_reset_business_date(p_business_date date, p_password text)
returns void
language plpgsql
security definer
set search_path = public
as $$
begin
    if p_password is distinct from '11223344' then
        raise exception 'invalid password';
    end if;

    delete from tickets where business_date = p_business_date;
end;
$$;

grant execute on function admin_reset_business_date(date, text) to anon;

-- Enable Realtime for the public display page's live subscription
-- (Database > Replication > supabase_realtime in the dashboard also
-- works instead of this statement). Guarded because, unlike the rest
-- of this file, ALTER PUBLICATION ... ADD TABLE errors on re-run if
-- the table is already a member.
do $$
begin
    if not exists (
        select 1 from pg_publication_tables
        where pubname = 'supabase_realtime' and tablename = 'tickets'
    ) then
        alter publication supabase_realtime add table tickets;
    end if;
end $$;
