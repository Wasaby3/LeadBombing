-- Своя схема leadbombing: на сервере Supabase общий с другим приложением (bani-pwa), его таблицы лежат в public.
-- Таблицы переезжают целиком (данные, индексы, RLS-политики и права едут вместе с ними). Функции пересоздаются:
-- в их телах явно написано public.*. API видит схему, если она есть в списке схем PostgREST
-- (локально api.schemas в config.toml, на сервере PGRST_DB_SCHEMAS), клиент выбирает её заголовком Accept/Content-Profile.

create schema if not exists leadbombing;  -- deploy.sh может создать её раньше для своего учёта миграций
grant usage on schema leadbombing to authenticated, service_role;

alter table public.user_settings set schema leadbombing;
alter table public.runs set schema leadbombing;
alter table public.leads set schema leadbombing;
alter table public.folders set schema leadbombing;
alter table public.folder_leads set schema leadbombing;

drop function public.fill_demo_urls(bigint, text, text[]);
drop function public.delete_folder_lead(bigint, text);

create function leadbombing.fill_demo_urls(p_folder_id bigint, p_base_url text, p_slugs text[] default null)
returns table (filled integer, kept integer)
language sql
security invoker
set search_path = ''
as $$
  with targets as (
    select slug, demo_source
      from leadbombing.folder_leads
     where folder_id = p_folder_id
       and client_status is null
       and (p_slugs is null or slug = any (p_slugs))
  ), done as (
    update leadbombing.folder_leads l
       set demo_url = p_base_url || '/' || l.slug, demo_source = 'auto'
      from targets t
     where l.folder_id = p_folder_id and l.slug = t.slug and t.demo_source is distinct from 'manual'
    returning 1
  ), folder as (
    update leadbombing.folders
       set demo_base_url = p_base_url, demo_filled_at = now()
     where id = p_folder_id
    returning 1
  )
  select (select count(*) from done)::integer,
         (select count(*) from targets where demo_source = 'manual')::integer
    from (select count(*) from folder) f;
$$;

revoke all on function leadbombing.fill_demo_urls(bigint, text, text[]) from public, anon;
grant execute on function leadbombing.fill_demo_urls(bigint, text, text[]) to authenticated;

create function leadbombing.delete_folder_lead(p_folder_id bigint, p_slug text)
returns boolean
language sql
security invoker
set search_path = ''
as $$
  with gone as (
    delete from leadbombing.folder_leads
     where folder_id = p_folder_id and slug = p_slug
    returning status
  ), counted as (
    update leadbombing.folders
       set removed_worked = removed_worked + 1
     where id = p_folder_id and exists (select 1 from gone where status <> 'not_written')
    returning 1
  )
  select exists (select 1 from gone) from (select count(*) from counted) c;
$$;

revoke all on function leadbombing.delete_folder_lead(bigint, text) from public, anon;
grant execute on function leadbombing.delete_folder_lead(bigint, text) to authenticated;

-- Кому открыт LeadBombing. Пользователи Auth общие с другим приложением, поэтому входят только участники.
-- Добавляют вручную (SQL от postgres), сами себя пользователи не добавляют.
create table leadbombing.members (
  user_id uuid primary key references auth.users (id) on delete cascade,
  added_at timestamptz not null default now()
);

alter table leadbombing.members enable row level security;
create policy "own membership" on leadbombing.members for select to authenticated
  using (user_id = (select auth.uid()));
revoke all on leadbombing.members from anon;
grant select on leadbombing.members to authenticated;

-- Локальные кабинеты (вход по логину = почта @leadbombing.local) остаются участниками.
insert into leadbombing.members (user_id)
select id from auth.users where email like '%@leadbombing.local'
on conflict do nothing;
