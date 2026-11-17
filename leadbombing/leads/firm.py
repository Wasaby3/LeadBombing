"""Facts about a firm read straight from its 2GIS profile, shared by every sphere's lead builder."""
from __future__ import annotations

from typing import Any, Optional


def firm_id(item: dict) -> str:
    """2GIS firm id without the branch suffix: '70000001007499623_abc' → '70000001007499623'."""
    return item['id'].split('_')[0]


def short_name(item: dict) -> str:
    """Display name without the rubric tail («Хлебниковские бани», not «…, баня»)."""
    return ((item.get('name_ex') or {}).get('primary') or item.get('name') or '').strip()


def district_of(item: dict) -> str:
    return next((a.get('name') for a in item.get('adm_div') or [] if a.get('type') == 'district'), '')


def main_photo(item: dict) -> dict[str, Any]:
    """The firm's common photo album ({} when there is none)."""
    return next((e for e in item.get('external_content') or []
                 if e.get('type') == 'photo_album' and e.get('subtype') == 'common'), {})


def hero_url_of(item: dict) -> Optional[str]:
    return main_photo(item).get('main_photo_url')


def legal_name(item: dict, short: str) -> Optional[str]:
    """Legal entity: name_ex.legal_name, else org.name unless it is just the firm name again (may be None)."""
    org = item.get('org') or {}
    return (item.get('name_ex') or {}).get('legal_name') or \
        (org.get('name') if org.get('name') not in (short, item.get('name')) else '')
