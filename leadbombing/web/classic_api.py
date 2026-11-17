"""HTTP API of the classic dashboard (/classic): parse 2GIS links, download results, history."""
from __future__ import annotations

import json
import os
import tempfile
from functools import lru_cache
from typing import Any, Callable

from ..config import Configuration
from ..logger import logger
from ..paths import data_path
from ..writer import WriterOptions, get_writer
from ..writer.writers import write_multisheet_xlsx
from .history import History
from .job import ParseJob

# Sheet name for documents that carry no district label (manual URLs, etc.).
_DEFAULT_SHEET = 'Прочее'

# Download file names per format.
_DOWNLOAD_NAMES = {'csv': '2gis.csv', 'xlsx': '2gis.xlsx',
                   'json': '2gis.json', 'html': '2gis.html'}

# Country code -> human name (for the link generator).
COUNTRIES = {
    'ru': 'Россия', 'kz': 'Казахстан', 'by': 'Беларусь', 'az': 'Азербайджан',
    'kg': 'Киргизия', 'uz': 'Узбекистан', 'cz': 'Чехия', 'eg': 'Египет',
    'it': 'Италия', 'sa': 'Саудовская Аравия', 'cy': 'Кипр', 'ae': 'ОАЭ',
    'cl': 'Чили', 'qa': 'Катар', 'om': 'Оман', 'bh': 'Бахрейн',
    'kw': 'Кувейт', 'iq': 'Ирак',
}


