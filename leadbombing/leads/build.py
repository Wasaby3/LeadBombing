"""Turn a 2GIS firm profile (+ its prices tab) into a lead, an outreach row and a bani-pwa business.json."""
from __future__ import annotations

import math
import re
from datetime import date
from typing import Any

from .contacts import (LABEL_ROOM_BOOKING, Reach, business_contacts, contact_book, contacts_of, lead_contact,
                       outreach_columns, reach_of)
from .demo import (amenities_description, legal_block, photos_block, policy_block, theme_block,
                   working_hours_block, wordmark_main)
from .firm import district_of, firm_id, legal_name, main_photo, short_name
from .prices import money, old_prices_since, parse_price, parse_updated
from .text import slugify, unique

AMENITY_GROUP = 'Бани / Сауны'
DEFAULT_PRICE = 2500
MIN_DURATION = 120
DAYS = [('Mon', 'mon', 'пн'), ('Tue', 'tue', 'вт'), ('Wed', 'wed', 'ср'), ('Thu', 'thu', 'чт'),
        ('Fri', 'fri', 'пт'), ('Sat', 'sat', 'сб'), ('Sun', 'sun', 'вс')]

HALL_RE = re.compile(r'зал|номер|сауна|сауны|баня|бани|парная|парилк', re.I)
NOT_HALL_RE = re.compile(r'парени|парильщик|массаж|шоу|пилинг|скраб|обёртыв|обертыв|программ|церемон'
                         r'|абонемент|сертификат|разовое посещение', re.I)
EXTRA_RE = re.compile(r'веник|полотен|простын|халат|тапоч|шапк|\bчай|\bм[её]д\b|квас|аромамасл|войлок', re.I)
HOURS_RE = re.compile(r'\s*за\s+(\d+)\s*час\w*', re.I)


def hm(minutes: int) -> str:
    return f'{minutes // 60:02d}:{minutes % 60:02d}'


def to_min(time: str) -> int:
    h, m = time.split(':')
    return int(h) * 60 + int(m)


def amenities_of(item: dict, group: str = AMENITY_GROUP) -> list[str]:
    for g in item.get('attribute_groups') or []:
        if g.get('name') == group:
            return [a['name'] for a in g.get('attributes') or [] if a.get('name')]
    return []


def attr_number(amenities: list[str], pattern: str) -> int | None:
    for a in amenities:
        m = re.search(pattern, a)
        if m:
            return int(re.sub(r'\D', '', m.group(1)))
    return None


def schedule_of(item: dict, min_duration: int) -> tuple[dict, str, bool]:
    """→ (working_hours.days, human hours, known)."""
    sch = item.get('schedule') or {}
    full = {'start_from': '00:00', 'start_to': '24:00'}
    if sch.get('is_24x7') or not any(sch.get(d) for d, _, _ in DAYS):
        return {k: dict(full) for _, k, _ in DAYS}, 'круглосуточно', bool(sch)
    days, spans = {}, {}
    for src, key, ru in DAYS:
        wh = (sch.get(src) or {}).get('working_hours') or []
        if not wh:
            days[key], spans[ru] = None, 'выходной'
            continue
        opens, closes = to_min(wh[0]['from']), to_min(wh[-1]['to'])
        if closes <= opens:  # closes after midnight
            closes += 1440
        start_to = min(closes - min_duration, 1440)
        days[key] = {'start_from': hm(opens), 'start_to': hm(start_to)} if start_to > opens else None
        spans[ru] = f"{wh[0]['from']}–{wh[-1]['to']}"
    if len(set(spans.values())) == 1:
        return days, f'ежедневно {next(iter(spans.values()))}', True
    return days, ', '.join(f'{ru} {s}' for ru, s in spans.items()), True


