-- Счётчик «Написали» на странице «Сохранённые лиды»: лиды папки со статусом не «Ещё не написал». Лид, переведённый
-- в клиенты, остаётся в folder_leads и считается оттуда; удалённый лид пропадает, поэтому папка помнит, сколько
-- удалено лидов, с которыми уже работали (removed_worked).

alter table public.folders
  add column removed_worked integer not null default 0 check (removed_worked >= 0);

-- Удаляет лид или клиента папки; если статус был не «Ещё не написал», увеличивает removed_worked. Работает с правами
-- вызывающего (RLS: только свои папки). Возвращает, был ли такой лид.
create function public.delete_folder_lead(p_folder_id bigint, p_slug text)
returns boolean
language sql
security invoker
set search_path = ''
as $$
  with gone as (
    delete from public.folder_leads
     where folder_id = p_folder_id and slug = p_slug
    returning status
  ), counted as (
    update public.folders
       set removed_worked = removed_worked + 1
     where id = p_folder_id and exists (select 1 from gone where status <> 'not_written')
    returning 1
  )
  select exists (select 1 from gone) from (select count(*) from counted) c;
$$;

revoke all on function public.delete_folder_lead(bigint, text) from public, anon;
grant execute on function public.delete_folder_lead(bigint, text) to authenticated;
