"""Template spheres (car services, beauty salons, …): a lead, an outreach row and a business.json
laid out like the bathhouse export, with services instead of halls."""
from __future__ import annotations

import re
from datetime import date
from typing import TYPE_CHECKING, Any, Optional

from .build import schedule_of
from .contacts import Reach, business_contacts, contacts_of, lead_contact, outreach_columns, reach_of
from .demo import (amenities_description, legal_block, photos_block, policy_block, theme_block,
                   working_hours_block, wordmark_main)
from .firm import district_of, firm_id, legal_name, main_photo, short_name
from .prices import money, old_prices_since, parse_price, parse_updated
from .text import slugify, unique

if TYPE_CHECKING:
    from .spheres import Template

COLUMNS = ['Название', 'Демо (slug)', 'Писать сюда', 'Канал', 'Телефон основной', 'Телефоны доп.', 'Telegram',
           'Email', 'Руководитель', 'Юрлицо', 'Адрес', 'Услуги', 'Крючок', 'Сообщение', 'Статус', '2ГИС']
MAX_SERVICES = 30
TIMEZONES = {'moscow': 'Europe/Moscow', 'spb': 'Europe/Moscow', 'kazan': 'Europe/Moscow',
             'n_novgorod': 'Europe/Moscow', 'voronezh': 'Europe/Moscow', 'krasnodar': 'Europe/Moscow',
             'rostov': 'Europe/Moscow', 'sochi': 'Europe/Moscow', 'samara': 'Europe/Samara',
             'ekaterinburg': 'Asia/Yekaterinburg', 'chelyabinsk': 'Asia/Yekaterinburg', 'ufa': 'Asia/Yekaterinburg',
             'perm': 'Asia/Yekaterinburg', 'omsk': 'Asia/Omsk', 'novosibirsk': 'Asia/Novosibirsk',
             'krasnoyarsk': 'Asia/Krasnoyarsk', 'irkutsk': 'Asia/Irkutsk', 'vladivostok': 'Asia/Vladivostok'}


def build_services(items: list[dict], stub: str, assumed: list[str]) -> tuple[list[dict], list[dict]]:
    """Prices tab items → (services for business.json, services_from_2gis)."""
    services: list[dict] = []
    raw: list[dict] = []
    taken: set[str] = set()
    for it in items:
        parsed = parse_price(it.get('price') or {})
        name = ' '.join((it.get('name') or '').split())
        if not parsed or not name or len(services) >= MAX_SERVICES:
            continue
        price, is_from = parsed
        raw.append({'name': name, 'price': ('от ' if is_from else '') + money(price)})
        key = unique(slugify(name, 30, '_') or 'service', taken, 30)
        taken.add(key)
        services.append({'key': key, 'name': name[:80], 'description': (it.get('description') or '').strip()[:1000],
                         'section': it.get('section') or '', 'price_rub': price, 'price_from': is_from})
    if not services:
        services.append({'key': slugify(stub, 30, '_') or 'service', 'name': stub, 'description': '',
                         'section': '', 'price_rub': None, 'price_from': False})
        assumed.append(f'услуг во вкладке цен нет — одна услуга «{stub}» без цены')
    return services, raw


def make_hook(has_site: bool, updated: Optional[str], today: date) -> str:
    parts = []
    if not has_site:
        parts.append('своего сайта нет, запись только звонком или в мессенджере')
    since = old_prices_since(updated, today)
    if since:
        parts.append(f'цены в 2ГИС не обновлялись с {since}')
    if not parts:
        parts.append('записаться онлайн с выбором времени негде — только звонок')
    text = '; '.join(parts)
    return text[0].upper() + text[1:]


def make_message(short: str, noun: str, names: list[str], has_site: bool, updated_old: Optional[str]) -> str:
    shown = names[:3]
    services = f'услуга «{shown[0]}» с ценой' if len(shown) == 1 else \
        'услуги ' + ', '.join(f'«{n}»' for n in shown) + ' с ценами'
    where = 'но записаться онлайн с выбором времени не нашёл' if has_site else \
        'но записаться онлайн негде, только звонить'
    prices = f', а цены там ещё с {updated_old}' if updated_old else ''
    found = f'Искал {noun} и нашёл вас в 2ГИС' if noun else 'Нашёл вас в 2ГИС'
    return (f'Здравствуйте! {found} — {where}{prices}. '
            f'Собрал для «{short}» пример страницы с онлайн-записью: {services}, клиент сам выбирает услугу, '
            f'дату и время, заявка сразу приходит вам на телефон. Посмотрите, это минута: [ссылка]. '
            f'Понравится — настрою под вас: фото, актуальные цены, часы. Не понравится — напишите, что не так.')


