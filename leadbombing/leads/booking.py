"""Lead priority from the 2GIS card: where its «Забронировать» button leads and whether the firm has its own site.

The button is a 2GIS ad feature, so many firms have none. It is not in the firm profile but in the page's search
context: `initialState.data.searchContext["<uuid>_<firm id>"].ads.options.actions`, each action a phone number or a
`link.2gis.ru` redirect with the real address after `?`. Pure functions, no network: the parser reads the actions
with `BOOKING_EXPR` in the same request as the prices tab.

Priority 5 is the hottest lead (no site, booking only by phone), 1 the coldest (online booking in a known service),
0 means no data about the button.
"""
from __future__ import annotations

import re
from typing import Any, Iterable, Optional
from urllib.parse import unquote, urlsplit

from .contacts import BOOKING_RE, _raw_value
from .text import clean_url

# JS over a firm page `initialState` (`s`), %s = firm id as JSON string. null when the page has no search context
# (2GIS changed its layout), [] when the firm has no ad actions.
BOOKING_EXPR = '''(() => {
    const ctx = s.data?.searchContext;
    if (!ctx) return null;
    const key = Object.keys(ctx).find(k => k.endsWith('_' + %s));
    return (key && ctx[key]?.ads?.options?.actions) || [];
})()'''

KIND_NONE = 'none'
KIND_PHONE = 'phone'
KIND_MESSENGER = 'messenger'
KIND_SERVICE = 'booking_service'
KIND_PAGE = 'booking_page'
KIND_SITE = 'site'

REDIRECT_HOSTS = ('link.2gis.ru', 'link.2gis.com')
MESSENGER_HOSTS = ('wa.me', 'whatsapp.com', 't.me', 'telegram.me', 'max.ru', 'vk.me', 'viber.com')
SOCIAL_HOSTS = ('vk.com', 'vk.ru', 'ok.ru', 'instagram.com', 'facebook.com', 'youtube.com', 'youtu.be', 'dzen.ru',
                'tiktok.com', 'rutube.ru')
BOOKING_SERVICES = {'yclients.com': 'YCLIENTS', 'dikidi.net': 'DIKIDI', 'dikidi.ru': 'DIKIDI', 'sonline.su': 'Sonline',
                    'altegio.com': 'Altegio', 'alteg.io': 'Altegio', 'easyweek.ru': 'EasyWeek',
                    'easyweek.io': 'EasyWeek', 'bnovo.ru': 'Bnovo', 'travelline.ru': 'TravelLine',
                    'bukza.com': 'Bukza', 'arnica.pro': 'Arnica', 'prodoctorov.ru': 'ПроДокторов',
                    'napopravku.ru': 'НаПоправку', 'medflex.ru': 'MedFlex'}
BOOKING_PATH_RE = re.compile(r'book|bron|zapis|reserv|record|appoint|брон|запис', re.I)
SCHEME_RE = re.compile(r'^[a-z][a-z0-9+.-]*://', re.I)

NO_BUTTON: dict[str, str] = {'kind': KIND_NONE, 'caption': '', 'value': ''}


def _host(url: str) -> str:
    host = (urlsplit(url if SCHEME_RE.match(url) else 'http://' + url).hostname or '').lower()
    return host[4:] if host.startswith('www.') else host


def _on(host: str, domains: Iterable[str]) -> Optional[str]:
    """The domain from `domains` the host belongs to (itself or a subdomain), else None."""
    return next((d for d in domains if host == d or host.endswith('.' + d)), None)


def _display(url: str) -> str:
    """Address without scheme, query and fragment: 'https://bani.ru/booking?utm=1' → 'bani.ru/booking'."""
    return SCHEME_RE.sub('', clean_url(url))


def own_sites(item: dict) -> list[str]:
    """The firm's own sites from the card, without messengers and social pages 2GIS also lists as websites."""
    sites: list[str] = []
    for group in item.get('contact_groups') or []:
        for c in group.get('contacts') or []:
            url = _raw_value('website', c) if c.get('type') == 'website' else ''
            host = _host(url) if url else ''
            site = _display(url).rstrip('/')
            if host and not _on(host, MESSENGER_HOSTS + SOCIAL_HOSTS) and site not in sites:
                sites.append(site)
    return sites


def _target(value: str) -> str:
    """The real address of a 2GIS redirect link (after the first `?`), else the link itself."""
    if _on(_host(value), REDIRECT_HOSTS) and '?' in value:
        value = value.split('?', 1)[1]
        return unquote(value) if value.lower().startswith(('http%3a', 'https%3a')) else value
    return value


def _link_kind(url: str) -> str:
    host = _host(url)
    if _on(host, MESSENGER_HOSTS):
        return KIND_MESSENGER
    if _on(host, BOOKING_SERVICES):
        return KIND_SERVICE
    return KIND_PAGE if BOOKING_PATH_RE.search(urlsplit(url).path) else KIND_SITE


def button_of(actions: Optional[list]) -> Optional[dict[str, str]]:
    """The booking button {kind, caption, value} from the firm's ad actions; None when there is no data."""
    if actions is None:
        return None
    action = next((a for a in actions if isinstance(a, dict) and BOOKING_RE.search(a.get('caption') or '')), None)
    if not action:
        return dict(NO_BUTTON)
    caption, value = action['caption'].strip(), str(action.get('value') or '').strip()
    if action.get('type') == 'phone':
        return {'kind': KIND_PHONE, 'caption': caption, 'value': value}
    url = _target(value)
    return {'kind': _link_kind(url), 'caption': caption, 'value': _display(url)}


def _rule(sites: list[str], button: dict[str, str]) -> tuple[int, str]:
    kind, caption, value = button['kind'], f'«{button["caption"]}»', button['value']
    site = sites[0] if sites else ''
    if kind == KIND_SERVICE:
        service = BOOKING_SERVICES[_on(_host(value), BOOKING_SERVICES) or '']
        return 1, f'Кнопка {caption} ведёт в сервис онлайн-брони {service} — услуга вряд ли нужна'
    if kind == KIND_PAGE:
        return 2, f'Кнопка {caption} ведёт на страницу брони {value.rstrip("/")}'
    if kind == KIND_SITE:
        return 3, f'Кнопка {caption} ведёт на сайт {_host(value)} — удобство брони не проверено'
    if kind in (KIND_PHONE, KIND_MESSENGER):
        how = 'звонок' if kind == KIND_PHONE else 'сообщение в мессенджер'
        if site:
            return 4, f'Сайт {site} есть, но кнопка {caption} в 2ГИС — {how}'
        return 5, f'Сайта нет, кнопка {caption} в 2ГИС — {how}'
    if site:
        return 3, f'Сайт {site} есть, кнопки брони в 2ГИС нет — удобство брони на сайте не проверено'
    return 4, 'Ни сайта, ни кнопки брони в 2ГИС — бронь только по телефону'


def assess(item: dict, actions: Optional[list]) -> dict[str, Any]:
    """{priority 0–5, note for the lead's comment, button} from the card and its ad actions (None: no data)."""
    button = button_of(actions)
    if button is None:
        return {'priority': 0, 'note': '', 'button': None}
    priority, note = _rule(own_sites(item), button)
    return {'priority': priority, 'note': note, 'button': button}
