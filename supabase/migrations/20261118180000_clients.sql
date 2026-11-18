-- Клиенты и новые статусы лида.
-- Статусы лида: «Ещё не написал» (по умолчанию), «Написал», «В работе», «Почти купил», «Купил», «Отказался».
-- Клиент — тот же лид в папке с client_status: null — лид (страница «Сохранённые лиды»), ok / question / bug —
-- клиент (страница «Клиенты»: «Всё ок», «Есть вопрос», «Срочный баг»). client_since — когда стал клиентом.
-- Старые статусы переводятся по смыслу: new → not_written, waiting и no_answer → written, lost → refused,
-- client → bought и сразу в клиенты со статусом «Всё ок».

alter table public.folder_leads drop constraint folder_leads_status_check;

alter table public.folder_leads
  add column client_status text check (client_status in ('ok', 'question', 'bug')),
  add column client_since timestamptz,
  add constraint folder_leads_client_since_with_status check ((client_status is null) = (client_since is null));

update public.folder_leads
   set client_status = 'ok', client_since = coalesce(worked_at, added_at)
 where status = 'client';

update public.folder_leads
   set status = case status
                  when 'new' then 'not_written'
                  when 'waiting' then 'written'
                  when 'no_answer' then 'written'
                  when 'lost' then 'refused'
                  when 'client' then 'bought'
                  else status
                end;

alter table public.folder_leads
  alter column status set default 'not_written',
  add constraint folder_leads_status_check
    check (status in ('not_written', 'written', 'in_progress', 'almost', 'bought', 'refused'));

create index folder_leads_clients_idx on public.folder_leads (user_id, client_since desc)
  where client_status is not null;
