"""Thin client of the local Supabase: password login (Auth) and the account tables (PostgREST, RLS by user JWT)."""
from __future__ import annotations

import os
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

import requests

from ..leads.contacts import card_owner_mark, phone_matches
from ..leads.firm import firm_id
from ..leads.text import phone_digits
from ..logger import logger
from .lead_crm import CRM_FIELDS, NOT_WRITTEN, crm_of
from .lead_statuses import LEAD_STATUS_FIELDS, check_deletable, seeded_rows

DEFAULT_URL = 'http://127.0.0.1:55321'
SCHEMA = 'leadbombing'  # own schema: on the server the Supabase is shared with another app
_READ_METHODS = ('GET', 'HEAD')
LOGIN_DOMAIN = 'leadbombing.local'  # Supabase logs in by email: login `admin` is admin@leadbombing.local
_TIMEOUT_S = 10
_ENV_FILE = '.env.local'
_RUN_FIELDS = 'id,sphere,query,cities,lead_limit,status,accepted,skipped,error,started_at,finished_at'
_FOLDER_FIELDS = 'id,name,sphere,query,cities,created_at,demo_base_url,demo_filled_at,removed_worked,message_template'
_FOLDER_CHUNK = 50  # leads per insert: raw firm data is tens of KB each
_CRM_SELECT = ','.join(CRM_FIELDS)
_LEAD_STATUS_SELECT = ','.join(LEAD_STATUS_FIELDS)
_ONLY_LEADS = {'client_status': 'is.null'}  # a folder shows and exports leads, not clients
_OWNER_SELECT = 'contacts:card->contacts,legal:card->legal'  # what the owner crown needs, not the whole card
_PHONE_SEARCH_SELECT = f'folder_id,slug,client_status,name:summary->>name,{_OWNER_SELECT},folder:folders(name)'


def client_row(r: dict) -> dict:
    """A clients table row from a folder_leads row with its folder name (`folder: {name}`)."""
    return {**r['summary'], 'slug': r['slug'], 'folder_id': r['folder_id'], 'folder': r['folder']['name'],
            'status': r['status'], 'priority': r['priority'], 'client_status': r['client_status'],
            'client_since': r['client_since'], 'owner': card_owner_mark(r)}


class StoreError(RuntimeError):
    """Database problem; the message is shown to the user."""


class InvalidCredentials(StoreError):
    pass


class SessionExpired(StoreError):
    pass


class AccessDenied(StoreError):
    """A user of the shared Supabase who is not in leadbombing.members."""


@dataclass(frozen=True)
class Session:
    user_id: str
    login: str
    access_token: str
    refresh_token: str
    expires_at: float  # unix time


def login_email(login: str) -> str:
    return login if '@' in login else f'{login}@{LOGIN_DOMAIN}'


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class _HttpError(StoreError):
    def __init__(self, status: int, code: str) -> None:
        super().__init__(f'HTTP {status} {code}')
        self.status, self.code = status, code


