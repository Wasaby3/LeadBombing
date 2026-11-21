"""Search spheres for the leads export.

`bani` is the original bathhouse template (Moscow only, output unchanged).
The other spheres are templates built on `generic.build_generic` with a similar folder layout.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Any, Optional

from . import build as bani_build
from . import generic
from .contacts import LABEL_ROOM_BOOKING, LABEL_SERVICE_BOOKING

BANI_COLUMNS = ['Баня', 'Демо (slug)', 'Писать сюда', 'Канал', 'Телефон основной', 'Телефоны доп.', 'Telegram',
                'Email', 'Руководитель', 'Юрлицо', 'Адрес', 'Залы', 'Крючок', 'Сообщение', 'Статус', '2ГИС']
BANI_RUBRIC = 'Бани и сауны'
MAX_BRANCHES = 5
BANI_EXCLUDE_RE = re.compile(r'фитнес|гостиниц|отел|хостел|аквапарк|термальн|санатори|бассейн', re.I)
BANI_EXCLUDE_NAME_RE = re.compile(r'\bтермы\b|аквапарк|фитнес|spa[- ]?отель|отель', re.I)
TEMPLATE_NOTE = 'Шаблон: структура как у бань, тексты и поля под сферу'
CUSTOM_NOTE = 'Свободный поиск: все фирмы из выдачи 2ГИС по вашему запросу, выгрузка как у шаблонов'

MOSCOW = {'code': 'moscow', 'name': 'Москва', 'domain': 'ru'}
NO_DEMO_URL = '[ссылка на демо]'
# The message of a saved bathhouse lead's card (never exported): {demo_url} is the lead's demo app link.
BANI_DEMO_MESSAGE = (
    'Здравствуйте! Хотел на днях с друзьями забронировать у вас баню, но не нашел, как это сделать быстро онлайн, '
    'а звонить не стал. К тому же если кто-то не может дозвониться то бронирует другую баню.\n'
    'как раз делаю такие штуки, поэтому собрал вам онлайн-запись с вашим названием, прайсом и залами: \n'
    '{demo_url}\n'
    'Домен пока временный, поэтому сайт так странно называется). Если понравится, перенесу на нормальный. '
    'Фото тоже поставлю ваши.\n'
    'Открывается как приложение: заходите по ссылке с телефона, в меню браузера жмёте «Добавить на главный экран», '
    'и рядом с остальными приложениями появляется ваша иконка. Запускается на весь экран без строки браузера, '
    'при этом ни вам, ни клиентам ничего скачивать не надо.\n'
    'Клиент сам выбирает услугу и время, запись сразу падает вам в кабинет, а слот на это время закрывается. '
    'Цены и фото поставим ваши.\n'
    'Гляньте, как будет минутка, и скажите, как вам.')


def _has_phone(item: dict) -> bool:
    return any(c.get('type') == 'phone' for g in item.get('contact_groups') or [] for c in g.get('contacts') or [])


def _primary_rubric(item: dict) -> Optional[str]:
    return next((r.get('name') for r in item.get('rubrics') or [] if r.get('kind') == 'primary'), None)


def _city_of(item: dict, cities: list[dict]) -> Optional[dict]:
    """The selected city the firm belongs to (by its city or region name)."""
    adm = {a.get('type'): a.get('name') for a in item.get('adm_div') or []}
    return next((c for c in cities if c['name'] in (adm.get('city'), adm.get('region'))), None)


def _is_chain(item: dict) -> bool:
    return ((item.get('org') or {}).get('branch_count') or 1) >= MAX_BRANCHES


class BaniSphere:
    """Original bathhouse template: rubric «Бани и сауны», Moscow, halls from the prices tab."""
    id = 'bani'
    title = 'Бани и сауны'
    query = 'Бани и сауны'
    note = 'Старый шаблон: только Москва, вывод точь-в-точь как раньше'
    fixed_city = 'moscow'
    columns = BANI_COLUMNS
    slug_prefix = 'banya'
    contact_label = LABEL_ROOM_BOOKING  # default label of an unlabelled phone in the lead card
    from_prices_label = ('Залы из вкладки цен', 'заглушка «Парная»')
    cities = [MOSCOW]

    def filter_reason(self, item: dict) -> Optional[str]:
        if not _city_of(item, self.cities):
            return 'не Москва'
        rubrics = item.get('rubrics') or []
        if _primary_rubric(item) != BANI_RUBRIC:
            return f'основная рубрика не «{BANI_RUBRIC}»'
        names = ' '.join(r.get('name') or '' for r in rubrics)
        if BANI_EXCLUDE_RE.search(names) or BANI_EXCLUDE_NAME_RE.search(item.get('name') or ''):
            return 'фитнес / отель / бассейн / термы'
        if _is_chain(item):
            return f'сеть от {MAX_BRANCHES} филиалов'
        if not _has_phone(item):
            return 'нет телефона'
        return None

    def build(self, item: dict, prices: Optional[dict], slug: str, hero: bool, today: date) -> dict[str, Any]:
        return bani_build.build(item, prices, slug, hero, today)

    def demo_message(self, demo_url: Optional[str]) -> Optional[str]:
        """The saved lead card's message with its demo app link (a placeholder until there is one)."""
        return BANI_DEMO_MESSAGE.format(demo_url=demo_url or NO_DEMO_URL)


