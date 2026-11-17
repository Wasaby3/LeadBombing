-- Работа с сохранённым лидом (страница «Лиды»): статус, приоритет, комментарий, по каким контактам связывались,
-- демо-приложение. Хранится у лида в конкретной папке. Пересохранение лида из поиска эти колонки не трогает
-- (upsert передаёт только снимок: summary, card, raw).

alter table public.folder_leads
  add column status text not null default 'new'
    check (status in ('new', 'client', 'lost', 'waiting', 'no_answer')),
  add column priority smallint not null default 0 check (priority between 0 and 3),
  add column comment text not null default '' check (length(comment) <= 5000),
  add column contacted jsonb not null default '[]'::jsonb check (jsonb_typeof(contacted) = 'array'),
  -- Демо-приложение: URL вписывают вручную (manual); позже его сможет заполнять генератор (auto).
  add column demo_url text check (demo_url ~ '^https?://' and length(demo_url) <= 2000),
  add column demo_source text check (demo_source in ('manual', 'auto')),
  add column worked_at timestamptz,
  add constraint folder_leads_demo_source_with_url check ((demo_url is null) = (demo_source is null));
