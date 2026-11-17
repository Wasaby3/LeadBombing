"""Phones, transliteration and slugs for the leads export."""
from __future__ import annotations

import re

_TR = dict(zip('абвгдеёжзийклмнопрстуфхцчшщъыьэюя',
               'a b v g d e e zh z i y k l m n o p r s t u f h ts ch sh sch _ y _ e yu ya'.split()))


def translit(text: str) -> str:
    return ''.join(_TR.get(ch, ch) for ch in text.lower()).replace('_', '')


def slugify(text: str, max_len: int = 40, sep: str = '-') -> str:
    slug = re.sub(r'[^a-z0-9]+', sep, translit(text)).strip(sep)
    if len(slug) > max_len:
        slug = slug[:max_len].rsplit(sep, 1)[0] or slug[:max_len]
    return slug


def unique(base: str, taken: set[str], max_len: int = 40) -> str:
    """`base`, or `base-2`, `base-3`… not in `taken`."""
    candidate, i = base, 2
    while candidate in taken:
        suffix = f'-{i}'
        candidate = base[:max_len - len(suffix)].rstrip('-') + suffix
        i += 1
    return candidate


def phone_digits(phone: str) -> str:
    """'+7 (985) 384-76-70' / '8985…' / wa.me link → '79853847670'."""
    d = re.sub(r'\D', '', phone)
    if len(d) == 11 and d[0] == '8':
        d = '7' + d[1:]
    elif len(d) == 10:
        d = '7' + d
    return d


def fmt_phone(phone: str) -> str:
    d = phone_digits(phone)
    if len(d) != 11 or d[0] != '7':
        return phone.strip()
    return f'+7 {d[1:4]} {d[4:7]}-{d[7:9]}-{d[9:]}'


def is_mobile(phone: str) -> bool:
    d = phone_digits(phone)
    return len(d) == 11 and d[:2] == '79'


def clean_url(url: str) -> str:
    """Drop query (utm, prefilled WhatsApp text) and fragment."""
    return re.split(r'[?#]', url.strip(), maxsplit=1)[0]
