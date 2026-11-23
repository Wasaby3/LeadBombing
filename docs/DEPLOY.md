# Деплой на VPS (рядом с bani-pwa)

Сервер FirstVDS 91.132.188.117 (Ubuntu 24.04, 2 CPU, 4 ГБ). На нём уже работает bani-pwa: Supabase self-hosted в
`/opt/supabase`, Caddy на 80/443 (`supabase-caddy`), сайт в `/opt/site`. LeadBombing использует **этот же Supabase**
в своей схеме `leadbombing` и живёт в `/opt/leadbombing`. Конфиги и сайт bani не трогаются, кроме одной строки
`PGRST_DB_SCHEMAS` в `/opt/supabase/.env` (бэкап `.env.bak-leadbombing-<дата>` рядом).

## Устройство

- Контейнер `leadbombing` (`deploy/docker-compose.yml`, образ из `Dockerfile`): Flask + Google Chrome в виртуальном
  дисплее (Xvfb). Порт `127.0.0.1:8666`, наружу не открыт. Лимит памяти 1.5 ГБ (пробный поиск — пик 1.0 ГБ).
- К Supabase ходит по внутренней сети docker `supabase_default`: `SUPABASE_URL=http://api-gw:8000`, ключ —
  `SUPABASE_PUBLISHABLE_KEY` бань. `SupabaseStore` шлёт `Accept-Profile`/`Content-Profile: leadbombing`.
- Пользователи Auth общие с банями, поэтому в LeadBombing входят только участники `leadbombing.members`.
- `/opt/leadbombing`: `.env` (ключи, chmod 600), `data/` (фото лидов папок, запуски), `backups/` (дампы схемы),
  `current`/`previous` (теги образов), `releases.log`, `admin-password.txt` (только root).
- Миграции применяются через `psql` в контейнере `supabase-db` с учётом в `leadbombing.schema_migrations`:
  `supabase db push` нельзя — учёт миграций Supabase общий с банями.

## Доступ (SSH-туннель)

```bash
ssh -N -L 8666:127.0.0.1:8666 root@91.132.188.117   # держать открытым
# браузер: http://localhost:8666, логин admin
ssh root@91.132.188.117 cat /opt/leadbombing/admin-password.txt   # пароль — в своём терминале, не в чат
```

Выгрузка лидов пишет в папку **на сервере** (окно выбора папки — только macOS). Забрать:
`rsync -az root@91.132.188.117:/opt/leadbombing/data/<папка>/ ./<папка>/`.

## Команды

```bash
scripts/deploy/server.sh              # обновление: тесты → код HEAD → бэкап схемы → образ → миграции → запуск → проверка
scripts/deploy/server.sh rollback     # вернуть предыдущий образ
scripts/deploy/server.sh setup        # один раз: папки, .env, схема в API
scripts/deploy/server.sh admin        # кабинет admin / новый пароль
scripts/deploy/server.sh import-local # один раз: данные и фото из локального Supabase в пустую схему
```

Выкладывается только коммит (при незакоммиченных изменениях скрипт останавливается).

## Откат

1. **Код:** `scripts/deploy/server.sh rollback` — предыдущий образ, секунды. Миграции только добавляют, старый код
   с новой схемой работает; миграцию, которая что-то удаляет, выкладывать отдельно и после бэкапа.
2. **Данные:** дампы `/opt/leadbombing/backups/*.sql.gz` (10 последних, перед каждой выкладкой):
   ```bash
   ssh root@91.132.188.117
   docker exec supabase-db psql -U postgres -c 'drop schema leadbombing cascade'
   gunzip -c /opt/leadbombing/backups/<файл>.sql.gz | docker exec -i supabase-db psql -U postgres -v ON_ERROR_STOP=1
   docker exec supabase-db psql -U postgres -c "notify pgrst, 'reload schema'"
   ```
   Между drop и восстановлением API бань недоступен (схема из PGRST_DB_SCHEMAS пропала) — делать подряд.
3. **Убрать LeadBombing целиком** (порядок важен, иначе ляжет API бань):
   ```bash
   cd /opt/leadbombing && LEADBOMBING_TAG=$(cat current) docker compose down
   cp /opt/supabase/.env.bak-leadbombing-<дата> /opt/supabase/.env && cd /opt/supabase && docker compose up -d --no-deps rest
   docker exec supabase-db psql -U postgres -c 'drop schema leadbombing cascade'
   docker exec supabase-db psql -U postgres -c "delete from auth.users where email = 'admin@leadbombing.local'"
   ```

## Если bani-pwa выкладывается

`npm run deploy:ru` в bani-pwa перезаписывает Caddyfile и compose бань в `/opt/supabase`, но не `.env` и не
`/opt/leadbombing`; `--remove-orphans` касается только проекта `supabase`. LeadBombing это не задевает.
