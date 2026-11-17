"""Pieces of leads.json / business.json (the demo app's config) that are the same for every sphere."""
from __future__ import annotations

from typing import Any, Optional

OPERATOR_STUB = 'ЗАГЛУШКА: оператор ПДн'
PRIVACY_POLICY_STUB = 'https://example.com/privacy'
WORDMARK_MAX = 20


def photos_block(photo: dict[str, Any], source: str) -> dict[str, Any]:
    """leads.json `photos`: cover URL and the 2GIS album."""
    return {'hero_url': photo.get('main_photo_url'), 'album': f'{source}/tab/photos',
            'album_count': photo.get('count')}


def legal_block(legal: Optional[str]) -> dict[str, str]:
    return {'operator_name': (legal or OPERATOR_STUB)[:200], 'privacy_policy_url': PRIVACY_POLICY_STUB}


def policy_block() -> dict[str, Any]:
    return {'deposit_percent': 0, 'free_cancellation_hours': 24, 'reschedule_pricing': 'current'}


def working_hours_block(days: dict) -> dict[str, Any]:
    return {'days': days, 'max_end_after_close_min': 0}


def wordmark_main(name: str) -> str:
    """Up to WORDMARK_MAX chars, cut on a word boundary when possible."""
    if len(name) <= WORDMARK_MAX:
        return name
    return name[:WORDMARK_MAX].rsplit(' ', 1)[0] or name[:WORDMARK_MAX]


def amenities_description(amenities: list[str]) -> str:
    """«Парковка, wi-fi.» from 2GIS attributes (capitalized sentence, at most 2000 chars)."""
    return (', '.join(amenities).capitalize() + '.' if amenities else '')[:2000]


def theme_block(accent: str, hero: bool, wordmark: dict[str, str]) -> dict[str, Any]:
    """business.json `theme`: accent color, the cover when hero.jpg was downloaded, the wordmark."""
    return {'accent': accent, **({'hero': 'hero.jpg'} if hero else {}), 'wordmark': wordmark}
