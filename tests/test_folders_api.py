"""Saved leads by folders: save from a run, add to an existing folder, card, photo and export like the search page."""
import pytest

import leadbombing.leads.writer as writer_mod
import leadbombing.web.folders_api as folders_mod
import leadbombing.web.leads_job as job_mod
from fake_store import FakeStore, login
from leadbombing.web import create_app
from test_leads_api import FakeParser, wait_done
from test_leads_golden import GOLDEN, tree, _FixedDate, _Resp


@pytest.fixture()
def client(tmp_path, monkeypatch):
    user_dir = lambda is_config=True: tmp_path / 'user'  # noqa: E731
    monkeypatch.setattr(job_mod, 'get_parser', FakeParser)
    monkeypatch.setattr(job_mod, 'user_path', user_dir)
    monkeypatch.setattr(folders_mod, 'user_path', user_dir)
    monkeypatch.setattr(writer_mod, 'date', _FixedDate)
    monkeypatch.setattr(writer_mod.urllib.request, 'urlopen', lambda url, timeout=0: _Resp())
    c = create_app(store=FakeStore(), secret_key='test-secret').test_client()
    login(c)
    return c


def run(client, **body):
    assert client.post('/api/leads/start', json={'limit': 10, **body}).get_json()['ok']
    wait_done(client)


def test_bani_folder_keeps_card_photo_and_exports_like_search(client, tmp_path):
    run(client, sphere='bani')
    assert client.post('/api/folders/save', json={'name': ' '}).status_code == 400
    r = client.post('/api/folders/save', json={'name': 'Бани', 'slugs': ['usadba-bannaya']}).get_json()
    assert r['saved'] == 1
    folder_id = r['folder']['id']
    r = client.post('/api/folders/save', json={'folder_id': folder_id}).get_json()  # all, the first one again
    assert r == {'ok': True, 'folder': {'id': folder_id, 'name': 'Бани'}, 'saved': 2}

    folders = client.get('/api/folders').get_json()['folders']
    assert [(f['name'], f['sphere'], f['count']) for f in folders] == [('Бани', 'bani', 2)]
    leads = client.get(f'/api/folders/{folder_id}').get_json()['leads']
    assert [lead['slug'] for lead in leads] == ['usadba-bannaya', 'hlebnikovskie-bani'] and leads[0]['has_photo']
    card = client.get(f'/api/folders/{folder_id}/item/usadba-bannaya').get_json()
    assert card['row']['Баня'] == 'Усадьба Банная'
    assert client.get(f'/api/folders/{folder_id}/item/usadba-bannaya/hero').status_code == 200
    assert client.get(f'/api/folders/{folder_id + 99}/item/usadba-bannaya/hero').status_code == 404

    run(client, sphere='custom', query='бани', cities=['moscow'])  # a new run wipes the run folder
    assert client.post('/api/folders/save', json={'folder_id': folder_id}).status_code == 409  # other sphere

    out = tmp_path / 'export'
    r = client.post(f'/api/folders/{folder_id}/export', json={'path': str(out)}).get_json()
    assert r['ok'] and r['added'] == 2
    assert tree(out) == tree(GOLDEN)


def test_free_search_folder_exports_like_search(client, tmp_path):
    run(client, sphere='custom', query='бани', cities=['moscow', 'spb'])
    folder_id = client.post('/api/folders/save', json={'name': 'бани'}).get_json()['folder']['id']
    picked = {'path': str(tmp_path / 'from-search'), 'slugs': ['hlebnikovskie-bani', 'fitnes-klub-sila']}
    assert client.post('/api/leads/export', json=picked).get_json()['ok']
    from_folder = {**picked, 'path': str(tmp_path / 'from-folder')}
    assert client.post(f'/api/folders/{folder_id}/export', json=from_folder).get_json()['ok']
    assert tree(tmp_path / 'from-folder') == tree(tmp_path / 'from-search')
