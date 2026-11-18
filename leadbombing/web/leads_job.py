"""Background leads run for the PWA: parse a 2GIS search into a staging base, stream leads, export on demand.

A run can be stopped at once and resumed from the same city and search results page.
"""
from __future__ import annotations

import csv
import logging
import shutil
import threading
import urllib.parse
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from ..config import Configuration
from ..leads import LeadsWriter
from ..leads.writer import CARD_KEYS
from ..leads.spheres import get_sphere
from ..logger import logger
from ..parser import get_parser
from ..paths import user_path
from .logs import ListLogHandler

if TYPE_CHECKING:
    from .account import RunRecorder

_MAX_LOG_LINES = 2000
_STOP_WAIT_S = 15  # how long a new or resumed run waits for the stopped one to let go of Chrome


def search_url(city: dict, query: str, page: int = 1) -> str:
    url = f"https://2gis.{city.get('domain') or 'ru'}/{city['code']}/search/{urllib.parse.quote(query.strip())}"
    return f'{url}/page/{page}' if page > 1 else url


def lead_summary(event: dict) -> dict[str, Any]:
    """Compact row for the live table."""
    lead, row = event['lead'], event['row']
    names = [h['name'] for h in lead.get('halls_from_2gis') or lead.get('services_from_2gis') or []]
    return {'slug': event['slug'], 'name': row.get('Баня') or row.get('Название'), 'district': lead.get('district'),
            'rating': lead.get('rating'), 'reviews': lead.get('reviews'), 'channel': row.get('Канал'),
            'write_here': row.get('Писать сюда'), 'has_photo': bool(lead['photos'].get('hero_url')),
            'prices': names, 'updated': event.get('updated', False),
            'priority': (event.get('assessment') or {}).get('priority', 0)}  # from the 2GIS card, see leads/booking.py


@dataclass(frozen=True)
class RunPlan:
    """What a run searches: the same plan is continued on resume (only the limit may change)."""
    sphere_id: str
    query: str
    cities: tuple[dict, ...]
    limit: int

    @property
    def params(self) -> dict[str, Any]:
        return {'sphere': self.sphere_id, 'query': self.query,
                'cities': [c['code'] for c in self.cities], 'limit': self.limit}


@dataclass(frozen=True)
class Progress:
    """Where a run is: city index in the plan, search results page, firms written in that city."""
    city: int = 0
    page: int = 1
    done: int = 0


