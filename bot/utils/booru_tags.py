"""Danbooru / Rule34 tag syntax for conjure and tag lookup."""
from __future__ import annotations

import re

# Colons for rating:general, character:name, and (series:_subtag) qualifiers.
BOORU_TAG_RE = re.compile(r"^[a-z0-9_():*.\-!]+$", re.I)

_META_SEARCH_PREFIXES = (
    "rating:",
    "score:",
    "order:",
    "age:",
    "status:",
    "user:",
    "id:",
)


def is_valid_booru_tag(tag: str, *, max_len: int = 120) -> bool:
    tag = (tag or "").strip()
    if not tag or len(tag) > max_len:
        return False
    return bool(BOORU_TAG_RE.match(tag))


def is_valid_tag_query(query: str) -> bool:
    """Partial query for /check autocomplete."""
    query = (query or "").strip()
    if not query or len(query) > 80:
        return False
    return bool(BOORU_TAG_RE.match(query))


def is_meta_search_tag(tag: str) -> bool:
    low = tag.strip().lower()
    return any(low.startswith(p) for p in _META_SEARCH_PREFIXES)
