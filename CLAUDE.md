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
- `leads/writer.py` `LeadsWriter`: the output path is a folder, not a file. It dedups by 2GIS firm id and by (name, address). It applies `sphere.filter_reason`, fetches prices through `fetch_state` (which `MainParser` injects), downloads `hero.jpg` (a 403/429 here also aborts the run), and calls `sphere.build`. It merges with an existing `leads.json`/`outreach.csv` and never overwrites the hand-filled `Статус` / `Руководитель`. It emits `lead`/`skip` events through `on_event` (a `lead` event also carries `card_details`: `contacts` and `legal`, card-only, never exported; the web app keeps `CARD_KEYS` of it as the lead card) and keeps every accepted firm in `raw` so the web app can replay it into another folder with `add()`.
- `leads/spheres.py` handles sphere selection:
  - `BaniSphere`: the original bathhouse template. Moscow only, `BANI_COLUMNS` (`Баня`, `Залы`), builds with `leads/build.py`. Its output must stay byte-identical; `tests/test_leads_golden.py` checks it against `tests/fixtures/bani_golden/`.
  - `TemplateSphere` + `Template` entries in `TEMPLATES` (auto, beauty, dental): multi-city, builds with `leads/generic.py` using `generic.COLUMNS` (`Название`, `Услуги`, `services` instead of `halls`). To add a sphere, add a `Template`.
  - `custom`: free search. The user's query is used as-is, there's no rubric filter, and the output format matches the templates.
