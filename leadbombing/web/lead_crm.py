"""Work on a saved lead (the «Сохранённые лиды» page) or a client («Клиенты»): status, priority, comment, contacted
channels, the demo app and, for a client, its client status.

`parse_patch` checks a change from the UI before it goes to the database. The demo app's `demo_source` is
`manual` for a URL typed by hand; a future generator will write `auto` through the store directly.
A lead becomes a client only through the store's `make_client` (status «Купил», client status «Всё ок»);
`client_status` is None for a lead.
"""
from __future__ import annotations

from typing import Any, Callable

STATUSES = ('not_written', 'written', 'in_progress', 'almost', 'bought', 'refused')
CLIENT_STATUSES = ('ok', 'question', 'bug')  # «Всё ок», «Есть вопрос», «Срочный баг»
MAX_PRIORITY = 5  # 0 not set, 1 very low … 5 very high (see leads/booking.py for the automatic one)
MAX_COMMENT = 5000
MAX_URL = 2000
MAX_CONTACTED = 50
MAX_CONTACT_TEXT = 300
CRM_FIELDS = ('status', 'priority', 'comment', 'contacted', 'demo_url', 'demo_source', 'client_status', 'client_since')
DEFAULT_CRM: dict[str, Any] = {'status': 'not_written', 'priority': 0, 'comment': '', 'contacted': [],
                               'demo_url': None, 'demo_source': None, 'client_status': None, 'client_since': None}


def _status(value: Any) -> dict:
    if value not in STATUSES:
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


_PARSERS: dict[str, Callable[[Any], dict]] = {
    'status': _status, 'client_status': _client_status, 'priority': _priority, 'comment': _comment,
    'contacted': _contacted, 'demo_url': _demo_url}


def parse_patch(data: Any) -> dict:
    """Checked database fields for a change from the UI; ValueError with a Russian message otherwise."""
    if not isinstance(data, dict) or not data:
        raise ValueError('Нечего сохранять')
    unknown = [k for k in data if k not in _PARSERS]
    if unknown:
        raise ValueError(f'Неизвестное поле: {unknown[0]}')
    patch: dict = {}
    for key, value in data.items():
        patch = {**patch, **_PARSERS[key](value)}
    return patch


def crm_of(row: dict) -> dict:
    """The lead's work fields from a database row, with defaults for missing ones."""
    return {k: row.get(k, DEFAULT_CRM[k]) for k in CRM_FIELDS}
