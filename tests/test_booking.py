"""Lead priority from the 2GIS card: the «Забронировать» button and the firm's own site."""
import pytest

from leadbombing.leads.booking import assess, button_of, own_sites

REDIRECT = 'http://link.2gis.ru/1.2/490FA845/online/20261101/project32/4504127908676775/null/j8l9kng?'


def link(target: str, caption: str = 'Забронировать') -> dict:
    return {'caption': caption, 'name': caption, 'type': 'link', 'value': REDIRECT + target}


def phone(number: str = '+74956639901', caption: str = 'Забронировать') -> dict:
    return {'caption': caption, 'name': caption, 'type': 'phone', 'value': number}


def card(*urls: str) -> dict:
    return {'id': '1', 'contact_groups': [{'contacts': [
        {'type': 'website', 'url': u, 'text': u.split('://')[-1]} for u in urls]}]}


def test_own_sites_skip_messengers_and_social_pages_given_as_websites():
    item = card('http://sanduny.ru', 'http://t.me/sanduny', 'http://max.ru/id77_biz', 'https://vk.com/sanduny')
    assert own_sites(item) == ['sanduny.ru']


def test_own_sites_of_a_card_without_contacts_are_empty():
    assert own_sites({'id': '1'}) == []


def test_phone_button():
    assert button_of([phone()]) == {'kind': 'phone', 'caption': 'Забронировать', 'value': '+74956639901'}


def test_link_button_target_is_taken_from_the_2gis_redirect_without_utm():
    b = button_of([link('http://banya-vip.ru/booking/?utm_source=2gis&utm_medium=cpc')])
    assert b == {'kind': 'booking_page', 'caption': 'Забронировать', 'value': 'banya-vip.ru/booking/'}


@pytest.mark.parametrize('target, kind', [
    ('http://api.whatsapp.com/send/?phone=79300357717&text=hi', 'messenger'),
    ('https://wa.me/79300357717', 'messenger'),
    ('https://t.me/bani_bot', 'messenger'),
    ('https://max.ru/id773391203301_bot', 'messenger'),
    ('https://n123.yclients.com/company/1/menu', 'booking_service'),
    ('https://dikidi.net/123456', 'booking_service'),
    ('https://sauna.ru/bron', 'booking_page'),
    ('https://sauna.ru/online-zapis/', 'booking_page'),
    ('https://sauna.ru/prices', 'site'),
    ('https://sauna.ru/', 'site'),
])
def test_link_button_kinds(target, kind):
    assert button_of([link(target)])['kind'] == kind


def test_redirect_with_an_encoded_target_is_decoded():
    b = button_of([link('https%3A%2F%2Fdikidi.net%2F42')])
    assert (b['kind'], b['value']) == ('booking_service', 'dikidi.net/42')


def test_only_a_booking_caption_counts_as_the_booking_button():
    assert button_of([link('https://mitbani.ru/', 'Перейти на сайт')]) == {'kind': 'none', 'caption': '', 'value': ''}
    assert button_of([phone(caption='Записаться')])['caption'] == 'Записаться'


def test_no_actions_means_no_button_and_unknown_data_stays_unknown():
    assert button_of([])['kind'] == 'none'
    assert button_of(None) is None


@pytest.mark.parametrize('sites, actions, priority, note', [
    ((), [phone()], 5, 'Сайта нет, кнопка «Забронировать» в 2ГИС — звонок'),
    ((), [link('https://wa.me/79300357717')], 5, 'Сайта нет, кнопка «Забронировать» в 2ГИС — сообщение в мессенджер'),
    ((), [], 4, 'Ни сайта, ни кнопки брони в 2ГИС — бронь только по телефону'),
    (('http://bani.ru',), [phone()], 4, 'Сайт bani.ru есть, но кнопка «Забронировать» в 2ГИС — звонок'),
    (('http://bani.ru',), [], 3, 'Сайт bani.ru есть, кнопки брони в 2ГИС нет — удобство брони на сайте не проверено'),
    ((), [link('https://bani.ru/')], 3, 'Кнопка «Забронировать» ведёт на сайт bani.ru — удобство брони не проверено'),
    ((), [link('https://bani.ru/booking')], 2, 'Кнопка «Забронировать» ведёт на страницу брони bani.ru/booking'),
    ((), [link('https://n1.yclients.com/c/1')], 1,
     'Кнопка «Забронировать» ведёт в сервис онлайн-брони YCLIENTS — услуга вряд ли нужна'),
])
def test_priority_and_note_from_the_card(sites, actions, priority, note):
    result = assess(card(*sites), actions)
    assert (result['priority'], result['note']) == (priority, note)


def test_note_names_the_button_caption():
    assert assess(card(), [phone(caption='Записаться')])['note'] == 'Сайта нет, кнопка «Записаться» в 2ГИС — звонок'


def test_unknown_button_gives_no_priority():
    assert assess(card(), None) == {'priority': 0, 'note': '', 'button': None}


def test_assessment_keeps_the_button():
    assert assess(card(), [phone()])['button'] == {'kind': 'phone', 'caption': 'Забронировать',
                                                   'value': '+74956639901'}
