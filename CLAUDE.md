# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

LeadBombing is a local lead-finding app (LGPLv3; distribution and import package `leadbombing`). It drives a local Google Chrome over 2GIS search results and exports leads into a folder on disk. UI text, log messages, and user-facing errors are in Russian; keep them that way.

`PROMPT.md` is the original product brief. Its hard constraints still apply:
- Runtime is fully local: only Python, Chrome, 2GIS, and the local Supabase in Docker (accounts; the user asked for it). No LLM or other external service calls. Hook and message texts come from sphere templates.
- Export formats must not change: CSV (including `--writer.csv.clean`), `leads.json`, `outreach.csv` (column set and order), `business.json`, and the folder layout. New fields need the user's consent.
- Don't rewrite the working parser internals described below.

## Commands

The `.venv` uses Python 3.13. Google Chrome and Docker must be installed. The web app needs the local Supabase running; the CLI doesn't.

```bash
.venv/bin/python -m pip install -e .            # install (add .[dev] for pytest/tox/pre-commit)
npx supabase@3.1.0 start                         # local Supabase on 5532x (supabase/config.toml), applies migrations + seed
npx supabase@3.1.0 db reset                      # re-create the DB: migrations + seed (wipes account data)
.venv/bin/leadbombing                             # leads app at http://localhost:8666 (opens a browser)
.venv/bin/leadbombing-cli -i "https://2gis.ru/moscow/search/Аптеки" -o out.csv -f csv   # headless CLI
.venv/bin/python -m pytest                        # all tests (testpaths=tests, pythonpath=.)
.venv/bin/python -m pytest tests/test_leads_golden.py -k <name>   # single test
.venv/bin/python -m pytest --ignore=tests/test_parser.py          # skip the live-2GIS test
.venv/bin/python -m flake8 leadbombing tests     # max-line-length 130 (setup.cfg)
.venv/bin/python -m mypy                          # configured in setup.cfg, files = leadbombing (has pre-existing errors)
```

- `tests/test_parser.py` launches real Chrome against live 2GIS. It's slow (over a minute) and can fail on captcha or network issues. The other tests use fixtures and fakes.
- `.claude/launch.json` defines the `leadbombing` preview server (port 8666, no auto-open).
- Port 8666 already in use means an old server is still running. Kill it before starting a new one.
- Supabase settings come from the environment or `.env.local` (gitignored; template `.env.example`): `SUPABASE_URL` (default `http://127.0.0.1:55321`) and `SUPABASE_ANON_KEY` (the publishable key from `npx supabase status`). The bathhouse project `../bani-pwa` runs its own stack on 5432x; both can run at once.
- Test account: login `admin`, password `admin` (`supabase/seed.sql`). Logins map to `<login>@leadbombing.local`. Signup is off; add users by hand (SQL like the seed, or Supabase admin API).
- `leadbombing-cli` with no arguments also starts the web UI. With `-i`, `-o`, and `-f` it runs the CLI (`cli.py`).

## Architecture

### Scraping pipeline (`parser/`, `chrome/`)
`parser/factory.get_parser(url)` picks `FirmParser`, `InBuildingParser`, or `MainParser` by URL pattern. `MainParser` (`parser/parsers/main.py`) controls Chrome through `chrome/remote.py` (pychrome over CDP). 2GIS changed its site, and these workarounds are deliberate:
- Pagination navigates to `/page/N` URLs. Clicking in the SPA doesn't update the list.
- Firm data: `_fetch_state(path, js_expr)` runs a synchronous XHR in the same tab and parses the server-rendered `window.initialState`. Firm profile: `/firm/<id>` → `data.entity.profile[<id>].data`. Prices: `/firm/<id>/tab/prices` → `data.market`.
- HTTP 403/429 or a page without `initialState` means captcha or block. The parser raises `ParserException` and the whole run stops. Any other per-firm error is logged and skipped.
- Headless mode forces a viewport size. Without it the WebGL map sends a degenerate bound and the API returns 400.

Writers get catalog-item documents through `writer.write(doc)`. `writer/factory.get_writer` returns CSV/XLSX/JSON/HTML writers (optionally wrapped in `FilterWriter`), or `LeadsWriter` for `-f leads`.

### Leads mode (`leads/`)
- `leads/writer.py` `LeadsWriter`: the output path is a folder, not a file. It dedups by 2GIS firm id and by (name, address). It applies `sphere.filter_reason`, fetches prices through `fetch_state` (which `MainParser` injects), downloads `hero.jpg` (a 403/429 here also aborts the run), and calls `sphere.build`. It merges with an existing `leads.json`/`outreach.csv` and never overwrites the hand-filled `Статус` / `Руководитель`. It emits `lead`/`skip` events through `on_event` and keeps every accepted firm in `raw` so the web app can replay it into another folder with `add()`.
- `leads/spheres.py` handles sphere selection:
  - `BaniSphere`: the original bathhouse template. Moscow only, `BANI_COLUMNS` (`Баня`, `Залы`), builds with `leads/build.py`. Its output must stay byte-identical; `tests/test_leads_golden.py` checks it against `tests/fixtures/bani_golden/`.
  - `TemplateSphere` + `Template` entries in `TEMPLATES` (auto, beauty, dental): multi-city, builds with `leads/generic.py` using `generic.COLUMNS` (`Название`, `Услуги`, `services` instead of `halls`). To add a sphere, add a `Template`.
  - `custom`: free search. The user's query is used as-is, there's no rubric filter, and the output format matches the templates.