- Shared by both builders (put new cross-sphere code here, not in `build.py`):
  - `firm.py`: reads profile facts (id, short name, district, photo, legal name).
  - `contacts.py`: `contact_book` (every 2GIS contact with its label and role: owner/general/booking/department; the
    lead card shows it), `contacts_of`, `reach_of` (channel by role: owner first, then general, booking, other
    departments; `public_*` for `business.json` never the owner's number), and the outreach/lead/business contact
    blocks. Without labels the choice is the old channel order, so goldens don't change.
  - `firm.py` also has `owner_of_ip` (owner's full name from «ИП …»).
  - `prices.py`: the prices-tab JS, price parsing, and the «old prices» threshold.
  - `booking.py`: lead priority 0–5 from the 2GIS card (own site + where the «Забронировать» button leads). The
    button is an ad action in `initialState.data.searchContext`, read by `LeadsWriter` in the same prices-tab request
    (`FIRM_STATE_EXPR`); the result is `assessment` in the `lead` event and card, the raw actions are `raw.booking`.
    Never exported. A lead new to a folder starts with this priority and its note as the comment.
  - `demo.py`: shared pieces of `business.json`/`leads.json` (legal, policy, theme, wordmark).
  - `text.py`: phones, transliteration, slugs.
  - `build.py` keeps the bathhouse-only parts (halls, schedule) plus `schedule_of`, which `generic.py` also uses.
- Dict key order is part of the output format: build `business`/`lead` dicts in their existing order.

### Web app (`web/`)
- `server.py` `create_app(store=None, secret_key=None)`: Flask app setup and static pages only. `/search`, `/leads` (the «Сохранённые лиды» page, saved lead folders; `/saved` redirects there), `/clients`, `/profile`, `/settings` and `/docs` (the in-app «Документация», same text as `docs/LOGIC.md`; keep both in sync) serve the leads SPA from `web/static/app/` (`/` redirects to `/search`; `app.js` picks the page from the URL, side menu in `index.html`, theme choice in localStorage), and `/classic` serves the legacy dashboard page. Tests pass a `FakeStore` and a fixed key.
- Accounts (Supabase):
  - `supabase.py` `SupabaseStore`: thin `requests` client. Password login via Auth, account tables via PostgREST with the user's JWT, so RLS limits every row to its owner. Errors are `StoreError` / `InvalidCredentials` / `SessionExpired` with Russian messages.
  - `account.py`: `Account` keeps the access token fresh (long runs outlive the 1-hour JWT), `Accounts` maps user id → account in memory, `RunRecorder` saves a run and its leads; database errors are logged and never stop a run.
  - `auth.py`: `/api/auth/{login,logout,me}` and a `before_request` guard. Everything under `/api/` except `/api/auth/*` returns 401 without a session; `/classic` redirects to `/`. The Flask session cookie (HttpOnly, SameSite=Lax, 30 days, key from `LEADBOMBING_SECRET_KEY` or `user_path()/secret_key`) holds the user id and refresh token, so a server restart restores the login.
  - `account_api.py`: `/api/account/settings` (GET/POST, the UI form and export path), `/api/account/runs`, `/api/account/leads`.
  - Tables (`supabase/migrations/`): `user_settings`, `runs`, `leads` (PK `user_id, sphere, firm_id`; `summary` is the table row, `card` is `lead`/`row`/`business`). Hero photos stay on disk; export still replays only the current run's `raw`.
  - Saved lead folders («Сохранённые лиды»): `folders`, `folder_leads` (PK `folder_id, slug`; snapshot `summary`/`card`/`raw` plus the work on the lead: `status`, `priority`, `comment`, `contacted`, `demo_url`, `demo_source` (`manual` typed by hand, `auto` from «Проработать лиды»), `worked_at`). `folders_api.py` serves them (`PATCH`/`DELETE /api/folders/<id>/item/<slug>`); `lead_crm.py` `parse_patch` validates a change. Re-saving a lead upserts only the snapshot columns, so the work survives. These fields never go into export files.
  - A folder slug is the lead's demo name: `tenants/<slug>/` in an export and the end of its demo URL. `folder_slugs.py` maps run slugs on save (a firm already in the folder keeps its slug, a new one gets a free one, so chains from different runs never overwrite each other; `store.folder_firms`), and the folder export calls `export_raw(..., keep_slugs=True)`, so `LeadsWriter.add(slug=…)` writes that exact folder and refuses a slug another firm has in the target. The search page export still makes names afresh.
  - «Проработать лиды» (`work_api.py`, `POST /api/folders/<id>/work {base_url, slugs?}`, UI in `work.js`): demo URL `base_url/<slug>` (`auto`) for the folder's leads, not clients or `manual` links, through the SQL function `fill_demo_urls`; `folders.demo_base_url`/`demo_filled_at` remember the base URL so the window opens with it. `lead_crm.parse_base_url` validates it. Further analysis goes here later.
  - Clients («Клиенты», `/clients`): a folder lead with `client_status` (`ok`/`question`/`bug`, null for a lead) and `client_since`. `clients_api.py` adds `GET /api/clients` (all folders) and `POST /api/folders/<id>/item/<slug>/client` («Перевести в клиенты»: status `bought`, client status `ok`). A client stays in `folder_leads`, so its card, photo, PATCH and DELETE use the folder item routes, but the store leaves clients out of a folder's list, count, export and «Проработать лиды» (`_ONLY_LEADS`).
- Lead API routes live in two `register(app, load_cities)` modules: `leads_api.py` adds `/api/leads/*`, and `classic_api.py` adds the legacy dashboard's `/api/{start,status,results,download,history,…}` (`job.py` `ParseJob`, `history.py`).
- `logs.py` `ListLogHandler` feeds both jobs' live logs.
- `leads_job.py` `LeadsJob`: one run at a time on a background thread. For each selected city it builds a 2GIS search URL, runs the parser into a `LeadsWriter` staging base under `user_path(is_config=False)/runs/<timestamp>` (earlier runs are wiped), and collects events. The UI polls `/api/leads/status?cursor=N` (also `busy`, `resumable`, `params`). `stop()` marks the run stopped at once and closes Chrome on a side thread; `resume()` (`/api/leads/resume`) continues from the saved `Progress` (city, `MainParser.page`, firms done) with the same writer, which skips firms seen before via `skip_firm`; `clear()` (`/api/leads/clear`) wipes the run. `LeadsWriter.cancelled` turns an error during a stop into `RunCancelled` instead of a skipped firm. The search form is saved (localStorage and account `form`) only when a search is started or resumed (`searchForm` in `app.js`); unsent edits are reverted when the page changes or reloads. `export(target, slugs)` replays `raw` into the chosen folder and refuses a folder whose `outreach.csv` header belongs to another sphere.
- Frontend: plain static files with no build step. Alpine.js, Motion and the Lucide icon sprite (`icons.svg`) are vendored in `static/app/vendor/`. Logic lives in `app.js` (the work on a saved lead or client — statuses, priority, comment, demo, «Перевести в клиенты» — in `crm.js`, «Проработать лиды» in `work.js`, both merged into the same Alpine component), layout in `index.html`, styles in `app.css`. `sw.js` is a network-first service worker that caches the shell. Bump `CACHE` in `sw.js` when the shell file list or the icon sprite changes.
- `pick-folder` opens the native macOS folder dialog through `osascript`. Other platforms must type a path.

## UI work (any change in `web/static/app/`)

Every new screen, window, button or text follows the design system; read these before touching the UI:
- `DESIGN.md` (repo root, Impeccable/DESIGN.md format): tokens, typography, layout zones, shapes, the component
  classes in `app.css` and the JS helpers in `app.js` (`WINDOWS`/`trapTab` focus handling, `showFormError`, `notify`,
  `plural`/`leadsWord`, `formatDate`, `radioKeys`, `toggleMore`, `setTheme`). Build from these; add a token or class
  only when it repeats three times with one meaning, and define a new color token in all three theme blocks.
- `docs/UX-RULES.md`: button levels (one primary per area, danger only for irreversible actions, channel colors only
  as labels), window types (drawer / dialog / toast / inline error), screen zones, the copy glossary (verb + object,
  Russian sentence case), Lucide icons (local sprite only, one icon per action, icon + text for main actions), theme,
  states, and §8, the checklist for a new feature.
- `docs/UX-AUDIT.md` records past decisions; `docs/ux/before|after/` hold reference screenshots.

Check a UI change before committing: Playwright screenshots at 1440 and 375 in light and dark (no horizontal scroll
at 375), `/web-design-guidelines` on the changed `app/` files and Impeccable `audit` (detector:
`.claude/skills/impeccable/scripts/impeccable detect --json leadbombing/web/static/app/index.html`) with no new
findings, Impeccable `critique` for a new screen and `polish` at the end. Keep the in-app «Документация» and
`docs/LOGIC.md` in sync.

## Tests to keep green
Golden tests compare output byte for byte against `tests/fixtures/*_golden/`. A missing golden is recorded on the first run and that test is skipped. Re-record only when a format change is intended and approved.
- `test_leads_golden.py` and `test_template_golden.py`: bathhouse and template-sphere (free search) leads output, with a fixed date of 2026-11-16 and a fake hero download.
- `test_writers_golden.py`: CSV (plain and clean), JSON and HTML writers on `catalog_items.json`. That fixture is `bani_items.json` with the fields the catalog models require; the leads fixture is too thin for the writers.
- `test_leads_api.py`, `test_dashboard_api.py`, `test_cli.py`: the leads API, the classic dashboard API and the CLI, each with a `FakeParser` replaying fixtures.
- `test_spheres.py`, `test_leads.py`, `test_demo.py`, `test_web_logs.py`, `test_lead_crm.py`, `test_booking.py`: unit tests.
- `test_work_api.py`: «Проработать лиды»: demo URL = base URL + folder slug, manual links and clients kept, picked leads only, the folder remembers the base URL.
- `test_leads_resume.py`: instant stop, resume from the same city and page without repeats, clear (a paged `PagedParser` fake).
- `test_clients_api.py`: clients: a lead made a client leaves its folder's list, count and export, shows in `/api/clients`, keeps its client status on re-save.
- `test_folders_api.py`: saved lead folders («Сохранённые лиды»): save, card, export, the work on a lead (status, priority, comment,
  contacted, demo URL), re-save keeps it, delete with the photo; same-name firms from different runs get their own slugs, export writes `tenants/` by the folder slug and refuses a slug taken by another firm.
- `test_auth.py`, `test_account_api.py`: login, guard and account data with `tests/fake_store.py` (`FakeStore`, `login(client)`); API test clients must log in.
- `test_supabase_store.py`: `SupabaseStore` against the local Supabase; skipped when it isn't running. It cleans up its rows.
