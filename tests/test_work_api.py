"""«Проработать лиды» on «Сохранённые лиды»: the demo URL of each lead is the base URL plus its folder slug,
the same name as its `tenants/<slug>/` folder in an export."""
import pytest

from fake_store import FakeStore
from leadbombing.web import create_app
from test_folders_api import client, saved_folder  # noqa: F401  (fixture and helper)


def work(client, folder_id, **body):  # noqa: F811
    return client.post(f'/api/folders/{folder_id}/work', json=body)


def demo(client, folder_id, slug):  # noqa: F811
    crm = client.get(f'/api/folders/{folder_id}/item/{slug}').get_json()['crm']
    return crm['demo_url'], crm['demo_source']


def test_every_lead_gets_the_base_url_plus_its_slug(client):  # noqa: F811
    folder_id = saved_folder(client)

    r = work(client, folder_id, base_url=' https://demo.example.ru/s/ ').get_json()

    assert r == {'ok': True, 'filled': 2, 'kept': 0, 'base_url': 'https://demo.example.ru/s',
                 'filled_at': r['filled_at']} and r['filled_at']
    assert demo(client, folder_id, 'usadba-bannaya') == ('https://demo.example.ru/s/usadba-bannaya', 'auto')
    assert demo(client, folder_id, 'hlebnikovskie-bani') == ('https://demo.example.ru/s/hlebnikovskie-bani', 'auto')


def test_the_folder_remembers_the_base_url_for_the_next_time(client):  # noqa: F811
    folder_id = saved_folder(client)
    assert client.get('/api/folders').get_json()['folders'][0]['demo_base_url'] is None

    work(client, folder_id, base_url='https://demo.example.ru')

    folder = client.get('/api/folders').get_json()['folders'][0]
    assert folder['demo_base_url'] == 'https://demo.example.ru' and folder['demo_filled_at']


def test_a_new_base_url_replaces_auto_links_and_keeps_links_typed_by_hand(client):  # noqa: F811
    folder_id = saved_folder(client)
    work(client, folder_id, base_url='https://old.example.ru')
    client.patch(f'/api/folders/{folder_id}/item/usadba-bannaya', json={'demo_url': 'https://my.example/usadba'})

    r = work(client, folder_id, base_url='https://new.example.ru').get_json()

    assert (r['filled'], r['kept']) == (1, 1)
    assert demo(client, folder_id, 'usadba-bannaya') == ('https://my.example/usadba', 'manual')
    assert demo(client, folder_id, 'hlebnikovskie-bani') == ('https://new.example.ru/hlebnikovskie-bani', 'auto')


def test_only_picked_leads_are_worked_on_and_clients_are_left_alone(client):  # noqa: F811
    folder_id = saved_folder(client)
    client.post(f'/api/folders/{folder_id}/item/hlebnikovskie-bani/client')

    r = work(client, folder_id, base_url='https://demo.example.ru', slugs=['usadba-bannaya', 'hlebnikovskie-bani'])

    assert r.get_json()['filled'] == 1
    assert demo(client, folder_id, 'hlebnikovskie-bani') == (None, None)


@pytest.mark.parametrize('body, message', [
    ({}, 'адрес'),
    ({'base_url': 'demo.example.ru'}, 'http'),
    ({'base_url': 'https://demo.example.ru/?a=1'}, '?'),
    ({'base_url': 'https://demo example.ru'}, 'пробел'),
    ({'base_url': 'https://demo.example.ru/' + 'a' * 2000}, 'длинн'),
    ({'base_url': 'https://demo.example.ru', 'slugs': ['BAD!']}, 'лидов'),
])
def test_bad_request_is_refused_with_a_message(client, body, message):  # noqa: F811
    folder_id = saved_folder(client)
    r = work(client, folder_id, **body)
    assert r.status_code == 400 and message in r.get_json()['error']


def test_unknown_folder_is_404_and_a_guest_gets_401(client):  # noqa: F811
    assert work(client, 999, base_url='https://demo.example.ru').status_code == 404
    guest = create_app(store=FakeStore(), secret_key='test-secret').test_client()
    assert guest.post('/api/folders/1/work', json={'base_url': 'https://demo.example.ru'}).status_code == 401