- Shared by both builders (put new cross-sphere code here, not in `build.py`):
  - `firm.py`: reads profile facts (id, short name, district, photo, legal name).
  - `contacts.py`: `contacts_of`, `pick_channel`, `Reach` and the outreach/lead/business contact blocks.
  - `prices.py`: the prices-tab JS, price parsing, and the «old prices» threshold.
  - `demo.py`: shared pieces of `business.json`/`leads.json` (legal, policy, theme, wordmark).
  - `text.py`: phones, transliteration, slugs.
  - `build.py` keeps the bathhouse-only parts (halls, schedule) plus `schedule_of`, which `generic.py` also uses.
- Dict key order is part of the output format: build `business`/`lead` dicts in their existing order.

### Web app (`web/`)
- `server.py` `create_app(store=None, secret_key=None)`: Flask app setup and static pages only. `/search`, `/profile` and `/settings` serve the leads SPA from `web/static/app/` (`/` redirects to `/search`; `app.js` picks the page from the URL, side menu in `index.html`, theme choice in localStorage), and `/classic` serves the legacy dashboard page. Tests pass a `FakeStore` and a fixed key.
- Accounts (Supabase):
  - `supabase.py` `SupabaseStore`: thin `requests` client. Password login via Auth, account tables via PostgREST with the user's JWT, so RLS limits every row to its owner. Errors are `StoreError` / `InvalidCredentials` / `SessionExpired` with Russian messages.
  - `account.py`: `Account` keeps the access token fresh (long runs outlive the 1-hour JWT), `Accounts` maps user id → account in memory, `RunRecorder` saves a run and its leads; database errors are logged and never stop a run.
  - `auth.py`: `/api/auth/{login,logout,me}` and a `before_request` guard. Everything under `/api/` except `/api/auth/*` returns 401 without a session; `/classic` redirects to `/`. The Flask session cookie (HttpOnly, SameSite=Lax, 30 days, key from `LEADBOMBING_SECRET_KEY` or `user_path()/secret_key`) holds the user id and refresh token, so a server restart restores the login.
  - `account_api.py`: `/api/account/settings` (GET/POST, the UI form and export path), `/api/account/runs`, `/api/account/leads`.
  - Tables (`supabase/migrations/`): `user_settings`, `runs`, `leads` (PK `user_id, sphere, firm_id`; `summary` is the table row, `card` is `lead`/`row`/`business`). Hero photos stay on disk; export still replays only the current run's `raw`.
- Lead API routes live in two `register(app, load_cities)` modules: `leads_api.py` adds `/api/leads/*`, and `classic_api.py` adds the legacy dashboard's `/api/{start,status,results,download,history,…}` (`job.py` `ParseJob`, `history.py`).
- `logs.py` `ListLogHandler` feeds both jobs' live logs.
- `leads_job.py` `LeadsJob`: one run at a time on a background thread. For each selected city it builds a 2GIS search URL, runs the parser into a `LeadsWriter` staging base under `user_path(is_config=False)/runs/<timestamp>` (earlier runs are wiped), and collects events. The UI polls `/api/leads/status?cursor=N`. `export(target, slugs)` replays `raw` into the chosen folder and refuses a folder whose `outreach.csv` header belongs to another sphere.
- Frontend: plain static files with no build step. Alpine.js and Motion are vendored in `static/app/vendor/`. Logic lives in `app.js`, layout in `index.html`, styles in `app.css`. `sw.js` is a network-first service worker that caches the shell. Bump `CACHE` in `sw.js` when the shell file list changes.
- `pick-folder` opens the native macOS folder dialog through `osascript`. Other platforms must type a path.

## Tests to keep green
Golden tests compare output byte for byte against `tests/fixtures/*_golden/`. A missing golden is recorded on the first run and that test is skipped. Re-record only when a format change is intended and approved.
- `test_leads_golden.py` and `test_template_golden.py`: bathhouse and template-sphere (free search) leads output, with a fixed date of 2026-11-16 and a fake hero download.
- `test_writers_golden.py`: CSV (plain and clean), JSON and HTML writers on `catalog_items.json`. That fixture is `bani_items.json` with the fields the catalog models require; the leads fixture is too thin for the writers.
- `test_leads_api.py`, `test_dashboard_api.py`, `test_cli.py`: the leads API, the classic dashboard API and the CLI, each with a `FakeParser` replaying fixtures.
- `test_spheres.py`, `test_leads.py`, `test_demo.py`, `test_web_logs.py`: unit tests.
- `test_auth.py`, `test_account_api.py`: login, guard and account data with `tests/fake_store.py` (`FakeStore`, `login(client)`); API test clients must log in.
- `test_supabase_store.py`: `SupabaseStore` against the local Supabase; skipped when it isn't running. It cleans up its rows.
