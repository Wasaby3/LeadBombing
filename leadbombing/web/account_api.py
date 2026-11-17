"""Personal account API: saved settings, run history and found leads of the logged-in user."""
from __future__ import annotations

import json
from typing import Any, Callable

from .supabase import SessionExpired, StoreError

_MAX_SETTINGS_BYTES = 20_000
_DEFAULT_LIMIT = 200
_MAX_LIMIT = 1000


def register(app: Any) -> None:
    from flask import g, jsonify, request

    def fail(message: str, code: int = 400):
        return jsonify({'ok': False, 'error': message}), code

    def with_store(call: Callable[[Any, str], Any]):
        """Run `call(store, token)` for the current account and map database errors to responses."""
        try:
            return call(g.account.store, g.account.token())
        except SessionExpired as e:
            return fail(str(e), 401)
        except StoreError as e:
            return fail(str(e), 503)

    def limit_arg() -> int:
        return min(_MAX_LIMIT, max(1, request.args.get('limit', default=_DEFAULT_LIMIT, type=int)))

    @app.route('/api/account/settings')
    def account_settings():
        return with_store(lambda store, token: jsonify({'ok': True, 'settings': store.get_settings(token)}))

    @app.route('/api/account/settings', methods=['POST'])
    def account_save_settings():
        settings = (request.get_json(silent=True) or {}).get('settings')
        if not isinstance(settings, dict):
            return fail('Настройки должны быть объектом')
        if len(json.dumps(settings, ensure_ascii=False).encode('utf-8')) > _MAX_SETTINGS_BYTES:
            return fail('Настройки слишком большие')

        def save(store: Any, token: str):
            store.save_settings(token, settings)
            return jsonify({'ok': True})
        return with_store(save)

    @app.route('/api/account/runs')
    def account_runs():
        return with_store(lambda store, token: jsonify({'ok': True, 'runs': store.list_runs(token, limit_arg())}))

    @app.route('/api/account/leads')
    def account_leads():
        def leads(store: Any, token: str):
            rows = store.list_leads(token, limit_arg())
            return jsonify({'ok': True, 'leads': [{**r['summary'], 'sphere': r['sphere']} for r in rows]})
        return with_store(leads)
