"""HTTP API of the leads PWA: start/stop a run, live status, lead cards, folder export."""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Optional

from ..leads.spheres import sphere_list
from ..logger import logger
from .account import RunRecorder
from .leads_job import LeadsJob
from .supabase import StoreError

_SLUG_RE = re.compile(r'^[a-z0-9_-]{1,60}$')
_PICK_TIMEOUT_S = 300
_MAX_LIMIT = 2000
_MAX_CITIES = 30


def pick_folder() -> str:
    """Native folder dialog (macOS). Returns '' when cancelled."""
    if sys.platform != 'darwin':
        raise RuntimeError('Окно выбора папки есть только на macOS — впишите путь вручную')
    script = 'POSIX path of (choose folder with prompt "Куда выгрузить лиды?")'
    res = subprocess.run(['osascript', '-e', script], capture_output=True, text=True, timeout=_PICK_TIMEOUT_S)
    return res.stdout.strip() if res.returncode == 0 else ''


def slugs_arg(data: dict) -> Optional[list[str]]:
    """Optional `slugs` list of a request body; ValueError when malformed."""
    slugs = data.get('slugs')
    if slugs is not None and (not isinstance(slugs, list) or not all(_SLUG_RE.match(str(x)) for x in slugs)):
        raise ValueError('Неверный список лидов')
    return slugs


def export_args(data: dict) -> tuple[Path, Optional[list[str]]]:
    """Target folder and optional slugs of an export request; ValueError with a user message when invalid."""
    raw_path = str(data.get('path') or '').strip()
    if not raw_path:
        raise ValueError('Выберите папку')
    target = Path(raw_path).expanduser()
    if not target.is_absolute():
        raise ValueError('Нужен полный путь к папке')
    return target, slugs_arg(data)


def run_export(export: Callable[[], dict]) -> Any:
    """Run an export and map its errors to JSON responses."""
    from flask import jsonify

    try:
        return jsonify({'ok': True, **export()})
    except RuntimeError as e:
        return jsonify({'ok': False, 'error': str(e)}), 409
    except OSError as e:
        logger.error('Выгрузка не удалась: %r', e)
        return jsonify({'ok': False, 'error': f'Не удалось записать в папку: {e.strerror or e}'}), 500


def register(app: Any, load_cities: Callable[[], list[dict]]) -> LeadsJob:
    from flask import g, jsonify, request, send_file

    job = LeadsJob()

    def fail(message: str, code: int = 400):
        return jsonify({'ok': False, 'error': message}), code

    def city_by_code(code: str) -> dict | None:
        return next(({'code': c['code'], 'name': c['name'], 'domain': c['domain']}
                     for c in load_cities() if c['code'] == code), None)

    @app.route('/api/leads/meta')
    def leads_meta():
        cities = [{'code': c['code'], 'name': c['name'], 'domain': c['domain']}
                  for c in load_cities() if c.get('country_code') == 'ru']
        cities.sort(key=lambda c: (c['code'] not in ('moscow', 'spb'), c['name']))
        return jsonify({'spheres': sphere_list(), 'cities': cities})

    @app.route('/api/leads/start', methods=['POST'])
    def leads_start():
        data = request.get_json(force=True, silent=True) or {}
        codes = data.get('cities') or [data.get('city') or 'moscow']
        if not isinstance(codes, list) or len(codes) > _MAX_CITIES:
            return fail(f'Выберите от 1 до {_MAX_CITIES} городов')
        cities = [city_by_code(str(code)) for code in codes]
        if not cities or None in cities:
            return fail('Неизвестный город')
        try:
            limit = min(_MAX_LIMIT, max(1, int(data.get('limit') or 100)))
            job.start(str(data.get('sphere') or 'bani'), cities, str(data.get('query') or ''), limit,
                      headless=bool(data.get('headless', True)), recorder=RunRecorder(g.account))
        except (ValueError, RuntimeError) as e:
            return fail(str(e), 409 if isinstance(e, RuntimeError) else 400)
        return jsonify({'ok': True})

    @app.route('/api/leads/stop', methods=['POST'])
    def leads_stop():
        job.stop()
        return jsonify({'ok': True})

    @app.route('/api/leads/resume', methods=['POST'])
    def leads_resume():
        data = request.get_json(force=True, silent=True) or {}
        try:
            limit = min(_MAX_LIMIT, max(1, int(data['limit']))) if data.get('limit') else None
            job.resume(limit, headless=bool(data.get('headless', True)))
        except (ValueError, TypeError):
            return fail('Неверный лимит')
        except RuntimeError as e:
            return fail(str(e), 409)
        return jsonify({'ok': True})

    @app.route('/api/leads/clear', methods=['POST'])
    def leads_clear():
        try:
            job.clear()
        except RuntimeError as e:
            return fail(str(e), 409)
        return jsonify({'ok': True})

    @app.route('/api/leads/status')
    def leads_status():
        return jsonify(job.snapshot(request.args.get('cursor', default=0, type=int)))

    def saved_card(slug: str) -> dict | None:
        """A lead from an earlier run (e.g. before a server restart), from the user's account."""
        try:
            return g.account.store.find_lead(g.account.token(), slug)
        except StoreError as e:
            logger.warning('Карточка из кабинета: %s', e)
            return None

    @app.route('/api/leads/item/<slug>')
    def leads_item(slug: str):
        if not _SLUG_RE.match(slug):
            return fail('Лид не найден', 404)
        result = job.results.get(slug) or saved_card(slug)
        return jsonify(result) if result else fail('Лид не найден', 404)

    @app.route('/api/leads/item/<slug>/hero')
    def leads_hero(slug: str):
        if not _SLUG_RE.match(slug) or slug not in job.results or not job.staging:
            return fail('Нет фото', 404)
        path = job.staging / 'tenants' / slug / 'images' / 'hero.jpg'
        return send_file(path, mimetype='image/jpeg') if path.is_file() else fail('Нет фото', 404)

    @app.route('/api/leads/pick-folder', methods=['POST'])
    def leads_pick_folder():
        try:
            return jsonify({'ok': True, 'path': pick_folder()})
        except (RuntimeError, subprocess.SubprocessError) as e:
            return fail(str(e))

    @app.route('/api/leads/export', methods=['POST'])
    def leads_export():
        try:
            target, slugs = export_args(request.get_json(force=True, silent=True) or {})
        except ValueError as e:
            return fail(str(e))
        return run_export(lambda: job.export(target, slugs))

    @app.route('/api/leads/open-folder', methods=['POST'])
    def leads_open_folder():
        path = Path(str((request.get_json(force=True, silent=True) or {}).get('path') or '')).expanduser()
        if not path.is_dir():
            return fail('Папка не найдена', 404)
        subprocess.Popen(['open' if sys.platform == 'darwin' else 'xdg-open', str(path)])
        return jsonify({'ok': True})

    return job
