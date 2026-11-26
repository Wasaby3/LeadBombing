"""Work on a saved lead (the «Сохранённые лиды» page) or a client («Клиенты»): status, priority, comment, contacted
channels, the demo app and, for a client, its client status.

`parse_patch` checks a change from the UI before it goes to the database. A status is one of the user's own
lead_statuses (see lead_statuses.py and statuses_api.py), so `parse_patch` needs the caller's current set of valid
ids whenever `status` may be in the patch. The demo app's `demo_source` is `manual` for a URL typed by hand and
`auto` for one put by «Проработать лиды» (base URL from `parse_base_url` plus the lead's slug, written by the
store's `fill_demo_urls`).
A lead becomes a client only through the store's `make_client` (status «Купил», client status «Всё ок»);
`client_status` is None for a lead.
"""
from __future__ import annotations

import re
from typing import AbstractSet, Any, Callable, Optional

NOT_WRITTEN = 'not_written'  # «Ещё не написал»: any other status counts in «Написали» (lead_statuses.PROTECTED_IDS)
CLIENT_STATUSES = ('ok', 'question', 'bug')  # «Всё ок», «Есть вопрос», «Срочный баг»
MAX_PRIORITY = 5  # 0 not set, 1 very low … 5 very high (see leads/booking.py for the automatic one)
MAX_COMMENT = 5000
MAX_MESSAGE = 5000  # a folder's «Общее сообщение» (folders.message_template)
MAX_URL = 2000
MAX_SLUG = 60  # a folder slug (leads_api._SLUG_RE); the base URL leaves room for "/<slug>" within MAX_URL
MAX_CONTACTED = 50
_BASE_URL_RE = re.compile(r'^https?://[^/\s]+', re.IGNORECASE)  # a scheme and a host
MAX_CONTACT_TEXT = 300
CRM_FIELDS = ('status', 'priority', 'comment', 'contacted', 'demo_url', 'demo_source', 'client_status', 'client_since')
DEFAULT_CRM: dict[str, Any] = {'status': NOT_WRITTEN, 'priority': 0, 'comment': '', 'contacted': [],
                               'demo_url': None, 'demo_source': None, 'client_status': None, 'client_since': None}


def _status(value: Any, valid_ids: AbstractSet[str]) -> dict:
    if value not in valid_ids:
        raise ValueError('Неизвестный статус лида')
    return {'status': value}


def _client_status(value: Any) -> dict:
    if value not in CLIENT_STATUSES:
        raise ValueError('Неизвестный статус клиента')
    return {'client_status': value}


def _priority(value: Any) -> dict:
    if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= MAX_PRIORITY:
        raise ValueError(f'Приоритет — число от 0 до {MAX_PRIORITY}')
    return {'priority': value}


def _comment(value: Any) -> dict:
    if not isinstance(value, str):
        raise ValueError('Комментарий должен быть текстом')
    text = value.strip()
    if len(text) > MAX_COMMENT:
        raise ValueError(f'Комментарий длиннее {MAX_COMMENT} символов')
    return {'comment': text}


def _is_contact(c: Any) -> bool:
    return (isinstance(c, dict) and set(c) == {'title', 'value'}
            and all(isinstance(c[k], str) and 0 < len(c[k]) <= MAX_CONTACT_TEXT for k in c))


def _contacted(value: Any) -> dict:
    if not isinstance(value, list) or len(value) > MAX_CONTACTED or not all(_is_contact(c) for c in value):
        raise ValueError('Канал связи: неверный список контактов')
    unique: list[dict] = []
    for c in value:
        if c not in unique:
            unique.append({'title': c['title'], 'value': c['value']})
    return {'contacted': unique}


def _demo_url(value: Any) -> dict:
    if not isinstance(value, str):
        raise ValueError('Ссылка на демо должна быть текстом')
    url = value.strip()
    if not url:
        return {'demo_url': None, 'demo_source': None}
    if not url.lower().startswith(('http://', 'https://')):
        raise ValueError('Ссылка на демо должна начинаться с http:// или https://')
    if len(url) > MAX_URL:
        raise ValueError(f'Ссылка на демо длиннее {MAX_URL} символов')
    return {'demo_url': url, 'demo_source': 'manual'}


def parse_base_url(value: Any) -> str:
    """The demo app's base URL for «Проработать лиды», without a trailing slash; ValueError with a Russian message."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError('Введите адрес демо-приложения')
    url = value.strip().rstrip('/')
    if not _BASE_URL_RE.match(url):
        raise ValueError('Адрес демо-приложения должен начинаться с http:// или https://')
    scheme, rest = url.split('://', 1)
    url = f'{scheme.lower()}://{rest}'  # the database checks a lower-case scheme
    if any(ch.isspace() for ch in url):
        raise ValueError('В адресе демо-приложения не должно быть пробелов')
    if '?' in url or '#' in url:
        raise ValueError('Адрес демо-приложения нужен без ? и # — название лида добавится в конец через /')
    if len(url) + 1 + MAX_SLUG > MAX_URL:
        raise ValueError('Адрес демо-приложения слишком длинный')
    return url


def parse_message_template(value: Any) -> Optional[str]:
    """A folder's «Общее сообщение», optionally with the demo link's place marked by NO_DEMO_URL; None (the sphere's
    message) for an empty text; ValueError with a Russian message otherwise."""
    if not isinstance(value, str):
        raise ValueError('Сообщение должно быть текстом')
    text = value.strip()
    if not text:
        return None
    if len(text) > MAX_MESSAGE:
        raise ValueError(f'Сообщение длиннее {MAX_MESSAGE} символов')
    return text


_PARSERS: dict[str, Callable[[Any], dict]] = {
    'client_status': _client_status, 'priority': _priority, 'comment': _comment,
    'contacted': _contacted, 'demo_url': _demo_url}
_FIELDS = (*_PARSERS, 'status')


def parse_patch(data: Any, valid_statuses: Optional[AbstractSet[str]] = None) -> dict:
    """Checked database fields for a change from the UI; ValueError with a Russian message otherwise.
    `valid_statuses` — the caller's current lead_statuses ids — is required whenever `status` may be in `data`."""
    if not isinstance(data, dict) or not data:
        raise ValueError('Нечего сохранять')
    unknown = [k for k in data if k not in _FIELDS]
    if unknown:
        raise ValueError(f'Неизвестное поле: {unknown[0]}')
    patch: dict = {}
    for key, value in data.items():
        patch = {**patch, **(_status(value, valid_statuses or frozenset()) if key == 'status' else _PARSERS[key](value))}
    return patch


def crm_of(row: dict) -> dict:
    """The lead's work fields from a database row, with defaults for missing ones."""
    return {k: row.get(k, DEFAULT_CRM[k]) for k in CRM_FIELDS}
