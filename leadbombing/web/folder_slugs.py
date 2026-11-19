"""A lead's slug in a folder names its demo app: the export writes it to `tenants/<slug>/` and «Проработать лиды» puts
it at the end of the demo URL. So a slug in a folder belongs to one firm and never changes.

A run gives slugs of its own (a chain's branches are `rigla`, `rigla-2`… in the order 2GIS shows them), so saving into
a folder maps them: a firm already in the folder keeps its folder slug, a new firm keeps its run slug unless another
firm of the folder has it, then gets the next free one.
"""
from __future__ import annotations

from ..leads.text import unique


def folder_slugs(known: dict[str, str], firms: list[tuple[str, str]]) -> dict[str, str]:
    """Run slug → folder slug for `firms` [(run slug, firm id)]; `known` is firm id → slug of the folder's leads."""
    taken = set(known.values())
    result: dict[str, str] = {}
    for slug, fid in firms:
        if fid in known:
            result[slug] = known[fid]
            continue
        result[slug] = unique(slug, taken)
        taken.add(result[slug])
    return result


def with_slug(lead: dict, slug: str) -> dict:
    """A folder row ({slug, summary, card, ...}) under another slug, with every place of its card that names it."""
    if lead['slug'] == slug:
        return lead
    card = lead['card']
    return {**lead, 'slug': slug, 'summary': {**lead['summary'], 'slug': slug},
            'card': {**card,
                     'lead': {**card['lead'], 'slug': slug, 'folder': f'tenants/{slug}', 'demo_path': f'/s/{slug}/'},
                     'row': {**card['row'], 'Демо (slug)': slug},
                     'business': {**card['business'], 'slug': slug}}}
