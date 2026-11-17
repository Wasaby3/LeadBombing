"""Contacts of a firm from its 2GIS profile and the best channel to write to first."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Optional

from .text import clean_url, fmt_phone, is_mobile, phone_digits


@dataclass(frozen=True)
class Reach:
    """How to reach a firm: the channel to write first, formatted phones and the main one."""
    write_first: str
    write_here: str
    channel: str
    phones: list[str]
    main_phone: str
    whatsapp: Optional[str]  # first WhatsApp on a mobile number, as found in 2GIS


def contacts_of(item: dict) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {k: [] for k in ('phone', 'whatsapp', 'telegram', 'vkontakte', 'website', 'email')}
    for group in item.get('contact_groups') or []:
        for c in group.get('contacts') or []:
            kind = c.get('type')
            if kind not in out:
                continue
            if kind in ('phone', 'email'):
                value = c.get('value') or c.get('text') or ''
            else:
                value = c.get('url') or c.get('value') or ''
                if 'link.2gis' in value and c.get('text'):  # 2GIS redirect link
                    value = c['text'] if '://' in c['text'] else 'http://' + c['text']
                value = clean_url(value)
            if value and value not in out[kind]:
                out[kind].append(value)
    return out


def pick_channel(c: dict[str, list[str]]) -> tuple[str, str, str]:
    """→ (write_first, where, channel label): WhatsApp on a mobile → Telegram → VK → mobile → any phone."""
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
    return 'phone', fmt_phone(c['phone'][0]), 'Звонок (городской)'


def reach_of(c: dict[str, list[str]]) -> Reach:
    """Main phone: the WhatsApp mobile if it is listed among phones, else the first mobile, else none."""
    write_first, write_here, channel = pick_channel(c)
    wa_phone = next((fmt_phone(w) for w in c['whatsapp'] if is_mobile(w)), None)
    mobiles = [fmt_phone(p) for p in c['phone'] if is_mobile(p)]
    phones = [fmt_phone(p) for p in c['phone']]
    main_phone = wa_phone if wa_phone in mobiles else (mobiles[0] if mobiles else '')
    whatsapp = next((w for w in c['whatsapp'] if is_mobile(w)), None)
    return Reach(write_first, write_here, channel, phones, main_phone, whatsapp)


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
    out: dict[str, Any] = {'phone': reach.main_phone or reach.phones[0], 'address': address}
    if reach.whatsapp:
        out['whatsapp'] = '+' + phone_digits(reach.whatsapp)
    if c['telegram'] and len(c['telegram'][0]) <= 64:
        out['telegram'] = c['telegram'][0]
    if c['email'] and re.fullmatch(r'[^@\s]+@[^@\s]+\.[a-z]{2,}', c['email'][0], re.I):
        out['email'] = c['email'][0]
    if with_website and c['website']:
        out['website'] = c['website'][0]
    if point.get('lat') and point.get('lon'):
        out['coords'] = {'lat': point['lat'], 'lng': point['lon']}
    return out
