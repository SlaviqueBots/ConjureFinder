from __future__ import annotations

import re

_R34_TAG_RE = re.compile(r"^(.+?)_\([^)]+\)$")
AI_EXCLUDE = "-ai_generated"
AI_INCLUDE = "ai_generated"
GURO_EXCLUDE = "-guro"
# Skip -guro when the query is already this full (e.g. animated gif -webm -swf + -ai).
R34_MAX_QUERY_TAGS = 5


def r34_query_tag_count(query: str) -> int:
    return len((query or "").split())


def r34_tag_candidates(char: dict) -> list[str]:
    """Search tags to try on rule34 (normalized, de-duplicated)."""
    seen: set[str] = set()
    out: list[str] = []

    def add(raw: str | None) -> None:
        if not raw or raw.strip() in ("unknown", "?", ""):
            return
        tag = raw.strip().lower().replace(" ", "_")
        if tag not in seen:
            seen.add(tag)
            out.append(tag)
        m = _R34_TAG_RE.match(tag)
        if m:
            base = m.group(1)
            if base not in seen:
                seen.add(base)
                out.append(base)

    add(char.get("character_tag"))
    add(char.get("canonical_tag"))
    return out


def normalize_r34_tag(tag: str) -> str:
    """Normalize a single tag token (spaces, case, HTML entities)."""
    import html
    from urllib.parse import unquote_plus

    name = html.unescape(unquote_plus((tag or "").strip())).lower().replace(" ", "_")
    if "&#" in name or "&amp;" in name:
        name = html.unescape(name).replace(" ", "_")
    return name


def append_r34_guro_if_room(query: str) -> str:
    """Append -guro when the query is not already at the tag cap."""
    q = (query or "").strip()
    if not q or GURO_EXCLUDE in q.split():
        return q
    if r34_query_tag_count(q) >= R34_MAX_QUERY_TAGS:
        return q
    return f"{q} {GURO_EXCLUDE}"


def append_r34_default_excludes(parts: list[str]) -> list[str]:
    """Add standard r34 negated tags when there is room."""
    if AI_EXCLUDE not in parts:
        parts.append(AI_EXCLUDE)
    if r34_query_tag_count(" ".join(parts)) < R34_MAX_QUERY_TAGS:
        if GURO_EXCLUDE not in parts:
            parts.append(GURO_EXCLUDE)
    return parts


def append_r34_slopify_tags(parts: list[str]) -> list[str]:
    """Require ai_generated (slopify) and add -guro when there is room."""
    cleaned = [p for p in parts if p != AI_EXCLUDE]
    if AI_INCLUDE not in cleaned:
        cleaned.append(AI_INCLUDE)
    if r34_query_tag_count(" ".join(cleaned)) < R34_MAX_QUERY_TAGS:
        if GURO_EXCLUDE not in cleaned:
            cleaned.append(GURO_EXCLUDE)
    return cleaned


def _normalize_r34_query_parts(tags: str) -> list[str]:
    parts: list[str] = []
    for token in (tags or "").split():
        if token.startswith("-"):
            parts.append(token.lower())
        elif ":" in token:
            parts.append(token.lower())
        else:
            parts.append(normalize_r34_tag(token))
    return parts


def build_r34_query(tags: str) -> str:
    """Build rule34 search query with AI/guro posts excluded when there is room."""
    raw = (tags or "").strip()
    if not raw:
        return " ".join(append_r34_default_excludes([]))
    return " ".join(append_r34_default_excludes(_normalize_r34_query_parts(raw)))


def build_r34_slopify_query(tags: str) -> str:
    """Build rule34 search that requires ai_generated (opposite of reshape)."""
    raw = (tags or "").strip()
    if not raw:
        return " ".join(append_r34_slopify_tags([]))
    return " ".join(append_r34_slopify_tags(_normalize_r34_query_parts(raw)))


def build_r34_random_query() -> str:
    return " ".join(append_r34_default_excludes(["sort:random"]))


def prepare_r34_api_tags(tags: str) -> str:
    """Final tag string for rule34 dapi post search (skip id: lookups)."""
    q = (tags or "").strip()
    if not q or q.startswith("id:"):
        return q
    return append_r34_guro_if_room(q)
