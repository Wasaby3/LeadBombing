"""Classic dashboard API (/classic): run, results, downloads and history (parser replaced by fixture items)."""
import json
import time

import pytest

import leadbombing.web.history as history_mod
import leadbombing.web.job as dashboard_job_mod
from fake_store import FakeStore, login
from leadbombing.web import create_app
from test_leads_golden import FIXTURES

GOLDEN = FIXTURES / 'dashboard_golden'
URL = 'https://2gis.ru/moscow/search/Бани'


class FakeParser:
    def __init__(self, url, **kw):
        self.url = url

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def close(self):
        pass

    def parse(self, writer):
        for item in json.loads((FIXTURES / 'catalog_items.json').read_text('utf-8')):
            writer.write({'meta': {'code': 200}, 'result': {'items': [item]}})


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(dashboard_job_mod, 'get_parser', FakeParser)
    monkeypatch.setattr(history_mod, 'user_path', lambda is_config=True: tmp_path / 'user')
    c = create_app(store=FakeStore(), secret_key='test-secret').test_client()
    login(c)
    return c


def run_parse(client) -> dict:
    assert client.post('/api/start', json={'urls': [URL]}).get_json() == {'ok': True}
    for _ in range(200):
        status = client.get('/api/status').get_json()
        if not status['running']:
            return status
        time.sleep(0.02)
    raise AssertionError('run did not finish')


def assert_golden(name: str, data: bytes) -> None:
    golden = GOLDEN / name
    if not golden.exists():  # first run records the reference output of the current code
        GOLDEN.mkdir(parents=True, exist_ok=True)
        golden.write_bytes(data)
        pytest.skip('golden recorded')
    assert data == golden.read_bytes()


def test_pages_are_served(client):
    for path in ('/search', '/leads', '/classic', '/sw.js', '/manifest.webmanifest'):
        assert client.get(path).status_code == 200, path
    assert client.get('/sw.js').headers['Cache-Control'] == 'no-cache'
    old = client.get('/saved')  # the page was renamed: old bookmarks still work
    assert old.status_code in (301, 302) and old.headers['Location'].endswith('/leads')


def test_generator_lists_reference_data(client):
    data = client.get('/api/generator').get_json()
    assert set(data) == {'countries', 'cities', 'rubrics', 'districts'}
    assert any(c['code'] == 'moscow' for c in data['cities'])


def test_start_validation_and_empty_download(client):
    assert client.post('/api/start', json={'urls': []}).status_code == 400
    assert client.get('/api/download?format=csv').status_code == 400
    assert client.get('/api/download?format=doc').status_code == 400


def test_run_results_and_downloads(client):
    status = run_parse(client)
    assert status['status'] == 'done' and status['count'] == 4
    names = [r['name'] for r in client.get('/api/results').get_json()['records']]
    assert names[0] == 'Усадьба Банная' and len(names) == 4
    for fmt, name in (('csv', 'result.csv'), ('json', 'result.json'), ('html', 'result.html')):
        response = client.get(f'/api/download?format={fmt}')
        assert response.status_code == 200, fmt
        assert_golden(name, response.data)
    assert client.get('/api/download?format=xlsx').status_code == 200


def test_failed_link_is_skipped_and_reported(client, monkeypatch):
    class BrokenOnce(FakeParser):
        def parse(self, writer):
            if self.url.endswith('broken'):
                raise RuntimeError('anti-bot timeout')
            super().parse(writer)

    monkeypatch.setattr(dashboard_job_mod, 'get_parser', BrokenOnce)
    assert client.post('/api/start', json={'urls': [URL + '/broken', URL]}).get_json() == {'ok': True}
    for _ in range(200):
        status = client.get('/api/status').get_json()
        if not status['running']:
            break
        time.sleep(0.02)
    logs = '\n'.join(status['logs'])
    assert status['status'] == 'done' and status['count'] == 4
    assert 'Ссылка пропущена из-за ошибки: anti-bot timeout' in logs
    assert 'Готово частично: 1 из 2 ссылок не обработаны.' in logs


def test_history_save_download_merge_delete(client):
    run_parse(client)
    items = client.get('/api/history').get_json()['items']
    assert len(items) == 1
    hid = items[0]['id']
    assert len(client.get(f'/api/history/{hid}/results').get_json()['records']) == 4
    assert client.get(f'/api/history/{hid}/download?format=csv').data == client.get('/api/download?format=csv').data
    assert client.get('/api/history/nope/results').status_code == 404
    merged = client.post('/api/history/merge', json={'ids': [hid]}).get_json()
    assert merged['ok'] and merged['count'] == 4
    assert client.delete(f'/api/history/{hid}').get_json() == {'ok': True}
    assert client.post('/api/clear').get_json() == {'ok': True}
    assert client.get('/api/status').get_json()['status'] == 'idle'
