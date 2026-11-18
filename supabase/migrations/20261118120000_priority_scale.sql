-- Приоритет лида — пять уровней вместо трёх: 1 очень низкий … 5 очень высокий, 0 не задан. Новый лид получает
-- приоритет и комментарий из оценки карточки 2ГИС (leads/booking.py) при сохранении в папку.
-- Старые значения переводятся по смыслу: низкий 1 → 1, средний 2 → 3, высокий 3 → 5.

alter table public.folder_leads drop constraint folder_leads_priority_check;

update public.folder_leads
   set priority = case priority when 3 then 5 when 2 then 3 else priority end
 where priority in (2, 3);

alter table public.folder_leads
  add constraint folder_leads_priority_check check (priority between 0 and 5);
