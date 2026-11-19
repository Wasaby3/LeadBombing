"""Work on a saved lead (status, priority, comment, contact channels, demo app): validation of a change."""
import pytest

from leadbombing.web.lead_crm import DEFAULT_CRM, MAX_COMMENT, parse_base_url, parse_patch


def test_default_is_a_lead_not_written_to_without_priority_or_demo():
    assert DEFAULT_CRM == {'status': 'not_written', 'priority': 0, 'comment': '', 'contacted': [],
                           'demo_url': None, 'demo_source': None, 'client_status': None, 'client_since': None}


@pytest.mark.parametrize('status', ['not_written', 'written', 'in_progress', 'almost', 'bought', 'refused'])
def test_accepts_every_lead_status(status):
    assert parse_patch({'status': status}) == {'status': status}


@pytest.mark.parametrize('client_status', ['ok', 'question', 'bug'])
def test_accepts_every_client_status(client_status):
    assert parse_patch({'client_status': client_status}) == {'client_status': client_status}


def test_accepts_known_fields_and_cleans_them():
    patch = parse_patch({'status': 'almost', 'priority': 5, 'comment': '  перезвонить в пятницу \n',
                         'contacted': [{'title': 'WhatsApp', 'value': '+7 900 000-00-00'}]})
    assert patch == {'status': 'almost', 'priority': 5, 'comment': 'перезвонить в пятницу',
                     'contacted': [{'title': 'WhatsApp', 'value': '+7 900 000-00-00'}]}


def test_manual_demo_url_is_marked_manual_and_empty_url_clears_it():
    assert parse_patch({'demo_url': ' https://demo.example/bani '}) == {
        'demo_url': 'https://demo.example/bani', 'demo_source': 'manual'}
    assert parse_patch({'demo_url': ''}) == {'demo_url': None, 'demo_source': None}


def test_duplicate_contacts_are_kept_once():
    c = {'title': 'Телефон', 'value': '+7 495 000-00-00'}
    assert parse_patch({'contacted': [c, dict(c)]}) == {'contacted': [c]}


@pytest.mark.parametrize('data, message', [
    ({}, 'Нечего сохранять'),
    ({'nope': 1}, 'Неизвестное поле'),
    ({'demo_source': 'auto'}, 'Неизвестное поле'),  # only a future generator sets «auto», not the UI
    ({'status': 'won'}, 'Неизвестный статус'),
    ({'status': 'new'}, 'Неизвестный статус'),  # the old statuses are gone (migration 20261118180000_clients)
    ({'status': 'client'}, 'Неизвестный статус'),
    ({'client_status': 'fine'}, 'Неизвестный статус клиента'),
    ({'client_status': None}, 'Неизвестный статус клиента'),  # a lead becomes a client by POST …/client
    ({'client_since': '2026-11-18'}, 'Неизвестное поле'),
    ({'priority': 6}, 'Приоритет'),
    ({'priority': -1}, 'Приоритет'),
    ({'priority': True}, 'Приоритет'),
    ({'priority': '2'}, 'Приоритет'),
    ({'comment': 5}, 'Комментарий'),
    ({'comment': 'я' * (MAX_COMMENT + 1)}, 'Комментарий длиннее'),
    ({'demo_url': 'javascript:alert(1)'}, 'http'),
    ({'demo_url': 'ftp://x'}, 'http'),
    ({'demo_url': 'https://' + 'a' * 2000}, 'длиннее'),
    ({'contacted': 'WhatsApp'}, 'Канал связи'),
    ({'contacted': [{'title': 'WhatsApp'}]}, 'Канал связи'),
    ({'contacted': [{'title': 'WhatsApp', 'value': 5}]}, 'Канал связи'),
])
def test_rejects_bad_values_with_russian_message(data, message):
    with pytest.raises(ValueError, match=message):
        parse_patch(data)


@pytest.mark.parametrize('value, url', [
    (' https://demo.example.ru/s/ ', 'https://demo.example.ru/s'),
    ('HTTPS://Demo.example.ru', 'https://Demo.example.ru'),
    ('http://localhost:3000//', 'http://localhost:3000'),
])
def test_base_url_loses_the_trailing_slash_and_gets_a_lower_case_scheme(value, url):
    assert parse_base_url(value) == url


@pytest.mark.parametrize('value', [None, 5, '', '   ', 'demo.example.ru', 'https://', 'ftp://demo.example.ru',
                                   'https://demo.example.ru/?a=1', 'https://demo.example.ru/#x', 'https://a b.ru'])
def test_bad_base_url_is_refused(value):
    with pytest.raises(ValueError):
        parse_base_url(value)
