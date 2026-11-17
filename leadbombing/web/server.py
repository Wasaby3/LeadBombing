from __future__ import annotations

import json
import os
import secrets
import webbrowser
from datetime import timedelta
from functools import lru_cache
from typing import Any, Optional

from ..logger import logger
from ..paths import data_path, user_path
from .account import Accounts
from .account_api import register as register_account
from .auth import register as register_auth
from .classic_api import register as register_classic
from .folders_api import register as register_folders
from .leads_api import register as register_leads
from .supabase import store_from_env

_SESSION_DAYS = 30
_SECRET_ENV = 'LEADBOMBING_SECRET_KEY'


@lru_cache(maxsize=1)
def _load_cities() -> list[dict[str, Any]]:
    with open(data_path() / 'cities.json', 'r', encoding='utf-8') as f:
        return json.load(f)


def _secret_key() -> str:
    """Session signing key: from the environment, else generated once into the user config dir."""
    if os.environ.get(_SECRET_ENV):
        return os.environ[_SECRET_ENV]
    path = user_path() / 'secret_key'
    if path.is_file():
        return path.read_text('utf-8').strip()
    path.parent.mkdir(parents=True, exist_ok=True)
    key = secrets.token_hex(32)
    path.touch(mode=0o600)
    path.write_text(key, 'utf-8')
    return key


def create_app(store: Optional[Any] = None, secret_key: Optional[str] = None):
    """Create the Flask app: the leads app at `/search`, `/saved`, `/profile`, `/settings`, `/docs`, the classic dashboard at
    `/classic`.

    Everything under /api/ (except /api/auth/*) needs a login; `store` is the Supabase account store.
    """
    try:
        from flask import Flask, redirect, send_from_directory
    except ImportError as e:  # pragma: no cover
        raise ImportError(
            'Для веб-интерфейса нужен Flask. Установите: pip install -e .'
        ) from e

    static_dir = os.path.join(os.path.dirname(__file__), 'static')
    app = Flask(__name__, static_folder=static_dir, static_url_path='/static')
    app_dir = os.path.join(static_dir, 'app')
    app.config.update(SECRET_KEY=secret_key or _secret_key(), SESSION_COOKIE_HTTPONLY=True,
                      SESSION_COOKIE_SAMESITE='Lax', PERMANENT_SESSION_LIFETIME=timedelta(days=_SESSION_DAYS))
    register_auth(app, Accounts(store or store_from_env()))
    register_account(app)
    register_folders(app, register_leads(app, _load_cities))
    register_classic(app, _load_cities)

    @app.route('/')
    def index():
        return redirect('/search')

    @app.route('/search')
    @app.route('/saved')
    @app.route('/profile')
    @app.route('/settings')
    @app.route('/docs')
    def app_page():  # one SPA shell; the page is picked from the URL in app.js
        return send_from_directory(app_dir, 'index.html')

    @app.route('/sw.js')
    def service_worker():  # served from the root so it controls the whole app
        response = send_from_directory(app_dir, 'sw.js', mimetype='text/javascript')
        response.headers['Cache-Control'] = 'no-cache'
        return response

    @app.route('/manifest.webmanifest')
    def manifest():
        return send_from_directory(app_dir, 'manifest.webmanifest', mimetype='application/manifest+json')

    @app.route('/classic')
    def classic():
        return send_from_directory(static_dir, 'index.html')

    return app


def run_server(host: str = '127.0.0.1', port: int = 8666, open_browser: bool = True) -> None:
    """Run the dashboard server (blocking)."""
    app = create_app()
    url = f'http://{host}:{port}/'
    logger.info('Веб-интерфейс запущен: %s', url)
    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    app.run(host=host, port=port, threaded=True, debug=False, use_reloader=False)
