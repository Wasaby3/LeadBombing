"""Contacts of a firm from its 2GIS profile and the best channel to write to first.

Every contact of the card goes into the contact book with its 2GIS label (group name, group comment, contact
comment) or a default one. The label also gives the contact a role: the owner's contacts are tried first,
then general numbers, then booking, then other departments.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable, Optional

from .text import clean_url, fmt_phone, is_mobile, phone_digits

ROLE_OWNER = 'owner'
ROLE_GENERAL = 'general'
ROLE_BOOKING = 'booking'
ROLE_DEPARTMENT = 'department'
ROLE_ORDER = (ROLE_OWNER, ROLE_GENERAL, ROLE_BOOKING, ROLE_DEPARTMENT)

OWNER_RE = re.compile(r'директор|владел|руководител|управляющ|собственник|основател|\bceo\b', re.I)
BOOKING_RE = re.compile(r'запис|брон|резерв', re.I)
DEPARTMENT_RE = re.compile(r'бухгалт|отдел|кадр|снабжен|закуп|достав|склад|продаж|маркет|реклам|претенз|юрид|юрист'
                           r'|\bопт|тендер|партн[её]р', re.I)

KINDS = ('phone', 'whatsapp', 'telegram', 'vkontakte', 'website', 'email')  # what the export uses
PHONE_KINDS = ('phone', 'fax')
MESSENGER_KINDS = ('whatsapp', 'telegram', 'viber', 'max')
VOICE_KINDS = ('phone',) + MESSENGER_KINDS  # labelled «для записи / бронирования» by default
SOCIAL_KINDS = ('vkontakte', 'instagram', 'facebook', 'odnoklassniki', 'youtube', 'twitter', 'linkedin',
                'pinterest', 'googleplus')
TITLES = {'phone': 'Телефон', 'fax': 'Факс', 'email': 'Email', 'website': 'Сайт', 'whatsapp': 'WhatsApp',
          'telegram': 'Telegram', 'viber': 'Viber', 'max': 'MAX', 'vkontakte': 'ВКонтакте', 'instagram': 'Instagram',
          'facebook': 'Facebook', 'odnoklassniki': 'Одноклассники', 'youtube': 'YouTube', 'twitter': 'Twitter',
          'linkedin': 'LinkedIn', 'pinterest': 'Pinterest', 'googleplus': 'Google+', 'skype': 'Skype',
          'icq': 'ICQ', 'jabber': 'Jabber', 'pobox': 'Абонентский ящик'}
DEFAULT_LABELS = {'website': 'сайт фирмы', 'email': 'почта фирмы', 'fax': 'факс', 'pobox': 'для писем'}
SOCIAL_LABEL = 'страница фирмы'
LABEL_SERVICE_BOOKING = 'для записи'  # default label of a phone or messenger
LABEL_ROOM_BOOKING = 'для бронирования'  # the same for bathhouses
OTHER_LABEL = 'для связи'
URL_SCHEME_RE = re.compile(r'^[a-z][a-z0-9+.-]*://', re.I)


@dataclass(frozen=True)
class Reach:
    """How to reach a firm: the channel to write first, formatted phones and the main one.

    `public_*` are for the demo page clients see: never the owner's own number when the firm has another one.
    """
    write_first: str
    write_here: str
    channel: str
    phones: list[str]
    main_phone: str
    whatsapp: Optional[str]  # WhatsApp of the chosen channel, else the first one on a mobile number
    public_phone: str
    public_whatsapp: Optional[str]


@dataclass(frozen=True)
class _Entry:
    kind: str
    raw: str
    labels: tuple[str, ...]


def _raw_value(kind: str, contact: dict) -> str:
    """The contact's value as 2GIS gives it: a phone/e-mail as is, a link without utm (2GIS redirects resolved)."""
    if kind in ('phone', 'email', 'fax'):
        return (contact.get('value') or contact.get('text') or '').strip()
    value = contact.get('url') or contact.get('value') or contact.get('text') or ''
    if 'link.2gis' in value and contact.get('text'):  # 2GIS redirect link
        value = contact['text'] if '://' in contact['text'] else 'http://' + contact['text']
    return value.strip() if kind == 'viber' else clean_url(value)  # viber://chat?number=… keeps its number


def _key(kind: str, value: str) -> tuple[str, str]:
    return kind, phone_digits(value) if kind in PHONE_KINDS else value.lower()


def contacts_of(item: dict) -> dict[str, list[str]]:
    """Values of the kinds the export uses ({kind: [value, …]}, in card order, without repeats)."""
    out: dict[str, list[str]] = {k: [] for k in KINDS}
    for group in item.get('contact_groups') or []:
        for c in group.get('contacts') or []:
            kind = c.get('type')
            if kind not in out:
                continue
            value = _raw_value(kind, c)
            if value and value not in out[kind]:
                out[kind].append(value)
    return out


