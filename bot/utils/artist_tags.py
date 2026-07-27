from __future__ import annotations

# Meta / request tags — not real artists (danbooru + rule34).
INVALID_ARTIST_TAGS = frozenset({
    "unknown",
    "?",
    "artist_request",
    "translation_request",
    "commentary_request",
    "commission_request",
    "character_request",
    "copyright_request",
    "tagme",
})


def normalize_artist_tag(raw: str | None) -> str:
    return (raw or "").strip().replace(" ", "_").lower()


def is_valid_artist_tag(raw: str | None) -> bool:
    tag = normalize_artist_tag(raw)
    if not tag:
        return False
    if tag in INVALID_ARTIST_TAGS:
        return False
    if tag.endswith("_request"):
        return False
    return True
