"""Saved leads by folders: save the current run's leads into a folder, browse folders, export a folder.

A folder lead is a snapshot (table row, card, raw firm data) in Supabase; its hero photo is on disk.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Optional

from ..leads.spheres import get_sphere
from ..logger import logger
from ..paths import user_path
from .leads_api import _SLUG_RE, export_args, run_export, slugs_arg
from .leads_job import LeadsJob, export_raw
from .supabase import SessionExpired, StoreError

_MAX_NAME = 200
_OTHER_SPHERE = 'Это папка другой сферы — выберите папку той же сферы или создайте новую'


def folders_dir() -> Path:
    """Hero photos of saved leads: <dir>/<folder id>/<slug>.jpg."""
    return user_path(is_config=False) / 'folders'


def _hero_path(folder_id: int, slug: str) -> Path:
    return folders_dir() / str(folder_id) / f'{slug}.jpg'


def _read_hero(folder_id: int, slug: str) -> Optional[bytes]:
    path = _hero_path(folder_id, slug)
    return path.read_bytes() if path.is_file() else None


def _store_heroes(folder_id: int, raw: list[dict]) -> None:
    """Copy hero photos next to the folder; a failed copy only loses the photo."""
    for r in raw:
        if not r['hero']:
            continue
        path = _hero_path(folder_id, r['slug'])
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(r['hero'])
        except OSError as e:
            logger.warning('Фото %s не сохранено в папку: %r', r['slug'], e)


def _merge_cities(old: list[dict], new: list[dict]) -> list[dict]:
    known = {c['code'] for c in old}
    return old + [c for c in new if c['code'] not in known]


def _folder_leads(job: LeadsJob, raw: list[dict]) -> list[dict]:
    """Folder rows for the job's firms: table row, card and raw firm data for export."""
    summaries = {e['slug']: e for e in job.events if e['type'] == 'lead'}
    return [{'slug': r['slug'],
             'summary': {**{k: v for k, v in summaries[r['slug']].items() if k != 'type'}, 'has_photo': bool(r['hero'])},
             'card': job.results[r['slug']],
             'raw': {'item': r['item'], 'prices': r['prices']}}
            for r in raw if r['slug'] in summaries and r['slug'] in job.results]


def register(app: Any, job: LeadsJob) -> None:
    from flask import g, jsonify, request, send_file

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

    @app.route('/api/folders')
    def folders_list():
        return with_store(lambda store, token: jsonify({'ok': True, 'folders': store.list_folders(token)}))

    @app.route('/api/folders/save', methods=['POST'])
    def folders_save():
        data = request.get_json(silent=True) or {}
        try:
            raw = job.picked_raw(slugs_arg(data))
        except ValueError as e:
            return fail(str(e))
        leads = _folder_leads(job, raw)
        if not leads or job.writer is None:
            return fail('Нечего сохранять — сначала найдите лиды')
        sphere = job.writer.sphere
        folder_id, name = data.get('folder_id'), str(data.get('name') or '').strip()
        if folder_id is not None and (not isinstance(folder_id, int) or isinstance(folder_id, bool)):
            return fail('Неверная папка')
        if folder_id is None and not name:
            return fail('Введите имя папки')
        if len(name) > _MAX_NAME:
            return fail(f'Имя папки длиннее {_MAX_NAME} символов')

        def save(store: Any, token: str):
            if folder_id is None:
                folder = {'name': name, 'sphere': sphere.id, 'query': sphere.query, 'cities': sphere.cities}
                target = {'id': store.create_folder(token, folder), 'name': name}
            else:
                target = store.get_folder(token, folder_id)
                if not target:
                    return fail('Папка не найдена', 404)
                if target['sphere'] != sphere.id:
                    return fail(_OTHER_SPHERE, 409)
                cities = _merge_cities(target['cities'], sphere.cities)
                if cities != target['cities']:
                    store.update_folder(token, folder_id, {'cities': cities})
            store.add_to_folder(token, target['id'], leads)
            _store_heroes(target['id'], raw)
            return jsonify({'ok': True, 'folder': {'id': target['id'], 'name': target['name']}, 'saved': len(leads)})
        return with_store(save)

    @app.route('/api/folders/<int:folder_id>')
    def folders_leads(folder_id: int):
        return with_store(lambda store, token: jsonify({'ok': True, 'leads': store.folder_leads(token, folder_id)}))

    @app.route('/api/folders/<int:folder_id>/item/<slug>')
    def folders_item(folder_id: int, slug: str):
        if not _SLUG_RE.match(slug):
            return fail('Лид не найден', 404)

        def card(store: Any, token: str):
            found = store.folder_card(token, folder_id, slug)
            return jsonify(found) if found else fail('Лид не найден', 404)
        return with_store(card)

    @app.route('/api/folders/<int:folder_id>/item/<slug>/hero')
    def folders_hero(folder_id: int, slug: str):
        if not _SLUG_RE.match(slug):
            return fail('Нет фото', 404)

        def hero(store: Any, token: str):  # the folder must be the user's own (RLS)
            path = _hero_path(folder_id, slug)
            if not store.get_folder(token, folder_id) or not path.is_file():
                return fail('Нет фото', 404)
            return send_file(path, mimetype='image/jpeg')
        return with_store(hero)

    @app.route('/api/folders/<int:folder_id>/export', methods=['POST'])
    def folders_export(folder_id: int):
        try:
            target, slugs = export_args(request.get_json(force=True, silent=True) or {})
        except ValueError as e:
            return fail(str(e))

        def export(store: Any, token: str):
            folder = store.get_folder(token, folder_id)
            if not folder:
                return fail('Папка не найдена', 404)
            wanted = set(slugs) if slugs is not None else None
            raw = [{**r['raw'], 'slug': r['slug'], 'hero': _read_hero(folder_id, r['slug'])}
                   for r in store.folder_raw(token, folder_id) if wanted is None or r['slug'] in wanted]
            sphere = get_sphere(folder['sphere'], folder['cities'], folder['query'])
            return run_export(lambda: export_raw(target, sphere, raw))
        return with_store(export)
