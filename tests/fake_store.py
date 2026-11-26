"""In-memory stand-in for SupabaseStore: one user admin/admin, same methods and errors."""
from __future__ import annotations

import copy
import itertools
import time
from datetime import datetime, timezone
from typing import Any, Optional

from leadbombing.leads.contacts import card_owner_mark, phone_matches
from leadbombing.leads.firm import firm_id
from leadbombing.leads.text import phone_digits
from leadbombing.web.lead_crm import DEFAULT_CRM, NOT_WRITTEN, crm_of
from leadbombing.web.lead_statuses import check_deletable, seeded_rows
from leadbombing.web.supabase import AccessDenied, InvalidCredentials, Session, SessionExpired, StoreError, client_row

ADMIN_ID = 'a0000000-0000-4000-8000-000000000001'
TOKEN_TTL_S = 3600


class FakeStore:
    def __init__(self) -> None:
        self.settings: dict[str, dict] = {}
        self.lead_statuses: list[dict] = []
        self.runs: list[dict] = []
        self.leads: dict[tuple, dict] = {}
        self.folders: dict[int, dict] = {}
        self.folder_items: dict[int, dict[str, dict]] = {}
        self.refreshed = 0
        self.members: set[str] = {ADMIN_ID}
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
        if ADMIN_ID not in self.members:
            raise AccessDenied('Этой учётной записи закрыт доступ к LeadBombing')
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

    def list_lead_statuses(self, token: str) -> list[dict]:
        self._check(token)
        if not self.lead_statuses:
            self.lead_statuses = seeded_rows()
        return copy.deepcopy(self.lead_statuses)

    def create_lead_status(self, token: str, name: str, color: str) -> dict:
        self._write(token)
        existing = self.list_lead_statuses(token)
        sort_order = max((s['sort_order'] for s in existing), default=-1) + 1
        status_id = f'custom-{next(self._ids)}'
        row = {'id': status_id, 'name': name, 'color': color, 'sort_order': sort_order}
        self.lead_statuses.append(row)
        return copy.deepcopy(row)

    def update_lead_status(self, token: str, status_id: str, fields: dict) -> Optional[dict]:
        self._write(token)
        if not any(s['id'] == status_id for s in self.lead_statuses):
            return None
        self.lead_statuses = [{**s, **fields} if s['id'] == status_id else s for s in self.lead_statuses]
        return copy.deepcopy(next(s for s in self.lead_statuses if s['id'] == status_id))

    def delete_lead_status(self, token: str, status_id: str) -> Optional[bool]:
        self._write(token)
        if not check_deletable(self.list_lead_statuses(token), status_id):
            return None
        remaining = sorted((s for s in self.lead_statuses if s['id'] != status_id), key=lambda s: s['sort_order'])
        fallback = remaining[0]['id']
        self.lead_statuses = remaining
        for items in self.folder_items.values():
            for slug, row in items.items():
                if row['status'] == status_id:
                    items[slug] = {**row, 'status': fallback}
        return True

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
        self.folders[folder_id] = {'id': folder_id, 'created_at': f'2026-11-17T00:00:{folder_id:02d}',
                                   'demo_base_url': None, 'demo_filled_at': None, 'removed_worked': 0,
                                   'message_template': None, **folder}
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
        return [{**copy.deepcopy(f), 'count': len(self._leads_of(f['id']))} for f in reversed(self.folders.values())]

    def _leads_of(self, folder_id: int) -> list[dict]:
        """The folder's leads, not its clients."""
        return [r for r in self.folder_items.get(folder_id, {}).values() if r['client_status'] is None]

    def add_to_folder(self, token: str, folder_id: int, leads: list[dict], default_status: str = NOT_WRITTEN) -> None:
        self._write(token)
        items = self.folder_items[folder_id]
        for lead in leads:
            snapshot = {k: v for k, v in lead.items() if k != 'initial'}
            old = items.pop(lead['slug'], None)  # a re-added lead moves to the end, like a newer added_at
            # the snapshot is replaced, the work on the lead is kept; a new lead starts with its `initial` work
            work = crm_of(old) if old else {**DEFAULT_CRM, 'status': default_status, **(lead.get('initial') or {})}
            items[lead['slug']] = {**copy.deepcopy(work), **copy.deepcopy(snapshot)}

    def folder_firms(self, token: str, folder_id: int) -> dict[str, str]:
        self._check(token)
        return {firm_id(r['raw']['item']): r['slug'] for r in self.folder_items.get(folder_id, {}).values()}

    def folder_leads(self, token: str, folder_id: int) -> list[dict]:
        self._check(token)
        return [{**copy.deepcopy(r['summary']), 'status': r['status'], 'priority': r['priority'],
                 'owner': card_owner_mark(r['card'])} for r in self._leads_of(folder_id)]

    def folder_card(self, token: str, folder_id: int, slug: str) -> Optional[dict]:
        self._check(token)
        row = self.folder_items.get(folder_id, {}).get(slug)
        return {**copy.deepcopy(row['card']), 'crm': copy.deepcopy(crm_of(row))} if row else None

    def update_folder_lead(self, token: str, folder_id: int, slug: str, fields: dict) -> Optional[dict]:
        self._write(token)
        items = self.folder_items.get(folder_id, {})
        if slug not in items or ('client_status' in fields and items[slug]['client_status'] is None):
            return None
        items[slug] = {**items[slug], **copy.deepcopy(fields)}
        return copy.deepcopy(crm_of(items[slug]))

    def make_client(self, token: str, folder_id: int, slug: str) -> Optional[dict]:
        self._write(token)
        items = self.folder_items.get(folder_id, {})
        if slug not in items or items[slug]['client_status'] is not None:
            return None
        since = datetime.now(timezone.utc).isoformat()
        items[slug] = {**items[slug], 'status': 'bought', 'client_status': 'ok', 'client_since': since}
        return copy.deepcopy(crm_of(items[slug]))

    def list_clients(self, token: str) -> list[dict]:
        self._check(token)
        rows = [{**copy.deepcopy(r), 'folder_id': folder_id, 'folder': {'name': self.folders[folder_id]['name']},
                 'contacts': r['card'].get('contacts'), 'legal': r['card'].get('legal')}
                for folder_id, items in self.folder_items.items() for r in items.values()
                if r['client_status'] is not None]
        return [client_row(r) for r in sorted(rows, key=lambda r: r['client_since'], reverse=True)]

    def delete_folder_lead(self, token: str, folder_id: int, slug: str) -> bool:
        self._write(token)
        gone = self.folder_items.get(folder_id, {}).pop(slug, None)
        if gone and gone['status'] != NOT_WRITTEN:
            folder = self.folders[folder_id]
            self.folders[folder_id] = {**folder, 'removed_worked': folder['removed_worked'] + 1}
        return gone is not None

    def worked_outside(self, token: str, folder_id: int) -> int:
        self._check(token)
        clients = [r for r in self.folder_items.get(folder_id, {}).values()
                   if r['client_status'] is not None and r['status'] != NOT_WRITTEN]
        return len(clients) + self.folders[folder_id]['removed_worked']

    def fill_demo_urls(self, token: str, folder_id: int, base_url: str, slugs: Optional[list[str]]) -> dict:
        self._write(token)
        targets = [r for r in self._leads_of(folder_id) if slugs is None or r['slug'] in slugs]
        items = self.folder_items[folder_id]
        for r in targets:
            if r['demo_source'] != 'manual':
                items[r['slug']] = {**r, 'demo_url': f"{base_url}/{r['slug']}", 'demo_source': 'auto'}
        self.folders[folder_id] = {**self.folders[folder_id], 'demo_base_url': base_url,
                                   'demo_filled_at': datetime.now(timezone.utc).isoformat()}
        kept = sum(1 for r in targets if r['demo_source'] == 'manual')
        return {'filled': len(targets) - kept, 'kept': kept}

    def folder_raw(self, token: str, folder_id: int) -> list[dict]:
        self._check(token)
        return [{'slug': r['slug'], 'raw': copy.deepcopy(r['raw'])} for r in self._leads_of(folder_id)]

    def find_leads_by_phone(self, token: str, phone: str) -> list[dict]:
        self._check(token)
        found = []
        for folder_id, items in self.folder_items.items():
            for r in items.values():
                match = phone_matches(r['card'].get('contacts') or [], phone_digits(phone))
                if match:
                    found.append({
                        'folder_id': folder_id, 'slug': r['slug'], 'folder': self.folders[folder_id]['name'],
                        'name': r['summary'].get('name'), 'is_client': r['client_status'] is not None,
                        'matched_contact': {'type': match['type'], 'value': match['value']},
                    })
        return found


def login(client: Any, password: str = 'admin') -> Any:
    return client.post('/api/auth/login', json={'login': 'admin', 'password': password})
