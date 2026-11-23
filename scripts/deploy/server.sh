#!/usr/bin/env bash
# LeadBombing на VPS рядом с bani-pwa (/opt/leadbombing). Supabase общий, схема leadbombing; bani не трогаем,
# кроме одной строки PGRST_DB_SCHEMAS в /opt/supabase/.env (setup, с бэкапом).
#   scripts/deploy/server.sh               — выкладка HEAD: тесты, бэкап БД, образ, миграции, запуск, проверка
#   scripts/deploy/server.sh rollback      — вернуть предыдущий образ
#   scripts/deploy/server.sh setup         — один раз: .env на сервере, схема leadbombing в API
#   scripts/deploy/server.sh admin         — кабинет admin с новым паролем (пароль остаётся на сервере)
#   scripts/deploy/server.sh import-local  — один раз: данные и фото из локального Supabase
# Доступ: ssh -N -L 8666:127.0.0.1:8666 root@91.132.188.117, затем http://localhost:8666
set -euo pipefail

HOST="${LB_HOST:-root@91.132.188.117}"
APP=/opt/leadbombing
SB=/opt/supabase
LOCAL_DB=supabase_db_leadbombing
LOCAL_DATA="$HOME/Library/Application Support/leadbombing/folders"
ADMIN_ID=a0000000-0000-4000-8000-000000000001
APP_UID=1001
KEEP_IMAGES=3
KEEP_BACKUPS=10
TABLES=(user_settings runs leads folders folder_leads)

step() { printf '\n\033[1;33m▶ %s\033[0m\n' "$*"; }
die() { printf '\033[1;31m✘ %s\033[0m\n' "$*" >&2; exit 1; }
remote() { ssh -o BatchMode=yes "$HOST" "$@"; }
psql_remote() { remote "docker exec -i supabase-db psql -U postgres -v ON_ERROR_STOP=1 -q $*"; }

cd "$(git rev-parse --show-toplevel)"

up() {  # up <tag>: запустить образ и дождаться healthcheck
  remote "cd $APP && LEADBOMBING_TAG=$1 docker compose up -d --wait --wait-timeout 90"
  remote "curl -fsS -o /dev/null http://127.0.0.1:8666/search && test \"\$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8666/api/auth/me)\" = 401" \
    || die "Приложение не отвечает — откат: scripts/deploy/server.sh rollback"
}

