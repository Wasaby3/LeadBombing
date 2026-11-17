"""Logged-in accounts of this server process and saving a leads run into the account."""
from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from typing import Any, Optional

from ..leads.writer import firm_id_of
from ..logger import logger
from .supabase import Session, StoreError

_REFRESH_MARGIN_S = 60  # refresh the access token a minute before it expires


class Account:
    """One logged-in user; keeps the access token fresh for requests and long background runs."""

    def __init__(self, store: Any, session: Session) -> None:
        self.store = store
        self._session = session
        self._lock = threading.Lock()

    @property
    def user_id(self) -> str:
        return self._session.user_id

    @property
    def login(self) -> str:
        return self._session.login

    @property
    def refresh_token(self) -> str:
        return self._session.refresh_token

    def token(self) -> str:
        with self._lock:
            if self._session.expires_at - time.time() < _REFRESH_MARGIN_S:
                fresh = self.store.refresh(self._session.refresh_token)
                self._session = Session(fresh.user_id, self._session.login or fresh.login, fresh.access_token,
                                        fresh.refresh_token, fresh.expires_at)
            return self._session.access_token

    def sign_out(self) -> None:
        self.store.sign_out(self._session.access_token)


class Accounts:
    """Accounts by user id. After a server restart an account is restored from the cookie's refresh token."""

    def __init__(self, store: Any) -> None:
        self.store = store
        self._by_id: dict[str, Account] = {}
        self._lock = threading.Lock()

    def sign_in(self, login: str, password: str) -> Account:
        return self._keep(Account(self.store, self.store.sign_in(login, password)))

    def get(self, user_id: str) -> Optional[Account]:
        return self._by_id.get(user_id)

    def restore(self, user_id: str, refresh_token: str) -> Account:
        session = self.store.refresh(refresh_token)
        if session.user_id != user_id:
            raise StoreError('Сессия принадлежит другому пользователю')
        return self._keep(Account(self.store, session))

    def sign_out(self, user_id: str) -> None:
        with self._lock:
            account = self._by_id.pop(user_id, None)
        if account:
            account.sign_out()

    def _keep(self, account: Account) -> Account:
        with self._lock:
            self._by_id[account.user_id] = account
        return account


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class RunRecorder:
    """Saves one leads run and its leads to the account. Database errors are logged and never stop the run."""

    def __init__(self, account: Account) -> None:
        self._account = account
        self._run_id: Optional[int] = None
        self._sphere = ''

    def started(self, sphere: str, query: str, cities: list[str], limit: int) -> None:
        self._sphere = sphere
        self._run_id = self._safe('запуск', lambda token: self._account.store.create_run(
            token, {'sphere': sphere, 'query': query, 'cities': cities, 'lead_limit': limit}))

    def lead(self, event: dict, summary: dict) -> None:
        row = {'sphere': self._sphere, 'firm_id': firm_id_of(event['lead'].get('source', '')),
               'slug': event['slug'], 'run_id': self._run_id, 'summary': summary,
               'card': {k: event[k] for k in ('lead', 'row', 'business')}}
        self._safe('лид', lambda token: self._account.store.save_lead(token, row))

    def finished(self, status: str, accepted: int, skipped: int, error: Optional[str]) -> None:
        if self._run_id is None:
            return
        fields = {'status': status, 'accepted': accepted, 'skipped': skipped, 'error': error, 'finished_at': _now()}
        self._safe('итоги запуска', lambda token: self._account.store.update_run(token, self._run_id, fields))

    def _safe(self, what: str, call: Any) -> Any:
        try:
            return call(self._account.token())
        except StoreError as e:
            logger.warning('Не сохранено в кабинет (%s): %s', what, e)
            return None
