"""«Общее сообщение» of a saved lead folder: one text for every lead's card, with the place of the lead's own demo
link marked by [ссылка на демо]. Never exported."""
import pytest

from fake_store import FakeStore
from leadbombing.leads.spheres import BANI_DEMO_MESSAGE, NO_DEMO_URL
from leadbombing.web import create_app
from leadbombing.web.lead_crm import MAX_MESSAGE, parse_message_template
from test_folders_api import client, saved_folder  # noqa: F401  (fixture and helper)

TEXT = f'Здравствуйте! Собрал вам онлайн-запись: {NO_DEMO_URL}\nПишите, если понравится.'


def set_message(client, folder_id, text):  # noqa: F811
    return client.put(f'/api/folders/{folder_id}/message', json={'text': text})


def card(client, folder_id, slug):  # noqa: F811
    return client.get(f'/api/folders/{folder_id}/item/{slug}').get_json()


def test_parse_keeps_a_text_with_the_demo_link_mark():
    assert parse_message_template(f'  {TEXT}  ') == TEXT


def test_parse_turns_an_empty_text_into_none():
    assert parse_message_template('   ') is None


@pytest.mark.parametrize('value, message', [
    (None, 'текст'),
    (5, 'текст'),
    (NO_DEMO_URL + 'а' * MAX_MESSAGE, 'длиннее'),
])
def test_parse_refuses_a_bad_text(value, message):
    with pytest.raises(ValueError, match=message):
        parse_message_template(value)


def test_every_card_of_the_folder_gets_the_message(client):  # noqa: F811
    folder_id = saved_folder(client)

    r = set_message(client, folder_id, f' {TEXT} ')

    assert r.get_json() == {'ok': True, 'message_template': TEXT}
    assert card(client, folder_id, 'usadba-bannaya')['demo_message'] == TEXT
    assert card(client, folder_id, 'hlebnikovskie-bani')['demo_message'] == TEXT
    assert client.get('/api/folders').get_json()['folders'][0]['message_template'] == TEXT


def test_each_card_keeps_its_own_demo_link(client):  # noqa: F811
    folder_id = saved_folder(client)
    set_message(client, folder_id, TEXT)
    client.post(f'/api/folders/{folder_id}/work', json={'base_url': 'https://demo.example.ru'})

    links = {slug: card(client, folder_id, slug)['crm']['demo_url'] for slug in ('usadba-bannaya', 'hlebnikovskie-bani')}

    assert links == {'usadba-bannaya': 'https://demo.example.ru/usadba-bannaya',
                     'hlebnikovskie-bani': 'https://demo.example.ru/hlebnikovskie-bani'}


def test_an_empty_text_brings_back_the_sphere_message(client):  # noqa: F811
    folder_id = saved_folder(client)
    set_message(client, folder_id, TEXT)

    r = set_message(client, folder_id, '')

    assert r.get_json() == {'ok': True, 'message_template': None}
    assert card(client, folder_id, 'usadba-bannaya')['demo_message'] == BANI_DEMO_MESSAGE.format(demo_url=NO_DEMO_URL)


def test_a_text_without_the_demo_link_mark_is_accepted(client):  # noqa: F811
    folder_id = saved_folder(client)

    r = set_message(client, folder_id, 'Здравствуйте!')

    assert r.get_json() == {'ok': True, 'message_template': 'Здравствуйте!'}


def test_unknown_folder_is_404_and_a_guest_gets_401(client):  # noqa: F811
    assert set_message(client, 999, TEXT).status_code == 404
    guest = create_app(store=FakeStore(), secret_key='test-secret').test_client()
    assert guest.put('/api/folders/1/message', json={'text': TEXT}).status_code == 401
