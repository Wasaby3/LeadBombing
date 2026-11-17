# Команды

Все команды запускаются из корня репозитория.

## Приложение

| Команда | Что делает |
|---------|------------|
| `.venv/bin/python -m pip install -e .` | Установить пакет (добавьте `.[dev]` для pytest, tox, pre-commit) |
| `.venv/bin/leadbombing` | Веб-приложение на http://localhost:8666 (открывает браузер) |
| `.venv/bin/leadbombing-cli` | То же без аргументов; с `-i`, `-o`, `-f` — CLI |
| `.venv/bin/leadbombing-cli --help` | Полный список флагов CLI |

Если порт 8666 занят — работает старый сервер, остановите его.

## Supabase (аккаунты)

| Команда | Что делает |
|---------|------------|
| `npx supabase@3.1.0 start` | Поднять локальный Supabase (порты 5532x), применить миграции и seed |
| `npx supabase@3.1.0 status` | Показать URL и ключи (`SUPABASE_ANON_KEY`) |
| `npx supabase@3.1.0 db reset` | Пересоздать БД из миграций и seed — **стирает данные аккаунтов** |
| `npx supabase@3.1.0 stop` | Остановить контейнеры |

## Проверки

| Команда | Что делает |
|---------|------------|
| `.venv/bin/python -m pytest` | Все тесты |
| `.venv/bin/python -m pytest --ignore=tests/test_parser.py` | Без живого теста 2ГИС (он медленный и может упасть на капче) |
| `.venv/bin/python -m pytest tests/test_leads_golden.py -k <name>` | Один тест |
| `.venv/bin/python -m flake8 leadbombing tests` | Линтер (длина строки 130) |
| `.venv/bin/python -m mypy` | Типы (настроено в `setup.cfg`, есть старые ошибки) |

Golden-тесты сравнивают выгрузку побайтно с `tests/fixtures/*_golden/`. Перезаписывать эталоны — только при
согласованной смене формата. `tests/test_supabase_store.py` пропускается, если Supabase не запущен.

## Основные флаги CLI

| Флаг | Значение |
|------|----------|
| `-i URL [URL ...]` | Ссылки на выдачу 2ГИС |
| `-o PATH` | Файл результата (для `-f leads` — папка) |
| `-f {csv,xlsx,json,html,leads}` | Формат |
| `--chrome.headless yes` | Скрыть браузер |
| `--writer.csv.clean yes` | Только основные колонки в CSV/XLSX |
| `--filters.require-phone yes` и др. `--filters.*` | Фильтры: телефон, WhatsApp, соцсети, e-mail, сайт, рейтинг, отзывы, франшизы |
| `--parser.max-records N` | Лимит записей на ссылку |

## Скрипты

| Команда | Что делает |
|---------|------------|
| `.venv/bin/python scripts/update_cities_list.py` | Обновить список городов в `leadbombing/data/` |
| `.venv/bin/python scripts/update_rubrics_list.py` | Обновить список рубрик в `leadbombing/data/` |