class LeadsJob:
    """One leads run at a time; results live in a staging base until exported."""

    def __init__(self, runs_dir: Optional[Path] = None) -> None:
        self._runs_dir = runs_dir or user_path(is_config=False) / 'runs'
        self._lock = threading.Lock()
        self._cancel = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._parser: Any = None
        self._plan: Optional[RunPlan] = None
        self._progress = Progress()
        self._recorder: Optional[RunRecorder] = None
        self.status = 'idle'  # idle | running | done | stopped | error
        self.error: Optional[str] = None
        self.events: list[dict] = []
        self.logs: list[str] = []
        self.results: dict[str, dict] = {}
        self.writer: Optional[LeadsWriter] = None
        self.staging: Optional[Path] = None
        self.query = ''

    @property
    def running(self) -> bool:
        return self.status == 'running'

    @property
    def busy(self) -> bool:
        """The worker thread is still alive (e.g. finishing the firm in progress after a stop)."""
        return self._thread is not None and self._thread.is_alive()

    @property
    def resumable(self) -> bool:
        return (self.status in ('stopped', 'error') and self._plan is not None and self.writer is not None
                and self._progress.city < len(self._plan.cities))

    def start(self, sphere_id: str, cities: list[dict], query: str, limit: int, headless: bool = True,
              recorder: Optional[RunRecorder] = None) -> None:
        """Search `query` in every city (the bathhouse template is fixed to Moscow); `limit` firms per city.

        `recorder` saves the run and its leads into the user's account.
        """
        sphere = get_sphere(sphere_id, cities, query)
        self._wait_stopped()
        with self._lock:
            if self.running:
                raise RuntimeError('Поиск уже идёт')
            shutil.rmtree(self._runs_dir, ignore_errors=True)  # keep only the current run
            self.staging = self._runs_dir / datetime.now().strftime('%Y%m%d-%H%M%S')
            self.status, self.error = 'running', None
            self._cancel.clear()
            self.events, self.logs, self.results = [], [], {}
            self.query = query.strip() or sphere.query
            self._recorder = recorder
            self._plan = RunPlan(sphere_id, self.query, tuple(sphere.cities), max(1, int(limit)))
            self._progress = Progress()
            self.writer = LeadsWriter(str(self.staging), sphere=sphere, on_event=self._on_event)
            self.writer.cancelled = self._cancel.is_set
            self.writer.__enter__()  # stays open across resumes; closed (summary logged) when each part ends
            self._launch(headless, fresh=True)

    def resume(self, limit: Optional[int] = None, headless: bool = True) -> None:
        """Continue a stopped or failed run from the city and page where it ended; found firms are not repeated."""
        self._wait_stopped()
        with self._lock:
            if self.running:
                raise RuntimeError('Поиск уже идёт')
            if not self.resumable or self._plan is None or self.writer is None:
                raise RuntimeError('Продолжать нечего — начните новый поиск')
            if limit:
                self._plan = replace(self._plan, limit=max(1, int(limit)))
            self.status, self.error = 'running', None
            self._cancel.clear()
            self.writer.mark_resume()
            self._launch(headless, fresh=False)

    def stop(self) -> None:
        """Stop at once: the run is marked stopped right away and Chrome is closed in the background."""
        self._cancel.set()
        with self._lock:
            if self.running:
                self.status = 'stopped'
            parser = self._parser
        if parser:
            threading.Thread(target=_close_quietly, args=(parser,), daemon=True).start()

    def clear(self) -> None:
        """Forget the found leads and the run (staging folder included)."""
        with self._lock:
            if self.running or self.busy:
                raise RuntimeError('Сначала остановите поиск')
            shutil.rmtree(self._runs_dir, ignore_errors=True)
            self.status, self.error, self.query = 'idle', None, ''
            self.events, self.logs, self.results = [], [], {}
            self.writer = self.staging = self._plan = self._recorder = None
            self._progress = Progress()

    def _launch(self, headless: bool, fresh: bool) -> None:
        config = Configuration()
        config.chrome.headless = headless
        self._thread = threading.Thread(target=self._run, args=(config, fresh), daemon=True)
        self._thread.start()

    def _wait_stopped(self) -> None:
        thread = self._thread
        if self.running or thread is None or not thread.is_alive():
            return
        thread.join(_STOP_WAIT_S)
        if thread.is_alive():
            raise RuntimeError('Прошлый поиск ещё останавливается — подождите пару секунд')

    def _on_event(self, event: dict) -> None:
        if event['type'] == 'lead':
            self.results[event['slug']] = {k: event[k] for k in CARD_KEYS}
            summary = {'type': 'lead', **lead_summary(event)}
            self.events.append(summary)
            if self._recorder:
                self._recorder.lead(event, summary)
        else:
            self.events.append(event)

    def _run(self, config: Configuration, fresh: bool) -> None:
        assert self._plan is not None and self.writer is not None
        handler = ListLogHandler(self.logs, '%(asctime)s %(message)s', _MAX_LOG_LINES)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        if fresh and self._recorder:
            plan = self._plan.params
            self._recorder.started(plan['sphere'], plan['query'], plan['cities'], plan['limit'])
        try:
            while self._progress.city < len(self._plan.cities) and not self._cancel.is_set():
                self._run_city(config)
            self.status = 'stopped' if self._cancel.is_set() else 'done'
        except Exception as e:
            if self._cancel.is_set():
                self.status = 'stopped'
            else:
                self.error, self.status = str(e), 'error'
                logger.error('Поиск прерван: %s', e)
        finally:
            self._parser = None
            self.writer.__exit__(None, None, None)
            if self._recorder:
                skipped = sum(1 for e in self.events if e['type'] == 'skip')
                self._recorder.finished(self.status, len(self.results), skipped, self.error)
            logger.removeHandler(handler)

    def _run_city(self, config: Configuration) -> None:
        """Parse the current city from the saved page; on a stop or failure remember where it ended."""
        assert self._plan is not None
        at = self._progress
        remaining = self._plan.limit - at.done
        if remaining <= 0:
            self._progress = Progress(city=at.city + 1)
            return
        url = search_url(self._plan.cities[at.city], self._plan.query, at.page)
        logger.info('Поиск: %s', urllib.parse.unquote(url))
        events_before = len(self.events)
        parser: Any = None

        def stopped_at() -> Progress:
            page = max(at.page, getattr(parser, 'page', at.page) or at.page)
            done = at.done + len(self.events) - events_before  # one event per firm handed to the writer
            return Progress(at.city, page, done)

        try:
            parser = get_parser(url, chrome_options=config.chrome,
                                parser_options=config.parser.model_copy(update={'max_records': remaining}))
            self._parser = parser
            with parser:
                if not self._cancel.is_set():
                    parser.parse(self.writer)
        except BaseException:
            self._progress = stopped_at()
            raise
        self._progress = stopped_at() if self._cancel.is_set() else Progress(city=at.city + 1)

    def snapshot(self, cursor: int) -> dict[str, Any]:
        events = self.events[cursor:]
        summary = self.writer.summary if self.writer and hasattr(self.writer, '_skipped') else {}
        return {'status': self.status, 'error': self.error, 'query': self.query,
                'events': events, 'cursor': cursor + len(events), 'summary': summary,
                'log': self.logs[-1] if self.logs else '', 'busy': self.busy, 'resumable': self.resumable,
                'params': self._plan.params if self._plan else None}

    def picked_raw(self, slugs: Optional[list[str]] = None) -> list[dict]:
        """Collected firms ({item, prices, hero, slug}): all, or only `slugs`."""
        raw = list(self.writer.raw) if self.writer else []
        if slugs is None:
            return raw
        wanted = set(slugs)
        return [r for r in raw if r['slug'] in wanted]

    def export(self, target: Path, slugs: Optional[list[str]] = None) -> dict[str, Any]:
        """Replay collected firms (all, or only `slugs`) into `target`, merging with a base already there."""
        raw = self.picked_raw(slugs)
        if not raw or self.writer is None:
            raise RuntimeError('Нечего выгружать — сначала найдите лиды')
        return export_raw(target, self.writer.sphere, raw)


def _close_quietly(parser: Any) -> None:
    try:
        parser.close()
    except Exception as e:  # browser may already be gone
        logger.debug('Закрытие браузера: %r', e)


def export_raw(target: Path, sphere: Any, raw: list[dict]) -> dict[str, Any]:
    """Replay firms ({item, prices, hero}) into the base at `target`; refuses a base of another sphere."""
    if not raw:
        raise RuntimeError('Нечего выгружать')
    outreach = target / 'outreach.csv'
    if outreach.exists():
        with outreach.open(encoding='utf-8-sig', newline='') as f:
            header = next(csv.reader(f), [])
        if header and header != sphere.columns:
            raise RuntimeError('В этой папке база другой сферы — выберите пустую папку или папку этой сферы')
    with LeadsWriter(str(target), sphere=sphere) as out:
        for r in raw:
            out.add(r['item'], r['prices'], r['hero'])
    return {'path': str(target), 'added': out.summary['added'], 'updated': out.summary['updated']}
