"""Clients («Клиенты»): a saved lead made a client leaves its folder and shows on the clients page with its own status."""
import pytest

from test_folders_api import client, saved_folder  # noqa: F401  (the fixture and helper of folder tests)


@pytest.fixture()
def made_client(client):  # noqa: F811
    folder_id = saved_folder(client)
    r = client.post(f'/api/folders/{folder_id}/item/usadba-bannaya/client')
    return folder_id, r


def test_lead_made_client_is_bought_and_ok(client, made_client):  # noqa: F811
    # Arrange
    folder_id, r = made_client

    # Assert
    crm = r.get_json()['crm']
    assert r.status_code == 200 and r.get_json()['ok']
    assert (crm['status'], crm['client_status']) == ('bought', 'ok') and crm['client_since']
    card = client.get(f'/api/folders/{folder_id}/item/usadba-bannaya').get_json()
    assert card['crm']['client_status'] == 'ok' and card['row']['Баня'] == 'Усадьба Банная'


def test_client_leaves_folder_list_count_and_export(client, made_client, tmp_path):  # noqa: F811
    # Arrange
    folder_id, _ = made_client

    # Act
    leads = client.get(f'/api/folders/{folder_id}').get_json()['leads']
    folders = client.get('/api/folders').get_json()['folders']
    exported = client.post(f'/api/folders/{folder_id}/export', json={'path': str(tmp_path / 'out')}).get_json()

    # Assert
    assert [lead['slug'] for lead in leads] == ['hlebnikovskie-bani']
    assert folders[0]['count'] == 1
    assert exported['ok'] and exported['added'] == 1


def test_clients_page_lists_clients_with_their_folder(client, made_client):  # noqa: F811
    # Arrange
    folder_id, _ = made_client

    # Act
    clients = client.get('/api/clients').get_json()['clients']

    # Assert
    assert len(clients) == 1
    c = clients[0]
    assert (c['slug'], c['name'], c['folder_id'], c['folder']) == ('usadba-bannaya', 'Усадьба Банная', folder_id, 'Бани')
    assert (c['client_status'], c['status']) == ('ok', 'bought') and c['client_since'] and c['has_photo']
    assert client.get(f'/api/folders/{folder_id}/item/usadba-bannaya/hero').status_code == 200


def test_client_status_is_changed_and_kept_on_resave(client, made_client):  # noqa: F811
    # Arrange
    folder_id, _ = made_client
    item = f'/api/folders/{folder_id}/item/usadba-bannaya'

    # Act
    r = client.patch(item, json={'client_status': 'bug', 'comment': 'не открывается демо'}).get_json()
    client.post('/api/folders/save', json={'folder_id': folder_id})  # the same firm saved again from the search

    # Assert
    assert (r['crm']['client_status'], r['crm']['comment']) == ('bug', 'не открывается демо')
    assert [c['client_status'] for c in client.get('/api/clients').get_json()['clients']] == ['bug']
    assert [lead['slug'] for lead in client.get(f'/api/folders/{folder_id}').get_json()['leads']] == ['hlebnikovskie-bani']


def test_client_status_of_a_lead_is_refused(client):  # noqa: F811
    folder_id = saved_folder(client)
    r = client.patch(f'/api/folders/{folder_id}/item/usadba-bannaya', json={'client_status': 'bug'})
    assert r.status_code == 404 and r.get_json()['error'] == 'Клиент не найден'
    assert client.get('/api/clients').get_json()['clients'] == []


def test_making_a_client_twice_or_of_a_missing_lead_is_refused(client, made_client):  # noqa: F811
    folder_id, _ = made_client
    again = client.post(f'/api/folders/{folder_id}/item/usadba-bannaya/client')
    assert again.status_code == 404 and again.get_json()['error'] == 'Лид не найден'
    assert client.post(f'/api/folders/{folder_id}/item/nope/client').status_code == 404
    assert client.post(f'/api/folders/{folder_id + 99}/item/hlebnikovskie-bani/client').status_code == 404
    assert client.post(f'/api/folders/{folder_id}/item/BAD!/client').status_code == 404


def test_clients_need_login(client):  # noqa: F811
    client.post('/api/auth/logout')
    assert client.get('/api/clients').status_code == 401