def _join(parts: Iterable[Optional[str]], sep: str) -> str:
    seen: list[str] = []
    for p in parts:
        text = ' '.join((p or '').split())
        if text and text.lower() not in (s.lower() for s in seen):
            seen.append(text)
    return sep.join(seen)


def _role(label: str) -> str:
    if OWNER_RE.search(label):
        return ROLE_OWNER
    if BOOKING_RE.search(label):
        return ROLE_BOOKING
    if DEPARTMENT_RE.search(label):
        return ROLE_DEPARTMENT
    return ROLE_GENERAL


def _best_role(labels: Iterable[str]) -> str:
    return min((_role(label) for label in labels), key=ROLE_ORDER.index, default=ROLE_GENERAL)


def _entries(item: dict) -> list[_Entry]:
    """Every contact of the card once (the same value in two groups keeps both labels)."""
    found: dict[tuple[str, str], list[_Entry]] = {}
    for group in item.get('contact_groups') or []:
        for c in group.get('contacts') or []:
            kind = c.get('type') or ''
            raw = _raw_value(kind, c)
            if raw:
                label = _join((group.get('name'), group.get('comment'), c.get('comment')), ' · ')
                found.setdefault(_key(kind, raw), []).append(_Entry(kind, raw, (label,)))
    return [_Entry(same[0].kind, same[0].raw, tuple(_join((e.labels[0] for e in same), '; ').split('; ')))
            for same in found.values()]


def _messenger_phone(entry: _Entry) -> str:
    digits = phone_digits(entry.raw)
    return digits if entry.kind in MESSENGER_KINDS and len(digits) == 11 and digits[0] == '7' else ''


def _default_label(kind: str, booking_label: str) -> str:
    if kind in VOICE_KINDS:
        return booking_label
    if kind in SOCIAL_KINDS:
        return SOCIAL_LABEL
    return DEFAULT_LABELS.get(kind, OTHER_LABEL)


def _href(kind: str, raw: str) -> Optional[str]:
    if kind in PHONE_KINDS:
        digits = phone_digits(raw)
        return f'tel:+{digits}' if len(digits) == 11 else f'tel:{digits}'
    if kind == 'email':
        return f'mailto:{raw}'
    return raw if URL_SCHEME_RE.match(raw) else None


def _title(kind: str) -> str:
    return TITLES.get(kind) or (f'Прочее ({kind})' if kind else 'Прочее')


def contact_book(item: dict, booking_label: str) -> list[dict[str, Any]]:
    """All contacts of the card for the lead card, the owner's first.

    Each: type, title, value, href, label, label_source ('2gis' | 'phone' — the label of a phone with the same
    number | 'default') and role (owner | general | booking | department).
    """
    entries = _entries(item)
    phone_labels = {phone_digits(e.raw): e.labels for e in entries if e.kind == 'phone' and any(e.labels)}
    book = []
    for e in entries:
        labels, source = [label for label in e.labels if label], '2gis'
        if not labels and phone_labels.get(_messenger_phone(e)):
            labels, source = list(phone_labels[_messenger_phone(e)]), 'phone'
        value = fmt_phone(e.raw) if e.kind in PHONE_KINDS else e.raw
        book.append({'type': e.kind, 'title': _title(e.kind), 'value': value, 'href': _href(e.kind, e.raw),
                     'label': '; '.join(labels) or _default_label(e.kind, booking_label),
                     'label_source': source if labels else 'default', 'role': _best_role(labels)})
    return sorted(book, key=lambda c: ROLE_ORDER.index(c['role']))


MARK_OWNER = 'owner'  # 2GIS labels a contact as the director/owner
MARK_MAYBE = 'maybe'  # a guess: a general mobile phone of a sole trader, or the card's only phone


def owner_mark(book: list[dict], is_ip: bool) -> str:
    """'owner', 'maybe' or '' for the leads table (from `contact_book` and whether the firm is an ИП).

    Keep in sync with `markLikelyOwner` in web/static/app/app.js, which marks the very phone in the lead card.
    """
    if any(c.get('role') == ROLE_OWNER for c in book):
        return MARK_OWNER
    phones = [c for c in book if c.get('type') == 'phone']
    if not (is_ip or len(phones) == 1):
        return ''
    found = any(is_mobile(c.get('value') or '') and c.get('role') == ROLE_GENERAL for c in phones)
    return MARK_MAYBE if found else ''


def card_owner_mark(card: dict) -> str:
    """`owner_mark` of a lead card or `lead` event (its `contacts` and `legal`); '' for cards saved before them."""
    return owner_mark(card.get('contacts') or [], bool((card.get('legal') or {}).get('owner')))


def _roles(book: Iterable[dict]) -> dict[tuple[str, str], str]:
    return {_key(c['type'], c['value']): c['role'] for c in book}


def _with_role(c: dict[str, list[str]], roles: dict[tuple[str, str], str], keep: Iterable[str]) -> dict[str, list[str]]:
    wanted = set(keep)
    return {k: [v for v in values if roles.get(_key(k, v), ROLE_GENERAL) in wanted] for k, values in c.items()}


