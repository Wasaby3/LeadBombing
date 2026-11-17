# Структура проекта

```
leadbombing/            пакет
  main.py, cli.py       точка входа и CLI
  config.py, paths.py   настройки и пути к папкам пользователя
  chrome/               управление Chrome через CDP (pychrome)
  parser/               парсеры 2ГИС: factory.get_parser(url) → Main/Firm/InBuilding
  writer/               CSV, XLSX, JSON, HTML и фильтры результатов
  leads/                режим лидов
    writer.py             LeadsWriter: дедуп, фильтр сферы, фото, слияние с существующей папкой
    spheres.py            сферы: бани, шаблоны (авто, красота, стоматология), свободный поиск
    build.py, generic.py  сборка выгрузки для бань и для шаблонов
    contacts.py           все контакты карточки с подписями и ролями, выбор канала (руководитель первым)
    firm.py, prices.py, demo.py, text.py   общие части (firm.py: юрлицо, владелец ИП)
  web/                  Flask-приложение
    server.py             создание приложения и страницы (/search, /leads, /settings, /profile, /docs, /classic)
    auth.py, account*.py  вход, сессия, данные аккаунта
    supabase.py           клиент Supabase (Auth + PostgREST)
    leads_api.py, leads_job.py   поиск лидов в фоне и выгрузка
    folders_api.py        папки сохранённых лидов (страница «Лиды»), работа с лидом и удаление
    lead_crm.py           статусы, приоритет, комментарий, каналы связи, демо: проверка изменений
    classic_api.py, job.py, history.py   старый дашборд /classic
    static/app/           фронтенд без сборки (Alpine.js, app.js, index.html, app.css, sw.js)
  data/                 списки городов и рубрик
supabase/               config.toml, миграции (таблицы аккаунтов, запусков, лидов, папок, работа с лидом), seed.sql
tests/                  pytest; fixtures/*_golden/ — эталоны выгрузки
scripts/                обновление списков городов и рубрик
```

## Формат выгрузки лидов

```
<папка>/
  leads.json
  outreach.csv            колонки «Статус» и «Руководитель» заполняются вручную и не перезаписываются
  tenants/<slug>/
    business.json
    images/hero.jpg
```

Формат файлов и порядок колонок менять нельзя без согласования: на него завязаны golden-тесты и внешние потребители.

## Прочее

- `docs/LOGIC.md` — логика поиска, отсева и выбора контактов (то же, что страница «Документация»).
- `CLAUDE.md` — подробные заметки об архитектуре для разработки с Claude Code.
- `PROMPT.md` — исходный бриф продукта и его жёсткие ограничения.
