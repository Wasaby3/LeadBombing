-- Сохранённые лиды по папкам. Лид в папке — снимок: строка таблицы, карточка и сырые данные фирмы для выгрузки.
-- Фото лежат на диске (user_path()/folders/<id>/<slug>.jpg). Каждый видит только своё (RLS).

create table public.folders (
  id bigint generated always as identity primary key,
  user_id uuid not null default auth.uid() references auth.users (id) on delete cascade,
  name text not null check (length(name) between 1 and 200),
  sphere text not null,
  query text not null default '',
  cities jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now()
);

create index folders_user_created_idx on public.folders (user_id, created_at desc);

create table public.folder_leads (
  folder_id bigint not null references public.folders (id) on delete cascade,
  user_id uuid not null default auth.uid() references auth.users (id) on delete cascade,
  slug text not null,
  summary jsonb not null,
  card jsonb not null,
  raw jsonb not null,
  added_at timestamptz not null default now(),
  primary key (folder_id, slug)
);

alter table public.folders enable row level security;
alter table public.folder_leads enable row level security;

create policy "own folders" on public.folders for all to authenticated
  using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));
create policy "own folder leads" on public.folder_leads for all to authenticated
  using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));

revoke all on public.folders, public.folder_leads from anon;
grant select, insert, update, delete on public.folders, public.folder_leads to authenticated;