def _amenities(item: dict) -> list[str]:
    return [a['name'] for g in item.get('attribute_groups') or [] for a in g.get('attributes') or []
            if a.get('name') and not re.match(r'(Цена от|До \d)', a['name'])]


def _address(item: dict, city: dict) -> str:
    return f"{city['name']}, {item.get('address_name') or ''}".rstrip(', ')


def _notes(prices: Optional[dict], hours_known: bool, city: dict, hero: bool) -> list[str]:
    """Assumptions made on top of the services' own notes, in the order they are reported."""
    notes = []
    if prices and (prices.get('pages') or 1) > 1:
        notes.append('в 2ГИС больше одной страницы цен — взята первая')
    if not hours_known:
        notes.append('часы работы в 2ГИС не указаны — взято круглосуточно')
    if city['code'] not in TIMEZONES:
        notes.append('часовой пояс города неизвестен — взят Europe/Moscow')
    if not hero:
        notes.append('обложки нет — hero.jpg не скачан')
    return notes


def _business(item: dict, t: Template, city: dict, slug: str, hero: bool, days: dict, hours: str,
              reach: Reach, c: dict[str, list[str]], services: list[dict]) -> dict[str, Any]:
    """business.json of the demo app with online booking of services."""
    short = short_name(item)
    district = district_of(item)
    main = wordmark_main(short)
    extension = (item.get('name_ex') or {}).get('extension') or t.title.lower()
    return {
        'schema_version': 1, 'sphere': t.id, 'timezone': TIMEZONES.get(city['code'], 'Europe/Moscow'),
        'locale': 'ru-RU', 'currency': 'RUB',
        'legal': legal_block(legal_name(item, short)), 'policy': policy_block(),
        'working_hours': working_hours_block(days),
        'exceptions': [], 'slug': slug, 'name': short[:80],
        'theme': theme_block(t.accent, hero, {'main': main, 'sub': f'{extension} · {hours}'[:40]}),
        'pwa': {'short_name': main[:12].strip(), 'description': f'Онлайн-запись: {short}'[:200]},
        'texts': {'tagline': ' · '.join(x for x in (district, hours) if x)[:120],
                  'description': amenities_description(_amenities(item)),
                  'booking_note': ''},
        'contacts': business_contacts(reach, c, _address(item, city), item.get('point') or {}, with_website=True),
        'services': services}


def build_generic(item: dict, prices: Optional[dict], slug: str, hero: bool, today: date,
                  t: Template, city: dict) -> dict[str, Any]:
    """→ {'lead', 'row', 'business', 'from_prices'} for one firm of a template sphere."""
    short = short_name(item)
    district = district_of(item)
    address = _address(item, city)
    c = contacts_of(item)
    reviews = item.get('reviews') or {}
    source = f"https://2gis.{city.get('domain') or 'ru'}/{city['code']}/firm/{firm_id(item)}"

    assumed: list[str] = []
    services, raw = build_services((prices or {}).get('items') or [], t.stub_service, assumed)
    days, hours, hours_known = schedule_of(item, 0)
    assumed += _notes(prices, hours_known, city, hero)

    updated = parse_updated((prices or {}).get('updated'))
    has_site = bool(c['website'])
    hook = make_hook(has_site, updated, today)
    reach = reach_of(c)
    names = [s['name'] for s in services]

    row = {'Название': short, 'Демо (slug)': slug, **outreach_columns(reach, c, legal_name(item, short), short),
           'Адрес': f'{address} ({district})' if district else address,
           'Услуги': '; '.join(names), 'Крючок': hook,
           'Сообщение': make_message(short, t.noun, names, has_site, old_prices_since(updated, today)),
           'Статус': 'новый', '2ГИС': source}

    contact = {**lead_contact(reach, c), 'website': c['website'][0] if c['website'] else None}
    lead = {'slug': slug, 'folder': f'tenants/{slug}', 'demo_path': f'/s/{slug}/', 'name': item.get('name') or short,
            'sphere': t.id, 'city': city['name'], 'source': source, 'contact': {k: v for k, v in contact.items() if v},
            'rating': reviews.get('general_rating'), 'reviews': reviews.get('general_review_count'),
            'district': district, 'hours': hours, 'pitch': hook + '.', 'services_from_2gis': raw,
            'prices_updated': updated, 'photos': photos_block(main_photo(item), source),
            'assumed': assumed, 'status': 'новый'}
    business = _business(item, t, city, slug, hero, days, hours, reach, c, services)
    return {'lead': lead, 'row': row, 'business': business, 'from_prices': bool(raw)}