class SupabaseStore:
    def __init__(self, url: str, key: str) -> None:
        self._url = url.rstrip('/')
        self._key = key

    # --- Auth ---

    def sign_in(self, login: str, password: str) -> Session:
        session = self._session(self._auth('token?grant_type=password',
                                           {'email': login_email(login), 'password': password}))
        if not self._is_member(session):
            self.sign_out(session.access_token)
            raise AccessDenied('Этой учётной записи закрыт доступ к LeadBombing')
        return session

    def _is_member(self, session: Session) -> bool:
        return bool(self._request('GET', '/rest/v1/members', session.access_token,
                                  params={'select': 'user_id', 'user_id': f'eq.{session.user_id}'}))

    def refresh(self, refresh_token: str) -> Session:
        return self._session(self._auth('token?grant_type=refresh_token', {'refresh_token': refresh_token}))

    def sign_out(self, access_token: str) -> None:
        try:
            self._request('POST', '/auth/v1/logout', access_token)
        except StoreError as e:  # the token expires on its own anyway
            logger.debug('Выход из Supabase: %s', e)

    # --- Account data ---

    def get_settings(self, token: str) -> dict:
        rows = self._request('GET', '/rest/v1/user_settings', token, params={'select': 'data'})
        return rows[0]['data'] if rows else {}

    def save_settings(self, token: str, data: dict) -> None:
        self._request('POST', '/rest/v1/user_settings', token, json={'data': data, 'updated_at': _now()},
                      prefer='resolution=merge-duplicates,return=minimal')

    def create_run(self, token: str, run: dict) -> int:
        rows = self._request('POST', '/rest/v1/runs', token, json=run, params={'select': 'id'},
                             prefer='return=representation')
        return int(rows[0]['id'])

    def update_run(self, token: str, run_id: int, fields: dict) -> None:
        self._request('PATCH', '/rest/v1/runs', token, json=fields, params={'id': f'eq.{run_id}'},
                      prefer='return=minimal')

    def save_lead(self, token: str, lead: dict) -> None:
        self._request('POST', '/rest/v1/leads', token, json={**lead, 'updated_at': _now()},
                      params={'on_conflict': 'user_id,sphere,firm_id'},
                      prefer='resolution=merge-duplicates,return=minimal')

    # --- Custom lead statuses (Настройки → «Статусы лидов») ---

    def list_lead_statuses(self, token: str) -> list[dict]:
        """The user's lead statuses, in picker order; the 6 builtin ones are seeded on first call."""
        rows = self._request('GET', '/rest/v1/lead_statuses', token,
                             params={'select': _LEAD_STATUS_SELECT, 'order': 'sort_order.asc'})
        if rows:
            return rows
        self._request('POST', '/rest/v1/lead_statuses', token, json=seeded_rows(),
                      params={'on_conflict': 'user_id,id'}, prefer='resolution=ignore-duplicates,return=minimal')
        return seeded_rows()

    def create_lead_status(self, token: str, name: str, color: str) -> dict:
        existing = self.list_lead_statuses(token)
        sort_order = max((s['sort_order'] for s in existing), default=-1) + 1
        status_id = f'custom-{uuid.uuid4().hex[:10]}'
        rows = self._request('POST', '/rest/v1/lead_statuses', token,
                             json={'id': status_id, 'name': name, 'color': color, 'sort_order': sort_order},
                             params={'select': _LEAD_STATUS_SELECT}, prefer='return=representation')
        return rows[0]

    def update_lead_status(self, token: str, status_id: str, fields: dict) -> Optional[dict]:
        """Rename and/or recolor a status; None if there is no such status."""
        self._request('PATCH', '/rest/v1/lead_statuses', token, json=fields, params={'id': f'eq.{status_id}'},
                      prefer='return=minimal')
        rows = self._request('GET', '/rest/v1/lead_statuses', token,
                             params={'select': _LEAD_STATUS_SELECT, 'id': f'eq.{status_id}'})
        return rows[0] if rows else None

    def delete_lead_status(self, token: str, status_id: str) -> Optional[bool]:
        """Delete a status, moving every lead that had it to the status that becomes default once it's gone (the
        one with the smallest sort_order among what's left); None if there is no such status. Raises ValueError
        (lead_statuses.check_deletable) if deletion isn't allowed."""
        if not check_deletable(self.list_lead_statuses(token), status_id):
            return None
        self._request('POST', '/rest/v1/rpc/delete_lead_status', token, json={'p_id': status_id})
        return True

    def list_runs(self, token: str, limit: int) -> list[dict]:
        return self._request('GET', '/rest/v1/runs', token,
                             params={'select': _RUN_FIELDS, 'order': 'started_at.desc', 'limit': str(limit)})

    def list_leads(self, token: str, limit: int) -> list[dict]:
        return self._request('GET', '/rest/v1/leads', token,
                             params={'select': 'slug,sphere,summary', 'order': 'updated_at.desc', 'limit': str(limit)})

    def find_lead(self, token: str, slug: str) -> Optional[dict]:
        rows = self._request('GET', '/rest/v1/leads', token, params={
            'select': 'card', 'slug': f'eq.{slug}', 'order': 'updated_at.desc', 'limit': '1'})
        return rows[0]['card'] if rows else None

    # --- Folders of saved leads ---

    def create_folder(self, token: str, folder: dict) -> int:
        rows = self._request('POST', '/rest/v1/folders', token, json=folder, params={'select': 'id'},
                             prefer='return=representation')
        return int(rows[0]['id'])

    def get_folder(self, token: str, folder_id: int) -> Optional[dict]:
        rows = self._request('GET', '/rest/v1/folders', token,
                             params={'select': _FOLDER_FIELDS, 'id': f'eq.{folder_id}'})
        return rows[0] if rows else None

    def update_folder(self, token: str, folder_id: int, fields: dict) -> None:
        self._request('PATCH', '/rest/v1/folders', token, json=fields, params={'id': f'eq.{folder_id}'},
                      prefer='return=minimal')

    def list_folders(self, token: str) -> list[dict]:
        rows = self._request('GET', '/rest/v1/folders', token, params={
            'select': f'{_FOLDER_FIELDS},folder_leads(count)', 'folder_leads.client_status': 'is.null',
            'order': 'created_at.desc'})
        return [{**{k: v for k, v in r.items() if k != 'folder_leads'},
                 'count': r['folder_leads'][0]['count'] if r['folder_leads'] else 0} for r in rows]

    def add_to_folder(self, token: str, folder_id: int, leads: list[dict], default_status: str = NOT_WRITTEN) -> None:
        """Insert leads ({slug, summary, card, raw, initial?}) in order; a lead already in the folder gets the new
        snapshot and keeps the work on it (only the sent columns are merged). A lead new to the folder starts with
        `default_status` plus its `initial` work fields (priority, comment), if any."""
        known = {r['slug'] for r in self._request('GET', '/rest/v1/folder_leads', token, params={
            'select': 'slug', 'folder_id': f'eq.{folder_id}'})}
        base = datetime.now(timezone.utc)
        rows = [{**{k: v for k, v in lead.items() if k != 'initial'},
                 **({} if lead['slug'] in known else {'status': default_status, **(lead.get('initial') or {})}),
                 'folder_id': folder_id, 'added_at': (base + timedelta(microseconds=i)).isoformat()}
                for i, lead in enumerate(leads)]
        groups: dict[tuple[str, ...], list[dict]] = {}  # PostgREST wants the same columns in every row of a request
        for row in rows:
            groups.setdefault(tuple(sorted(row)), []).append(row)
        for group in groups.values():
            for start in range(0, len(group), _FOLDER_CHUNK):
                self._request('POST', '/rest/v1/folder_leads', token, json=group[start:start + _FOLDER_CHUNK],
                              params={'on_conflict': 'folder_id,slug'},
                              prefer='resolution=merge-duplicates,return=minimal')

    def folder_firms(self, token: str, folder_id: int) -> dict[str, str]:
        """Firm id → slug of every lead and client of the folder: a slug in a folder belongs to one firm."""
        rows = self._request('GET', '/rest/v1/folder_leads', token, params={
            'select': 'slug,item_id:raw->item->>id', 'folder_id': f'eq.{folder_id}'})
        return {firm_id({'id': r['item_id'] or ''}): r['slug'] for r in rows}

    def folder_leads(self, token: str, folder_id: int) -> list[dict]:
        """Table rows of the folder's leads (not clients) in folder order, each with the lead's status and priority."""
        rows = self._request('GET', '/rest/v1/folder_leads', token, params={
            'select': f'summary,status,priority,{_OWNER_SELECT}', **_ONLY_LEADS,
            'folder_id': f'eq.{folder_id}', 'order': 'added_at.asc'})
        return [{**r['summary'], 'status': r['status'], 'priority': r['priority'], 'owner': card_owner_mark(r)}
                for r in rows]

    def folder_card(self, token: str, folder_id: int, slug: str) -> Optional[dict]:
        """The lead card with the work on it (`crm`), or None."""
        rows = self._request('GET', '/rest/v1/folder_leads', token, params={
            'select': f'card,{_CRM_SELECT}', 'folder_id': f'eq.{folder_id}', 'slug': f'eq.{slug}'})
        return {**rows[0]['card'], 'crm': crm_of(rows[0])} if rows else None

    def update_folder_lead(self, token: str, folder_id: int, slug: str, fields: dict) -> Optional[dict]:
        """Change the work on a lead (fields from lead_crm); the lead's crm after it, None if there is no such lead.
        A client status is changed only for a client: for a lead the result is None too."""
        only_clients = {'client_status': 'not.is.null'} if 'client_status' in fields else {}
        rows = self._request('PATCH', '/rest/v1/folder_leads', token, json={**fields, 'worked_at': _now()},
                             params={'folder_id': f'eq.{folder_id}', 'slug': f'eq.{slug}', 'select': _CRM_SELECT,
                                     **only_clients},
                             prefer='return=representation')
        return crm_of(rows[0]) if rows else None

    def make_client(self, token: str, folder_id: int, slug: str) -> Optional[dict]:
        """Make a lead a client: status «Купил», client status «Всё ок». Its crm, None if there is no such lead or it
        is a client already."""
        now = _now()
        rows = self._request('PATCH', '/rest/v1/folder_leads', token,
                             json={'status': 'bought', 'client_status': 'ok', 'client_since': now, 'worked_at': now},
                             params={'folder_id': f'eq.{folder_id}', 'slug': f'eq.{slug}', 'select': _CRM_SELECT,
                                     **_ONLY_LEADS},
                             prefer='return=representation')
        return crm_of(rows[0]) if rows else None

    def list_clients(self, token: str) -> list[dict]:
        """Table rows of all clients, newest first: the lead row plus its folder, statuses and client_since."""
        rows = self._request('GET', '/rest/v1/folder_leads', token, params={
            'select': f'folder_id,slug,summary,status,priority,client_status,client_since,{_OWNER_SELECT},'
                      'folder:folders(name)',
            'client_status': 'not.is.null', 'order': 'client_since.desc'})
        return [client_row(r) for r in rows]

    def delete_folder_lead(self, token: str, folder_id: int, slug: str) -> bool:
        """Delete a lead or client; one already worked on (status not «Ещё не написал») stays counted in the folder's
        removed_worked. False if there is no such lead."""
        return bool(self._request('POST', '/rest/v1/rpc/delete_folder_lead', token,
                                  json={'p_folder_id': folder_id, 'p_slug': slug}))

    def worked_outside(self, token: str, folder_id: int) -> int:
        """Leads of the folder worked on but not in its list: its clients and deleted leads that had a status."""
        clients = self._request('GET', '/rest/v1/folder_leads', token, params={
            'select': 'slug', 'folder_id': f'eq.{folder_id}', 'client_status': 'not.is.null',
            'status': f'neq.{NOT_WRITTEN}'})
        folder = self.get_folder(token, folder_id)
        return len(clients) + (folder['removed_worked'] if folder else 0)

    def fill_demo_urls(self, token: str, folder_id: int, base_url: str, slugs: Optional[list[str]]) -> dict:
        """«Проработать лиды»: demo URL `base_url/<slug>` (auto) for the folder's leads, all or only `slugs`; not
        for clients or URLs typed by hand. {filled, kept} and the folder remembers the base URL with the time."""
        rows = self._request('POST', '/rest/v1/rpc/fill_demo_urls', token,
                             json={'p_folder_id': folder_id, 'p_base_url': base_url, 'p_slugs': slugs})
        return rows[0]

    def folder_raw(self, token: str, folder_id: int) -> list[dict]:
        """[{slug, raw: {item, prices}}] of the folder's leads (not clients) in folder order, for export."""
        return self._request('GET', '/rest/v1/folder_leads', token, params={
            'select': 'slug,raw', **_ONLY_LEADS, 'folder_id': f'eq.{folder_id}', 'order': 'added_at.asc'})

    def find_leads_by_phone(self, token: str, phone: str) -> list[dict]:
        """Saved leads and clients, across every folder of the user, whose contacts hold `phone` (any contact,
        matched with `phone_matches` — so a WhatsApp or «maybe owner» number counts too). [] for a query too short
        to search by."""
        digits = phone_digits(phone)
        rows = self._request('GET', '/rest/v1/folder_leads', token, params={'select': _PHONE_SEARCH_SELECT})
        found = []
        for r in rows:
            match = phone_matches(r.get('contacts') or [], digits)
            if match:
                found.append({
                    'folder_id': r['folder_id'], 'slug': r['slug'], 'folder': r['folder']['name'],
                    'name': r['name'], 'is_client': r['client_status'] is not None,
                    'matched_contact': {'type': match['type'], 'value': match['value']},
                })
        return found

    # --- HTTP ---

    @staticmethod
    def _session(data: dict) -> Session:
        user = data['user']
        login = (user.get('user_metadata') or {}).get('login') or user.get('email', '')
        expires_at = float(data.get('expires_at') or time.time() + int(data.get('expires_in') or 0))
        return Session(user['id'], login, data['access_token'], data['refresh_token'], expires_at)

    def _auth(self, path: str, body: dict) -> dict:
        try:
            return self._request('POST', f'/auth/v1/{path}', None, json=body)
        except _HttpError as e:
            if e.status == 400 and e.code == 'invalid_credentials':
                raise InvalidCredentials('Неверный логин или пароль') from None
            if e.status in (400, 401, 403):
                raise SessionExpired('Сессия истекла — войдите снова') from None
            raise StoreError(f'Ошибка входа ({e.status})') from None

    def _request(self, method: str, path: str, token: Optional[str], json: Any = None,
                 params: Optional[dict] = None, prefer: str = '') -> Any:
        if not self._key:
            raise StoreError('Не задан SUPABASE_ANON_KEY — впишите его в .env.local (см. .env.example)')
        headers = {'apikey': self._key, 'Authorization': f'Bearer {token or self._key}'}
        if prefer:
            headers['Prefer'] = prefer
        if path.startswith('/rest/'):
            headers['Accept-Profile' if method in _READ_METHODS else 'Content-Profile'] = SCHEMA
        try:
            res = requests.request(method, self._url + path, headers=headers, json=json, params=params,
                                   timeout=_TIMEOUT_S)
        except requests.RequestException as e:
            logger.debug('Supabase недоступен: %r', e)
            raise StoreError('База недоступна — запустите Supabase (npx supabase start)') from None
        if res.ok:
            return res.json() if res.content else None
        body = res.json() if res.content and 'json' in res.headers.get('Content-Type', '') else {}
        code = str(body.get('error_code') or body.get('code') or '')
        if path.startswith('/auth/'):
            raise _HttpError(res.status_code, code)
        if res.status_code == 401:
            raise SessionExpired('Сессия истекла — войдите снова')
        logger.error('Ошибка базы: %s %s → %s %s %s', method, path, res.status_code, code, body.get('message', ''))
        raise StoreError(f'Ошибка базы ({res.status_code})')


def _read_env_file(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    pairs = (line.split('=', 1) for line in path.read_text('utf-8').splitlines()
             if '=' in line and not line.lstrip().startswith('#'))
    return {k.strip(): v.strip().strip('"\'') for k, v in pairs}


def store_from_env() -> SupabaseStore:
    """SUPABASE_URL / SUPABASE_ANON_KEY from the environment, else from .env.local (repo root, then cwd)."""
    repo_root = Path(__file__).resolve().parents[2]
    file_env = {**_read_env_file(repo_root / _ENV_FILE), **_read_env_file(Path.cwd() / _ENV_FILE)}

    def get(name: str, default: str = '') -> str:
        return os.environ.get(name) or file_env.get(name) or default

    return SupabaseStore(get('SUPABASE_URL', DEFAULT_URL), get('SUPABASE_ANON_KEY'))
