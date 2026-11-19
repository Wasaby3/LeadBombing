-- «Проработать лиды» на странице «Сохранённые лиды»: ссылка на демо каждого лида папки = базовый адрес
-- демо-приложения + "/" + slug лида (то же имя, что у папки tenants/<slug>/ при выгрузке).
-- Папка помнит последний базовый адрес и когда лиды прорабатывали — окно открывается с ним.

alter table public.folders
  add column demo_base_url text check (demo_base_url ~ '^https?://' and length(demo_base_url) <= 2000),
  add column demo_filled_at timestamptz;

-- Ставит ссылку (demo_source = 'auto') лидам папки: всем или только p_slugs. Клиентов и ссылки, вписанные вручную
-- (manual), не трогает; прежние auto-ссылки пересобирает. Работает с правами вызывающего, поэтому RLS видит только
-- его папки и лиды. Возвращает, скольким лидам ссылка проставлена (filled) и сколько оставлено с ручной (kept).
create function public.fill_demo_urls(p_folder_id bigint, p_base_url text, p_slugs text[] default null)
returns table (filled integer, kept integer)
language sql
security invoker
set search_path = ''
as $$
  with targets as (
    select slug, demo_source
      from public.folder_leads
     where folder_id = p_folder_id
       and client_status is null
       and (p_slugs is null or slug = any (p_slugs))
  ), done as (
    update public.folder_leads l
       set demo_url = p_base_url || '/' || l.slug, demo_source = 'auto'
      from targets t
     where l.folder_id = p_folder_id and l.slug = t.slug and t.demo_source is distinct from 'manual'
    returning 1
  ), folder as (
    update public.folders
       set demo_base_url = p_base_url, demo_filled_at = now()
     where id = p_folder_id
    returning 1
  )
  select (select count(*) from done)::integer,
         (select count(*) from targets where demo_source = 'manual')::integer
    from (select count(*) from folder) f;
$$;

revoke all on function public.fill_demo_urls(bigint, text, text[]) from public, anon;
grant execute on function public.fill_demo_urls(bigint, text, text[]) to authenticated;
