"""Clients (the «Клиенты» page): a saved lead made a client with «Перевести в клиенты» leaves its folder's list and
shows here, from all folders, with a client status («Всё ок», «Есть вопрос», «Срочный баг»).

A client stays a row of its folder (snapshot, photo, work on it), so its card, photo, PATCH and DELETE go through
the folder item routes in folders_api.py.
"""
from __future__ import annotations

from typing import Any

from .folders_api import fail, with_store
from .leads_api import _SLUG_RE


def register(app: Any) -> None:
    from flask import jsonify

    @app.route('/api/clients')
    def clients_list():
        return with_store(lambda store, token: jsonify({'ok': True, 'clients': store.list_clients(token)}))

    @app.route('/api/folders/<int:folder_id>/item/<slug>/client', methods=['POST'])
    def folders_item_make_client(folder_id: int, slug: str):
        if not _SLUG_RE.match(slug):
            return fail('Лид не найден', 404)

        def make(store: Any, token: str):
            crm = store.make_client(token, folder_id, slug)
            return jsonify({'ok': True, 'crm': crm}) if crm is not None else fail('Лид не найден', 404)
        return with_store(make)
