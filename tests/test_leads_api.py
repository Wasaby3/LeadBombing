"""Leads API: live events, lead card, export into a folder (parser replaced by fixture items)."""
import json
import time

import pytest

import leadbombing.web.leads_job as job_mod
from fake_store import FakeStore, login
from leadbombing.web import create_app
from test_leads_golden import FIXTURES, GOLDEN, tree, _FixedDate, _Resp
import leadbombing.leads.writer as writer_mod


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
        data = json.loads((FIXTURES / 'bani_items.json').read_text('utf-8'))
        writer.fetch_state = lambda path, expr: data['prices'].get(path.split('/')[2])
        for item in data['items']:
            writer.write({'result': {'items': [item]}})


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(job_mod, 'get_parser', FakeParser)
    monkeypatch.setattr(job_mod, 'user_path', lambda is_config=True: tmp_path / 'user')
    monkeypatch.setattr(writer_mod, 'date', _FixedDate)
    monkeypatch.setattr(writer_mod.urllib.request, 'urlopen', lambda url, timeout=0: _Resp())
    c = create_app(store=FakeStore(), secret_key='test-secret').test_client()
    login(c)
    return c


def wait_done(client):
    for _ in range(200):
        s = client.get('/api/leads/status?cursor=0').get_json()
        if s["status"] != "running":
            return s
        time.sleep(0.02)
    raise AssertionError('run did not finish')


def test_run_card_and_export_match_bani_format(client, tmp_path):
    assert client.get('/search').status_code == 200 and client.get('/sw.js').status_code == 200
    assert client.get('/docs').status_code == 200
    meta = client.get('/api/leads/meta').get_json()
    assert meta['spheres'][0]['id'] == 'bani' and meta['cities'][0]['code'] == 'moscow'

    assert client.post('/api/leads/start', json={'sphere': 'bani', 'city': 'spb', 'limit': 10}).get_json()['ok']
    s = wait_done(client)
    leads = [e for e in s['events'] if e['type'] == 'lead']
    assert s['status'] == 'done' and [l['slug'] for l in leads] == ['usadba-bannaya', 'hlebnikovskie-bani']
    assert {e['reason'] for e in s['events'] if e['type'] == 'skip'} >= {'не Москва', 'дубль'}

    card = client.get('/api/leads/item/usadba-bannaya').get_json()
    assert card['row']['Баня'] == 'Усадьба Банная' and card['business']['halls']
    assert [(c['title'], c['value'], c['label'], c['label_source']) for c in card['contacts']] == [
        ('Телефон', '+7 958 775-20-88', 'для бронирования', 'default'),
        ('Телефон', '+7 499 111-25-70', 'для бронирования', 'default'),
        ('WhatsApp', 'https://wa.me/79587752088', 'для бронирования', 'default'),
        ('Telegram', 'https://t.me/+79035490939', 'для бронирования', 'default'),
        ('Email', 'info@usadba.ru', 'почта фирмы', 'default')]
    assert card['legal'] == {'name': 'ООО Усадьба', 'owner': None}
    assert client.get('/api/leads/item/usadba-bannaya/hero').status_code == 200
    assert client.get('/api/leads/item/..%2F..%2Fetc').status_code == 404

    out = tmp_path / 'export'
    r = client.post('/api/leads/export', json={'path': str(out)}).get_json()
    assert r['ok'] and r['added'] == 2
    assert tree(out) == tree(GOLDEN)


def test_export_refuses_other_sphere_folder_and_relative_path(client, tmp_path):
    client.post('/api/leads/start', json={'sphere': 'bani', 'limit': 10})
    wait_done(client)
    other = tmp_path / 'auto'
    other.mkdir()
    (other / 'outreach.csv').write_text('﻿Название,Демо (slug)\n', 'utf-8')
    assert client.post('/api/leads/export', json={'path': str(other)}).status_code == 409
    assert client.post('/api/leads/export', json={'path': 'relative/dir'}).status_code == 400


def test_free_search_in_two_cities_exports_only_selected(client, tmp_path):
    from leadbombing.leads.generic import COLUMNS
    assert client.post('/api/leads/start', json={'sphere': 'custom', 'query': '', 'cities': ['moscow']}).status_code == 400
    r = client.post('/api/leads/start', json={'sphere': 'custom', 'query': 'бани', 'cities': ['moscow', 'spb'], 'limit': 10})
    assert r.get_json()['ok']
    s = wait_done(client)
    slugs = [e['slug'] for e in s['events'] if e['type'] == 'lead']
    assert slugs == ['usadba-bannaya', 'hlebnikovskie-bani', 'fitnes-klub-sila']  # no rubric filter in free search
    assert s['summary']['skipped']['не из выбранных городов'] == 1

    out = tmp_path / 'picked'
    r = client.post('/api/leads/export', json={'path': str(out), 'slugs': ['hlebnikovskie-bani']}).get_json()
    assert r['ok'] and r['added'] == 1
    assert [p.name for p in (out / 'tenants').iterdir()] == ['hlebnikovskie-bani']
    assert (out / 'outreach.csv').read_text('utf-8-sig').splitlines()[0] == ','.join(COLUMNS)
    assert client.post('/api/leads/export', json={'path': str(out), 'slugs': ['../x']}).status_code == 400