@dataclass(frozen=True)
class Template:
    """Settings of a template sphere."""
    id: str
    title: str
    query: str
    rubric_re: str  # the primary rubric must match ('' — any rubric)
    exclude_re: str  # neither the primary rubric nor the firm name may match ('' — no exclusions)
    noun: str  # «Искал <noun> и нашёл вас в 2ГИС» ('' — «Нашёл вас в 2ГИС»)
    stub_service: str  # used when the prices tab is empty
    slug_prefix: str
    accent: str


TEMPLATES = [
    Template('auto', 'Автосервисы', 'Автосервис',
             r'автосервис|ремонт|шиномонтаж|кузовн|техобслуживан|диагностик|автоэлектрик|развал',
             r'автомойк|автосалон|запчаст|автомагазин|эвакуат|дилер',
             'автосервис', 'Диагностика', 'auto', '#E4572E'),
    Template('beauty', 'Салоны красоты', 'Салон красоты',
             r'салон|парикмахер|ногтев|маникюр|косметолог|бров|ресниц|визаж|эпиляц',
             r'магазин|учебн|школа|обучени|оптов',
             'салон красоты', 'Стрижка', 'beauty', '#C2185B'),
    Template('dental', 'Стоматологии', 'Стоматология',
             r'стоматолог',
             r'оборудован|материал|поликлиник|зуботехническ',
             'стоматологию', 'Консультация', 'dental', '#1E88E5'),
]


class TemplateSphere:
    """A template sphere searched in one or more cities."""
    columns = generic.COLUMNS
    from_prices_label = ('Услуги из вкладки цен', 'без цен')
    fixed_city = None
    contact_label = LABEL_SERVICE_BOOKING

    def __init__(self, template: Template, cities: list[dict]) -> None:
        if not cities:
            raise ValueError('Выберите хотя бы один город')
        self.template = template
        self.cities = list(cities)
        self.id, self.title, self.query = template.id, template.title, template.query
        self.slug_prefix = template.slug_prefix
        self.note = CUSTOM_NOTE if template.id == CUSTOM_ID else TEMPLATE_NOTE
        self._rubric_re = re.compile(template.rubric_re, re.I) if template.rubric_re else None
        self._exclude_re = re.compile(template.exclude_re, re.I) if template.exclude_re else None

    def filter_reason(self, item: dict) -> Optional[str]:
        if not _city_of(item, self.cities):
            return f'не {self.cities[0]["name"]}' if len(self.cities) == 1 else 'не из выбранных городов'
        primary = _primary_rubric(item) or ''
        if self._rubric_re and not self._rubric_re.search(primary):
            return f'основная рубрика не «{self.title}»'
        if self._exclude_re and (self._exclude_re.search(primary) or self._exclude_re.search(item.get('name') or '')):
            return 'другой профиль (магазин, мойка, обучение…)'
        if _is_chain(item):
            return f'сеть от {MAX_BRANCHES} филиалов'
        if not _has_phone(item):
            return 'нет телефона'
        return None

    def build(self, item: dict, prices: Optional[dict], slug: str, hero: bool, today: date) -> dict[str, Any]:
        city = _city_of(item, self.cities) or self.cities[0]
        return generic.build_generic(item, prices, slug, hero, today, self.template, city)

    def demo_message(self, demo_url: Optional[str]) -> Optional[str]:
        """No demo message for templates yet: the card keeps the message made by the search."""
        return None


def sphere_list() -> list[dict[str, Any]]:
    """Spheres for the UI picker."""
    bani = BaniSphere()
    out = [{'id': bani.id, 'title': bani.title, 'query': bani.query, 'note': bani.note, 'fixed_city': bani.fixed_city}]
    out += [{'id': t.id, 'title': t.title, 'query': t.query, 'note': TEMPLATE_NOTE, 'fixed_city': None}
            for t in TEMPLATES]
    return out


CUSTOM_ID = 'custom'


def get_sphere(sphere_id: str = 'bani', cities: Optional[list[dict]] = None, query: str = ''):
    """Sphere by id; template spheres need cities ([{code, name, domain}]).

    `custom` is a free search: any firm found by `query`, no rubric filter.
    """
    if sphere_id == 'bani':
        return BaniSphere()
    if sphere_id == CUSTOM_ID:
        if not query.strip():
            raise ValueError('Введите, что искать в 2ГИС')
        template = Template(CUSTOM_ID, 'Свободный поиск', query.strip(), '', '', '', 'Услуга', 'firm', '#5b5bd6')
    else:
        template = next((t for t in TEMPLATES if t.id == sphere_id), None)
        if template is None:
            raise ValueError(f'Неизвестная сфера: {sphere_id}')
    return TemplateSphere(template, cities or [MOSCOW])
