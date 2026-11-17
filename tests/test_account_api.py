"""Personal account data: settings, run history and found leads saved to the store."""
import pytest

import leadbombing.leads.writer as writer_mod
import leadbombing.web.leads_job as job_mod
from fake_store import FakeStore, login
from leadbombing.web import create_app
from test_leads_api import FakeParser, wait_done
from test_leads_golden import _FixedDate, _Resp


@pytest.fixture()
def store():
    return FakeStore()


@pytest.fixture()
def app(tmp_path, monkeypatch, store):
    monkeypatch.setattr(job_mod, 'get_parser', FakeParser)
    monkeypatch.setattr(job_mod, 'user_path', lambda is_config=True: tmp_path / 'user')
    monkeypatch.setattr(writer_mod, 'date', _FixedDate)
    monkeypatch.setattr(writer_mod.urllib.request, 'urlopen', lambda url, timeout=0: _Resp())
    return create_app(store=store, secret_key='test-secret')


@pytest.fixture()
def client(app):
    c = app.test_client()
    login(c)
    return c


def test_settings_start_empty_and_are_saved(client):
    assert client.get('/api/account/settings').get_json() == {'ok': True, 'settings': {}}
    settings = {'form': {'sphere': 'auto', 'cities': ['kazan'], 'limit': 50}, 'exportPath': '/tmp/leads'}
    assert client.post('/api/account/settings', json={'settings': settings}).get_json() == {'ok': True}
    assert client.get('/api/account/settings').get_json() == {'ok': True, 'settings': settings}


def test_settings_reject_bad_payload(client):
    assert client.post('/api/account/settings', json={'settings': [1, 2]}).status_code == 400
    huge = {'form': {'query': 'x' * 30000}}
    assert client.post('/api/account/settings', json={'settings': huge}).status_code == 400


def test_run_and_leads_are_saved_to_account(client, store):
    assert client.post('/api/leads/start', json={'sphere': 'bani', 'limit': 10}).get_json()['ok']
    wait_done(client)

    runs = client.get('/api/account/runs').get_json()['runs']
    assert len(runs) == 1
    run = runs[0]
    assert (run['sphere'], run['status'], run['accepted'], run['lead_limit']) == ('bani', 'done', 2, 10)
    assert run['skipped'] > 0 and run['cities'] == ['moscow'] and run['finished_at']

    leads = client.get('/api/account/leads').get_json()['leads']
    assert {lead['slug'] for lead in leads} == {'usadba-bannaya', 'hlebnikovskie-bani'}
    assert all(lead['type'] == 'lead' and lead['name'] for lead in leads)
    saved = next(iter(store.leads.values()))
    assert saved['run_id'] == run['id'] and saved['firm_id'].isdigit()


def test_lead_card_comes_from_account_after_restart(app, store):
    first = app.test_client()
    login(first)
    first.post('/api/leads/start', json={'sphere': 'bani', 'limit': 10})
    wait_done(first)

    from leadbombing.web import create_app as fresh_app
    restarted = fresh_app(store=store, secret_key='test-secret').test_client()
    login(restarted)
    card = restarted.get('/api/leads/item/usadba-bannaya').get_json()
    assert card['row']['Баня'] == 'Усадьба Банная' and card['business']['halls']
    assert restarted.get('/api/leads/item/nope').status_code == 404


def test_database_errors_do_not_stop_the_run(client, store):
    store.fail_writes = True
    client.post('/api/leads/start', json={'sphere': 'bani', 'limit': 10})
    s = wait_done(client)
    assert s['status'] == 'done' and len([e for e in s['events'] if e['type'] == 'lead']) == 2
    assert store.runs == [] and store.leads == {}


def test_account_endpoints_report_database_down(client, store):
    store.down = True
    r = client.get('/api/account/runs')
    assert r.status_code == 503 and r.get_json() == {'ok': False, 'error': 'База недоступна'}