def build_halls(items: list[dict], cap_attr: int | None, price_attr: int | None,
                assumed: list[str]) -> tuple[list[dict], list[dict], list[dict]]:
    """Prices tab items → (halls, extras, halls_from_2gis)."""
    halls: list[dict] = []
    extras: list[dict] = []
    raw: list[dict] = []
    cap_max_default = min(cap_attr or 10, 10)
    for it in items:
        parsed = parse_price(it.get('price') or {})
        name = ' '.join((it.get('name') or '').split())
        if not parsed or not name:
            continue
        price, is_from = parsed
        hall_like = HALL_RE.search(name) or 'номера саун' in (it.get('section') or '').lower()
        if hall_like and not NOT_HALL_RE.search(name):
            raw.append({'name': name, 'price': ('от ' if is_from else '') + money(price)})
            hours = HOURS_RE.search(name)
            k = int(hours.group(1)) if hours and int(hours.group(1)) > 0 else None
            first, _, rest = HOURS_RE.sub('', name).strip(' .,').partition('. ')
            couple = re.search(r'для\s+двоих', name, re.I)
            cap_max = 2 if couple else cap_max_default
            desc = ' '.join(x for x in (rest.strip(), (it.get('description') or '').strip()) if x)
            per_hour = math.ceil(price / k) if k else price
            if k:
                assumed.append(f'{first[:80]}: {money(price)} за {k} ч → {money(per_hour)}/ч, минимум {k} ч')
            halls.append(_hall(first.rstrip('.')[:80], desc[:1000], cap_max, per_hour, k * 60 if k else MIN_DURATION))
        elif EXTRA_RE.search(name) and not NOT_HALL_RE.search(name):
            extras.append({'key': slugify(name, 30, '_') or 'extra', 'name': name[:80], 'description': '',
                           'price_rub': price, 'unit': 'per_booking', 'max_qty': 10})
    if not halls:
        price = price_attr or DEFAULT_PRICE
        halls.append(_hall('Парная', '', cap_max_default, price, MIN_DURATION))
        assumed.append('залов во вкладке цен нет — один зал «Парная» по ' +
                       (f'«Цена от {money(price)}»' if price_attr else f'умолчанию {money(price)}/ч'))
    taken: set[str] = set()
    for h in halls:
        h['key'] = unique(slugify(h['name'], 30, '_') or 'hall', taken, 30)
        taken.add(h['key'])
    taken = set()
    for e in extras:
        e['key'] = unique(e['key'], taken, 30)
        taken.add(e['key'])
    return halls, extras, raw


def _hall(name: str, description: str, cap_max: int, per_hour: int, min_duration: int) -> dict:
    rule = {'from': '00:00', 'to': '24:00', 'price_per_hour_rub': per_hour}
    return {'key': '', 'name': name, 'description': description,
            'capacity_included': min(4, cap_max), 'capacity_max': cap_max,
            'extra_guest_price_rub': 300, 'extra_guest_unit': 'per_hour',
            'min_duration_min': min_duration, 'slot_step_min': 60, 'buffer_min': 30, 'photos': [],
            'tariffs': [{'effective_from': f'{date.today().year}-01-01',
                         'rules': [{'day_type': 'weekday', **rule}, {'day_type': 'weekend', **rule}]}]}


def make_hook(has_site: bool, updated: str | None, n_halls: int, today: date) -> str:
    parts = []
    if not has_site:
        parts.append('своего сайта нет, бронь только звонком или в мессенджере')
    since = old_prices_since(updated, today)
    if since:
        parts.append(f'цены в 2ГИС не обновлялись с {since}')
    if not parts:
        parts.append(f'залов {n_halls} с разными ценами, а выбрать время онлайн негде' if n_halls > 1
                     else 'выбрать время и забронировать онлайн негде — только звонок')
    text = '; '.join(parts)
    return text[0].upper() + text[1:]


def make_message(short: str, hall_names: list[str], has_site: bool, updated_old: str | None) -> str:
    halls = f'зал «{hall_names[0]}» с ценой' if len(hall_names) == 1 else \
        'залы ' + ', '.join(f'«{n}»' for n in hall_names) + ' с ценами'
    where = 'но забронировать зал онлайн с выбором времени не нашёл' if has_site else \
        'но записаться онлайн негде, только звонить'
    prices = f', а цены там ещё с {updated_old}' if updated_old else ''
    return (f'Здравствуйте! Искал баню и нашёл вас в 2ГИС — {where}{prices}. '
            f'Собрал для «{short}» пример приложения для брони: {halls}, гость сам выбирает зал, дату и время, '
            f'бронь сразу приходит вам в кабинет и на телефон. Посмотрите, это минута: [ссылка]. '
            f'Понравится — настрою под вас: фото, актуальные цены, часы. Не понравится — напишите, что не так.')


def _notes(prices: dict | None, hours_known: bool, halls: list[dict], cap_attr: int | None, hero: bool) -> list[str]:
    """Assumptions made on top of the halls' own notes, in the order they are reported."""
    notes = []
    if prices and (prices.get('pages') or 1) > 1:
        notes.append('в 2ГИС больше одной страницы цен — взята первая')
    if not hours_known:
        notes.append('часы работы в 2ГИС не указаны — взято круглосуточно')
    notes += [f'вместимость: {halls[0]["capacity_included"]} включено, до {halls[0]["capacity_max"]}'
              + (f' (в 2ГИС «до {cap_attr} человек» на всё заведение)' if cap_attr else ' (по умолчанию)'),
              'цена из 2ГИС взята как цена за час', 'одинаковый тариф будни/выходные',
              'мин. 2 ч, шаг 1 ч, буфер 30 мин, доплата 300 ₽/ч за гостя']
    if not hero:
        notes.append('обложки нет — hero.jpg не скачан')
    return notes


