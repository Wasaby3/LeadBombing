-- Настраиваемые статусы лидов (Настройки → «Статусы лидов»): своё название и цвет вместо жёстко заданных шести.
-- Статус хранится один раз в этой таблице и читается по id, поэтому переименование и смена цвета показываются
-- сразу во всех лидах без их обхода. Обход нужен только при удалении статуса — лиды с ним переносит на статус по
-- умолчанию приложение (web/lead_statuses.py), атомарно через delete_lead_status. Таблицу с шестью стандартными
-- статусами приложение заводит лениво при первом обращении пользователя (list_lead_statuses), поэтому backfill
-- здесь не нужен — старые значения folder_leads.status совпадают с id стандартных статусов.
-- Статус по умолчанию — это не отдельное поле, а всегда статус с наименьшим sort_order (первый в списке);
-- not_written заводится с sort_order = 0 и не удаляется, поэтому остаётся дефолтным, пока список не переставят.
-- not_written и bought нельзя удалить (можно переименовать и перекрасить): на их id держится счётчик «Написали» и
-- переход «Перевести в клиенты» (см. PROTECTED_IDS в web/lead_statuses.py).

create table leadbombing.lead_statuses (
  user_id uuid not null default auth.uid() references auth.users (id) on delete cascade,
  id text not null check (id ~ '^[a-z0-9_-]{1,40}$'),
  name text not null check (length(name) between 1 and 40),
  color text not null
    check (color in ('neutral', 'good', 'wait', 'active', 'warm', 'bad', 'purple', 'teal', 'pink')),
  sort_order integer not null,
  created_at timestamptz not null default now(),
  primary key (user_id, id)
);

alter table leadbombing.lead_statuses enable row level security;
create policy "own lead statuses" on leadbombing.lead_statuses for all to authenticated
  using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));

revoke all on leadbombing.lead_statuses from anon;
grant select, insert, update, delete on leadbombing.lead_statuses to authenticated;

-- Старый жёсткий список снят: допустимость статуса теперь проверяет приложение по строкам lead_statuses.
alter table leadbombing.folder_leads drop constraint folder_leads_status_check;

-- Удаление статуса: лиды с ним переходят на статус с наименьшим sort_order среди оставшихся (новый дефолт), и
-- только тогда сама строка удаляется.
create function leadbombing.delete_lead_status(p_id text)
returns void
language plpgsql
security invoker
set search_path = ''
as $$
declare
  v_user uuid := (select auth.uid());
  v_fallback text;
begin
  select id into v_fallback from leadbombing.lead_statuses
   where user_id = v_user and id <> p_id
   order by sort_order asc limit 1;
  update leadbombing.folder_leads set status = v_fallback where user_id = v_user and status = p_id;
  delete from leadbombing.lead_statuses where user_id = v_user and id = p_id;
end;
$$;

revoke all on function leadbombing.delete_lead_status(text) from public, anon;
grant execute on function leadbombing.delete_lead_status(text) to authenticated;
