# Переменные окружения

Нужны только веб-приложению; CLI работает без них. Значения берутся из окружения, иначе из `.env.local`
(сначала в корне репозитория, потом в текущей папке). Шаблон — `.env.example`, `.env.local` в git не попадает.

| Переменная | Обязательна | Описание | По умолчанию |
|------------|-------------|----------|--------------|
| `SUPABASE_URL` | Нет | Адрес локального Supabase | `http://127.0.0.1:55321` |
| `SUPABASE_ANON_KEY` | Да | Публичный ключ (`PUBLISHABLE_KEY` или `ANON_KEY` из `npx supabase@3.1.0 status`) | — |
| `LEADBOMBING_SECRET_KEY` | Нет | Ключ подписи cookie сессии. Без него создаётся один раз в файле `secret_key` в папке настроек приложения (`~/Library/Application Support/leadbombing` на macOS) | генерируется |
| `XDG_CONFIG_HOME`, `XDG_DATA_HOME` | Нет | Только Linux: где лежат настройки и данные (папка запусков `runs/`) | стандартные пути ОС |

Вход в аккаунт: логин `<login>` превращается в e-mail `<login>@leadbombing.local`. Тестовый пользователь — `admin` / `admin`
(из `supabase/seed.sql`).
