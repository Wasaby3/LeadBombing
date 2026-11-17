from datetime import date

from leadbombing.leads.build import build_halls, schedule_of
from leadbombing.leads.prices import old_prices_since, parse_price, parse_updated
from leadbombing.leads.text import clean_url, fmt_phone, is_mobile, slugify, unique


def test_phones_and_urls():
    assert fmt_phone('+79853847670') == '+7 985 384-76-70'
    assert fmt_phone('8 (499) 111-25-70') == '+7 499 111-25-70'
    assert is_mobile('https://wa.me/79671018331') and not is_mobile('+74991112570')
    assert clean_url('https://wa.me/79671018331?text=Hi') == 'https://wa.me/79671018331'


def test_slug():
    assert slugify('Хлебниковские бани') == 'hlebnikovskie-bani'
    assert slugify('Марфинские бани, сауна') == 'marfinskie-bani-sauna'
    assert unique('bani', {'bani', 'bani-2'}) == 'bani-3'


def test_prices_and_dates():
    assert parse_price({'fixed': {'value': 2800}}) == (2800, False)
    assert parse_price({'from': {'value': 3500}}) == (3500, True)
    assert parse_price({'range': {'min': 1800, 'max': 3000}}) == (1800, True)
    assert parse_updated('Обновлено 21 января 2025') == '2025-01-21'
    assert parse_updated('2026-08-07T09:51:22Z') == '2026-08-07'


def test_old_prices_since_after_half_a_year():
    today = date(2025, 7, 23)  # 183 days after 2025-01-21
    assert old_prices_since('2025-01-21', today) is None
    assert old_prices_since('2025-01-20', today) == 'января 2025'
    assert old_prices_since(None, today) is None


def test_halls():
    assumed = []
    items = [{'name': 'Русская баня с бильярдом. Купель с гейзером. Веники.', 'price': {'fixed': {'value': 2800}}},
             {'name': 'Зал для двоих с джакузи за 3 часа', 'price': {'fixed': {'value': 5500}}},
             {'name': 'Парение', 'price': {'fixed': {'value': 2000}}},
             {'name': 'Веник дубовый', 'price': {'fixed': {'value': 500}}}]
    halls, extras, raw = build_halls(items, 20, None, assumed)
    assert [h['name'] for h in halls] == ['Русская баня с бильярдом', 'Зал для двоих с джакузи']
    assert halls[0]['description'].startswith('Купель с гейзером') and halls[0]['capacity_max'] == 10
    couple = halls[1]
    assert (couple['capacity_max'], couple['min_duration_min']) == (2, 180)
    assert couple['tariffs'][0]['rules'][0]['price_per_hour_rub'] == 1834
    assert [e['name'] for e in extras] == ['Веник дубовый'] and len(raw) == 2
    stub, _, _ = build_halls([], None, 1800, [])
    assert stub[0]['name'] == 'Парная' and stub[0]['tariffs'][0]['rules'][0]['price_per_hour_rub'] == 1800


def test_schedule():
    sch = {d: {'working_hours': [{'from': '10:00', 'to': '02:00'}]} for d in ('Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun')}
    days, text, known = schedule_of({'schedule': sch}, 120)
    assert days['mon'] == {'start_from': '10:00', 'start_to': '24:00'} and text == 'ежедневно 10:00–02:00' and known
    days, text, _ = schedule_of({'schedule': {'is_24x7': True}}, 120)
    assert days['sun'] == {'start_from': '00:00', 'start_to': '24:00'} and text == 'круглосуточно'