migrate() {
  remote "docker exec -i supabase-db psql -U postgres -v ON_ERROR_STOP=1 -q" <<'SQL'
create schema if not exists leadbombing;
create table if not exists leadbombing.schema_migrations (version text primary key, applied_at timestamptz not null default now());
SQL
  local applied version f
  applied=$(remote "docker exec supabase-db psql -U postgres -Atc 'select version from leadbombing.schema_migrations'")
  for f in supabase/migrations/*.sql; do
    version=$(basename "$f" | cut -d_ -f1)
    grep -qx "$version" <<<"$applied" && continue
    echo "  миграция $(basename "$f")"
    { cat "$f"; echo "insert into leadbombing.schema_migrations (version) values ('$version');"; } \
      | psql_remote --single-transaction
  done
}

deploy() {
  git diff --quiet HEAD || die "Есть незакоммиченные изменения — выкладывается только коммит"
  local sha; sha=$(git rev-parse --short HEAD)

  step "1/6 Тесты"
  .venv/bin/python -m pytest -q --ignore=tests/test_parser.py

  step "2/6 Код $sha → $HOST:$APP/src"
  remote "test -f $APP/.env" || die "Сначала scripts/deploy/server.sh setup"
  git archive --format=tar HEAD | remote "rm -rf $APP/src && mkdir -p $APP/src && tar -x -C $APP/src"
  scp -q deploy/docker-compose.yml "$HOST:$APP/docker-compose.yml"

  step "3/6 Бэкап схемы leadbombing"
  remote "mkdir -p $APP/backups && docker exec supabase-db pg_dump -U postgres -n leadbombing | gzip > $APP/backups/\$(date +%F-%H%M%S)-$sha.sql.gz \
    && ls -1t $APP/backups/*.sql.gz | tail -n +$((KEEP_BACKUPS + 1)) | xargs -r rm --"

  step "4/6 Образ leadbombing:$sha"
  remote "cd $APP/src && docker build -q -t leadbombing:$sha . >/dev/null"

  step "5/6 Миграции"
  migrate

  step "6/6 Запуск и проверка"
  remote "cd $APP && { test -f current && cp current previous || true; } && echo $sha > current"
  up "$sha"
  remote "echo \"\$(date -Is) $sha\" >> $APP/releases.log; \
    docker images leadbombing --format '{{.Tag}}' | grep -vx -e smoke -e $sha -e \"\$(cat $APP/previous 2>/dev/null)\" \
      | tail -n +$KEEP_IMAGES | xargs -r -I{} docker rmi -f leadbombing:{} >/dev/null"
  printf '\n\033[1;32m✔ Выложено %s\033[0m  ssh -N -L 8666:127.0.0.1:8666 %s → http://localhost:8666\n' "$sha" "$HOST"
}

rollback() {
  local prev; prev=$(remote "cat $APP/previous 2>/dev/null") || die "Нет предыдущего выпуска"
  step "Откат на $prev"
  remote "cd $APP && cp current previous.new && echo $prev > current && mv previous.new previous"
  up "$prev"
  echo "Код откатан. Миграции только добавляют, данные не трогаются; восстановить БД — см. docs/DEPLOY.md."
}

setup() {
  step "Папки и .env на сервере"
  remote "mkdir -p $APP/data $APP/backups && chown $APP_UID:$APP_UID $APP/data"
  remote "test -f $APP/.env || { umask 077; printf 'SUPABASE_URL=http://api-gw:8000\nSUPABASE_ANON_KEY=%s\nLEADBOMBING_SECRET_KEY=%s\n' \
    \"\$(grep '^SUPABASE_PUBLISHABLE_KEY=' $SB/.env | cut -d= -f2-)\" \"\$(openssl rand -hex 32)\" > $APP/.env; }"

  step "Схема leadbombing в API Supabase (одна строка в $SB/.env, бэкап рядом)"
  # Сначала схема: PostgREST не грузится, если в PGRST_DB_SCHEMAS есть несуществующая схема (и API бань ложится).
  remote "docker exec supabase-db psql -U postgres -v ON_ERROR_STOP=1 -qc 'create schema if not exists leadbombing; grant usage on schema leadbombing to authenticated, service_role;'"
  if remote "grep -q '^PGRST_DB_SCHEMAS=.*leadbombing' $SB/.env"; then
    echo "  уже добавлена"
  else
    remote "cp -p $SB/.env $SB/.env.bak-leadbombing-\$(date +%F-%H%M%S) \
      && sed -i 's/^PGRST_DB_SCHEMAS=\(.*\)$/PGRST_DB_SCHEMAS=\1,leadbombing/' $SB/.env \
      && grep '^PGRST_DB_SCHEMAS=' $SB/.env \
      && cd $SB && docker compose up -d --no-deps rest"
  fi
}

admin() {
  remote "docker exec supabase-db psql -U postgres -Atc 'select 1 from pg_namespace where nspname = \$\$leadbombing\$\$'" | grep -q 1 \
    || die "Сначала выкладка (миграции создают схему)"
  step "Кабинет admin: новый пароль → $APP/admin-password.txt (только root)"
  remote "umask 077; openssl rand -base64 24 | tr -d '/+=\n' | head -c 24 > $APP/admin-password.txt"
  remote "docker exec -i supabase-db psql -U postgres -v ON_ERROR_STOP=1 -q -v pw=\"\$(cat $APP/admin-password.txt)\"" <<SQL
insert into auth.users (instance_id, id, aud, role, email, encrypted_password, email_confirmed_at,
  raw_app_meta_data, raw_user_meta_data, created_at, updated_at, confirmation_token, email_change,
  email_change_token_new, recovery_token)
values ('00000000-0000-0000-0000-000000000000', '$ADMIN_ID', 'authenticated', 'authenticated',
  'admin@leadbombing.local', extensions.crypt(:'pw', extensions.gen_salt('bf')), now(),
  '{"provider": "email", "providers": ["email"]}', '{"login": "admin"}', now(), now(), '', '', '', '')
on conflict (id) do update set encrypted_password = excluded.encrypted_password, updated_at = now();
insert into auth.identities (id, user_id, provider_id, identity_data, provider, last_sign_in_at, created_at, updated_at)
select gen_random_uuid(), '$ADMIN_ID', '$ADMIN_ID',
  '{"sub": "$ADMIN_ID", "email": "admin@leadbombing.local", "email_verified": true}', 'email', now(), now(), now()
where not exists (select 1 from auth.identities where user_id = '$ADMIN_ID' and provider = 'email');
insert into leadbombing.members (user_id) values ('$ADMIN_ID') on conflict do nothing;
SQL
  echo "Пароль прочитайте в своём терминале: ssh $HOST cat $APP/admin-password.txt"
}

import_local() {
  local count
  count=$(remote "docker exec supabase-db psql -U postgres -Atc 'select (select count(*) from leadbombing.folders) + (select count(*) from leadbombing.runs)'")
  [[ "$count" == 0 ]] || die "На сервере уже есть данные — импорт только в пустую схему"

  step "Данные: локальный Supabase → сервер"
  local args=(); for t in "${TABLES[@]}"; do args+=(-t "leadbombing.$t"); done
  docker exec "$LOCAL_DB" pg_dump -U postgres --data-only "${args[@]}" | psql_remote --single-transaction
  for t in "${TABLES[@]}"; do
    printf '  %-14s локально %s, на сервере %s\n' "$t" \
      "$(docker exec "$LOCAL_DB" psql -U postgres -Atc "select count(*) from leadbombing.$t")" \
      "$(remote "docker exec supabase-db psql -U postgres -Atc 'select count(*) from leadbombing.$t'")"
  done

  step "Фото лидов → $APP/data/folders"
  rsync -az "$LOCAL_DATA/" "$HOST:$APP/data/folders/"
  remote "chown -R $APP_UID:$APP_UID $APP/data"
}

case "${1:-deploy}" in
  deploy) deploy ;;
  rollback) rollback ;;
  setup) setup ;;
  admin) admin ;;
  import-local) import_local ;;
  *) die "Неизвестная команда: $1 (deploy | rollback | setup | admin | import-local)" ;;
esac