def _pick(c: dict[str, list[str]]) -> Optional[tuple[str, str, str]]:
    wa = [w for w in c['whatsapp'] if is_mobile(w)]
    if wa:
        return 'whatsapp', wa[0], 'WhatsApp (мобильный из 2ГИС)'
    if c['telegram']:
        return 'telegram', c['telegram'][0], 'Telegram'
    if c['vkontakte']:
        return 'vk', c['vkontakte'][0], 'ВКонтакте'
    mobiles = [p for p in c['phone'] if is_mobile(p)]
    if mobiles:
        return 'phone', fmt_phone(mobiles[0]), 'Звонок/SMS (мобильный)'
    if c['phone']:
        return 'phone', fmt_phone(c['phone'][0]), 'Звонок (городской)'
    return None


def pick_channel(c: dict[str, list[str]]) -> tuple[str, str, str]:
    """→ (write_first, where, channel label): WhatsApp on a mobile → Telegram → VK → mobile → any phone."""
    picked = _pick(c)
    if picked is None:
        raise ValueError('У фирмы нет ни телефона, ни мессенджера')
    return picked


def _main_phone(c: dict[str, list[str]], any_phone: bool = False) -> str:
    """The WhatsApp mobile if it is listed among phones, else the first mobile (else any phone, or none)."""
    wa_phone = next((fmt_phone(w) for w in c['whatsapp'] if is_mobile(w)), None)
    mobiles = [fmt_phone(p) for p in c['phone'] if is_mobile(p)]
    if wa_phone in mobiles:
        return wa_phone or ''
    if mobiles:
        return mobiles[0]
    return fmt_phone(c['phone'][0]) if any_phone and c['phone'] else ''


def _first_mobile_whatsapp(c: dict[str, list[str]]) -> Optional[str]:
    return next((w for w in c['whatsapp'] if is_mobile(w)), None)


def reach_of(c: dict[str, list[str]], book: Iterable[dict] = ()) -> Reach:
    """Channel and main phone by role: owner → general → booking → other departments (see `contact_book`).

    Within a role: WhatsApp on a mobile → Telegram → VK → mobile → any phone. Without labels every contact
    is general, so the choice is the same as by the channel order alone.
    """
    roles = _roles(book)
    tiers = [(role, _with_role(c, roles, [role])) for role in ROLE_ORDER]
    write_first, write_here, channel = next((p for p in (_pick(t) for _, t in tiers) if p), None) or pick_channel(c)
    main_phone = next((m for m in (_main_phone(t, role == ROLE_OWNER) for role, t in tiers) if m), '')
    public = _with_role(c, roles, ROLE_ORDER[1:])
    if not public['phone']:
        public = c
    return Reach(write_first, write_here, channel, [fmt_phone(p) for p in c['phone']], main_phone,
                 write_here if write_first == 'whatsapp' else _first_mobile_whatsapp(c),
                 _main_phone(public) or fmt_phone(public['phone'][0]), _first_mobile_whatsapp(public))


def outreach_columns(reach: Reach, c: dict[str, list[str]], legal: Optional[str], short: str) -> dict[str, str]:
    """outreach.csv columns «Писать сюда» … «Юрлицо», shared by every sphere."""
    return {'Писать сюда': reach.write_here, 'Канал': reach.channel,
            'Телефон основной': reach.main_phone,
            'Телефоны доп.': '; '.join(p for p in reach.phones if p != reach.main_phone),
            'Telegram': c['telegram'][0] if c['telegram'] else '', 'Email': c['email'][0] if c['email'] else '',
            'Руководитель': 'не найден', 'Юрлицо': legal if legal and legal != short else ''}


def lead_contact(reach: Reach, c: dict[str, list[str]]) -> dict[str, Any]:
    """leads.json `contact` before empty values are dropped."""
    return {'write_first': reach.write_first, 'whatsapp': reach.whatsapp,
            'telegram': c['telegram'][0] if c['telegram'] else None,
            'phones': reach.phones, 'email': c['email'][0] if c['email'] else None}


def business_contacts(reach: Reach, c: dict[str, list[str]], address: str, point: dict,
                      with_website: bool) -> dict[str, Any]:
    """business.json `contacts`: only values the demo app can use (valid e-mail, short Telegram, coordinates)."""
    out: dict[str, Any] = {'phone': reach.public_phone, 'address': address}
    if reach.public_whatsapp:
        out['whatsapp'] = '+' + phone_digits(reach.public_whatsapp)
    if c['telegram'] and len(c['telegram'][0]) <= 64:
        out['telegram'] = c['telegram'][0]
    if c['email'] and re.fullmatch(r'[^@\s]+@[^@\s]+\.[a-z]{2,}', c['email'][0], re.I):
        out['email'] = c['email'][0]
    if with_website and c['website']:
        out['website'] = c['website'][0]
    if point.get('lat') and point.get('lon'):
        out['coords'] = {'lat': point['lat'], 'lng': point['lon']}
    return out
