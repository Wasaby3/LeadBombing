"""Custom lead statuses (Настройки → «Статусы лидов»): own name and color instead of the fixed six, up to
MAX_STATUSES total. A status is stored once (lead_statuses table), so renaming or recoloring it shows everywhere
at once. The default status isn't a field of its own — it's always the one with the smallest `sort_order` (the
first in the picker); `not_written` is seeded at sort_order 0 and is never deleted, so it stays the default unless
the list is ever reordered. Deleting a status moves every lead that had it to the status that is default once it
is gone (SupabaseStore/FakeStore do this through `check_deletable` plus their own `sort_order`-ordered fallback).
`not_written` and `bought` can be renamed and recolored but never deleted — the app depends on their ids for the
«Написали» count (supabase.py `worked_outside`, the delete_folder_lead function) and for «Перевести в клиенты»
(supabase.py `make_client`).
"""
from __future__ import annotations

from typing import Any, Optional

PALETTE = ('neutral', 'good', 'wait', 'active', 'warm', 'bad', 'purple', 'teal', 'pink')
MAX_STATUSES = 9
MAX_NAME = 40
PROTECTED_IDS = ('not_written', 'bought')
LEAD_STATUS_FIELDS = ('id', 'name', 'color', 'sort_order')
DEFAULT_NAME = 'Новый статус'  # «Добавить статус» adds one with this name right away, no dialog

BUILTIN_STATUSES: tuple[dict[str, Any], ...] = (
    {'id': 'not_written', 'name': 'Ещё не написал', 'color': 'neutral', 'sort_order': 0},
    {'id': 'written', 'name': 'Написал', 'color': 'wait', 'sort_order': 1},
    {'id': 'in_progress', 'name': 'В работе', 'color': 'active', 'sort_order': 2},
    {'id': 'almost', 'name': 'Почти купил', 'color': 'warm', 'sort_order': 3},
    {'id': 'bought', 'name': 'Купил', 'color': 'good', 'sort_order': 4},
    {'id': 'refused', 'name': 'Отказался', 'color': 'bad', 'sort_order': 5},
)


def seeded_rows() -> list[dict]:
    """Fresh rows for a user with no lead_statuses yet: the 6 builtin statuses, in picker order."""
    return [dict(row) for row in BUILTIN_STATUSES]


def validate_name(value: Any, existing: list[dict], *, exclude_id: Optional[str] = None) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError('Введите название статуса')
    name = value.strip()
    if len(name) > MAX_NAME:
        raise ValueError(f'Название статуса длиннее {MAX_NAME} символов')
    if any(s['name'] == name for s in existing if s['id'] != exclude_id):
        raise ValueError('Такой статус уже есть')
    return name


def pick_unused_color(existing: list[dict]) -> str:
    """A palette color no status in `existing` already uses; PALETTE[0] once every color is taken."""
    used = {s['color'] for s in existing}
    return next((c for c in PALETTE if c not in used), PALETTE[0])


def default_name(existing: list[dict]) -> str:
    """«Добавить статус» names the new one DEFAULT_NAME, numbered if that's already taken."""
    taken = {s['name'] for s in existing}
    if DEFAULT_NAME not in taken:
        return DEFAULT_NAME
    n = 2
    while f'{DEFAULT_NAME} {n}' in taken:
        n += 1
    return f'{DEFAULT_NAME} {n}'


def validate_color(value: Any) -> str:
    if value not in PALETTE:
        raise ValueError('Неизвестный цвет статуса')
    return value


def check_deletable(statuses: list[dict], status_id: str) -> bool:
    """False if `status_id` isn't in `statuses` (404 for the caller). Raises ValueError with a Russian message if
    it's there but can't be deleted (protected, or the last one). True otherwise."""
    if not any(s['id'] == status_id for s in statuses):
        return False
    if status_id in PROTECTED_IDS:
        raise ValueError('Этот статус нельзя удалить')
    if len(statuses) == 1:
        raise ValueError('Нужен хотя бы один статус')
    return True
