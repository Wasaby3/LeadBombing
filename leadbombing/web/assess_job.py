"""TEMP: one-off assessment of leads saved before the 2GIS «Забронировать» button was collected.

New leads get their assessment while the search runs (leads/booking.py, LeadsWriter). Leads saved earlier have none,
so this job opens Chrome on 2GIS, reads each such lead's button (one request per lead, the prices tab) and saves the
assessment into the card; priority and comment are set only when the user left them empty. Started by the
«Оценить лиды» button on «Сохранённые лиды».

To remove once old folders are assessed: this file, `tests/test_assess_job.py`, its `register` call in server.py,
the TEMP store methods (`folder_assess_rows`, `set_assessment`) in supabase.py and tests/fake_store.py, and the TEMP
parts of index.html / app.js (the button, `assess*` state and methods).
"""
from __future__ import annotations

import json
import threading
from typing import Any, Callable, Optional

from ..chrome import ChromeRemote
from ..config import Configuration
from ..leads.booking import BOOKING_EXPR, assess
from ..leads.firm import firm_id
from ..logger import logger
from ..parser.exceptions import ParserException
from ..parser.parsers.main import fetch_state
from .supabase import SessionExpired, StoreError

START_URL = 'https://2gis.ru/%s'  # a city page: the bare domain redirects after load and breaks requests
DEFAULT_CITY = 'moscow'
PAUSE_S = 2.0  # between leads: back-to-back requests get a captcha page from 2GIS after a couple of firms
Fetch = Callable[[str, str], Any]


def open_cards(headless: bool, city: str) -> tuple[Fetch, Callable[[], None]]:
    """Chrome on a 2GIS city page: (fetch(path, expr) over a page's initialState, close)."""
    config = Configuration()
    config.chrome.headless = headless
    remote = ChromeRemote(chrome_options=config.chrome, response_patterns=[])
    remote.start()
    try:
        remote.navigate(START_URL % city, referer='https://google.com', timeout=120)
    except Exception:
        remote.stop()
        raise
    return (lambda path, expr: fetch_state(remote, path, expr)), remote.stop


def needs_assessment(card: dict) -> bool:
    """No button data yet: saved before it was collected (or 2GIS gave none last time)."""
    return not (card.get('assessment') or {}).get('button')


def assessed_fields(row: dict, actions: Optional[list]) -> dict:
    """Database fields for a lead: the card with its assessment, plus priority and comment if they are empty."""
    result = assess(row['item'] or {}, actions)
    fields: dict = {'card': {**row['card'], 'assessment': result}}
    if result['priority'] and not row['priority']:
        fields['priority'] = result['priority']
    if result['note'] and not (row['comment'] or '').strip():
        fields['comment'] = result['note']
    return fields


class AssessJob:
    """One assessment at a time on a background thread; the UI polls `snapshot()`."""

    def __init__(self, search_running: Callable[[], bool]) -> None:
        self._search_running = search_running
        self._lock = threading.Lock()
        self._cancel = threading.Event()
        self.status = 'idle'  # idle | running | done | stopped | error
        self.error: Optional[str] = None
        self.folder_id: Optional[int] = None
        self.total = self.done = self.errors = 0

    def start(self, account: Any, folder_id: int, headless: bool) -> None:
        with self._lock:
            if self.status == 'running':
                raise RuntimeError('Оценка уже идёт — дождитесь конца или остановите её')
            if self._search_running():
                raise RuntimeError('Идёт поиск лидов — оцените лиды после него')
            self.status, self.error, self.folder_id = 'running', None, folder_id
            self.total = self.done = self.errors = 0
            self._cancel.clear()
        threading.Thread(target=self._run, args=(account, folder_id, headless), daemon=True).start()

    def stop(self) -> None:
        self._cancel.set()

    def snapshot(self) -> dict[str, Any]:
        return {'status': self.status, 'error': self.error, 'folder_id': self.folder_id,
                'total': self.total, 'done': self.done, 'errors': self.errors}

    def _run(self, account: Any, folder_id: int, headless: bool) -> None:
        close: Optional[Callable[[], None]] = None
        try:
            rows = [r for r in account.store.folder_assess_rows(account.token(), folder_id)
                    if needs_assessment(r['card'])]
            self.total = len(rows)
            if rows:
                fetch, close = open_cards(headless, (rows[0]['item'] or {}).get('city_alias') or DEFAULT_CITY)
                self._assess_rows(account, folder_id, rows, fetch)
            self.status = 'stopped' if self._cancel.is_set() else 'done'
        except (ParserException, StoreError, SessionExpired) as e:
            self.status, self.error = 'error', str(e)
        except Exception as e:  # Chrome failed to start or the tab died
            logger.error('Оценка лидов прервана: %r', e)
            self.status, self.error = 'error', 'Не удалось открыть 2ГИС в Chrome — попробуйте ещё раз'
        finally:
            if close:
                close()
        logger.info('Оценка лидов: %s, оценено %d из %d', self.status, self.done, self.total)

    def _assess_rows(self, account: Any, folder_id: int, rows: list[dict], fetch: Fetch) -> None:
        for i, row in enumerate(rows):
            if self._cancel.is_set() or (i and self._cancel.wait(PAUSE_S)):
                return
            fid = firm_id(row['item'] or {'id': ''})
            try:
                actions = fetch(f'/firm/{fid}/tab/prices', BOOKING_EXPR % json.dumps(fid)) if fid else None
            except ParserException:
                raise  # captcha / block: stop
            except Exception as e:  # one bad lead must not stop the rest
                logger.error('Оценка %s: %r', row['slug'], e)
                self.errors += 1
                continue
            account.store.set_assessment(account.token(), folder_id, row['slug'], assessed_fields(row, actions))
            self.done += 1


def register(app: Any, search_running: Callable[[], bool]) -> AssessJob:
    from flask import g, jsonify, request

    job = AssessJob(search_running)

    def fail(message: str, code: int = 400):
        return jsonify({'ok': False, 'error': message}), code

    @app.route('/api/folders/<int:folder_id>/assess', methods=['POST'])
    def folders_assess(folder_id: int):
        data = request.get_json(silent=True) or {}
        try:
            if not g.account.store.get_folder(g.account.token(), folder_id):
                return fail('Папка не найдена', 404)
            job.start(g.account, folder_id, headless=bool(data.get('headless', True)))
        except SessionExpired as e:
            return fail(str(e), 401)
        except StoreError as e:
            return fail(str(e), 503)
        except RuntimeError as e:
            return fail(str(e), 409)
        return jsonify({'ok': True, **job.snapshot()})

    @app.route('/api/folders/assess/status')
    def folders_assess_status():
        return jsonify({'ok': True, **job.snapshot()})

    @app.route('/api/folders/assess/stop', methods=['POST'])
    def folders_assess_stop():
        job.stop()
        return jsonify({'ok': True, **job.snapshot()})

    return job
