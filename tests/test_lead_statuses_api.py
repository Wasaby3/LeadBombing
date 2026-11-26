"""Настройки → «Статусы лидов»: create, rename, recolor, delete with its cascade onto leads. The default status
isn't a separate field — it's always the one with the smallest sort_order (the first in the list)."""
import pytest

from test_folders_api import client, run, saved_folder  # noqa: F401  (fixture and helpers of folder tests)

BUILTIN_IDS = ['not_written', 'written', 'in_progress', 'almost', 'bought', 'refused']


def test_list_seeds_the_six_builtin_statuses_not_written_first(client):  # noqa: F811
    statuses = client.get('/api/account/lead-statuses').get_json()['statuses']
    assert [s['id'] for s in statuses] == BUILTIN_IDS
    assert next(s for s in statuses if s['id'] == 'in_progress')['color'] == 'active'


def test_create_adds_a_status_named_new_status_by_default(client):  # noqa: F811
    r = client.post('/api/account/lead-statuses', json={})
    status = r.get_json()['status']
    assert r.status_code == 200 and status['name'] == 'Новый статус'
    assert status['id'] not in BUILTIN_IDS

    r2 = client.post('/api/account/lead-statuses', json={})  # a second default-named one is numbered, not rejected
    assert r2.get_json()['status']['name'] == 'Новый статус 2'


def test_create_without_a_color_picks_one_not_already_used(client):  # noqa: F811
    # the 6 builtins use neutral/wait/active/warm/good/bad; the first free color is purple
    status = client.post('/api/account/lead-statuses', json={}).get_json()['status']
    assert status['color'] == 'purple'
    status2 = client.post('/api/account/lead-statuses', json={}).get_json()['status']
    assert status2['color'] == 'teal'


def test_rename_and_recolor_a_status(client):  # noqa: F811
    status = client.post('/api/account/lead-statuses', json={}).get_json()['status']
    r = client.patch(f"/api/account/lead-statuses/{status['id']}", json={'name': 'Позвонить завтра'})
    assert r.get_json()['status']['name'] == 'Позвонить завтра'
    r = client.patch(f"/api/account/lead-statuses/{status['id']}", json={'color': 'teal'})
    assert r.get_json()['status']['color'] == 'teal'


@pytest.mark.parametrize('data, message', [
    ({'name': ''}, 'название'), ({'name': '   '}, 'название'), ({'name': 'Купил'}, 'уже есть'),
    ({'color': 'purple-ish'}, 'цвет'), ({'name': None}, 'название'),
])
def test_create_rejects_bad_values(client, data, message):  # noqa: F811
    r = client.post('/api/account/lead-statuses', json={'name': 'Статус', 'color': 'neutral', **data})
    assert r.status_code == 400 and message.lower() in r.get_json()['error'].lower()


@pytest.mark.parametrize('color', ['neutral', 'good', 'wait', 'active', 'warm', 'bad', 'purple', 'teal', 'pink'])
def test_create_accepts_every_palette_color(client, color):  # noqa: F811
    r = client.post('/api/account/lead-statuses', json={'name': f'Статус {color}', 'color': color})
    assert r.status_code == 200 and r.get_json()['status']['color'] == color


def test_create_is_capped_at_nine_statuses_total(client):  # noqa: F811
    for _ in range(3):  # 6 builtin + 3 = 9
        assert client.post('/api/account/lead-statuses', json={}).status_code == 200
    r = client.post('/api/account/lead-statuses', json={})
    assert r.status_code == 400 and 'не больше' in r.get_json()['error']


def test_rename_to_an_existing_name_is_rejected(client):  # noqa: F811
    r = client.patch('/api/account/lead-statuses/written', json={'name': 'Купил'})
    assert r.status_code == 400 and 'уже есть' in r.get_json()['error']


def test_unknown_status_is_404_on_update_and_delete(client):  # noqa: F811
    assert client.patch('/api/account/lead-statuses/ghost', json={'name': 'x'}).status_code == 404
    assert client.delete('/api/account/lead-statuses/ghost').status_code == 404


def test_protected_statuses_cannot_be_deleted(client):  # noqa: F811
    assert client.delete('/api/account/lead-statuses/not_written').status_code == 400
    assert client.delete('/api/account/lead-statuses/bought').status_code == 400


def test_last_remaining_status_cannot_be_deleted(client):  # noqa: F811
    for status_id in ('written', 'almost', 'refused'):
        assert client.delete(f'/api/account/lead-statuses/{status_id}').status_code == 200
    assert client.delete('/api/account/lead-statuses/bought').status_code == 400  # protected, still there
    assert client.delete('/api/account/lead-statuses/in_progress').status_code == 200
    # only not_written and bought are left; neither can be removed now
    assert client.delete('/api/account/lead-statuses/not_written').status_code == 400
    assert client.delete('/api/account/lead-statuses/bought').status_code == 400


def test_deleting_a_status_moves_its_leads_to_the_new_first_status(client):  # noqa: F811
    folder_id = saved_folder(client, slugs=['usadba-bannaya', 'hlebnikovskie-bani'])
    client.patch(f'/api/folders/{folder_id}/item/usadba-bannaya', json={'status': 'in_progress'})
    client.patch(f'/api/folders/{folder_id}/item/hlebnikovskie-bani', json={'status': 'in_progress'})

    assert client.delete('/api/account/lead-statuses/in_progress').status_code == 200

    leads = {lead['slug']: lead for lead in client.get(f'/api/folders/{folder_id}').get_json()['leads']}
    assert leads['usadba-bannaya']['status'] == 'not_written'
    assert leads['hlebnikovskie-bani']['status'] == 'not_written'
    ids = [s['id'] for s in client.get('/api/account/lead-statuses').get_json()['statuses']]
    assert 'in_progress' not in ids


def test_deleting_not_written_would_need_removal_but_is_protected_so_leads_keep_it(client):  # noqa: F811
    # not_written can't be deleted at all, so a new lead's status never needs to fall back off it.
    folder_id = saved_folder(client, slugs=['usadba-bannaya'])
    leads = client.get(f'/api/folders/{folder_id}').get_json()['leads']
    assert leads[0]['status'] == 'not_written'  # the first status (smallest sort_order) is the default


def test_lead_crm_patch_rejects_a_status_that_does_not_exist_for_this_user(client):  # noqa: F811
    folder_id = saved_folder(client, slugs=['usadba-bannaya'])
    r = client.patch(f'/api/folders/{folder_id}/item/usadba-bannaya', json={'status': 'ghost'})
    assert r.status_code == 400 and 'Неизвестный статус' in r.get_json()['error']
