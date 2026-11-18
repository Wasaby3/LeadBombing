"""Work on a saved lead (status, priority, comment, contact channels, demo app): validation of a change."""
import pytest

from leadbombing.web.lead_crm import DEFAULT_CRM, MAX_COMMENT, parse_patch


def test_default_is_a_new_lead_without_priority_or_demo():
    assert DEFAULT_CRM == {'status': 'new', 'priority': 0, 'comment': '', 'contacted': [],
                           'demo_url': None, 'demo_source': None}


def test_accepts_known_fields_and_cleans_them():
    patch = parse_patch({'status': 'client', 'priority': 5, 'comment': '  перезвонить в пятницу \n',
                         'contacted': [{'title': 'WhatsApp', 'value': '+7 900 000-00-00'}]})
    assert patch == {'status': 'client', 'priority': 5, 'comment': 'перезвонить в пятницу',
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