@lru_cache(maxsize=1)
def _load_districts() -> dict[str, list[str]]:
    """District names keyed by city code (for the generator picker)."""
    try:
        with open(data_path() / 'districts.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


@lru_cache(maxsize=1)
def _load_rubrics() -> list[dict[str, Any]]:
    """Flat list of rubrics for the web generator picker."""
    with open(data_path() / 'rubrics.json', 'r', encoding='utf-8') as f:
        rubrics = json.load(f)
    out = []
    for node in rubrics.values():
        # Skip the synthetic root and group headers without a usable label.
        if node.get('code') in (None, '0') or not node.get('label'):
            continue
        out.append({
            'code': node['code'],
            'label': node['label'],
            'is_russian': bool(node.get('isRussian', True)),
            'is_non_russian': bool(node.get('isNonRussian', True)),
        })
    out.sort(key=lambda r: r['label'].lower())
    return out


def _group_by_label(docs: list[Any], labels: Any) -> list[tuple[str, list[Any]]]:
    """Group documents by their district label, preserving first-seen order.

    Documents without a label fall into a single default sheet. Returns a list
    of (sheet_name, docs) pairs.
    """
    labels = list(labels or [])
    labels += [None] * (len(docs) - len(labels))  # tolerate missing/short labels
    order: list[str] = []
    groups: dict[str, list[Any]] = {}
    for doc, label in zip(docs, labels):
        key = label if label else _DEFAULT_SHEET
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(doc)
    return [(k, groups[k]) for k in order]


def _labels_from_request(data: dict[str, Any]) -> dict[str, str]:
    """URL -> district label map from the request's `directions` payload."""
    out: dict[str, str] = {}
    for d in (data.get('directions') or []):
        try:
            url = str(d.get('url', '')).strip()
            label = str(d.get('label', '')).strip()
        except (AttributeError, TypeError):
            continue
        if url and label:
            out[url] = label
    return out


def _build_config(data: dict[str, Any]) -> Configuration:
    """Build a Configuration from the web request payload."""
    config = Configuration()
    config.chrome.headless = bool(data.get('headless', True))
    config.parser.max_records = max(1, int(data.get('max_records', 100)))
    config.writer.csv.clean = bool(data.get('clean', True))

    adv = data.get('advanced', {}) or {}
    if adv:
        config.chrome.disable_images = bool(adv.get('disable_images', config.chrome.disable_images))
        config.chrome.start_maximized = bool(adv.get('start_maximized', config.chrome.start_maximized))
        if adv.get('memory_limit'):
            config.chrome.memory_limit = max(1, int(adv['memory_limit']))
        config.parser.skip_404_response = bool(adv.get('skip_404_response', config.parser.skip_404_response))
        config.parser.delay_between_clicks = max(0, int(adv.get('delay_between_clicks', 0) or 0))
        config.writer.csv.add_rubrics = bool(adv.get('add_rubrics', config.writer.csv.add_rubrics))
        config.writer.csv.add_comments = bool(adv.get('add_comments', config.writer.csv.add_comments))
        config.writer.csv.remove_empty_columns = bool(adv.get('remove_empty_columns', config.writer.csv.remove_empty_columns))
        config.writer.csv.remove_duplicates = bool(adv.get('remove_duplicates', config.writer.csv.remove_duplicates))
        if adv.get('columns_per_entity'):
            config.writer.csv.columns_per_entity = min(5, max(1, int(adv['columns_per_entity'])))
        if adv.get('encoding'):
            config.writer.encoding = str(adv['encoding'])

    f = data.get('filters', {}) or {}
    config.filters.dedup_franchises = bool(f.get('dedup_franchises'))
    config.filters.dedup_across_niches = bool(f.get('dedup_across_niches', True))
    config.filters.require_phone = bool(f.get('require_phone'))
    config.filters.require_whatsapp = bool(f.get('require_whatsapp'))
    config.filters.require_social = bool(f.get('require_social'))
    config.filters.require_email = bool(f.get('require_email'))
    config.filters.require_website = bool(f.get('require_website'))
    config.filters.min_rating = float(f.get('min_rating', 0) or 0)
    config.filters.min_reviews = int(f.get('min_reviews', 0) or 0)
    return config


def _fail(message: str, code: int):
    from flask import jsonify
    return jsonify({'ok': False, 'error': message}), code


def _export_send(docs, writer_opts: WriterOptions, fmt: str, labels=None):
    """Write `docs` to a temp file in `fmt` and send it as a download.

    When district `labels` split the documents into two or more groups, XLSX
    exports place each district on its own worksheet.
    """
    from flask import send_file

    tmp_dir = tempfile.mkdtemp(prefix='p2gis_web_')
    out_path = os.path.join(tmp_dir, _DOWNLOAD_NAMES[fmt])

    groups = _group_by_label(docs, labels)
    # Split into per-district sheets whenever any district label is present,
    # even for a single district (so a partial run still names its sheet).
    has_district = any(name != _DEFAULT_SHEET for name, _ in groups)
    if fmt == 'xlsx' and has_district:
        write_multisheet_xlsx(out_path, groups, writer_opts)
    else:
        with get_writer(out_path, fmt, writer_opts) as writer:
            for doc in docs:
                writer.write(doc)
    return send_file(out_path, as_attachment=True, download_name=_DOWNLOAD_NAMES[fmt])


def _register_run_routes(app: Any, job: ParseJob, load_cities: Callable[[], list[dict[str, Any]]]) -> None:
    from flask import jsonify, request

    @app.route('/api/start', methods=['POST'])
    def api_start():
        data = request.get_json(force=True, silent=True) or {}
        urls = [u.strip() for u in (data.get('urls') or []) if u and u.strip()]
        if not urls:
            return _fail('Не указаны ссылки', 400)
        try:
            config = _build_config(data)
            job.start(config, urls, _labels_from_request(data))
        except RuntimeError as e:
            return _fail(str(e), 409)
        except Exception as e:
            logger.error('Не удалось запустить парсинг: %s', e)
            return _fail(str(e), 400)
        return jsonify({'ok': True})

    @app.route('/api/stop', methods=['POST'])
    def api_stop():
        job.stop()
        return jsonify({'ok': True})

    @app.route('/api/clear', methods=['POST'])
    def api_clear():
        return jsonify({'ok': job.clear()})

    @app.route('/api/status')
    def api_status():
        cursor = request.args.get('cursor', default=0, type=int)
        logs = job.logs[cursor:]
        return jsonify({
            'status': job.status,
            'running': job.running,
            'count': job.count,
            'error': job.error,
            'logs': logs,
            'cursor': cursor + len(logs),
        })

    @app.route('/api/results')
    def api_results():
        return jsonify({'records': job.results()})

    @app.route('/api/generator')
    def api_generator():
        """Data for the link generator: countries, cities, rubrics."""
        cities = [
            {'name': c['name'], 'code': c['code'], 'domain': c['domain'],
             'country_code': c['country_code']}
            for c in load_cities()
        ]
        countries = [{'code': k, 'name': v} for k, v in COUNTRIES.items()]
        countries.sort(key=lambda c: c['name'])
        return jsonify({'countries': countries, 'cities': cities,
                        'rubrics': _load_rubrics(), 'districts': _load_districts()})

    @app.route('/api/download')
    def api_download():
        fmt = request.args.get('format', 'csv')
        if fmt not in _DOWNLOAD_NAMES:
            return _fail('Неизвестный формат', 400)
        if not job.count:
            return _fail('Нет данных', 400)

        try:
            assert job.collector is not None
            return _export_send(job.collector.docs, job.collector._options, fmt,
                                job.collector.labels)
        except Exception as e:
            logger.error('Ошибка экспорта: %s', e)
            return _fail(str(e), 500)


def _register_history_routes(app: Any, history: History) -> None:
    from flask import jsonify, request

    @app.route('/api/history')
    def api_history():
        return jsonify({'items': history.list()})

    @app.route('/api/history/<hid>/results')
    def api_history_results(hid):
        docs = history.docs(hid)
        if docs is None:
            return _fail('Запись не найдена', 404)
        return jsonify({'records': history.records(hid)})

    @app.route('/api/history/<hid>/download')
    def api_history_download(hid):
        fmt = request.args.get('format', 'csv')
        if fmt not in _DOWNLOAD_NAMES:
            return _fail('Неизвестный формат', 400)
        docs = history.docs(hid)
        if not docs:
            return _fail('Запись не найдена', 404)
        try:
            opts = WriterOptions(**history.writer_options(hid))
        except Exception:
            opts = WriterOptions()
        try:
            return _export_send(docs, opts, fmt, history.labels(hid))
        except Exception as e:
            logger.error('Ошибка экспорта истории: %s', e)
            return _fail(str(e), 500)

    @app.route('/api/history/merge', methods=['POST'])
    def api_history_merge():
        data = request.get_json(force=True, silent=True) or {}
        ids = [str(i) for i in (data.get('ids') or [])]
        if not ids:
            return _fail('Не выбраны записи', 400)
        result = history.merge_and_save(ids)
        if not result:
            return _fail('Нет данных для объединения', 400)
        new_id, count = result
        return jsonify({'ok': True, 'id': new_id, 'count': count})

    @app.route('/api/history/<hid>', methods=['DELETE'])
    def api_history_delete(hid):
        return jsonify({'ok': history.delete(hid)})


def register(app: Any, load_cities: Callable[[], list[dict[str, Any]]]) -> ParseJob:
    """Add the classic dashboard API to `app`; one parse job and its history per app."""
    job = ParseJob()
    _register_run_routes(app, job, load_cities)
    _register_history_routes(app, History())
    return job
