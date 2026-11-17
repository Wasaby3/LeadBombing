"""Background leads run for the PWA: parse a 2GIS search into a staging base, stream leads, export on demand."""
from __future__ import annotations

import csv
import logging
import shutil
import threading
import urllib.parse
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


def search_url(city: dict, query: str) -> str:
    return f"https://2gis.{city.get('domain') or 'ru'}/{city['code']}/search/{urllib.parse.quote(query.strip())}"


def lead_summary(event: dict) -> dict[str, Any]:
    """Compact row for the live table."""
    lead, row = event['lead'], event['row']
    names = [h['name'] for h in lead.get('halls_from_2gis') or lead.get('services_from_2gis') or []]
    return {'slug': event['slug'], 'name': row.get('Баня') or row.get('Название'), 'district': lead.get('district'),
            'rating': lead.get('rating'), 'reviews': lead.get('reviews'), 'channel': row.get('Канал'),
            'write_here': row.get('Писать сюда'), 'has_photo': bool(lead['photos'].get('hero_url')),
            'prices': names, 'updated': event.get('updated', False)}


class LeadsJob:
    """One leads run at a time; results live in a staging base until exported."""

    def __init__(self, runs_dir: Optional[Path] = None) -> None:
        self._runs_dir = runs_dir or user_path(is_config=False) / 'runs'
        self._lock = threading.Lock()
        self._parser: Any = None
        self._cancelled = False
        self.status = 'idle'  # idle | running | done | stopped | error
        self.error: Optional[str] = None
        self.events: list[dict] = []
        self.logs: list[str] = []
        self.results: dict[str, dict] = {}
        self.writer: Optional[LeadsWriter] = None
        self.staging: Optional[Path] = None
        self.query = ''
        self._recorder: Optional[RunRecorder] = None

    @property
    def running(self) -> bool:
        return self.status == 'running'

    def start(self, sphere_id: str, cities: list[dict], query: str, limit: int, headless: bool = True,
              recorder: Optional[RunRecorder] = None) -> None:
        """Search `query` in every city (the bathhouse template is fixed to Moscow); `limit` firms per city.

        `recorder` saves the run and its leads into the user's account.
        """
        sphere = get_sphere(sphere_id, cities, query)
        with self._lock:
            if self.running:
                raise RuntimeError('Поиск уже идёт')
            shutil.rmtree(self._runs_dir, ignore_errors=True)  # keep only the current run
            self.staging = self._runs_dir / datetime.now().strftime('%Y%m%d-%H%M%S')
            self.status, self.error, self._cancelled = 'running', None, False
            self.events, self.logs, self.results = [], [], {}
            self.query = query.strip() or sphere.query
            self._recorder = recorder
            self.writer = LeadsWriter(str(self.staging), sphere=sphere, on_event=self._on_event)
        config = Configuration()
        config.chrome.headless = headless
        config.parser.max_records = max(1, int(limit))
        urls = [search_url(city, self.query) for city in sphere.cities]
        run_info = (sphere_id, self.query, [city['code'] for city in sphere.cities], config.parser.max_records)
        threading.Thread(target=self._run, args=(config, urls, run_info), daemon=True).start()

    def stop(self) -> None:
        with self._lock:
            self._cancelled = True
            if self._parser:
                try:
                    self._parser.close()
                except Exception as e:  # browser may already be gone
                    logger.debug('Закрытие браузера: %r', e)

    def _on_event(self, event: dict) -> None:
        if event['type'] == 'lead':
            self.results[event['slug']] = {k: event[k] for k in CARD_KEYS}
            summary = {'type': 'lead', **lead_summary(event)}
            self.events.append(summary)
            if self._recorder:
                self._recorder.lead(event, summary)
        else:
            self.events.append(event)

    def _run(self, config: Configuration, urls: list[str], run_info: tuple) -> None:
        handler = ListLogHandler(self.logs, '%(asctime)s %(message)s', _MAX_LOG_LINES)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        if self._recorder:
            self._recorder.started(*run_info)
        try:
            assert self.writer is not None
            with self.writer:
                for url in urls:
                    if self._cancelled:
                        break
                    logger.info('Поиск: %s', urllib.parse.unquote(url))
                    self._parser = get_parser(url, chrome_options=config.chrome, parser_options=config.parser)
                    with self._parser:
                        if not self._cancelled:
                            self._parser.parse(self.writer)
            self.status = 'stopped' if self._cancelled else 'done'
        except Exception as e:
            if self._cancelled:
                self.status = 'stopped'
            else:
                self.error, self.status = str(e), 'error'
                logger.error('Поиск прерван: %s', e)
        finally:
            self._parser = None
            if self._recorder:
                skipped = sum(1 for e in self.events if e['type'] == 'skip')
                self._recorder.finished(self.status, len(self.results), skipped, self.error)
            logger.removeHandler(handler)

    def snapshot(self, cursor: int) -> dict[str, Any]:
        events = self.events[cursor:]
        summary = self.writer.summary if self.writer and hasattr(self.writer, '_skipped') else {}
        return {'status': self.status, 'error': self.error, 'query': self.query,
                'events': events, 'cursor': cursor + len(events), 'summary': summary,
                'log': self.logs[-1] if self.logs else ''}

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
