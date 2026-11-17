-- Личный кабинет: настройки, история запусков и найденные лиды. Каждый видит только своё (RLS).

create table public.user_settings (
  user_id uuid primary key default auth.uid() references auth.users (id) on delete cascade,
  data jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now()
);

create table public.runs (
  id bigint generated always as identity primary key,
  user_id uuid not null default auth.uid() references auth.users (id) on delete cascade,
  sphere text not null,
  query text not null default '',
  cities jsonb not null default '[]'::jsonb,
  lead_limit integer not null check (lead_limit > 0),
  status text not null default 'running' check (status in ('running', 'done', 'stopped', 'error')),
  accepted integer not null default 0,
  skipped integer not null default 0,
  error text,
  started_at timestamptz not null default now(),
  finished_at timestamptz
);

create index runs_user_started_idx on public.runs (user_id, started_at desc);

create table public.leads (
  user_id uuid not null default auth.uid() references auth.users (id) on delete cascade,
  sphere text not null,
  firm_id text not null,
  slug text not null,
  run_id bigint references public.runs (id) on delete set null,
  summary jsonb not null,
  card jsonb not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key (user_id, sphere, firm_id)
);

create index leads_user_updated_idx on public.leads (user_id, updated_at desc);
create index leads_run_idx on public.leads (run_id);

alter table public.user_settings enable row level security;
alter table public.runs enable row level security;
alter table public.leads enable row level security;

create policy "own settings" on public.user_settings for all to authenticated
  using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));
create policy "own runs" on public.runs for all to authenticated
  using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));
create policy "own leads" on public.leads for all to authenticated
  using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));

revoke all on public.user_settings, public.runs, public.leads from anon;
grant select, insert, update, delete on public.user_settings, public.runs, public.leads to authenticated;
