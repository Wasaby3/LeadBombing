"""In-memory stand-in for SupabaseStore: one user admin/admin, same methods and errors."""
from __future__ import annotations

import copy
import itertools
import time
from typing import Any, Optional

from leadbombing.web.lead_crm import DEFAULT_CRM, crm_of
from leadbombing.web.supabase import InvalidCredentials, Session, SessionExpired, StoreError

ADMIN_ID = 'a0000000-0000-4000-8000-000000000001'
TOKEN_TTL_S = 3600


class FakeStore:
    def __init__(self) -> None:
        self.settings: dict[str, dict] = {}
        self.runs: list[dict] = []
        self.leads: dict[tuple, dict] = {}
        self.folders: dict[int, dict] = {}
        self.folder_items: dict[int, dict[str, dict]] = {}
        self.refreshed = 0
        self.fail_writes = False
        self.down = False
        self._tokens = itertools.count(1)
        self._ids = itertools.count(1)
        self._valid_access: set[str] = set()
        self._valid_refresh: set[str] = set()

    def _session(self, ttl: float = TOKEN_TTL_S) -> Session:
        n = next(self._tokens)
        access, refresh = f'access-{n}', f'refresh-{n}'
        self._valid_access.add(access)
        self._valid_refresh.add(refresh)
        return Session(ADMIN_ID, 'admin', access, refresh, time.time() + ttl)

    def _check(self, token: str) -> None:
        if self.down:
            raise StoreError('База недоступна')
        if token not in self._valid_access:
            raise SessionExpired('Сессия истекла — войдите снова')

    def _write(self, token: str) -> None:
        self._check(token)
        if self.fail_writes:
            raise StoreError('Ошибка базы')

    def sign_in(self, login: str, password: str) -> Session:
        if self.down:
            raise StoreError('База недоступна')
        if (login, password) != ('admin', 'admin'):
            raise InvalidCredentials('Неверный логин или пароль')
        return self._session()

    def refresh(self, refresh_token: str) -> Session:
        if refresh_token not in self._valid_refresh:
            raise SessionExpired('Сессия истекла — войдите снова')
        self._valid_refresh.discard(refresh_token)
        self.refreshed += 1
        return self._session()

    def sign_out(self, access_token: str) -> None:
        self._valid_access.discard(access_token)

    def get_settings(self, token: str) -> dict:
        self._check(token)
        return copy.deepcopy(self.settings.get(ADMIN_ID, {}))

    def save_settings(self, token: str, data: dict) -> None:
        self._write(token)
        self.settings[ADMIN_ID] = copy.deepcopy(data)

    def create_run(self, token: str, run: dict) -> int:
        self._write(token)
        run_id = next(self._ids)
        self.runs.insert(0, {'id': run_id, 'status': 'running', 'accepted': 0, 'skipped': 0, 'error': None, **run})
        return run_id

    def update_run(self, token: str, run_id: int, fields: dict) -> None:
        self._write(token)
        self.runs = [{**r, **fields} if r['id'] == run_id else r for r in self.runs]

    def save_lead(self, token: str, lead: dict) -> None:
        self._write(token)
        self.leads[(lead['sphere'], lead['firm_id'])] = copy.deepcopy(lead)

    def list_runs(self, token: str, limit: int) -> list[dict]:
        self._check(token)
        return copy.deepcopy(self.runs[:limit])

    def list_leads(self, token: str, limit: int) -> list[dict]:
        self._check(token)
        rows = list(self.leads.values())[::-1][:limit]
        return [{'slug': r['slug'], 'sphere': r['sphere'], 'summary': r['summary']} for r in rows]

    def find_lead(self, token: str, slug: str) -> Optional[dict]:
        self._check(token)
        return next((copy.deepcopy(r['card']) for r in self.leads.values() if r['slug'] == slug), None)

    def create_folder(self, token: str, folder: dict) -> int:
        self._write(token)
        folder_id = next(self._ids)
        self.folders[folder_id] = {'id': folder_id, 'created_at': f'2026-11-17T00:00:{folder_id:02d}', **folder}
        self.folder_items[folder_id] = {}
        return folder_id

    def get_folder(self, token: str, folder_id: int) -> Optional[dict]:
        self._check(token)
        return copy.deepcopy(self.folders.get(folder_id))

    def update_folder(self, token: str, folder_id: int, fields: dict) -> None:
        self._write(token)
        self.folders[folder_id] = {**self.folders[folder_id], **copy.deepcopy(fields)}

    def list_folders(self, token: str) -> list[dict]:
        self._check(token)
        return [{**copy.deepcopy(f), 'count': len(self.folder_items[f['id']])} for f in reversed(self.folders.values())]

    def add_to_folder(self, token: str, folder_id: int, leads: list[dict]) -> None:
        self._write(token)
        items = self.folder_items[folder_id]
        for lead in leads:
            snapshot = {k: v for k, v in lead.items() if k != 'initial'}
            old = items.pop(lead['slug'], None)  # a re-added lead moves to the end, like a newer added_at
            # the snapshot is replaced, the work on the lead is kept; a new lead starts with its `initial` work
            work = crm_of(old) if old else {**DEFAULT_CRM, **(lead.get('initial') or {})}
            items[lead['slug']] = {**copy.deepcopy(work), **copy.deepcopy(snapshot)}

    def folder_leads(self, token: str, folder_id: int) -> list[dict]:
        self._check(token)
        return [{**copy.deepcopy(r['summary']), 'status': r['status'], 'priority': r['priority']}
                for r in self.folder_items.get(folder_id, {}).values()]

    def folder_card(self, token: str, folder_id: int, slug: str) -> Optional[dict]:
        self._check(token)
        row = self.folder_items.get(folder_id, {}).get(slug)
        return {**copy.deepcopy(row['card']), 'crm': copy.deepcopy(crm_of(row))} if row else None

    def update_folder_lead(self, token: str, folder_id: int, slug: str, fields: dict) -> Optional[dict]:
        self._write(token)
        items = self.folder_items.get(folder_id, {})
        if slug not in items:
            return None
        items[slug] = {**items[slug], **copy.deepcopy(fields)}
        return copy.deepcopy(crm_of(items[slug]))

    def delete_folder_lead(self, token: str, folder_id: int, slug: str) -> bool:
        self._write(token)
        return self.folder_items.get(folder_id, {}).pop(slug, None) is not None

    def folder_raw(self, token: str, folder_id: int) -> list[dict]:
        self._check(token)
        return [{'slug': r['slug'], 'raw': copy.deepcopy(r['raw'])} for r in self.folder_items.get(folder_id, {}).values()]

    # TEMP: assessment of old leads (web/assess_job.py)
    def folder_assess_rows(self, token: str, folder_id: int) -> list[dict]:
        self._check(token)
        return [{'slug': r['slug'], 'card': copy.deepcopy(r['card']), 'item': copy.deepcopy(r['raw']['item']),
                 'priority': r['priority'], 'comment': r['comment']} for r in self.folder_items.get(folder_id, {}).values()]

    def set_assessment(self, token: str, folder_id: int, slug: str, fields: dict) -> None:
        self._write(token)
        items = self.folder_items.get(folder_id, {})
        if slug in items:
            items[slug] = {**items[slug], **copy.deepcopy(fields)}


def login(client: Any, password: str = 'admin') -> Any:
    return client.post('/api/auth/login', json={'login': 'admin', 'password': password})