def _wordmark(short: str, extension: str | None, hours: str) -> dict[str, str]:
    """«Хлебниковские / Бани / баня · ежедневно …»: a trailing «бани/сауна» goes on top."""
    words = short.split()
    top = words[-1].capitalize() if len(words) > 1 and words[-1].lower() in ('бани', 'баня', 'сауна', 'сауны') else None
    main = wordmark_main(' '.join(words[:-1]) if top else short)
    sub = f"{extension or 'баня'} · {hours}"
    return {**({'top': top} if top else {}), 'main': main, 'sub': sub[:40]}


def _business(item: dict, slug: str, hero: bool, days: dict, hours: str, reach: Reach,
              c: dict[str, list[str]], halls: list[dict], extras: list[dict], amen: list[str]) -> dict[str, Any]:
    """bani-pwa business.json: halls booked by the hour."""
    short = short_name(item)
    district = district_of(item)
    wordmark = _wordmark(short, (item.get('name_ex') or {}).get('extension'), hours)
    amenity_text = [a for a in amen if not re.match(r'(Цена от|До \d)', a)]
    halls_count = {1: 'Один зал', 2: 'Два зала', 3: 'Три зала', 4: 'Четыре зала'}.get(len(halls), f'{len(halls)} залов')
    address = f"Москва, {item.get('address_name') or ''}".rstrip(', ')
    return {
        'schema_version': 1, 'timezone': 'Europe/Moscow', 'locale': 'ru-RU', 'currency': 'RUB',
        'legal': legal_block(legal_name(item, short)), 'policy': policy_block(),
        'working_hours': working_hours_block(days),
        'extras': extras, 'exceptions': [], 'slug': slug, 'name': short[:80],
        'theme': theme_block('#C8873A', hero, wordmark),
        'pwa': {'short_name': wordmark['main'][:12].strip(), 'description': f'Бронь залов: {short}'[:200]},
        'texts': {'tagline': ' · '.join(x for x in (halls_count, district, hours) if x)[:120],
                  'description': amenities_description(amenity_text),
                  'booking_note': 'Баня для гостей старше 18 лет.'},
        'contacts': business_contacts(reach, c, address, item.get('point') or {}, with_website=False),
        'halls': halls}


def build(item: dict, prices: dict | None, slug: str, hero: bool, today: date) -> dict[str, Any]:
    """→ {'lead', 'row', 'business', 'from_prices'} for one firm."""
    short = short_name(item)
    district = district_of(item)
    address = item.get('address_name') or ''
    c = contacts_of(item)
    amen = amenities_of(item)
    cap_attr = attr_number(amen, r'До\s+(\d+)\s+человек')
    price_attr = attr_number(amen, r'Цена от\s+([\d\s]+)')
    reviews = item.get('reviews') or {}

    assumed: list[str] = []
    halls, extras, raw = build_halls((prices or {}).get('items') or [], cap_attr, price_attr, assumed)
    days, hours, hours_known = schedule_of(item, min(h['min_duration_min'] for h in halls))
    assumed += _notes(prices, hours_known, halls, cap_attr, hero)

    updated = parse_updated((prices or {}).get('updated'))
    has_site = bool(c['website'])
    hook = make_hook(has_site, updated, len(halls), today)
    reach = reach_of(c, contact_book(item, LABEL_ROOM_BOOKING))
    hall_names = [h['name'] for h in halls]
    source = f'https://2gis.ru/moscow/firm/{firm_id(item)}'

    row = {'Баня': short, 'Демо (slug)': slug, **outreach_columns(reach, c, legal_name(item, short), short),
           'Адрес': f'Москва, {address} ({district})' if district else f'Москва, {address}'.rstrip(', '),
           'Залы': '; '.join(hall_names), 'Крючок': hook,
           'Сообщение': make_message(short, hall_names, has_site, old_prices_since(updated, today)),
           'Статус': 'новый', '2ГИС': source}

    contact = lead_contact(reach, c)
    lead = {'slug': slug, 'folder': f'tenants/{slug}', 'demo_path': f'/s/{slug}/', 'name': item.get('name') or short,
            'source': source, 'contact': {k: v for k, v in contact.items() if v},
            'rating': reviews.get('general_rating'), 'reviews': reviews.get('general_review_count'),
            'district': district, 'hours': hours, 'pitch': hook + '.', 'halls_from_2gis': raw,
            'prices_updated': updated, 'photos': photos_block(main_photo(item), source),
            'assumed': assumed, 'status': 'новый'}
    business = _business(item, slug, hero, days, hours, reach, c, halls, extras, amen)
    return {'lead': lead, 'row': row, 'business': business, 'from_prices': bool(raw)}
