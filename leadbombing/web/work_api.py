"""«Проработать лиды» on «Сохранённые лиды»: work on a folder's leads in one go.

For now it puts each lead's demo app URL: the base URL typed in the window plus "/<slug>", the slug being the
lead's folder slug, which is also its `tenants/<slug>/` folder in an export (see folder_slugs.py). Links typed by
hand and clients are left alone; the folder remembers the base URL so the window opens with it next time.
"""
from __future__ import annotations

from typing import Any

from .folders_api import fail, with_store
from .lead_crm import parse_base_url
from .leads_api import slugs_arg


def register(app: Any) -> None:
    from flask import jsonify, request

    @app.route('/api/folders/<int:folder_id>/work', methods=['POST'])
    def folders_work(folder_id: int):
        data = request.get_json(silent=True) or {}
        try:
            base_url = parse_base_url(data.get('base_url'))
            slugs = slugs_arg(data)
        except ValueError as e:
            return fail(str(e))

        def work(store: Any, token: str):
            if not store.get_folder(token, folder_id):
                return fail('Папка не найдена', 404)
            result = store.fill_demo_urls(token, folder_id, base_url, slugs)
            folder = store.get_folder(token, folder_id) or {}
            return jsonify({'ok': True, 'filled': result['filled'], 'kept': result['kept'],
                            'base_url': folder.get('demo_base_url'), 'filled_at': folder.get('demo_filled_at')})
        return with_store(work)
