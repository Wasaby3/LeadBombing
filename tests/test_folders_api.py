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


def saved_folder(client, slugs=None):
    run(client, sphere='bani')
    body = {'name': 'Бани', **({'slugs': slugs} if slugs else {})}
    return client.post('/api/folders/save', json=body).get_json()['folder']['id']


def test_lead_work_is_saved_shown_in_list_and_card(client):
    folder_id = saved_folder(client)
    item = f'/api/folders/{folder_id}/item/usadba-bannaya'
    leads = client.get(f'/api/folders/{folder_id}').get_json()['leads']
    assert [(lead['status'], lead['priority']) for lead in leads] == [('new', 0), ('new', 0)]
    assert client.get(item).get_json()['crm']['status'] == 'new'

    contact = {'title': 'Телефон', 'value': '+7 495 000-00-00'}
    r = client.patch(item, json={'status': 'waiting', 'priority': 3, 'comment': 'звонил, перезвонить',
                                 'contacted': [contact], 'demo_url': 'https://demo.example/usadba'}).get_json()
    assert r == {'ok': True, 'crm': {'status': 'waiting', 'priority': 3, 'comment': 'звонил, перезвонить',
                                     'contacted': [contact], 'demo_url': 'https://demo.example/usadba',
                                     'demo_source': 'manual'}}
    assert client.patch(item, json={'status': 'client'}).get_json()['crm']['comment'] == 'звонил, перезвонить'

    card = client.get(item).get_json()
    assert card['crm']['status'] == 'client' and card['row']['Баня'] == 'Усадьба Банная'
    leads = client.get(f'/api/folders/{folder_id}').get_json()['leads']
    assert (leads[0]['slug'], leads[0]['status'], leads[0]['priority']) == ('usadba-bannaya', 'client', 3)


def test_resaving_a_lead_keeps_its_work(client):
    folder_id = saved_folder(client, ['usadba-bannaya'])
    item = f'/api/folders/{folder_id}/item/usadba-bannaya'
    client.patch(item, json={'status': 'lost', 'comment': 'не интересно'})
    assert client.post('/api/folders/save', json={'folder_id': folder_id}).get_json()['saved'] == 2
    crm = client.get(item).get_json()['crm']
    assert (crm['status'], crm['comment']) == ('lost', 'не интересно')


def test_bad_lead_change_is_refused(client):
    folder_id = saved_folder(client)
    item = f'/api/folders/{folder_id}/item/usadba-bannaya'
    r = client.patch(item, json={'status': 'won'})
    assert r.status_code == 400 and 'статус' in r.get_json()['error']
    assert client.patch(item, data='not json', content_type='application/json').status_code == 400
    assert client.patch(f'/api/folders/{folder_id}/item/nope', json={'status': 'lost'}).status_code == 404
    assert client.patch(f'/api/folders/{folder_id + 99}/item/usadba-bannaya', json={'status': 'lost'}).status_code == 404
    assert client.patch(f'/api/folders/{folder_id}/item/BAD!', json={'status': 'lost'}).status_code == 404


def test_deleted_lead_leaves_folder_with_its_photo(client, tmp_path):
    folder_id = saved_folder(client)
    item = f'/api/folders/{folder_id}/item/usadba-bannaya'
    hero = tmp_path / 'user' / 'folders' / str(folder_id) / 'usadba-bannaya.jpg'
    assert hero.is_file()

    assert client.delete(item).get_json() == {'ok': True}
    assert not hero.exists()
    assert client.get(item).status_code == 404
    assert [lead['slug'] for lead in client.get(f'/api/folders/{folder_id}').get_json()['leads']] == [
        'hlebnikovskie-bani']
    assert client.get('/api/folders').get_json()['folders'][0]['count'] == 1
    assert client.delete(item).status_code == 404
