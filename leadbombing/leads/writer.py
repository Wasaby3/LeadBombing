"""`-f leads`: write firms of a sphere into a leads base folder (leads.json, outreach.csv, tenants/<slug>/)."""
from __future__ import annotations

import csv
import json
import re
import urllib.request
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any, Callable, Optional

from ..logger import logger
from ..parser.exceptions import ParserException
from . import firm
from .booking import BOOKING_EXPR, assess
from .contacts import contact_book
from .prices import PRICES_EXPR
from .spheres import BaniSphere
from .text import slugify, unique

KEEP = ('Статус', 'Руководитель')  # filled by hand, never overwritten
CARD_KEYS = ('lead', 'row', 'business', 'contacts', 'legal', 'assessment')  # what the web app keeps of a `lead` event
# The prices tab page also has the firm's «Забронировать» button: both come from one request.
FIRM_STATE_EXPR = '({prices: %s, booking: %s})' % (PRICES_EXPR, BOOKING_EXPR)


class RunCancelled(Exception):
    """The run was stopped by the user while a firm was being processed."""


def firm_id_of(url: str) -> str:
    m = re.search(r'/firm/(\d+)', url or '')
    return m.group(1) if m else ''


def card_details(item: dict, sphere: Any) -> dict[str, Any]:
    """Lead card details that are not exported: every contact with its label, the legal entity, the ИП owner."""
    short = firm.short_name(item)
    legal = firm.legal_name(item, short) or ''
    return {'contacts': contact_book(item, sphere.contact_label),
            'legal': {'name': legal if legal != short else '', 'owner': firm.owner_of_ip(legal)}}


