"""SupabaseStore against the local Supabase (supabase start). Skipped when it is not running."""
import uuid

import pytest
import requests

from leadbombing.web.supabase import InvalidCredentials, SessionExpired, store_from_env

store = store_from_env()
SPHERE = f'it-{uuid.uuid4().hex[:8]}'


def _reachable() -> bool:
    try:
        store.sign_in('admin', 'admin')
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _reachable(), reason='локальный Supabase не запущен')


@pytest.fixture()
def token():
    session = store.sign_in('admin', 'admin')
    yield session.access_token
    headers = {'apikey': store._key, 'Authorization': f'Bearer {session.access_token}'}
    for table in ('leads', 'runs', 'folders'):
        requests.delete(f'{store._url}/rest/v1/{table}', params={'sphere': f'eq.{SPHERE}'}, headers=headers,
                        timeout=10)


def test_admin_logs_in_and_wrong_password_fails():
    session = store.sign_in('admin', 'admin')
    assert session.login == 'admin' and session.access_token and session.refresh_token
    assert store.refresh(session.refresh_token).user_id == session.user_id
    with pytest.raises(InvalidCredentials):
        store.sign_in('admin', 'wrong')
    with pytest.raises(SessionExpired):
        store.refresh('not-a-token')


def test_settings_round_trip(token):
    before = store.get_settings(token)
    try:
        store.save_settings(token, {'probe': SPHERE})
        assert store.get_settings(token) == {'probe': SPHERE}
    finally:
        store.save_settings(token, before)


def test_run_and_lead_are_saved_and_found(token):
    run_id = store.create_run(token, {'sphere': SPHERE, 'query': 'Бани', 'cities': ['moscow'], 'lead_limit': 5})
    store.update_run(token, run_id, {'status': 'done', 'accepted': 1, 'skipped': 2})
    run = next(r for r in store.list_runs(token, 20) if r['id'] == run_id)
    assert (run['status'], run['accepted'], run['skipped'], run['cities']) == ('done', 1, 2, ['moscow'])

    slug = f'{SPHERE}-lead'
    lead = {'sphere': SPHERE, 'firm_id': '70000001', 'slug': slug, 'run_id': run_id,
            'summary': {'type': 'lead', 'slug': slug, 'name': 'Тест'}, 'card': {'row': {'Название': 'Тест'}}}
    store.save_lead(token, lead)
    store.save_lead(token, {**lead, 'card': {'row': {'Название': 'Тест 2'}}})  # upsert, not a duplicate
    assert store.find_lead(token, slug) == {'row': {'Название': 'Тест 2'}}
    assert [r['slug'] for r in store.list_leads(token, 1000) if r['sphere'] == SPHERE] == [slug]


def test_folder_round_trip(token):
    cities = [{'code': 'moscow', 'name': 'Москва', 'domain': 'ru'}]
    folder_id = store.create_folder(token, {'name': 'Тест', 'sphere': SPHERE, 'query': 'бани', 'cities': cities})
    lead = {'summary': {'name': 'А'}, 'card': {'row': {'Название': 'А'}}, 'raw': {'item': {'id': '1'}, 'prices': None}}
    store.add_to_folder(token, folder_id, [{**lead, 'slug': 'a'}, {**lead, 'slug': 'b'}])
    store.add_to_folder(token, folder_id, [{**lead, 'slug': 'a', 'card': {'row': {'Название': 'А2'}}}])  # replaced
    store.update_folder(token, folder_id, {'cities': cities * 2})

    folder = next(f for f in store.list_folders(token) if f['id'] == folder_id)
    assert (folder['name'], folder['count'], len(folder['cities'])) == ('Тест', 2, 2)
    assert store.get_folder(token, folder_id)['query'] == 'бани'
    assert [r['slug'] for r in store.folder_raw(token, folder_id)] == ['b', 'a']
    assert store.folder_leads(token, folder_id) == [{'name': 'А', 'status': 'new', 'priority': 0}] * 2
    assert store.folder_card(token, folder_id, 'a')['row'] == {'Название': 'А2'}
    assert store.folder_card(token, folder_id, 'zzz') is None


def test_anonymous_requests_see_nothing():
    r = requests.get(f'{store._url}/rest/v1/leads', headers={'apikey': store._key}, timeout=10)
    assert r.status_code in (401, 403)


def test_folder_lead_work_round_trip(token):
    folder_id = store.create_folder(token, {'name': 'CRM', 'sphere': SPHERE, 'query': '', 'cities': []})
    lead = {'slug': 'a', 'summary': {'name': 'А'}, 'card': {'row': {}}, 'raw': {'item': {}, 'prices': None}}
    store.add_to_folder(token, folder_id, [lead, {**lead, 'slug': 'b'}])
    assert store.folder_card(token, folder_id, 'a')['crm']['status'] == 'new'

    crm = store.update_folder_lead(token, folder_id, 'a', {'status': 'client', 'priority': 2, 'comment': 'да',
                                                           'demo_url': 'https://d.example', 'demo_source': 'manual'})
    assert (crm['status'], crm['priority'], crm['demo_source']) == ('client', 2, 'manual')
    assert store.update_folder_lead(token, folder_id, 'zzz', {'status': 'lost'}) is None
    store.add_to_folder(token, folder_id, [lead])  # re-saving keeps the work
    assert store.folder_card(token, folder_id, 'a')['crm']['comment'] == 'да'
    assert store.folder_leads(token, folder_id)[1] == {'name': 'А', 'status': 'client', 'priority': 2}

    assert store.delete_folder_lead(token, folder_id, 'a') is True
    assert store.delete_folder_lead(token, folder_id, 'a') is False
    assert [r['slug'] for r in store.folder_raw(token, folder_id)] == ['b']
