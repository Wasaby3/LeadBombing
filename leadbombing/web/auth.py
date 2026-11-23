"""Login to the personal account: /api/auth/* and the guard that closes the rest of the API without a session."""
from __future__ import annotations

from typing import Any, Optional

from ..logger import logger
from .account import Account, Accounts
from .supabase import AccessDenied, InvalidCredentials, StoreError

_PUBLIC_API = '/api/auth/'
_PROTECTED_PAGES = ('/classic',)
_MAX_FIELD_LEN = 200


def register(app: Any, accounts: Accounts) -> None:
    from flask import g, jsonify, redirect, request, session

    def fail(message: str, code: int):
        return jsonify({'ok': False, 'error': message}), code

    def load_account() -> Optional[Account]:
        user_id, refresh_token = session.get('uid'), session.get('rt')
        if not user_id:
            return None
        account = accounts.get(user_id)
        if account is None and refresh_token:
            try:
                account = accounts.restore(user_id, refresh_token)
            except StoreError as e:
                logger.info('Сессия не восстановлена: %s', e)
        if account is None:
            session.clear()
            return None
        if session.get('rt') != account.refresh_token:
            session['rt'] = account.refresh_token
        return account

    @app.before_request
    def require_login():
        path = request.path
        if path.startswith(_PUBLIC_API) or not (path.startswith('/api/') or path in _PROTECTED_PAGES):
            return None
        account = load_account()
        if account is None:
            return redirect('/search') if path in _PROTECTED_PAGES else fail('Нужно войти', 401)
        g.account = account
        return None

    @app.route('/api/auth/login', methods=['POST'])
    def auth_login():
        data = request.get_json(silent=True)
        login = data.get('login') if isinstance(data, dict) else None
        password = data.get('password') if isinstance(data, dict) else None
        if not isinstance(login, str) or not isinstance(password, str) or not login.strip() or not password \
                or len(login) > _MAX_FIELD_LEN or len(password) > _MAX_FIELD_LEN:
            return fail('Введите логин и пароль', 400)
        try:
            account = accounts.sign_in(login.strip().lower(), password)
        except InvalidCredentials as e:
            return fail(str(e), 401)
        except AccessDenied as e:
            return fail(str(e), 403)
        except StoreError as e:
            return fail(str(e), 503)
        session.clear()
        session.permanent = True
        session['uid'], session['rt'] = account.user_id, account.refresh_token
        logger.info('Вход в кабинет: %s', account.login)
        return jsonify({'ok': True, 'login': account.login})

    @app.route('/api/auth/logout', methods=['POST'])
    def auth_logout():
        user_id = session.get('uid')
        session.clear()
        if user_id:
            accounts.sign_out(user_id)
        return jsonify({'ok': True})

    @app.route('/api/auth/me')
    def auth_me():
        account = load_account()
        return jsonify({'ok': True, 'login': account.login}) if account else fail('Нужно войти', 401)