class LeadsWriter:
    """Not a FileWriter: the output path is a folder, and it filters records itself.

    `sphere` decides filters and the record layout (default: the original bathhouse template).
    `on_event` gets {'type': 'lead' | 'skip', ...} for live progress. Every accepted firm is kept in
    `raw` (item, prices, hero bytes) so it can be replayed into another base with `add()`.
    """

    def __init__(self, base_dir: str, refresh: bool = False, sphere: Any = None,
                 on_event: Optional[Callable[[dict], None]] = None) -> None:
        self._base = Path(base_dir).expanduser()
        self._refresh = refresh
        self.sphere = sphere or BaniSphere()
        self.on_event = on_event
        self.raw: list[dict] = []
        # Set by MainParser: (page path, JS expression over its initialState `s`) -> value.
        self.fetch_state: Optional[Callable[[str, str], Any]] = None
        # Set by the web app: True once the user stopped the run; the firm in progress is then not counted.
        self.cancelled: Callable[[], bool] = lambda: False
        self._resumed_ids: frozenset[str] = frozenset()

    def __enter__(self) -> LeadsWriter:
        (self._base / 'tenants').mkdir(parents=True, exist_ok=True)
        leads_path = self._base / 'leads.json'
        self._leads: list[dict] = json.loads(leads_path.read_text('utf-8')) if leads_path.exists() else []
        out_path = self._base / 'outreach.csv'
        self._rows: list[dict] = []
        if out_path.exists():
            with out_path.open(encoding='utf-8-sig', newline='') as f:
                self._rows = list(csv.DictReader(f))
        self._seen: set[str] = set()
        self._seen_keys: set[tuple[str, str]] = set()
        self._skipped: Counter[str] = Counter()
        self._errors: list[str] = []
        self._added: list[str] = []
        self._updated: list[str] = []
        self._from_prices = self._stub = 0
        return self

    def __exit__(self, *exc: Any) -> None:
        logger.info('Лиды: собрано %d (добавлено %d, обновлено %d), отсеяно %d.',
                    len(self._added) + len(self._updated), len(self._added), len(self._updated),
                    sum(self._skipped.values()))
        for reason, n in self._skipped.most_common():
            logger.info('  отсеяно — %s: %d', reason, n)
        with_prices, without = self.sphere.from_prices_label
        logger.info(f'{with_prices}: %d, {without}: %d.', self._from_prices, self._stub)
        logger.info('Добавлены: %s', ', '.join(self._added) or '—')
        logger.info('Обновлены: %s', ', '.join(self._updated) or '—')
        for e in self._errors:
            logger.info('  ошибка: %s', e)

    @property
    def summary(self) -> dict[str, Any]:
        return {'added': len(self._added), 'updated': len(self._updated),
                'skipped': dict(self._skipped.most_common()), 'errors': list(self._errors)}

    def write(self, catalog_doc: Any) -> None:
        try:
            item = catalog_doc['result']['items'][0]
        except (KeyError, IndexError, TypeError):
            self._skip('нет данных')
            return
        name = item.get('name') or item.get('id', '?')
        if self.cancelled():
            raise RunCancelled()
        try:
            self._process(item)
        except ParserException:
            raise  # captcha / block: stop the run
        except Exception as e:  # one bad firm must not stop the run
            if self.cancelled():  # the browser was closed under it: fetch this firm again on resume
                self._forget(item)
                raise RunCancelled() from e
            self._errors.append(f'{name}: {e!r}')
            self._skip('ошибка обработки', name)

    def mark_resume(self) -> None:
        """A resumed run skips the firms seen so far without fetching them again (see `skip_firm`)."""
        self._resumed_ids = frozenset(self._seen)

    def skip_firm(self, firm_id: str) -> bool:
        """Asked by MainParser before fetching a firm: True for firms done before the run was resumed."""
        return firm_id in self._resumed_ids

    def _forget(self, item: dict) -> None:
        self._seen.discard(firm.firm_id(item))
        self._seen_keys.discard((firm.short_name(item).lower(), (item.get('address_name') or '').lower()))

    def add(self, item: dict, prices: Optional[dict], hero: Optional[bytes], slug: Optional[str] = None) -> None:
        """Store an already filtered firm (e.g. replayed from another run); known firms are updated.
        `slug` (a saved lead's) names its tenant folder instead of one made from the name."""
        firm_id = firm.firm_id(item)
        if firm_id in self._seen:
            return
        self._seen.add(firm_id)
        self._store(item, prices, hero, self._known(firm_id), slug=slug)

    def slug_owner(self, slug: str) -> Optional[str]:
        """Firm id of the lead with `slug` in this base, None when the slug is free."""
        lead = next((lead for lead in self._leads if lead.get('slug') == slug), None)
        return firm_id_of(lead.get('source', '')) if lead else None

    def _skip(self, reason: str, name: Optional[str] = None) -> None:
        self._skipped[reason] += 1
        if self.on_event:
            self.on_event({'type': 'skip', 'reason': reason, 'name': name})

    def _known(self, firm_id: str) -> Optional[dict]:
        return next((lead for lead in self._leads if firm_id_of(lead.get('source', '')) == firm_id), None)

    def _process(self, item: dict) -> None:
        firm_id = firm.firm_id(item)
        short = firm.short_name(item)
        key = (short.lower(), (item.get('address_name') or '').lower())
        if firm_id in self._seen or key in self._seen_keys:
            return self._skip('дубль', short)
        self._seen.add(firm_id)
        self._seen_keys.add(key)

        reason = self.sphere.filter_reason(item)
        if reason:
            return self._skip(reason, short)
        known = self._known(firm_id)
        if known and not self._refresh:
            return self._skip('уже в базе (кэш, --writer.refresh yes — обновить)', short)

        state: dict = {}
        if self.fetch_state:
            fid = json.dumps(firm_id)
            state = self.fetch_state(f'/firm/{firm_id}/tab/prices', FIRM_STATE_EXPR % (fid, fid)) or {}
        prices, booking = state.get('prices'), state.get('booking')
        hero = self._download_hero(item)
        slug = self._store(item, prices, hero, known, booking)
        self.raw.append({'item': item, 'prices': prices, 'booking': booking, 'hero': hero, 'slug': slug})

    def _store(self, item: dict, prices: Optional[dict], hero: Optional[bytes], known: Optional[dict],
               booking: Optional[list] = None, slug: Optional[str] = None) -> str:
        firm_id = firm.firm_id(item)
        short = firm.short_name(item)
        prefix = self.sphere.slug_prefix
        taken = {lead['slug'] for lead in self._leads if lead is not known}
        if not slug:
            slug = known['slug'] if known else unique(slugify(short) or f'{prefix}-{firm_id[-6:]}', taken)
            if len(slug) < 3:
                slug = unique(f'{prefix}-{slug}', taken)
        elif known and known['slug'] != slug:
            logger.warning('%s: папка tenants/%s теперь tenants/%s, старая осталась', short, known['slug'], slug)
        folder = self._base / 'tenants' / slug
        if hero:
            (folder / 'images').mkdir(parents=True, exist_ok=True)
            (folder / 'images' / 'hero.jpg').write_bytes(hero)
        result = self.sphere.build(item, prices, slug, bool(hero), date.today())

        folder.mkdir(parents=True, exist_ok=True)
        (folder / 'business.json').write_text(
            json.dumps(result['business'], ensure_ascii=False, indent=2) + '\n', 'utf-8')
        self._merge(result, known)
        (self._updated if known else self._added).append(f'tenants/{slug}')
        if result['from_prices']:
            self._from_prices += 1
        else:
            self._stub += 1
        self._save()
        logger.info('Лид: %s → tenants/%s', short, slug)
        if self.on_event:
            self.on_event({'type': 'lead', 'slug': slug, 'updated': bool(known), **result,
                           **card_details(item, self.sphere), 'assessment': assess(item, booking)})
        return slug

    def _download_hero(self, item: dict) -> Optional[bytes]:
        url = firm.hero_url_of(item)
        if not url:
            return None
        try:
            with urllib.request.urlopen(url, timeout=20) as r:
                return r.read()
        except Exception as e:
            if getattr(e, 'code', None) in (403, 429):
                raise ParserException(f'Фото 2ГИС отвечает {e.code} — похоже на блокировку, прогон остановлен.')
            logger.warning('hero не скачан (%s): %r', url, e)
            return None

    def _merge(self, result: dict, known: Optional[dict]) -> None:
        lead, row = result['lead'], result['row']
        if known:
            lead['status'] = known.get('status', lead['status'])
            self._leads[self._leads.index(known)] = lead
        else:
            self._leads.append(lead)
        old = next((r for r in self._rows if r.get('2ГИС') == row['2ГИС']), None)
        if old:
            row.update({k: old[k] for k in KEEP if old.get(k)})
            self._rows[self._rows.index(old)] = row
        else:
            self._rows.append(row)

    def _save(self) -> None:
        (self._base / 'leads.json').write_text(json.dumps(self._leads, ensure_ascii=False, indent=2) + '\n', 'utf-8')
        with (self._base / 'outreach.csv').open('w', encoding='utf-8-sig', newline='') as f:
            w = csv.DictWriter(f, fieldnames=self.sphere.columns, extrasaction='ignore')
            w.writeheader()
            w.writerows(self._rows)
