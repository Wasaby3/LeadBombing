"""Prices tab of a firm: JS to read it from 2GIS, price parsing and the «prices are old» check."""
from __future__ import annotations

import re
from datetime import date
from typing import Optional

OLD_PRICES_DAYS = 183  # prices not updated for half a year count as old
MONTHS = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня',
          'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря']

# JS over the prices tab `initialState` (`s`), %s = firm id as JSON string.
PRICES_EXPR = '''(() => {
    const m = s.data?.market;
    if (!m) return null;
    const os = m.offersSearch?.profile?.[%s]?.data;
    return {updated: os?.updated_at ?? null, pages: os?.pages ?? 1,
            items: Object.values(m.offers ?? {}).map(o => {
                const p = m.products?.[o.data?.productId]?.data?.product;
                return p && {name: p.name ?? '', description: p.description ?? '',
                             section: (p.categories ?? []).map(c => c.label).join(' / '),
                             price: o.data.price_value ?? {}};
            }).filter(Boolean)};
})()'''


def money(rub: int) -> str:
    return f'{rub:,}'.replace(',', ' ') + ' ₽'


def parse_price(price_value: dict) -> tuple[int, bool] | None:
    """2GIS `price_value` → (rubles, is «от»). Ranges «N–M» → N."""
    for k in ('fixed', 'from', 'min'):
        v = (price_value.get(k) or {}).get('value')
        if isinstance(v, (int, float)) and v > 0:
            return int(v), k != 'fixed'
    rng = price_value.get('range') or {}
    v = rng.get('min', (rng.get('from') or {}).get('value'))
    if isinstance(v, (int, float)) and v > 0:
        return int(v), True
    return None


def parse_updated(text: str | None) -> str | None:
    """'2026-08-07T09:51:22Z' or 'Обновлено 21 января 2025' → '2025-01-21'."""
    if not text:
        return None
    if re.match(r'\d{4}-\d{2}-\d{2}', text):
        return text[:10]
    m = re.search(r'(\d{1,2})\s+(\w+)\s+(\d{4})', text)
    if m and m.group(2) in MONTHS:
        return f'{m.group(3)}-{MONTHS.index(m.group(2)) + 1:02d}-{int(m.group(1)):02d}'
    return None


def month_genitive(month: int) -> str:
    """«с января»: genitive is what MONTHS already holds."""
    return MONTHS[month - 1]


def old_prices_since(updated: Optional[str], today: date) -> Optional[str]:
    """'2025-01-21' updated over OLD_PRICES_DAYS ago → 'января 2025'; fresh or unknown → None."""
    if not updated or (today - date.fromisoformat(updated)).days <= OLD_PRICES_DAYS:
        return None
    return f'{month_genitive(int(updated[5:7]))} {updated[:4]}'
