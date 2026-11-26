"""Настройки → «Статусы лидов»: create, rename, recolor, and delete a lead status. The rules (limit, protected
ids, the cascade on delete) are in lead_statuses.py; the actual reads/writes are store methods (supabase.py /
tests/fake_store.py).
"""
from __future__ import annotations

from typing import Any

from .folders_api import fail, with_store
from .lead_statuses import MAX_STATUSES, default_name, pick_unused_color, validate_color, validate_name


def register(app: Any) -> None:
    from flask import jsonify, request

    @app.route('/api/account/lead-statuses')
    def lead_statuses_list():
        return with_store(lambda store, token: jsonify({'ok': True, 'statuses': store.list_lead_statuses(token)}))

    @app.route('/api/account/lead-statuses', methods=['POST'])
    def lead_statuses_create():
        data = request.get_json(silent=True) or {}

        def create(store: Any, token: str):
            existing = store.list_lead_statuses(token)
            if len(existing) >= MAX_STATUSES:
                return fail(f'Статусов не больше {MAX_STATUSES}')
            # «Добавить статус» adds one right away with a default name/color; the UI never prompts for them.
            try:
                name = validate_name(data['name'], existing) if 'name' in data else default_name(existing)
                color = validate_color(data['color']) if 'color' in data else pick_unused_color(existing)
            except ValueError as e:
                return fail(str(e))
            return jsonify({'ok': True, 'status': store.create_lead_status(token, name, color)})
        return with_store(create)

    @app.route('/api/account/lead-statuses/<status_id>', methods=['PATCH'])
    def lead_statuses_update(status_id: str):
        data = request.get_json(silent=True) or {}

        def update(store: Any, token: str):
            existing = store.list_lead_statuses(token)
            fields: dict = {}
            try:
                if 'name' in data:
                    fields['name'] = validate_name(data['name'], existing, exclude_id=status_id)
                if 'color' in data:
                    fields['color'] = validate_color(data['color'])
            except ValueError as e:
                return fail(str(e))
            if not fields:
                return fail('Нечего сохранять')
            updated = store.update_lead_status(token, status_id, fields)
            return jsonify({'ok': True, 'status': updated}) if updated else fail('Статус не найден', 404)
        return with_store(update)

    @app.route('/api/account/lead-statuses/<status_id>', methods=['DELETE'])
    def lead_statuses_delete(status_id: str):
        def delete(store: Any, token: str):
            try:
                deleted = store.delete_lead_status(token, status_id)
            except ValueError as e:
                return fail(str(e))
            return jsonify({'ok': True}) if deleted else fail('Статус не найден', 404)
        return with_store(delete)
